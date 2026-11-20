from typing import Any, LiteralString

import psycopg

from app.core.errors import ApiError
from app.integrations.db import Connection

_DEFAULT_ERRORS: dict[str, tuple[int, str, str]] = {
    "42P01": (404, "table_not_found", "Table not found"),
    "42703": (404, "column_not_found", "Column not found"),
    "22P02": (422, "invalid_row", "Row data is invalid"),
    "42501": (403, "database_access_denied", "Database access was denied"),
}


def map_db_error(error: psycopg.Error) -> ApiError:
    if isinstance(error, psycopg.OperationalError):
        return ApiError(503, "database_unavailable", "Database is unavailable")
    mapped = _DEFAULT_ERRORS.get(error.sqlstate or "")
    if mapped is None:
        return ApiError(502, "database_request_failed", "Database request failed")
    return ApiError(*mapped)


def invalid_response() -> ApiError:
    return ApiError(
        502,
        "database_response_invalid",
        "Database returned an invalid response",
    )


def ensure_row(
    rows: list[dict[str, Any]],
    *,
    code: str,
    message: str,
) -> dict[str, Any]:
    if not rows:
        raise ApiError(404, code, message)
    return rows[0]


async def fetch_all(
    connection: Connection,
    query: LiteralString,
    params: tuple[object, ...] = (),
) -> list[dict[str, Any]]:
    try:
        cursor = await connection.execute(query, params)
        return await cursor.fetchall()
    except psycopg.Error as error:
        raise map_db_error(error) from error
