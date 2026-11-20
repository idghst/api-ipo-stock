from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from psycopg import errors

from app.core.config import Settings
from app.main import create_app

IPO_STOCK = {
    "id": "019fc702-5c1b-7c1a-80f0-5f510de0f171",
    "company_name": "테스트 기업",
    "ticker": "TEST",
    "market": "KOSDAQ",
    "offer_price": 12000,
    "subscription_start": "2026-08-10",
    "subscription_end": "2026-08-11",
    "listing_date": "2026-08-20",
    "status": "scheduled",
    "memo": "관리 대상",
}
OFFERING_ROW = {
    "id": IPO_STOCK["id"],
    "name": "테스트 기업",
    "stock_code": "TEST",
    "market": "KOSDAQ",
    "final_price_krw": 12000,
    "subscribe_start": "2026-08-10",
    "subscribe_end": "2026-08-11",
    "listing_date": "2026-08-20",
    "status": "scheduled",
    "note": "관리 대상",
}

IPO_STOCK_JSON = {
    "id": IPO_STOCK["id"],
    "companyName": "테스트 기업",
    "ticker": "TEST",
    "market": "KOSDAQ",
    "offerPrice": 12000,
    "subscriptionStart": "2026-08-10",
    "subscriptionEnd": "2026-08-11",
    "listingDate": "2026-08-20",
    "status": "scheduled",
    "memo": "관리 대상",
}


def _today() -> date:
    return datetime.now(tz=ZoneInfo("Asia/Seoul")).date()


def _in_upcoming(value: str | None) -> bool:
    if not value:
        return False
    parsed = date.fromisoformat(value)
    today = _today()
    return today <= parsed <= today + timedelta(days=14)


def _list_payload(
    items: list[dict[str, Any]], *, count: int | None = None
) -> dict[str, Any]:
    summary = {
        "total": len(items),
        "scheduled": 0,
        "subscriptionOpen": 0,
        "subscriptionClosed": 0,
        "listed": 0,
        "cancelled": 0,
        "upcomingSubscription": 0,
        "upcomingListing": 0,
    }
    aliases = {
        "scheduled": "scheduled",
        "subscription_open": "subscriptionOpen",
        "subscription_closed": "subscriptionClosed",
        "listed": "listed",
        "cancelled": "cancelled",
    }
    upcoming: list[dict[str, Any]] = []
    for item in items:
        summary[aliases[item["status"]]] += 1
        if _in_upcoming(item.get("subscriptionStart")):
            summary["upcomingSubscription"] += 1
        if _in_upcoming(item.get("listingDate")):
            summary["upcomingListing"] += 1
        if _in_upcoming(item.get("subscriptionStart")) or _in_upcoming(
            item.get("listingDate")
        ):
            upcoming.append(item)
    upcoming.sort(
        key=lambda item: min(
            date
            for date in (
                item.get("subscriptionStart"),
                item.get("listingDate"),
            )
            if date and _in_upcoming(date)
        )
    )
    return {
        "items": items,
        "count": len(items) if count is None else count,
        "summary": summary,
        "upcoming": upcoming,
    }


class FakeDb:
    def __init__(self, *responses: list[dict[str, Any]] | Exception) -> None:
        self.responses = list(responses)
        self.queries: list[tuple[str, tuple[object, ...]]] = []
        self.rows: list[dict[str, Any]] = []
        self.closed = False

    async def execute(self, query: str, params: tuple[object, ...] = ()) -> "FakeDb":
        self.queries.append((query, params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        self.rows = response
        return self

    async def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    async def close(self) -> None:
        self.closed = True


def _app() -> object:
    return create_app(
        Settings(
            DATABASE_URL="postgresql://app@db.test/ipostock",
            IPO_STOCK_API_KEY="administrator-secret",
        )
    )


def _client_with_fake_admin(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeDb,
) -> tuple[TestClient, list[str]]:
    from app.integrations import db

    connected: list[str] = []

    async def connect(settings: Settings) -> FakeDb:
        connected.append(settings.DATABASE_URL.get_secret_value())
        return fake

    monkeypatch.setattr(db, "connect", connect)
    return TestClient(_app()), connected


def test_ipo_stock_list_requires_administrator_key() -> None:
    response = TestClient(_app()).get("/api/v1/ipo-stocks")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_admin_api_key"


def test_invalid_administrator_key_does_not_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, connected = _client_with_fake_admin(monkeypatch, FakeDb())
    response = client.get(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "wrong-key"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_admin_api_key"
    assert connected == []


def test_list_ipo_stocks_reads_view_and_returns_camel_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDb([OFFERING_ROW])
    client, connected = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        "/api/v1/ipo-stocks?limit=25&offset=0",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 200
    assert response.json() == _list_payload([IPO_STOCK_JSON])
    assert connected == ["postgresql://app@db.test/ipostock"]
    assert fake.closed is True
    assert "from ipostock.v_offerings order by id" in fake.queries[0][0]
    assert fake.queries[0][1] == ()


def test_ipo_stock_writes_are_not_routed() -> None:
    client = TestClient(_app())
    headers = {"X-Admin-Key": "administrator-secret"}

    created = client.post("/api/v1/ipo-stocks", headers=headers, json={})
    updated = client.patch(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}", headers=headers, json={}
    )
    deleted = client.delete(f"/api/v1/ipo-stocks/{IPO_STOCK['id']}", headers=headers)

    assert created.status_code == 405
    assert updated.status_code == 405
    assert deleted.status_code == 405


def test_tables_and_routines_are_not_mounted() -> None:
    client = TestClient(_app())
    headers = {"X-Admin-Key": "administrator-secret"}

    assert client.get("/api/v1/tables", headers=headers).status_code == 404
    assert client.get("/api/v1/routines", headers=headers).status_code == 404


def test_openapi_exposes_read_only_surface() -> None:
    spec = TestClient(_app()).get("/openapi.json").json()
    paths = spec["paths"]

    assert set(paths["/api/v1/ipo-stocks"]) == {"get"}
    assert set(paths["/api/v1/ipo-stocks/{ipo_stock_id}"]) == {"get"}
    assert not any(
        path.startswith(("/api/v1/tables", "/api/v1/routines")) for path in paths
    )


def test_get_ipo_stock_exposes_view_columns_and_status_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(tz=ZoneInfo("Asia/Seoul")).date()
    fake = FakeDb(
        [
            {
                "id": 36,
                "source_no": "2304",
                "name": "해치텍",
                "stock_code": "0155E0",
                "market": "코스닥",
                "status": "공모주",
                "underwriters": "DB증권",
                "hope_price": "23,000 ~ 28,000 원",
                "hope_price_low": 23000,
                "final_price": "23,000 원",
                "final_price_krw": 23000,
                "subscribe_start": (today - timedelta(days=5)).isoformat(),
                "subscribe_end": (today - timedelta(days=4)).isoformat(),
                "listing_date": (today + timedelta(days=8)).isoformat(),
                "note": None,
            }
        ]
    )
    client, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        "/api/v1/ipo-stocks/36",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["id"] == "36"
    assert body["companyName"] == "해치텍"
    assert body["ticker"] == "0155E0"
    assert body["market"] == "코스닥"
    assert body["offerPrice"] == 23000
    assert body["status"] == "subscription_closed"
    assert body["statusRaw"] == "공모주"
    assert body["sourceNo"] == "2304"
    assert body["underwriters"] == "DB증권"
    assert body["hopePrice"] == "23,000 ~ 28,000 원"
    assert body["memo"] is None
    assert "retailApps" not in body


def test_get_ipo_stock_ignores_unknown_database_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDb([{**OFFERING_ROW, "sector": "tech"}])
    client, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 200
    assert response.json() == IPO_STOCK_JSON


def test_get_ipo_stock_returns_camel_case_or_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDb([OFFERING_ROW], [])
    client, _ = _client_with_fake_admin(monkeypatch, fake)

    found = client.get(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
    )
    missing = client.get(
        "/api/v1/ipo-stocks/019fc702-5c1b-7c1a-80f0-5f510de0f172",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert found.status_code == 200
    assert found.json() == IPO_STOCK_JSON
    assert fake.queries[0] == (
        "select * from ipostock.v_offerings where id = %s limit 1",
        (IPO_STOCK["id"],),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "ipo_stock_not_found"


def test_get_ipo_stock_rejects_invalid_row_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDb([{"id": IPO_STOCK["id"]}])
    client, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 502
    assert response.json()["code"] == "database_response_invalid"


def test_ipo_stock_maps_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDb(errors.InsufficientPrivilege("private privilege detail"))
    client, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "database_access_denied"
    assert "private privilege detail" not in response.text


def test_list_ipo_stocks_filters_and_keeps_global_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = _today()
    scheduled = {
        **OFFERING_ROW,
        "id": 34,
        "name": "스카이랩스",
        "stock_code": "SKY",
        "status": "공모주",
        "subscribe_start": (today + timedelta(days=8)).isoformat(),
        "subscribe_end": (today + timedelta(days=9)).isoformat(),
        "listing_date": None,
        "note": None,
    }
    listed = {
        **OFFERING_ROW,
        "id": 41,
        "name": "과거상장",
        "stock_code": "OLD",
        "status": "신규상장",
        "subscribe_start": "2020-01-01",
        "subscribe_end": "2020-01-02",
        "listing_date": "2020-01-10",
        "note": None,
    }
    fake = FakeDb(
        [scheduled, listed],
        [scheduled, listed],
        [scheduled, listed],
    )
    client, _ = _client_with_fake_admin(monkeypatch, fake)

    filtered = client.get(
        "/api/v1/ipo-stocks?q=스카이&pipeline=true",
        headers={"X-Admin-Key": "administrator-secret"},
    )
    listed_only = client.get(
        "/api/v1/ipo-stocks?status=listed",
        headers={"X-Admin-Key": "administrator-secret"},
    )
    dated = client.get(
        f"/api/v1/ipo-stocks?dateFrom={today.isoformat()}&dateTo={(today + timedelta(days=14)).isoformat()}",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    body = filtered.json()
    assert filtered.status_code == 200
    assert body["count"] == 1
    assert body["items"][0]["companyName"] == "스카이랩스"
    assert body["items"][0]["status"] == "scheduled"
    assert body["summary"]["total"] == 2
    assert body["summary"]["scheduled"] == 1
    assert body["summary"]["listed"] == 1
    assert body["summary"]["upcomingSubscription"] == 1
    assert listed_only.status_code == 200
    assert listed_only.json()["count"] == 1
    assert listed_only.json()["items"][0]["status"] == "listed"
    assert dated.status_code == 200
    assert dated.json()["count"] == 1
    assert dated.json()["items"][0]["companyName"] == "스카이랩스"
