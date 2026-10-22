"""和差倍问题策略模板（方法内置 · 第一批）。

方法：已知两数和 S 与差 D → 大数=(S+D)/2，小数=(S-D)/2。
全部答案由程序计算并经 SymPy 断言核验（不硬编码、不由 LLM 猜）。
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

_PATTERN = re.compile(r"和是\s*(\d{1,6})\s*，?\s*差是\s*(\d{1,6})")


def _parse(text: str) -> tuple[int, int] | None:
    m = _PATTERN.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _applies_to(problem_text: str) -> bool:
    parsed = _parse(problem_text)
    if parsed is None:
        return False
    s, d = parsed
    # 两数之和与差同奇偶（整数解前提），且和 > 差（两数均正）
    return s > d and (s - d) % 2 == 0


def _extract_params(problem_text: str) -> dict:
    parsed = _parse(problem_text)
    if parsed is None:
        raise ValueError(f"not a sum-diff problem: {problem_text!r}")
    s, d = parsed
    big = int(evaluate_expression(f"({s}+{d})/2"))
    small = int(evaluate_expression(f"({s}-{d})/2"))
    # SymPy 复验：大数+小数==和 且 大数-小数==差
    assert evaluate_expression(f"{small}+{big}") == s
    assert evaluate_expression(f"{big}-{small}") == d
    return {"s": s, "d": d}


def _variants(params: dict, count: int = 10) -> list[dict]:
    s0, d0 = params["s"], params["d"]
    out: list[dict] = []
    for s in range(6, 200):
        for d in range(1, s):
            if (s - d) % 2 != 0:
                continue
            if (s, d) == (s0, d0):
                continue
            out.append({"s": s, "d": d})
            if len(out) >= count:
                return out
    return out


MISCONCEPTIONS = (
    Misconception(
        id="big-plus-small-mix",
        description="把(和+差)/2 当成小数；大数/小数角色颠倒。",
        distractor_hint="给出两数顺序颠倒的错误结果",
    ),
    Misconception(
        id="parity-overlook",
        description="不检查和与差同奇偶就硬除，出现非整数。",
        distractor_hint="给出未检查奇偶的直接除法结果",
    ),
)

GUIDED_STEPS = (
    GuidedStepTemplate(
        id="find-big",
        prompt_template="两数和是 {s}，差是 {d}，(和+差)÷2 得到的是哪个数？",
        assistance=("把大的数再多给一份，两个数就一样大了。",),
        distractors_from=("big-plus-small-mix",),
    ),
    GuidedStepTemplate(
        id="find-small",
        prompt_template="大的数是 {big}，小的数是 {small} 吗？怎么验证？",
        assistance=("用 大数−差 或 和−大数 检查。",),
        distractors_from=("parity-overlook",),
    ),
)


def _build(params: dict) -> LessonSpecV2:
    s, d = params["s"], params["d"]
    big = int(evaluate_expression(f"({s}+{d})/2"))
    small = int(evaluate_expression(f"({s}-{d})/2"))
    claim = ClaimEvidence(
        id="arithmetic",
        statement=f"和{s}差{d}→大数{big}、小数{small}（{small}+{big}={s}，{big}-{small}={d}）",
        status="verified",
        method="精确计算",
    )
    nodes = [
        PredictNode(
            type="predict",
            id="find-big",
            prompt=f"两个数，和是 {s}，差是 {d}。(和+差)÷2 等于多少？",
            response=ResponseNumber(kind="number", expected=str(big)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"把大的数补一份给小的数，就和差补齐成两个大数：({s}+{d})÷2。",),
            next_ids=["find-small"],
        ),
        PredictNode(
            type="predict",
            id="find-small",
            prompt=f"大的数是 {big}，用和或差求小数：和−大数 = ?",
            response=ResponseNumber(kind="number", expected=str(small)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"小数 = 和 − 大数 = {s} − {big}。",),
            distractors_from=("parity-overlook",),
            next_ids=["replay"],
        ),
        ObserveNode(
            type="observe",
            id="replay",
            narration=(
                f"完整演示：大数=(和+差)÷2=({s}+{d})÷2={big}；小数=和−大数={s}−{big}={small}。"
                f"验证：{big}+{small}={s}、{big}-{small}={d}。"
            ),
            next_ids=["__end__"],
        ),
    ]
    return LessonSpecV2(
        lesson_id=f"sum-diff-{s}-d{d}",
        revision=1,
        teaching_request={"kind": "problem", "content": f"两数和为{s}，差为{d}"},
        curriculum_context={"stage": "primary", "grade": 3},
        learning_objectives=[
            LearningObjective(id="lo-sum-diff", description=f"用和差关系求两数（和{s}差{d}）")
        ],
        teaching_design=TeachingDesign(modes=["引导"], strategy_refs=["sum_diff@0.1.0"]),
        verification=Verification(
            verified=True,
            verifier_version=VERIFIER_VERSION,
            normalized_problem_hash=None,
            claims=[claim],
            covered_claim_ids=["arithmetic"],
        ),
        activity_graph=nodes,
        assessment=[{"id": "assess-sum-diff", "objective_refs": ["lo-sum-diff"], "evidence_kind": "numeric_answer"}],
        render=RenderSpec(runtime_version="0.1.0"),
        presentation=PresentationSpec(age_band="upper_primary", visual_theme="clean_school"),
    )


sum_diff = StrategyTemplate(
    id="sum_diff",
    version="0.1.0",
    applies_to=_applies_to,
    extract_params=_extract_params,
    guided_steps=GUIDED_STEPS,
    variants=_variants,
    misconceptions=MISCONCEPTIONS,
    build_fn=_build,
)
