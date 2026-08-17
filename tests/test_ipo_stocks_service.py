from uuid import UUID

import httpx
import pytest
from postgrest.exceptions import APIError

from app.core.errors import ApiError
from app.services import ipo_stocks
from tests.test_ipo_stocks import IPO_STOCK, FakeResponse, FakeSupabase


def _api_error(code: str) -> APIError:
    return APIError(
        {
            "code": code,
            "message": "private upstream detail",
            "details": None,
            "hint": None,
        }
    )


@pytest.mark.asyncio
async def test_execute_maps_check_constraint_to_invalid_ipo_stock() -> None:
    client = FakeSupabase(_api_error("23514"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(
            client, UUID("019fc702-5c1b-7c1a-80f0-5f510de0f171")
        )

    assert caught.value.status_code == 422
    assert caught.value.code == "invalid_ipo_stock"


@pytest.mark.asyncio
async def test_execute_maps_permission_error_to_access_denied() -> None:
    client = FakeSupabase(_api_error("42501"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(
            client, UUID("019fc702-5c1b-7c1a-80f0-5f510de0f171")
        )

    assert caught.value.status_code == 403
    assert caught.value.code == "database_access_denied"


@pytest.mark.asyncio
async def test_execute_maps_unknown_postgrest_error_to_502() -> None:
    client = FakeSupabase(_api_error("XX000"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(
            client, UUID("019fc702-5c1b-7c1a-80f0-5f510de0f171")
        )

    assert caught.value.status_code == 502
    assert caught.value.code == "database_request_failed"


@pytest.mark.asyncio
async def test_execute_maps_http_error_to_unavailable() -> None:
    client = FakeSupabase(httpx.ConnectError("connection refused"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(
            client, UUID("019fc702-5c1b-7c1a-80f0-5f510de0f171")
        )

    assert caught.value.status_code == 503
    assert caught.value.code == "database_unavailable"


@pytest.mark.asyncio
async def test_execute_rejects_invalid_response_shape() -> None:
    client = FakeSupabase(FakeResponse({"id": "not-a-list"}))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(
            client, UUID("019fc702-5c1b-7c1a-80f0-5f510de0f171")
        )

    assert caught.value.status_code == 502
    assert caught.value.code == "database_response_invalid"


@pytest.mark.asyncio
async def test_list_rejects_missing_count() -> None:
    client = FakeSupabase(FakeResponse([IPO_STOCK], count=None))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.list_ipo_stocks(client, limit=10, offset=0)

    assert caught.value.status_code == 502
    assert caught.value.code == "database_response_invalid"


@pytest.mark.asyncio
async def test_list_rejects_boolean_count() -> None:
    client = FakeSupabase(FakeResponse([IPO_STOCK], count=True))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.list_ipo_stocks(client, limit=10, offset=0)

    assert caught.value.status_code == 502
    assert caught.value.code == "database_response_invalid"


@pytest.mark.asyncio
async def test_output_rejects_invalid_row() -> None:
    client = FakeSupabase(FakeResponse([{"id": "not-a-uuid"}]))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(
            client, UUID("019fc702-5c1b-7c1a-80f0-5f510de0f171")
        )

    assert caught.value.status_code == 502
    assert caught.value.code == "database_response_invalid"
