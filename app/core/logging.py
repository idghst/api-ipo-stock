"""JSON logging configuration."""

import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """Serialize the request fields used by application logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": record.__dict__.get("request_id"),
            "method": record.__dict__.get("method"),
            "path": record.__dict__.get("path"),
            "status": record.__dict__.get("status"),
            "duration": record.__dict__.get("duration"),
            "exception_type": record.__dict__.get("exception_type"),
        }
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    """Configure the root logger with one UTC JSON stream handler."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
