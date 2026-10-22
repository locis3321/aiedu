"""破十法（退位减法）策略模板（第二个切片）。

teaching-skills/borrow-ten 的确定性实现：被减数两位、减数一位、个位不够减。
步骤：找十 → 拆十先减（10-b）→ 拆十后剩余（a-10）→ 合并 → 回放 → 变式练习。
每个 predict 节点带 require_attempt 门槛与提示阶梯（assistance）。
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

_PATTERN = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d)\s*$")


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
    # 被减数两位数且个位不够减（退位）；个位够减应先讲直接减
    return 10 <= a <= 99 and 1 <= b <= 9 and a % 10 < b


def _extract_params(problem_text: str) -> dict:
    parsed = _parse(problem_text)
    if parsed is None:
        raise ValueError(f"not a borrow-ten problem: {problem_text!r}")
    a, b = parsed
    # SymPy 程序化复验：a-b == (10-b) + (a-10)（把 1 个十拆成 10 个一，总量不变）
    assert evaluate_expression(f"{a}-{b}") == evaluate_expression(
        f"(10-{b})+({a}-10)"
    )
    return {"a": a, "b": b}


def _variants(params: dict, count: int = 10) -> list[dict]:
    """程序化生成满足同一适用条件的新数对（排除当前数对）。"""
    a0, b0 = params["a"], params["b"]
    out: list[dict] = []
    for b in range(1, 10):
        for a in range(10, 100):
            if a % 10 >= b:
                continue
            if (a, b) == (a0, b0):
                continue
            out.append({"a": a, "b": b})
            if len(out) >= count:
                return out
    return out


MISCONCEPTIONS = (
    Misconception(
        id="forget-borrow",
        description="借了十之后忘记被减数变小（如 13-5 错算成 9）。",
        distractor_hint="给出'十位照减、个位直接相减'的错误结果",
    ),
    Misconception(
        id="use-big-minus-small",
        description="个位不够减时直接用大数减小数（如 9-6），忘记借十。",
        distractor_hint="给出用 b 减个位 r 的错误结果",
    ),
    Misconception(
        id="forget-remaining-tens",
        description="拆十后忘记还剩几个十，合起来时少加了一个十。",
        distractor_hint="给出只用拆出的十与个位相减的错误结果",
    ),
)

GUIDED_STEPS = (
    GuidedStepTemplate(
        id="find-tens",
        prompt_template="{a} 是由几个十和几个一组成的？零散的是几颗？",
        assistance=("把 {a} 分成十位和个位：十位是 {t}，个位是 {r}。",),
        distractors_from=("use-big-minus-small",),
    ),
    GuidedStepTemplate(
        id="borrow-ten",
        prompt_template="个位 {r} 颗不够减 {b} 颗，拆开 1 个十（10 颗）。先算 10 - {b} = ?",
        assistance=("被减数的十位里有 1 个十，把它拆成 10 颗散开的。",),
        on_correct_actions=("arithmetic.break_ten",),
        distractors_from=("forget-borrow",),
    ),
    GuidedStepTemplate(
        id="subtract-rest",
        prompt_template="拆走 1 个十后，{a} 还剩多少颗（整捆和零散一起算）？",
        assistance=("原有 {t} 个十，拆走 1 个十后还剩 {t-1} 个十，加零散的 {r} 颗。",),
        distractors_from=("forget-remaining-tens",),
    ),
    GuidedStepTemplate(
        id="merge",
        prompt_template="先算出的 {c} 颗，加上剩下的 {a-10} 颗，一共还剩多少颗？",
        assistance=("10 里减掉 {b} 后剩 {c} 颗，和剩下的 {a-10} 颗合在一起。",),
        on_correct_actions=("arithmetic.recombine",),
        distractors_from=("forget-remaining-tens",),
    ),
)


def _build(params: dict) -> LessonSpecV2:
    a, b = params["a"], params["b"]
    r, t = a % 10, a // 10
    c = int(evaluate_expression(f"10-{b}"))
    total = int(evaluate_expression(f"{a}-{b}"))
    rest = int(evaluate_expression(f"{a}-10"))
    # 变式练习：同族新数对（程序生成），答案由 SymPy 精确计算
    transfer = _variants({"a": a, "b": b}, count=1)[0]
    a2, b2 = transfer["a"], transfer["b"]
    transfer_total = int(evaluate_expression(f"{a2}-{b2}"))
    claim = ClaimEvidence(
        id="arithmetic",
        statement=f"{a}-{b}={total}（破十：(10-{b})+({a}-10)={c}+{rest}={total}）",
        status="verified",
        method="精确计算",
    )
    nodes = [
        PredictNode(
            type="predict",
            id="find-tens",
            prompt=f"小松鼠有 {a} 颗松果，每 10 颗装成一捆。零散着（不够一捆）的有几颗？",
            response=ResponseNumber(kind="number", expected=str(r)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"把 {a} 分成十位和个位：十位是 {t}，个位是 {r}。",),
            next_ids=["borrow-ten"],
        ),
        PredictNode(
            type="predict",
            id="borrow-ten",
            prompt=f"要送朋友 {b} 颗，但零散的 {r} 颗不够。小松鼠解开一捆（10 颗）。10 - {b} = ?",
            response=ResponseNumber(kind="number", expected=str(c)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"一捆有 10 颗，从这 10 颗里拿 {b} 颗送人。",),
            on_correct=["arithmetic.break_ten"],
            next_ids=["subtract-rest"],
        ),
        PredictNode(
            type="predict",
            id="subtract-rest",
            prompt=f"解开一捆后，原来的 {a} 颗还剩多少颗（整捆和零散一起算）？",
            response=ResponseNumber(kind="number", expected=str(rest)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"原来有 {t} 捆，解开 1 捆后还剩 {t-1} 捆，再加零散的 {r} 颗。",),
            distractors_from=("forget-remaining-tens",),
            next_ids=["merge"],
        ),
        PredictNode(
            type="predict",
            id="merge",
            prompt=f"解开的这 10 颗里送走 {b} 颗后剩下 {c} 颗，把它和剩下的 {rest} 颗合起来，一共是多少颗？",
            response=ResponseNumber(kind="number", expected=str(total)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"10 里减掉 {b} 后剩 {c} 颗，再合上剩下的 {rest} 颗。",),
            on_correct=["arithmetic.recombine"],
            next_ids=["replay"],
        ),
        ObserveNode(
            type="observe",
            id="replay",
            narration=(
                f"完整演示：{a} 里个位 {r} 不够减 {b}，把 1 个十拆成 10 个一："
                f"10-{b}={c}，剩下的 {rest} 颗一起算：{c}+{rest}={total}。"
                "这就是破十法——个位不够减时，从十位借 1 个十拆成 10 个一，"
                "先减再加，总量不变。"
            ),
            next_ids=["transfer-practice"],
        ),
        PredictNode(
            type="predict",
            id="transfer-practice",
            prompt=f"试试这题：{a2}-{b2}怎么算？（先自己想一想）",
            response=ResponseNumber(kind="number", expected=str(transfer_total)),
            gate=Gate(mode="require_attempt"),
            assistance=("个位够不够减？不够就从十位借 1 个十。",),
            next_ids=["__end__"],
        ),
    ]
    return LessonSpecV2(
        lesson_id=f"borrow-ten-{a}-minus-{b}",
        revision=1,
        teaching_request={"kind": "problem", "content": f"{a}-{b}"},
        curriculum_context={"stage": "primary", "grade": 2},
        learning_objectives=[
            LearningObjective(id="lo-borrow-ten", description=f"用破十法计算{a}-{b}")
        ],
        domain_models=[
            DomainModelDef(id="m-arithmetic", domain="arithmetic", plugin_version="0.1.0")
        ],
        teaching_design=TeachingDesign(
            modes=["引导"], strategy_refs=["borrow_ten@0.1.0"]
        ),
        verification=Verification(
            verified=True,
            verifier_version=VERIFIER_VERSION,
            normalized_problem_hash=None,
            claims=[claim],
            covered_claim_ids=["arithmetic"],
        ),
        initial_states={"m-arithmetic": {"tens": t, "ones": r, "borrowed": 0}},
        operations=[
            OperationDef(id="arithmetic.break_ten"),
            OperationDef(id="arithmetic.recombine"),
        ],
        activity_graph=nodes,
        assessment=[
            {
                "id": "assess-diff",
                "objective_refs": ["lo-borrow-ten"],
                "evidence_kind": "numeric_answer",
            }
        ],
        representations=[
            {"id": "rep-bundles", "model_refs": ["m-arithmetic"], "kind": "diagram_2d"}
        ],
        render=RenderSpec(runtime_version="0.1.0"),
        presentation=PresentationSpec(
            age_band="lower_primary",
            visual_theme="storybook",
            scene_metaphor="pinecone_bundles",
            feedback_tone="encouraging",
            motion_style="playful",
            interaction_affordances=["type", "tap"],
        ),
    )


borrow_ten = StrategyTemplate(
    id="borrow_ten",
    version="0.1.0",
    applies_to=_applies_to,
    extract_params=_extract_params,
    guided_steps=GUIDED_STEPS,
    variants=_variants,
    misconceptions=MISCONCEPTIONS,
    build_fn=_build,
)
