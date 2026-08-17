from typing import Any, get_args

from postgrest.types import CountMethod
from pydantic import ValidationError

from app.schemas import (
    IpoStockCreate,
    IpoStockListOut,
    IpoStockOut,
    IpoStockStatus,
    IpoStockUpdate,
)
from app.services.postgrest import ensure_row, execute_query, invalid_response
from supabase import AsyncClient

READ_TABLE = "v_offerings"
WRITE_TABLE = "ipo_stocks"
_NOT_FOUND = ("ipo_stock_not_found", "IPO stock not found")
_CODE_ERRORS = {
    "23505": (409, "ticker_already_exists", "Ticker already exists"),
    "23514": (422, "invalid_ipo_stock", "IPO stock data is invalid"),
}
_STATUS_BY_LABEL = {
    "신규상장": "listed",
    "공모주": "scheduled",
    "공모철회": "cancelled",
    "공모철회 (공모철회)": "cancelled",
}


async def _execute(query: Any) -> tuple[list[dict[str, Any]], int | None]:
    return await execute_query(query, code_errors=_CODE_ERRORS)


def _ensure_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])


def _int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _status(value: object) -> IpoStockStatus:
    if value in get_args(IpoStockStatus):
        return value  # type: ignore[return-value]
    if isinstance(value, str) and value in _STATUS_BY_LABEL:
        return _STATUS_BY_LABEL[value]  # type: ignore[return-value]
    return "scheduled"


def _output(row: dict[str, Any]) -> IpoStockOut:
    if "company_name" in row:
        data = {**row, "id": str(row["id"])}
    else:
        data = {
            "id": str(row.get("id", "")),
            "company_name": row.get("name"),
            "ticker": row.get("stock_code"),
            "market": row.get("market"),
            "offer_price": _int_or_none(row.get("final_price_krw")),
            "subscription_start": row.get("subscribe_start"),
            "subscription_end": row.get("subscribe_end"),
            "listing_date": row.get("listing_date"),
            "status": _status(row.get("status")),
            "memo": row.get("note"),
        }
    try:
        return IpoStockOut.model_validate(data)
    except ValidationError as error:
        raise invalid_response() from error


async def list_ipo_stocks(
    client: AsyncClient,
    *,
    limit: int,
    offset: int,
) -> IpoStockListOut:
    rows, count = await _execute(
        client.table(READ_TABLE)
        .select("*", count=CountMethod.exact)
        .order("subscribe_start", nullsfirst=False)
        .order("name")
        .range(offset, offset + limit - 1)
    )
    if count is None:
        raise invalid_response()
    return IpoStockListOut(items=[_output(row) for row in rows], count=count)


async def get_ipo_stock(client: AsyncClient, ipo_stock_id: str) -> IpoStockOut:
    rows, _ = await _execute(
        client.table(READ_TABLE).select("*").eq("id", ipo_stock_id).limit(1)
    )
    return _output(_ensure_row(rows))


async def create_ipo_stock(
    client: AsyncClient,
    payload: IpoStockCreate,
) -> IpoStockOut:
    row = payload.model_dump(mode="json", by_alias=False)
    rows, _ = await _execute(client.table(WRITE_TABLE).insert(row).select("*"))
    return _output(_ensure_row(rows))


async def update_ipo_stock(
    client: AsyncClient,
    ipo_stock_id: str,
    payload: IpoStockUpdate,
) -> IpoStockOut:
    updates = payload.model_dump(mode="json", by_alias=False, exclude_unset=True)
    rows, _ = await _execute(
        client.table(WRITE_TABLE).update(updates).eq("id", ipo_stock_id).select("*")
    )
    return _output(_ensure_row(rows))


async def delete_ipo_stock(client: AsyncClient, ipo_stock_id: str) -> None:
    rows, _ = await _execute(
        client.table(WRITE_TABLE).delete().eq("id", ipo_stock_id).select("id")
    )
    _ensure_row(rows)
