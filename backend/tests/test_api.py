from pathlib import Path
from unittest.mock import MagicMock, patch

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "repotraverse-backend"


def test_index_repo_invalid_url():
    response = client.post("/api/index-repo", json={"github_url": "invalid-url"})
    assert response.status_code == 400
    assert "Invalid GitHub repository URL" in str(response.json()["detail"])


@patch("app.api.indexing.increment_indexing_rate_limits")
@patch("app.api.indexing.validate_github_repository")
def test_rate_limit_not_applied_on_validation_failure(
    mock_validate_repo: MagicMock,
    mock_increment_rate_limits: MagicMock,
):
    from fastapi import HTTPException

    mock_validate_repo.side_effect = HTTPException(status_code=422, detail="Repository license is not open source")

    response = client.post("/api/index-repo", json={"github_url": "https://github.com/owner/no-license-repo"})
    assert response.status_code == 422
    mock_validate_repo.assert_called_once()
    mock_increment_rate_limits.assert_not_called()


@patch("app.api.indexing.create_session_credentials")
@patch("app.api.indexing.validate_github_repository")
@patch("app.api.indexing.celery_app.send_task")
def test_index_repo_valid_url(
    mock_send_task: MagicMock,
    mock_validate_repo: MagicMock,
    mock_create_creds: MagicMock,
    tmp_path: Path,
):
    mock_validate_repo.return_value = "MIT"
    mock_create_creds.return_value = ("mock_secret_123", "mock_csrf_456")
    mock_task = MagicMock()
    mock_task.id = "test-task-123"
    mock_send_task.return_value = mock_task

    with patch("app.api.indexing.settings.shared_data_dir", str(tmp_path)):
        response = client.post("/api/index-repo", json={"github_url": "https://github.com/fastapi/fastapi"})

    assert response.status_code == 202
    data = response.json()
    assert data["task_id"] == "test-task-123"
    session_id = data["session_id"]
    assert session_id.startswith("session-")
    assert data["csrf_token"] == "mock_csrf_456"
    assert "github.com/fastapi/fastapi" in data["github_url"]
    assert f"session_secret_{session_id}=mock_secret_123" in response.headers.get("set-cookie", "")
    mock_send_task.assert_called_once()
    mock_validate_repo.assert_called_once_with("fastapi", "fastapi")


@patch("app.api.indexing.create_session_credentials")
@patch("app.api.indexing.increment_indexing_rate_limits")
@patch("app.api.indexing.acquire_concurrency_slot")
@patch("app.api.indexing.validate_github_repository")
def test_index_repo_concurrency_limit_exceeded(
    mock_validate_repo: MagicMock,
    mock_acquire_slot: MagicMock,
    mock_increment_rate_limits: MagicMock,
    mock_create_creds: MagicMock,
):
    from fastapi import HTTPException

    mock_validate_repo.return_value = "MIT"
    mock_acquire_slot.side_effect = HTTPException(status_code=429, detail="Indexing concurrency limit reached.")

    response = client.post("/api/index-repo", json={"github_url": "https://github.com/fastapi/fastapi"})
    assert response.status_code == 429
    mock_validate_repo.assert_called_once()
    mock_acquire_slot.assert_called_once()
    mock_increment_rate_limits.assert_not_called()
    mock_create_creds.assert_not_called()


@patch("app.api.indexing.release_concurrency_slot")
@patch("app.api.indexing.celery_app.send_task")
@patch("app.api.indexing.create_session_credentials")
@patch("app.api.indexing.validate_github_repository")
def test_index_repo_celery_dispatch_failure_cleans_up_session(
    mock_validate_repo: MagicMock,
    mock_create_creds: MagicMock,
    mock_send_task: MagicMock,
    mock_release_slot: MagicMock,
    tmp_path: Path,
):
    mock_validate_repo.return_value = "MIT"
    mock_send_task.side_effect = Exception("Celery connection error")

    def mock_create_creds_impl(sess_id):
        sess_dir = tmp_path / sess_id
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "session_meta.json").write_text("{}")
        return ("secret", "csrf")

    mock_create_creds.side_effect = mock_create_creds_impl

    with patch("app.api.indexing.settings.shared_data_dir", str(tmp_path)):
        response = client.post("/api/index-repo", json={"github_url": "https://github.com/fastapi/fastapi"})
        assert response.status_code == 500
        mock_release_slot.assert_called_once()
        # Verify session directory was cleaned up
        remaining_dirs = list(tmp_path.iterdir())
        assert len(remaining_dirs) == 0


@patch("app.api.indexing.AsyncResult")
def test_index_status(mock_async_result: MagicMock):
    mock_result_instance = MagicMock()
    mock_result_instance.state = "PROCESSING"
    mock_result_instance.info = {"stage": "indexing", "session_id": "session-123"}
    mock_async_result.return_value = mock_result_instance

    response = client.get("/api/index-status/test-task-123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PROCESSING"
    assert data["task_id"] == "test-task-123"
    assert data["stage"] == "indexing"


@patch("app.api.indexing.AsyncResult")
def test_index_status_failure_is_generic(mock_async_result: MagicMock):
    mock_result_instance = MagicMock()
    mock_result_instance.state = "FAILURE"
    mock_result_instance.info = RuntimeError("backend path /var/data/private leaked")
    mock_async_result.return_value = mock_result_instance

    response = client.get("/api/index-status/test-task-456")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "FAILURE"
    assert data["detail"] == "Indexing failed. Please try again."
    assert "/var/data/private" not in data["detail"]


@patch("app.api.session.validate_session_auth")
def test_clear_session_endpoint(mock_validate_session_auth: MagicMock):
    payload = {"session_id": "session-123456"}
    client.cookies.set("session_secret_session-123456", "valid_secret_123")
    response = client.post("/api/clear-session", json=payload, headers={"X-CSRF-Token": "valid_csrf_456"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "session_secret_session-123456=" in response.headers.get("set-cookie", "")
    mock_validate_session_auth.assert_called_once_with("session-123456", "valid_secret_123", "valid_csrf_456")
