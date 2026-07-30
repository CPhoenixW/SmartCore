"""Deterministic Feishu Plan-result prompts.

This module intentionally has no OpenClaw dependency.  A result is accepted
only when Feishu identifies it as a reply to the exact outbound card stored in
``planCompletionPrompt`` and the authenticated binding still owns that card.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.server.feishu.bot_service import runtime
from app.server.feishu.cards import build_plan_completion_card
from app.server.feishu.client import FeishuAPIError
from app.server.new_core.models import (
    ActLog,
    EvtBase,
    FeishuBind,
    FeishuBot,
    PlanCompletionPrompt,
    PlanEvt,
    nowIso,
)

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_DELIVERY_WINDOW = timedelta(minutes=5)
_CLAIM_LEASE = timedelta(minutes=2)
_MAX_RESPONSE_LENGTH = 4000


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=_DEFAULT_TZ) if parsed.tzinfo is None else parsed


def _expected_end(plan: PlanEvt) -> str:
    return (_aware(plan.stTime) + timedelta(minutes=int(plan.durationMin))).isoformat()


def _same_instant(left: str, right: str) -> bool:
    try:
        return _aware(left).astimezone(ZoneInfo("UTC")) == _aware(right).astimezone(ZoneInfo("UTC"))
    except ValueError:
        return False


def _active_primary_binding(db: Session, *, user_id: str) -> tuple[FeishuBind, FeishuBot] | None:
    row = db.execute(
        select(FeishuBind, FeishuBot)
        .join(FeishuBot, FeishuBot.botId == FeishuBind.botId)
        .where(
            FeishuBind.userId == user_id,
            FeishuBind.stat == "active",
            FeishuBind.isPrimary.is_(True),
            FeishuBot.enabled.is_(True),
        )
        .order_by(FeishuBind.updatedAt.desc(), FeishuBind.createdAt.desc())
    ).first()
    return row if row is not None else None


def _message_id(response: object) -> str | None:
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    value = data.get("message_id") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def dispatch_plan_completion_prompts(db: Session, *, now: datetime) -> dict[str, int]:
    """Send one Feishu-only result card in the five minutes after a Plan ends."""

    now = now.astimezone(_DEFAULT_TZ)
    sent = 0
    failed = 0
    candidates = db.execute(
        select(EvtBase, PlanEvt)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .where(EvtBase.evtType == "plan", EvtBase.stat != "cancelled")
    ).all()
    for base, plan in candidates:
        expected_end = _expected_end(plan)
        end = _aware(expected_end).astimezone(_DEFAULT_TZ)
        if now < end or now > end + _DELIVERY_WINDOW:
            continue
        existing = db.scalar(
            select(PlanCompletionPrompt).where(
                PlanCompletionPrompt.planEvtId == base.evtId,
                PlanCompletionPrompt.expectedEndAt == expected_end,
            )
        )
        if existing is not None:
            if existing.stat in {"sent", "answered", "expired"}:
                continue
            if existing.stat == "queued":
                last_attempt = _aware(existing.lastAttemptAt) if existing.lastAttemptAt else None
                if last_attempt and now - last_attempt.astimezone(_DEFAULT_TZ) < _CLAIM_LEASE:
                    continue

        binding_and_bot = _active_primary_binding(db, user_id=base.userId)
        claim_time = now.replace(microsecond=0).isoformat()
        lease_cutoff = (now - _CLAIM_LEASE).replace(microsecond=0).isoformat()
        if binding_and_bot is None:
            if existing is None:
                db.add(
                    PlanCompletionPrompt(
                        userId=base.userId,
                        planEvtId=base.evtId,
                        expectedEndAt=expected_end,
                        stat="failed",
                        attemptCount=1,
                        lastAttemptAt=claim_time,
                        failReason="no active primary Feishu binding",
                        createdAt=claim_time,
                        updatedAt=claim_time,
                    )
                )
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    continue
            else:
                changed = db.execute(
                    update(PlanCompletionPrompt)
                    .where(
                        PlanCompletionPrompt.promptId == existing.promptId,
                        or_(
                            PlanCompletionPrompt.stat == "failed",
                            and_(
                                PlanCompletionPrompt.stat == "queued",
                                or_(
                                    PlanCompletionPrompt.lastAttemptAt.is_(None),
                                    PlanCompletionPrompt.lastAttemptAt <= lease_cutoff,
                                ),
                            ),
                        ),
                    )
                    .values(
                        stat="failed",
                        attemptCount=PlanCompletionPrompt.attemptCount + 1,
                        lastAttemptAt=claim_time,
                        failReason="no active primary Feishu binding",
                        updatedAt=claim_time,
                    )
                )
                db.commit()
                if changed.rowcount != 1:
                    continue
            failed += 1
            continue

        binding, bot = binding_and_bot
        prompt_id: str
        if existing is None:
            prompt = PlanCompletionPrompt(
                userId=base.userId,
                planEvtId=base.evtId,
                expectedEndAt=expected_end,
                bindId=binding.bindId,
                botId=bot.botId,
                chatId=binding.chatId,
                stat="queued",
                attemptCount=1,
                lastAttemptAt=claim_time,
                createdAt=claim_time,
                updatedAt=claim_time,
            )
            db.add(prompt)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                continue
            prompt_id = prompt.promptId
        else:
            claimed = db.execute(
                update(PlanCompletionPrompt)
                .where(
                    PlanCompletionPrompt.promptId == existing.promptId,
                    or_(
                        PlanCompletionPrompt.stat == "failed",
                        and_(
                            PlanCompletionPrompt.stat == "queued",
                            or_(
                                PlanCompletionPrompt.lastAttemptAt.is_(None),
                                PlanCompletionPrompt.lastAttemptAt <= lease_cutoff,
                            ),
                        ),
                    ),
                )
                .values(
                    bindId=binding.bindId,
                    botId=bot.botId,
                    chatId=binding.chatId,
                    stat="queued",
                    attemptCount=PlanCompletionPrompt.attemptCount + 1,
                    lastAttemptAt=claim_time,
                    failReason=None,
                    updatedAt=claim_time,
                )
            )
            db.commit()
            if claimed.rowcount != 1:
                continue
            prompt_id = existing.promptId
        try:
            client = runtime(bot).client()
            response = client.send_interactive_card(
                binding.chatId,
                build_plan_completion_card(
                    prompt_id=prompt_id,
                    evt_id=base.evtId,
                    title=base.title,
                ),
                idempotency_key=f"plan-completion-{prompt_id}",
            )
            outbound_id = _message_id(response)
            if outbound_id is None:
                raise ValueError("Feishu response missing message_id")
        except (FeishuAPIError, ValueError) as exc:
            changed = db.execute(
                update(PlanCompletionPrompt)
                .where(
                    PlanCompletionPrompt.promptId == prompt_id,
                    PlanCompletionPrompt.stat == "queued",
                    PlanCompletionPrompt.lastAttemptAt == claim_time,
                )
                .values(stat="failed", failReason=str(exc)[:1000], updatedAt=nowIso())
            )
            db.commit()
            failed += int(changed.rowcount == 1)
            continue
        except Exception as exc:  # runtime/client errors must not break scheduling.
            changed = db.execute(
                update(PlanCompletionPrompt)
                .where(
                    PlanCompletionPrompt.promptId == prompt_id,
                    PlanCompletionPrompt.stat == "queued",
                    PlanCompletionPrompt.lastAttemptAt == claim_time,
                )
                .values(
                    stat="failed",
                    failReason=f"{type(exc).__name__}: {exc}"[:1000],
                    updatedAt=nowIso(),
                )
            )
            db.commit()
            failed += int(changed.rowcount == 1)
            continue

        changed = db.execute(
            update(PlanCompletionPrompt)
            .where(
                PlanCompletionPrompt.promptId == prompt_id,
                PlanCompletionPrompt.stat == "queued",
                PlanCompletionPrompt.lastAttemptAt == claim_time,
            )
            .values(
                outboundMessageId=outbound_id,
                stat="sent",
                failReason=None,
                sentAt=nowIso(),
                updatedAt=nowIso(),
            )
        )
        db.commit()
        sent += int(changed.rowcount == 1)
    return {"sent": sent, "failed": failed}


def _prompt_plan_is_current(
    db: Session, prompt: PlanCompletionPrompt
) -> tuple[EvtBase, PlanEvt] | None:
    row = db.execute(
        select(EvtBase, PlanEvt)
        .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
        .where(EvtBase.evtId == prompt.planEvtId)
        .execution_options(populate_existing=True)
    ).first()
    if row is None:
        return None
    base, plan = row
    if (
        base is None
        or plan is None
        or base.userId != prompt.userId
        or base.evtType != "plan"
        or base.stat == "cancelled"
    ):
        return None
    return (base, plan) if _same_instant(_expected_end(plan), prompt.expectedEndAt) else None


def _prompt_owned_by_binding(
    prompt: PlanCompletionPrompt,
    *,
    bot_id: str,
    binding: FeishuBind,
    chat_id: str,
) -> bool:
    return (
        prompt.userId == binding.userId
        and prompt.botId == bot_id
        and prompt.bindId == binding.bindId
        and prompt.chatId == chat_id
    )


def _append_result(
    db: Session,
    *,
    prompt: PlanCompletionPrompt,
    plan: PlanEvt,
    note: str,
    mark_done: bool,
) -> bool:
    values: dict[str, object] = {
        "desc": case(
            (
                or_(EvtBase.desc.is_(None), func.trim(EvtBase.desc) == ""),
                note,
            ),
            else_=EvtBase.desc + "\n\n" + note,
        ),
        "updatedAt": nowIso(),
    }
    if mark_done:
        values["stat"] = "done"
    changed = db.execute(
        update(EvtBase)
        .where(
            EvtBase.evtId == prompt.planEvtId,
            EvtBase.userId == prompt.userId,
            EvtBase.evtType == "plan",
            EvtBase.stat != "cancelled",
            exists(
                select(PlanEvt.evtId).where(
                    PlanEvt.evtId == prompt.planEvtId,
                    PlanEvt.stTime == plan.stTime,
                    PlanEvt.durationMin == plan.durationMin,
                )
            ),
        )
        .values(**values)
    )
    if changed.rowcount == 1:
        db.add(
            ActLog(
                userId=prompt.userId,
                actorKind="user",
                actorId=f"feishu:{prompt.bindId or 'unknown'}",
                action="complete" if mark_done else "update",
                targetKind="evt",
                targetId=prompt.planEvtId,
                result="ok",
            )
        )
    return changed.rowcount == 1


def accept_plan_completion_reply(
    db: Session,
    *,
    bot_id: str,
    binding: FeishuBind,
    chat_id: str,
    message_id: str | None,
    text: str | None,
    parent_id: str | None,
    root_id: str | None,
) -> bool:
    """Append a free-text result only when it is a verified card reply.

    ``True`` means the message belonged to a SmartCore completion-card thread,
    even when it is rejected (wrong owner, stale Plan or duplicate).  The
    caller must then keep it out of the normal OpenClaw forwarding flow.
    """

    reply_to = [value for value in (parent_id, root_id) if isinstance(value, str) and value]
    if not reply_to:
        return False
    prompt = db.scalar(
        select(PlanCompletionPrompt)
        .where(PlanCompletionPrompt.outboundMessageId.in_(reply_to))
        .order_by(PlanCompletionPrompt.createdAt.desc())
    )
    if prompt is None:
        return False
    if (
        prompt.stat != "sent"
        or not _prompt_owned_by_binding(prompt, bot_id=bot_id, binding=binding, chat_id=chat_id)
        or _prompt_plan_is_current(db, prompt) is None
        or not message_id
    ):
        return True
    clean_text = str(text or "").strip()
    if not clean_text:
        return True
    clean_text = clean_text[:_MAX_RESPONSE_LENGTH]

    claimed = db.execute(
        update(PlanCompletionPrompt)
        .where(
            PlanCompletionPrompt.promptId == prompt.promptId,
            PlanCompletionPrompt.stat == "sent",
            PlanCompletionPrompt.responseMessageId.is_(None),
        )
        .values(
            stat="answered",
            responseMessageId=message_id,
            responseText=clean_text,
            answeredAt=nowIso(),
            updatedAt=nowIso(),
        )
    )
    if claimed.rowcount != 1:
        db.rollback()
        return True
    current = _prompt_plan_is_current(db, prompt)
    if current is None:  # Defensive recheck after the atomic response claim.
        db.rollback()
        return True
    note = f"执行结果：{clean_text}"
    if not _append_result(db, prompt=prompt, plan=current[1], note=note, mark_done=False):
        db.rollback()
        return True
    db.commit()
    return True


def accept_plan_completion_action(
    db: Session,
    *,
    prompt_id: str,
    bot_id: str,
    binding: FeishuBind,
    chat_id: str,
    outbound_message_id: str | None,
    action_event_id: str | None,
) -> bool:
    """Claim the one-click completion action and mark the Plan done once."""

    prompt = db.get(PlanCompletionPrompt, prompt_id)
    if prompt is None or prompt.stat != "sent":
        return False
    if not _prompt_owned_by_binding(prompt, bot_id=bot_id, binding=binding, chat_id=chat_id):
        return False
    if not outbound_message_id or outbound_message_id != prompt.outboundMessageId:
        return False
    if _prompt_plan_is_current(db, prompt) is None:
        return False
    response_id = action_event_id or f"card:{prompt.promptId}"
    claimed = db.execute(
        update(PlanCompletionPrompt)
        .where(
            PlanCompletionPrompt.promptId == prompt.promptId,
            PlanCompletionPrompt.stat == "sent",
            PlanCompletionPrompt.responseMessageId.is_(None),
        )
        .values(
            stat="answered",
            responseMessageId=response_id,
            responseText="已完成",
            answeredAt=nowIso(),
            updatedAt=nowIso(),
        )
    )
    if claimed.rowcount != 1:
        db.rollback()
        return False
    current = _prompt_plan_is_current(db, prompt)
    if current is None:
        db.rollback()
        return False
    if not _append_result(
        db,
        prompt=prompt,
        plan=current[1],
        note="执行结果：已完成",
        mark_done=True,
    ):
        db.rollback()
        return False
    db.commit()
    return True
