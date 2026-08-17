from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, get_args
from zoneinfo import ZoneInfo

from postgrest.types import CountMethod
from pydantic import ValidationError

from app.core.errors import ApiError
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
_NOT_FOUND = ("ipo_stock_not_found", "IPO stock not found")
_WRITE_BLOCKED = ApiError(
    422,
    "unsupported_write_target",
    "Live schema has no ipo_stocks table. Write companies/offerings via "
    "/api/v1/tables or POST /api/v1/routines/backfill_batch.",
)
_STATUS_BY_LABEL = {
    "신규상장": "listed",
    "공모주": "scheduled",
    "공모철회": "cancelled",
    "공모철회 (공모철회)": "cancelled",
}


async def _execute(query: Any) -> tuple[list[dict[str, Any]], int | None]:
    return await execute_query(query)


def _ensure_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])


def _number(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except InvalidOperation:
            return None
        return _number(parsed)
    return None


def _int_or_none(value: object) -> int | None:
    number = _number(value)
    return number if isinstance(number, int) else None


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _gongmo_status(row: dict[str, Any]) -> IpoStockStatus:
    today = datetime.now(tz=ZoneInfo("Asia/Seoul")).date()
    listing = _as_date(row.get("listing_date"))
    start = _as_date(row.get("subscribe_start"))
    end = _as_date(row.get("subscribe_end"))
    if listing is not None and listing <= today:
        return "listed"
    if start is not None and end is not None and start <= today <= end:
        return "subscription_open"
    if end is not None and end < today:
        return "subscription_closed"
    return "scheduled"


def _status(value: object, row: dict[str, Any] | None = None) -> IpoStockStatus:
    if value in get_args(IpoStockStatus):
        return value  # type: ignore[return-value]
    if isinstance(value, str) and value.startswith("공모철회"):
        return "cancelled"
    if value == "공모주":
        return _gongmo_status(row or {})
    if isinstance(value, str) and value in _STATUS_BY_LABEL:
        return _STATUS_BY_LABEL[value]  # type: ignore[return-value]
    return "scheduled"


def _status_raw(value: object) -> str | None:
    if isinstance(value, str) and value and value not in get_args(IpoStockStatus):
        return value
    return None


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
            "status": _status(row.get("status"), row),
            "status_raw": _status_raw(row.get("status")),
            "memo": row.get("note"),
            "source_no": row.get("source_no"),
            "detail_url": row.get("detail_url"),
            "underwriters": row.get("underwriters"),
            "hope_price": row.get("hope_price"),
            "hope_price_low": _number(row.get("hope_price_low")),
            "hope_price_high": _number(row.get("hope_price_high")),
            "final_price": row.get("final_price"),
            "offering_shares": row.get("offering_shares"),
            "offering_shares_count": _number(row.get("offering_shares_count")),
            "par_value": row.get("par_value"),
            "offering_amount": row.get("offering_amount"),
            "offering_mix": row.get("offering_mix"),
            "retail_comp_rate": row.get("retail_comp_rate"),
            "inst_comp_rate": row.get("inst_comp_rate"),
            "retail_apps": row.get("retail_apps"),
            "bookbuilding_start": row.get("bookbuilding_start"),
            "bookbuilding_end": row.get("bookbuilding_end"),
            "payment_date": row.get("payment_date"),
            "refund_date": row.get("refund_date"),
            "allotment_date": row.get("allotment_date"),
            "ir_period": row.get("ir_period"),
            "lockup_ratio": row.get("lockup_ratio"),
            "industry": row.get("industry"),
            "ceo": row.get("ceo"),
            "hq": row.get("hq"),
            "products": row.get("products"),
            "company_type": row.get("company_type"),
            "homepage": row.get("homepage"),
            "major_shareholder": row.get("major_shareholder"),
            "revenue": row.get("revenue"),
            "net_income": row.get("net_income"),
            "capital": row.get("capital"),
            "open_price_krw": _number(row.get("open_price_krw")),
            "open_vs_ipo_pct": _number(row.get("open_vs_ipo_pct")),
            "first_close_krw": _number(row.get("first_close_krw")),
            "collected_at": row.get("collected_at"),
            "updated_at": row.get("updated_at"),
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
    _client: AsyncClient,
    _payload: IpoStockCreate,
) -> IpoStockOut:
    raise _WRITE_BLOCKED


async def update_ipo_stock(
    _client: AsyncClient,
    _ipo_stock_id: str,
    _payload: IpoStockUpdate,
) -> IpoStockOut:
    raise _WRITE_BLOCKED


async def delete_ipo_stock(_client: AsyncClient, _ipo_stock_id: str) -> None:
    raise _WRITE_BLOCKED
