from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from postgrest.types import CountMethod

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


@dataclass
class FakeResponse:
    data: object
    count: int | None = None


class FakeQuery:
    def __init__(self, table: str, responses: list[FakeResponse | Exception]) -> None:
        self.table = table
        self.responses = responses
        self.columns: tuple[str, ...] = ()
        self.count: object | None = None
        self.filters: list[tuple[str, object]] = []
        self.ordering: list[tuple[str, bool, bool | None]] = []
        self.range_values: tuple[int, int] | None = None
        self.limit_value: int | None = None

    def select(self, *columns: str, count: object | None = None) -> "FakeQuery":
        self.columns = columns
        self.count = count
        return self

    def eq(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def order(
        self,
        column: str,
        *,
        desc: bool = False,
        nullsfirst: bool | None = None,
    ) -> "FakeQuery":
        self.ordering.append((column, desc, nullsfirst))
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.range_values = (start, end)
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.limit_value = value
        return self

    async def execute(self) -> FakeResponse:
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeSupabase:
    def __init__(self, *responses: FakeResponse | Exception) -> None:
        self.responses = list(responses)
        self.queries: list[FakeQuery] = []

    def table(self, name: str) -> FakeQuery:
        query = FakeQuery(name, self.responses)
        self.queries.append(query)
        return query


class FakeHttpClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def _app() -> object:
    return create_app(
        Settings(
            SUPABASE_URL="https://test.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
            SUPABASE_SECRET_KEY="sb_secret_test",
            IPO_STOCK_API_KEY="administrator-secret",
        )
    )


def _client_with_fake_admin(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeSupabase,
) -> tuple[TestClient, list[str], FakeHttpClient]:
    from app.integrations import supabase

    received_keys: list[str] = []
    http_client = FakeHttpClient()

    async def new_client(_: Settings, key: str) -> tuple[Any, FakeHttpClient]:
        received_keys.append(key)
        return fake, http_client

    monkeypatch.setattr(supabase, "_new_client", new_client)
    return TestClient(_app()), received_keys, http_client


def test_ipo_stock_list_requires_administrator_key() -> None:
    response = TestClient(_app()).get("/api/v1/ipo-stocks")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_admin_api_key"


def test_invalid_administrator_key_does_not_create_secret_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.integrations import supabase

    attempted_keys: list[str] = []

    async def unexpected_client(_: Settings, key: str) -> tuple[Any, Any]:
        attempted_keys.append(key)
        raise AssertionError("secret client must not be created")

    monkeypatch.setattr(supabase, "_new_client", unexpected_client)
    response = TestClient(_app()).get(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "wrong-key"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_admin_api_key"
    assert attempted_keys == []


def test_list_ipo_stocks_uses_secret_client_and_returns_camel_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSupabase(FakeResponse([OFFERING_ROW], count=1))
    client, received_keys, http_client = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        "/api/v1/ipo-stocks?limit=25&offset=0",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 200
    assert response.json() == _list_payload([IPO_STOCK_JSON])
    assert received_keys == ["sb_secret_test"]
    assert http_client.closed is True
    assert fake.queries[0].table == "v_offerings"
    assert fake.queries[0].count == CountMethod.exact
    assert fake.queries[0].range_values == (0, 999)


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
    fake = FakeSupabase(
        FakeResponse(
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
    )
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

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
    fake = FakeSupabase(FakeResponse([{**OFFERING_ROW, "sector": "tech"}]))
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 200
    assert response.json() == IPO_STOCK_JSON


def test_get_ipo_stock_returns_camel_case_or_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSupabase(FakeResponse([OFFERING_ROW]), FakeResponse([]))
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

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
    assert fake.queries[0].table == "v_offerings"
    assert fake.queries[0].limit_value == 1
    assert missing.status_code == 404
    assert missing.json()["code"] == "ipo_stock_not_found"


def test_list_ipo_stocks_rejects_missing_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSupabase(FakeResponse([OFFERING_ROW], count=None))
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 502
    assert response.json()["code"] == "database_response_invalid"


def test_get_ipo_stock_rejects_invalid_row_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSupabase(FakeResponse([{"id": IPO_STOCK["id"]}]))
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 502
    assert response.json()["code"] == "database_response_invalid"


def test_ipo_stock_maps_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSupabase(
        APIError(
            {
                "code": "42501",
                "message": "private privilege detail",
                "details": None,
                "hint": None,
            }
        )
    )
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "database_access_denied"
    assert "private privilege detail" not in response.text


def test_ipo_stocks_migration_keeps_data_api_roles_unprivileged() -> None:
    migration = next(
        (Path(__file__).parents[1] / "supabase" / "migrations").glob(
            "*_add_ipo_stocks_table.sql"
        )
    ).read_text()

    assert "create table if not exists ipo_stock.ipo_stocks" in migration
    assert "alter table ipo_stock.ipo_stocks enable row level security;" in migration
    assert (
        "revoke all privileges on schema ipo_stock from public, anon, authenticated;"
        in migration
    )
    assert (
        "revoke all privileges on table ipo_stock.ipo_stocks from public, anon, authenticated;"
        in migration
    )
    assert "grant usage on schema ipo_stock to service_role;" in migration
    assert (
        "grant select, insert, update, delete on table ipo_stock.ipo_stocks to service_role;"
        in migration
    )


def test_schema_admin_migration_keeps_functions_service_role_only() -> None:
    migration = next(
        (Path(__file__).parents[1] / "supabase" / "migrations").glob(
            "*_add_schema_admin_functions.sql"
        )
    ).read_text()

    assert "create or replace function ipo_stock.schema_list_tables()" in migration
    assert "create or replace function ipo_stock.schema_add_column(" in migration
    assert "create or replace function ipo_stock.schema_drop_column(" in migration
    assert "pg_notify('pgrst', 'reload schema')" in migration
    assert (
        "revoke all on function ipo_stock.schema_list_tables() from public, anon, authenticated;"
        in migration
    )
    assert (
        "grant execute on function ipo_stock.schema_list_tables() to service_role;"
        in migration
    )
    hyphen = next(
        (Path(__file__).parents[1] / "supabase" / "migrations").glob(
            "*_add_ipo_stock_hyphen_schema_admin.sql"
        )
    ).read_text()
    assert 'create or replace function "ipo-stock".schema_list_tables()' in hyphen
    assert 'create or replace function "ipo-stock".schema_list_routines()' in hyphen
    assert (
        'revoke all on function "ipo-stock".schema_list_routines() from public, anon, authenticated;'
        in hyphen
    )
    revoke = next(
        (Path(__file__).parents[1] / "supabase" / "migrations").glob(
            "*_revoke_ipo_stock_backfill_from_data_api.sql"
        )
    ).read_text()
    assert (
        'revoke all on function "ipo-stock".backfill_batch(json) from public, anon, authenticated;'
        in revoke
    )


def test_v_offerings_wrapper_migration_is_service_role_select_only() -> None:
    migration = next(
        (Path(__file__).parents[1] / "supabase" / "migrations").glob(
            "*_add_ipo_stock_v_offerings_view.sql"
        )
    ).read_text()

    assert "create schema if not exists ipo_stock;" in migration
    assert "with (security_invoker = true)" in migration
    assert 'as select * from "ipo-stock".v_offerings' in migration
    assert (
        "revoke all on table ipo_stock.v_offerings from public, anon, authenticated"
        in migration
    )
    assert "grant select on table ipo_stock.v_offerings to service_role" in migration
    assert "grant insert" not in migration.lower()
    assert "grant update" not in migration.lower()
    assert "grant delete" not in migration.lower()
    assert "notify pgrst, 'reload schema'" in migration


def test_v_offerings_status_norm_migration_is_select_only() -> None:
    migration = next(
        (Path(__file__).parents[1] / "supabase" / "migrations").glob(
            "*_enrich_ipo_stock_v_offerings_status_norm.sql"
        )
    ).read_text()

    assert "status_norm" in migration
    assert "with (security_invoker = true)" in migration
    assert 'from "ipo-stock".v_offerings as src' in migration
    assert (
        "revoke all on table ipo_stock.v_offerings from public, anon, authenticated"
        in migration
    )
    assert "grant select on table ipo_stock.v_offerings to service_role" in migration
    assert "grant insert" not in migration.lower()
    assert "notify pgrst, 'reload schema'" in migration


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
    fake = FakeSupabase(
        FakeResponse([scheduled, listed], count=2),
        FakeResponse([scheduled, listed], count=2),
        FakeResponse([scheduled, listed], count=2),
    )
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

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
