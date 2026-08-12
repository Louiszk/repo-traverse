from pathlib import Path
from unittest.mock import MagicMock, patch

from app.main import app
from app.session import create_session_credentials
from fastapi.testclient import TestClient

client = TestClient(app)


@patch("app.api.chat.validate_session_auth")
@patch("app.api.chat.stream_chat_with_agent")
def test_chat_stream_endpoint_tool_status(mock_stream_chat: MagicMock, mock_validate_session_auth: MagicMock):
    async def mock_generator(session_id, message):
        yield {"type": "tool_start", "tool": "search_code", "args": {"query": "test"}}
        yield {"type": "tool_end", "tool": "search_code", "status": "error", "output": "Error: Connection failed"}
        yield {"type": "final_reply", "reply": "Finished", "tool_calls": []}

    mock_stream_chat.side_effect = mock_generator
    payload = {"session_id": "session-stream123", "message": "Run search"}
    client.cookies.set("session_secret_session-stream123", "valid_secret_123")
    response = client.post("/api/chat/stream", json=payload, headers={"X-CSRF-Token": "valid_csrf_456"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    content = response.text
    assert '"type": "tool_end"' in content
    assert '"status": "error"' in content


def test_chat_stream_endpoint_unauthorized_missing_cookie(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        secret, csrf = create_session_credentials("session-active123")
        payload = {"session_id": "session-active123", "message": "How does routing work?"}

        client.cookies.clear()
        response = client.post("/api/chat/stream", json=payload, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 401

        client.cookies.set("session_secret_session-active123", secret)
        response = client.post("/api/chat/stream", json=payload)
        assert response.status_code == 403
