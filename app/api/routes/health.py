from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.integrations.db import connect

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


async def probe_database(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    try:
        async with await connect(settings) as connection:
            await connection.execute("select 1")
    except (ApiError, psycopg.Error) as error:
        raise ApiError(
            503, "dependency_unavailable", "Database is unavailable"
        ) from error


@router.get("/ready")
async def readiness(_: Annotated[None, Depends(probe_database)]) -> dict[str, str]:
    return {"status": "ok"}
