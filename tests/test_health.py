from typing import Self

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(DATABASE_URL=SecretStr("postgresql://app@db.test/ipostock"))


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_maps_unavailable_dependency_to_sanitized_503(
    client: TestClient, app: FastAPI
) -> None:
    from app.api.routes.health import probe_database

    async def unavailable() -> None:
        raise ApiError(503, "dependency_unavailable", "Database is unavailable")

    app.dependency_overrides[probe_database] = unavailable

    response = client.get("/health/ready", headers={"X-Request-ID": "req-ready"})

    assert response.status_code == 503
    assert response.json() == {
        "code": "dependency_unavailable",
        "message": "Database is unavailable",
        "request_id": "req-ready",
    }


class FakeConnection:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.queries: list[str] = []
        self.closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    async def execute(self, query: str) -> None:
        self.queries.append(query)
        if self.failure is not None:
            raise self.failure


@pytest.mark.asyncio
async def test_probe_database_runs_select_and_closes(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    from app.api.routes import health

    connection = FakeConnection()

    async def connect(_: Settings) -> FakeConnection:
        return connection

    monkeypatch.setattr(health, "connect", connect)

    await health.probe_database(settings)

    assert connection.queries == ["select 1"]
    assert connection.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "connect",
        psycopg.OperationalError("server closed the connection"),
    ],
)
async def test_probe_database_sanitizes_failures(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    failure: str | Exception,
) -> None:
    from app.api.routes import health

    async def connect(_: Settings) -> FakeConnection:
        if failure == "connect":
            raise ApiError(503, "database_unavailable", "Database is unavailable")
        return FakeConnection(failure)  # type: ignore[arg-type]

    monkeypatch.setattr(health, "connect", connect)

    with pytest.raises(ApiError) as caught:
        await health.probe_database(settings)

    assert caught.value.status_code == 503
    assert caught.value.code == "dependency_unavailable"
    assert caught.value.message == "Database is unavailable"


def test_factory_injects_supplied_settings_and_root_message(
    app: FastAPI, client: TestClient, settings: Settings
) -> None:
    assert app.dependency_overrides[get_settings]() is settings

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "IPO Stock API"}


def test_production_host_disables_docs_and_openapi() -> None:
    app = create_app(
        Settings(
            DATABASE_URL=SecretStr("postgresql://app@db.example.com/ipostock"),
            IPO_STOCK_API_KEY=SecretStr("administrator-secret"),
        )
    )
    client = TestClient(app, base_url="http://api.example.com")

    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path, headers={"X-Request-ID": "req-docs"})

        assert response.status_code == 404
        assert response.json() == {
            "code": "http_error",
            "message": "HTTP error",
            "request_id": "req-docs",
        }


def test_localhost_and_test_hosts_expose_docs(settings: Settings) -> None:
    app = create_app(settings)
    for base_url in ("http://localhost:8000", "http://testserver"):
        client = TestClient(app, base_url=base_url)
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200


def test_production_host_without_admin_credentials_returns_503() -> None:
    app = create_app(
        Settings(DATABASE_URL=SecretStr("postgresql://app@db.example.com/ipostock"))
    )
    client = TestClient(app, base_url="http://api.example.com")

    live = client.get("/health/live")
    root = client.get("/")

    assert live.status_code == 200
    assert root.status_code == 503
    assert root.json()["code"] == "administrator_authentication_unavailable"


def test_cors_allows_only_configured_origin(settings: Settings) -> None:
    client = TestClient(create_app(settings))

    allowed = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = client.options(
        "/health/live",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert denied.status_code == 400
