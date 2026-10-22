"""LessonSpec v0.1：原型兼容模型（只读兼容层）。

对应 D:\\aiedu\\schemas\\lesson-spec.schema.json。v0.1 课程经 legacy adapter
继续作为演示课程；新内容一律产出 v2（app.models.lesson_v2）。
"""

from typing import Literal

from pydantic import BaseModel, Field


class AudienceV01(BaseModel):
    grade: int = Field(ge=1, le=9)
    language: str = Field(min_length=2)
    priorKnowledge: list[str] = Field(default_factory=list, max_length=5)
    assumption: str | None = None


class SolutionStepV01(BaseModel):
    id: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    expression: str | None = None
    check: str | None = None


class AlternativeApproachV01(BaseModel):
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    expression: str | None = None
    whenToUse: str = Field(min_length=1)


class SolutionV01(BaseModel):
    answer: str = Field(min_length=1)
    verified: Literal[True] = True
    verificationMethod: str = Field(min_length=1)
    alternativeApproaches: list[AlternativeApproachV01] = Field(
        default_factory=list, max_length=3
    )
    steps: list[SolutionStepV01] = Field(min_length=1, max_length=12)


class SceneInteractionV01(BaseModel):
    prompt: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=5)
    correctIndex: int = Field(ge=0)
    feedback: dict[str, str] = Field(
        description="必须包含 correct 与 incorrect 两个键"
    )


class SceneV01(BaseModel):
    id: str = Field(min_length=1)
    kind: Literal["orient", "model", "connect", "check", "summary"]
    title: str = Field(min_length=1)
    narration: str = Field(min_length=1)
    expression: str | None = None
    visibleMath: list[str] = Field(default_factory=list)
    visual: dict | None = None
    interaction: SceneInteractionV01 | None = None


class ApproachV01(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    method: str = Field(min_length=1)
    whenToUse: str | None = None
    mnemonic: str | None = None
    scenes: list[SceneV01] = Field(min_length=3, max_length=10)


class TeachingPlanV01(BaseModel):
    objective: str = Field(min_length=1)
    misconceptions: list[str] = Field(default_factory=list, max_length=3)
    scenes: list[SceneV01] = Field(min_length=3, max_length=10)
    approaches: list[ApproachV01] = Field(default_factory=list, max_length=3)


class RenderV01(BaseModel):
    mode: Literal["interactive_html"] = "interactive_html"
    engine: Literal["vanilla_svg", "threejs_local", "diagram", "geometry3d"]
    template_config_ref: str | None = None


class LessonSpecV01(BaseModel):
    version: Literal["0.1"] = "0.1"
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    audience: AudienceV01
    question: str = Field(min_length=1)
    solution: SolutionV01
    teachingPlan: TeachingPlanV01
    render: RenderV01
