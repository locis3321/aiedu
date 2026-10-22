"""全局教学政策：内置通用教学规范。

本模块是产品底线，独立于任何 Teaching Skill。Skill 只能补充特殊教学方法，
不能覆盖或弱化这里的规则。通用规范不散落在每个 SKILL.md 中。
"""

from aiedu_core.intent.contract import TeachingIntent
from aiedu_core.models.lesson_v2 import LessonSpecV2

# 内置通用规范（供 prompt 与门禁共用；新增规则需同步 reviewer prompt）
GLOBAL_TEACHING_POLICY: dict[str, str] = {
    "先想后看": (
        "解题类课程必须至少一次学生先尝试/预测的交互；"
        "禁止提交题目后直接展示完整解法。"
    ),
    "不泄露答案": "提示与讲解不得在学生尝试前给出最终答案。",
    "交互优先": (
        "优先数字输入、拖拽、构造等生成式回答；"
        "选择题仅作支架，且干扰项必须基于常见错误模式，不能是随机数字。"
    ),
    "反馈友好": (
        "错误反馈应鼓励、具体、可继续操作；"
        "不简单判错、不羞辱、不直接给答案。"
    ),
    "儿童友好": (
        "按年龄阶段选择呈现：低年级更具体、卡通、可操作；"
        "高年级可更简洁，但仍需可视化与可操作。"
    ),
    "动画同源": (
        "引导与回放共用同一套 action/state_delta；"
        "动画必须表达数学意义，不能只是装饰或清空重绘。"
    ),
    "能力诚实": (
        "不支持的领域/表示必须显式标记能力缺口，不得假装覆盖。"
    ),
    "数学硬前提": (
        "verified==true 是发布硬前提；LLM 的 verified 无发布权限。"
    ),
}

_ATTEMPT_GATES = {"require_attempt", "require_correct_or_assisted"}
_ATTEMPT_TYPES = ("predict", "construct", "prove", "retrieve")


def check_teaching_policy(
    spec: LessonSpecV2,
    intent: TeachingIntent | None = None,
) -> list[str]:
    """程序化教学政策门禁：返回违规列表（BLOCKER/MAJOR 前缀），空列表表示通过。

    软性体验（文案语气、卡通程度）由 reviewer prompt 检查；本函数只做
    可机械判定的硬规则。
    """
    issues: list[str] = []

    # 数学硬前提
    if not spec.verification.verified:
        issues.append("BLOCKER: verification.verified is false (数学硬前提)")
    if (
        spec.teaching_request.kind == "problem"
        and not spec.verification.covered_claim_ids
    ):
        issues.append("BLOCKER: no covered claims (数学硬前提)")

    nodes = list(spec.activity_graph)
    attempt_nodes = [
        n for n in nodes
        if getattr(n, "gate", None) is not None and n.gate.mode in _ATTEMPT_GATES
    ]

    # 先想后看：problem 类必须有尝试门槛
    if spec.teaching_request.kind == "problem" and not attempt_nodes:
        issues.append("BLOCKER: problem lesson lacks attempt gate (先想后看)")

    # 解题/方法类课程：第一个活动必须是学生尝试，不能先讲解完整答案
    goal_kind = intent.goal_kind if intent else None
    if (
        spec.teaching_request.kind == "problem"
        and goal_kind in {"skill_practice", "method_understanding"}
        and attempt_nodes
    ):
        first_attempt_idx = min(nodes.index(n) for n in attempt_nodes)
        before = nodes[:first_attempt_idx]
        if any(n.type == "observe" for n in before):
            issues.append(
                "BLOCKER: observe narration precedes first attempt "
                "(可能先泄露答案)"
            )

    # 交互优先：选择题必须有错误模式依据
    for node in nodes:
        response = getattr(node, "response", None)
        if response is not None and getattr(response, "kind", None) == "choice":
            if not getattr(response, "distractors_from", None):
                issues.append(
                    f"MAJOR: {node.id} choice response lacks distractors_from "
                    "(干扰项需基于常见错误模式)"
                )

    # 提示梯度：尝试类节点应提供提示序列（示范出口）
    for node in attempt_nodes:
        assistance = getattr(node, "assistance", None)
        if assistance is not None and not assistance:
            issues.append(
                f"MAJOR: {node.id} attempt node lacks assistance (提示梯度)"
            )

    return issues
