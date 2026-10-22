"""硬约束的独立可执行断言（CI 里作为独立 job 运行，证据逐条打印）。

覆盖 AGENTS.md 的硬约束 1/2/3（4 由 aiedu-mcp 用例覆盖，5 由 aiedu-player Playwright 覆盖）：
- 硬约束 1：answer-filtered 投影后，未解锁节点的 response.expected 必须为 None；
- 硬约束 2：verified 只能由 SymPy 核验产生（refuted / requires_review 不得写成 verified）；
- 硬约束 3：不编造——未覆盖题型必须显式 capability gap，不得返回编造的 spec。

用法：python scripts/check_constraints.py
退出码非 0 表示违反硬约束（CI 直接失败，不用 continue-on-error）。
"""

import asyncio
import json
import os
import sys

from aiedu_core.models.filtering import filtered_spec
from aiedu_core.pipeline.pipeline import PipelineError, run_pipeline
from aiedu_core.verify.sympy_verify import verify_math

FAILURES: list[str] = []


def disable_llm() -> None:
    """中和宿主 LLM env：让"未覆盖题型"在任何环境都走确定性路径。

    否则宿主机若配了 LLM env，52-37 会走 LLM 自由设计出课，断言语义被污染
    （D1–D2.5 的同类教训：默认行为必须与环境无关）。
    """
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_NAME"):
        os.environ.pop(key, None)
    from aiedu_core.config import get_settings

    get_settings.cache_clear()


def check(name: str, ok: bool, evidence: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {evidence}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    disable_llm()

    # ---- 硬约束 1：先想后看（filtered 投影不含未解锁答案）----
    spec = asyncio.run(run_pipeline({"kind": "problem", "content": "16+8"}))
    spec_dict = spec.model_dump(mode="json")
    filtered = filtered_spec(spec_dict, set())
    leaks = [
        node["id"]
        for node in filtered["activity_graph"]
        if (node.get("response") or {}).get("expected") is not None
    ]
    check(
        "硬约束1 未解锁节点 response.expected is None",
        not leaks,
        f"泄漏节点={leaks or '无'}（full 模式对照："
        f"{sum(1 for n in spec_dict['activity_graph'] if (n.get('response') or {}).get('expected') is not None)} 个节点含答案）",
    )

    # ---- 硬约束 2：verified 仅由 SymPy 核验产生 ----
    good = verify_math("7x8", 56)
    bad = verify_math("7x8", 57)
    broken = verify_math("__import__('os')", 1)
    check(
        "硬约束2 verified 仅由 SymPy 产生",
        good.result == "verified" and bad.result == "refuted" and broken.result == "requires_review",
        f"7x8=56 → {good.result}；7x8=57 → {bad.result}；非法表达式 → {broken.result}",
    )

    # ---- 硬约束 3：不编造（未覆盖题型显式 capability gap）----
    gap_cases = [
        ("52-37", "problem", "两位数减两位数"),
        ("1/2+1/4", "concept", "分数四则"),
        ("7x8", "problem", "乘法出课（核验能过、出课不能）"),
    ]
    all_gapped = True
    for expr, kind, label in gap_cases:
        try:
            asyncio.run(run_pipeline({"kind": kind, "content": expr}))
            print(f"[FAIL] 硬约束3 {label}（{expr}）竟然出课了（编造）")
            all_gapped = False
        except PipelineError as exc:
            ok = "capability gap" in str(exc)
            print(f"  {label}（{expr}）→ capability gap: {ok}")
            all_gapped = all_gapped and ok
    check("硬约束3 未覆盖题型显式 capability gap", all_gapped,
          "；".join(f"{e}→gap" for e, _, _ in gap_cases))

    print(json.dumps({"failures": FAILURES}, ensure_ascii=False))
    if FAILURES:
        print("硬约束断言失败")
        return 1
    print("全部硬约束断言通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
