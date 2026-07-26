from typing import Annotated

from fastapi import APIRouter, Depends

from app.integrations.supabase import AuthContext, get_auth_context

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def me(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> dict[str, str | None]:
    return {"id": context.user.id, "email": context.user.email}
