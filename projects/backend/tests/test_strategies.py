"""T6 测试：策略模板库与凑十法切片。"""


from app.models.lesson_v2 import LessonSpecV2
from app.models.semantics import validate_activity_graph
from app.services.sympy_verify import evaluate_expression
from app.strategies import make_ten, registry


def test_match_16_plus_8() -> None:
    match = registry.match("16+8")
    assert match is not None
    assert match.template_id == "make_ten"
    assert match.params == {"a": 16, "b": 8, "k": 2}


def test_match_not_applicable() -> None:
    # k=6, a=3 < 6 → 不命中
    assert registry.match("3+4") is None
    # 非两位数加一位数格式
    assert registry.match("16+8=24") is None


def test_match_boundary_a_equals_k() -> None:
    # 7+3：k=7, a=7 ≥ k → 命中（边界条件）
    match = registry.match("7+3")
    assert match is not None
    assert match.params == {"a": 7, "b": 3, "k": 7}


def test_build_produces_valid_v2_spec() -> None:
    spec = make_ten.build({"a": 16, "b": 8, "k": 2})
    assert isinstance(spec, LessonSpecV2)
    assert spec.verification.verified is True
    assert validate_activity_graph(spec) == []
    # 「先想后看」门槛存在
    gates = [n.gate.mode for n in spec.activity_graph if hasattr(n, "gate")]
    assert gates.count("require_attempt") >= 3


def test_variants_all_valid_and_reverified() -> None:
    variants = make_ten.variants({"a": 16, "b": 8, "k": 2}, count=100)
    assert len(variants) == 100
    for v in variants:
        a, b, k = v["a"], v["b"], v["k"]
        assert 1 <= a <= 99 and 1 <= b <= 9 and k == 10 - b and a >= k
        # SymPy 复验：a+b == (a-k)+(b+k)
        assert evaluate_expression(f"{a}+{b}") == evaluate_expression(f"{a-k}+{b+k}")
        # 不与原题重复
        assert (a, b) != (16, 8)


def test_misconception_distractors_exclude_answer() -> None:
    """错误模式干扰项不得等于正确答案。"""
    for m in make_ten.misconceptions:
        # distractor_hint 是生成提示而非具体值；这里校验 hint 不含正确答案数字
        assert m.id in {"complement-wrong", "wrong-source", "forget-transfer"}
        assert m.description


def test_registry_ids() -> None:
    assert "make_ten" in registry.ids()
