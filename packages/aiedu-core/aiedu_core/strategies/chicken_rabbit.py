"""鸡兔同笼策略模板（方法内置 · 第一批）。

方法：H 头 F 足 → 设全为鸡：多出的足 = (兔子比鸡多的足数)×兔数 →
兔=(F-2H)/2，鸡=H-兔。答案程序计算 + SymPy 复验（2×鸡+4×兔==F 且 鸡+兔==H）。
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

_HEADS = re.compile(r"(\d{1,4})\s*(?:个)?头")
_FEET = re.compile(r"(\d{1,5})\s*(?:只|条)?(?:脚|腿)")


def _parse(text: str) -> tuple[int, int] | None:
    h = _HEADS.search(text)
    f = _FEET.search(text)
    if not h or not f:
        return None
    return int(h.group(1)), int(f.group(1))


def _applies_to(problem_text: str) -> bool:
    parsed = _parse(problem_text)
    if parsed is None:
        return False
    heads, feet = parsed
    # 整数解前提：足数介于 2H~4H 之间（且与 H 同奇偶——兔=(F-2H)/2 须为整数 → F 为偶数）
    return 2 * heads < feet < 4 * heads and feet % 2 == 0


def _extract_params(problem_text: str) -> dict:
    parsed = _parse(problem_text)
    if parsed is None:
        raise ValueError(f"not a chicken-rabbit problem: {problem_text!r}")
    heads, feet = parsed
    rabbits = int(evaluate_expression(f"({feet}-2*{heads})/2"))
    chickens = heads - rabbits
    # SymPy 复验：头数守恒 + 足数守恒
    assert evaluate_expression(f"{chickens}+{rabbits}") == heads
    assert evaluate_expression(f"2*{chickens}+4*{rabbits}") == feet
    return {"h": heads, "f": feet}


def _variants(params: dict, count: int = 10) -> list[dict]:
    h0, f0 = params["h"], params["f"]
    out: list[dict] = []
    for h in range(3, 40):
        for r in range(1, h):
            f = 2 * h + 2 * r
            if (h, f) == (h0, f0):
                continue
            out.append({"h": h, "f": f})
            if len(out) >= count:
                return out
    return out


MISCONCEPTIONS = (
    Misconception(
        id="assume-rabbit-first",
        description="假设全是兔子再反向推，差值方向写反。",
        distractor_hint="给出按全兔假设推导的错误结果",
    ),
    Misconception(
        id="feet-parity",
        description="未检查足数奇偶/范围，得到非整数或负数的鸡兔数。",
        distractor_hint="给出非法输入推导的错误结果",
    ),
)

GUIDED_STEPS = (
    GuidedStepTemplate(
        id="assume-chickens",
        prompt_template="设 {h} 个头全是鸡，一共多少只脚？",
        assistance=("每只鸡 2 只脚。",),
        distractors_from=(),
    ),
    GuidedStepTemplate(
        id="extra-feet",
        prompt_template="实际 {f} 只脚，比全是鸡多了多少只脚？每只兔子比鸡多 2 只脚，兔子有几只？",
        assistance=("多出的脚数 ÷ 2 = 兔子数。",),
        distractors_from=("assume-rabbit-first",),
    ),
)


def _build(params: dict) -> LessonSpecV2:
    h, f = params["h"], params["f"]
    rabbits = int(evaluate_expression(f"({f}-2*{h})/2"))
    chickens = h - rabbits
    claim = ClaimEvidence(
        id="arithmetic",
        statement=f"{h}头{f}足→鸡{chickens}只、兔{rabbits}只（{chickens}+{rabbits}={h}，2×{chickens}+4×{rabbits}={f}）",
        status="verified",
        method="精确计算",
    )
    nodes = [
        PredictNode(
            type="predict",
            id="assume-chickens",
            prompt=f"鸡兔同笼：{h} 个头，{f} 只脚。假设全是鸡，共有多少只脚？",
            response=ResponseNumber(kind="number", expected=str(2 * h)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"每只鸡 2 只脚：2×{h}=?。",),
            next_ids=["extra-feet"],
        ),
        PredictNode(
            type="predict",
            id="extra-feet",
            prompt="多出来的脚都由兔子贡献（每只兔子比鸡多 2 只脚），兔子有几只？",
            response=ResponseNumber(kind="number", expected=str(rabbits)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"({f}−2×{h})÷2 = ?。",),
            distractors_from=("assume-rabbit-first",),
            next_ids=["find-chickens"],
        ),
        PredictNode(
            type="predict",
            id="find-chickens",
            prompt="鸡有几只？",
            response=ResponseNumber(kind="number", expected=str(chickens)),
            gate=Gate(mode="require_attempt"),
            assistance=(f"鸡 = {h} − 兔 = {h} − {rabbits}。",),
            distractors_from=("feet-parity",),
            next_ids=["replay"],
        ),
        ObserveNode(
            type="observe",
            id="replay",
            narration=(
                f"完整演示：假设全是鸡→2×{h}={2*h} 只脚；多出 {f}-{2*h}={f-2*h} 只脚；"
                f"兔子={f-2*h}÷2={rabbits} 只；鸡={h}-{rabbits}={chickens} 只。"
                f"验证：{chickens}+{rabbits}={h}、2×{chickens}+4×{rabbits}={f}。"
            ),
            next_ids=["transfer-practice"],
        ),
        PredictNode(
            type="predict",
            id="transfer-practice",
            prompt="试试：鸡兔同笼，12 个头，34 只脚，兔子几只？",
            response=ResponseNumber(kind="number", expected=str(int(evaluate_expression("(34-2*12)/2")))),
            gate=Gate(mode="require_attempt"),
            assistance=("先假设全是鸡，多出的脚除以 2。",),
            next_ids=["__end__"],
        ),
    ]
    return LessonSpecV2(
        lesson_id=f"chicken-rabbit-{h}-h{f}-f",
        revision=1,
        teaching_request={"kind": "problem", "content": f"鸡兔同笼：{h}个头，{f}只脚"},
        curriculum_context={"stage": "primary", "grade": 4},
        learning_objectives=[
            LearningObjective(id="lo-chicken-rabbit", description=f"鸡兔同笼（{h}头{f}足）用假设法")
        ],
        teaching_design=TeachingDesign(modes=["引导"], strategy_refs=["chicken_rabbit@0.1.0"]),
        verification=Verification(
            verified=True,
            verifier_version=VERIFIER_VERSION,
            normalized_problem_hash=None,
            claims=[claim],
            covered_claim_ids=["arithmetic"],
        ),
        activity_graph=nodes,
        assessment=[{"id": "assess-cr", "objective_refs": ["lo-chicken-rabbit"], "evidence_kind": "numeric_answer"}],
        render=RenderSpec(runtime_version="0.1.0"),
        presentation=PresentationSpec(age_band="upper_primary", visual_theme="clean_school"),
    )


chicken_rabbit = StrategyTemplate(
    id="chicken_rabbit",
    version="0.1.0",
    applies_to=_applies_to,
    extract_params=_extract_params,
    guided_steps=GUIDED_STEPS,
    variants=_variants,
    misconceptions=MISCONCEPTIONS,
    build_fn=_build,
)
