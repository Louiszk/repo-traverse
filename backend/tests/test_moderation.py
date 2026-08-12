from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_check_content_moderation_passes_clean_text():
    from app.moderation import check_content_moderation

    response = SimpleNamespace(results=[SimpleNamespace(flagged=False)])
    client = MagicMock()
    client.moderations.create = AsyncMock(return_value=response)

    with patch("app.moderation.AsyncOpenAI", return_value=client) as mock_openai:
        result = await check_content_moderation("Please review this code")

    assert result.flagged is False
    assert result.categories == []
    assert result.reason is None
    mock_openai.assert_called_once()
    client.moderations.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_content_moderation_flags_violating_text():
    from app.moderation import check_content_moderation

    response = SimpleNamespace(
        results=[
            SimpleNamespace(
                flagged=True,
                categories=SimpleNamespace(model_dump=lambda: {"hate": True, "violence": False}),
            )
        ]
    )
    client = MagicMock()
    client.moderations.create = AsyncMock(return_value=response)

    with patch("app.moderation.AsyncOpenAI", return_value=client):
        result = await check_content_moderation("harmful text")

    assert result.flagged is True
    assert result.categories == ["hate"]
    assert result.reason == "Content violates safety guidelines (hate)."


@pytest.mark.asyncio
async def test_check_content_moderation_fail_open_on_error():
    from app.moderation import check_content_moderation, settings

    client = MagicMock()
    client.moderations.create = AsyncMock(side_effect=RuntimeError("network failure"))

    with patch("app.moderation.AsyncOpenAI", return_value=client), patch.object(settings, "moderation_fail_open", True):
        result = await check_content_moderation("text")

    assert result.flagged is False


@pytest.mark.asyncio
async def test_check_content_moderation_fail_closed_on_error():
    from app.moderation import check_content_moderation, settings

    client = MagicMock()
    client.moderations.create = AsyncMock(side_effect=RuntimeError("network failure"))

    with (
        patch("app.moderation.AsyncOpenAI", return_value=client),
        patch.object(settings, "moderation_fail_open", False),
    ):
        result = await check_content_moderation("text")

    assert result.flagged is True
    assert result.reason == "Moderation service is temporarily unavailable. Please try again later."


def test_chat_stream_blocks_flagged_content():
    client = TestClient(app)

    with (
        patch("app.api.chat.validate_session_auth"),
        patch("app.api.chat.get_human_message_count", return_value=0),
        patch("app.api.chat.get_session_token_count", return_value=0),
        patch(
            "app.api.chat.check_content_moderation",
            return_value=SimpleNamespace(flagged=True, reason="Content violates safety guidelines (hate)."),
        ),
    ):
        payload = {"session_id": "session-flagged", "message": "bad content"}
        client.cookies.set("session_secret_session-flagged", "secret")
        response = client.post("/api/chat/stream", json=payload, headers={"X-CSRF-Token": "csrf"})

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Your message couldn't be sent because it doesn't meet our content guidelines. Please rephrase and try again."
    }
