"""方法模板批量测试（和差倍 / 鸡兔同笼 / 等差数列）：参数、复验、变式、语义、filtered、policy。"""

import pytest

from aiedu_core.models.filtering import filtered_spec
from aiedu_core.models.semantics import validate_activity_graph
from aiedu_core.policy import check_teaching_policy
from aiedu_core.strategies import arithmetic_sequence, chicken_rabbit, sum_diff
from aiedu_core.verify.sympy_verify import evaluate_expression

TEMPLATES = [sum_diff, chicken_rabbit, arithmetic_sequence]


@pytest.mark.parametrize(
    "text,params",
    [
        ("两个数的和是 18，差是 4", {"s": 18, "d": 4}),
        ("和是 33，差是 5", {"s": 33, "d": 5}),
    ],
)
def test_sum_diff_params(text, params) -> None:
    assert sum_diff.extract_params(text) == params


@pytest.mark.parametrize(
    "text,params",
    [
        ("鸡兔同笼，共10个头，28条腿", {"h": 10, "f": 28}),
        ("鸡兔同笼 20个头 56只脚", {"h": 20, "f": 56}),
    ],
)
def test_chicken_rabbit_params(text, params) -> None:
    assert chicken_rabbit.extract_params(text) == params


@pytest.mark.parametrize(
    "text,params",
    [
        ("从 5 开始每次加 3，共 8 个数", {"a1": 5, "d": 3, "n": 8}),
        ("从2开始每次加4到第6个", {"a1": 2, "d": 4, "n": 6}),
    ],
)
def test_arithmetic_sequence_params(text, params) -> None:
    assert arithmetic_sequence.extract_params(text) == params


def test_not_applicable() -> None:
    assert sum_diff.applies_to("两个数的和是 18，差是 4") is True
    assert sum_diff.applies_to("和是 10，差是 3") is False  # 奇偶不一致
    assert sum_diff.applies_to("和是 3，差是 5") is False   # 和小于差
    assert chicken_rabbit.applies_to("鸡兔同笼，共10个头，28条腿") is True
    assert chicken_rabbit.applies_to("鸡兔同笼，共10个头，50条腿") is False  # 超出范围
    assert arithmetic_sequence.applies_to("从 5 开始每次加 3，共 8 个数") is True
    assert arithmetic_sequence.applies_to("16+8") is False


def test_sympy_recheck_in_extract() -> None:
    for tpl, cases in [
        (sum_diff, [("两个数的和是 18，差是 4", 18, 4)]),
        (chicken_rabbit, [("鸡兔同笼，共10个头，28条腿", 10, 28)]),
        (arithmetic_sequence, [("从 5 开始每次加 3，共 8 个数", 5, 3, 8)]),
    ]:
        for case in cases[:1]:
            tpl.extract_params(case[0])  # 内部断言即复验；不抛即过


def test_variants_valid() -> None:
    for tpl, params, check in [
        (sum_diff, {"s": 18, "d": 4}, lambda p: p["s"] > p["d"] and (p["s"] - p["d"]) % 2 == 0),
        (chicken_rabbit, {"h": 10, "f": 28}, lambda p: 2 * p["h"] < p["f"] < 4 * p["h"] and p["f"] % 2 == 0),
        (arithmetic_sequence, {"a1": 5, "d": 3, "n": 8}, lambda p: p["n"] >= 2),
    ]:
        vs = tpl.variants(params, count=20)
        assert len(vs) == 20
        for v in vs:
            assert check(v), v


def test_builds_valid_spec_and_answers_computed() -> None:
    spec = sum_diff.build({"s": 18, "d": 4})
    assert validate_activity_graph(spec) == []
    assert spec.verification.verified is True
    # 答案程序计算：18/4 → 11/7
    nodes = {n.id: n for n in spec.activity_graph}
    assert nodes["find-big"].response.expected == "11"
    assert nodes["find-small"].response.expected == "7"

    spec = chicken_rabbit.build({"h": 10, "f": 28})
    assert validate_activity_graph(spec) == []
    nodes = {n.id: n for n in spec.activity_graph}
    assert nodes["extra-feet"].response.expected == "4"
    assert nodes["find-chickens"].response.expected == "6"

    spec = arithmetic_sequence.build({"a1": 5, "d": 3, "n": 8})
    assert validate_activity_graph(spec) == []
    nodes = {n.id: n for n in spec.activity_graph}
    assert nodes["find-last"].response.expected == "26"
    assert nodes["find-sum"].response.expected == "124"


def test_spec_passes_policy() -> None:
    for tpl, params in [
        (sum_diff, {"s": 18, "d": 4}),
        (chicken_rabbit, {"h": 10, "f": 28}),
        (arithmetic_sequence, {"a1": 5, "d": 3, "n": 8}),
    ]:
        spec = tpl.build(params)
        assert not any("BLOCKER" in i for i in check_teaching_policy(spec))


def test_filtered_projection_hides_answers() -> None:
    """硬约束 1：未解锁节点 expected 必须为 None。"""
    for tpl, params in [
        (sum_diff, {"s": 18, "d": 4}),
        (chicken_rabbit, {"h": 10, "f": 28}),
        (arithmetic_sequence, {"a1": 5, "d": 3, "n": 8}),
    ]:
        spec_dict = tpl.build(params).model_dump(mode="json")
        filtered = filtered_spec(spec_dict, set())
        for node in filtered["activity_graph"]:
            if node["type"] == "predict":
                assert node["response"]["expected"] is None, f"{tpl.id}:{node['id']}"
            if node["type"] == "observe":
                assert node["narration"] == ""
        for claim in filtered["verification"]["claims"]:
            assert claim["statement"] == ""
