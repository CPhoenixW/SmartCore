from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.server.config import Settings
from app.server.new_core.memory import (
    apply_operations,
    create_memory,
    delete_memory,
    extract_and_merge,
    handle_explicit_command,
    list_memories,
    parse_explicit_command,
    select_for_prompt,
    should_extract,
)

pytestmark = pytest.mark.unit


def test_create_memory_normalizes_and_dedupes(db_session) -> None:
    row, created = create_memory(
        db_session, user_id="alice", content="我喜欢早上处理难的任务", source="user_explicit"
    )
    assert created
    assert row.content == "用户喜欢早上处理难的任务"
    assert row.memType == "preference"
    assert row.source == "user_explicit"

    again, created_again = create_memory(
        db_session,
        user_id="alice",
        content="用户喜欢早上处理难的任务。",
        source="auto_extracted",
        confidence=0.6,
    )
    assert not created_again
    assert again.memoryId == row.memoryId
    assert again.source == "user_explicit"
    assert len(list_memories(db_session, user_id="alice")) == 1


def test_memories_are_owner_scoped_and_soft_deleted(db_session) -> None:
    alice, _ = create_memory(db_session, user_id="alice", content="用户在杭州读研究生")
    create_memory(db_session, user_id="bob", content="用户喜欢喝美式咖啡")

    assert [item["content"] for item in list_memories(db_session, user_id="bob")] == [
        "用户喜欢喝美式咖啡"
    ]
    with pytest.raises(ValueError):
        delete_memory(db_session, user_id="bob", memory_id=alice.memoryId)

    delete_memory(db_session, user_id="alice", memory_id=alice.memoryId)
    assert list_memories(db_session, user_id="alice") == []
    assert alice.deletedAt is not None


def test_secrets_are_never_stored(db_session) -> None:
    with pytest.raises(ValueError):
        create_memory(db_session, user_id="alice", content="我的邮箱密码是 hunter2")
    assert handle_explicit_command(db_session, user_id="alice", text="记住我的 api key 是 sk-abcdefghijk") is None
    assert list_memories(db_session, user_id="alice") == []


def test_expired_memories_are_not_injected(db_session) -> None:
    past = (datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(days=1)).isoformat()
    create_memory(db_session, user_id="alice", content="用户这周在出差", expires_at=past)
    create_memory(db_session, user_id="alice", content="用户喜欢简短的回答")
    lines = select_for_prompt(db_session, user_id="alice", query_text="你好")
    assert lines == ["[偏好] 用户喜欢简短的回答"]


def test_select_for_prompt_prefers_relevant_and_respects_caps(db_session) -> None:
    for index in range(30):
        create_memory(
            db_session,
            user_id="alice",
            content=f"用户的第{index}个无关事实是编号{index * 7919}",
            source="auto_extracted",
            confidence=0.6,
        )
    create_memory(db_session, user_id="alice", content="用户喜欢早上处理难的任务")
    lines = select_for_prompt(
        db_session, user_id="alice", query_text="明天早上我该先处理什么任务？", limit=5, max_chars=400
    )
    assert len(lines) <= 5
    assert sum(len(line) for line in lines) <= 400
    assert "[偏好] 用户喜欢早上处理难的任务" in lines
    db_session.commit()
    used = [item for item in list_memories(db_session, user_id="alice") if item["lastUsedAt"]]
    assert len(used) == len(lines)


def test_explicit_remember_and_forget(db_session) -> None:
    result = handle_explicit_command(db_session, user_id="alice", text="记住我喜欢早上处理难的任务")
    assert result is not None and result.action == "remember"
    assert "用户喜欢早上处理难的任务" in result.summary
    assert len(list_memories(db_session, user_id="alice")) == 1

    forgot = handle_explicit_command(db_session, user_id="alice", text="忘掉我喜欢早上处理难的任务")
    assert forgot is not None and forgot.action == "forget"
    assert len(forgot.memories) == 1
    assert list_memories(db_session, user_id="alice") == []


def test_reminder_like_requests_are_not_memory_commands() -> None:
    assert parse_explicit_command("记住明天下午3点开组会") is None
    assert parse_explicit_command("提醒我周五交作业") is None
    assert parse_explicit_command("帮我记住：我对花生过敏") == ("remember", "我对花生过敏")
    assert not should_extract("谢谢")
    assert not should_extract("记住我是左撇子")
    assert should_extract("我现在在浙大读计算机研究生")


def test_apply_operations_add_update_delete(db_session) -> None:
    existing, _ = create_memory(
        db_session, user_id="alice", content="用户在读研一", source="auto_extracted", confidence=0.7
    )
    stale, _ = create_memory(
        db_session, user_id="alice", content="用户每天晚上跑步", source="auto_extracted", confidence=0.7
    )
    counts = apply_operations(
        db_session,
        user_id="alice",
        operations=[
            {"op": "ADD", "type": "goal", "content": "用户想在年底前发一篇论文", "confidence": 0.9},
            {"op": "ADD", "type": "fact", "content": "用户可能喜欢猫", "confidence": 0.2},
            {"op": "UPDATE", "id": existing.memoryId, "type": "profile", "content": "用户在读研二", "confidence": 0.9},
            {"op": "DELETE", "id": stale.memoryId, "confidence": 0.9},
            {"op": "DELETE", "id": "someone-else", "confidence": 0.9},
            {"op": "ADD", "content": "用户的密码是 123456", "confidence": 0.9},
        ],
        max_active=200,
    )
    assert counts == {"added": 1, "updated": 1, "deleted": 1, "skipped": 3}
    contents = sorted(item["content"] for item in list_memories(db_session, user_id="alice"))
    assert contents == ["用户在读研二", "用户想在年底前发一篇论文"]


def test_active_memory_cap_evicts_automatic_first(db_session) -> None:
    create_memory(db_session, user_id="alice", content="用户是左撇子", source="user_explicit", max_active=2)
    create_memory(db_session, user_id="alice", content="用户常用 Mac 电脑", source="auto_extracted", confidence=0.5, max_active=2)
    create_memory(db_session, user_id="alice", content="用户养了一只柯基", source="auto_extracted", confidence=0.9, max_active=2)
    contents = sorted(item["content"] for item in list_memories(db_session, user_id="alice"))
    assert contents == ["用户养了一只柯基", "用户是左撇子"]


def test_extract_and_merge_uses_llm_and_tolerates_bad_output(db_session) -> None:
    settings = Settings(memory_enabled=True, llm_api_key="test")
    captured: dict[str, object] = {}

    def fake_llm(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return '```json\n{"operations":[{"op":"ADD","type":"profile","content":"用户在浙大读计算机研究生","confidence":0.9}]}\n```'

    result = extract_and_merge(
        db_session,
        user_id="alice",
        user_text="我现在在浙大读计算机研究生，帮我看看这周的课",
        assistant_text="好的，这周你有三节课。",
        settings=settings,
        llm=fake_llm,
    )
    assert result == {"added": 1, "updated": 0, "deleted": 0, "skipped": 0}
    assert captured["kwargs"]["response_format"] == {"type": "json_object"}

    bad = extract_and_merge(
        db_session,
        user_id="alice",
        user_text="我最近在准备考雅思",
        assistant_text="加油",
        settings=settings,
        llm=lambda *_args, **_kwargs: "not json",
    )
    assert bad == {"added": 0, "updated": 0, "deleted": 0, "skipped": 0}

    disabled = extract_and_merge(
        db_session,
        user_id="alice",
        user_text="我最近在准备考雅思",
        assistant_text="加油",
        settings=Settings(memory_enabled=False),
        llm=fake_llm,
    )
    assert disabled is None
