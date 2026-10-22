"""TeachingIntent 契约：意图识别结果（生成链路第一步的输出）。

设计约束：
- 意图识别先于 skill 检索与策略匹配；
- 信息缺失时 requires_clarification=True，不允许默默改写输入目标；
- candidate_skill_queries 只是候选查询词，由后续检索器决定是否命中，
  检索器不得直接读取原始用户输入。
"""

from typing import Literal

from pydantic import BaseModel, Field

InputKind = Literal[
    "problem",
    "concept",
    "theorem",
    "topic",
    "objective",
    "misconception",
    "lesson_request",
    "unit_request",
]

SubjectDomain = Literal[
    "number_and_operations",
    "algebra",
    "geometry",
    "function",
    "statistics_probability",
    "proof_reasoning",
    "modeling",
    "unknown",
]

AgeBand = Literal[
    "lower_primary",  # 小学低年级（1~3）
    "upper_primary",  # 小学高年级（4~6）
    "middle_school",  # 初中（7~9）
    "high_school",  # 高中（10~12）
    "unknown",
]

GoalKind = Literal[
    "skill_practice",  # 运算/计算技能训练
    "concept_building",  # 概念建立
    "method_understanding",  # 方法/策略理解
    "misconception_correction",  # 误区纠正
    "reasoning_proof",  # 推理证明
    "exploration_discovery",  # 探究发现
    "practice_review",  # 练习评价与复习
    "unknown",
]


class TeachingIntent(BaseModel):
    """结构化教学意图：后续所有生成步骤的事实来源。"""

    input_kind: InputKind
    subject_domain: SubjectDomain
    age_band: AgeBand
    goal_kind: GoalKind
    teaching_goal: str = Field(
        min_length=1,
        description="一句话教学目标（不含答案泄露）",
    )
    learner_difficulties: list[str] = Field(
        default_factory=list,
        description="预判的常见学习困难；不确定时留空，不编造",
    )
    requires_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    candidate_skill_queries: list[str] = Field(
        default_factory=list,
        description="候选教学方法查询词；由检索器消费，不直接决定课程",
    )
    source: Literal["rule_based", "llm"] = "rule_based"
