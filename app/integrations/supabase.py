from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AsyncClient, AsyncClientOptions, acreate_client
from supabase_auth.errors import AuthApiError, AuthRetryableError, AuthUnknownError
from supabase_auth.types import User

from app.core.config import Settings, get_settings
from app.core.errors import ApiError

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    client: AsyncClient


async def _new_client(
    settings: Settings, key: str
) -> tuple[AsyncClient, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(timeout=settings.SUPABASE_TIMEOUT_SECONDS)
    try:
        client = await acreate_client(
            str(settings.SUPABASE_URL),
            key,
            options=AsyncClientOptions(
                schema=settings.supabase_schema,
                persist_session=False,
                auto_refresh_token=False,
                postgrest_client_timeout=settings.SUPABASE_TIMEOUT_SECONDS,
                httpx_client=http_client,
            ),
        )
    except Exception:
        await http_client.aclose()
        raise
    return client, http_client


async def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[AuthContext]:
    if credentials is None:
        raise ApiError(401, "authentication_required", "Bearer token is required")

    client, http_client = await _new_client(
        settings, settings.SUPABASE_PUBLISHABLE_KEY.get_secret_value()
    )
    try:
        try:
            response = await client.auth.get_user(credentials.credentials)
        except AuthApiError as error:
            if error.status in (401, 403) or (
                error.status == 400 and error.code in {"bad_jwt", "invalid_jwt"}
            ):
                raise ApiError(
                    401, "invalid_access_token", "Invalid access token"
                ) from error
            raise ApiError(
                503,
                "authentication_service_unavailable",
                "Authentication service is unavailable",
            ) from error
        except (AuthRetryableError, AuthUnknownError, httpx.HTTPError) as error:
            raise ApiError(
                503,
                "authentication_service_unavailable",
                "Authentication service is unavailable",
            ) from error

        if response is None:
            raise ApiError(401, "invalid_access_token", "Invalid access token")

        client.postgrest.auth(credentials.credentials)
        yield AuthContext(user=response.user, client=client)
    finally:
        await http_client.aclose()


async def get_admin_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[AsyncClient]:
    if settings.SUPABASE_SECRET_KEY is None:
        raise ApiError(
            503,
            "administrator_client_unavailable",
            "Administrator client is unavailable",
        )

    client, http_client = await _new_client(
        settings, settings.SUPABASE_SECRET_KEY.get_secret_value()
    )
    try:
        yield client
    finally:
        await http_client.aclose()
