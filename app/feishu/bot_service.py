from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import auth_secret
from app.config import Settings
from app.feishu.client import FeishuClient
from app.new_core.models import FeishuBot, LifeDevice, nowIso


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(auth_secret() + b":feishu-bot-v1").digest())
    return Fernet(key)


def seal(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def open_sealed(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("stored Feishu credential cannot be decrypted") from exc


@dataclass(frozen=True)
class BotRuntime:
    botId: str | None
    userId: str
    botName: str
    appId: str
    appSecret: str
    verificationToken: str
    encryptKey: str
    chatId: str

    def client(self) -> FeishuClient:
        return FeishuClient(self.appId, self.appSecret)


def runtime(bot: FeishuBot) -> BotRuntime:
    return BotRuntime(
        botId=bot.botId,
        userId=bot.userId,
        botName=bot.botName,
        appId=bot.appId,
        appSecret=open_sealed(bot.appSecretCipher),
        verificationToken=open_sealed(bot.verificationTokenCipher),
        encryptKey=open_sealed(bot.encryptKeyCipher),
        chatId=open_sealed(bot.defaultChatCipher),
    )


def legacyRuntime(settings: Settings) -> BotRuntime | None:
    if not settings.feishu_app_id or not settings.feishu_app_secret or not settings.feishu_verification_token:
        return None
    return BotRuntime(
        botId=None,
        userId="default",
        botName="环境默认机器人",
        appId=settings.feishu_app_id,
        appSecret=settings.feishu_app_secret,
        verificationToken=settings.feishu_verification_token,
        encryptKey=settings.feishu_encrypt_key,
        chatId=settings.feishu_default_chat_id,
    )


def enabledRuntimes(db: Session, settings: Settings) -> list[BotRuntime]:
    rows = db.scalars(select(FeishuBot).where(FeishuBot.enabled.is_(True)).order_by(FeishuBot.createdAt)).all()
    values = [runtime(row) for row in rows]
    return values or ([legacyRuntime(settings)] if legacyRuntime(settings) is not None else [])


def botDict(bot: FeishuBot) -> dict:
    return {
        "botId": bot.botId,
        "userId": bot.userId,
        "deviceId": bot.deviceId,
        "botName": bot.botName,
        "appIdHint": f"…{bot.appId[-6:]}" if len(bot.appId) > 6 else "configured",
        "enabled": bot.enabled,
        "isDefault": bot.isDefault,
        "hasRecipient": bool(bot.defaultChatCipher),
        "lastTestAt": bot.lastTestAt,
        "lastTestStat": bot.lastTestStat,
        "lastTestMessage": bot.lastTestMessage,
        "createdAt": bot.createdAt,
        "updatedAt": bot.updatedAt,
    }


def setDefaultChat(bot: FeishuBot, chatId: str) -> None:
    if chatId:
        bot.defaultChatCipher = seal(chatId)
        bot.updatedAt = nowIso()


def seedLegacyBot(db: Session, settings: Settings) -> None:
    if db.scalar(select(FeishuBot.botId).limit(1)) is not None:
        return
    legacy = legacyRuntime(settings)
    if legacy is None:
        return
    existing_device = db.scalar(
        select(LifeDevice).where(LifeDevice.userId == "default", LifeDevice.deviceKind == "feishuBot").order_by(LifeDevice.createdAt)
    )
    db.add(
        FeishuBot(
            userId="default",
            deviceId=existing_device.deviceId if existing_device is not None else None,
            botName=legacy.botName,
            appId=legacy.appId,
            appSecretCipher=seal(legacy.appSecret),
            verificationTokenCipher=seal(legacy.verificationToken),
            encryptKeyCipher=seal(legacy.encryptKey),
            defaultChatCipher=seal(legacy.chatId) if legacy.chatId else None,
            enabled=True,
            isDefault=True,
        )
    )
    db.commit()
