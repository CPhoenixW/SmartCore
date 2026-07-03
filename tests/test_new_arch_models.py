from sqlalchemy import inspect

from app.db.session import SessionLocal, init_db
from app.new_core import crud


def test_new_arch_tables_are_the_only_business_tables(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        tables = set(inspect(db.get_bind()).get_table_names())
    finally:
        db.close()

    assert {
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
    }.issubset(tables)
    assert "assignments" not in tables
    assert "life_events" not in tables
    assert "pending_operations" not in tables


def test_life_and_ddl_events_create_act_logs(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        life = crud.createLifeEvt(
            db,
            title="整理项目架构",
            dueAt="2026-07-03T20:00:00+08:00",
            src="test",
        )
        ddl = crud.createDdlEvt(
            db,
            title="提交报告",
            ddlAt="2026-07-04T23:00:00+08:00",
            hardDdl=True,
            src="test",
        )
        logs = crud.listActLog(db)
    finally:
        db.close()

    assert life["evtType"] == "life"
    assert life["stat"] == "todo"
    assert ddl["evtType"] == "ddl"
    assert ddl["hardDdl"] is True
    assert [item["actType"] for item in logs] == ["create", "create"]


def test_idea_can_convert_to_event(app_env) -> None:
    init_db()
    db = SessionLocal()
    try:
        idea = crud.createIdea(db, content="把副屏做成低干扰模式", srcType="text")
        event = crud.ideaToLifeEvt(
            db,
            ideaId=idea["ideaId"],
            title="设计副屏低干扰模式",
            dueAt=None,
            src="test",
        )
        ideas = crud.listIdeas(db)
    finally:
        db.close()

    assert event["evtType"] == "life"
    assert ideas[0]["handled"] is True
