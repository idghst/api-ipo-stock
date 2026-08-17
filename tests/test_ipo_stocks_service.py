from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
from postgrest.exceptions import APIError

from app.core.errors import ApiError
from app.schemas import IpoStockCreate, IpoStockUpdate
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
async def test_execute_maps_check_constraint_to_invalid_row() -> None:
    client = FakeSupabase(_api_error("23514"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(client, "019fc702-5c1b-7c1a-80f0-5f510de0f171")

    assert caught.value.status_code == 422
    assert caught.value.code == "invalid_row"


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
                    "source_no": "2304",
                    "name": "뷰 기업",
                    "stock_code": "123456",
                    "market": "코스닥",
                    "final_price": "15,000 원",
                    "final_price_krw": Decimal(15000),
                    "hope_price": "14,000 ~ 16,000 원",
                    "hope_price_low": "14000",
                    "hope_price_high": 16000.0,
                    "subscribe_start": "2026-08-10",
                    "subscribe_end": "2026-08-11",
                    "listing_date": "2026-08-20",
                    "status": "신규상장",
                    "note": "실데이터",
                    "underwriters": "삼성증권",
                    "industry": "제조업",
                    "open_vs_ipo_pct": Decimal("12.5"),
                }
            ]
        )
    )

    item = await ipo_stocks.get_ipo_stock(client, "41")
    dumped = item.model_dump(by_alias=True)

    assert item.id == "41"
    assert item.company_name == "뷰 기업"
    assert item.ticker == "123456"
    assert item.offer_price == 15000
    assert item.status == "listed"
    assert item.status_raw == "신규상장"
    assert item.memo == "실데이터"
    assert item.source_no == "2304"
    assert item.underwriters == "삼성증권"
    assert item.hope_price_low == 14000
    assert item.hope_price_high == 16000
    assert item.open_vs_ipo_pct == 12.5
    assert dumped["statusRaw"] == "신규상장"
    assert dumped["sourceNo"] == "2304"
    assert "retailApps" not in dumped


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
    assert item.status_raw == "알수없음"
    assert ipo_stocks._int_or_none(12.5) is None
    assert ipo_stocks._int_or_none(9) == 9
    assert ipo_stocks._int_or_none(Decimal(23000)) == 23000
    assert ipo_stocks._status("cancelled") == "cancelled"
    assert ipo_stocks._status("공모철회") == "cancelled"
    assert ipo_stocks._status("공모철회 (공모철회)") == "cancelled"


@pytest.mark.asyncio
async def test_output_maps_gongmo_status_from_dates() -> None:
    today = datetime.now(tz=ZoneInfo("Asia/Seoul")).date()
    closed = {
        "id": 36,
        "name": "해치텍",
        "status": "공모주",
        "subscribe_start": (today - timedelta(days=5)).isoformat(),
        "subscribe_end": (today - timedelta(days=4)).isoformat(),
        "listing_date": (today + timedelta(days=8)).isoformat(),
    }
    opened = {
        **closed,
        "id": 35,
        "subscribe_start": today.isoformat(),
        "subscribe_end": today.isoformat(),
    }
    scheduled = {
        **closed,
        "id": 34,
        "subscribe_start": (today + timedelta(days=10)).isoformat(),
        "subscribe_end": (today + timedelta(days=11)).isoformat(),
        "listing_date": None,
    }
    listed = {
        **closed,
        "id": 33,
        "listing_date": today.isoformat(),
    }
    client = FakeSupabase(
        FakeResponse([closed]),
        FakeResponse([opened]),
        FakeResponse([scheduled]),
        FakeResponse([listed]),
    )

    assert (
        await ipo_stocks.get_ipo_stock(client, "36")
    ).status == "subscription_closed"
    assert (await ipo_stocks.get_ipo_stock(client, "35")).status == "subscription_open"
    assert (await ipo_stocks.get_ipo_stock(client, "34")).status == "scheduled"
    assert (await ipo_stocks.get_ipo_stock(client, "33")).status == "listed"


@pytest.mark.asyncio
async def test_domain_writes_are_blocked() -> None:
    client = FakeSupabase()

    with pytest.raises(ApiError) as created:
        await ipo_stocks.create_ipo_stock(
            client, IpoStockCreate.model_validate({"companyName": "테스트"})
        )
    with pytest.raises(ApiError) as updated:
        await ipo_stocks.update_ipo_stock(
            client, "1", IpoStockUpdate.model_validate({"memo": "x"})
        )
    with pytest.raises(ApiError) as deleted:
        await ipo_stocks.delete_ipo_stock(client, "1")

    assert created.value.code == "unsupported_write_target"
    assert updated.value.code == "unsupported_write_target"
    assert deleted.value.code == "unsupported_write_target"
    assert client.queries == []
