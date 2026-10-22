"""意图识别器：程序化规则优先，LLM 为可选扩展点。

规则识别保证确定性、可测试、零成本；LLM 只用于规则无法覆盖的开放输入。
识别结果只描述「要教什么」，不生成课程内容。
"""

import re

from aiedu_core.intent.contract import TeachingIntent

# ---------------------------------------------------------------------------
# 规则表
# ---------------------------------------------------------------------------

_ARITHMETIC = re.compile(
    r"^\s*\d{1,4}\s*[+\-×x*·÷]\s*\d{1,4}\s*(=\s*\d{1,4})?\s*$"
)
_FRACTION = re.compile(r"\d+\s*/\s*\d+")
_TWO_DIGIT_PLUS_ONE = re.compile(r"^\s*(\d{1,2})\s*\+\s*(\d)\s*$")
_TWO_DIGIT_MINUS_ONE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d)\s*$")

_MISCONCEPTION_WORDS = ("分不清", "总是错", "误区", "混淆", "搞混", "容易错", "错误")
_THEOREM_WORDS = ("定理", "求证", "证明题")
_CONCEPT_WORDS = ("概念", "什么是", "理解", "意义", "为什么")
_OBJECTIVE_WORDS = ("目标", "学会", "掌握", "能够")
_TOPIC_WORDS = ("单元", "章节", "主题", "复习")
_LESSON_WORDS = ("设计一节", "上一节", "课程", "一节课")

_DOMAIN_RULES = (
    ("number_and_operations", ("分数", "小数", "计算", "加减乘除", "凑十", "破十", "竖式")),
    ("algebra", ("方程", "代数", "不等式", "未知数")),
    ("geometry", ("三角形", "几何", "全等", "相似", "圆", "角", "面积")),
    ("function", ("函数", "图像", "单调", "斜率")),
    ("statistics_probability", ("概率", "统计", "随机")),
    ("proof_reasoning", ("证明", "推理")),
)

_GOAL_RULES = (
    ("skill_practice", ("计算", "运算", "口算", "速算")),
    ("method_understanding", ("方法", "策略")),
    ("concept_building", ("概念", "理解")),
    ("reasoning_proof", ("证明题",)),
    ("exploration_discovery", ("探究", "发现")),
    ("practice_review", ("练习", "复习")),
)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def _age_band_from_context(curriculum_context: dict | None) -> str:
    if not curriculum_context:
        return "unknown"
    grade = curriculum_context.get("grade")
    if isinstance(grade, int):
        if grade <= 3:
            return "lower_primary"
        if grade <= 6:
            return "upper_primary"
        if grade <= 9:
            return "middle_school"
        return "high_school"
    stage = curriculum_context.get("stage")
    return {
        "primary": "upper_primary",
        "junior": "middle_school",
        "senior": "high_school",
    }.get(stage, "unknown")


def _input_kind_of(text: str) -> str:
    if _contains_any(text, _MISCONCEPTION_WORDS):
        return "misconception"
    if _contains_any(text, _THEOREM_WORDS):
        return "theorem"
    if _contains_any(text, _LESSON_WORDS):
        return "lesson_request"
    if _contains_any(text, _OBJECTIVE_WORDS):
        return "objective"
    if _contains_any(text, _TOPIC_WORDS):
        return "topic"
    if _contains_any(text, _CONCEPT_WORDS):
        return "concept"
    if _ARITHMETIC.match(text):
        return "problem"
    # 兜底：短文本按概念请求处理（如“教一下凑十法”“讲讲分数”）
    return "concept"


def _domain_of(text: str) -> str:
    if _FRACTION.search(text) or _ARITHMETIC.match(text):
        return "number_and_operations"
    for domain, words in _DOMAIN_RULES:
        if _contains_any(text, words):
            return domain
    return "unknown"


def _goal_of(text: str, input_kind: str) -> str:
    if input_kind == "misconception":
        return "misconception_correction"
    if input_kind == "theorem":
        return "reasoning_proof"
    if _ARITHMETIC.match(text):
        return "skill_practice"
    if re.search(r"凑十法|破十法|退位减法|竖式|方法|策略", text):
        return "method_understanding"
    for goal, words in _GOAL_RULES:
        if _contains_any(text, words):
            return goal
    return "unknown"


def _candidate_queries(text: str) -> list[str]:
    """候选教学方法查询词：仅作检索建议，不直接决定课程。"""
    queries: list[str] = []
    m = _TWO_DIGIT_PLUS_ONE.match(text)
    if m and int(m.group(1)) % 10 + int(m.group(2)) >= 10:
        queries.append("凑十法")
        queries.append("凑整思想")
        queries.append("数量守恒")
        return queries
    m = _TWO_DIGIT_MINUS_ONE.match(text)
    if m and int(m.group(1)) % 10 < int(m.group(2)):
        queries.append("破十法")
        queries.append("退位减法")
        return queries
    for known in ("凑十法", "破十法", "退位减法", "竖式加法"):
        if known in text:
            queries.append(known)
    for known in ("分数", "等分", "平均分"):
        if known in text:
            queries.append("分数")
            break
    return queries


def analyze_intent(
    input_json: dict,
    curriculum_context: dict | None = None,
) -> TeachingIntent:
    """规则意图识别：输入 → TeachingIntent。

    输入过短或无法识别时 requires_clarification=True，不伪造教学事实。
    """
    content = str(input_json.get("content") or "").strip()
    if len(content) < 2:
        return TeachingIntent(
            input_kind="concept",
            subject_domain="unknown",
            age_band=_age_band_from_context(curriculum_context),
            goal_kind="unknown",
            teaching_goal="待澄清",
            requires_clarification=True,
            clarification_questions=["请提供更具体的教学内容或题目。"],
            source="rule_based",
        )

    input_kind = _input_kind_of(content)
    goal_kind = _goal_of(content, input_kind)

    return TeachingIntent(
        input_kind=input_kind,
        subject_domain=_domain_of(content),
        age_band=_age_band_from_context(curriculum_context),
        goal_kind=goal_kind,
        teaching_goal=f"围绕「{content}」开展符合年龄阶段的教学活动",
        learner_difficulties=[],
        requires_clarification=False,
        candidate_skill_queries=_candidate_queries(content),
        source="rule_based",
    )
