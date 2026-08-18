from dataclasses import dataclass

import httpx
import pytest
from postgrest.exceptions import APIError

from app.core.errors import ApiError
from app.services.postgrest import (
    ensure_row,
    execute_query,
    invalid_response,
    map_postgrest_error,
)


@dataclass
class FakeResponse:
    data: object
    count: int | None = None


class FakeQuery:
    def __init__(self, result: FakeResponse | Exception) -> None:
        self.result = result

    async def execute(self) -> FakeResponse:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize(
    ("code", "status_code", "public_code"),
    [
        ("42P01", 404, "table_not_found"),
        ("PGRST205", 404, "table_not_found"),
        ("42703", 404, "column_not_found"),
        ("PGRST204", 404, "column_not_found"),
        ("22P02", 422, "invalid_row"),
        ("42501", 403, "database_access_denied"),
        ("PGRST000", 503, "database_unavailable"),
        ("PGRST001", 503, "database_unavailable"),
        ("PGRST002", 503, "database_unavailable"),
        ("PGRST106", 406, "schema_not_exposed"),
        ("XX000", 502, "database_request_failed"),
        ("23514", 502, "database_request_failed"),
        ("PGRST202", 502, "database_request_failed"),
    ],
)
def test_map_postgrest_error(code: str, status_code: int, public_code: str) -> None:
    error = map_postgrest_error(
        APIError({"code": code, "message": "private", "details": None, "hint": None})
    )

    assert error.status_code == status_code
    assert error.code == public_code
    assert "private" not in error.message


@pytest.mark.asyncio
async def test_execute_query_returns_rows_and_count() -> None:
    rows, count = await execute_query(FakeQuery(FakeResponse([{"id": 34}], count=1)))

    assert rows == [{"id": 34}]
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        FakeResponse("nope"),
        FakeResponse([{"id": 34}], count=True),
    ],
)
async def test_execute_query_rejects_invalid_payload(response: FakeResponse) -> None:
    with pytest.raises(ApiError) as error:
        await execute_query(FakeQuery(response))

    assert error.value.status_code == 502
    assert error.value.code == "database_response_invalid"


@pytest.mark.asyncio
async def test_execute_query_maps_http_errors() -> None:
    with pytest.raises(ApiError) as error:
        await execute_query(FakeQuery(httpx.ConnectError("offline")))

    assert error.value.status_code == 503
    assert error.value.code == "database_unavailable"


@pytest.mark.asyncio
async def test_execute_query_maps_postgrest_error() -> None:
    with pytest.raises(ApiError) as error:
        await execute_query(
            FakeQuery(
                APIError(
                    {
                        "code": "42501",
                        "message": "private",
                        "details": None,
                        "hint": None,
                    }
                )
            )
        )

    assert error.value.code == "database_access_denied"


def test_ensure_row_returns_first_or_not_found() -> None:
    assert ensure_row([{"id": 34}], code="missing", message="gone") == {"id": 34}

    with pytest.raises(ApiError) as error:
        ensure_row([], code="missing", message="gone")

    assert error.value.status_code == 404
    assert error.value.code == "missing"
    assert error.value.message == "gone"


def test_invalid_response_is_stable() -> None:
    error = invalid_response()

    assert error.status_code == 502
    assert error.code == "database_response_invalid"
