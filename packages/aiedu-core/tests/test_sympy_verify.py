"""T3 测试：受限 SymPy 核验服务（含乘除法写法归一化扩展）。"""

import pytest
from sympy import Rational, Symbol

from aiedu_core.verify import math_verify
from aiedu_core.verify.evidence import VERIFIER_VERSION, VerificationRecord
from aiedu_core.verify.sympy_verify import (
    UnsafeExpressionError,
    evaluate_expression,
    normalize_expr_text,
    verify_arithmetic,
    verify_expression,
    verify_math,
)


def test_verify_arithmetic_16_plus_8() -> None:
    record = verify_arithmetic("16+8")
    assert record.result == "verified"
    assert record.covered_claim_ids == ("arithmetic",)
    assert evaluate_expression("16+8") == 24


def test_fraction_exactness() -> None:
    """分数精确计算，不出现浮点误差。"""
    record = verify_expression("1/3+1/6", "1/2")
    assert record.result == "verified"
    assert evaluate_expression("1/3+1/6") == Rational(1, 2)


def test_refuted_expression() -> None:
    record = verify_expression("2+2", "5")
    assert record.result == "refuted"


@pytest.mark.parametrize(
    "payload",
    [
        "__import__('os').system('dir')",
        "open('x')",
        "x.__class__",
        "(lambda: 1)()",
        "[i for i in range(3)]",
        "import os",
        "x.y",
    ],
)
def test_injection_rejected(payload: str) -> None:
    with pytest.raises((UnsafeExpressionError, SyntaxError)):
        evaluate_expression(payload)


def test_disallowed_name_rejected() -> None:
    with pytest.raises(UnsafeExpressionError):
        evaluate_expression("evil_var + 1")


def test_hash_invalidated_by_verifier_version() -> None:
    """verifier_version 变更 → content_hash 不同（缓存失效语义）。"""
    record = verify_arithmetic("16+8")
    changed = VerificationRecord(
        verifier_version="0.2.0",
        normalized_problem_hash=record.normalized_problem_hash,
        assumptions=record.assumptions,
        claims=record.claims,
        covered_claim_ids=record.covered_claim_ids,
        result=record.result,
    )
    assert record.content_hash() != changed.content_hash()
    assert VERIFIER_VERSION == record.verifier_version


def test_math_verify_registry() -> None:
    assert math_verify.get_verifier("arithmetic") is not None
    # 未注册领域显式返回 None（能力缺口），不假装覆盖
    assert math_verify.get_verifier("geometry") is None


# ---------------------------------------------------------------------------
# 乘除法与写法归一化（D1-D2 verify 域扩展：7x8 / 7×8 / 7·8 / 56÷7）
# ---------------------------------------------------------------------------

def test_normalize_expr_text() -> None:
    assert normalize_expr_text("7x8") == "7*8"
    assert normalize_expr_text("7×8") == "7*8"
    assert normalize_expr_text("7·8") == "7*8"
    assert normalize_expr_text("56÷7") == "56/7"
    assert normalize_expr_text("2x+3") == "2x+3"  # 变量 x 不归一化


@pytest.mark.parametrize("expr", ["7x8", "7×8", "7·8", "7*8", "7 x 8"])
def test_multiplication_written_variants(expr: str) -> None:
    record = verify_arithmetic(expr)
    assert record.result == "verified"
    assert evaluate_expression(expr) == 56


def test_variable_x_not_treated_as_multiplication() -> None:
    """x 单独作为变量（两侧非数字）仍按符号解析，不被归一化为乘号。"""
    expr = evaluate_expression("x+1")
    assert expr.free_symbols == {Symbol("x")}


def test_division_normalized() -> None:
    record = verify_arithmetic("56÷7")
    assert record.result == "verified"
    assert evaluate_expression("56÷7") == 8


def test_verify_math_matches_expected() -> None:
    record = verify_math("7x8", 56)
    assert record.result == "verified"
    assert record.covered_claim_ids == ("arithmetic-eq",)
    assert record.claims[0].status == "verified"


def test_verify_math_refuted() -> None:
    record = verify_math("7x8", 57)
    assert record.result == "refuted"


def test_verify_math_string_expected() -> None:
    record = verify_math("56÷7", "8")
    assert record.result == "verified"


def test_verify_math_invalid_expression_review() -> None:
    """无法解析的输入显式 requires_review，不猜测。"""
    record = verify_math("__import__('os')", 1)
    assert record.result == "requires_review"
