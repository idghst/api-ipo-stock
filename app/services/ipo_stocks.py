from typing import Any
from uuid import UUID

from postgrest.types import CountMethod
from pydantic import ValidationError

from app.core.errors import ApiError
from app.schemas import IpoStockCreate, IpoStockListOut, IpoStockOut, IpoStockUpdate
from app.services.postgrest import ensure_row, execute_query
from supabase import AsyncClient

TABLE_NAME = "ipo_stocks"
_NOT_FOUND = ("ipo_stock_not_found", "IPO stock not found")
_CODE_ERRORS = {
    "23505": (409, "ticker_already_exists", "Ticker already exists"),
    "23514": (422, "invalid_ipo_stock", "IPO stock data is invalid"),
}


async def _execute(query: Any) -> tuple[list[dict[str, Any]], int | None]:
    return await execute_query(query, code_errors=_CODE_ERRORS)


def _ensure_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return ensure_row(rows, code=_NOT_FOUND[0], message=_NOT_FOUND[1])


def _output(row: dict[str, Any]) -> IpoStockOut:
    try:
        return IpoStockOut.model_validate(row)
    except ValidationError as error:
        raise ApiError(
            502,
            "database_response_invalid",
            "Database returned an invalid response",
        ) from error


async def list_ipo_stocks(
    client: AsyncClient,
    *,
    limit: int,
    offset: int,
) -> IpoStockListOut:
    rows, count = await _execute(
        client.table(TABLE_NAME)
        .select("*", count=CountMethod.exact)
        .order("subscription_start", nullsfirst=False)
        .order("company_name")
        .range(offset, offset + limit - 1)
    )
    if count is None:
        raise ApiError(
            502,
            "database_response_invalid",
            "Database returned an invalid response",
        )
    return IpoStockListOut(items=[_output(row) for row in rows], count=count)


async def get_ipo_stock(client: AsyncClient, ipo_stock_id: UUID) -> IpoStockOut:
    rows, _ = await _execute(
        client.table(TABLE_NAME).select("*").eq("id", str(ipo_stock_id)).limit(1)
    )
    return _output(_ensure_row(rows))


async def create_ipo_stock(
    client: AsyncClient,
    payload: IpoStockCreate,
) -> IpoStockOut:
    row = payload.model_dump(mode="json", by_alias=False)
    rows, _ = await _execute(client.table(TABLE_NAME).insert(row).select("*"))
    return _output(_ensure_row(rows))


async def update_ipo_stock(
    client: AsyncClient,
    ipo_stock_id: UUID,
    payload: IpoStockUpdate,
) -> IpoStockOut:
    updates = payload.model_dump(mode="json", by_alias=False, exclude_unset=True)
    rows, _ = await _execute(
        client.table(TABLE_NAME).update(updates).eq("id", str(ipo_stock_id)).select("*")
    )
    return _output(_ensure_row(rows))


async def delete_ipo_stock(client: AsyncClient, ipo_stock_id: UUID) -> None:
    rows, _ = await _execute(
        client.table(TABLE_NAME).delete().eq("id", str(ipo_stock_id)).select("id")
    )
    _ensure_row(rows)
