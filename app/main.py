from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.agent.feedback_routes import createFeedbackRouter, ensure_feedback_tools
from app.agent.legacy_time_routes import createLegacyTimeRouter
from app.agent.relation_query_routes import createRelationQueryRouter
from app.agent.relation_write_routes import createRelationWriteRouter
from app.agent.routes import createAgentRouter, createDevRouter
from app.agent.v2_routes import createAgentV2Router
from app.api.admin_routes import router as adminApiRouter
from app.api.auth_routes import router as authApiRouter
from app.api.avatar_routes import router as avatarApiRouter
from app.api.device_state_routes import router as deviceStateApiRouter
from app.api.event_view_routes import router as eventViewApiRouter
from app.api.routes import router as apiRouter
from app.auth.security import session_user_id_from_request
from app.auth.storage import ensure_auth_schema
from app.config import get_settings
from app.db.session import SessionLocal, init_db
from app.device.routes import router as deviceRouter
from app.feishu.event_handler import create_feishu_router
from app.new_core.relation_compat import install_relation_compat
from app.new_core.relation_maintenance import (
    close_past_course_occurrences,
    ensure_missing_relations,
)
from app.scheduler.service import build_scheduler_service
from app.screen.routes import router as screenRouter
from app.user_device.routes import router as userDeviceRouter


def _sync_event_relations() -> None:
    db = SessionLocal()
    try:
        ensure_missing_relations(db)
        close_past_course_occurrences(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _initialize_database() -> None:
    init_db()
    ensure_auth_schema()
    install_relation_compat()
    _sync_event_relations()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _initialize_database()
    settings = get_settings()
    scheduler_service = build_scheduler_service(settings)
    if scheduler_service is not None:
        scheduler_service.start()
    try:
        yield
    finally:
        if scheduler_service is not None:
            scheduler_service.shutdown()


def _register_work_frontend(app: FastAPI) -> None:
    frontend_dist = Path(__file__).resolve().parent / "web" / "dist"
    frontend_assets = frontend_dist / "assets"

    if frontend_dist.is_dir() and frontend_assets.is_dir():
        app.mount("/work/assets", StaticFiles(directory=frontend_assets), name="work_assets")

        @app.get("/work", include_in_schema=False)
        @app.get("/work/{path:path}", include_in_schema=False)
        def serve_work(request: Request, path: str = "") -> Response:
            user_id = session_user_id_from_request(request)
            if path == "login":
                if user_id:
                    return RedirectResponse("/work", status_code=303)
                return FileResponse(frontend_dist / "index.html")
            if not user_id:
                next_path = quote(request.url.path, safe="/")
                return RedirectResponse(f"/work/login?next={next_path}", status_code=303)
            return FileResponse(frontend_dist / "index.html")
    else:

        @app.get("/work", include_in_schema=False)
        @app.get("/work/{path:path}", include_in_schema=False)
        def serve_missing_work(path: str = "") -> PlainTextResponse:
            return PlainTextResponse(
                "SmartCore frontend build is missing. Build frontend/ before starting the app.",
                status_code=503,
            )

    @app.get("/work-v2", include_in_schema=False)
    @app.get("/work-v2/{path:path}", include_in_schema=False)
    def redirect_work_v2(path: str = "") -> RedirectResponse:
        suffix = f"/{path}" if path else ""
        return RedirectResponse(f"/work{suffix}", status_code=308)


def create_app() -> FastAPI:
    _initialize_database()
    settings = get_settings()
    ensure_feedback_tools()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    parse_router = __import__("app.api.ai_routes", fromlist=["router"]).router
    app.include_router(authApiRouter)
    app.include_router(adminApiRouter)
    app.include_router(parse_router)
    app.include_router(avatarApiRouter)
    app.include_router(deviceStateApiRouter)
    app.include_router(eventViewApiRouter)
    app.include_router(apiRouter)
    app.include_router(createDevRouter())
    app.include_router(deviceRouter)
    app.include_router(userDeviceRouter)
    app.include_router(createRelationQueryRouter())
    app.include_router(createRelationWriteRouter())
    app.include_router(createFeedbackRouter())
    app.include_router(createAgentV2Router())
    app.include_router(createLegacyTimeRouter())
    app.include_router(createAgentRouter())
    app.include_router(create_feishu_router())
    app.include_router(screenRouter)

    screen_static_dir = Path(__file__).resolve().parent / "screen" / "static"
    app.mount("/static/screen", StaticFiles(directory=screen_static_dir), name="screen_static")

    _register_work_frontend(app)
    return app


app = create_app()
