from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application Settings loaded from environment variables and .env file."""

    # Required environment setting
    environment: Literal["development", "staging", "production"] = Field(...)
    service_role: Literal["api", "worker", "beat"] = Field(...)
    log_level: str = "INFO"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # Comma-separated list of allowed CORS origins
    cors_allowed_origins: str = "http://localhost,http://localhost:5173,http://127.0.0.1,http://127.0.0.1:5173"

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_redis_url: str = "redis://redis:6379/1"

    # Shared data volume & scratch mount points
    shared_data_dir: str = "/app/data"
    scratch_data_dir: str = "/app/data/scratch"

    # Session security settings
    session_cookie_name: str = "session_secret"
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_secure: bool = False

    # Task subprocess timeout limits (seconds)
    clone_timeout_seconds: int = 120
    index_timeout_seconds: int = 300

    # Repository cleanup configuration
    repo_max_age_seconds: int = 7200
    repo_storage_threshold_gb: float = 10.0
    repo_cleanup_interval_seconds: int = 300
    max_repo_size_mb: int = 200
    max_graph_db_size_mb: int = 250

    # Traces storage configuration
    traces_max_age_seconds: int = 60 * 24 * 60 * 60
    traces_storage_threshold_gb: float = 1.0

    # Rate Limits
    max_daily_budget_dollars: float = 0.40
    max_daily_global_indexes: int = 20
    max_daily_ip_indexes: int = 4
    max_daily_device_sessions: int = 4
    max_messages_per_session: int = 8
    max_concurrent_indexing_tasks: int = 2
    max_chat_message_length: int = 2000

    # API credentials and LLM configuration
    openai_api_key: SecretStr | None = None
    github_pat: SecretStr | None = None
    llm_model: str = "gpt-5.6-luna"
    moderation_model: str = "omni-moderation-latest"
    moderation_enabled: bool = True
    moderation_fail_open: bool = True
    moderation_timeout_seconds: float = 5.0
    tokenizer_encoding: str = "o200k_base"
    agent_max_tool_calls: int = 6
    max_context_tokens: int = 1000000
    max_completion_tokens: int = 20000
    reasoning_effort: str = "low"

    # LLM pricing per 1M tokens (USD)
    cost_input_tokens: float = 0.20
    cost_cached_input_tokens: float = 0.02
    cost_output_tokens: float = 1.20

    @property
    def parsed_cors_origins(self) -> list[str]:
        """Returns parsed list of allowed CORS origins."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Helper checking if app is running in production mode."""
        return self.environment == "production"

    @staticmethod
    def _redis_url_has_password(redis_url: str) -> bool:
        """Checks whether a Redis URL includes an explicit password."""
        parsed = urlsplit(redis_url)
        return bool(parsed.password and parsed.password.strip())

    @model_validator(mode="after")
    def validate_environment_requirements(self) -> "Settings":
        """Fails fast at startup if development or production environment lacks required settings."""
        missing_or_invalid: list[str] = []

        if self.environment in ("development", "production") and self.service_role == "api":
            if not self.openai_api_key or not self.openai_api_key.get_secret_value().strip():
                missing_or_invalid.append("OPENAI_API_KEY (must be set for api role in development or production)")
            if not self.github_pat or not self.github_pat.get_secret_value().strip():
                missing_or_invalid.append("GITHUB_PAT (must be set for api role in development or production)")

        if self.is_production:
            # Ensure LOG_LEVEL is not set to DEBUG in production
            if self.log_level.upper() == "DEBUG":
                missing_or_invalid.append("LOG_LEVEL (must not be 'DEBUG' in production)")

            if not self._redis_url_has_password(self.redis_url):
                missing_or_invalid.append("REDIS_URL (must include a password in production)")
            if not self._redis_url_has_password(self.celery_redis_url):
                missing_or_invalid.append("CELERY_REDIS_URL (must include a password in production)")

            # Ensure dev localhost origins are not leaking into production CORS
            if any("localhost" in origin or "127.0.0.1" in origin for origin in self.parsed_cors_origins):
                missing_or_invalid.append("CORS_ALLOWED_ORIGINS (must specify explicit production domain)")

            # Ensure COOKIE_SECURE is set to True in production
            if not self.cookie_secure:
                missing_or_invalid.append("COOKIE_SECURE (must be set to True in production)")

        if missing_or_invalid:
            raise ValueError(f"Configuration error - Invalid or missing settings: {', '.join(missing_or_invalid)}")

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]
