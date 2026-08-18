from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, get_args
from zoneinfo import ZoneInfo

from postgrest.types import CountMethod
from pydantic import ValidationError

from app.schemas import (
    IpoStockListOut,
    IpoStockOut,
    IpoStockStatus,
    IpoStockSummaryOut,
)
from app.services.postgrest import ensure_row, execute_query, invalid_response
from supabase import AsyncClient

READ_TABLE = "v_offerings"
_NOT_FOUND = ("ipo_stock_not_found", "IPO stock not found")
_SEOUL = ZoneInfo("Asia/Seoul")
_UPCOMING_DAYS = 14
_FETCH_PAGE = 1000
_LIST_COLUMNS = (
    "id,name,stock_code,market,status,final_price_krw,subscribe_start,"
    "subscribe_end,listing_date,retail_comp_rate,inst_comp_rate,"
    "underwriters,hope_price,note,source_no"
)


async def _execute(query: Any) -> tuple[list[dict[str, Any]], int | None]:
    return await execute_query(query)


def _ensure_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])


def _today() -> date:
    return datetime.now(tz=_SEOUL).date()


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
    today = _today()
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
    if value == "신규상장":
        return "listed"
    return _gongmo_status(row or {})


def _status_raw(value: object) -> str | None:
    if isinstance(value, str) and value and value not in get_args(IpoStockStatus):
        return value
    return None


def _output(row: dict[str, Any]) -> IpoStockOut:
    data = {
        "id": str(row.get("id", "")),
        "company_name": row.get("name"),
        "ticker": row.get("stock_code"),
        "market": row.get("market"),
        "offer_price": _int_or_none(row.get("final_price_krw")),
        "subscription_start": row.get("subscribe_start"),
        "subscription_end": row.get("subscribe_end"),
        "listing_date": row.get("listing_date"),
        "status": _status(row.get("status_norm") or row.get("status"), row),
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


def _horizon(today: date) -> date:
    return today + timedelta(days=_UPCOMING_DAYS)


def _upcoming_dates(item: IpoStockOut, today: date) -> list[date]:
    horizon = _horizon(today)
    dates: list[date] = []
    if item.subscription_start and today <= item.subscription_start <= horizon:
        dates.append(item.subscription_start)
    if item.listing_date and today <= item.listing_date <= horizon:
        dates.append(item.listing_date)
    return dates


def _summary(items: list[IpoStockOut], today: date) -> IpoStockSummaryOut:
    counts = dict.fromkeys(get_args(IpoStockStatus), 0)
    upcoming_subscription = 0
    upcoming_listing = 0
    horizon = _horizon(today)
    for item in items:
        counts[item.status] += 1
        if item.subscription_start and today <= item.subscription_start <= horizon:
            upcoming_subscription += 1
        if item.listing_date and today <= item.listing_date <= horizon:
            upcoming_listing += 1
    return IpoStockSummaryOut(
        total=len(items),
        scheduled=counts["scheduled"],
        subscription_open=counts["subscription_open"],
        subscription_closed=counts["subscription_closed"],
        listed=counts["listed"],
        cancelled=counts["cancelled"],
        upcoming_subscription=upcoming_subscription,
        upcoming_listing=upcoming_listing,
    )


def _sort_key(item: IpoStockOut) -> tuple[int, int]:
    start = item.subscription_start
    if start is None:
        return (1, 0)
    return (0, -start.toordinal())


def _in_pipeline(item: IpoStockOut, today: date) -> bool:
    if item.status in {"scheduled", "subscription_open"}:
        return True
    return bool(
        item.status == "subscription_closed"
        and item.listing_date is not None
        and item.listing_date >= today
    )


def _matches(
    item: IpoStockOut,
    *,
    q: str | None,
    status: IpoStockStatus | None,
    date_from: date | None,
    date_to: date | None,
    pipeline: bool,
    today: date,
) -> bool:
    if status is not None and item.status != status:
        return False
    if pipeline and status is None and not _in_pipeline(item, today):
        return False
    if q:
        needle = q.casefold()
        haystacks = (item.company_name, item.ticker or "")
        if not any(needle in value.casefold() for value in haystacks):
            return False
    if date_from is None and date_to is None:
        return True
    dates = [
        value
        for value in (
            item.subscription_start,
            item.subscription_end,
            item.listing_date,
        )
        if value is not None
    ]
    if not dates:
        return False
    if date_from is not None and all(value < date_from for value in dates):
        return False
    return not (date_to is not None and all(value > date_to for value in dates))


async def _fetch_rows(client: AsyncClient, columns: str) -> list[dict[str, Any]]:
    rows_all: list[dict[str, Any]] = []
    offset = 0
    while True:
        rows, count = await _execute(
            client.table(READ_TABLE)
            .select(columns, count=CountMethod.exact)
            .order("id")
            .range(offset, offset + _FETCH_PAGE - 1)
        )
        if count is None:
            raise invalid_response()
        rows_all.extend(rows)
        offset += _FETCH_PAGE
        if offset >= count or not rows:
            break
    return rows_all


async def list_ipo_stocks(
    client: AsyncClient,
    *,
    limit: int,
    offset: int,
    q: str | None = None,
    status: IpoStockStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    pipeline: bool = False,
) -> IpoStockListOut:
    today = _today()
    query = q.strip() if q else None
    items = [_output(row) for row in await _fetch_rows(client, _LIST_COLUMNS)]
    filtered = [
        item
        for item in items
        if _matches(
            item,
            q=query,
            status=status,
            date_from=date_from,
            date_to=date_to,
            pipeline=pipeline,
            today=today,
        )
    ]
    filtered.sort(key=_sort_key)
    upcoming = [item for item in items if _upcoming_dates(item, today)]
    upcoming.sort(key=lambda item: min(_upcoming_dates(item, today)))
    return IpoStockListOut(
        items=filtered[offset : offset + limit],
        count=len(filtered),
        summary=_summary(items, today),
        upcoming=upcoming,
    )


async def get_ipo_stock(client: AsyncClient, ipo_stock_id: str) -> IpoStockOut:
    rows, _ = await _execute(
        client.table(READ_TABLE).select("*").eq("id", ipo_stock_id).limit(1)
    )
    return _output(_ensure_row(rows))
