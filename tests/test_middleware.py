import json
import logging
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import configure_logging
from app.middleware.request_context import RequestContextMiddleware, resolve_request_id


def test_request_id_accepts_safe_value() -> None:
    assert resolve_request_id("req-123") == "req-123"


def test_request_id_replaces_unsafe_value() -> None:
    value = resolve_request_id("!" * 129)

    assert value != "!" * 129
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value)


def test_middleware_returns_request_id_header() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok"}

    response = TestClient(app).get("/", headers={"X-Request-ID": "req-123"})

    assert response.headers["X-Request-ID"] == "req-123"


def test_configure_logging_emits_json_with_request_fields() -> None:
    configure_logging("INFO")
    handler = logging.getLogger().handlers[0]
    record = logging.LogRecord(
        "test.logger",
        logging.INFO,
        __file__,
        1,
        "done",
        (),
        None,
    )
    record.request_id = "req-123"
    record.method = "GET"
    record.path = "/health"
    record.status = 200
    record.duration = 1.5
    record.exception_type = None

    payload = json.loads(handler.format(record))

    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "INFO",
        "logger": "test.logger",
        "message": "done",
        "request_id": "req-123",
        "method": "GET",
        "path": "/health",
        "status": 200,
        "duration": 1.5,
        "exception_type": None,
    }
