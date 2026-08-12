import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from app.celery_app import celery_app
from app.cleanup import cleanup_repositories, cleanup_traces
from app.config import settings
from app.logger import logger
from app.redis_client import get_redis_client
from app.session import get_project_name_from_session_db, update_session_metadata
from app.tools import get_saved_schema
from app.utils import handle_remove_readonly, run_isolated_subprocess


def _update_stage(task, stage: str, session_id: str) -> None:
    """Safely updates Celery task state if running within a valid task request context."""
    if getattr(task, "request", None) and getattr(task.request, "id", None):
        task.update_state(state="PROCESSING", meta={"stage": stage, "session_id": session_id})


@celery_app.task(name="app.tasks.cleanup_repositories")
def cleanup_repositories_task() -> dict:
    """Periodically cleans up expired sessions and traces, then enforces FIFO storage capacity thresholds."""
    logger.info("Executing periodic repository and traces cleanup task")
    repo_res = cleanup_repositories()
    trace_res = cleanup_traces()
    return {"repositories": repo_res, "traces": trace_res}


@celery_app.task(
    bind=True,
    name="app.tasks.index_repository",
    soft_time_limit=settings.clone_timeout_seconds + settings.index_timeout_seconds + 15,
    time_limit=settings.clone_timeout_seconds + settings.index_timeout_seconds + 30,
)
def index_repository_task(self, github_url: str, session_id: str) -> dict:
    """Clone a GitHub repository, index it with codebase-memory-mcp in bounded scratch space, and persist the graph artifact and source files."""
    scratch_session_dir = None
    final_session_dir = Path(settings.shared_data_dir) / session_id
    try:
        scratch_session_dir = Path(settings.scratch_data_dir) / session_id
        clone_dir = scratch_session_dir / "repo"
        final_clone_dir = final_session_dir / "repo"
        scratch_session_dir.mkdir(parents=True, exist_ok=True)

        _update_stage(self, "cloning", session_id)
        logger.info(f"Cloning {github_url} into scratch directory {clone_dir}")

        clone_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": "/tmp",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ALLOW_PROTOCOL": "https",
        }
        if "SystemRoot" in os.environ:
            clone_env["SystemRoot"] = os.environ["SystemRoot"]

        clone_result = run_isolated_subprocess(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--",
                github_url,
                str(clone_dir),
            ],
            env=clone_env,
            timeout=settings.clone_timeout_seconds,
        )

        if clone_result.returncode != 0:
            logger.error(f"git clone failed for {github_url} (session {session_id}): {clone_result.stderr.strip()}")
            raise RuntimeError("Git repository cloning failed. Please check the repository URL and accessibility.")

        git_dir = clone_dir / ".git"
        if git_dir.exists():
            logger.info(f"Removing git metadata from cloned repository at {git_dir}")
            shutil.rmtree(git_dir, onerror=handle_remove_readonly)

        logger.info(f"Sanitizing cloned repository at {clone_dir}")
        file_count = 0
        total_bytes = 0
        max_bytes = settings.max_repo_size_mb * 1024 * 1024

        for file_path in clone_dir.rglob("*"):
            if file_path.is_symlink():
                file_path.unlink()
                continue

            if file_path.is_file():
                file_count += 1
                if file_count > 10_000:
                    raise RuntimeError(f"Repository exceeds the 10,000 maximum file limit ({file_count} found).")

                try:
                    total_bytes += file_path.stat().st_size
                except OSError:
                    pass

                if total_bytes > max_bytes:
                    size_mb = total_bytes / (1024 * 1024)
                    raise RuntimeError(
                        f"Unpacked repository size ({size_mb:.1f} MB) exceeds maximum allowed limit ({settings.max_repo_size_mb} MB)."
                    )

        _update_stage(self, "indexing", session_id)
        logger.info(f"Indexing repository at {clone_dir}")

        subprocess_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": "/tmp",
            "CBM_CACHE_DIR": str(scratch_session_dir),
        }

        index_result = run_isolated_subprocess(
            ["codebase-memory-mcp", "cli", "index_repository", "--repo-path", str(clone_dir)],
            env=subprocess_env,
            timeout=settings.index_timeout_seconds,
        )

        if index_result.returncode != 0:
            logger.error(f"CBM indexing failed for session {session_id}: {index_result.stderr.strip()}")
            raise RuntimeError("Repository indexing failed. Please ensure the repository is valid.")

        _update_stage(self, "finalizing", session_id)

        graph_files = list(scratch_session_dir.rglob("*.db")) + list(scratch_session_dir.rglob("*.db.zst"))
        if not graph_files:
            raise RuntimeError("No graph database file found after indexing")

        max_graph_bytes = settings.max_graph_db_size_mb * 1024 * 1024
        total_graph_bytes = sum(f.stat().st_size for f in graph_files if f.is_file())
        if total_graph_bytes > max_graph_bytes:
            db_size_mb = total_graph_bytes / (1024 * 1024)
            raise RuntimeError(
                f"Generated knowledge graph database is too large ({db_size_mb:.1f} MB exceeds {settings.max_graph_db_size_mb} MB limit)."
            )

        # Update root_path in SQLite database so get_code_snippet resolves source files from final_session_dir
        for db_file in scratch_session_dir.rglob("*.db"):
            try:
                conn = sqlite3.connect(db_file)
                try:
                    conn.execute("UPDATE projects SET root_path = ?", (str(final_clone_dir),))
                    conn.commit()
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to update root_path in SQLite DB {db_file}: {exc}")

        # Move approved artifacts (repo + graph DB) into final_session_dir while preserving session_meta.json created by API
        final_session_dir.mkdir(parents=True, exist_ok=True)
        for item in scratch_session_dir.iterdir():
            target = final_session_dir / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target, onerror=handle_remove_readonly)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))
        shutil.rmtree(scratch_session_dir, onerror=handle_remove_readonly)
        scratch_session_dir = None

        # Pre-cache static graph schema for the session so agent system prompt loading is instant
        project_name = get_project_name_from_session_db(final_session_dir)
        if project_name:
            update_session_metadata(session_id, project_name=project_name)
        else:
            logger.warning(f"Failed to cache project name for session {session_id}: no project DB found")

        get_saved_schema(session_id)

        final_graph_files = list(final_session_dir.rglob("*.db")) + list(final_session_dir.rglob("*.db.zst"))
        graph_name = final_graph_files[0].name if final_graph_files else "graph artifact"
        logger.info(f"Indexing complete for session {session_id} with graph artifact {graph_name}")

        return {
            "status": "success",
            "session_id": session_id,
            "github_url": github_url,
        }

    except subprocess.TimeoutExpired as exc:
        logger.error(f"Timeout during indexing for session {session_id}: {exc}")
        if final_session_dir and final_session_dir.exists():
            shutil.rmtree(final_session_dir, onerror=handle_remove_readonly)
        raise
    except Exception as exc:
        logger.error(f"Indexing failed for session {session_id}: {exc}")
        if final_session_dir and final_session_dir.exists():
            shutil.rmtree(final_session_dir, onerror=handle_remove_readonly)
        raise
    finally:
        if scratch_session_dir and scratch_session_dir.exists():
            shutil.rmtree(scratch_session_dir, onerror=handle_remove_readonly)
        get_redis_client().decr("celery_active_tasks")
