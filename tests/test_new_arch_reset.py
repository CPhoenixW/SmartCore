from pathlib import Path

from app.db.session import SessionLocal, init_db
from app.new_core import crud
from app.new_core.reset_db import resetDatabase


def test_explicit_reset_database_clears_old_file_and_recreates_new_tables(app_env) -> None:
    db_path = Path(app_env)
    init_db()
    db = SessionLocal()
    try:
        crud.createLifeEvt(db, title="会被清空", dueAt=None, src="test")
    finally:
        db.close()

    backup_path = resetDatabase()
    assert backup_path is not None
    assert backup_path.exists()

    db = SessionLocal()
    try:
        assert crud.listEvt(db) == []
        crud.createLifeEvt(db, title="新数据", dueAt=None, src="test")
        assert crud.listEvt(db)[0]["title"] == "新数据"
    finally:
        db.close()

    assert db_path.exists()



def test_reset_database_removes_unknown_old_tables(app_env) -> None:
    from sqlalchemy import inspect, text

    init_db()
    db = SessionLocal()
    try:
        db.execute(text("CREATE TABLE oldTable (id INTEGER PRIMARY KEY)"))
        db.commit()
    finally:
        db.close()

    resetDatabase()

    db = SessionLocal()
    try:
        tables = set(inspect(db.get_bind()).get_table_names())
    finally:
        db.close()

    assert "oldTable" not in tables
    assert tables == {
        "evtBase",
        "lifeEvt",
        "ddlEvt",
        "courseTpl",
        "courseInst",
        "idea",
        "ideaToEvt",
        "devState",
        "notifyLog",
        "msgLog",
        "actLog",
    }
