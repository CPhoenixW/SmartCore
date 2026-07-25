from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.server.db.session import Base

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def newId() -> str:
    return uuid.uuid4().hex


def nowIso() -> str:
    return datetime.now(_DEFAULT_TZ).isoformat()


class AppUser(Base):
    __tablename__ = "appUser"

    userId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    loginName: Mapped[str | None] = mapped_column(String(100), unique=True)
    passwd: Mapped[str | None] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    stat: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    sessionVersion: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lastLoginAt: Mapped[str | None] = mapped_column(String(64))
    displayName: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="zh", nullable=False)
    avatarUrl: Mapped[str | None] = mapped_column(String(500))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class EvtBase(Base):
    __tablename__ = "evtBase"

    evtId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(
        String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    desc: Mapped[str | None] = mapped_column(Text)
    evtType: Mapped[str] = mapped_column(String(20), nullable=False)
    prio: Mapped[str] = mapped_column(String(10), default="mid", nullable=False)
    stat: Mapped[str] = mapped_column(String(20), default="todo", nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class DailySummary(Base):
    __tablename__ = "dailySummary"
    __table_args__ = (
        UniqueConstraint("userId", "reportDate", name="uq_daily_summary_user_date"),
    )

    summaryId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(
        String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False
    )
    reportDate: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    stat: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    errorMessage: Mapped[str | None] = mapped_column(Text)
    generatedAt: Mapped[str | None] = mapped_column(String(64))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class WeatherForecast(Base):
    __tablename__ = "weatherForecast"

    locationKey: Mapped[str] = mapped_column(String(80), primary_key=True)
    locationName: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    forecast: Mapped[dict | None] = mapped_column(JSON)
    fetchedAt: Mapped[str | None] = mapped_column(String(64))
    lastAttemptAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    errorMessage: Mapped[str | None] = mapped_column(Text)


class PlanEvt(Base):
    __tablename__ = "planEvt"

    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), primary_key=True
    )
    stTime: Mapped[str] = mapped_column(String(64), nullable=False)
    durationMin: Mapped[int] = mapped_column(Integer, nullable=False)


class DdlEvt(Base):
    __tablename__ = "ddlEvt"

    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), primary_key=True
    )
    endTime: Mapped[str] = mapped_column(String(64), nullable=False)
    hardDdl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DdlPlan(Base):
    __tablename__ = "ddlPlan"

    ddlEvtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("ddlEvt.evtId", ondelete="CASCADE"), primary_key=True
    )
    planEvtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("planEvt.evtId", ondelete="CASCADE"), primary_key=True
    )
    planRole: Mapped[str] = mapped_column(String(30), nullable=False)
    sortOrder: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CourseEvt(Base):
    __tablename__ = "courseEvt"

    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), primary_key=True
    )
    courseName: Mapped[str] = mapped_column(String(200), nullable=False)
    teacher: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(200))
    stTime: Mapped[str] = mapped_column(String(8), nullable=False)
    endTime: Mapped[str] = mapped_column(String(8), nullable=False)
    stDate: Mapped[str] = mapped_column(String(16), nullable=False)
    endDate: Mapped[str] = mapped_column(String(16), nullable=False)
    weekDay: Mapped[int] = mapped_column(Integer, nullable=False)
    startWeek: Mapped[int | None] = mapped_column(Integer)
    endWeek: Mapped[int | None] = mapped_column(Integer)
    weekMode: Mapped[str] = mapped_column(String(10), default="all", nullable=False)


class CoursePlan(Base):
    __tablename__ = "coursePlan"
    __table_args__ = (
        UniqueConstraint("courseEvtId", "occurrenceDate", name="uq_course_plan_occurrence"),
        UniqueConstraint("planEvtId", name="uq_course_plan_plan"),
    )

    courseEvtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("courseEvt.evtId", ondelete="CASCADE"), primary_key=True
    )
    planEvtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("planEvt.evtId", ondelete="CASCADE"), primary_key=True
    )
    occurrenceDate: Mapped[str] = mapped_column(String(16), nullable=False)
    sequenceNo: Mapped[int] = mapped_column(Integer, nullable=False)


class RemindEvt(Base):
    __tablename__ = "remindEvt"
    __table_args__ = (
        UniqueConstraint("planEvtId", "remindKind", name="uq_plan_remind_kind"),
        CheckConstraint("planEvtId IS NULL OR ddlEvtId IS NULL", name="ck_remind_evt_single_owner"),
    )

    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), primary_key=True
    )
    planEvtId: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("planEvt.evtId", ondelete="CASCADE"), nullable=True
    )
    ddlEvtId: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("ddlEvt.evtId", ondelete="CASCADE"), nullable=True
    )
    remindKind: Mapped[str] = mapped_column(String(30), nullable=False)
    triggerTime: Mapped[str] = mapped_column(String(64), nullable=False)
    offsetMin: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    firedAt: Mapped[str | None] = mapped_column(String(64))


class Idea(Base):
    __tablename__ = "idea"

    ideaId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(
        String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    srcType: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    handled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class IdeaAttachment(Base):
    __tablename__ = "ideaAttachment"

    attachmentId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    ideaId: Mapped[str] = mapped_column(
        String(32), ForeignKey("idea.ideaId", ondelete="CASCADE"), nullable=False
    )
    fileName: Mapped[str] = mapped_column(String(300), nullable=False)
    mimeType: Mapped[str] = mapped_column(String(120), nullable=False)
    storagePath: Mapped[str] = mapped_column(String(700), nullable=False)
    sizeBytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class IdeaUpload(Base):
    __tablename__ = "ideaUpload"

    uploadId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    fileName: Mapped[str] = mapped_column(String(300), nullable=False)
    mimeType: Mapped[str] = mapped_column(String(120), nullable=False)
    storagePath: Mapped[str] = mapped_column(String(700), nullable=False)
    sizeBytes: Mapped[int] = mapped_column(Integer, nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class IdeaMediaJob(Base):
    __tablename__ = "ideaMediaJob"

    jobId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(
        String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False
    )
    ideaId: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("idea.ideaId", ondelete="CASCADE")
    )
    uploadId: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    stat: Mapped[str] = mapped_column(String(30), default="queued", nullable=False)
    contextText: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ocrText: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    ocrEvidence: Mapped[str | None] = mapped_column(Text)
    errorMessage: Mapped[str | None] = mapped_column(Text)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    expiresAt: Mapped[str] = mapped_column(String(64), nullable=False)


class Device(Base):
    __tablename__ = "device"

    deviceId: Mapped[str] = mapped_column(String(50), primary_key=True)
    userId: Mapped[str] = mapped_column(
        String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False
    )
    deviceName: Mapped[str] = mapped_column(String(100), nullable=False)
    deviceKind: Mapped[str] = mapped_column(String(30), nullable=False)
    isActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    registeredAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class DeviceStateLog(Base):
    __tablename__ = "deviceStateLog"

    stateLogId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    deviceId: Mapped[str] = mapped_column(
        String(50), ForeignKey("device.deviceId", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    seenAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON)


class DevicePhotoRequest(Base):
    __tablename__ = "devicePhotoRequest"

    requestId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    deviceId: Mapped[str] = mapped_column(
        String(50), ForeignKey("device.deviceId", ondelete="CASCADE"), nullable=False
    )
    stat: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    requestedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    expiresAt: Mapped[str] = mapped_column(String(64), nullable=False)
    dispatchedAt: Mapped[str | None] = mapped_column(String(64))
    capturedAt: Mapped[str | None] = mapped_column(String(64))
    completedAt: Mapped[str | None] = mapped_column(String(64))
    imagePath: Mapped[str | None] = mapped_column(String(500))
    mimeType: Mapped[str | None] = mapped_column(String(100))
    imageSize: Mapped[int | None] = mapped_column(Integer)
    recognition: Mapped[dict | None] = mapped_column(JSON)
    errorMessage: Mapped[str | None] = mapped_column(Text)


class ActLog(Base):
    __tablename__ = "actLog"

    actId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(
        String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False
    )
    actorKind: Mapped[str] = mapped_column(String(20), nullable=False)
    actorId: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    targetKind: Mapped[str] = mapped_column(String(30), nullable=False)
    targetId: Mapped[str] = mapped_column(String(32), nullable=False)
    sourceDeviceId: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("device.deviceId", ondelete="SET NULL")
    )
    result: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)
    errorMessage: Mapped[str | None] = mapped_column(Text)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class NotifyLog(Base):
    __tablename__ = "notifyLog"

    notifyId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(
        String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False
    )
    evtId: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    receiver: Mapped[str | None] = mapped_column(String(100))
    sourceDeviceId: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("device.deviceId", ondelete="SET NULL")
    )
    routeReason: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scheduledAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    sentAt: Mapped[str | None] = mapped_column(String(64))
    stat: Mapped[str] = mapped_column(String(20), nullable=False)
    failReason: Mapped[str | None] = mapped_column(Text)
    dedupKey: Mapped[str | None] = mapped_column(String(200), unique=True)


class MsgLog(Base):
    __tablename__ = "msgLog"

    msgId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(
        String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    externalId: Mapped[str | None] = mapped_column(String(200))
    sourceDeviceId: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("device.deviceId", ondelete="SET NULL")
    )
    rawText: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(100))
    stat: Mapped[str | None] = mapped_column(String(50))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class UserSession(Base):
    __tablename__ = "userSession"

    sessionId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    actorUserId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    activeUserId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    expiresAt: Mapped[str] = mapped_column(String(64), nullable=False)
    revokedAt: Mapped[str | None] = mapped_column(String(64))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class LifeDevice(Base):
    __tablename__ = "lifeDevice"

    deviceId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    deviceName: Mapped[str] = mapped_column(String(100), nullable=False)
    deviceKind: Mapped[str] = mapped_column(String(30), nullable=False)
    stat: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    lastSeenAt: Mapped[str | None] = mapped_column(String(64))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class DeviceKey(Base):
    __tablename__ = "deviceKey"

    keyId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    deviceId: Mapped[str] = mapped_column(String(32), ForeignKey("lifeDevice.deviceId", ondelete="CASCADE"), nullable=False)
    tokenHash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    lastUsedAt: Mapped[str | None] = mapped_column(String(64))
    revokedAt: Mapped[str | None] = mapped_column(String(64))


class DevicePair(Base):
    __tablename__ = "devicePair"

    pairId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    deviceId: Mapped[str | None] = mapped_column(String(32), ForeignKey("lifeDevice.deviceId", ondelete="SET NULL"))
    botId: Mapped[str | None] = mapped_column(String(32), ForeignKey("feishuBot.botId", ondelete="SET NULL"))
    deviceName: Mapped[str] = mapped_column(String(100), nullable=False)
    deviceKind: Mapped[str] = mapped_column(String(30), nullable=False)
    claimCode: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    stat: Mapped[str] = mapped_column(String(20), default="created", nullable=False)
    expiresAt: Mapped[str] = mapped_column(String(64), nullable=False)
    claimedAt: Mapped[str | None] = mapped_column(String(64))
    confirmedAt: Mapped[str | None] = mapped_column(String(64))
    activatedAt: Mapped[str | None] = mapped_column(String(64))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class FeishuBot(Base):
    __tablename__ = "feishuBot"

    botId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    deviceId: Mapped[str | None] = mapped_column(String(32), ForeignKey("lifeDevice.deviceId", ondelete="SET NULL"))
    botName: Mapped[str] = mapped_column(String(100), nullable=False)
    appId: Mapped[str] = mapped_column(String(200), nullable=False)
    appSecretCipher: Mapped[str] = mapped_column(Text, nullable=False)
    verificationTokenCipher: Mapped[str] = mapped_column(Text, nullable=False)
    encryptKeyCipher: Mapped[str] = mapped_column(Text, nullable=False)
    defaultChatCipher: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    isDefault: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lastTestAt: Mapped[str | None] = mapped_column(String(64))
    lastTestStat: Mapped[str | None] = mapped_column(String(20))
    lastTestMessage: Mapped[str | None] = mapped_column(String(300))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class FeishuBind(Base):
    __tablename__ = "feishuBind"
    __table_args__ = (UniqueConstraint("botId", "identityId", "chatId", name="uq_feishu_bind_endpoint"),)

    bindId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    botId: Mapped[str] = mapped_column(String(32), ForeignKey("feishuBot.botId", ondelete="CASCADE"), nullable=False)
    identityId: Mapped[str] = mapped_column(String(32), ForeignKey("lifeIdentity.identityId", ondelete="CASCADE"), nullable=False)
    chatId: Mapped[str] = mapped_column(String(300), nullable=False)
    chatType: Mapped[str] = mapped_column(String(20), default="p2p", nullable=False)
    stat: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    isPrimary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    lastSeenAt: Mapped[str | None] = mapped_column(String(64))


class FeishuChatPair(Base):
    __tablename__ = "feishuChatPair"

    pairId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    botId: Mapped[str] = mapped_column(String(32), ForeignKey("feishuBot.botId", ondelete="CASCADE"), nullable=False)
    claimCode: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    stat: Mapped[str] = mapped_column(String(20), default="created", nullable=False)
    identityId: Mapped[str | None] = mapped_column(String(32), ForeignKey("lifeIdentity.identityId", ondelete="SET NULL"))
    chatId: Mapped[str | None] = mapped_column(String(300))
    chatType: Mapped[str | None] = mapped_column(String(20))
    expiresAt: Mapped[str] = mapped_column(String(64), nullable=False)
    claimedAt: Mapped[str | None] = mapped_column(String(64))
    confirmedAt: Mapped[str | None] = mapped_column(String(64))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class LifeIdentity(Base):
    __tablename__ = "lifeIdentity"
    __table_args__ = (UniqueConstraint("provider", "externalId", name="uq_life_identity_provider_external"),)

    identityId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    deviceId: Mapped[str | None] = mapped_column(String(32), ForeignKey("lifeDevice.deviceId", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    externalId: Mapped[str] = mapped_column(String(200), nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class DeviceDispatch(Base):
    __tablename__ = "deviceDispatch"

    dispatchId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    deviceId: Mapped[str] = mapped_column(String(32), ForeignKey("lifeDevice.deviceId", ondelete="CASCADE"), nullable=False)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    stat: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    deliveredAt: Mapped[str | None] = mapped_column(String(64))
    acknowledgedAt: Mapped[str | None] = mapped_column(String(64))


class DeviceReceipt(Base):
    __tablename__ = "deviceReceipt"
    __table_args__ = (UniqueConstraint("dispatchId", name="uq_device_receipt_dispatch"),)

    receiptId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    dispatchId: Mapped[str] = mapped_column(String(32), ForeignKey("deviceDispatch.dispatchId", ondelete="CASCADE"), nullable=False)
    deviceId: Mapped[str] = mapped_column(String(32), ForeignKey("lifeDevice.deviceId", ondelete="CASCADE"), nullable=False)
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class ComputerActivityContext(Base):
    __tablename__ = "computerActivityContext"
    __table_args__ = (
        UniqueConstraint("userId", "fingerprint", name="uq_computer_context_user_fingerprint"),
    )

    contextId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    bundleId: Mapped[str] = mapped_column(String(300), nullable=False)
    appName: Mapped[str] = mapped_column(String(200), nullable=False)
    windowTitle: Mapped[str | None] = mapped_column(String(300))
    contextKind: Mapped[str | None] = mapped_column(String(20))
    domain: Mapped[str | None] = mapped_column(String(253))
    workspace: Mapped[str | None] = mapped_column(String(300))
    documentName: Mapped[str | None] = mapped_column(String(300))
    titleRedacted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    firstSeenAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    lastSeenAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class ComputerActivityBucket(Base):
    __tablename__ = "computerActivityBucket"
    __table_args__ = (
        UniqueConstraint("deviceId", "bucketStart", name="uq_computer_bucket_device_start"),
    )

    bucketId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    deviceId: Mapped[str] = mapped_column(String(32), nullable=False)
    sessionId: Mapped[str | None] = mapped_column(String(64))
    bucketStart: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    localDate: Mapped[str] = mapped_column(String(10), nullable=False)
    coveredSeconds: Mapped[int] = mapped_column(Integer, nullable=False)
    switchCount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    schemaVersion: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    receivedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class ComputerActivitySlice(Base):
    __tablename__ = "computerActivitySlice"

    sliceId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    bucketId: Mapped[str] = mapped_column(String(32), ForeignKey("computerActivityBucket.bucketId", ondelete="CASCADE"), nullable=False)
    contextId: Mapped[str | None] = mapped_column(String(32), ForeignKey("computerActivityContext.contextId", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    seconds: Mapped[int] = mapped_column(Integer, nullable=False)


class ComputerMonitorStatus(Base):
    __tablename__ = "computerMonitorStatus"

    deviceId: Mapped[str] = mapped_column(String(32), ForeignKey("lifeDevice.deviceId", ondelete="CASCADE"), primary_key=True)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    currentState: Mapped[str] = mapped_column(String(20), default="offline", nullable=False)
    currentAppName: Mapped[str | None] = mapped_column(String(200))
    currentWindowTitle: Mapped[str | None] = mapped_column(String(300))
    stateSince: Mapped[str | None] = mapped_column(String(64))
    observedAt: Mapped[str | None] = mapped_column(String(64))
    appVersion: Mapped[str | None] = mapped_column(String(50))
    osVersion: Mapped[str | None] = mapped_column(String(100))
    accessibilityGranted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    queueDepth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lastHeartbeatAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class ComputerDailyUsage(Base):
    __tablename__ = "computerDailyUsage"
    __table_args__ = (
        UniqueConstraint("deviceId", "usageDate", name="uq_computer_daily_device_date"),
    )

    dailyUsageId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    userId: Mapped[str] = mapped_column(String(32), ForeignKey("appUser.userId", ondelete="CASCADE"), nullable=False)
    deviceId: Mapped[str] = mapped_column(String(32), nullable=False)
    usageDate: Mapped[str] = mapped_column(String(10), nullable=False)
    activeSeconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idleSeconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lockedSeconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sleepingSeconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pausedSeconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    switchCount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class ComputerDailyAppUsage(Base):
    __tablename__ = "computerDailyAppUsage"
    __table_args__ = (
        UniqueConstraint("dailyUsageId", "bundleId", name="uq_computer_daily_app_bundle"),
    )

    dailyAppUsageId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    dailyUsageId: Mapped[str] = mapped_column(String(32), ForeignKey("computerDailyUsage.dailyUsageId", ondelete="CASCADE"), nullable=False)
    bundleId: Mapped[str] = mapped_column(String(300), nullable=False)
    appName: Mapped[str] = mapped_column(String(200), nullable=False)
    activeSeconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
