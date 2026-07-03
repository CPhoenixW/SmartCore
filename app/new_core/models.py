from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.session import Base

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def newId() -> str:
    return uuid.uuid4().hex


def nowIso() -> str:
    return datetime.now(_DEFAULT_TZ).isoformat()


class EvtBase(Base):
    __tablename__ = "evtBase"

    evtId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    desc: Mapped[str | None] = mapped_column(Text)
    evtType: Mapped[str] = mapped_column(String(20), nullable=False)
    prio: Mapped[str] = mapped_column(String(10), default="mid", nullable=False)
    stat: Mapped[str] = mapped_column(String(20), default="todo", nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    updatedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class LifeEvt(Base):
    __tablename__ = "lifeEvt"

    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), primary_key=True
    )
    dueAt: Mapped[str | None] = mapped_column(String(64))
    doneAt: Mapped[str | None] = mapped_column(String(64))


class DdlEvt(Base):
    __tablename__ = "ddlEvt"

    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), primary_key=True
    )
    ddlAt: Mapped[str | None] = mapped_column(String(64))
    hardDdl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CourseTpl(Base):
    __tablename__ = "courseTpl"

    tplId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    courseName: Mapped[str] = mapped_column(String(200), nullable=False)
    teacher: Mapped[str | None] = mapped_column(String(100))
    room: Mapped[str | None] = mapped_column(String(200))
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    startTime: Mapped[str | None] = mapped_column(String(8))
    endTime: Mapped[str | None] = mapped_column(String(8))
    startWeek: Mapped[int | None] = mapped_column(Integer)
    endWeek: Mapped[int | None] = mapped_column(Integer)
    weekMode: Mapped[str] = mapped_column(String(10), default="all", nullable=False)
    semester: Mapped[str | None] = mapped_column(String(50))


class CourseInst(Base):
    __tablename__ = "courseInst"

    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), primary_key=True
    )
    tplId: Mapped[str] = mapped_column(
        String(32), ForeignKey("courseTpl.tplId", ondelete="RESTRICT"), nullable=False
    )
    classDate: Mapped[str | None] = mapped_column(String(16))
    attendStat: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)


class Idea(Base):
    __tablename__ = "idea"

    ideaId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    srcType: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    mediaPath: Mapped[str | None] = mapped_column(String(500))
    handled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class IdeaToEvt(Base):
    __tablename__ = "ideaToEvt"

    ideaId: Mapped[str] = mapped_column(
        String(32), ForeignKey("idea.ideaId", ondelete="CASCADE"), primary_key=True
    )
    evtId: Mapped[str] = mapped_column(
        String(32), ForeignKey("evtBase.evtId", ondelete="CASCADE"), nullable=False
    )
    convertedAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class DevState(Base):
    __tablename__ = "devState"

    stateId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    devId: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    seenAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON)


class NotifyLog(Base):
    __tablename__ = "notifyLog"

    notifyId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    dedupKey: Mapped[str | None] = mapped_column(String(200), unique=True)
    targetKind: Mapped[str] = mapped_column(String(20), nullable=False)
    targetId: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scheduledAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
    sentAt: Mapped[str | None] = mapped_column(String(64))
    stat: Mapped[str] = mapped_column(String(20), nullable=False)
    failReason: Mapped[str | None] = mapped_column(Text)


class MsgLog(Base):
    __tablename__ = "msgLog"

    msgId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    src: Mapped[str] = mapped_column(String(50), nullable=False)
    externalId: Mapped[str | None] = mapped_column(String(200))
    rawText: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(100))
    stat: Mapped[str | None] = mapped_column(String(50))
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)


class ActLog(Base):
    __tablename__ = "actLog"

    actId: Mapped[str] = mapped_column(String(32), primary_key=True, default=newId)
    src: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(100))
    actType: Mapped[str] = mapped_column(String(20), nullable=False)
    targetKind: Mapped[str | None] = mapped_column(String(50))
    targetId: Mapped[str | None] = mapped_column(String(32))
    beforeData: Mapped[dict | None] = mapped_column(JSON)
    afterData: Mapped[dict | None] = mapped_column(JSON)
    undoToken: Mapped[str | None] = mapped_column(String(64), unique=True)
    createdAt: Mapped[str] = mapped_column(String(64), default=nowIso, nullable=False)
