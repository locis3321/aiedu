"""按主张类型路由的数学验证器注册表。

R2 §9：验证器按主张类型路由，不能统一为「SymPy 算出同一答案」：
- 代数：检查定义域与等价；
- 几何：检查构造约束及定理前提；
- 函数：区分采样可视化与全称性质；
- 统计：区分模拟结果与理论结论；
- 证明：检查前提、量词和推导依赖。

本模块先落地 arithmetic；其余领域显式标记能力缺口（返回 None），
不假装已经覆盖全部 K12。
"""

from typing import Protocol

from app.services.evidence import ClaimEvidenceData


class MathVerifier(Protocol):
    domain: str
    verifier_version: str

    def verify(self, claim_id: str, statement: str) -> ClaimEvidenceData:
        """返回 verified / refuted / inconclusive / requires_review 证据。"""
        ...


class ArithmeticVerifier:
    """数与运算验证器：精确计算（整数/Fraction），经受限解析。"""

    domain = "arithmetic"
    verifier_version = "0.1.0"

    def verify(self, claim_id: str, statement: str) -> ClaimEvidenceData:
        from app.services.sympy_verify import verify_arithmetic

        record = verify_arithmetic(statement)
        claim = record.claims[0]
        return ClaimEvidenceData(
            id=claim_id,
            statement=claim.statement,
            status=claim.status,
            method=claim.method,
        )


VERIFIERS: dict[str, MathVerifier] = {
    ArithmeticVerifier.domain: ArithmeticVerifier(),
}


def get_verifier(domain: str) -> MathVerifier | None:
    """按领域取验证器；未注册领域返回 None（能力缺口，显式标记）。"""
    return VERIFIERS.get(domain)


def available_domains() -> list[str]:
    return sorted(VERIFIERS)
