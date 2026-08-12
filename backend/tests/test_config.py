import pytest
from app.config import Settings
from pydantic import ValidationError


def test_missing_environment_fails_validation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file="")  # pyright: ignore[reportCallIssue]


def test_development_settings():
    config = Settings(
        _env_file="",  # pyright: ignore[reportCallIssue]
        environment="development",
        service_role="api",
        openai_api_key="sk-test",  # type: ignore[arg-type]
        github_pat="ghp_test",  # type: ignore[arg-type]
    )
    assert config.environment == "development"
    assert config.service_role == "api"
    assert not config.is_production
    assert "http://localhost" in config.parsed_cors_origins
    assert config.github_pat is not None
    assert config.github_pat.get_secret_value() == "ghp_test"
    assert config.moderation_enabled
    assert config.moderation_model == "omni-moderation-latest"
    assert config.moderation_fail_open
    assert config.moderation_timeout_seconds == 5.0
    assert config.celery_redis_url.endswith("/1")


def test_development_fails_without_openai_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="development",
            service_role="api",
            openai_api_key=None,
            github_pat="ghp_test",  # type: ignore[arg-type]
        )


def test_development_fails_without_github_pat(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    with pytest.raises(ValueError, match="GITHUB_PAT"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="development",
            service_role="api",
            openai_api_key="sk-test",  # type: ignore[arg-type]
            github_pat=None,
        )


def test_production_fails_without_openai_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="production",
            service_role="api",
            openai_api_key=None,
            github_pat="ghp_test",  # type: ignore[arg-type]
            cors_allowed_origins="https://app.mydomain.com",
            redis_url="redis://:redispass@redis:6379/0",
            celery_redis_url="redis://:redispass@redis:6379/1",
        )


def test_production_fails_without_github_pat(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    with pytest.raises(ValueError, match="GITHUB_PAT"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="production",
            service_role="api",
            openai_api_key="sk-test",  # type: ignore[arg-type]
            github_pat=None,
            cors_allowed_origins="https://app.mydomain.com",
            redis_url="redis://:redispass@redis:6379/0",
            celery_redis_url="redis://:redispass@redis:6379/1",
        )


def test_production_fails_with_localhost_cors():
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="production",
            service_role="api",
            openai_api_key="sk-test",  # type: ignore[arg-type]
            github_pat="ghp_test",  # type: ignore[arg-type]
            cors_allowed_origins="http://localhost:5173",
            redis_url="redis://:redispass@redis:6379/0",
            celery_redis_url="redis://:redispass@redis:6379/1",
        )


def test_production_fails_with_debug_log_level():
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="production",
            service_role="api",
            openai_api_key="sk-test",  # type: ignore[arg-type]
            github_pat="ghp_test",  # type: ignore[arg-type]
            log_level="DEBUG",
            cors_allowed_origins="https://app.mydomain.com",
            redis_url="redis://:redispass@redis:6379/0",
            celery_redis_url="redis://:redispass@redis:6379/1",
        )


def test_production_fails_with_insecure_cookie():
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="production",
            service_role="api",
            openai_api_key="sk-test",  # type: ignore[arg-type]
            github_pat="ghp_test",  # type: ignore[arg-type]
            cors_allowed_origins="https://app.mydomain.com",
            cookie_secure=False,
            redis_url="redis://:redispass@redis:6379/0",
            celery_redis_url="redis://:redispass@redis:6379/1",
        )


def test_valid_production_settings():
    config = Settings(
        _env_file="",  # pyright: ignore[reportCallIssue]
        environment="production",
        service_role="api",
        openai_api_key="sk-test",  # type: ignore[arg-type]
        github_pat="ghp_test",  # type: ignore[arg-type]
        log_level="INFO",
        cors_allowed_origins="https://app.mydomain.com",
        cookie_secure=True,
        redis_url="redis://:redispass@redis:6379/0",
        celery_redis_url="redis://:redispass@redis:6379/1",
    )
    assert config.is_production
    assert config.cookie_secure
    assert config.parsed_cors_origins == ["https://app.mydomain.com"]


def test_production_fails_without_redis_password():
    with pytest.raises(ValueError, match="REDIS_URL"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="production",
            service_role="api",
            openai_api_key="sk-test",  # type: ignore[arg-type]
            github_pat="ghp_test",  # type: ignore[arg-type]
            cors_allowed_origins="https://app.mydomain.com",
            cookie_secure=True,
            redis_url="redis://redis:6379/0",
            celery_redis_url="redis://:redispass@redis:6379/1",
        )


def test_production_fails_without_celery_redis_password():
    with pytest.raises(ValueError, match="CELERY_REDIS_URL"):
        Settings(
            _env_file="",  # pyright: ignore[reportCallIssue]
            environment="production",
            service_role="api",
            openai_api_key="sk-test",  # type: ignore[arg-type]
            github_pat="ghp_test",  # type: ignore[arg-type]
            cors_allowed_origins="https://app.mydomain.com",
            cookie_secure=True,
            redis_url="redis://:redispass@redis:6379/0",
            celery_redis_url="redis://redis:6379/1",
        )


def test_production_worker_role_does_not_require_api_keys():
    config = Settings(
        _env_file="",  # pyright: ignore[reportCallIssue]
        environment="production",
        service_role="worker",
        cors_allowed_origins="https://app.mydomain.com",
        cookie_secure=True,
        redis_url="redis://:redispass@redis:6379/0",
        celery_redis_url="redis://:redispass@redis:6379/1",
    )
    assert config.service_role == "worker"
