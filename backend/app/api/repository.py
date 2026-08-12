import json

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.config import settings
from app.file_access import FileAccessError, read_secure_text_file
from app.models import FileContentResponse, SymbolContentResponse, TreeItem
from app.session import validate_session_auth
from app.tools import _run_cbm_cli

router = APIRouter(tags=["API"])


def _get_expired_cookie_header(cookie_name: str) -> dict[str, str]:
    """Helper to construct Set-Cookie expiration header for exception objects."""
    sec_flag = "; Secure" if settings.cookie_secure else ""
    return {
        "Set-Cookie": f"{cookie_name}=; Max-Age=0; Path=/api; HttpOnly; SameSite={settings.cookie_samesite}{sec_flag}"
    }


@router.get("/file", response_model=FileContentResponse, status_code=status.HTTP_200_OK)
def get_file_content(
    request: Request,
    session_id: str = Query(..., description="Active session ID"),
    file_path: str = Query(..., description="Relative file path within repository"),
    csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
):
    """Retrieves text content of a file from the session repository with path traversal protection."""
    clean_session_id = session_id.strip()
    clean_file_path = file_path.strip()

    if not clean_session_id or not clean_file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'session_id' and 'file_path' must be non-empty strings.",
        )

    cookie_name = f"{settings.session_cookie_name}_{clean_session_id}"
    cookie_secret = request.cookies.get(cookie_name)

    try:
        session_dir = validate_session_auth(clean_session_id, cookie_secret, csrf_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            exc.headers = _get_expired_cookie_header(cookie_name)
        raise

    try:
        result = read_secure_text_file(session_dir / "repo", clean_file_path)
    except FileAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return FileContentResponse(content=result.content, file_path=clean_file_path)


@router.get("/tree", response_model=list[TreeItem], status_code=status.HTTP_200_OK)
def get_tree_content(
    request: Request,
    session_id: str = Query(..., description="Active session ID"),
    path: str = Query("", description="Relative directory path within repository"),
    csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
):
    """Retrieves list of files and folders in a repository directory with path traversal protection."""
    clean_session_id = session_id.strip()
    clean_path = path.strip()

    if not clean_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'session_id' must be a non-empty string.",
        )

    cookie_name = f"{settings.session_cookie_name}_{clean_session_id}"
    cookie_secret = request.cookies.get(cookie_name)

    try:
        session_dir = validate_session_auth(clean_session_id, cookie_secret, csrf_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            exc.headers = _get_expired_cookie_header(cookie_name)
        raise

    repo_root = (session_dir / "repo").resolve()
    target_relative = clean_path.lstrip("/\\")
    target_path = (repo_root / target_relative).resolve()

    try:
        if not target_path.is_relative_to(repo_root):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Path traversal attempt detected.",
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path traversal attempt detected.",
        )

    if not target_path.exists() or not target_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested directory does not exist in repository.",
        )

    try:
        folders: list[TreeItem] = []
        files: list[TreeItem] = []

        for item in target_path.iterdir():
            if item.name == ".git" or item.is_symlink():
                continue
            item_rel = item.relative_to(repo_root).as_posix()
            if item.is_dir():
                folders.append(TreeItem(name=item.name, path=item_rel, is_dir=True))
            elif item.is_file():
                files.append(TreeItem(name=item.name, path=item_rel, is_dir=False))

        folders.sort(key=lambda x: x.name.lower())
        files.sort(key=lambda x: x.name.lower())
        return folders + files
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read directory contents.",
        )


@router.get("/symbol", response_model=SymbolContentResponse, status_code=status.HTTP_200_OK)
def get_symbol_content(
    request: Request,
    session_id: str = Query(..., description="Active session ID"),
    symbol: str = Query(..., description="Qualified symbol name"),
    csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
):
    """Retrieves source code for a symbol using codebase-memory-mcp CLI with session auth validation."""
    clean_session_id = session_id.strip()
    clean_symbol = symbol.strip()

    if not clean_session_id or not clean_symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'session_id' and 'symbol' must be non-empty strings.",
        )

    cookie_name = f"{settings.session_cookie_name}_{clean_session_id}"
    cookie_secret = request.cookies.get(cookie_name)

    try:
        validate_session_auth(clean_session_id, cookie_secret, csrf_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            exc.headers = _get_expired_cookie_header(cookie_name)
        raise

    raw_output = _run_cbm_cli(clean_session_id, "get_code_snippet", ["--qualified-name", clean_symbol])

    if not raw_output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Symbol not found.")

    if raw_output.startswith("ERROR:"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=raw_output)

    try:
        parsed = json.loads(raw_output)
        if isinstance(parsed, dict):
            content = parsed.get("source", raw_output)
        else:
            content = raw_output
    except (json.JSONDecodeError, TypeError):
        content = raw_output

    if not isinstance(content, str):
        content = str(content)

    return SymbolContentResponse(content=content, symbol=clean_symbol)
