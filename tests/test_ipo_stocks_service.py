from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
from postgrest.exceptions import APIError

from app.core.errors import ApiError
from app.services import ipo_stocks
from tests.test_ipo_stocks import OFFERING_ROW, FakeResponse, FakeSupabase


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
async def test_execute_maps_unknown_constraint_to_request_failed() -> None:
    client = FakeSupabase(_api_error("23514"))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.get_ipo_stock(client, "019fc702-5c1b-7c1a-80f0-5f510de0f171")

    assert caught.value.status_code == 502
    assert caught.value.code == "database_request_failed"


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
    client = FakeSupabase(FakeResponse([OFFERING_ROW], count=None))

    with pytest.raises(ApiError) as caught:
        await ipo_stocks.list_ipo_stocks(client, limit=10, offset=0)

    assert caught.value.status_code == 502
    assert caught.value.code == "database_response_invalid"


@pytest.mark.asyncio
async def test_list_rejects_boolean_count() -> None:
    client = FakeSupabase(FakeResponse([OFFERING_ROW], count=True))

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
    assert (
        ipo_stocks._status(
            None,
            {
                "subscribe_start": "2004-12-01",
                "subscribe_end": "2004-12-02",
                "listing_date": None,
            },
        )
        == "subscription_closed"
    )
    assert (
        ipo_stocks._status(
            None,
            {
                "subscribe_start": "2012-01-16",
                "subscribe_end": "2012-01-17",
                "listing_date": "2012-01-31",
            },
        )
        == "listed"
    )


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
async def test_list_sorts_by_subscription_start_desc() -> None:
    today = datetime.now(tz=ZoneInfo("Asia/Seoul")).date()
    older = {
        **OFFERING_ROW,
        "id": 9,
        "name": "과거상장",
        "status": "신규상장",
        "subscribe_start": "2020-01-01",
        "subscribe_end": "2020-01-02",
        "listing_date": "2020-01-10",
        "note": None,
    }
    newer = {
        **OFFERING_ROW,
        "id": 2,
        "name": "예정종목",
        "status": "공모주",
        "subscribe_start": (today + timedelta(days=5)).isoformat(),
        "subscribe_end": (today + timedelta(days=6)).isoformat(),
        "listing_date": None,
        "note": None,
    }
    missing = {
        **OFFERING_ROW,
        "id": 3,
        "name": "날짜없음",
        "status": "공모주",
        "subscribe_start": None,
        "subscribe_end": None,
        "listing_date": None,
        "note": None,
    }
    client = FakeSupabase(FakeResponse([older, missing, newer], count=3))

    page = await ipo_stocks.list_ipo_stocks(client, limit=10, offset=0)

    assert [item.company_name for item in page.items] == [
        "예정종목",
        "과거상장",
        "날짜없음",
    ]
    assert page.summary.total == 3
    assert page.upcoming[0].company_name == "예정종목"


@pytest.mark.asyncio
async def test_pipeline_keeps_only_calendar_closed_rows() -> None:
    today = datetime.now(tz=ZoneInfo("Asia/Seoul")).date()
    awaiting = {
        **OFFERING_ROW,
        "id": 36,
        "name": "해치텍",
        "status": "공모주",
        "subscribe_start": (today - timedelta(days=6)).isoformat(),
        "subscribe_end": (today - timedelta(days=5)).isoformat(),
        "listing_date": (today + timedelta(days=7)).isoformat(),
        "note": None,
    }
    historic = {
        **OFFERING_ROW,
        "id": 5,
        "name": "모빌리언스",
        "status": None,
        "subscribe_start": "2004-12-01",
        "subscribe_end": "2004-12-02",
        "listing_date": None,
        "note": None,
    }
    client = FakeSupabase(FakeResponse([awaiting, historic], count=2))

    page = await ipo_stocks.list_ipo_stocks(client, limit=10, offset=0, pipeline=True)

    assert page.summary.subscription_closed == 2
    assert [item.company_name for item in page.items] == ["해치텍"]


@pytest.mark.asyncio
async def test_pipeline_sorts_by_subscription_start_desc() -> None:
    today = datetime.now(tz=ZoneInfo("Asia/Seoul")).date()
    opened = {
        **OFFERING_ROW,
        "id": 1,
        "name": "청약중",
        "status": "공모주",
        "subscribe_start": today.isoformat(),
        "subscribe_end": today.isoformat(),
        "listing_date": (today + timedelta(days=10)).isoformat(),
        "note": None,
    }
    later = {
        **OFFERING_ROW,
        "id": 2,
        "name": "더늦은예정",
        "status": "공모주",
        "subscribe_start": (today + timedelta(days=20)).isoformat(),
        "subscribe_end": (today + timedelta(days=21)).isoformat(),
        "listing_date": None,
        "note": None,
    }
    closed = {
        **OFFERING_ROW,
        "id": 3,
        "name": "마감대기",
        "status": "공모주",
        "subscribe_start": (today - timedelta(days=6)).isoformat(),
        "subscribe_end": (today - timedelta(days=5)).isoformat(),
        "listing_date": (today + timedelta(days=7)).isoformat(),
        "note": None,
    }
    client = FakeSupabase(FakeResponse([opened, closed, later], count=3))

    page = await ipo_stocks.list_ipo_stocks(client, limit=10, offset=0, pipeline=True)

    assert [item.company_name for item in page.items] == [
        "더늦은예정",
        "청약중",
        "마감대기",
    ]
