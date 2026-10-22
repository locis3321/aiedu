"""T3 测试：受限 SymPy 核验服务。"""

import pytest
from sympy import Rational

from app.services import math_verify
from app.services.evidence import VERIFIER_VERSION, VerificationRecord
from app.services.sympy_verify import (
    UnsafeExpressionError,
    evaluate_expression,
    verify_arithmetic,
    verify_expression,
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
