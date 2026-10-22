"""分数等分概念策略模板（第三个切片）。

teaching-skills/fraction-equal-parts 的确定性实现：概念型课程（concept 输入，
如"一块披萨平均分成 4 份，取其中 1 份"），教"分母=平均分成几份、分子=取了几份"。
节点用 observe / predict(number,choice) 组合；expected 由程序计算（SymPy 复验）。

明确不做：分数四则运算（如 1/2+1/4）——本期仍走 capability gap，禁止编造。
"""

import re

from sympy import Rational

from aiedu_core.models.lesson_v2 import (
    ClaimEvidence,
    Gate,
    LearningObjective,
    LessonSpecV2,
    ObserveNode,
    PredictNode,
    PresentationSpec,
    RenderSpec,
    ResponseChoice,
    ResponseNumber,
    TeachingDesign,
    Verification,
)
from aiedu_core.verify.evidence import VERIFIER_VERSION
from aiedu_core.verify.sympy_verify import evaluate_expression
from aiedu_core.strategies.base import GuidedStepTemplate, Misconception, StrategyTemplate

# 平均分成 N 份；默认取 1 份（unit fraction）
_PARTS = re.compile(r"平均分(?:成|为)?\s*(\d{1,2})\s*份")
_TAKE = re.compile(r"取(?:其中|了)?\s*(\d{1,2})\s*份")


def _parse(text: str) -> tuple[int, int] | None:
    m = _PARTS.search(text)
    if not m:
        return None
    n = int(m.group(1))
    mt = _TAKE.search(text)
    m = int(mt.group(1)) if mt else 1
    return n, m


def _applies_to(problem_text: str) -> bool:
    """概念型等分输入；明确不匹配分数四则与开放性概念请求。"""
    parsed = _parse(problem_text)
    if parsed is None:
        return False
    n, m = parsed
    # "平均分成 N 份" 且 N 在合理范围（2~12）、取的份数真实小于总份数
    return 2 <= n <= 12 and 1 <= m < n


def _extract_params(problem_text: str) -> dict:
    parsed = _parse(problem_text)
    if parsed is None:
        raise ValueError(f"not a fraction-equal-parts problem: {problem_text!r}")
    n, m = parsed
    if not (2 <= n <= 12 and 1 <= m < n):
        raise ValueError(f"out of supported range: {n}/{m}")
    # SymPy 程序化复验：取 m 份 = m/n（精确有理数，无浮点误差）
    assert evaluate_expression(f"{m}/{n}") == Rational(m, n)
    return {"n": n, "m": m}


def _variants(params: dict, count: int = 10) -> list[dict]:
    """程序化生成同族数对（排除当前数对）。"""
    n0, m0 = params["n"], params["m"]
    out: list[dict] = []
    for n in range(2, 13):
        for m in range(1, n):
            if (n, m) == (n0, m0):
                continue
            out.append({"n": n, "m": m})
            if len(out) >= count:
                return out
    return out


MISCONCEPTIONS = (
    Misconception(
        id="swap-numerator-denominator",
        description="混淆分子分母含义：把份数当分子、把取的份数当分母。",
        distractor_hint="给出分子分母颠倒的分数",
    ),
    Misconception(
        id="not-equal-parts",
        description="把'随便切'当成'平均分'，不理解每份必须一样大。",
        distractor_hint="给出非等分情境下的份数",
    ),
    Misconception(
        id="bigger-denominator-bigger-piece",
        description="认为分母大的分数一定大（忽略每份大小与整体）。",
        distractor_hint="给出分母更大的分数作为'更大'选项",
    ),
)

GUIDED_STEPS = (
    GuidedStepTemplate(
        id="find-denominator",
        prompt_template="平均分成 {n} 份，分母是几？",
        assistance=("分母表示把整体平均分成了几份。",),
        distractors_from=("swap-numerator-denominator",),
    ),
    GuidedStepTemplate(
        id="find-numerator",
        prompt_template="取其中 {m} 份，分子是几？",
        assistance=("分子表示取了几份。",),
        distractors_from=("swap-numerator-denominator",),
    ),
)


def _build(params: dict) -> LessonSpecV2:
    n, m = params["n"], params["m"]
    value = evaluate_expression(f"{m}/{n}")
    claim = ClaimEvidence(
        id="fraction-part",
        statement=f"取{m}份=整体的{m}/{n}（{m}/{n} = {value}）",
        status="verified",
        method="精确计算",
    )
    # 变式：同一整体取 m2 份（程序生成，答案由 SymPy 计算）
    v = _variants({"n": n, "m": m}, count=1)[0]
    n2, m2 = v["n"], v["m"]
    frac2 = f"{m2}/{n2}"
    # 对比节点：同一整体下两份 1/x 与 1/y（份数越少每份越大）
    compare = _build_compare(n)
    nodes = [
        ObserveNode(
            type="observe",
            id="observe-whole",
            narration=(
                f"这里有一个整体（比如一块披萨）。要把它分成大小一样的 {n} 份——"
                "这就是'平均分'：每份一样大，不是随便切。"
            ),
            next_ids=["find-denominator"],
        ),
        PredictNode(
            type="predict",
            id="find-denominator",
            prompt=f"平均分成 {n} 份，分母是几？",
            response=ResponseNumber(kind="number", expected=str(n)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"分母表示把整体平均分成了几份——这里分成了 {n} 份。",),
            next_ids=["find-numerator"],
        ),
        PredictNode(
            type="predict",
            id="find-numerator",
            prompt=f"取其中 {m} 份，分子是几？",
            response=ResponseNumber(kind="number", expected=str(m)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"分子表示取了几份——这里取了 {m} 份。",),
            distractors_from=("swap-numerator-denominator",),
            next_ids=["name-fraction"],
        ),
        PredictNode(
            type="predict",
            id="name-fraction",
            prompt=f"取出的 {m} 份是整体的几分之几？",
            response=ResponseChoice(
                kind="choice",
                options=[f"{m}/{n}", f"{n}/{m}", f"{m}/{n + 1}"],
                correct_index=0,
                distractors_from=("swap-numerator-denominator", "bigger-denominator-bigger-piece"),
            ),
            gate=Gate(mode="require_attempt"),
            assistance=(f"分子写取的份数 {m}，分母写总份数 {n}。",),
            next_ids=["compare-unit"],
        ),
        PredictNode(
            type="predict",
            id="compare-unit",
            prompt=f"同一个整体，{compare['options'][0]} 和 {compare['options'][1]} 哪一份更大？",
            response=ResponseChoice(
                kind="choice",
                options=compare["options"],
                correct_index=compare["correct_index"],
                distractors_from=("bigger-denominator-bigger-piece",),
            ),
            gate=Gate(mode="require_attempt"),
            assistance=(f"分得份数越多，每份越小；所以 {compare['options'][0]} 更大。",),
            next_ids=["transfer-practice"],
        ),
        PredictNode(
            type="predict",
            id="transfer-practice",
            prompt=f"同一个整体平均分成 {n2} 份，取 {m2} 份，是几分之几？",
            response=ResponseChoice(
                kind="choice",
                options=[frac2, f"{n2}/{m2}", f"{m2}/{n2 + 1}"],
                correct_index=0,
                distractors_from=("swap-numerator-denominator", "bigger-denominator-bigger-piece"),
            ),
            gate=Gate(mode="require_attempt"),
            assistance=(f"分子是取的份数 {m2}，分母是总份数 {n2}。",),
            next_ids=["__end__"],
        ),
    ]
    return LessonSpecV2(
        lesson_id=f"fraction-equal-parts-{m}-over-{n}",
        revision=1,
        teaching_request={"kind": "concept", "content": f"把一个整体平均分成{n}份，取其中{m}份"},
        curriculum_context={"stage": "primary", "grade": 3},
        learning_objectives=[
            LearningObjective(
                id="lo-fraction-equal-parts",
                description=f"理解等分：整体平均分成{n}份，取{m}份是{m}/{n}",
            )
        ],
        teaching_design=TeachingDesign(
            modes=["引导"], strategy_refs=["fraction_equal_parts@0.1.0"]
        ),
        verification=Verification(
            verified=True,
            verifier_version=VERIFIER_VERSION,
            normalized_problem_hash=None,
            claims=[claim],
            covered_claim_ids=["fraction-part"],
        ),
        activity_graph=nodes,
        assessment=[
            {
                "id": "assess-fraction",
                "objective_refs": ["lo-fraction-equal-parts"],
                "evidence_kind": "classification",
            }
        ],
        representations=[
            {"id": "rep-shapes", "model_refs": [], "kind": "diagram_2d"}
        ],
        render=RenderSpec(runtime_version="0.1.0"),
        presentation=PresentationSpec(
            age_band="upper_primary",
            visual_theme="storybook",
            scene_metaphor="pizza_party",
            feedback_tone="encouraging",
            motion_style="calm",
            interaction_affordances=["type", "tap"],
        ),
    )


def _build_compare(n: int) -> dict:
    """同一整体 1/n 与 1/(n+1) 的比较：份数越少每份越大。

    返回 choice 内容（正解 index 由程序确定）；n=12 时退化为 n-1 对比。
    """
    a, b = n, n + 1
    if b > 12:
        a, b = n - 1, n
    return {
        "options": [f"1/{a}", f"1/{b}", "一样大"],
        "correct_index": 0,
    }


fraction_equal_parts = StrategyTemplate(
    id="fraction_equal_parts",
    version="0.1.0",
    applies_to=_applies_to,
    extract_params=_extract_params,
    guided_steps=GUIDED_STEPS,
    variants=_variants,
    misconceptions=MISCONCEPTIONS,
    build_fn=_build,
)
