from typing import Any, cast

import httpx
from postgrest.exceptions import APIError as PostgrestAPIError

from app.core.errors import ApiError

CodeError = tuple[int, str, str]

_DEFAULT_ERRORS: dict[str, CodeError] = {
    "42P01": (404, "table_not_found", "Table not found"),
    "PGRST205": (404, "table_not_found", "Table not found"),
    "42703": (404, "column_not_found", "Column not found"),
    "PGRST204": (404, "column_not_found", "Column not found"),
    "42883": (404, "routine_not_found", "Routine not found"),
    "PGRST202": (404, "routine_not_found", "Routine not found"),
    "42701": (409, "column_already_exists", "Column already exists"),
    "22023": (422, "invalid_schema_change", "Schema change is invalid"),
    "22P02": (422, "invalid_row", "Row data is invalid"),
    "23503": (409, "foreign_key_violation", "Foreign key constraint violated"),
    "23505": (409, "unique_violation", "Unique constraint violated"),
    "23514": (422, "invalid_row", "Row data is invalid"),
    "23502": (422, "not_null_violation", "A required value is missing"),
    "42501": (403, "database_access_denied", "Database access was denied"),
    "PGRST000": (503, "database_unavailable", "Database is unavailable"),
    "PGRST001": (503, "database_unavailable", "Database is unavailable"),
    "PGRST002": (503, "database_unavailable", "Database is unavailable"),
    "PGRST106": (406, "schema_not_exposed", "Requested schema is not exposed"),
}


def map_postgrest_error(
    error: PostgrestAPIError,
    code_errors: dict[str, CodeError] | None = None,
) -> ApiError:
    mapped = {**_DEFAULT_ERRORS, **(code_errors or {})}.get(error.code or "")
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


async def _run(
    query: Any,
    *,
    code_errors: dict[str, CodeError] | None = None,
) -> Any:
    try:
        return await query.execute()
    except PostgrestAPIError as error:
        raise map_postgrest_error(error, code_errors) from error
    except httpx.HTTPError as error:
        raise ApiError(
            503, "database_unavailable", "Database is unavailable"
        ) from error


async def execute_query(
    query: Any,
    *,
    code_errors: dict[str, CodeError] | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    response = await _run(query, code_errors=code_errors)
    data = response.data
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise invalid_response()
    count = response.count
    if count is not None and (not isinstance(count, int) or isinstance(count, bool)):
        raise invalid_response()
    return cast(list[dict[str, Any]], data), count


async def execute_rpc(
    query: Any,
    *,
    code_errors: dict[str, CodeError] | None = None,
) -> Any:
    return (await _run(query, code_errors=code_errors)).data
