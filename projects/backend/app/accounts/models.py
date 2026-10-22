"""账号域模型：家长用户/孩子档案/监护同意/短信验证码/时长设置（规格 v2 §5.1）。

- 最小必要收集：昵称+年级(或年龄段)必填；教材版本可选；不收集姓名/学校/精确生日/兴趣标签。
- 删除语义：children 软删标记（deleted_at），物理删除策略待业务确认（§5.3）。
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


class ParentUser(Base):
    """家长账号：微信 openid 与手机号至少其一（登录方式不同）。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    wechat_openid: Mapped[str | None] = mapped_column(String(64), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    nickname: Mapped[str | None] = mapped_column(String(64))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChildProfile(Base):
    """孩子档案：归属家长；软删标记保留学习数据处置策略（§5.3）。"""

    __tablename__ = "children"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    parent_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=False, index=True
    )
    nickname: Mapped[str] = mapped_column(String(32), nullable=False)
    grade: Mapped[str | None] = mapped_column(String(16))  # 年级（如 '3'）
    age_group: Mapped[str | None] = mapped_column(String(16))  # 年龄段（如 '6-8'）
    textbook_version: Mapped[str | None] = mapped_column(String(32))  # 可选（2026-10-10）
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConsentRecord(Base):
    """监护同意：每个家长×同意项一行，状态 granted|withdrawn（可撤回后重新同意）。"""

    __tablename__ = "consents"
    __table_args__ = (
        UniqueConstraint("parent_id", "consent_key", name="uq_parent_consent"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    parent_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=False, index=True
    )
    consent_key: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="granted")
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SmsVerification(Base):
    """短信验证码：只存哈希；有效期/尝试次数/防刷由服务层按设置执行。"""

    __tablename__ = "sms_verifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)  # dev|prod
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UsageSettings(Base):
    """按孩子的使用时长设置（每日/连续/休息）+ 陪伴开关；跨孩子隔离。"""

    __tablename__ = "usage_settings"

    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), primary_key=True
    )
    daily_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    continuous_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    rest_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    companion_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
