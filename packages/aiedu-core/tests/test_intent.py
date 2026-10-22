"""T1 测试：TeachingIntent 契约与规则意图识别。"""

from aiedu_core.intent import analyze_intent
from aiedu_core.intent.contract import TeachingIntent


def test_arithmetic_problem_intent() -> None:
    """纯算式 → problem + 数与运算 + 技能训练 + 凑十候选查询。"""
    intent = analyze_intent({"kind": "problem", "content": "16+8"})
    assert intent.input_kind == "problem"
    assert intent.subject_domain == "number_and_operations"
    assert intent.goal_kind == "skill_practice"
    assert "凑十法" in intent.candidate_skill_queries
    assert intent.requires_clarification is False


def test_borrow_subtraction_candidate_queries() -> None:
    """退位减法 → 候选查询包含破十法/退位减法。"""
    intent = analyze_intent({"kind": "problem", "content": "13-5"})
    assert intent.input_kind == "problem"
    assert any(q in intent.candidate_skill_queries for q in ("破十法", "退位减法"))


def test_method_request_intent() -> None:
    """「教一下凑十法」→ concept + 方法理解 + 候选查询。"""
    intent = analyze_intent({"kind": "concept", "content": "教一下凑十法"})
    assert intent.input_kind == "concept"
    assert intent.goal_kind == "method_understanding"
    assert "凑十法" in intent.candidate_skill_queries


def test_misconception_intent() -> None:
    """误区输入 → misconception + 误区纠正。"""
    intent = analyze_intent(
        {"kind": "misconception", "content": "孩子总是分不清1/3和1/4哪个大"}
    )
    assert intent.input_kind == "misconception"
    assert intent.goal_kind == "misconception_correction"
    assert intent.subject_domain == "number_and_operations"


def test_geometry_theorem_intent() -> None:
    """「讲三角形全等」→ geometry + 推理证明。"""
    intent = analyze_intent({"kind": "theorem", "content": "讲三角形全等的判定定理"})
    assert intent.input_kind == "theorem"
    assert intent.subject_domain == "geometry"
    assert intent.goal_kind == "reasoning_proof"


def test_function_exploration_intent() -> None:
    """探究课请求 → lesson_request + function + 探究发现。"""
    intent = analyze_intent(
        {"kind": "topic", "content": "设计一节函数单调性的探究课"}
    )
    assert intent.input_kind == "lesson_request"
    assert intent.subject_domain == "function"
    assert intent.goal_kind == "exploration_discovery"


def test_age_band_from_grade_context() -> None:
    """年级上下文映射年龄阶段。"""
    intent = analyze_intent(
        {"kind": "problem", "content": "16+8"},
        curriculum_context={"stage": "primary", "grade": 1},
    )
    assert intent.age_band == "lower_primary"
    intent = analyze_intent(
        {"kind": "problem", "content": "16+8"},
        curriculum_context={"stage": "junior", "grade": 8},
    )
    assert intent.age_band == "middle_school"


def test_empty_input_requires_clarification() -> None:
    """空输入 → requires_clarification，不伪造教学事实。"""
    intent = analyze_intent({"kind": "problem", "content": ""})
    assert intent.requires_clarification is True
    assert intent.clarification_questions


def test_intent_is_pydantic_contract() -> None:
    """TeachingIntent 可被 Pydantic 校验（生成链路第一步的契约）。"""
    intent = analyze_intent({"kind": "problem", "content": "27+6"})
    parsed = TeachingIntent.model_validate(intent.model_dump())
    assert parsed.input_kind == "problem"
