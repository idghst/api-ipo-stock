from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.integrations.supabase import get_admin_api_client
from app.schemas import (
    ColumnCreate,
    ColumnNameOut,
    ColumnOut,
    RowListOut,
    TableListOut,
    TableOut,
)
from app.services import tables
from supabase import AsyncClient

router = APIRouter(prefix="/tables", tags=["tables"])
AdminClient = Annotated[AsyncClient, Depends(get_admin_api_client)]


@router.get("", response_model=TableListOut, response_model_by_alias=True)
async def list_tables(client: AdminClient) -> TableListOut:
    return await tables.list_tables(client)


@router.get("/{table_name}", response_model=TableOut, response_model_by_alias=True)
async def get_table(table_name: str, client: AdminClient) -> TableOut:
    return await tables.get_table(client, table_name)


@router.post(
    "/{table_name}/columns",
    response_model=ColumnOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def add_column(
    table_name: str,
    payload: ColumnCreate,
    client: AdminClient,
) -> ColumnOut:
    return await tables.add_column(client, table_name, payload)


@router.delete(
    "/{table_name}/columns/{column_name}",
    response_model=ColumnNameOut,
)
async def drop_column(
    table_name: str,
    column_name: str,
    client: AdminClient,
) -> ColumnNameOut:
    return await tables.drop_column(client, table_name, column_name)


@router.get("/{table_name}/rows", response_model=RowListOut)
async def list_rows(
    table_name: str,
    client: AdminClient,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RowListOut:
    return await tables.list_rows(client, table_name, limit=limit, offset=offset)


@router.post(
    "/{table_name}/rows",
    status_code=status.HTTP_201_CREATED,
)
async def create_row(
    table_name: str,
    payload: dict[str, Any],
    client: AdminClient,
) -> dict[str, Any]:
    return await tables.create_row(client, table_name, payload)


@router.get("/{table_name}/rows/{row_id}")
async def get_row(
    table_name: str,
    row_id: str,
    client: AdminClient,
) -> dict[str, Any]:
    return await tables.get_row(client, table_name, row_id)


@router.patch("/{table_name}/rows/{row_id}")
async def update_row(
    table_name: str,
    row_id: str,
    payload: dict[str, Any],
    client: AdminClient,
) -> dict[str, Any]:
    return await tables.update_row(client, table_name, row_id, payload)


@router.delete(
    "/{table_name}/rows/{row_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_row(
    table_name: str,
    row_id: str,
    client: AdminClient,
) -> None:
    await tables.delete_row(client, table_name, row_id)
