from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.session import Base

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def newId() -> str:
    return uuid.uuid4().hex


def nowIso() -> str:
    return datetime.now(_DEFAULT_TZ).isoformat()


class AppUser(Base):
    __tablename__ = "appUser"

    userId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
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
    )

    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), primary_key=True
    )
    planEvtId: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("planEvt.evtId", ondelete="CASCADE"), nullable=True
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
    content: Mapped[str] = mapped_column(Text, nullable=False)
    srcType: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    mediaPath: Mapped[str | None] = mapped_column(String(500))
    handled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


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
