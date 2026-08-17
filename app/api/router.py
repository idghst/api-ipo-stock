from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.ipo_stocks import router as ipo_stocks_router
from app.api.routes.routines import router as routines_router
from app.api.routes.tables import router as tables_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(ipo_stocks_router)
api_router.include_router(tables_router)
api_router.include_router(routines_router)
