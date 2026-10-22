"""D3–D4 测试：破十法（退位减法）策略模板。"""

import pytest
from sympy import Rational

from aiedu_core.intent import analyze_intent
from aiedu_core.models.filtering import filtered_spec
from aiedu_core.models.lesson_v2 import LessonSpecV2
from aiedu_core.models.semantics import validate_activity_graph
from aiedu_core.policy import check_teaching_policy
from aiedu_core.strategies import borrow_ten
from aiedu_core.verify.sympy_verify import evaluate_expression


def test_applies_to() -> None:
    # 两位数 - 一位数、个位不够减 → 命中
    assert borrow_ten.applies_to("16-9") is True
    assert borrow_ten.applies_to("23-8") is True
    assert borrow_ten.applies_to("13-5") is True
    # 个位够减 → 不命中（应先讲直接减）
    assert borrow_ten.applies_to("15-3") is False
    assert borrow_ten.applies_to("16-6") is False
    # 非本族：加法 / 两位数减数 / 减数为 0
    assert borrow_ten.applies_to("16+8") is False
    assert borrow_ten.applies_to("52-37") is False
    assert borrow_ten.applies_to("16-0") is False


def test_extract_params() -> None:
    params = borrow_ten.extract_params("16-9")
    assert params == {"a": 16, "b": 9}


def test_extract_params_sympy_recheck() -> None:
    """SymPy 复验：a-b == (10-b)+(a-10)（借十换一，总量不变）。"""
    for a, b in ((16, 9), (23, 8), (10, 7), (31, 6)):
        params = borrow_ten.extract_params(f"{a}-{b}")
        assert evaluate_expression(f"{a}-{b}") == evaluate_expression(
            f"(10-{b})+({a}-10)"
        )
        assert params == {"a": a, "b": b}


def test_extract_params_rejects_non_matching() -> None:
    with pytest.raises(ValueError):
        borrow_ten.extract_params("52-37")


def test_variants_all_valid_and_reverified() -> None:
    variants = borrow_ten.variants({"a": 16, "b": 9}, count=100)
    assert len(variants) == 100
    for v in variants:
        a, b = v["a"], v["b"]
        assert 10 <= a <= 99 and 1 <= b <= 9 and a % 10 < b
        assert evaluate_expression(f"{a}-{b}") == evaluate_expression(
            f"(10-{b})+({a}-10)"
        )
        assert (a, b) != (16, 9)


def test_build_produces_valid_v2_spec() -> None:
    spec = borrow_ten.build({"a": 16, "b": 9})
    assert isinstance(spec, LessonSpecV2)
    assert spec.lesson_id == "borrow-ten-16-minus-9"
    assert spec.verification.verified is True
    assert spec.verification.covered_claim_ids == ["arithmetic"]
    assert validate_activity_graph(spec) == []
    # 「先想后看」门槛存在（每个 predict 节点 require_attempt）
    gates = [n.gate.mode for n in spec.activity_graph if hasattr(n, "gate")]
    assert gates.count("require_attempt") == 5
    # 节点序列：拆十 → 减剩余 → 合并 → replay → 变式
    ids = [n.id for n in spec.activity_graph]
    assert ids == [
        "find-tens", "borrow-ten", "subtract-rest", "merge",
        "replay", "transfer-practice",
    ]


def test_build_answers_programmatically_computed() -> None:
    """答案全部由 SymPy 精确计算，不硬编码。"""
    spec = borrow_ten.build({"a": 23, "b": 8})
    by_id = {n.id: n for n in spec.activity_graph}
    assert by_id["borrow-ten"].response.expected == str(evaluate_expression("10-8"))
    assert by_id["subtract-rest"].response.expected == str(evaluate_expression("23-10"))
    assert by_id["merge"].response.expected == str(evaluate_expression("23-8"))
    assert by_id["transfer-practice"].response.expected == str(
        evaluate_expression("10-1")
    )  # variants 首个同族数对 10-1
    assert spec.verification.claims[0].status == "verified"


def test_misconceptions_present() -> None:
    ids = {m.id for m in borrow_ten.misconceptions}
    assert {"forget-borrow", "use-big-minus-small", "forget-remaining-tens"} <= ids
    assert all(m.description and m.distractor_hint for m in borrow_ten.misconceptions)


def test_spec_passes_teaching_policy() -> None:
    spec = borrow_ten.build({"a": 16, "b": 9})
    intent = analyze_intent({"kind": "problem", "content": "16-9"})
    issues = check_teaching_policy(spec, intent)
    assert not any("BLOCKER" in i for i in issues)


def test_filtered_projection_hides_unlocked_answers() -> None:
    """AGENTS 硬约束 1：未解锁节点 response.expected 必须为 None。"""
    spec_dict = borrow_ten.build({"a": 16, "b": 9}).model_dump(mode="json")
    filtered = filtered_spec(spec_dict, unlocked_ids=set())
    for node in filtered["activity_graph"]:
        if node["type"] == "predict":
            assert node["response"]["expected"] is None, node["id"]
            assert node.get("locked") is True, node["id"]
        if node["type"] == "observe":
            assert node["narration"] == "", node["id"]
    for claim in filtered["verification"]["claims"]:
        assert claim["statement"] == ""


def test_filtered_projection_reveals_only_unlocked() -> None:
    spec_dict = borrow_ten.build({"a": 16, "b": 9}).model_dump(mode="json")
    filtered = filtered_spec(spec_dict, unlocked_ids={"find-tens", "borrow-ten"})
    nodes = {n["id"]: n for n in filtered["activity_graph"]}
    assert nodes["find-tens"]["response"]["expected"] == "6"
    assert nodes["borrow-ten"]["response"]["expected"] == "1"
    assert nodes["merge"]["response"]["expected"] is None
    assert nodes["transfer-practice"]["response"]["expected"] is None


def test_fraction_recheck_helper_keeps_exactness() -> None:
    """分数精确性不回退（借用 SymPy 有理数，与 fraction 模板同原则）。"""
    assert evaluate_expression("1/2+1/4") == Rational(3, 4)
