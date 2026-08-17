from typing import Annotated

from fastapi import APIRouter, Depends

from app.integrations.supabase import AuthContext, get_auth_context
from app.schemas import AuthMeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthMeOut)
async def me(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthMeOut:
    return AuthMeOut(id=context.user.id, email=context.user.email)
