from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import ApiError
from app.schemas import AuthMeOut

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@router.get("/me", response_model=AuthMeOut)
async def me(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthMeOut:
    if credentials is None:
        raise ApiError(401, "authentication_required", "Bearer token is required")
    # shortcut: Supabase Auth(GoTrue)를 멈춰 토큰을 검증할 곳이 없다. 자체 인증을 정하면 교체한다.
    raise ApiError(
        503,
        "authentication_service_unavailable",
        "Authentication service is unavailable",
    )
