import shutil
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.logger import logger
from app.utils import handle_remove_readonly


def get_dir_size(path: Path) -> int:
    """Calculates total byte size of all files inside a directory recursively."""
    total = 0
    if not path.exists():
        return 0
    try:
        for file in path.rglob("*"):
            try:
                if file.is_file() and not file.is_symlink():
                    total += file.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def cleanup_repositories() -> dict[str, Any]:
    """
    Cleans up indexed repository session directories from shared_data_dir:
    1. Deletes session directories older than settings.repo_max_age_seconds (age-based).
    2. Deletes oldest remaining session directories FIFO if total storage exceeds settings.repo_storage_threshold_gb.
    """
    data_dir = Path(settings.shared_data_dir)
    if not data_dir.exists():
        return {
            "status": "success",
            "deleted_sessions": [],
            "freed_bytes": 0,
            "remaining_sessions_count": 0,
            "remaining_bytes": 0,
        }

    now = time.time()
    max_age_seconds = settings.repo_max_age_seconds
    threshold_bytes = int(settings.repo_storage_threshold_gb * 1024 * 1024 * 1024)

    deleted_sessions: list[str] = []
    freed_bytes = 0

    session_entries: list[dict[str, Any]] = []

    for path in data_dir.iterdir():
        if path.is_dir() and (path.name.startswith("session-") or path.name.startswith("app-data-session")):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = now
            size = get_dir_size(path)
            session_entries.append(
                {
                    "path": path,
                    "session_id": path.name,
                    "mtime": mtime,
                    "size": size,
                }
            )

    # 1. Age-based eviction
    remaining_sessions: list[dict[str, Any]] = []
    for item in session_entries:
        age = now - item["mtime"]
        if age > max_age_seconds:
            logger.info(
                f"Evicting expired repository session {item['session_id']} (age: {age:.0f}s > {max_age_seconds}s)"
            )
            try:
                shutil.rmtree(item["path"], onerror=handle_remove_readonly)
                deleted_sessions.append(item["session_id"])
                freed_bytes += item["size"]
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to remove expired session directory {item['path']}: {exc}")
        else:
            remaining_sessions.append(item)

    # Sort remaining sessions by mtime ascending (oldest first for FIFO)
    remaining_sessions.sort(key=lambda x: x["mtime"])

    # 2. FIFO Storage Limit Eviction
    total_remaining_size = sum(item["size"] for item in remaining_sessions)
    idx = 0
    while total_remaining_size > threshold_bytes and idx < len(remaining_sessions):
        oldest = remaining_sessions[idx]
        logger.info(
            f"Storage threshold exceeded ({total_remaining_size} bytes > {threshold_bytes} bytes). "
            f"Evicting session {oldest['session_id']} FIFO."
        )
        try:
            shutil.rmtree(oldest["path"], onerror=handle_remove_readonly)
            deleted_sessions.append(oldest["session_id"])
            freed_bytes += oldest["size"]
            total_remaining_size -= oldest["size"]
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to remove FIFO session directory {oldest['path']}: {exc}")
        idx += 1

    final_remaining = remaining_sessions[idx:]
    final_count = len(final_remaining)
    final_bytes = sum(item["size"] for item in final_remaining)

    if deleted_sessions:
        logger.info(
            f"Cleanup complete: removed {len(deleted_sessions)} sessions, freed {freed_bytes} bytes. "
            f"Remaining: {final_count} sessions ({final_bytes} bytes)."
        )

    return {
        "status": "success",
        "deleted_sessions": deleted_sessions,
        "freed_bytes": freed_bytes,
        "remaining_sessions_count": final_count,
        "remaining_bytes": final_bytes,
    }


def cleanup_traces() -> dict[str, Any]:
    """
    Cleans up stored trace `.jsonl` files from shared_data_dir / "traces".
    1. Deletes trace files older than settings.traces_max_age_seconds.
    2. Deletes oldest remaining trace files FIFO if total size exceeds settings.traces_storage_threshold_gb.
    """
    traces_dir = Path(settings.shared_data_dir) / "traces"
    if not traces_dir.exists():
        return {
            "status": "success",
            "deleted_traces": [],
            "freed_bytes": 0,
            "remaining_traces_count": 0,
            "remaining_bytes": 0,
        }

    max_age_seconds = settings.traces_max_age_seconds
    threshold_bytes = int(settings.traces_storage_threshold_gb * 1024 * 1024 * 1024)
    target_bytes = int(threshold_bytes * 0.9)

    trace_files: list[dict[str, Any]] = []
    now = time.time()

    for path in traces_dir.glob("*.jsonl"):
        if path.is_file():
            try:
                mtime = path.stat().st_mtime
                size = path.stat().st_size
            except OSError:
                mtime = now
                size = 0
            trace_files.append(
                {
                    "path": path,
                    "name": path.name,
                    "mtime": mtime,
                    "size": size,
                }
            )

    total_bytes = sum(item["size"] for item in trace_files)
    deleted_traces: list[str] = []
    freed_bytes = 0

    remaining_files: list[dict[str, Any]] = []

    for item in trace_files:
        age = now - item["mtime"]
        if age > max_age_seconds:
            logger.info(f"Evicting expired trace file {item['name']} (age: {age:.0f}s > {max_age_seconds}s)")
            try:
                item["path"].unlink(missing_ok=True)
                deleted_traces.append(item["name"])
                freed_bytes += item["size"]
                total_bytes -= item["size"]
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to remove expired trace file {item['path']}: {exc}")
        else:
            remaining_files.append(item)

    remaining_files.sort(key=lambda x: x["mtime"])
    total_bytes = sum(item["size"] for item in remaining_files)

    if total_bytes > threshold_bytes:
        idx = 0
        while total_bytes > target_bytes and idx < len(remaining_files):
            oldest = remaining_files[idx]
            logger.info(
                f"Traces storage threshold exceeded ({total_bytes} bytes > {threshold_bytes} bytes). "
                f"Evicting trace file {oldest['name']} FIFO."
            )
            try:
                oldest["path"].unlink(missing_ok=True)
                deleted_traces.append(oldest["name"])
                freed_bytes += oldest["size"]
                total_bytes -= oldest["size"]
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to remove trace file {oldest['path']}: {exc}")
            idx += 1
        remaining_files = remaining_files[idx:]

    final_count = len(remaining_files)
    final_bytes = sum(item["size"] for item in remaining_files)

    if deleted_traces:
        logger.info(
            f"Traces cleanup complete: removed {len(deleted_traces)} files, freed {freed_bytes} bytes. "
            f"Remaining: {final_count} trace files ({final_bytes} bytes)."
        )

    return {
        "status": "success",
        "deleted_traces": deleted_traces,
        "freed_bytes": freed_bytes,
        "remaining_traces_count": final_count,
        "remaining_bytes": final_bytes,
    }
