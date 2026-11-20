import psycopg
import pytest
from psycopg import errors

from app.core.config import Settings
from app.core.errors import ApiError
from app.integrations import db
from app.services.db import ensure_row, fetch_all, invalid_response, map_db_error
from tests.test_ipo_stocks import FakeDb


@pytest.mark.parametrize(
    ("error", "status_code", "public_code"),
    [
        (errors.UndefinedTable("private"), 404, "table_not_found"),
        (errors.UndefinedColumn("private"), 404, "column_not_found"),
        (errors.InvalidTextRepresentation("private"), 422, "invalid_row"),
        (errors.InsufficientPrivilege("private"), 403, "database_access_denied"),
        (errors.QueryCanceled("private"), 503, "database_unavailable"),
        (psycopg.OperationalError("private"), 503, "database_unavailable"),
        (errors.InternalError_("private"), 502, "database_request_failed"),
        (errors.CheckViolation("private"), 502, "database_request_failed"),
        (psycopg.ProgrammingError("private"), 502, "database_request_failed"),
    ],
)
def test_map_db_error(error: psycopg.Error, status_code: int, public_code: str) -> None:
    mapped = map_db_error(error)

    assert mapped.status_code == status_code
    assert mapped.code == public_code
    assert "private" not in mapped.message


@pytest.mark.asyncio
async def test_fetch_all_binds_params_and_returns_rows() -> None:
    fake = FakeDb([{"id": 34}])

    rows = await fetch_all(fake, "select %s", (34,))  # type: ignore[arg-type]

    assert rows == [{"id": 34}]
    assert fake.queries == [("select %s", (34,))]


@pytest.mark.asyncio
async def test_fetch_all_maps_errors() -> None:
    fake = FakeDb(errors.InsufficientPrivilege("private"))

    with pytest.raises(ApiError) as error:
        await fetch_all(fake, "select 1")  # type: ignore[arg-type]

    assert error.value.code == "database_access_denied"


@pytest.mark.asyncio
async def test_connect_maps_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    async def refuse(conninfo: str, **kwargs: object) -> None:
        observed["conninfo"] = conninfo
        observed.update(kwargs)
        raise psycopg.OperationalError("private connection detail")

    monkeypatch.setattr(db.psycopg.AsyncConnection, "connect", refuse)

    with pytest.raises(ApiError) as error:
        await db.connect(Settings(DATABASE_URL="postgresql://app@db.test/ipostock"))

    assert error.value.status_code == 503
    assert error.value.code == "database_unavailable"
    assert "private" not in error.value.message
    assert observed["conninfo"] == "postgresql://app@db.test/ipostock"
    assert observed["connect_timeout"] == 5
    assert observed["options"] == "-c statement_timeout=5000"
    assert observed["autocommit"] is True


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
