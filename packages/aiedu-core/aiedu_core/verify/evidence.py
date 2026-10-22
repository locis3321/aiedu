"""核验证据模型：服务端核验器生成的凭据。

R2 §9：验证凭据包括 normalized_problem、assumptions、strategy_version、claims、
action_graph、unit_rules 的规范化哈希，verifier_version、covered_claim_ids、
结果和报告引用。LLM 的 verified=true 不具备发布权限。
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

VERIFIER_VERSION = "0.1.0"


@dataclass(frozen=True)
class ClaimEvidenceData:
    """单条数学主张的核验证据。"""

    id: str
    statement: str
    status: Literal["verified", "refuted", "inconclusive", "requires_review"]
    method: str


@dataclass(frozen=True)
class VerificationRecord:
    """核验凭据；content_hash 含 verifier_version，版本变更即失效。"""

    verifier_version: str
    normalized_problem_hash: str | None
    assumptions: tuple[str, ...]
    claims: tuple[ClaimEvidenceData, ...]
    covered_claim_ids: tuple[str, ...]
    result: Literal["verified", "refuted", "inconclusive", "requires_review"]
    report_ref: str | None = None

    def content_hash(self) -> str:
        payload = {
            "verifier_version": self.verifier_version,
            "normalized_problem_hash": self.normalized_problem_hash,
            "assumptions": list(self.assumptions),
            "claims": [
                {
                    "id": c.id,
                    "statement": c.statement,
                    "status": c.status,
                    "method": c.method,
                }
                for c in self.claims
            ],
            "covered_claim_ids": list(self.covered_claim_ids),
            "result": self.result,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_problem(text: str) -> str:
    """规范化题目文本（去空白）；作为哈希输入。"""
    return " ".join(text.split())
