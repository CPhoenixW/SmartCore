from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db.session import init_db
from app.feishu.event_handler import create_feishu_router
from app.web.routes import create_web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(create_feishu_router())
    app.include_router(create_web_router())

    return app


app = create_app()
