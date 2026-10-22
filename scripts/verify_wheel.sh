#!/usr/bin/env bash
# 发布前后自检：把构建出的 wheel 装进干净 venv，用**已安装的产物**做真实调用。
#
# 这是"发了但装不上"的自动化防护：
#   - 装的是 dist 里的 wheel（不是源码树，源码树能跑不代表包能跑）；
#   - 走 MCP 协议真实调用（stdio + 官方 client），不是 import 一下就算过；
#   - 覆盖 README 承诺的三类零 LLM 题型（装不上 skill 资产就会在这里露馅）。
#
# 用法：bash scripts/verify_wheel.sh
set -euo pipefail

cd "$(dirname "$0")/.."

VENV="${TMPDIR:-/tmp}/aiedu-wheelcheck"
rm -rf "$VENV"
python -m venv "$VENV"
"$VENV/Scripts/python.exe" -m pip install -q --upgrade pip 2>/dev/null || \
  "$VENV/bin/python" -m pip install -q --upgrade pip

PY="$VENV/Scripts/python.exe"
[ -x "$PY" ] || PY="$VENV/bin/python"

"$PY" -m pip install -q \
  packages/aiedu-core/dist/aiedu_core-*.whl \
  packages/aiedu-mcp/dist/aiedu_mcp-*.whl

echo "=== 已安装 ==="
"$PY" -m pip list 2>/dev/null | grep -iE "^(aiedu|fastmcp|sympy|pydantic) " || true

"$PY" - <<'PYEOF'
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    exe = next(
        p
        for p in (
            os.path.join(os.path.dirname(sys.executable), "aiedu-mcp.exe"),
            os.path.join(os.path.dirname(sys.executable), "aiedu-mcp"),
        )
        if os.path.exists(p)
    )
    params = StdioServerParameters(command=exe, args=["--transport", "stdio"])
    failures = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"[wheel] server: {init.server_info.name} {init.server_info.version}")
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            print(f"[wheel] tools: {tools}")
            if tools != ["generate_lesson", "get_lesson", "render_lesson", "submit_attempt", "verify_math"]:
                failures.append(f"工具面不符：{tools}")

            for question, kind in [
                ("16+8", "凑十法"),
                ("16-9", "破十法"),
                ("一块披萨平均分成4份，取其中1份", "分数等分"),
            ]:
                res = await session.call_tool("generate_lesson", {"question": question})
                payload = json.loads(res.content[0].text)
                if "error" in payload:
                    failures.append(f"{kind} 未出课：{payload}")
                    print(f"[wheel] {kind} -> ERROR {payload['error']}")
                else:
                    print(
                        f"[wheel] {kind} -> {payload['lesson_id']} "
                        f"verified={payload['verification']['verified']}"
                    )

            vm = await session.call_tool("verify_math", {"expression": "7×8", "expected": "56"})
            result = json.loads(vm.content[0].text)["result"]
            print(f"[wheel] verify_math('7×8',56) -> {result}")
            if result != "verified":
                failures.append("verify_math 未通过")

    if failures:
        print("[wheel] 失败：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[wheel] 全部通过：已安装产物可跑且覆盖承诺的题型")
    return 0


raise SystemExit(asyncio.run(main()))
PYEOF
