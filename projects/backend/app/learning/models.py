"""学习闭环模型：会话/活动/尝试/证据/会话事件（规格 v2 §5.1）。

- evidence.id = 纯完成证据 ID（R7' 积分幂等键）；
- 证据分级服务端判定：independent/assisted/demonstrated/needs_review（全局枚举）；
- session_events：StreamBus 事件持久化（seq 续传）。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return uuid.uuid4().hex


class LearningSession(Base):
    """每日学习 session：一个 session 含多个 activity（不是一道题）。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SessionActivity(Base):
    """session 内单个学习活动：gate 课堂/变式/迁移/试卷等。"""

    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id"), nullable=False, index=True
    )
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="gate")
    lesson_id: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int | None] = mapped_column(Integer)
    spec_json: Mapped[dict | None] = mapped_column(JSONType)  # 服务端完整课程规格
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    method_source: Mapped[str | None] = mapped_column(String(8))  # skill|standard
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Attempt(Base):
    """一次作答或一次提示请求（kind=answer|hint）。"""

    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    activity_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("activities.id"), nullable=False, index=True
    )
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    step_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="answer")
    value_json: Mapped[dict | None] = mapped_column(JSONType)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EvidenceRecord(Base):
    """学习证据：完成证据（R7' 幂等键）+ 分级；一次活动×kind 至多一条。"""

    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("activity_id", "kind", name="uq_activity_evidence_kind"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id"), nullable=False, index=True
    )
    activity_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("activities.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    detail_json: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SessionEvent(Base):
    """StreamBus 事件持久化：session 内按 turn/seq 续传（断线重连依据）。"""

    __tablename__ = "session_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id"), nullable=False, index=True
    )
    turn_id: Mapped[str] = mapped_column(String(32), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="server")
    stage: Mapped[str | None] = mapped_column(String(32))
    payload_json: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
