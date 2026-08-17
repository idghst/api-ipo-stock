from datetime import UTC, datetime
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError, AuthRetryableError, AuthUnknownError
from supabase_auth.types import User, UserResponse

from app.core.config import Settings
from app.core.errors import ApiError
from app.main import create_app
from supabase import AsyncClient, AsyncClientOptions


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_context():
    from app.integrations.supabase import AuthContext

    return AuthContext(
        user=User.model_validate(
            {
                "id": "user-123",
                "email": "user@example.com",
                "app_metadata": {},
                "user_metadata": {},
                "aud": "authenticated",
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ),
        client=cast(AsyncClient, object()),
    )


def test_me_requires_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_me_returns_verified_identity(
    client: TestClient, app: FastAPI, auth_context
) -> None:
    from app.api.routes.auth import get_auth_context

    async def authenticated():
        yield auth_context

    app.dependency_overrides[get_auth_context] = authenticated
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    assert response.json() == {"id": "user-123", "email": "user@example.com"}


class FakeHttpClient:
    def __init__(self, **_: object) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakePostgrest:
    def __init__(self) -> None:
        self.token: str | None = None

    def auth(self, token: str) -> None:
        self.token = token


class FakeAuth:
    def __init__(self, result: UserResponse | Exception) -> None:
        self.result = result

    async def get_user(self, _: str) -> UserResponse:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeSupabaseClient:
    def __init__(self, result: UserResponse | Exception) -> None:
        self.auth = FakeAuth(result)
        self.postgrest = FakePostgrest()


@pytest.fixture
def verified_user() -> UserResponse:
    return UserResponse(
        user=User.model_validate(
            {
                "id": "user-123",
                "email": "user@example.com",
                "app_metadata": {},
                "user_metadata": {},
                "aud": "authenticated",
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )


@pytest.mark.asyncio
async def test_auth_context_scopes_verified_token_and_closes_client(
    monkeypatch: pytest.MonkeyPatch, verified_user: UserResponse, settings: Settings
) -> None:
    from app.integrations import supabase
    from app.integrations.supabase import AuthContext, get_auth_context

    http_client = FakeHttpClient()
    supabase_client = FakeSupabaseClient(verified_user)
    options: list[AsyncClientOptions] = []
    monkeypatch.setattr(supabase.httpx, "AsyncClient", lambda **_: http_client)

    async def create_client(*_: object, **kwargs: object) -> FakeSupabaseClient:
        options.append(cast(AsyncClientOptions, kwargs["options"]))
        return supabase_client

    monkeypatch.setattr(supabase, "acreate_client", create_client)

    contexts: list[AuthContext] = []
    async for context in get_auth_context(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-123"), settings
    ):
        contexts.append(context)

    assert contexts[0].user.id == "user-123"
    assert contexts[0].client is supabase_client
    assert supabase_client.postgrest.token == "token-123"
    assert http_client.closed is True
    assert options[0].schema == "ipo_stock"
    assert options[0].persist_session is False
    assert options[0].auto_refresh_token is False
    assert options[0].postgrest_client_timeout == 5.0
    assert options[0].httpx_client is http_client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status_code", "code", "message"),
    [
        (
            AuthApiError("token rejected", 401, "invalid_jwt"),
            401,
            "invalid_access_token",
            "Invalid access token",
        ),
        (
            AuthApiError("database details", 500, "unexpected_failure"),
            503,
            "authentication_service_unavailable",
            "Authentication service is unavailable",
        ),
        (
            AuthApiError("rate limit details", 429, "over_request_rate_limit"),
            503,
            "authentication_service_unavailable",
            "Authentication service is unavailable",
        ),
        (
            AuthApiError("upstream bad request", 400, "unexpected_failure"),
            503,
            "authentication_service_unavailable",
            "Authentication service is unavailable",
        ),
        (
            AuthRetryableError("retry details", 503),
            503,
            "authentication_service_unavailable",
            "Authentication service is unavailable",
        ),
        (
            AuthUnknownError("malformed details", ValueError("payload details")),
            503,
            "authentication_service_unavailable",
            "Authentication service is unavailable",
        ),
        (
            httpx.ConnectError("offline details"),
            503,
            "authentication_service_unavailable",
            "Authentication service is unavailable",
        ),
    ],
)
async def test_auth_context_maps_authentication_failures(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    failure: Exception,
    status_code: int,
    code: str,
    message: str,
) -> None:
    from app.integrations import supabase
    from app.integrations.supabase import get_auth_context

    monkeypatch.setattr(supabase.httpx, "AsyncClient", FakeHttpClient)

    async def create_client(*_: object, **__: object) -> FakeSupabaseClient:
        return FakeSupabaseClient(failure)

    monkeypatch.setattr(supabase, "acreate_client", create_client)

    with pytest.raises(ApiError) as raised:
        async for _ in get_auth_context(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-123"),
            settings,
        ):
            pass

    assert raised.value.status_code == status_code
    assert raised.value.code == code
    assert raised.value.message == message
    assert str(failure) not in raised.value.message


@pytest.mark.asyncio
async def test_admin_client_uses_only_secret_key_and_closes_client(
    monkeypatch: pytest.MonkeyPatch, verified_user: UserResponse, settings: Settings
) -> None:
    from app.integrations import supabase
    from app.integrations.supabase import get_admin_client

    http_client = FakeHttpClient()
    supabase_client = FakeSupabaseClient(verified_user)
    received_keys: list[str] = []
    monkeypatch.setattr(supabase.httpx, "AsyncClient", lambda **_: http_client)

    async def create_client(*args: object, **_: object) -> FakeSupabaseClient:
        received_keys.append(cast(str, args[1]))
        return supabase_client

    monkeypatch.setattr(supabase, "acreate_client", create_client)
    admin_settings = Settings(
        SUPABASE_URL=settings.SUPABASE_URL,
        SUPABASE_PUBLISHABLE_KEY=settings.SUPABASE_PUBLISHABLE_KEY,
        SUPABASE_SECRET_KEY="sb_secret_test",
    )

    clients: list[AsyncClient] = []
    async for configured_client in get_admin_client(admin_settings):
        clients.append(configured_client)

    assert clients[0] is supabase_client
    assert received_keys == ["sb_secret_test"]
    assert supabase_client.postgrest.token is None
    assert http_client.closed is True


@pytest.mark.asyncio
async def test_admin_client_requires_secret_key(settings: Settings) -> None:
    from app.integrations.supabase import get_admin_client

    with pytest.raises(ApiError) as raised:
        async for _ in get_admin_client(settings):
            pass

    assert raised.value.status_code == 503
    assert raised.value.code == "administrator_client_unavailable"


@pytest.mark.asyncio
async def test_client_creation_failure_closes_http_client(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    from app.integrations import supabase

    http_client = FakeHttpClient()
    monkeypatch.setattr(supabase.httpx, "AsyncClient", lambda **_: http_client)

    async def create_client(*_: object, **__: object) -> FakeSupabaseClient:
        raise RuntimeError("client creation failed")

    monkeypatch.setattr(supabase, "acreate_client", create_client)

    with pytest.raises(RuntimeError, match="client creation failed"):
        await supabase._new_client(settings, "sb_publishable_test")

    assert http_client.closed is True
