from pathlib import Path


def test_refactor_docs_are_the_source_of_truth() -> None:
    root = Path("doc/refactor")

    assert (root / "README.md").exists()
    assert (root / "target-arch.md").exists()
    assert (root / "build-plan.md").exists()
    assert (root / "acceptance.md").exists()

    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "不做旧表兼容" in readme
    assert "不保留旧 OpenClaw skill" in readme
    assert "不保留旧确认卡片体验" in readme
    assert "服务器是主要运行和测试环境" in readme


def test_refactor_docs_use_compact_lower_camel_names() -> None:
    text = Path("doc/refactor/target-arch.md").read_text(encoding="utf-8")

    for name in [
        "evtBase",
        "lifeEvt",
        "ddlEvt",
        "courseTpl",
        "courseInst",
        "ideaToEvt",
        "devState",
        "notifyLog",
        "msgLog",
        "actLog",
    ]:
        assert name in text

    assert "schedule_events" not in text
    assert "course_templates" not in text
