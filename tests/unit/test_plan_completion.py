from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.server.feishu.cards import build_plan_completion_card
from app.server.feishu.client import FeishuClient
from app.server.new_core.event_relations import create_plan_event
from app.server.new_core.models import (
    ActLog,
    FeishuBind,
    FeishuBot,
    LifeIdentity,
    PlanCompletionPrompt,
)
from app.server.new_core.plan_completion import (
    accept_plan_completion_action,
    accept_plan_completion_reply,
    dispatch_plan_completion_prompts,
)
from tests.factories import create_user

pytestmark = pytest.mark.unit
TZ = ZoneInfo("Asia/Shanghai")


class _CardClient:
    def __init__(self) -> None:
        self.cards: list[tuple[str, dict]] = []
        self.idempotency_keys: list[str | None] = []

    def send_interactive_card(
        self, chat_id: str, card: dict, *, idempotency_key: str | None = None
    ) -> dict:
        self.cards.append((chat_id, card))
        self.idempotency_keys.append(idempotency_key)
        return {"code": 0, "data": {"message_id": "om_plan_prompt"}}


class _RetryCardClient(_CardClient):
    def send_interactive_card(
        self, chat_id: str, card: dict, *, idempotency_key: str | None = None
    ) -> dict:
        self.cards.append((chat_id, card))
        self.idempotency_keys.append(idempotency_key)
        if len(self.cards) == 1:
            raise RuntimeError("temporary Feishu failure")
        return {"code": 0, "data": {"message_id": "om_plan_retry"}}


def _binding(db_session, *, user_id: str = "owner", chat_id: str = "oc_owner"):
    create_user(db_session, user_id=user_id)
    identity = LifeIdentity(userId=user_id, provider="feishu", externalId=f"ou_{user_id}")
    bot = FeishuBot(
        userId=user_id,
        botName="test bot",
        appId=f"app_{user_id}",
        appSecretCipher="cipher",
        verificationTokenCipher="cipher",
        encryptKeyCipher="cipher",
        enabled=True,
    )
    db_session.add_all((identity, bot))
    db_session.flush()
    binding = FeishuBind(
        userId=user_id,
        botId=bot.botId,
        identityId=identity.identityId,
        chatId=chat_id,
        isPrimary=True,
    )
    db_session.add(binding)
    db_session.commit()
    return binding, bot


def _ended_plan(db_session, *, user_id: str = "owner", now: datetime):
    return create_plan_event(
        db_session,
        title="实现日报",
        stTime=(now - timedelta(minutes=30)).isoformat(),
        durationMin=30,
        userId=user_id,
    )


def test_completion_card_is_feishu_only_idempotent_and_bound(db_session, monkeypatch) -> None:
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)
    binding, _ = _binding(db_session)
    plan = _ended_plan(db_session, now=now)
    client = _CardClient()
    monkeypatch.setattr(
        "app.server.new_core.plan_completion.runtime",
        lambda _bot: SimpleNamespace(client=lambda: client),
    )

    first = dispatch_plan_completion_prompts(db_session, now=now)
    second = dispatch_plan_completion_prompts(db_session, now=now)

    assert first == {"sent": 1, "failed": 0}
    assert second == {"sent": 0, "failed": 0}
    assert client.cards[0][0] == binding.chatId
    action = client.cards[0][1]["elements"][-1]["actions"][0]
    assert action["value"]["kind"] == "planCompletionPrompt"
    assert action["value"]["evtId"] == plan["evtId"]
    prompt = db_session.query(PlanCompletionPrompt).one()
    assert prompt.stat == "sent"
    assert prompt.outboundMessageId == "om_plan_prompt"
    assert client.idempotency_keys == [f"plan-completion-{prompt.promptId}"]


def test_completion_prompt_records_no_binding_and_send_failure(db_session, monkeypatch) -> None:
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)
    create_user(db_session, user_id="owner")
    _binding(db_session, user_id="other")
    _ended_plan(db_session, now=now)

    result = dispatch_plan_completion_prompts(db_session, now=now)

    assert result == {"sent": 0, "failed": 1}
    prompt = db_session.query(PlanCompletionPrompt).one()
    assert prompt.stat == "failed"
    assert prompt.failReason == "no active primary Feishu binding"


def test_completion_prompt_retries_transient_send_failure(db_session, monkeypatch) -> None:
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)
    _binding(db_session)
    _ended_plan(db_session, now=now)
    client = _RetryCardClient()
    monkeypatch.setattr(
        "app.server.new_core.plan_completion.runtime",
        lambda _bot: SimpleNamespace(client=lambda: client),
    )

    assert dispatch_plan_completion_prompts(db_session, now=now) == {"sent": 0, "failed": 1}
    assert dispatch_plan_completion_prompts(
        db_session, now=now + timedelta(minutes=1)
    ) == {"sent": 1, "failed": 0}
    prompt = db_session.query(PlanCompletionPrompt).one()
    assert prompt.stat == "sent"
    assert prompt.attemptCount == 2
    assert prompt.outboundMessageId == "om_plan_retry"
    assert client.idempotency_keys == [
        f"plan-completion-{prompt.promptId}",
        f"plan-completion-{prompt.promptId}",
    ]


def test_completed_plan_can_still_receive_a_result_note(db_session, monkeypatch) -> None:
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)
    binding, bot = _binding(db_session)
    plan = _ended_plan(db_session, now=now)
    from app.server.new_core.models import EvtBase

    base = db_session.get(EvtBase, plan["evtId"])
    base.stat = "done"
    base.desc = "原有说明"
    db_session.commit()
    client = _CardClient()
    monkeypatch.setattr(
        "app.server.new_core.plan_completion.runtime",
        lambda _bot: SimpleNamespace(client=lambda: client),
    )

    assert dispatch_plan_completion_prompts(db_session, now=now) == {"sent": 1, "failed": 0}
    prompt = db_session.query(PlanCompletionPrompt).one()
    assert accept_plan_completion_reply(
        db_session,
        bot_id=bot.botId,
        binding=binding,
        chat_id=binding.chatId,
        message_id="om_done_result",
        text="交付并验证完成",
        parent_id=prompt.outboundMessageId,
        root_id=None,
    )
    db_session.refresh(base)
    assert base.stat == "done"
    assert base.desc == "原有说明\n\n执行结果：交付并验证完成"


def test_reply_requires_exact_bound_card_and_is_idempotent(db_session) -> None:
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)
    binding, bot = _binding(db_session)
    plan = _ended_plan(db_session, now=now)
    prompt = PlanCompletionPrompt(
        userId="owner",
        planEvtId=plan["evtId"],
        bindId=binding.bindId,
        botId=bot.botId,
        chatId=binding.chatId,
        expectedEndAt=now.isoformat(),
        outboundMessageId="om_prompt",
        stat="sent",
    )
    db_session.add(prompt)
    db_session.commit()

    assert not accept_plan_completion_reply(
        db_session, bot_id=bot.botId, binding=binding, chat_id=binding.chatId,
        message_id="om_plain", text="ordinary message", parent_id=None, root_id=None,
    )
    assert accept_plan_completion_reply(
        db_session, bot_id=bot.botId, binding=binding, chat_id=binding.chatId,
        message_id="om_result", text="完成接口和测试", parent_id="om_prompt", root_id=None,
    )
    assert accept_plan_completion_reply(
        db_session, bot_id=bot.botId, binding=binding, chat_id=binding.chatId,
        message_id="om_result", text="完成接口和测试", parent_id="om_prompt", root_id=None,
    )
    db_session.refresh(prompt)
    from app.server.new_core.models import EvtBase

    base = db_session.get(EvtBase, plan["evtId"])
    assert prompt.stat == "answered"
    assert base is not None and base.desc == "执行结果：完成接口和测试"
    audit = (
        db_session.query(ActLog)
        .filter(
            ActLog.targetId == plan["evtId"],
            ActLog.actorId == f"feishu:{binding.bindId}",
        )
        .one()
    )
    assert audit.actorKind == "user"
    assert audit.actorId == f"feishu:{binding.bindId}"
    assert audit.action == "update"


def test_reply_rejects_cross_chat_and_rescheduled_plan(db_session) -> None:
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)
    binding, bot = _binding(db_session)
    plan = _ended_plan(db_session, now=now)
    prompt = PlanCompletionPrompt(
        userId="owner", planEvtId=plan["evtId"], bindId=binding.bindId, botId=bot.botId,
        chatId=binding.chatId, expectedEndAt=now.isoformat(), outboundMessageId="om_prompt", stat="sent",
    )
    db_session.add(prompt)
    db_session.commit()
    assert accept_plan_completion_reply(
        db_session, bot_id=bot.botId, binding=binding, chat_id="oc_wrong",
        message_id="om_wrong", text="不应写入", parent_id="om_prompt", root_id=None,
    )
    db_session.refresh(prompt)
    assert prompt.stat == "sent"
    other_binding, other_bot = _binding(db_session, user_id="other", chat_id="oc_other")
    assert accept_plan_completion_reply(
        db_session, bot_id=other_bot.botId, binding=other_binding, chat_id=other_binding.chatId,
        message_id="om_other", text="不应跨用户写入", parent_id="om_prompt", root_id=None,
    )
    db_session.refresh(prompt)
    assert prompt.stat == "sent"
    from app.server.new_core.models import PlanEvt

    db_session.get(PlanEvt, plan["evtId"]).stTime = (now - timedelta(minutes=1)).isoformat()
    db_session.commit()
    assert accept_plan_completion_reply(
        db_session, bot_id=bot.botId, binding=binding, chat_id=binding.chatId,
        message_id="om_stale", text="不应写入", parent_id="om_prompt", root_id=None,
    )
    db_session.refresh(prompt)
    assert prompt.stat == "sent"


def test_completion_action_marks_done_once(db_session) -> None:
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)
    binding, bot = _binding(db_session)
    plan = _ended_plan(db_session, now=now)
    prompt = PlanCompletionPrompt(
        userId="owner", planEvtId=plan["evtId"], bindId=binding.bindId, botId=bot.botId,
        chatId=binding.chatId, expectedEndAt=now.isoformat(), outboundMessageId="om_prompt", stat="sent",
    )
    db_session.add(prompt)
    db_session.commit()
    assert accept_plan_completion_action(
        db_session, prompt_id=prompt.promptId, bot_id=bot.botId, binding=binding,
        chat_id=binding.chatId, outbound_message_id="om_prompt", action_event_id="evt_action",
    )
    assert not accept_plan_completion_action(
        db_session, prompt_id=prompt.promptId, bot_id=bot.botId, binding=binding,
        chat_id=binding.chatId, outbound_message_id="om_prompt", action_event_id="evt_duplicate",
    )
    from app.server.new_core.models import EvtBase

    base = db_session.get(EvtBase, plan["evtId"])
    assert base.stat == "done"
    assert base.desc == "执行结果：已完成"
    audit = (
        db_session.query(ActLog)
        .filter(
            ActLog.targetId == plan["evtId"],
            ActLog.actorId == f"feishu:{binding.bindId}",
        )
        .one()
    )
    assert audit.action == "complete"


def test_completion_action_requires_the_original_card_message_id(db_session) -> None:
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)
    binding, bot = _binding(db_session)
    plan = _ended_plan(db_session, now=now)
    prompt = PlanCompletionPrompt(
        userId="owner",
        planEvtId=plan["evtId"],
        bindId=binding.bindId,
        botId=bot.botId,
        chatId=binding.chatId,
        expectedEndAt=now.isoformat(),
        outboundMessageId="om_prompt",
        stat="sent",
    )
    db_session.add(prompt)
    db_session.commit()

    assert not accept_plan_completion_action(
        db_session,
        prompt_id=prompt.promptId,
        bot_id=bot.botId,
        binding=binding,
        chat_id=binding.chatId,
        outbound_message_id=None,
        action_event_id="evt_missing_message",
    )


def test_plan_completion_card_has_only_completion_action() -> None:
    card = build_plan_completion_card(prompt_id="prompt-1", evt_id="plan-1", title="写测试")
    action = card["elements"][-1]["actions"]
    assert card["header"]["template"] == "green"
    assert len(action) == 1
    assert action[0]["value"] == {
        "kind": "planCompletionPrompt", "promptId": "prompt-1", "evtId": "plan-1", "action": "complete",
    }


def test_feishu_client_forwards_message_idempotency_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(
                200,
                json={"code": 0, "tenant_access_token": "token", "expire": 7200},
            )
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_once"}})

    client = FeishuClient(
        "app",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    client.send_interactive_card(
        "oc_chat",
        {"schema": "2.0"},
        idempotency_key="plan-completion-prompt-1",
    )

    assert requests[-1].url.params["uuid"] == "plan-completion-prompt-1"
