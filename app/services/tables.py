import json
import re
from typing import Any

from postgrest.types import CountMethod
from pydantic import ValidationError

from app.core.errors import ApiError
from app.schemas import (
    IDENT_PATTERN,
    ColumnCreate,
    ColumnNameOut,
    ColumnOut,
    RowListOut,
    TableListOut,
    TableOut,
)
from app.services.postgrest import (
    ensure_row,
    execute_query,
    execute_rpc,
    invalid_response,
)
from supabase import AsyncClient

_IDENT = re.compile(IDENT_PATTERN)


def _require_ident(value: str, code: str, message: str) -> str:
    if _IDENT.fullmatch(value) is None:
        raise ApiError(422, code, message)
    return value


def _snake_to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail if part)


def _camel_to_snake(name: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(name):
        if char.isupper():
            if index:
                chars.append("_")
            chars.append(char.lower())
        else:
            chars.append(char)
    return "".join(chars)


def _row_out(row: dict[str, Any]) -> dict[str, Any]:
    return {_snake_to_camel(key): value for key, value in row.items()}


def _decode_json(data: object) -> object:
    if not isinstance(data, str):
        return data
    try:
        return json.loads(data)
    except json.JSONDecodeError as error:
        raise invalid_response() from error


def _parse_tables(data: object) -> list[TableOut]:
    data = _decode_json(data)
    if not isinstance(data, list):
        raise invalid_response()
    try:
        return [TableOut.model_validate(item) for item in data]
    except ValidationError as error:
        raise invalid_response() from error


def _parse_column(data: object) -> ColumnOut:
    try:
        return ColumnOut.model_validate(_decode_json(data))
    except ValidationError as error:
        raise invalid_response() from error


def _ensure_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return ensure_row(rows, code="row_not_found", message="Row not found")


def _primary_key(table: TableOut) -> str:
    keys = [column.name for column in table.columns if column.primary_key]
    if len(keys) != 1:
        raise ApiError(
            422,
            "unsupported_primary_key",
            "Table must have a single primary key",
        )
    return keys[0]


def _row_in(payload: dict[str, Any], columns: set[str]) -> dict[str, Any]:
    if any("_" in key for key in payload):
        raise ApiError(422, "validation_error", "Request validation failed")
    converted: dict[str, Any] = {}
    for key, value in payload.items():
        column = _camel_to_snake(key)
        if column not in columns:
            raise ApiError(422, "unknown_column", "Unknown column")
        converted[column] = value
    return converted


async def list_tables(client: AsyncClient) -> TableListOut:
    data = await execute_rpc(client.rpc("schema_list_tables", {}))
    return TableListOut(items=_parse_tables(data))


async def get_table(client: AsyncClient, table_name: str) -> TableOut:
    _require_ident(table_name, "invalid_table_name", "Table name is invalid")
    for table in (await list_tables(client)).items:
        if table.name == table_name:
            return table
    raise ApiError(404, "table_not_found", "Table not found")


async def add_column(
    client: AsyncClient, table_name: str, payload: ColumnCreate
) -> ColumnOut:
    _require_ident(table_name, "invalid_table_name", "Table name is invalid")
    data = await execute_rpc(
        client.rpc(
            "schema_add_column",
            {
                "p_table": table_name,
                "p_column": payload.name,
                "p_type": payload.type,
                "p_nullable": payload.nullable,
            },
        )
    )
    return _parse_column(data)


async def drop_column(
    client: AsyncClient, table_name: str, column_name: str
) -> ColumnNameOut:
    _require_ident(table_name, "invalid_table_name", "Table name is invalid")
    _require_ident(column_name, "invalid_column_name", "Column name is invalid")
    data = _decode_json(
        await execute_rpc(
            client.rpc(
                "schema_drop_column",
                {"p_table": table_name, "p_column": column_name},
            )
        )
    )
    if not isinstance(data, dict) or data.get("name") != column_name:
        raise invalid_response()
    return ColumnNameOut(name=column_name)


async def list_rows(
    client: AsyncClient,
    table_name: str,
    *,
    limit: int,
    offset: int,
) -> RowListOut:
    table = await get_table(client, table_name)
    primary_key = _primary_key(table)
    rows, count = await execute_query(
        client.table(table.name)
        .select("*", count=CountMethod.exact)
        .order(primary_key)
        .range(offset, offset + limit - 1)
    )
    if count is None:
        raise invalid_response()
    return RowListOut(items=[_row_out(row) for row in rows], count=count)


async def get_row(client: AsyncClient, table_name: str, row_id: str) -> dict[str, Any]:
    table = await get_table(client, table_name)
    primary_key = _primary_key(table)
    rows, _ = await execute_query(
        client.table(table.name).select("*").eq(primary_key, row_id).limit(1)
    )
    return _row_out(_ensure_row(rows))


async def create_row(
    client: AsyncClient, table_name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    table = await get_table(client, table_name)
    row = _row_in(payload, {column.name for column in table.columns})
    rows, _ = await execute_query(client.table(table.name).insert(row))
    return _row_out(_ensure_row(rows))


async def update_row(
    client: AsyncClient,
    table_name: str,
    row_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    table = await get_table(client, table_name)
    updates = _row_in(payload, {column.name for column in table.columns})
    if not updates:
        raise ApiError(422, "validation_error", "Request validation failed")
    primary_key = _primary_key(table)
    rows, _ = await execute_query(
        client.table(table.name).update(updates).eq(primary_key, row_id)
    )
    return _row_out(_ensure_row(rows))


async def delete_row(client: AsyncClient, table_name: str, row_id: str) -> None:
    table = await get_table(client, table_name)
    primary_key = _primary_key(table)
    rows, _ = await execute_query(
        client.table(table.name).delete().eq(primary_key, row_id)
    )
    _ensure_row(rows)
