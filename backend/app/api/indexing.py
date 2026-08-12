import re
import shutil
import uuid
from pathlib import Path

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.celery_app import celery_app
from app.config import settings
from app.logger import logger
from app.models import (
    IndexRepoRequest,
    IndexRepoResponse,
    IndexStatusResponse,
)
from app.rate_limit import (
    acquire_concurrency_slot,
    check_indexing_rate_limits,
    increment_indexing_rate_limits,
    release_concurrency_slot,
)
from app.repo_validation import validate_github_repository
from app.session import create_session_credentials, update_session_metadata
from app.utils import handle_remove_readonly

router = APIRouter(tags=["API"])

# Strict GitHub repository URL pattern capturing owner and repo
GITHUB_URL_REGEX = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:\.git)?/?$")


@router.post("/index-repo", response_model=IndexRepoResponse, status_code=status.HTTP_202_ACCEPTED)
async def index_repo(payload: IndexRepoRequest, request: Request, response: Response):
    """Validates GitHub repository URL, checks repository license, and dispatches an async Celery indexing task."""
    # 1. Check global, IP, and device rate limits before making external validation calls
    check_indexing_rate_limits(request)

    cleaned_url = payload.github_url.strip()
    if len(cleaned_url) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub URL exceeds maximum allowed length of 1000 characters.",
        )

    if not cleaned_url.startswith(("http://", "https://")):
        cleaned_url = f"https://{cleaned_url}"

    match = GITHUB_URL_REGEX.match(cleaned_url)
    if not match:
        logger.warning(f"Invalid GitHub URL submitted: {payload.github_url}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Invalid GitHub repository URL format. Example: https://github.com/owner/repo",
                "reason": "URLs for specific branches, commits, or subdirectories are currently not supported.",
            },
        )

    owner, repo = match.group(1), match.group(2)
    repo = repo.removesuffix(".git")

    spdx_id = await validate_github_repository(owner, repo)
    logger.info(f"Verified license '{spdx_id}' for {owner}/{repo}")

    acquire_concurrency_slot()

    increment_indexing_rate_limits(request, response)

    session_id = f"session-{uuid.uuid4().hex[:12]}"
    session_secret, csrf_token = create_session_credentials(session_id)
    update_session_metadata(session_id, repo_slug=f"{owner}/{repo}")

    cookie_name = f"{settings.session_cookie_name}_{session_id}"
    response.set_cookie(
        key=cookie_name,
        value=session_secret,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        max_age=settings.repo_max_age_seconds,
        path="/api",
    )

    try:
        task = celery_app.send_task("app.tasks.index_repository", args=[cleaned_url, session_id])
        logger.info(f"Dispatched indexing task {task.id} for {cleaned_url} (session: {session_id})")
    except Exception as exc:  # noqa: BLE001
        release_concurrency_slot()
        session_dir = Path(settings.shared_data_dir) / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, onerror=handle_remove_readonly)
        logger.error(f"Failed to dispatch celery task for {cleaned_url}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to dispatch indexing task. Please try again.")

    return IndexRepoResponse(
        task_id=task.id,
        session_id=session_id,
        message=f"Indexing task queued for {cleaned_url}.",
        github_url=cleaned_url,
        csrf_token=csrf_token,
    )


@router.get("/index-status/{task_id}", response_model=IndexStatusResponse, status_code=status.HTTP_200_OK)
async def index_status(task_id: str):
    """Polls Celery task status and maps internal states to a clean API response."""
    result = AsyncResult(task_id, app=celery_app)

    if result.state == "PENDING":
        return IndexStatusResponse(status="PENDING", task_id=task_id)

    if result.state == "PROCESSING":
        meta = result.info or {}
        return IndexStatusResponse(
            status="PROCESSING",
            task_id=task_id,
            stage=meta.get("stage"),
            session_id=meta.get("session_id"),
        )

    if result.state == "SUCCESS":
        task_result = result.result or {}
        return IndexStatusResponse(
            status="SUCCESS",
            task_id=task_id,
            session_id=task_result.get("session_id"),
            github_url=task_result.get("github_url"),
        )

    if result.state == "FAILURE":
        logger.error("Indexing task failed for task_id=%s: %r", task_id, result.info)
        detail = "Indexing failed. Please try again."
        return IndexStatusResponse(status="FAILURE", task_id=task_id, detail=detail)

    meta = result.info if isinstance(result.info, dict) else {}
    return IndexStatusResponse(
        status="PROCESSING",
        task_id=task_id,
        stage=meta.get("stage"),
        session_id=meta.get("session_id"),
    )
