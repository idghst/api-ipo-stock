from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.integrations.supabase import get_admin_api_client
from app.schemas import IpoStockListOut, IpoStockOut, IpoStockStatus
from app.services import ipo_stocks
from supabase import AsyncClient

router = APIRouter(prefix="/ipo-stocks", tags=["ipo-stocks"])
AdminClient = Annotated[AsyncClient, Depends(get_admin_api_client)]


@router.get("", response_model=IpoStockListOut, response_model_by_alias=True)
async def list_ipo_stocks(
    client: AdminClient,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(max_length=80)] = None,
    status: Annotated[IpoStockStatus | None, Query()] = None,
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
    pipeline: Annotated[bool, Query()] = False,
) -> IpoStockListOut:
    return await ipo_stocks.list_ipo_stocks(
        client,
        limit=limit,
        offset=offset,
        q=q,
        status=status,
        date_from=date_from,
        date_to=date_to,
        pipeline=pipeline,
    )


@router.get(
    "/{ipo_stock_id}",
    response_model=IpoStockOut,
    response_model_by_alias=True,
)
async def get_ipo_stock(ipo_stock_id: str, client: AdminClient) -> IpoStockOut:
    return await ipo_stocks.get_ipo_stock(client, ipo_stock_id)
