"""verify 域：SymPy 受限 AST 核验 + 核验凭据生成。

- evidence.py：核验凭据模型（VerificationRecord / ClaimEvidenceData / content_hash）；
- sympy_verify.py：受限解析 + 精确计算；
- math_verify.py：按主张类型路由的验证器注册表（未注册领域显式能力缺口）。
"""

from aiedu_core.verify.evidence import (
    VERIFIER_VERSION,
    ClaimEvidenceData,
    VerificationRecord,
    normalize_problem,
)
from aiedu_core.verify.math_verify import available_domains, get_verifier
from aiedu_core.verify.sympy_verify import (
    UnsafeExpressionError,
    evaluate_expression,
    normalize_expr_text,
    parse_math_expr,
    verify_arithmetic,
    verify_expression,
    verify_math,
)

__all__ = [
    "VERIFIER_VERSION",
    "ClaimEvidenceData",
    "VerificationRecord",
    "normalize_problem",
    "available_domains",
    "get_verifier",
    "UnsafeExpressionError",
    "evaluate_expression",
    "normalize_expr_text",
    "parse_math_expr",
    "verify_arithmetic",
    "verify_expression",
    "verify_math",
]
