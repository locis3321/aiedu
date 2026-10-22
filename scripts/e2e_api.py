"""交付级 E2E（API 层）：真实 MCP 协议调用穿透全链路。

- 起真实 aiedu-mcp（stdio 子进程）与真实渲染服务（aiedu-player server/serve.mjs）；
- 用 MCP 官方 Python client 逐项调用并断言（无 mock、无编造）；
- 报告写入 .e2e/delivery-api-report.md。
用法：python scripts/e2e_api.py
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]
MCP_PY = str(REPO / "packages/aiedu-mcp/.venv/Scripts/python.exe")
E2E_DIR = REPO / ".e2e"

results: list[dict] = []


def disable_llm() -> None:
    """中和宿主 LLM env（D1-D2.5 教训：断言必须与环境无关，否则宿主配了 LLM 时
    模板外题面会走 LLM 自由设计出课，capability_gap 断言被污染）。"""
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_NAME"):
        os.environ.pop(key, None)
    from aiedu_core.config import get_settings

    get_settings.cache_clear()


def check(name: str, ok: bool, evidence: str) -> None:
    results.append({"name": name, "ok": bool(ok), "evidence": evidence})
    print(f"[{'PASS' if ok else 'FAIL'}] {name} :: {evidence[:220]}")


async def main() -> int:
    E2E_DIR.mkdir(exist_ok=True)
    disable_llm()
    # 渲染服务（真实子进程）
    player = subprocess.Popen(
        ["node", str(REPO / "packages/aiedu-player/server/serve.mjs"), "8130"],
        cwd=str(REPO / "packages/aiedu-player"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await asyncio.sleep(1.5)

    # 日志设施：本次 E2E 的调用全部落盘（模拟真实使用）
    log_path = E2E_DIR / "e2e-usage.jsonl"
    log_path.unlink(missing_ok=True)
    os.environ["AIEDU_USAGE_LOG"] = str(log_path)

    params = StdioServerParameters(
        command=MCP_PY,
        args=["-m", "aiedu_mcp.server", "--transport", "stdio"],
        cwd=str(REPO / "packages/aiedu-mcp"),
        env={**os.environ},  # 显式继承：AIEDU_USAGE_LOG 等环境变量必须传进 server 子进程
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            check("MCP 协议握手（stdio）", init.server_info.name == "aiedu-mcp",
                  f"server={init.server_info.name} v{init.server_info.version}")

            async def call(name, args):
                res = await session.call_tool(name, args)
                if getattr(res, "isError", False):
                    return {"error": res.content[0].text if res.content else "isError"}
                return json.loads(res.content[0].text)

            # ---- A. verify_math 三态 ----
            v1 = await call("verify_math", {"expression": "7x8", "expected": 56})
            check("A1 verify_math('7x8',56)=verified", v1.get("result") == "verified",
                  json.dumps(v1, ensure_ascii=False)[:160])
            v2 = await call("verify_math", {"expression": "7x8", "expected": 57})
            check("A2 verify_math 错值=refuted（不假装对）", v2.get("result") == "refuted",
                  f"result={v2.get('result')}")
            v3 = await call("verify_math", {"expression": "__import__('os')", "expected": 1})
            check("A3 非法表达式=requires_review", v3.get("result") == "requires_review",
                  f"result={v3.get('result')}")

            # ---- B. generate_lesson：三类出课 + 三类 gap ----
            lessons = {}
            for q, lid in [("16+8", "make-ten-16-plus-8"), ("16-9", "borrow-ten-16-minus-9"),
                           ("一块披萨平均分成4份，取其中1份", "fraction-equal-parts-1-over-4")]:
                out = await call("generate_lesson", {"question": q})
                ok = out.get("lesson_id") == lid and out["verification"]["verified"] is True
                lessons[q] = out
                check(f"B1 出课 {q}", ok,
                      f"lesson_id={out.get('lesson_id')} verified={out.get('verification', {}).get('verified')}")
            for q, err in [("52-37", "capability_gap"), ("1/2+1/4", "capability_gap"), ("7x8", "capability_gap")]:
                out = await call("generate_lesson", {"question": q})
                check(f"B2 未覆盖 {q} 显式失败（不编造）",
                      out.get("error") == err and "spec" not in out,
                      f"error={out.get('error') or out.get('lesson_id')}")

            spec = lessons["16-9"]["spec"]

            # ---- C. get_lesson：filtered/full/信封/非法 ----
            filt = await call("get_lesson", {"spec": spec, "reveal": "filtered", "unlocked_ids": []})
            leaks = [n["id"] for n in filt["spec"]["activity_graph"]
                     if (n.get("response") or {}).get("expected") is not None]
            check("C1 filtered 未解锁节点无答案（硬约束1）", not leaks,
                  f"泄漏={leaks or '无'}")
            full = await call("get_lesson", {"spec": spec, "reveal": "full"})
            reveals = [n["response"]["expected"] for n in full["spec"]["activity_graph"]
                       if (n.get("response") or {}).get("expected")]
            check("C2 full 可见程序化答案", len(reveals) >= 4, f"可见答案数={len(reveals)}")
            env = await call("get_lesson", {"spec": lessons["16+8"]})
            check("C3 信封入参显式拒绝", env.get("error") == "invalid_input"
                  and "spec 字段内容" in env.get("hint", ""), f"error={env.get('error')} hint 说明层级")
            bad = await call("get_lesson", {"spec": {"schema_version": "2.0", "lesson_id": "x"}})
            check("C4 缺 activity_graph 显式拒绝", bad.get("error") == "invalid_input",
                  f"error={bad.get('error')}")

            # ---- D. submit_attempt：判分/提示/无程序化答案 ----
            d1 = await call("submit_attempt", {"spec": spec, "node_id": "merge", "answer": "7"})
            check("D1 答对=independent", d1.get("correct") is True and d1.get("evidence") == "independent",
                  json.dumps(d1, ensure_ascii=False)[:100])
            d2 = await call("submit_attempt", {"spec": spec, "node_id": "merge", "answer": "8"})
            check("D2 答错=assisted+提示", d2.get("correct") is False and d2.get("evidence") == "assisted"
                  and bool(d2.get("hint")), json.dumps(d2, ensure_ascii=False)[:100])
            d3 = await call("submit_attempt", {"spec": spec, "node_id": "不存在", "answer": "1"})
            check("D3 未知节点显式拒绝", d3.get("error") == "node_not_found", f"error={d3.get('error')}")

            # ---- E. render_lesson：本地拼 URL（D5：无服务端依赖，player_unavailable 消亡）----
            r1 = await call("render_lesson", {"spec": spec})
            encoded = r1.get("url", "").split("?spec=")[-1]
            import base64 as _b64

            decoded = json.loads(_b64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            check("E1 render_lesson 本地拼 URL 且 spec 往返相等",
                  decoded == spec and "lesson.html?spec=" in r1.get("url", ""),
                  f"url={r1.get('url', '')[:70]}... 往返={'相等' if decoded == spec else '不等'}")

    # 日志设施：E2E 调用已落盘
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        check("F1 AIEDU_USAGE_LOG 落盘且合法", len(lines) > 5 and all(
            json.loads(l).get("tool") for l in lines if l.strip()), f"{len(lines)} 行 JSONL")
    else:
        check("F1 AIEDU_USAGE_LOG 落盘且合法", False, "无日志文件")

    player.terminate()
    results_json = {"total": len(results), "passed": sum(1 for r in results if r["ok"]),
                    "failed": [r for r in results if not r["ok"]]}
    report = E2E_DIR / "delivery-api-report.md"
    report.write_text(
        "# 交付级 E2E 报告（API 层，真实 MCP 协议调用）\n\n"
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M')}（本地）\n"
        f"- 结论：**{results_json['passed']}/{results_json['total']} 通过**\n\n"
        + "\n".join(f"- [{'✅' if r['ok'] else '❌'}] {r['name']} — {r['evidence']}" for r in results)
        + "\n",
        encoding="utf-8",
    )
    return 0 if not results_json["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
