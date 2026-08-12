import os
import sys
from pathlib import Path
from unittest.mock import patch

import fakeredis
import pytest

# Ensure backend directory is in sys.path for test discovery
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("SERVICE_ROLE", "api")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("GITHUB_PAT", "ghp_test")


@pytest.fixture(autouse=True)
def mock_redis():
    """Global autouse fixture replacing Redis with an in-memory FakeRedis instance for unit tests."""
    from app.redis_client import set_redis_client

    fake_client = fakeredis.FakeRedis(decode_responses=True)
    set_redis_client(fake_client)

    with patch("redis.from_url", return_value=fake_client):
        yield fake_client

    set_redis_client(None)
