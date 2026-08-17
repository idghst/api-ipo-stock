import json
from pathlib import Path

import httpx
import pytest
from postgrest.exceptions import APIError

from tests.test_ipo_stocks import (
    IPO_STOCK,
    IPO_STOCK_JSON,
    FakeResponse,
    FakeSupabase,
    TestClient,
    _app,
    _client_with_fake_admin,
)

IPO_TABLE = {
    "name": "ipo_stocks",
    "kind": "table",
    "columns": [
        {"name": "id", "type": "uuid", "nullable": False, "primary_key": True},
        {
            "name": "company_name",
            "type": "text",
            "nullable": False,
            "primary_key": False,
        },
        {"name": "ticker", "type": "text", "nullable": True, "primary_key": False},
        {"name": "memo", "type": "text", "nullable": True, "primary_key": False},
    ],
}
IPO_TABLE_JSON = {
    "name": "ipo_stocks",
    "kind": "table",
    "columns": [
        {"name": "id", "type": "uuid", "nullable": False, "primaryKey": True},
        {
            "name": "company_name",
            "type": "text",
            "nullable": False,
            "primaryKey": False,
        },
        {"name": "ticker", "type": "text", "nullable": True, "primaryKey": False},
        {"name": "memo", "type": "text", "nullable": True, "primaryKey": False},
    ],
}
ADMIN = {"X-Admin-Key": "administrator-secret"}


def _rpc_client(
    monkeypatch: pytest.MonkeyPatch,
    *responses: FakeResponse | Exception,
    rpc_responses: list[FakeResponse | Exception],
) -> tuple[TestClient, FakeSupabase]:
    fake = FakeSupabase(*responses, rpc_responses=rpc_responses)
    client, _, _ = _client_with_fake_admin(monkeypatch, fake)
    return client, fake


def test_tables_require_administrator_key() -> None:
    response = TestClient(_app()).get("/api/v1/tables")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_admin_api_key"


def test_list_and_get_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _rpc_client(
        monkeypatch,
        rpc_responses=[
            FakeResponse([IPO_TABLE]),
            FakeResponse([IPO_TABLE]),
            FakeResponse([IPO_TABLE]),
        ],
    )

    listed = client.get("/api/v1/tables", headers=ADMIN)
    found = client.get("/api/v1/tables/ipo_stocks", headers=ADMIN)
    missing = client.get("/api/v1/tables/missing_table", headers=ADMIN)
    invalid = client.get("/api/v1/tables/BadName", headers=ADMIN)

    assert listed.status_code == 200
    assert listed.json() == {"items": [IPO_TABLE_JSON]}
    assert found.status_code == 200
    assert found.json() == IPO_TABLE_JSON
    assert missing.status_code == 404
    assert missing.json()["code"] == "table_not_found"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_table_name"
    assert fake.rpc_calls[0].fn == "schema_list_tables"


def test_list_tables_accepts_json_string_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        rpc_responses=[FakeResponse(json.dumps([IPO_TABLE]))],
    )

    response = client.get("/api/v1/tables", headers=ADMIN)

    assert response.status_code == 200
    assert response.json() == {"items": [IPO_TABLE_JSON]}


@pytest.mark.parametrize(
    "payload",
    [{"no": "list"}, "{not-json", [{"name": 1}]],
)
def test_list_tables_rejects_invalid_rpc_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> None:
    client, _ = _rpc_client(monkeypatch, rpc_responses=[FakeResponse(payload)])

    response = client.get("/api/v1/tables", headers=ADMIN)

    assert response.status_code == 502
    assert response.json()["code"] == "database_response_invalid"


def test_add_and_drop_column(monkeypatch: pytest.MonkeyPatch) -> None:
    created = {
        "name": "sector",
        "type": "text",
        "nullable": True,
        "primary_key": False,
    }
    client, fake = _rpc_client(
        monkeypatch,
        rpc_responses=[
            FakeResponse(created),
            FakeResponse({"name": "sector"}),
        ],
    )

    added = client.post(
        "/api/v1/tables/ipo_stocks/columns",
        headers=ADMIN,
        json={"name": "sector", "type": "text"},
    )
    dropped = client.delete(
        "/api/v1/tables/ipo_stocks/columns/sector",
        headers=ADMIN,
    )

    assert added.status_code == 201
    assert added.json() == {
        "name": "sector",
        "type": "text",
        "nullable": True,
        "primaryKey": False,
    }
    assert dropped.status_code == 200
    assert dropped.json() == {"name": "sector"}
    assert fake.rpc_calls[0].params == {
        "p_table": "ipo_stocks",
        "p_column": "sector",
        "p_type": "text",
        "p_nullable": True,
    }
    assert fake.rpc_calls[1].fn == "schema_drop_column"


def test_add_column_rejects_invalid_type() -> None:
    response = TestClient(_app()).post(
        "/api/v1/tables/ipo_stocks/columns",
        headers=ADMIN,
        json={"name": "sector", "type": "varchar"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_drop_column_rejects_invalid_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _rpc_client(monkeypatch, rpc_responses=[])

    response = client.delete(
        "/api/v1/tables/ipo_stocks/columns/BadColumn",
        headers=ADMIN,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_column_name"
    assert fake.rpc_calls == []


@pytest.mark.parametrize("payload", [{"name": "other"}, "{not-json"])
def test_drop_column_rejects_invalid_rpc_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        rpc_responses=[FakeResponse(payload)],
    )

    response = client.delete(
        "/api/v1/tables/ipo_stocks/columns/sector",
        headers=ADMIN,
    )

    assert response.status_code == 502
    assert response.json()["code"] == "database_response_invalid"


def test_drop_column_accepts_json_string_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        rpc_responses=[FakeResponse('{"name": "sector"}')],
    )

    response = client.delete(
        "/api/v1/tables/ipo_stocks/columns/sector",
        headers=ADMIN,
    )

    assert response.status_code == 200
    assert response.json() == {"name": "sector"}


@pytest.mark.parametrize("payload", ["{not-json", {"name": "sector"}])
def test_add_column_rejects_invalid_rpc_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> None:
    client, _ = _rpc_client(monkeypatch, rpc_responses=[FakeResponse(payload)])

    response = client.post(
        "/api/v1/tables/ipo_stocks/columns",
        headers=ADMIN,
        json={"name": "sector", "type": "text"},
    )

    assert response.status_code == 502
    assert response.json()["code"] == "database_response_invalid"


def test_add_column_accepts_json_string_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = {
        "name": "sector",
        "type": "text",
        "nullable": True,
        "primary_key": False,
    }
    client, _ = _rpc_client(
        monkeypatch,
        rpc_responses=[FakeResponse(json.dumps(created))],
    )

    response = client.post(
        "/api/v1/tables/ipo_stocks/columns",
        headers=ADMIN,
        json={"name": "sector", "type": "text"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "sector"


def test_add_column_rejects_invalid_table_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, fake = _rpc_client(monkeypatch, rpc_responses=[])

    response = client.post(
        "/api/v1/tables/BadName/columns",
        headers=ADMIN,
        json={"name": "sector", "type": "text"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_table_name"
    assert fake.rpc_calls == []


def test_schema_rpc_maps_missing_table(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        rpc_responses=[
            APIError(
                {
                    "code": "42P01",
                    "message": "private",
                    "details": None,
                    "hint": None,
                }
            )
        ],
    )

    response = client.post(
        "/api/v1/tables/ipo_stocks/columns",
        headers=ADMIN,
        json={"name": "sector", "type": "text"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "table_not_found"
    assert "private" not in response.text


def test_schema_rpc_maps_duplicate_column(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        rpc_responses=[
            APIError(
                {
                    "code": "42701",
                    "message": "private",
                    "details": None,
                    "hint": None,
                }
            )
        ],
    )

    response = client.post(
        "/api/v1/tables/ipo_stocks/columns",
        headers=ADMIN,
        json={"name": "memo", "type": "text"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "column_already_exists"
    assert "private" not in response.text


def test_row_crud_uses_schema_then_secret_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, fake = _rpc_client(
        monkeypatch,
        FakeResponse([IPO_STOCK], count=1),
        FakeResponse([IPO_STOCK]),
        FakeResponse([IPO_STOCK]),
        FakeResponse([{**IPO_STOCK, "memo": None}]),
        FakeResponse([{"id": IPO_STOCK["id"]}]),
        rpc_responses=[FakeResponse([IPO_TABLE]) for _ in range(5)],
    )

    listed = client.get(
        "/api/v1/tables/ipo_stocks/rows?limit=10&offset=0", headers=ADMIN
    )
    created = client.post(
        "/api/v1/tables/ipo_stocks/rows",
        headers=ADMIN,
        json={"companyName": "테스트 기업", "ticker": "TEST"},
    )
    found = client.get(
        f"/api/v1/tables/ipo_stocks/rows/{IPO_STOCK['id']}", headers=ADMIN
    )
    updated = client.patch(
        f"/api/v1/tables/ipo_stocks/rows/{IPO_STOCK['id']}",
        headers=ADMIN,
        json={"memo": None},
    )
    deleted = client.delete(
        f"/api/v1/tables/ipo_stocks/rows/{IPO_STOCK['id']}",
        headers=ADMIN,
    )

    assert listed.status_code == 200
    assert listed.json() == {"items": [IPO_STOCK_JSON], "count": 1}
    assert created.status_code == 201
    assert created.json() == IPO_STOCK_JSON
    assert fake.queries[1].payload == {
        "company_name": "테스트 기업",
        "ticker": "TEST",
    }
    assert found.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["memo"] is None
    assert deleted.status_code == 204
    assert fake.queries[0].table == "ipo_stocks"
    assert fake.queries[0].range_values == (0, 9)


def test_create_row_rejects_snake_case_and_unknown_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, fake = _rpc_client(
        monkeypatch,
        rpc_responses=[FakeResponse([IPO_TABLE]), FakeResponse([IPO_TABLE])],
    )

    snake = client.post(
        "/api/v1/tables/ipo_stocks/rows",
        headers=ADMIN,
        json={"company_name": "테스트 기업"},
    )
    unknown = client.post(
        "/api/v1/tables/ipo_stocks/rows",
        headers=ADMIN,
        json={"sector": "tech"},
    )

    assert snake.status_code == 422
    assert snake.json()["code"] == "validation_error"
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "unknown_column"
    assert fake.queries == []


def test_patch_row_rejects_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _rpc_client(
        monkeypatch,
        rpc_responses=[FakeResponse([IPO_TABLE])],
    )

    response = client.patch(
        f"/api/v1/tables/ipo_stocks/rows/{IPO_STOCK['id']}",
        headers=ADMIN,
        json={},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert fake.queries == []


def test_get_row_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        FakeResponse([]),
        rpc_responses=[FakeResponse([IPO_TABLE])],
    )

    response = client.get(
        "/api/v1/tables/ipo_stocks/rows/missing",
        headers=ADMIN,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "row_not_found"


def test_list_rows_uses_id_when_primary_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = {
        "name": "v_offerings",
        "kind": "view",
        "columns": [
            {"name": "id", "type": "bigint", "nullable": True, "primary_key": False}
        ],
    }
    client, fake = _rpc_client(
        monkeypatch,
        FakeResponse([{"id": 1}], count=1),
        rpc_responses=[FakeResponse([table])],
    )

    response = client.get("/api/v1/tables/v_offerings/rows", headers=ADMIN)

    assert response.status_code == 200
    assert response.json() == {"items": [{"id": 1}], "count": 1}
    assert fake.queries[0].ordering == [("id", False, None)]


def test_view_writes_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    table = {
        "name": "v_offerings",
        "kind": "view",
        "columns": [
            {"name": "id", "type": "bigint", "nullable": True, "primary_key": False}
        ],
    }
    client, fake = _rpc_client(
        monkeypatch,
        rpc_responses=[FakeResponse([table])],
    )

    response = client.post(
        "/api/v1/tables/v_offerings/rows",
        headers=ADMIN,
        json={"id": 1},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "read_only_relation"
    assert fake.queries == []


def test_composite_primary_key_row_crud(monkeypatch: pytest.MonkeyPatch) -> None:
    table = {
        "name": "offering_underwriters",
        "kind": "table",
        "columns": [
            {
                "name": "offering_id",
                "type": "bigint",
                "nullable": False,
                "primary_key": True,
            },
            {
                "name": "underwriter_id",
                "type": "bigint",
                "nullable": False,
                "primary_key": True,
            },
            {"name": "role", "type": "text", "nullable": False, "primary_key": True},
        ],
    }
    row = {"offering_id": 10, "underwriter_id": 3, "role": "주관"}
    client, fake = _rpc_client(
        monkeypatch,
        FakeResponse([row]),
        FakeResponse([row]),
        rpc_responses=[FakeResponse([table]), FakeResponse([table])],
    )

    found = client.get(
        "/api/v1/tables/offering_underwriters/rows/10|3|주관",
        headers=ADMIN,
    )
    updated = client.patch(
        "/api/v1/tables/offering_underwriters/rows/10|3|주관",
        headers=ADMIN,
        json={"role": "인수"},
    )

    assert found.status_code == 200
    assert found.json() == {
        "offeringId": 10,
        "underwriterId": 3,
        "role": "주관",
    }
    assert fake.queries[0].filters == [
        ("offering_id", "10"),
        ("underwriter_id", "3"),
        ("role", "주관"),
    ]
    assert updated.status_code == 200
    assert fake.queries[1].payload == {"role": "인수"}


def test_composite_row_id_must_match_primary_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = {
        "name": "offering_underwriters",
        "kind": "table",
        "columns": [
            {
                "name": "offering_id",
                "type": "bigint",
                "nullable": False,
                "primary_key": True,
            },
            {
                "name": "underwriter_id",
                "type": "bigint",
                "nullable": False,
                "primary_key": True,
            },
        ],
    }
    client, fake = _rpc_client(
        monkeypatch,
        rpc_responses=[FakeResponse([table])],
    )

    response = client.get(
        "/api/v1/tables/offering_underwriters/rows/10",
        headers=ADMIN,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_row_id"
    assert fake.queries == []


def test_routines_list_and_call(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _rpc_client(
        monkeypatch,
        rpc_responses=[
            FakeResponse(
                [
                    {
                        "name": "backfill_batch",
                        "args": "payload json",
                        "result": "TABLE(n_off bigint, n_ou bigint)",
                    }
                ]
            ),
            FakeResponse(
                [
                    {
                        "name": "backfill_batch",
                        "args": "payload json",
                        "result": "TABLE(n_off bigint, n_ou bigint)",
                    }
                ]
            ),
            FakeResponse([{"n_off": 2, "n_ou": 1}]),
            FakeResponse(
                [
                    {
                        "name": "backfill_batch",
                        "args": "payload json",
                        "result": "TABLE(n_off bigint, n_ou bigint)",
                    }
                ]
            ),
        ],
    )

    listed = client.get("/api/v1/routines", headers=ADMIN)
    called = client.post(
        "/api/v1/routines/backfill_batch",
        headers=ADMIN,
        json={"payload": [{"sourceNo": "1"}]},
    )
    missing = client.post(
        "/api/v1/routines/missing_fn",
        headers=ADMIN,
        json={},
    )

    assert listed.status_code == 200
    assert listed.json() == {
        "items": [
            {
                "name": "backfill_batch",
                "args": "payload json",
                "result": "TABLE(n_off bigint, n_ou bigint)",
            }
        ]
    }
    assert called.status_code == 200
    assert called.json() == [{"nOff": 2, "nOu": 1}]
    assert fake.rpc_calls[2].fn == "backfill_batch"
    assert fake.rpc_calls[2].params == {"payload": [{"sourceNo": "1"}]}
    assert missing.status_code == 404
    assert missing.json()["code"] == "routine_not_found"


def test_list_rows_rejects_missing_count(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        FakeResponse([IPO_STOCK], count=None),
        rpc_responses=[FakeResponse([IPO_TABLE])],
    )

    response = client.get("/api/v1/tables/ipo_stocks/rows", headers=ADMIN)

    assert response.status_code == 502
    assert response.json()["code"] == "database_response_invalid"


def test_row_unique_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        APIError(
            {
                "code": "23505",
                "message": "private duplicate detail",
                "details": None,
                "hint": None,
            }
        ),
        rpc_responses=[FakeResponse([IPO_TABLE])],
    )

    response = client.post(
        "/api/v1/tables/ipo_stocks/rows",
        headers=ADMIN,
        json={"companyName": "테스트 기업", "ticker": "TEST"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "unique_violation"
    assert "private duplicate detail" not in response.text


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


def test_list_tables_maps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _rpc_client(
        monkeypatch,
        rpc_responses=[httpx.ConnectError("offline")],
    )

    response = client.get("/api/v1/tables", headers=ADMIN)

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"
