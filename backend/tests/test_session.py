import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from app.main import app
from app.session import create_session_credentials, touch_session, validate_session_auth
from fastapi import HTTPException
from fastapi.testclient import TestClient

client = TestClient(app)


def test_touch_session_valid_updates_mtime(tmp_path: Path):
    """Test that touch_session updates mtime for existing session directories."""
    session_dir = tmp_path / "session-active123"
    session_dir.mkdir(parents=True, exist_ok=True)

    old_mtime = time.time() - 3600
    os.utime(session_dir, (old_mtime, old_mtime))

    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        res_dir = touch_session("session-active123")
        assert res_dir == session_dir
        new_mtime = session_dir.stat().st_mtime
        assert new_mtime > old_mtime + 3000


def test_touch_session_missing_raises_404(tmp_path: Path):
    """Test that touch_session raises HTTP 404 for non-existent session directories."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        with pytest.raises(HTTPException) as exc_info:
            touch_session("session-expired999")
        assert exc_info.value.status_code == 404
        assert "Session has expired" in exc_info.value.detail


def test_chat_stream_endpoint_missing_session_returns_404(tmp_path: Path):
    """Test POST /api/chat/stream returns HTTP 404 when session directory is missing/expired."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        response = client.post(
            "/api/chat/stream",
            json={
                "session_id": "session-nonexistent",
                "message": "Hello codebase",
            },
        )
        assert response.status_code == 404
        assert "Session has expired due to inactivity" in response.json()["detail"]


def test_touch_session_path_traversal_rejection(tmp_path: Path):
    """Test that path traversal attempts in session_id are rejected with HTTP 400."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        with pytest.raises(HTTPException) as exc_info:
            touch_session("../../../etc")
        assert exc_info.value.status_code == 400
        assert "Invalid session ID format" in exc_info.value.detail


def test_create_session_credentials(tmp_path: Path):
    """Test create_session_credentials generates and persists session credentials."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        secret, csrf = create_session_credentials("session-test12345")
        assert len(secret) == 64
        assert len(csrf) == 64

        meta_file = tmp_path / "session-test12345" / "session_meta.json"
        assert meta_file.exists()


def test_validate_session_auth_success(tmp_path: Path):
    """Test validate_session_auth succeeds with valid cookie and CSRF token."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        secret, csrf = create_session_credentials("session-test12345")
        session_dir = validate_session_auth("session-test12345", secret, csrf)
        assert session_dir == (tmp_path / "session-test12345")


def test_validate_session_auth_invalid_cookie(tmp_path: Path):
    """Test validate_session_auth raises 401 for missing or mismatched cookie."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        _secret, csrf = create_session_credentials("session-test12345")

        with pytest.raises(HTTPException) as exc_missing:
            validate_session_auth("session-test12345", None, csrf)
        assert exc_missing.value.status_code == 401
        assert "missing session cookie" in exc_missing.value.detail

        with pytest.raises(HTTPException) as exc_invalid:
            validate_session_auth("session-test12345", "wrong-secret", csrf)
        assert exc_invalid.value.status_code == 401
        assert "Invalid or missing session cookie" in exc_invalid.value.detail


def test_validate_session_auth_invalid_csrf(tmp_path: Path):
    """Test validate_session_auth raises 403 for missing or mismatched CSRF token."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        secret, _csrf = create_session_credentials("session-test12345")

        with pytest.raises(HTTPException) as exc_missing:
            validate_session_auth("session-test12345", secret, None)
        assert exc_missing.value.status_code == 403
        assert "missing CSRF token" in exc_missing.value.detail

        with pytest.raises(HTTPException) as exc_invalid:
            validate_session_auth("session-test12345", secret, "wrong-csrf")
        assert exc_invalid.value.status_code == 403
        assert "Invalid or missing CSRF token" in exc_invalid.value.detail


def test_unauthenticated_request_does_not_touch_mtime(tmp_path: Path):
    """Test that failed authentication does not update the session directory mtime."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        _secret, csrf = create_session_credentials("session-mtime123")
        session_dir = tmp_path / "session-mtime123"

        old_mtime = time.time() - 3600
        os.utime(session_dir, (old_mtime, old_mtime))

        with pytest.raises(HTTPException):
            validate_session_auth("session-mtime123", "wrong_secret", csrf)

        assert session_dir.stat().st_mtime == old_mtime


def test_get_tree_content_success(tmp_path: Path):
    """Test GET /api/tree returns sorted directories first, then files, skipping .git."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        secret, csrf = create_session_credentials("session-tree123")
        repo_dir = tmp_path / "session-tree123" / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        (repo_dir / "src").mkdir()
        (repo_dir / "docs").mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / "README.md").write_text("hello")
        (repo_dir / "main.py").write_text("print('hi')")

        client.cookies.set("session_secret_session-tree123", secret)
        response = client.get(
            "/api/tree?session_id=session-tree123&path=",
            headers={"X-CSRF-Token": csrf},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4
        # Folders first (docs, src), then files (main.py, README.md)
        assert data[0] == {"name": "docs", "path": "docs", "is_dir": True}
        assert data[1] == {"name": "src", "path": "src", "is_dir": True}
        assert data[2] == {"name": "main.py", "path": "main.py", "is_dir": False}
        assert data[3] == {"name": "README.md", "path": "README.md", "is_dir": False}


def test_get_tree_content_path_traversal(tmp_path: Path):
    """Test GET /api/tree rejects path traversal attempts with HTTP 403."""
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        secret, csrf = create_session_credentials("session-tree456")
        repo_dir = tmp_path / "session-tree456" / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        client.cookies.set("session_secret_session-tree456", secret)
        response = client.get(
            "/api/tree?session_id=session-tree456&path=../../",
            headers={"X-CSRF-Token": csrf},
        )

        assert response.status_code == 403
        assert "Path traversal attempt detected" in response.json()["detail"]


def test_get_symbol_content_success(tmp_path: Path):
    """Test GET /api/symbol invokes _run_cbm_cli and returns symbol snippet."""
    with (
        patch("app.session.settings.shared_data_dir", str(tmp_path)),
        patch("app.api.repository._run_cbm_cli", return_value="def my_func(): pass") as mock_cli,
    ):
        secret, csrf = create_session_credentials("session-symbol123")
        (tmp_path / "session-symbol123").mkdir(exist_ok=True)

        client.cookies.set("session_secret_session-symbol123", secret)
        response = client.get(
            "/api/symbol?session_id=session-symbol123&symbol=app.my_func",
            headers={"X-CSRF-Token": csrf},
        )

        assert response.status_code == 200
        assert response.json() == {
            "content": "def my_func(): pass",
            "symbol": "app.my_func",
        }
        mock_cli.assert_called_once_with("session-symbol123", "get_code_snippet", ["--qualified-name", "app.my_func"])
