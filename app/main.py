from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.middleware.request_context import RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        description=(
            "IPO 목록/상세는 GET only. 데이터는 ipo_stock.v_offerings SELECT."
        ),
    )
    app.state.settings = settings
    app.dependency_overrides[get_settings] = lambda: settings
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"message": settings.app_name}

    return app


app = create_app()
