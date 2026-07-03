from collections.abc import Callable, Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_bound_database_url: str | None = None


def _ensure_engine() -> tuple[Engine, sessionmaker[Session]]:
    global _engine, _session_factory, _bound_database_url
    settings = get_settings()
    database_url = settings.database_url
    if _engine is not None and _bound_database_url == database_url:
        assert _session_factory is not None
        return _engine, _session_factory

    if _engine is not None:
        _engine.dispose()

    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    _engine = create_engine(database_url, connect_args=connect_args)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    _bound_database_url = database_url
    return _engine, _session_factory


class _SessionLocalFactory:
    def __call__(self) -> Session:
        _, session_factory = _ensure_engine()
        return session_factory()


SessionLocal: Callable[[], Session] = _SessionLocalFactory()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def dispose_engine() -> None:
    global _engine, _session_factory, _bound_database_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _bound_database_url = None


def reset_engine_for_tests() -> None:
    dispose_engine()


def init_db() -> None:
    from app.new_core import models  # noqa: F401

    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine, _ = _ensure_engine()
    Base.metadata.create_all(bind=engine)
