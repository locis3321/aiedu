"""D3–D4 测试：分数等分概念策略模板。"""

import pytest
from sympy import Rational

from aiedu_core.intent import analyze_intent
from aiedu_core.models.filtering import filtered_spec
from aiedu_core.models.lesson_v2 import LessonSpecV2
from aiedu_core.models.semantics import validate_activity_graph
from aiedu_core.policy import check_teaching_policy
from aiedu_core.strategies import fraction_equal_parts
from aiedu_core.verify.sympy_verify import evaluate_expression


def test_applies_to() -> None:
    # 概念型等分输入（来自 teaching-skills examples 的表述）
    assert fraction_equal_parts.applies_to("一块披萨平均分成4份，取其中1份") is True
    assert fraction_equal_parts.applies_to("把一个蛋糕平均分成4份，取1份是多少？") is True
    assert fraction_equal_parts.applies_to("平均分成6份，取其中2份") is True
    # 明确不匹配：分数四则运算 / 开放性概念请求（走 LLM 或能力缺口）
    assert fraction_equal_parts.applies_to("1/2+1/4") is False
    assert fraction_equal_parts.applies_to("理解分数的意义") is False
    assert fraction_equal_parts.applies_to("16-9") is False


def test_extract_params() -> None:
    assert fraction_equal_parts.extract_params("一块披萨平均分成4份，取其中1份") == {
        "n": 4,
        "m": 1,
    }
    assert fraction_equal_parts.extract_params("平均分成6份，取其中2份") == {
        "n": 6,
        "m": 2,
    }
    # 未写明取几份 → 默认取 1 份（unit fraction）
    assert fraction_equal_parts.extract_params("把一块蛋糕平均分成3份") == {
        "n": 3,
        "m": 1,
    }


def test_extract_params_sympy_recheck() -> None:
    """SymPy 复验：取 m 份 = m/n（精确有理数，无浮点误差）。"""
    params = fraction_equal_parts.extract_params("平均分成6份，取其中2份")
    assert evaluate_expression(f"{params['m']}/{params['n']}") == Rational(1, 3)


def test_extract_params_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        fraction_equal_parts.extract_params("平均分成1份，取其中1份")  # n 需 >=2
    with pytest.raises(ValueError):
        fraction_equal_parts.extract_params("平均分成13份，取其中1份")  # n 需 <=12


def test_out_of_range_applies_to_false() -> None:
    assert fraction_equal_parts.applies_to("平均分成13份，取其中1份") is False
    assert fraction_equal_parts.applies_to("平均分成2份，取其中2份") is False  # m<n


def test_variants_all_valid() -> None:
    variants = fraction_equal_parts.variants({"n": 4, "m": 1}, count=20)
    assert len(variants) == 20
    for v in variants:
        n, m = v["n"], v["m"]
        assert 2 <= n <= 12 and 1 <= m < n
        assert evaluate_expression(f"{m}/{n}") == Rational(m, n)
        assert (n, m) != (4, 1)


def test_build_produces_valid_v2_spec() -> None:
    spec = fraction_equal_parts.build({"n": 4, "m": 1})
    assert isinstance(spec, LessonSpecV2)
    assert spec.lesson_id == "fraction-equal-parts-1-over-4"
    assert spec.teaching_request.kind == "concept"
    assert spec.verification.verified is True
    assert validate_activity_graph(spec) == []
    gates = [n.gate.mode for n in spec.activity_graph if hasattr(n, "gate")]
    assert gates.count("require_attempt") >= 3


def test_build_answers_programmatically_computed() -> None:
    """分母/分子/分数答案由程序计算（不硬编码、不由 LLM 猜）。"""
    spec = fraction_equal_parts.build({"n": 6, "m": 2})
    by_id = {n.id: n for n in spec.activity_graph}
    assert by_id["find-denominator"].response.expected == "6"
    assert by_id["find-numerator"].response.expected == "2"
    name = by_id["name-fraction"].response
    assert name.options[0] == "2/6" and name.correct_index == 0
    compare = by_id["compare-unit"].response
    assert compare.options[compare.correct_index] == "1/6"  # 份数少 → 每份大
    assert spec.verification.claims[0].statement == "取2份=整体的2/6（2/6 = 1/3）"


def test_misconceptions_present() -> None:
    ids = {m.id for m in fraction_equal_parts.misconceptions}
    assert {
        "swap-numerator-denominator",
        "not-equal-parts",
        "bigger-denominator-bigger-piece",
    } <= ids


def test_spec_passes_teaching_policy() -> None:
    spec = fraction_equal_parts.build({"n": 4, "m": 1})
    intent = analyze_intent(
        {"kind": "concept", "content": "一块披萨平均分成4份，取其中1份"}
    )
    issues = check_teaching_policy(spec, intent)
    assert not any("BLOCKER" in i for i in issues)


def test_filtered_projection_hides_unlocked_answers() -> None:
    """AGENTS 硬约束 1：未解锁节点 response.expected/correct_index 必须为 None。"""
    spec_dict = fraction_equal_parts.build({"n": 4, "m": 1}).model_dump(mode="json")
    filtered = filtered_spec(spec_dict, unlocked_ids=set())
    for node in filtered["activity_graph"]:
        if node.get("response"):
            assert node["response"].get("expected") is None, node["id"]
            assert node["response"].get("correct_index") is None, node["id"]
            assert node.get("locked") is True, node["id"]
        if node["type"] == "observe":
            assert node["narration"] == "", node["id"]
    for claim in filtered["verification"]["claims"]:
        assert claim["statement"] == ""


def test_filtered_projection_reveals_only_unlocked() -> None:
    spec_dict = fraction_equal_parts.build({"n": 4, "m": 1}).model_dump(mode="json")
    filtered = filtered_spec(
        spec_dict, unlocked_ids={"find-denominator", "find-numerator"}
    )
    nodes = {n["id"]: n for n in filtered["activity_graph"]}
    assert nodes["find-denominator"]["response"]["expected"] == "4"
    assert nodes["find-numerator"]["response"]["expected"] == "1"
    assert nodes["name-fraction"]["response"]["correct_index"] is None
