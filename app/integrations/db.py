from collections.abc import AsyncIterator
from secrets import compare_digest
from typing import Annotated, Any

import psycopg
from fastapi import Depends, Header
from psycopg.rows import dict_row

from app.core.config import Settings, get_settings
from app.core.errors import ApiError

type Connection = psycopg.AsyncConnection[dict[str, Any]]


async def connect(settings: Settings) -> Connection:
    timeout = settings.DB_TIMEOUT_SECONDS
    try:
        return await psycopg.AsyncConnection.connect(
            settings.DATABASE_URL.get_secret_value(),
            connect_timeout=timeout,
            options=f"-c statement_timeout={timeout * 1000}",
            autocommit=True,
            row_factory=dict_row,
        )
    except psycopg.Error as error:
        raise ApiError(
            503, "database_unavailable", "Database is unavailable"
        ) from error


async def get_admin_connection(
    settings: Annotated[Settings, Depends(get_settings)],
    admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> AsyncIterator[Connection]:
    configured_key = settings.IPO_STOCK_API_KEY
    if configured_key is None:
        raise ApiError(
            503,
            "administrator_authentication_unavailable",
            "Administrator authentication is unavailable",
        )
    if admin_key is None or not compare_digest(
        admin_key,
        configured_key.get_secret_value(),
    ):
        raise ApiError(401, "invalid_admin_api_key", "Invalid administrator API key")

    connection = await connect(settings)
    try:
        yield connection
    finally:
        await connection.close()
