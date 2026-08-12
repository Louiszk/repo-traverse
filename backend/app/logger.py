import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for Docker container environments."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            log_data.update(extra_fields)

        return json.dumps(log_data)


def setup_logger(name: str = "app", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a structured logger printing to stdout."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if setup is called multiple times
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(JSONFormatter())
        logger.addHandler(console_handler)

    logger.propagate = False
    return logger


logger = setup_logger()
