from typing import Any, cast

import httpx
from postgrest.exceptions import APIError as PostgrestAPIError

from app.core.errors import ApiError

_DEFAULT_ERRORS: dict[str, tuple[int, str, str]] = {
    "42P01": (404, "table_not_found", "Table not found"),
    "PGRST205": (404, "table_not_found", "Table not found"),
    "42703": (404, "column_not_found", "Column not found"),
    "PGRST204": (404, "column_not_found", "Column not found"),
    "22P02": (422, "invalid_row", "Row data is invalid"),
    "42501": (403, "database_access_denied", "Database access was denied"),
    "PGRST000": (503, "database_unavailable", "Database is unavailable"),
    "PGRST001": (503, "database_unavailable", "Database is unavailable"),
    "PGRST002": (503, "database_unavailable", "Database is unavailable"),
    "PGRST106": (406, "schema_not_exposed", "Requested schema is not exposed"),
}


def map_postgrest_error(error: PostgrestAPIError) -> ApiError:
    mapped = _DEFAULT_ERRORS.get(error.code or "")
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


async def _run(query: Any) -> Any:
    try:
        return await query.execute()
    except PostgrestAPIError as error:
        raise map_postgrest_error(error) from error
    except httpx.HTTPError as error:
        raise ApiError(
            503, "database_unavailable", "Database is unavailable"
        ) from error


async def execute_query(query: Any) -> tuple[list[dict[str, Any]], int | None]:
    response = await _run(query)
    data = response.data
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise invalid_response()
    count = response.count
    if count is not None and (not isinstance(count, int) or isinstance(count, bool)):
        raise invalid_response()
    return cast(list[dict[str, Any]], data), count
