"""教学请求输入契约：题目 / 概念 / 定理 / 主题 / 学习目标 / 误区。

所有教学内容生成请求共用同一输入结构；信息缺失时由上层返回 needs_clarification，
不允许默默改写输入目标。
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class CurriculumContext(BaseModel):
    """课程内容目录上下文：学段、年级、课程版本。"""

    stage: Literal["primary", "junior", "senior"] = Field(
        description="学段：小学 / 初中 / 高中"
    )
    grade: int = Field(ge=1, le=12)
    curriculum_version: str | None = Field(
        default=None, description="课程标准/教材版本标识"
    )


class TeachingRequestProblem(BaseModel):
    kind: Literal["problem"]
    content: str = Field(min_length=1)


class TeachingRequestConcept(BaseModel):
    kind: Literal["concept"]
    content: str = Field(min_length=1)


class TeachingRequestTheorem(BaseModel):
    kind: Literal["theorem"]
    content: str = Field(min_length=1)


class TeachingRequestTopic(BaseModel):
    kind: Literal["topic"]
    content: str = Field(min_length=1)


class TeachingRequestObjective(BaseModel):
    kind: Literal["objective"]
    content: str = Field(min_length=1)


class TeachingRequestMisconception(BaseModel):
    kind: Literal["misconception"]
    content: str = Field(min_length=1)


TeachingRequestInput = Annotated[
    TeachingRequestProblem
    | TeachingRequestConcept
    | TeachingRequestTheorem
    | TeachingRequestTopic
    | TeachingRequestObjective
    | TeachingRequestMisconception,
    Field(discriminator="kind"),
]
