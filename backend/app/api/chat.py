import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.agent import (
    _get_safe_context_limit,
    get_human_message_count,
    get_session_token_count,
    stream_chat_with_agent,
)
from app.config import settings
from app.logger import logger
from app.models import ChatRequest
from app.moderation import check_content_moderation
from app.session import validate_session_auth

router = APIRouter(tags=["API"])

MODERATION_REJECTION_MESSAGE = (
    "Your message couldn't be sent because it doesn't meet our content guidelines. Please rephrase and try again."
)


def _get_expired_cookie_header(cookie_name: str) -> dict[str, str]:
    """Helper to construct Set-Cookie expiration header for exception objects."""
    sec_flag = "; Secure" if settings.cookie_secure else ""
    return {
        "Set-Cookie": f"{cookie_name}=; Max-Age=0; Path=/api; HttpOnly; SameSite={settings.cookie_samesite}{sec_flag}"
    }


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
):
    """Streams tool execution events and agent response via Server-Sent Events (SSE)."""
    session_id = payload.session_id.strip()
    message = payload.message.strip()

    if not session_id or not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'session_id' and 'message' must be non-empty strings.",
        )

    cookie_name = f"{settings.session_cookie_name}_{session_id}"
    cookie_secret = request.cookies.get(cookie_name)

    try:
        validate_session_auth(session_id, cookie_secret, csrf_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            exc.headers = _get_expired_cookie_header(cookie_name)
        raise

    if get_human_message_count(session_id) >= settings.max_messages_per_session:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session message limit reached.")

    safe_limit = _get_safe_context_limit()
    if get_session_token_count(session_id) >= safe_limit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Context full, start a new session")

    mod_result = await check_content_moderation(message)
    if mod_result.flagged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=MODERATION_REJECTION_MESSAGE,
        )

    logger.info(f"Streaming chat message for session {session_id}")

    async def event_generator():
        async for event in stream_chat_with_agent(session_id, message):
            yield f"data: {json.dumps(event)}\n\n"

    streaming_res = StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
    streaming_res.set_cookie(
        key=cookie_name,
        value=cookie_secret or "",
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        max_age=settings.repo_max_age_seconds,
        path="/api",
    )
    return streaming_res
