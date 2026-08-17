from typing import Any, cast

import httpx
from postgrest.exceptions import APIError as PostgrestAPIError

from app.core.errors import ApiError

CodeError = tuple[int, str, str]


async def execute_query(
    query: Any,
    *,
    code_errors: dict[str, CodeError] | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    mapped_errors = {
        "42501": (
            403,
            "database_access_denied",
            "Database access was denied",
        ),
        **(code_errors or {}),
    }
    try:
        response = await query.execute()
    except PostgrestAPIError as error:
        mapped = mapped_errors.get(error.code or "")
        if mapped is not None:
            status_code, code, message = mapped
            raise ApiError(status_code, code, message) from error
        raise ApiError(
            502,
            "database_request_failed",
            "Database request failed",
        ) from error
    except httpx.HTTPError as error:
        raise ApiError(
            503, "database_unavailable", "Database is unavailable"
        ) from error

    data = response.data
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ApiError(
            502,
            "database_response_invalid",
            "Database returned an invalid response",
        )
    count = response.count
    if count is not None and (not isinstance(count, int) or isinstance(count, bool)):
        raise ApiError(
            502,
            "database_response_invalid",
            "Database returned an invalid response",
        )
    return cast(list[dict[str, Any]], data), count


def ensure_row(
    rows: list[dict[str, Any]],
    *,
    code: str,
    message: str,
) -> dict[str, Any]:
    if not rows:
        raise ApiError(404, code, message)
    return rows[0]
