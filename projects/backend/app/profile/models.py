"""能力画像模型：维度定义/孩子维度状态/历史轨迹/L1 trace（规格 v2 §5.1/§10）。

- profile_states：child_id × dimension = evidence_level（四枚举），detail_json 携带
  证据链引用（L3→L2(evidence)→L1(trace)），可审计可回放；
- profile_history：聚合规则改版前的快照，历史轨迹不追改；
- trace_events：L1 原始证据轨迹 append-only（每次尝试/提示），写入永不抛错。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
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


class ProfileDimension(Base):
    """能力维度定义（教研资产）：首批 {运算,概念理解,应用迁移,数感}。"""

    __tablename__ = "profile_dimensions"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)


class ProfileState(Base):
    """每孩子×维度 = 证据带；detail_json 存证据链引用（审计用）。"""

    __tablename__ = "profile_states"
    __table_args__ = (
        UniqueConstraint("child_id", "dimension_code", name="uq_profile_child_dim"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    dimension_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("profile_dimensions.code"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # 四枚举
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    as_of_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    detail_json: Mapped[dict | None] = mapped_column(JSONType)  # L3→L2→L1 链引用
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProfileHistory(Base):
    """画像轨迹快照：聚合规则改版前留存，历史不追改。"""

    __tablename__ = "profile_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    as_of_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TraceEvent(Base):
    """L1 原始证据轨迹（append-only）：尝试/提示等原始记录。"""

    __tablename__ = "trace_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    activity_id: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # attempt|hint|...
    payload_json: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
