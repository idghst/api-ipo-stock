from typing import Annotated

import httpx
from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.errors import ApiError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


def probe_supabase(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    try:
        response = httpx.get(
            f"{str(settings.SUPABASE_URL).rstrip('/')}/auth/v1/health",
            headers={"apikey": settings.SUPABASE_PUBLISHABLE_KEY.get_secret_value()},
            timeout=settings.SUPABASE_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as error:
        raise ApiError(
            503, "dependency_unavailable", "Supabase is unavailable"
        ) from error

    if not response.is_success:
        raise ApiError(503, "dependency_unavailable", "Supabase is unavailable")


@router.get("/ready")
async def readiness(_: Annotated[None, Depends(probe_supabase)]) -> dict[str, str]:
    return {"status": "ok"}
