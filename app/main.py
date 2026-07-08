from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agent.legacy_time_routes import createLegacyTimeRouter
from app.agent.routes import createAgentRouter, createDevRouter
from app.agent.v2_routes import createAgentV2Router
from app.api.device_state_routes import router as deviceStateApiRouter
from app.api.routes import router as apiRouter
from app.config import get_settings
from app.db.session import init_db
from app.device.routes import router as deviceRouter
from app.feishu.event_handler import create_feishu_router
from app.scheduler.service import build_scheduler_service
from app.screen.routes import router as screenRouter
from app.web.device_routes import router as workDeviceRouter
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

    parse_router = __import__("app.api.ai_routes", fromlist=["router"]).router
    app.include_router(parse_router)
    app.include_router(deviceStateApiRouter)
    app.include_router(apiRouter)
    app.include_router(createDevRouter())
    app.include_router(deviceRouter)
    app.include_router(createAgentV2Router())
    app.include_router(createLegacyTimeRouter())
    app.include_router(createAgentRouter())
    app.include_router(create_feishu_router())
    app.include_router(workRouter)
    app.include_router(workDeviceRouter)
    app.include_router(screenRouter)

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount("/static/work", StaticFiles(directory=static_dir), name="work_static")
    screen_static_dir = Path(__file__).resolve().parent / "screen" / "static"
    app.mount(
        "/static/screen",
        StaticFiles(directory=screen_static_dir),
        name="screen_static",
    )

    return app


app = create_app()
