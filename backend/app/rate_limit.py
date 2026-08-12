import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request, Response

from app.config import settings
from app.redis_client import get_redis_client
from app.utils import get_client_ip


def check_daily_budget() -> None:
    """FastAPI dependency checking if daily global LLM budget ($1.00) has been reached."""
    client = get_redis_client()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cost_key = f"global_cost:{today}"
    current_cost = client.get(cost_key)
    if current_cost and float(str(current_cost)) >= settings.max_daily_budget_dollars:  # pyright: ignore[reportArgumentType]
        raise HTTPException(status_code=429, detail="Daily budget reached. Please come back tomorrow!")


def check_indexing_rate_limits(request: Request) -> None:
    """Read-only check if global daily indexing limit, IP limit, or device session limit is reached."""
    client = get_redis_client()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Global Daily Limit Check
    global_key = f"global_indexes:{today}"
    global_count_raw = client.get(global_key)
    global_count = int(str(global_count_raw)) if global_count_raw else 0  # pyright: ignore[reportArgumentType]
    if global_count >= settings.max_daily_global_indexes:
        raise HTTPException(status_code=429, detail="Global daily indexing limit reached.")

    # 2. IP Daily Limit Check
    client_ip = get_client_ip(request)
    ip_key = f"ip_indexes:{client_ip}:{today}"
    ip_count_raw = client.get(ip_key)
    ip_count = int(str(ip_count_raw)) if ip_count_raw else 0  # pyright: ignore[reportArgumentType]
    if ip_count >= settings.max_daily_ip_indexes:
        raise HTTPException(status_code=429, detail="You have reached your daily indexing limit.")

    # 3. Device Session Limit Check
    device_id = request.cookies.get("device_id")
    if device_id:
        device_key = f"sessions:{device_id}:{today}"
        device_count_raw = client.get(device_key)
        device_count = int(str(device_count_raw)) if device_count_raw else 0  # pyright: ignore[reportArgumentType]
        if device_count >= settings.max_daily_device_sessions:
            raise HTTPException(status_code=429, detail="You have reached your daily indexing limit.")


def increment_indexing_rate_limits(request: Request, response: Response) -> None:
    """Increments global daily indexing count, IP daily count, and device session count in Redis."""
    client = get_redis_client()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Global Daily Limit
    global_key = f"global_indexes:{today}"
    global_count = int(client.incr(global_key))  # pyright: ignore[reportArgumentType]
    if global_count == 1:
        client.expire(global_key, 86400)

    # 2. IP Daily Limit
    client_ip = get_client_ip(request)
    ip_key = f"ip_indexes:{client_ip}:{today}"
    ip_count = int(client.incr(ip_key))  # pyright: ignore[reportArgumentType]
    if ip_count == 1:
        client.expire(ip_key, 86400)

    # 3. Device Session Limit
    device_id = request.cookies.get("device_id")
    if not device_id:
        device_id = uuid.uuid4().hex
        response.set_cookie(
            "device_id",
            device_id,
            max_age=86400,
            httponly=True,
            path="/",
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )
    device_key = f"sessions:{device_id}:{today}"
    device_count = int(client.incr(device_key))  # pyright: ignore[reportArgumentType]
    if device_count == 1:
        client.expire(device_key, 86400)


def enforce_indexing_rate_limits(request: Request, response: Response) -> None:
    """Enforces global daily indexing limits, IP daily limits, and device session limits."""
    check_indexing_rate_limits(request)
    increment_indexing_rate_limits(request, response)


def acquire_concurrency_slot(queue_key: str = "celery_active_tasks", max_concurrent: int | None = None) -> None:
    """Increments active task counter and raises HTTP 429 if queue capacity is exceeded."""
    if max_concurrent is None:
        max_concurrent = settings.max_concurrent_indexing_tasks
    client = get_redis_client()
    active_count = int(client.incr(queue_key))  # pyright: ignore[reportArgumentType]
    client.expire(queue_key, 600)
    if active_count > max_concurrent:
        client.decr(queue_key)
        raise HTTPException(
            status_code=429, detail="The indexing queue is currently full. Please try again in 5 minutes."
        )


def release_concurrency_slot(queue_key: str = "celery_active_tasks") -> None:
    """Decrements active task counter upon task completion or dispatch failure."""
    client = get_redis_client()
    client.decr(queue_key)
