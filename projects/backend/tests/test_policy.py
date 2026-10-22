"""T2 测试：全局教学政策与程序化门禁。"""

from app.intent import analyze_intent
from app.policy import GLOBAL_TEACHING_POLICY, check_teaching_policy
from app.strategies import make_ten


def _spec():
    return make_ten.build({"a": 16, "b": 8, "k": 2})


def test_make_ten_spec_passes_policy() -> None:
    """凑十法切片应通过全局教学政策门禁。"""
    spec = _spec()
    intent = analyze_intent({"kind": "problem", "content": "16+8"})
    assert check_teaching_policy(spec, intent) == []


def test_policy_is_builtin_not_in_skill() -> None:
    """通用规范内置：包含先想后看/儿童友好/交互优先等条目。"""
    for key in ("先想后看", "不泄露答案", "交互优先", "反馈友好", "儿童友好", "动画同源"):
        assert key in GLOBAL_TEACHING_POLICY


def test_problem_without_attempt_gate_blocked() -> None:
    """problem 类无尝试门槛 → BLOCKER。"""
    spec = _spec()
    nodes = list(spec.activity_graph)
    # 移除全部 predict 节点，仅保留 observe
    observe = [n for n in nodes if n.type == "observe"]
    stripped = spec.model_copy(update={"activity_graph": observe})
    issues = check_teaching_policy(stripped)
    assert any("BLOCKER" in i and "attempt gate" in i for i in issues)


def test_observe_before_attempt_blocked() -> None:
    """解题类课程首节点为 observe（先讲解）→ BLOCKER。"""
    spec = _spec()
    nodes = list(spec.activity_graph)
    observe = next(n for n in nodes if n.type == "observe")
    predict = next(n for n in nodes if n.type == "predict")
    reordered = [observe, predict]
    stripped = spec.model_copy(update={"activity_graph": reordered})
    intent = analyze_intent({"kind": "problem", "content": "16+8"})
    issues = check_teaching_policy(stripped, intent)
    assert any("BLOCKER" in i and "precedes first attempt" in i for i in issues)


def test_choice_without_distractor_source_major() -> None:
    """选择题无错误模式依据 → MAJOR。"""
    spec = _spec()
    nodes = list(spec.activity_graph)
    predict = next(n for n in nodes if n.type == "predict")
    # 把数字回答换成无依据的选择题
    from app.models.lesson_v2 import ResponseChoice

    predict.response = ResponseChoice(
        kind="choice", options=["2", "8", "10"], correct_index=0
    )
    updated = spec.model_copy(update={"activity_graph": nodes})
    issues = check_teaching_policy(updated)
    assert any("MAJOR" in i and "distractors_from" in i for i in issues)


def test_attempt_node_without_assistance_major() -> None:
    """尝试节点无提示梯度 → MAJOR。"""
    spec = _spec()
    nodes = list(spec.activity_graph)
    predict = next(n for n in nodes if n.type == "predict")
    predict.assistance = []
    updated = spec.model_copy(update={"activity_graph": nodes})
    issues = check_teaching_policy(updated)
    assert any("MAJOR" in i and "assistance" in i for i in issues)


def test_unverified_spec_blocked() -> None:
    """数学硬前提：未核验 → BLOCKER。"""
    spec = _spec()
    verification = spec.verification.model_copy(update={"verified": False})
    stripped = spec.model_copy(update={"verification": verification})
    issues = check_teaching_policy(stripped)
    assert any("BLOCKER" in i and "verified" in i for i in issues)
