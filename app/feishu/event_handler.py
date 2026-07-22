from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.agent.scope import issue_agent_scope
from app.config import Settings, get_settings
from app.db.session import SessionLocal
from app.feishu.bot_service import BotRuntime, enabledRuntimes
from app.feishu.commands import extract_file_key, extract_image_key, extract_message_text, extract_routing_context
from app.feishu.security import FeishuSecurityError, parse_event_payload, validate_request_headers
from app.new_core import crud
from app.new_core.models import EvtBase
from app.user_device.service import claimFeishuChatPair, feishuBinding

logger = logging.getLogger(__name__)
_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")

ALLOWED_EVENT_TYPES = {
    "im.message.receive_v1",
    "card.action.trigger",
}
_BIND_PATTERN = re.compile(r"^(?:绑定|bind)\s+([^\s]+)$", re.IGNORECASE)


class FeishuEventHandler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def handle(
        self,
        body: bytes,
        headers: dict[str, str],
        db: Session,
        *,
        now: float | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body_text = body.decode("utf-8")
        matched: BotRuntime | None = None
        payload: dict[str, Any] | None = None
        for candidate in enabledRuntimes(db, self.settings):
            try:
                if candidate.encryptKey:
                    validate_request_headers(
                        headers,
                        encrypt_key=candidate.encryptKey,
                        body=body_text,
                        now=now,
                        max_age_seconds=self.settings.feishu_replay_max_age_seconds,
                    )
                payload = parse_event_payload(
                    body_text,
                    encrypt_key=candidate.encryptKey,
                    verification_token=candidate.verificationToken,
                )
                matched = candidate
                break
            except (FeishuSecurityError, ValueError):
                continue
        if matched is None or payload is None:
            logger.warning("feishu security validation failed")
            return 403, {"code": 403, "msg": "forbidden"}

        if payload.get("type") == "url_verification":
            return 200, {"challenge": payload.get("challenge", "")}

        event_type = None
        if isinstance(payload.get("header"), dict):
            event_type = payload["header"].get("event_type")
        if event_type and event_type not in ALLOWED_EVENT_TYPES:
            return 200, {"code": 0, "msg": "ignored event type"}

        if event_type == "card.action.trigger":
            handled, response = self._handleSmartcoreReminderAction(payload, db, matched, now=now)
            if handled:
                return 200, response

        if event_type == "im.message.receive_v1":
            handled, response = self._handlePairCommand(payload, db, matched)
            if handled:
                return 200, response

        if not self.settings.openclaw_events_endpoint:
            return 200, {"code": 0, "msg": "openclaw not configured"}

        if event_type == "card.action.trigger":
            return self._forwardCardAction(payload, db, matched, now=now)
        return self._forwardMessage(payload, db, matched, now=now)

    def _reply(self, payload: dict[str, Any], text: str, bot: BotRuntime, *, action: str) -> None:
        chat, _ = extract_routing_context(payload)
        chat_id = chat.get("chat_id")
        if not chat_id or not bot.appId or not bot.appSecret:
            return
        try:
            bot.client().send_text(chat_id, text)
        except Exception:
            logger.exception("failed to send Feishu reply: action=%s", action)

    def _handlePairCommand(self, payload: dict[str, Any], db: Session, bot: BotRuntime) -> tuple[bool, dict[str, Any]]:
        _, text = extract_message_text(payload)
        if not text:
            return False, {}
        match = _BIND_PATTERN.fullmatch(text.strip())
        if not match:
            return False, {}
        _, user = extract_routing_context(payload)
        external_id = user.get("open_id") or user.get("user_id")
        if not external_id:
            self._reply(payload, "无法识别你的飞书账号，请在私聊中重试。", bot, action="pairing")
            return True, {"code": 0, "msg": "missing Feishu identity"}
        try:
            chat, _ = extract_routing_context(payload)
            claimFeishuChatPair(
                db,
                match.group(1),
                botId=bot.botId,
                externalId=external_id,
                chatId=str(chat.get("chat_id") or ""),
                chatType=str(chat.get("chat_type") or "p2p"),
            )
        except HTTPException as exc:
            self._reply(payload, f"绑定失败：{exc.detail}", bot, action="pairing")
            return True, {"code": 0, "msg": "pairing failed"}
        self._reply(payload, "已认领会话。请回到 SmartCore 工作台确认后启用该会话。", bot, action="pairing")
        return True, {"code": 0, "msg": "pairing claimed"}

    def _openclawHeaders(self) -> dict[str, str] | None:
        token = self.settings.openclaw_events_token
        if not token:
            return None
        return {"Authorization": f"Bearer {token}"}

    def _postOpenclaw(self, event: dict[str, Any]) -> None:
        response = httpx.post(
            self.settings.openclaw_events_endpoint,
            json=event,
            headers=self._openclawHeaders(),
            timeout=10.0,
        )
        if response.is_error:
            raise httpx.HTTPStatusError(
                f"OpenClaw event endpoint returned {response.status_code}",
                request=response.request,
                response=response,
            )

    @staticmethod
    def _timeContext(now: float | None) -> dict[str, Any]:
        now_dt = (
            datetime.fromtimestamp(now, _DEFAULT_TZ)
            if now is not None
            else datetime.now(_DEFAULT_TZ)
        ).replace(microsecond=0)
        offset = now_dt.strftime("%z")
        return {
            "timezone": "Asia/Shanghai",
            "now": now_dt.isoformat(),
            "date": now_dt.date().isoformat(),
            "weekday": now_dt.isoweekday(),
            "utcOffset": f"{offset[:3]}:{offset[3:]}",
            "policy": "Resolve relative dates against this context, then call SmartCore with an absolute ISO 8601 date-time including its UTC offset.",
        }

    def _normalizeMessage(
        self,
        payload: dict[str, Any],
        *,
        db: Session,
        bot: BotRuntime,
        message_id: str,
        text: str,
        now: float | None,
    ) -> dict[str, Any]:
        time_context = self._timeContext(now)
        chat, user = extract_routing_context(payload)
        normalized: dict[str, Any] = {
            "eventType": "message",
            "message_id": message_id,
            "text": text,
            "message": {
                "message_id": message_id,
                "text": text,
            },
            "request": time_context,
            "time_context": time_context,
            "timezone": time_context["timezone"],
            "now": time_context["now"],
            "feishu_payload": payload,
        }
        if chat_id := chat.get("chat_id"):
            normalized["chat_id"] = chat_id
        if chat:
            normalized["chat"] = chat
        if user:
            normalized["user"] = user
        binding = feishuBinding(db, botId=bot.botId, externalId=user.get("open_id") or user.get("user_id"), chatId=chat.get("chat_id"))
        if binding is not None:
            normalized["userId"] = binding.userId
            normalized["sourceBindId"] = binding.bindId
            normalized["agentScope"] = issue_agent_scope(
                userId=binding.userId,
                botId=bot.botId,
                chatId=str(chat.get("chat_id") or ""),
                # Image OCR and agent execution can exceed the text-only default.
                ttl_seconds=1800,
            )
        return normalized

    def _normalizeCardAction(
        self,
        payload: dict[str, Any],
        *,
        now: float | None,
    ) -> dict[str, Any]:
        time_context = self._timeContext(now)
        event_body = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        context = event_body.get("context") if isinstance(event_body.get("context"), dict) else {}
        chat: dict[str, str] = {}
        if open_chat_id := context.get("open_chat_id"):
            if isinstance(open_chat_id, str) and open_chat_id:
                chat["chat_id"] = open_chat_id
        operator = event_body.get("operator")
        user: dict[str, str] = {}
        if isinstance(operator, dict):
            operator_id = operator.get("operator_id")
            if isinstance(operator_id, dict):
                for key in ("open_id", "union_id", "user_id"):
                    value = operator_id.get(key)
                    if isinstance(value, str) and value:
                        user[key] = value
        normalized: dict[str, Any] = {
            "eventType": "card_action",
            "card_action": {
                "action": event_body.get("action"),
                "context": context,
            },
            "request": time_context,
            "time_context": time_context,
            "timezone": time_context["timezone"],
            "now": time_context["now"],
            "feishu_payload": payload,
        }
        if chat_id := chat.get("chat_id"):
            normalized["chat_id"] = chat_id
        if chat:
            normalized["chat"] = chat
        if user:
            normalized["user"] = user
        return normalized

    def _handleSmartcoreReminderAction(
        self,
        payload: dict[str, Any],
        db: Session,
        bot: BotRuntime,
        *,
        now: float | None,
    ) -> tuple[bool, dict[str, Any]]:
        event_body = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        action = event_body.get("action")
        if not isinstance(action, dict):
            return False, {}
        value = action.get("value")
        if not isinstance(value, dict) or value.get("kind") != "smartcoreReminder":
            return False, {}

        evt_id = value.get("evtId")
        action_name = value.get("action")
        if not isinstance(evt_id, str) or not evt_id:
            return True, {"toast": {"type": "error", "content": "缺少事件 ID"}}
        context = event_body.get("context") if isinstance(event_body.get("context"), dict) else {}
        operator = event_body.get("operator") if isinstance(event_body.get("operator"), dict) else {}
        operator_id = operator.get("operator_id") if isinstance(operator.get("operator_id"), dict) else {}
        external_id = operator_id.get("open_id") or operator_id.get("user_id")
        binding = feishuBinding(db, botId=bot.botId, externalId=external_id, chatId=context.get("open_chat_id"))
        event = db.get(EvtBase, evt_id)
        if binding is None or event is None or event.userId != binding.userId:
            return True, {"toast": {"type": "error", "content": "无权操作此提醒"}}
        if action_name == "reminderDone":
            mapped = "done"
        elif action_name == "reminderSnooze10":
            mapped = "snooze10"
        else:
            return True, {"toast": {"type": "error", "content": "未知操作"}}

        now_dt = (
            datetime.fromtimestamp(now, _DEFAULT_TZ)
            if now is not None
            else datetime.now(_DEFAULT_TZ)
        )
        try:
            crud.applyReminderAction(
                db,
                evtId=evt_id,
                action=mapped,
                now=now_dt.isoformat(),
                src="feishu",
            )
        except ValueError:
            return True, {"toast": {"type": "error", "content": "事件不存在或无法更新"}}
        return True, {"toast": {"type": "success", "content": "已更新"}}

    def _forwardMessage(
        self,
        payload: dict[str, Any],
        db: Session,
        bot: BotRuntime,
        *,
        now: float | None,
    ) -> tuple[int, dict[str, Any]]:
        message_id, text = extract_message_text(payload)
        chat, user = extract_routing_context(payload)
        binding = feishuBinding(db, botId=bot.botId, externalId=user.get("open_id") or user.get("user_id"), chatId=chat.get("chat_id"))
        if binding is None:
            self._reply(payload, "请先在 SmartCore 工作台生成配对码，并发送“绑定 配对码”。", bot, action="unbound")
            return 200, {"code": 0, "msg": "unbound chat"}
        image_message_id, image_key = extract_image_key(payload)
        file_message_id, file_key, file_name = extract_file_key(payload)
        if image_message_id:
            message_id = image_message_id
        if file_message_id:
            message_id = file_message_id
        if message_id and crud.msgLogExists(db, src="feishu", externalId=message_id):
            return 200, {"code": 0, "msg": "duplicate message ignored"}
        media_uploads: list[dict[str, Any]] = []
        if image_key and message_id:
            try:
                image, mime_type = bot.client().download_message_resource(message_id, image_key)
                if len(image) > self.settings.vision_max_image_bytes:
                    self._reply(payload, "图片过大，暂不支持解析。", bot, action="image_too_large")
                    return 200, {"code": 0, "msg": "image too large"}
                suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime_type, ".bin")
                destination = self.settings.idea_media_path / f"{uuid4().hex}{suffix}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(image)
                media_uploads.append(crud.createIdeaUpload(db, userId=binding.userId, fileName=f"feishu-image{suffix}", mimeType=mime_type, storagePath=str(destination), sizeBytes=len(image)))
                text = (text or "") + "\n[用户发送了图片附件，请使用 kimi-k3 提炼并保存为灵感。]"
            except Exception as exc:
                logger.warning("failed to analyze Feishu image: message_id=%s error=%s", message_id, type(exc).__name__)
                self._reply(payload, "图片解析失败，请稍后重试或直接发送文字。", bot, action="image_failed")
                return 200, {"code": 0, "msg": "image analysis failed"}
        if file_key and message_id:
            try:
                content, mime_type = bot.client().download_message_resource(
                    message_id, file_key, resource_type="file"
                )
                allowed = {
                    "application/pdf", "text/plain", "application/zip",
                    "application/x-zip-compressed",
                }
                if mime_type not in allowed or len(content) > self.settings.idea_media_max_bytes:
                    self._reply(payload, "仅支持 20 MB 以内的 PDF、TXT 或 ZIP 附件。", bot, action="file_too_large")
                    return 200, {"code": 0, "msg": "unsupported file"}
                safe_name = Path(file_name or "feishu-file").name[:300]
                suffix = Path(safe_name).suffix or ".bin"
                destination = self.settings.idea_media_path / f"{uuid4().hex}{suffix}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                media_uploads.append(
                    crud.createIdeaUpload(
                        db, userId=binding.userId, fileName=safe_name, mimeType=mime_type,
                        storagePath=str(destination), sizeBytes=len(content),
                    )
                )
                text = (text or "") + "\n[用户发送了文档附件，请使用 kimi-k3 提炼并保存为灵感。]"
            except Exception as exc:
                logger.warning("failed to download Feishu file: message_id=%s error=%s", message_id, type(exc).__name__)
                self._reply(payload, "文件读取失败，请稍后重试。", bot, action="file_failed")
                return 200, {"code": 0, "msg": "file download failed"}
        if not text:
            return 200, {"code": 0, "msg": "unsupported message type"}

        self._reply(payload, "已收到，正在处理…", bot, action="processing_ack")

        normalized = self._normalizeMessage(
            payload,
            db=db,
            bot=bot,
            message_id=message_id or "",
            text=text,
            now=now,
        )
        if media_uploads:
            agent_attachments = [
                {**upload, "agentPath": f"/attachments/{Path(str(upload.get('storagePath', ''))).name}"}
                for upload in media_uploads
            ]
            normalized["attachments"] = agent_attachments
            normalized["message"]["attachments"] = agent_attachments
        stat = "forwarded"
        try:
            self._postOpenclaw(normalized)
        except Exception:
            logger.exception(
                "failed to forward feishu message to openclaw: message_id=%s",
                message_id,
            )
            stat = "forward_failed"

        if message_id:
            crud.createMsgLog(
                db,
                src="feishu",
                externalId=message_id,
                rawText=text,
                intent="openclaw_forward",
                stat=stat,
                userId=binding.userId,
                sourceDeviceId=None,
            )
        return 200, {"code": 0, "msg": "ok"}

    def _forwardCardAction(
        self,
        payload: dict[str, Any],
        db: Session,
        bot: BotRuntime,
        *,
        now: float | None,
    ) -> tuple[int, dict[str, Any]]:
        normalized = self._normalizeCardAction(payload, now=now)
        try:
            self._postOpenclaw(normalized)
        except Exception:
            logger.exception("failed to forward feishu card action to openclaw")
            return 200, {"toast": {"type": "error", "content": "事件转发失败"}}
        return 200, {"code": 0, "msg": "ok"}


def create_feishu_router(handler: FeishuEventHandler | None = None) -> APIRouter:
    router = APIRouter()
    cached_handler: FeishuEventHandler | None = handler

    def _handler() -> FeishuEventHandler:
        nonlocal cached_handler
        if cached_handler is not None:
            return cached_handler
        cached_handler = FeishuEventHandler(get_settings())
        return cached_handler

    @router.post("/feishu/event")
    async def feishu_event(request: Request) -> Response:
        body = await request.body()
        event_handler = _handler()
        headers = dict(request.headers)

        def handle_in_worker() -> tuple[int, dict[str, Any]]:
            db = SessionLocal()
            try:
                return event_handler.handle(body, headers, db)
            finally:
                db.close()

        status_code, payload = await run_in_threadpool(handle_in_worker)
        return Response(
            content=json.dumps(payload, ensure_ascii=False),
            status_code=status_code,
            media_type="application/json",
        )

    return router
