import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.tasks import index_repository_task


@patch("app.tasks.run_isolated_subprocess")
def test_index_repository_task_success(mock_subprocess: MagicMock, tmp_path: Path):
    scratch_dir = tmp_path / "scratch"
    final_dir = tmp_path / "data"
    with (
        patch("app.tasks.settings.scratch_data_dir", str(scratch_dir)),
        patch("app.tasks.settings.shared_data_dir", str(final_dir)),
    ):
        mock_clone = MagicMock()
        mock_clone.returncode = 0

        mock_index = MagicMock()
        mock_index.returncode = 0

        session_id = "session-test123"
        scratch_session_dir = scratch_dir / session_id
        final_session_dir = final_dir / session_id
        final_session_dir.mkdir(parents=True, exist_ok=True)
        meta_file = final_session_dir / "session_meta.json"
        meta_file.write_text('{"session_id": "session-test123"}', encoding="utf-8")

        def mock_run_impl(cmd, *args, **kwargs):
            if "clone" in cmd:
                assert "--" in cmd
                assert cmd.index("--") < cmd.index("https://github.com/owner/repo")
                git_metadata_dir = scratch_session_dir / "repo" / ".git"
                git_metadata_dir.mkdir(parents=True, exist_ok=True)
                (git_metadata_dir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
                (scratch_session_dir / "repo" / "src").mkdir(parents=True, exist_ok=True)
                return mock_clone
            scratch_session_dir.mkdir(parents=True, exist_ok=True)
            db_path = scratch_session_dir / "repo.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE projects (name TEXT, indexed_at TEXT, root_path TEXT)")
                conn.execute(
                    "INSERT INTO projects VALUES ('test', '2026-07-31', ?)",
                    (str(scratch_session_dir / "repo"),),
                )
                conn.commit()
            finally:
                conn.close()
            return mock_index

        mock_subprocess.side_effect = mock_run_impl

        res = index_repository_task.run("https://github.com/owner/repo", session_id)  # pyright: ignore[reportFunctionMemberAccess]

        assert res["status"] == "success"
        assert res["session_id"] == session_id
        assert (final_session_dir / "repo").exists()
        assert (final_session_dir / "repo.db").exists()
        assert not (final_session_dir / "repo" / ".git").exists()

        # Verify root_path in SQLite DB was updated to final_session_dir / "repo"
        conn = sqlite3.connect(final_session_dir / "repo.db")
        try:
            cur = conn.execute("SELECT root_path FROM projects")
            row = cur.fetchone()
            assert row[0] == str(final_session_dir / "repo")
        finally:
            conn.close()

        # Verify session_meta.json is preserved
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        assert meta["session_id"] == "session-test123"
        assert meta["project_name"] == "test"
        # Verify scratch directory was cleaned up after move
        assert not scratch_session_dir.exists()


@patch("app.tasks.run_isolated_subprocess")
def test_index_repository_task_graph_db_too_large(mock_subprocess: MagicMock, tmp_path: Path):
    scratch_dir = tmp_path / "scratch"
    final_dir = tmp_path / "data"
    with (
        patch("app.tasks.settings.scratch_data_dir", str(scratch_dir)),
        patch("app.tasks.settings.shared_data_dir", str(final_dir)),
        patch("app.tasks.settings.max_graph_db_size_mb", 1),
    ):
        mock_clone = MagicMock()
        mock_clone.returncode = 0

        mock_index = MagicMock()
        mock_index.returncode = 0

        session_id = "session-test-large-db"
        scratch_session_dir = scratch_dir / session_id

        def mock_run_impl(cmd, *args, **kwargs):
            if "clone" in cmd:
                (scratch_session_dir / "repo").mkdir(parents=True, exist_ok=True)
                return mock_clone
            scratch_session_dir.mkdir(parents=True, exist_ok=True)
            # Write a dummy DB file larger than 1 MB (1.5 MB)
            large_db = scratch_session_dir / "repo.db"
            large_db.write_bytes(b"0" * int(1.5 * 1024 * 1024))
            return mock_index

        mock_subprocess.side_effect = mock_run_impl

        import pytest

        with pytest.raises(RuntimeError, match="Generated knowledge graph database is too large"):
            index_repository_task.run("https://github.com/owner/repo", session_id)  # pyright: ignore[reportFunctionMemberAccess]


@patch("app.tasks.run_isolated_subprocess")
def test_index_repository_task_git_clone_clean_user_error(mock_subprocess: MagicMock, tmp_path: Path):
    scratch_dir = tmp_path / "scratch"
    final_dir = tmp_path / "data"
    with (
        patch("app.tasks.settings.scratch_data_dir", str(scratch_dir)),
        patch("app.tasks.settings.shared_data_dir", str(final_dir)),
    ):
        mock_clone = MagicMock()
        mock_clone.returncode = 1
        mock_clone.stderr = "fatal: repository not found\nDetailed stacktrace leaking /var/secret/path"
        mock_subprocess.return_value = mock_clone

        session_id = "session-test-clone-fail"

        import pytest

        with pytest.raises(RuntimeError) as exc_info:
            index_repository_task.run("https://github.com/owner/repo", session_id)  # pyright: ignore[reportFunctionMemberAccess]

        assert "Git repository cloning failed. Please check the repository URL and accessibility." in str(
            exc_info.value
        )
        assert "/var/secret/path" not in str(exc_info.value)
