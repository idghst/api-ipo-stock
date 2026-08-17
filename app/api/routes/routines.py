from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.integrations.supabase import get_admin_api_client
from app.schemas import RoutineListOut
from app.services import tables
from supabase import AsyncClient

router = APIRouter(prefix="/routines", tags=["routines"])
AdminClient = Annotated[AsyncClient, Depends(get_admin_api_client)]


@router.get("", response_model=RoutineListOut)
async def list_routines(client: AdminClient) -> RoutineListOut:
    return await tables.list_routines(client)


@router.post("/{routine_name}")
async def call_routine(
    routine_name: str,
    payload: dict[str, Any],
    client: AdminClient,
) -> object:
    return await tables.call_routine(client, routine_name, payload)
