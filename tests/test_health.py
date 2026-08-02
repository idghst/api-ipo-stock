import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY=SecretStr("sb_publishable_test"),
        SUPABASE_TIMEOUT_SECONDS=2.5,
    )


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
    from app.api.routes.health import probe_supabase

    async def unavailable() -> None:
        raise ApiError(503, "dependency_unavailable", "Supabase is unavailable")

    app.dependency_overrides[probe_supabase] = unavailable

    response = client.get("/health/ready", headers={"X-Request-ID": "req-ready"})

    assert response.status_code == 503
    assert response.json() == {
        "code": "dependency_unavailable",
        "message": "Supabase is unavailable",
        "request_id": "req-ready",
    }


def test_readiness_probes_auth_health_with_publishable_key_and_timeout(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    from app.api.routes.health import probe_supabase

    observed: dict[str, object] = {}

    def healthy(url: str, **kwargs: object) -> httpx.Response:
        observed["url"] = url
        observed.update(kwargs)
        return httpx.Response(204)

    monkeypatch.setattr("app.api.routes.health.httpx.get", healthy)

    probe_supabase(settings)

    assert observed == {
        "url": "https://test.supabase.co/auth/v1/health",
        "headers": {"apikey": "sb_publishable_test"},
        "timeout": 2.5,
    }


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("connection refused"),
        httpx.Response(503),
    ],
)
def test_probe_supabase_sanitizes_upstream_failures(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    failure: httpx.HTTPError | httpx.Response,
) -> None:
    from app.api.routes.health import probe_supabase

    def unavailable(_: str, **__: object) -> httpx.Response:
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr("app.api.routes.health.httpx.get", unavailable)

    with pytest.raises(ApiError) as caught:
        probe_supabase(settings)

    assert caught.value.status_code == 503
    assert caught.value.code == "dependency_unavailable"
    assert caught.value.message == "Supabase is unavailable"


def test_factory_injects_supplied_settings_and_root_message(
    app: FastAPI, client: TestClient, settings: Settings
) -> None:
    assert app.dependency_overrides[get_settings]() is settings

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "IPO Stock API"}


def test_production_disables_docs_and_openapi() -> None:
    app = create_app(
        Settings(
            APP_ENV="production",
            SUPABASE_URL="https://test.supabase.co",
            SUPABASE_PUBLISHABLE_KEY=SecretStr("sb_publishable_test"),
            SUPABASE_SECRET_KEY=SecretStr("sb_secret_test"),
            ADMIN_API_KEY=SecretStr("administrator-secret"),
        )
    )
    client = TestClient(app)

    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path, headers={"X-Request-ID": "req-docs"})

        assert response.status_code == 404
        assert response.json() == {
            "code": "http_error",
            "message": "HTTP error",
            "request_id": "req-docs",
        }


def test_cors_allows_only_configured_origin(settings: Settings) -> None:
    settings.CORS_ORIGINS = ["https://app.example.com"]
    client = TestClient(create_app(settings))

    allowed = client.options(
        "/health/live",
        headers={
            "Origin": "https://app.example.com",
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

    assert allowed.headers["access-control-allow-origin"] == "https://app.example.com"
    assert denied.status_code == 400
