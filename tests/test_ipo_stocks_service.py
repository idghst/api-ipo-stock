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
        await ipo_stocks.get_ipo_stock(client, "019fc702-5c1b-7c1a-80f0-5f510de0f171")

    assert caught.value.status_code == 422
    assert caught.value.code == "invalid_ipo_stock"


@pytest.mark.asyncio
async def test_execute_maps_permission_error_to_access_denied() -> None:
    client = FakeSupabase(_api_error("42501"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(client, "019fc702-5c1b-7c1a-80f0-5f510de0f171")

    assert caught.value.status_code == 403
    assert caught.value.code == "database_access_denied"


@pytest.mark.asyncio
async def test_execute_maps_unknown_postgrest_error_to_502() -> None:
    client = FakeSupabase(_api_error("XX000"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(client, "019fc702-5c1b-7c1a-80f0-5f510de0f171")

    assert caught.value.status_code == 502
    assert caught.value.code == "database_request_failed"


@pytest.mark.asyncio
async def test_execute_maps_http_error_to_unavailable() -> None:
    client = FakeSupabase(httpx.ConnectError("connection refused"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(client, "019fc702-5c1b-7c1a-80f0-5f510de0f171")

    assert caught.value.status_code == 503
    assert caught.value.code == "database_unavailable"


@pytest.mark.asyncio
async def test_execute_rejects_invalid_response_shape() -> None:
    client = FakeSupabase(FakeResponse({"id": "not-a-list"}))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(client, "019fc702-5c1b-7c1a-80f0-5f510de0f171")

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
        await ipo_stocks.get_ipo_stock(client, "019fc702-5c1b-7c1a-80f0-5f510de0f171")

    assert caught.value.status_code == 502
    assert caught.value.code == "database_response_invalid"


@pytest.mark.asyncio
async def test_output_maps_offering_view_row() -> None:
    client = FakeSupabase(
        FakeResponse(
            [
                {
                    "id": 41,
                    "name": "뷰 기업",
                    "stock_code": "123456",
                    "market": "KOSDAQ",
                    "final_price_krw": 15000.0,
                    "subscribe_start": "2026-08-10",
                    "subscribe_end": "2026-08-11",
                    "listing_date": "2026-08-20",
                    "status": "신규상장",
                    "note": "실데이터",
                }
            ]
        )
    )

    item = await ipo_stocks.get_ipo_stock(client, "41")

    assert item.id == "41"
    assert item.company_name == "뷰 기업"
    assert item.ticker == "123456"
    assert item.offer_price == 15000
    assert item.status == "listed"
    assert item.memo == "실데이터"


@pytest.mark.asyncio
async def test_output_maps_offering_status_and_price_fallbacks() -> None:
    client = FakeSupabase(
        FakeResponse(
            [
                {
                    "id": 7,
                    "name": "기본값",
                    "final_price_krw": True,
                    "status": "알수없음",
                }
            ]
        )
    )

    item = await ipo_stocks.get_ipo_stock(client, "7")

    assert item.offer_price is None
    assert item.status == "scheduled"
    assert ipo_stocks._int_or_none(12.5) is None
    assert ipo_stocks._int_or_none(9) == 9
    assert ipo_stocks._status("cancelled") == "cancelled"
    assert ipo_stocks._status("공모철회") == "cancelled"
