"""等差数列求和策略模板（方法内置 · 第一批）。

方法：首项 a1、公差 d、项数 n → 末项 an=a1+(n-1)d；和=(a1+an)×n÷2。
答案程序计算 + SymPy 复验（和 = n×首项 + d×n(n-1)/2 等价式）。
"""

import re

from aiedu_core.models.lesson_v2 import (
    ClaimEvidence,
    Gate,
    LearningObjective,
    LessonSpecV2,
    ObserveNode,
    PredictNode,
    PresentationSpec,
    RenderSpec,
    ResponseNumber,
    TeachingDesign,
    Verification,
)
from aiedu_core.verify.evidence import VERIFIER_VERSION
from aiedu_core.verify.sympy_verify import evaluate_expression
from aiedu_core.strategies.base import GuidedStepTemplate, Misconception, StrategyTemplate

_PATTERN = re.compile(
    r"从\s*(\d{1,4})\s*开始\s*每次加\s*(\d{1,3})\s*[,，]?\s*(?:共|到第|的)?\s*(\d{1,3})\s*(?:个数|项|个)?"
)


def _parse(text: str) -> tuple[int, int, int] | None:
    m = _PATTERN.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _applies_to(problem_text: str) -> bool:
    p = _parse(problem_text)
    if p is None:
        return False
    a1, d, n = p
    return 1 <= a1 <= 9999 and 1 <= d <= 99 and 2 <= n <= 100


def _extract_params(problem_text: str) -> dict:
    p = _parse(problem_text)
    if p is None:
        raise ValueError(f"not an arithmetic-sequence problem: {problem_text!r}")
    a1, d, n = p
    last = int(evaluate_expression(f"{a1}+({n}-1)*{d}"))
    total = int(evaluate_expression(f"({a1}+{last})*{n}/2"))
    # SymPy 复验：等价公式 n×a1 + d×n(n-1)/2
    assert evaluate_expression(f"{n}*{a1}+{d}*{n}*({n}-1)/2") == total
    return {"a1": a1, "d": d, "n": n}


def _variants(params: dict, count: int = 10) -> list[dict]:
    a10, d0, n0 = params["a1"], params["d"], params["n"]
    out: list[dict] = []
    for a1 in range(1, 50):
        for d in range(1, 10):
            for n in range(2, 30):
                if (a1, d, n) == (a10, d0, n0):
                    continue
                out.append({"a1": a1, "d": d, "n": n})
                if len(out) >= count:
                    return out
    return out


MISCONCEPTIONS = (
    Misconception(
        id="count-off-by-one",
        description="末项公式漏掉 (n-1)：把第 n 项算成 a1+n×d。",
        distractor_hint="给出多乘一次公差的末项",
    ),
    Misconception(
        id="pair-sum",
        description="求和时忘记除以 2（配对思想未落地）。",
        distractor_hint="给出未除以 2 的双倍总和",
    ),
)

GUIDED_STEPS = (
    GuidedStepTemplate(
        id="find-last",
        prompt_template="第 {n} 项是多少？",
        assistance=("每项比前一项多 {d}，到第 {n} 项一共加了 {n-1} 次。",),
        distractors_from=("count-off-by-one",),
    ),
    GuidedStepTemplate(
        id="find-sum",
        prompt_template="首尾配对：(第一项+末项)×项数÷2，和是多少？",
        assistance=("首尾相加 = {a1}+{last}，这样的对数共有 {n} 对，再除以 2。",),
        distractors_from=("pair-sum",),
    ),
)


def _build(params: dict) -> LessonSpecV2:
    a1, d, n = params["a1"], params["d"], params["n"]
    last = int(evaluate_expression(f"{a1}+({n}-1)*{d}"))
    total = int(evaluate_expression(f"({a1}+{last})*{n}/2"))
    claim = ClaimEvidence(
        id="arithmetic",
        statement=f"从{a1}起每次加{d}共{n}项：末项{last}，和{total}（({a1}+{last})×{n}÷2）",
        status="verified",
        method="精确计算",
    )
    nodes = [
        PredictNode(
            type="predict",
            id="find-last",
            prompt=f"从 {a1} 开始每次加 {d}，第 {n} 项是多少？",
            response=ResponseNumber(kind="number", expected=str(last)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"第 {n} 项 = {a1} + ({n}-1)×{d}。",),
            distractors_from=("count-off-by-one",),
            next_ids=["find-sum"],
        ),
        PredictNode(
            type="predict",
            id="find-sum",
            prompt=f"这 {n} 个数的和是多少？（首尾配对：({a1}+{last})×{n}÷2）",
            response=ResponseNumber(kind="number", expected=str(total)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"首尾两项之和相等，共 {n} 对；和 = ({a1}+{last})×{n}÷2。",),
            distractors_from=("pair-sum",),
            next_ids=["replay"],
        ),
        ObserveNode(
            type="observe",
            id="replay",
            narration=(
                f"完整演示：末项 an=a1+(n-1)d={a1}+({n}-1)×{d}={last}；"
                f"和=(a1+an)×n÷2=({a1}+{last})×{n}÷2={total}。"
            ),
            next_ids=["transfer-practice"],
        ),
        PredictNode(
            type="predict",
            id="transfer-practice",
            prompt="试试：从 2 开始每次加 3，共 9 个数，和是多少？",
            response=ResponseNumber(kind="number", expected=str(int(evaluate_expression("(2+2+8*3)*9/2")))),
            gate=Gate(mode="require_attempt"),
            assistance=("先求末项（第9项=2+8×3），再首尾配对求和。",),
            next_ids=["__end__"],
        ),
    ]
    return LessonSpecV2(
        lesson_id=f"arith-seq-{a1}-d{d}-n{n}",
        revision=1,
        teaching_request={"kind": "problem", "content": f"从{a1}开始每次加{d}共{n}项求和"},
        curriculum_context={"stage": "primary", "grade": 4},
        learning_objectives=[
            LearningObjective(id="lo-arith-seq", description=f"等差数列求和（a1={a1},d={d},n={n}）")
        ],
        teaching_design=TeachingDesign(modes=["引导"], strategy_refs=["arithmetic_sequence@0.1.0"]),
        verification=Verification(
            verified=True,
            verifier_version=VERIFIER_VERSION,
            normalized_problem_hash=None,
            claims=[claim],
            covered_claim_ids=["arithmetic"],
        ),
        activity_graph=nodes,
        assessment=[{"id": "assess-seq", "objective_refs": ["lo-arith-seq"], "evidence_kind": "numeric_answer"}],
        render=RenderSpec(runtime_version="0.1.0"),
        presentation=PresentationSpec(age_band="upper_primary", visual_theme="clean_school"),
    )


arithmetic_sequence = StrategyTemplate(
    id="arithmetic_sequence",
    version="0.1.0",
    applies_to=_applies_to,
    extract_params=_extract_params,
    guided_steps=GUIDED_STEPS,
    variants=_variants,
    misconceptions=MISCONCEPTIONS,
    build_fn=_build,
)
