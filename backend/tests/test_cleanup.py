import os
import time
from pathlib import Path
from unittest.mock import patch

from app.cleanup import cleanup_repositories
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def create_dummy_session(base_dir: Path, session_name: str, age_seconds: float, size_bytes: int = 100) -> Path:
    """Helper creating a dummy session directory with specified age and file size."""
    session_dir = base_dir / session_name
    session_dir.mkdir(parents=True, exist_ok=True)
    file_path = session_dir / "data.bin"
    file_path.write_bytes(b"A" * size_bytes)

    target_mtime = time.time() - age_seconds
    os.utime(session_dir, (target_mtime, target_mtime))
    os.utime(file_path, (target_mtime, target_mtime))
    return session_dir


def test_cleanup_expired_repositories(tmp_path: Path):
    """Test that sessions older than repo_max_age_seconds are deleted while younger ones remain."""
    with (
        patch("app.cleanup.settings.shared_data_dir", str(tmp_path)),
        patch("app.cleanup.settings.repo_max_age_seconds", 7200),
    ):
        s_old = create_dummy_session(tmp_path, "session-old1", age_seconds=8000)
        s_new = create_dummy_session(tmp_path, "session-new1", age_seconds=1000)

        res = cleanup_repositories()

        assert "session-old1" in res["deleted_sessions"]
        assert "session-new1" not in res["deleted_sessions"]
        assert not s_old.exists()
        assert s_new.exists()


def test_cleanup_fifo_threshold(tmp_path: Path):
    """Test that when total storage exceeds GB threshold, oldest sessions are deleted FIFO."""
    # Threshold = 250 bytes (~0.00000023 GB)
    threshold_gb = 250 / (1024 * 1024 * 1024)

    with (
        patch("app.cleanup.settings.shared_data_dir", str(tmp_path)),
        patch("app.cleanup.settings.repo_max_age_seconds", 86400),
        patch("app.cleanup.settings.repo_storage_threshold_gb", threshold_gb),
    ):
        # Create 4 sessions of 100 bytes each, aged 400s, 300s, 200s, 100s ago
        s1 = create_dummy_session(tmp_path, "session-oldest", age_seconds=400, size_bytes=100)
        s2 = create_dummy_session(tmp_path, "session-older", age_seconds=300, size_bytes=100)
        s3 = create_dummy_session(tmp_path, "session-newer", age_seconds=200, size_bytes=100)
        s4 = create_dummy_session(tmp_path, "session-newest", age_seconds=100, size_bytes=100)

        res = cleanup_repositories()

        # To get under 250 bytes, two sessions (200 bytes total) must be deleted FIFO (s1 and s2)
        assert res["deleted_sessions"] == ["session-oldest", "session-older"]
        assert not s1.exists()
        assert not s2.exists()
        assert s3.exists()
        assert s4.exists()
        assert res["remaining_sessions_count"] == 2


def test_cleanup_api_endpoint_is_not_public(tmp_path: Path):
    """Repository cleanup is scheduled-only and should not be exposed over HTTP."""
    with (
        patch("app.cleanup.settings.shared_data_dir", str(tmp_path)),
        patch("app.cleanup.settings.repo_max_age_seconds", 3600),
    ):
        create_dummy_session(tmp_path, "session-expired", age_seconds=5000, size_bytes=50)

        response = client.post("/api/cleanup-repos")
        assert response.status_code == 404
