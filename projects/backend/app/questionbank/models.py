"""题库与练习安排模型（规格 v2 §5.1）。

- questions：内置题（来源/知识点/审核态/数学核验）；未审核题不得进入抽题；
- question_sources：第三方题源配置（provider 工厂绑定、签名版本化、可启停）；
- exam_templates/papers/results：三类试卷模板/生成卷/结果（结果写入证据体系）；
- practice_sets：按表现安排的练习集；
- knowledge_nodes：教材同步知识图谱节点（前置关系 edges 表待 A5 教研数据接入后新增）。
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
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return uuid.uuid4().hex


class Question(Base):
    """题目：来源为业务事实；审核态控制是否可进入抽题。"""

    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # builtin|third_party
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    math_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuestionSource(Base):
    """第三方题源配置：provider 绑定后不可漂移；签名版本化。"""

    __tablename__ = "question_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(255))
    quota: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    knowledge_mapping_json: Mapped[dict | None] = mapped_column(JSONType)
    signature_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExamTemplate(Base):
    """三类试卷模板（diagnostic/sync/stage）：题目集 + 规则。"""

    __tablename__ = "exam_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # diagnostic|sync|stage
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    question_ids_json: Mapped[list | None] = mapped_column(JSONType)
    rules_json: Mapped[dict | None] = mapped_column(JSONType)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExamPaper(Base):
    """生成的试卷实例。"""

    __tablename__ = "exam_papers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    template_id: Mapped[str | None] = mapped_column(String(32))
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    question_ids_json: Mapped[list] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExamResult(Base):
    """试卷结果：answers + evidence_levels；写入证据体系（T3）与画像（T12）。"""

    __tablename__ = "exam_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    paper_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("exam_papers.id"), nullable=False
    )
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    answers_json: Mapped[dict | None] = mapped_column(JSONType)
    evidence_levels_json: Mapped[list | None] = mapped_column(JSONType)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unreviewed")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PracticeSet(Base):
    """按表现安排的练习集（basis_json 记录安排依据：薄弱点/来源）。"""

    __tablename__ = "practice_sets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    child_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("children.id"), nullable=False, index=True
    )
    question_ids_json: Mapped[list] = mapped_column(JSONType, nullable=False)
    basis_json: Mapped[dict | None] = mapped_column(JSONType)  # 薄弱点/来源注明
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnowledgeNode(Base):
    """知识图谱节点（教研生产+后台审核维护）。"""

    __tablename__ = "knowledge_nodes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)  # primary|junior|senior
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
