from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.integrations.supabase import get_admin_api_client
from app.schemas import IpoStockCreate, IpoStockListOut, IpoStockOut, IpoStockUpdate
from app.services import ipo_stocks
from supabase import AsyncClient

router = APIRouter(prefix="/ipo-stocks", tags=["ipo-stocks"])
AdminClient = Annotated[AsyncClient, Depends(get_admin_api_client)]


@router.get("", response_model=IpoStockListOut, response_model_by_alias=True)
async def list_ipo_stocks(
    client: AdminClient,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IpoStockListOut:
    return await ipo_stocks.list_ipo_stocks(client, limit=limit, offset=offset)


@router.post(
    "",
    response_model=IpoStockOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_ipo_stock(
    payload: IpoStockCreate,
    client: AdminClient,
) -> IpoStockOut:
    return await ipo_stocks.create_ipo_stock(client, payload)


@router.get(
    "/{ipo_stock_id}",
    response_model=IpoStockOut,
    response_model_by_alias=True,
)
async def get_ipo_stock(ipo_stock_id: UUID, client: AdminClient) -> IpoStockOut:
    return await ipo_stocks.get_ipo_stock(client, ipo_stock_id)


@router.patch(
    "/{ipo_stock_id}",
    response_model=IpoStockOut,
    response_model_by_alias=True,
)
async def update_ipo_stock(
    ipo_stock_id: UUID,
    payload: IpoStockUpdate,
    client: AdminClient,
) -> IpoStockOut:
    return await ipo_stocks.update_ipo_stock(client, ipo_stock_id, payload)


@router.delete("/{ipo_stock_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ipo_stock(ipo_stock_id: UUID, client: AdminClient) -> None:
    await ipo_stocks.delete_ipo_stock(client, ipo_stock_id)
