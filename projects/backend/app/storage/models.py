"""持久化模型：job/课程版本/核验凭据/资源清单/outbox + curriculum语义层占位。

R2 §11：job创建和outbox写入在同一事务；worker以job_id+stage+input_hash幂等领取；
阶段输出持久化后再推进；旧attempt不能覆盖新结果。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base

# SQLite（测试）用通用 JSON，PostgreSQL 用 JSONB
JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now()


class LessonJob(Base):
    """生成任务主记录；状态机 QUEUED→RUNNING→VALIDATING→SUCCEEDED。"""

    __tablename__ = "lesson_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    curriculum_context_json: Mapped[dict | None] = mapped_column(JSONType)
    objectives_json: Mapped[list | None] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    stage: Mapped[str | None] = mapped_column(String(32))
    stage_version: Mapped[str | None] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    error_code: Mapped[str | None] = mapped_column(String(64))
    clarification_json: Mapped[dict | None] = mapped_column(JSONType)
    lesson_id: Mapped[str | None] = mapped_column(String(64))
    parent_job_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JobStageRun(Base):
    """阶段运行记录：worker按 job_id+stage+input_hash 幂等领取。"""

    __tablename__ = "job_stage_runs"
    __table_args__ = (
        UniqueConstraint("job_id", "stage", "attempt", name="uq_stage_run"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("lesson_jobs.id"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    output_ref: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))


class LessonRevision(Base):
    """课程版本：不可变；manifest引用后标记SUCCEEDED。"""

    __tablename__ = "lesson_revisions"
    __table_args__ = (
        UniqueConstraint("lesson_id", "revision", name="uq_lesson_revision"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    runtime_version: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_manifest_ref: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VerificationRecordRow(Base):
    """核验凭据持久化：verifier_version+content_hash用于复用失效判断。"""

    __tablename__ = "verification_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str | None] = mapped_column(String(32))
    lesson_id: Mapped[str | None] = mapped_column(String(64))
    verifier_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ArtifactManifest(Base):
    """资源清单：内容寻址哈希为唯一键；DB事务引用最终manifest。"""

    __tablename__ = "artifact_manifests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DispatchOutbox(Base):
    """outbox：job创建同事务写入，dispatcher轮询派发到Redis队列。"""

    __tablename__ = "dispatch_outbox"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("lesson_jobs.id"), nullable=False
    )
    payload_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------------------
# curriculum语义层占位（R2 §11；本包仅建表结构，业务在后续扩展）
# ---------------------------------------------------------------------------

class CurriculumItem(Base):
    __tablename__ = "curriculum_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    curriculum_version: Mapped[str | None] = mapped_column(String(64))
    domain: Mapped[str | None] = mapped_column(String(32))
    concept_id: Mapped[str | None] = mapped_column(String(64))


class LearningObjectiveRow(Base):
    __tablename__ = "learning_objectives"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class InstructionalUnit(Base):
    __tablename__ = "instructional_units"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)


class UnitActivityRef(Base):
    __tablename__ = "unit_activity_refs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    unit_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("instructional_units.code"), nullable=False
    )
    activity_ref: Mapped[str] = mapped_column(String(128), nullable=False)


# ---------------------------------------------------------------------------
# job状态机常量与合法迁移表
# ---------------------------------------------------------------------------

JOB_STATUSES = {
    "QUEUED",
    "RUNNING",
    "VALIDATING",
    "SUCCEEDED",
}
ALLOWED_JOB_STATUSES = JOB_STATUSES | {"RETRYING", "FAILED", "CANCELED"}

JOB_TRANSITIONS: dict[str, set[str]] = {
    "QUEUED": {"RUNNING", "CANCELED", "FAILED"},
    "RUNNING": {"VALIDATING", "RETRYING", "FAILED", "CANCELED"},
    "VALIDATING": {"SUCCEEDED", "RETRYING", "FAILED", "CANCELED"},
}
