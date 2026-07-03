from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.routes import createAgentRouter, createDevRouter
from app.api.routes import router as apiRouter
from app.config import get_settings
from app.db.session import init_db
from app.feishu.event_handler import create_feishu_router
from app.scheduler.service import build_scheduler_service
from app.screen.routes import router as screenRouter
from app.web.work_routes import router as workRouter


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    scheduler_service = build_scheduler_service(settings)
    if scheduler_service is not None:
        scheduler_service.start()
    try:
        yield
    finally:
        if scheduler_service is not None:
            scheduler_service.shutdown()


def create_app() -> FastAPI:
    init_db()
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(apiRouter)
    app.include_router(createDevRouter())
    app.include_router(createAgentRouter())
    app.include_router(create_feishu_router())
    app.include_router(workRouter)
    app.include_router(screenRouter)

    return app


app = create_app()
