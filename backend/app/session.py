import contextlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import HTTPException, status

from app.config import settings
from app.logger import logger

# Strictly allow alphanumeric, hyphen, and underscore characters in session IDs up to 64 chars total
SESSION_ID_REGEX = re.compile(r"^(?:session|app-data-session)-[a-zA-Z0-9_\-]{1,50}$")


def get_session_dir(session_id: str) -> Path:
    """
    Validates session ID format and directory existence without modifying mtime.
    Raises HTTP 400 for malformed IDs or path traversal attempts.
    Raises HTTP 404 if session directory is missing or expired.
    """
    clean_session_id = session_id.strip()
    if not clean_session_id or len(clean_session_id) > 64 or not SESSION_ID_REGEX.match(clean_session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format.",
        )

    base_data_dir = Path(settings.shared_data_dir).resolve()
    session_dir = (base_data_dir / clean_session_id).resolve()

    # Prevent path traversal outside shared data directory
    try:
        if not session_dir.is_relative_to(base_data_dir):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session ID format.",
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format.",
        )

    if not session_dir.exists() or not session_dir.is_dir():
        logger.warning(f"Chat attempt on missing/expired session '{clean_session_id}'")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session has expired due to inactivity. Please index the repository again.",
        )

    meta_file = session_dir / "session_meta.json"
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise TypeError("Session metadata must be a JSON object.")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Corrupted session metadata for '{clean_session_id}': {exc}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session metadata is invalid or corrupted. Please index the repository again.",
            )

    return session_dir


def touch_session(session_id: str) -> Path:
    """
    Validates session directory existence and updates modification time (mtime)
    to reflect recent user activity. Raises HTTP 404 if session is expired or missing.
    """
    session_dir = get_session_dir(session_id)

    try:
        now = time.time()
        os.utime(session_dir, (now, now))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to update activity mtime for session '{session_id}': {exc}")

    return session_dir


def create_session_credentials(session_id: str) -> tuple[str, str]:
    """
    Generates high-entropy session_secret and csrf_token credentials,
    persisting them with 0600 file permissions in shared_data_dir/{session_id}/session_meta.json.
    Returns (session_secret, csrf_token).
    """
    clean_session_id = session_id.strip()
    if not clean_session_id or len(clean_session_id) > 64 or not SESSION_ID_REGEX.match(clean_session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format.",
        )

    base_data_dir = Path(settings.shared_data_dir).resolve()
    session_dir = (base_data_dir / clean_session_id).resolve()
    session_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    session_secret = secrets.token_hex(32)
    csrf_token = secrets.token_hex(32)

    meta_file = session_dir / "session_meta.json"
    meta_data = {
        "session_secret": session_secret,
        "csrf_token": csrf_token,
    }
    content = json.dumps(meta_data, indent=2).encode("utf-8")

    fd = os.open(meta_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "wb") as f:
        f.write(content)

    return session_secret, csrf_token


def get_session_meta_file(session_id: str) -> Path:
    """Returns the session metadata file path for a validated session id."""
    clean_session_id = session_id.strip()
    if not clean_session_id or len(clean_session_id) > 64 or not SESSION_ID_REGEX.match(clean_session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format.",
        )

    base_data_dir = Path(settings.shared_data_dir).resolve()
    session_dir = (base_data_dir / clean_session_id).resolve()
    return session_dir / "session_meta.json"


def read_session_metadata(session_id: str) -> dict[str, object]:
    """Reads session metadata if present, returning an empty dict on missing or invalid files."""
    meta_file = get_session_meta_file(session_id)
    if not meta_file.exists():
        return {}

    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to read session metadata for '{session_id}': {exc}")
        return {}

    return data if isinstance(data, dict) else {}


def update_session_metadata(session_id: str, **fields: object) -> None:
    """Merges metadata fields into session_meta.json, preserving existing values."""
    meta_file = get_session_meta_file(session_id)
    meta_file.parent.mkdir(parents=True, exist_ok=True)

    data = read_session_metadata(session_id)
    data.update(fields)

    tmp_file = meta_file.with_suffix(".json.tmp")
    content = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")

    fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with open(fd, "wb") as f:
            f.write(content)
        os.replace(tmp_file, meta_file)
    finally:
        if tmp_file.exists():
            with contextlib.suppress(Exception):
                tmp_file.unlink()


def get_project_name_from_session_db(session_dir: Path) -> str | None:
    """Reads the indexed project name from the session's SQLite graph database."""
    if not session_dir.exists() or not session_dir.is_dir():
        return None

    for db_file in sorted(session_dir.rglob("*.db")):
        try:
            conn = sqlite3.connect(db_file)
            try:
                row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to read project name from '{db_file}': {exc}")
            continue

        if row and isinstance(row[0], str):
            project_name = row[0].strip()
            if project_name:
                return project_name

    return None


def validate_session_auth(
    session_id: str,
    cookie_secret: str | None,
    header_csrf_token: str | None,
) -> Path:
    """
    Validates session cookie and CSRF token against persisted session_meta.json.
    Updates session activity mtime ONLY AFTER successful credential verification.
    Raises HTTP 401 Unauthorized for missing/invalid cookie or metadata.
    Raises HTTP 403 Forbidden for missing/invalid CSRF token.
    Raises HTTP 404 Not Found if session directory is missing or expired.
    """
    # 1. Inspect directory and check format without updating mtime
    session_dir = get_session_dir(session_id)
    meta_file = session_dir / "session_meta.json"

    if not meta_file.exists():
        logger.warning(f"Session metadata missing for session '{session_id}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing session credentials.",
        )

    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to read session metadata for '{session_id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing session credentials.",
        )

    if not isinstance(meta_data, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing session credentials.",
        )

    expected_secret = meta_data.get("session_secret")
    expected_csrf = meta_data.get("csrf_token")

    if not isinstance(expected_secret, str) or not isinstance(expected_csrf, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing session credentials.",
        )

    if not cookie_secret or not hmac.compare_digest(cookie_secret, expected_secret):
        logger.warning(f"Unauthorized access attempt (invalid cookie) for session '{session_id}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing session cookie.",
        )

    if not header_csrf_token or not hmac.compare_digest(header_csrf_token, expected_csrf):
        logger.warning(f"Forbidden access attempt (invalid CSRF token) for session '{session_id}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing CSRF token.",
        )

    # 2. Touch session mtime ONLY after credentials have been fully verified
    try:
        now = time.time()
        os.utime(session_dir, (now, now))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to update activity mtime for session '{session_id}': {exc}")

    return session_dir
