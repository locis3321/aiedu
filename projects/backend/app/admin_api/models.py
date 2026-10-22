"""运营后台模型（规格 v2 §5.1：audit_logs/skills/prompts/models_configs/
tts_configs/ai_avatar_configs/sms_templates/safety_feedbacks）。

原则：配置保存与运行时生效分离（版本/草稿/发布）；凭据只存配置状态不存密钥；
审计写操作；试卷结果治理只读+复核，不产生能力结论。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return uuid.uuid4().hex


class AuditLog(Base):
    """审计：敏感写操作留痕（检索分页；删除仅授权策略内且需确认）。"""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    actor_role: Mapped[str] = mapped_column(String(24), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    detail_json: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SkillRecord(Base):
    """Skill 注册表：版本/启停/引用保护（导入安全门见 service）。"""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # slug
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    referenced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manifest_json: Mapped[dict | None] = mapped_column(JSONType)  # 一行 manifest
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PromptRecord(Base):
    """提示词/人设：kind 分开管理（teaching|companion），版本草稿/发布独立。"""

    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # teaching|companion
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # draft|published
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelConfig(Base):
    """模型配置：凭据加密存储（Fernet），读取仅返回状态与尾号，不返回明文密钥。"""

    __tablename__ = "models_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # generate|tts|companion
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    credential_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="missing"
    )  # configured|missing（不返回密钥）
    api_key_enc: Mapped[str | None] = mapped_column(Text)
    params_json: Mapped[dict | None] = mapped_column(JSONType)


class TtsConfig(Base):
    """TTS 全局配置：供应商/音色/语速；未接入渠道显式提示，不假装成功。"""

    __tablename__ = "tts_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="mimo")
    voice: Mapped[str | None] = mapped_column(String(64))
    rate: Mapped[float | None] = mapped_column()
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AiAvatarConfig(Base):
    """AI 形象配置：轻量角色资产与启用开关；不影响数学过程动画。"""

    __tablename__ = "ai_avatar_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assets_json: Mapped[dict | None] = mapped_column(JSONType)  # speaking/waiting/encouraging
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SmsTemplateConfig(Base):
    """短信模板管理：腾讯云签名/模板 ID（不存真实密钥）。"""

    __tablename__ = "sms_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    sign_name: Mapped[str | None] = mapped_column(String(64))
    template_id: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SystemSetting(Base):
    """后台可配置系统参数/凭据：普通值存原始值，凭据存 {"enc": Fernet密文}。"""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SafetyFeedback(Base):
    """陪伴安全反馈：条目/处置状态；敏感对话默认不完整展示。"""

    __tablename__ = "safety_feedbacks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    child_id: Mapped[str | None] = mapped_column(String(32))
    session_id: Mapped[str | None] = mapped_column(String(32))
    summary_text: Mapped[str | None] = mapped_column(String(255))  # 摘要，非完整对话
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReviewRecord(Base):
    """审核记录：证据标记齐备才可发布；verification 数据只读（反强改）。"""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    revision_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    lesson_id: Mapped[str | None] = mapped_column(String(64))
    math_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    teaching_gate_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    age_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    layout_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reject_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_by_role: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
