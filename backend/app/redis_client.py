import redis

from app.config import settings

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Returns single application Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def set_redis_client(client: redis.Redis | None) -> None:
    """Sets or resets global Redis client instance (used for test environment overrides)."""
    global _redis_client
    _redis_client = client
