from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from app.config import settings
from app.models import ClearSessionRequest
from app.session import validate_session_auth

router = APIRouter(tags=["API"])


def _delete_session_cookie(response: Response, cookie_name: str) -> None:
    """Helper to delete a session cookie matching all security attributes."""
    response.delete_cookie(
        key=cookie_name,
        path="/api",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


@router.post("/clear-session", status_code=status.HTTP_200_OK)
def clear_session(
    payload: ClearSessionRequest,
    request: Request,
    response: Response,
    csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
):
    """Clears the session authentication cookie after validating session credentials."""
    session_id = payload.session_id.strip()
    cookie_name = f"{settings.session_cookie_name}_{session_id}"
    cookie_secret = request.cookies.get(cookie_name)

    try:
        validate_session_auth(session_id, cookie_secret, csrf_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            _delete_session_cookie(response, cookie_name)
            return {"status": "ok", "message": "Session already expired"}
        raise

    _delete_session_cookie(response, cookie_name)
    return {"status": "ok", "message": f"Session '{session_id}' cleared"}
