import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import ApiError, register_exception_handlers
from app.middleware.request_context import RequestContextMiddleware


def create_client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/api-error")
    async def api_error() -> None:
        raise ApiError(status_code=409, code="already_exists", message="Already exists")

    @app.get("/http-error")
    async def http_error() -> None:
        raise HTTPException(status_code=404, detail="Missing")

    @app.get("/unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError("Unexpected")

    @app.get("/validation-error")
    async def validation_error(value: int) -> dict[str, int]:
        return {"value": value}

    return TestClient(app, raise_server_exceptions=False)


def test_api_error_envelope() -> None:
    response = create_client().get("/api-error")

    assert response.status_code == 409
    assert response.json() == {
        "code": "already_exists",
        "message": "Already exists",
        "request_id": None,
    }


def test_http_error_has_stable_code() -> None:
    response = create_client().get("/http-error")

    assert response.status_code == 404
    assert response.json()["code"] == "http_error"


def test_validation_error_has_stable_code() -> None:
    response = create_client().get("/validation-error")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_unexpected_error_does_not_expose_details() -> None:
    response = create_client().get("/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "Internal server error",
        "request_id": None,
    }


def test_missing_route_uses_http_error_envelope_and_request_id() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    response = TestClient(app).get("/missing", headers={"X-Request-ID": "req-404"})

    assert response.status_code == 404
    assert response.json() == {
        "code": "http_error",
        "message": "HTTP error",
        "request_id": "req-404",
    }
    assert response.headers["X-Request-ID"] == "req-404"


def test_unexpected_error_preserves_request_id_and_logs_500(caplog) -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret exception text")

    caplog.set_level(logging.INFO, logger="app.middleware.request_context")
    response = TestClient(app, raise_server_exceptions=False).get(
        "/boom", headers={"X-Request-ID": "req-500"}
    )

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "Internal server error",
        "request_id": "req-500",
    }
    assert response.headers["X-Request-ID"] == "req-500"
    assert caplog.records[-1].status == 500
