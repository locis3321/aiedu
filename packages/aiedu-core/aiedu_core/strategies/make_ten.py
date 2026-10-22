"""凑十法策略模板（第一个切片）。

R2 §6 运行示例：领域状态只存 left/right/transferred/phase；步骤为
找补数→找来源→求新和→回放→迁移练习；适用条件 a为1~99正整数、b为1~9整数、
k=10-b且a≥k；本切片固定把第二个加数凑到10。
"""

import re

from aiedu_core.models.lesson_v2 import (
    ClaimEvidence,
    DomainModelDef,
    Gate,
    LearningObjective,
    LessonSpecV2,
    ObserveNode,
    OperationDef,
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

_PATTERN = re.compile(r"^\s*(\d{1,2})\s*\+\s*(\d)\s*$")


def _parse(text: str) -> tuple[int, int] | None:
    m = _PATTERN.match(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _applies_to(problem_text: str) -> bool:
    parsed = _parse(problem_text)
    if parsed is None:
        return False
    a, b = parsed
    k = 10 - b
    return 1 <= a <= 99 and 1 <= b <= 9 and a >= k


def _extract_params(problem_text: str) -> dict:
    parsed = _parse(problem_text)
    if parsed is None:
        raise ValueError(f"not a make-ten problem: {problem_text!r}")
    a, b = parsed
    k = 10 - b
    # SymPy 程序化复验参数与结果（不由 LLM 猜）
    assert evaluate_expression(f"{a}+{b}") == evaluate_expression(f"{a-k}+{b+k}")
    return {"a": a, "b": b, "k": k}


def _variants(params: dict, count: int = 10) -> list[dict]:
    """程序化生成满足同一适用条件的新数对（排除当前数对）。"""
    a0, b0 = params["a"], params["b"]
    out: list[dict] = []
    for b in range(1, 10):
        k = 10 - b
        for a in range(max(k, 11), 100):
            if (a, b) == (a0, b0):
                continue
            out.append({"a": a, "b": b, "k": k})
            if len(out) >= count:
                return out
    return out


MISCONCEPTIONS = (
    Misconception(
        id="complement-wrong",
        description="补数算错：把10-b算成b或其它值",
        distractor_hint="用与正确答案不同的补数值",
    ),
    Misconception(
        id="wrong-source",
        description="从错误的加数拆：从b拆而不是从a拆",
        distractor_hint="选择从较小的加数拆出的方案",
    ),
    Misconception(
        id="forget-transfer",
        description="拆完忘记更新总和：仍按原数相加",
        distractor_hint="给出未转移的总和作为干扰项",
    ),
)

GUIDED_STEPS = (
    GuidedStepTemplate(
        id="find-complement",
        prompt_template="{b}加几凑成10？",
        assistance=("想想10的补数：10-{b}=?",),
        distractors_from=("complement-wrong",),
    ),
    GuidedStepTemplate(
        id="find-source",
        prompt_template="从{a}里拆出{k}给{b}，{a}变成几？",
        assistance=("拆出的{k}要加到{b}那边去。",),
        on_correct_actions=("arithmetic.transfer_units",),
        distractors_from=("wrong-source",),
    ),
    GuidedStepTemplate(
        id="find-sum",
        prompt_template="现在两堆合起来是多少？",
        assistance=("先看{a-k}和{b+k}分别是多少，再相加。",),
        on_correct_actions=("arithmetic.group_total",),
        distractors_from=("forget-transfer",),
    ),
)


def _build(params: dict) -> LessonSpecV2:
    a, b, k = params["a"], params["b"], params["k"]
    total = int(evaluate_expression(f"{a}+{b}"))
    claim = ClaimEvidence(
        id="arithmetic",
        statement=f"{a}+{b}={total}（凑十：{a-k}+{b+k}={total}）",
        status="verified",
        method="精确计算",
    )
    nodes = [
        PredictNode(
            type="predict",
            id="find-complement",
            prompt=f"小兔想装满一篮10颗莓果，它现在有{b}颗，还差几颗？",
            response=ResponseNumber(kind="number", expected=str(10 - b)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"想想10的补数：10-{b}=?",),
            next_ids=["find-source"],
        ),
        PredictNode(
            type="predict",
            id="find-source",
            prompt=f"小熊有{a}颗莓果，借给谁、借几颗，能让小兔凑满一篮10颗？",
            response=ResponseNumber(kind="number", expected=str(k)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"拆出的{k}颗要搬到小兔那边去。",),
            on_correct=["arithmetic.transfer_units"],
            next_ids=["find-sum"],
        ),
        PredictNode(
            type="predict",
            id="find-sum",
            prompt="现在两篮莓果合起来是多少颗？",
            response=ResponseNumber(kind="number", expected=str(total)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"先看{a-k}和{b+k}分别是多少，再合起来。",),
            on_correct=["arithmetic.group_total"],
            next_ids=["replay"],
        ),
        ObserveNode(
            type="observe",
            id="replay",
            narration=(
                f"完整演示：小熊把{k}颗莓果搬给小兔，变成{a-k}+{b+k}={total}。"
                "这就是凑十法——先把一个加数凑成整十，再加剩下的。"
            ),
            next_ids=["transfer-practice"],
        ),
        PredictNode(
            type="predict",
            id="transfer-practice",
            prompt="试试这题：27+6怎么算？（先自己想一想）",
            response=ResponseNumber(kind="number", expected=str(27 + 6)),
            gate=Gate(mode="require_attempt"),
            assistance=("6的补数是4，从27里拆出4。",),
            next_ids=["__end__"],
        ),
    ]
    return LessonSpecV2(
        lesson_id=f"make-ten-{a}-plus-{b}",
        revision=1,
        teaching_request={"kind": "problem", "content": f"{a}+{b}"},
        curriculum_context={"stage": "primary", "grade": 1},
        learning_objectives=[
            LearningObjective(id="lo-make-ten", description=f"用凑十法计算{a}+{b}")
        ],
        domain_models=[
            DomainModelDef(id="m-arithmetic", domain="arithmetic", plugin_version="0.1.0")
        ],
        teaching_design=TeachingDesign(modes=["引导"], strategy_refs=["make_ten@0.1.0"]),
        verification=Verification(
            verified=True,
            verifier_version=VERIFIER_VERSION,
            normalized_problem_hash=None,
            claims=[claim],
            covered_claim_ids=["arithmetic"],
        ),
        initial_states={"m-arithmetic": {"left": a, "right": b, "transferred": 0}},
        operations=[
            OperationDef(id="arithmetic.transfer_units"),
            OperationDef(id="arithmetic.group_total"),
        ],
        activity_graph=nodes,
        assessment=[
            {
                "id": "assess-sum",
                "objective_refs": ["lo-make-ten"],
                "evidence_kind": "numeric_answer",
            }
        ],
        representations=[
            {"id": "rep-blocks", "model_refs": ["m-arithmetic"], "kind": "diagram_2d"}
        ],
        render=RenderSpec(runtime_version="0.1.0"),
        presentation=PresentationSpec(
            age_band="lower_primary",
            visual_theme="storybook",
            scene_metaphor="berry_basket",
            feedback_tone="encouraging",
            motion_style="playful",
            interaction_affordances=["type", "tap"],
        ),
    )


make_ten = StrategyTemplate(
    id="make_ten",
    version="0.1.0",
    applies_to=_applies_to,
    extract_params=_extract_params,
    guided_steps=GUIDED_STEPS,
    variants=_variants,
    misconceptions=MISCONCEPTIONS,
    build_fn=_build,
)
