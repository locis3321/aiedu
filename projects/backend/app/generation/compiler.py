"""教学单元编译 + 分域检查调用点（T9 validate.py 复用）。

编译：dict → LessonSpecV2（schema 校验）；
检查：数学（claims 复验）、教学（语义校验器）、布局（前端 layout.ts）。
"""

from app.models.lesson_v2 import LessonSpecV2
from app.models.semantics import validate_activity_graph


def compile_spec(spec_dict: dict) -> LessonSpecV2:
    """dict → LessonSpecV2；schema 校验失败抛 ValidationError。"""
    return LessonSpecV2.model_validate(spec_dict)


def check_math(spec: LessonSpecV2) -> list[str]:
    """数学检查：verification.verified + claims 覆盖（复验由 T3 完成）。"""
    issues: list[str] = []
    if not spec.verification.verified:
        issues.append("verification.verified is false")
    if not spec.verification.covered_claim_ids:
        issues.append("no covered claims")
    return issues


def check_teaching(spec: LessonSpecV2) -> list[str]:
    """教学检查：活动图语义（可达/引用/门槛）。"""
    return validate_activity_graph(spec)
