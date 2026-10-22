"""积分与成长模型：账本流水 + 发放规则（规格 v2 §5.1）。

- ledger 是业务事实：只增不改，balance_after 由流水推导写入；
- reward_rules 是配置：版本化、可启停；规则版本仅作流水属性（R7'）；
- 幂等：唯一约束 (evidence_id, event_type)——纯完成证据 ID，重复领取不重复发放。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class RewardRule(Base):
    """发放规则：事件类型 × 各级证据奖励值 × 上限 × 版本化启停。"""

    __tablename__ = "reward_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    points_independent: Mapped[int] = mapped_column(Integer, nullable=False)
    points_assisted: Mapped[int] = mapped_column(Integer, nullable=False)
    points_demonstrated: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_cap: Mapped[int | None] = mapped_column(Integer)  # 每孩子每日该事件上限
    per_event_cap: Mapped[int | None] = mapped_column(Integer)  # 每孩子该事件累计上限
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LedgerEntry(Base):
    """成长星账本流水：原因/关联证据ID/幂等键/变动前后余额。"""

    __tablename__ = "ledger"
    __table_args__ = (
        UniqueConstraint("evidence_id", "event_type", name="uq_ledger_evidence_event"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    evidence_id: Mapped[str | None] = mapped_column(String(32))  # R7' 幂等键=纯完成证据ID
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    rule_version: Mapped[int | None] = mapped_column(Integer)  # 仅流水属性，不改写历史
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # 变动值（可为负=扣减）
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
