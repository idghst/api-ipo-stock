from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
        self.payload: dict[str, object] | None = None
        self.filters: list[tuple[str, object]] = []
        self.ordering: list[tuple[str, bool, bool | None]] = []
        self.range_values: tuple[int, int] | None = None
        self.limit_value: int | None = None
        self.operation: str | None = None

    def select(self, *columns: str, count: object | None = None) -> "FakeQuery":
        self.columns = columns
        self.count = count
        return self

    def insert(self, payload: dict[str, object]) -> "FakeQuery":
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload: dict[str, object]) -> "FakeQuery":
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self) -> "FakeQuery":
        self.operation = "delete"
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
    fake = FakeSupabase(FakeResponse([IPO_STOCK], count=1))
    client, received_keys, http_client = _client_with_fake_admin(monkeypatch, fake)

    response = client.get(
        "/api/v1/ipo-stocks?limit=25&offset=5",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": [IPO_STOCK_JSON], "count": 1}
    assert received_keys == ["sb_secret_test"]
    assert http_client.closed is True
    assert fake.queries[0].table == "ipo_stocks"
    assert fake.queries[0].count == CountMethod.exact
    assert fake.queries[0].range_values == (5, 29)


def test_create_ipo_stock_accepts_only_camel_case_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSupabase(FakeResponse([IPO_STOCK]))
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.post(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "administrator-secret"},
        json={
            "companyName": "테스트 기업",
            "ticker": "test",
            "market": "KOSDAQ",
            "offerPrice": 12000,
            "subscriptionStart": "2026-08-10",
            "subscriptionEnd": "2026-08-11",
            "listingDate": "2026-08-20",
            "memo": "관리 대상",
        },
    )

    assert response.status_code == 201
    assert response.json() == IPO_STOCK_JSON
    assert fake.queries[0].payload == {
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


def test_create_ipo_stock_rejects_snake_case_payload() -> None:
    response = TestClient(_app()).post(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "administrator-secret"},
        json={"company_name": "테스트 기업"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_ipo_stock_rejects_invalid_subscription_range() -> None:
    response = TestClient(_app()).post(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "administrator-secret"},
        json={
            "companyName": "테스트 기업",
            "subscriptionStart": "2026-08-11",
            "subscriptionEnd": "2026-08-10",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_ipo_stock_maps_unique_ticker_to_stable_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate = APIError(
        {
            "code": "23505",
            "message": "private duplicate detail",
            "details": None,
            "hint": None,
        }
    )
    fake = FakeSupabase(duplicate)
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.post(
        "/api/v1/ipo-stocks",
        headers={"X-Admin-Key": "administrator-secret"},
        json={"companyName": "테스트 기업", "ticker": "TEST"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ticker_already_exists"
    assert "private duplicate detail" not in response.text


def test_get_ipo_stock_returns_camel_case_or_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSupabase(FakeResponse([IPO_STOCK]), FakeResponse([]))
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
    assert fake.queries[0].limit_value == 1
    assert missing.status_code == 404
    assert missing.json()["code"] == "ipo_stock_not_found"


def test_patch_ipo_stock_preserves_explicit_null_and_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleared = {**IPO_STOCK, "memo": None}
    fake = FakeSupabase(FakeResponse([cleared]), FakeResponse([]))
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    updated = client.patch(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
        json={"memo": None},
    )
    missing = client.patch(
        "/api/v1/ipo-stocks/019fc702-5c1b-7c1a-80f0-5f510de0f172",
        headers={"X-Admin-Key": "administrator-secret"},
        json={"status": "listed"},
    )

    assert updated.status_code == 200
    assert updated.json()["memo"] is None
    assert fake.queries[0].payload == {"memo": None}
    assert missing.status_code == 404
    assert missing.json()["code"] == "ipo_stock_not_found"


def test_patch_ipo_stock_rejects_empty_payload() -> None:
    response = TestClient(_app()).patch(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
        json={},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize("payload", [{"companyName": None}, {"status": None}])
def test_patch_ipo_stock_rejects_null_for_required_fields(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, None],
) -> None:
    fake = FakeSupabase()
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    response = client.patch(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert fake.queries == []


def test_delete_ipo_stock_returns_no_content_or_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSupabase(FakeResponse([{"id": IPO_STOCK["id"]}]), FakeResponse([]))
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)

    deleted = client.delete(
        f"/api/v1/ipo-stocks/{IPO_STOCK['id']}",
        headers={"X-Admin-Key": "administrator-secret"},
    )
    missing = client.delete(
        "/api/v1/ipo-stocks/019fc702-5c1b-7c1a-80f0-5f510de0f172",
        headers={"X-Admin-Key": "administrator-secret"},
    )

    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert missing.json()["code"] == "ipo_stock_not_found"


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
