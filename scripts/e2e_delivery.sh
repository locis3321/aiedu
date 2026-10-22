#!/usr/bin/env bash
# 交付级 E2E：一次跑完整个系统（内核 → MCP 协议 → 渲染服务 → 真实浏览器 → 负面用例 → 日志 → wheel 形态）。
#
# 用法：bash scripts/e2e_delivery.sh
# 产物（.e2e/，已 gitignore）：各层报告 + 截图 + JSONL 日志
set -uo pipefail
cd "$(dirname "$0")/.."

E2E=.e2e
mkdir -p "$E2E"
SUMMARY="$E2E/delivery-report.md"
: > "$SUMMARY"
echo "# 交付级 E2E 总报告（$(date '+%Y-%m-%d %H:%M') 本地）" >> "$SUMMARY"
echo "" >> "$SUMMARY"

step() { echo ""; echo "===== $1 ====="; echo "===== $1 =====" >> "$SUMMARY"; }

# 0) 准备：起渲染服务（e2e_api 与会话共用）
( cd packages/aiedu-player && node server/serve.mjs 8130 >/dev/null 2>&1 & )
sleep 2

# 1) 协议层 E2E（真实 MCP stdio 全链路）
step "1. API 层：MCP 协议全链路（真实调用）"
packages/aiedu-mcp/.venv/Scripts/python.exe scripts/e2e_api.py 2>/dev/null | tee /dev/stderr | grep -E "^\[(PASS|FAIL)\]" >> "$SUMMARY"
echo "" >> "$SUMMARY"

# 2) D5 语义：本地拼 URL——即使 AIEDU_PLAYER_URL 指向不可达端口也产出可往返 url（无服务端依赖）
step "2. render_lesson 本地拼 URL（无服务端依赖；player_unavailable 错误类型已消亡）"
AIEDU_PLAYER_URL="http://127.0.0.1:9" packages/aiedu-mcp/.venv/Scripts/python.exe - <<'PY' 2>/dev/null | tee /dev/stderr | sed 's/^/  /' >> "$SUMMARY"
import base64, json
from aiedu_mcp import tools
spec = {"lesson_id": "x", "schema_version": "2.0", "activity_graph": [{"id": "n1", "type": "observe", "narration": "hi"}]}
out = tools.render_lesson(spec)
enc = out["url"].split("?spec=")[-1]
roundtrip = json.loads(base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4)))
print(json.dumps({"url_head": out["url"][:60], "roundtrip_ok": roundtrip == spec}, ensure_ascii=False))
PY
echo "" >> "$SUMMARY"

# 3) 浏览器层 E2E（真实课堂页）
step "3. 浏览器层：真实渲染课堂（48px/一屏一任务/不泄题/交互）"
( cd packages/aiedu-player && node ../../scripts/e2e_browser.mjs 2>/dev/null ) | tee /dev/stderr | grep -E "^\[(PASS|FAIL)\]" >> "$SUMMARY"

# 4) 三包回归 + 硬约束独立断言 + wheel 自检
step "4. 三包测试 + 硬约束断言"
echo "### aiedu-core（无 LLM env）" >> "$SUMMARY"
( cd packages/aiedu-core && env -u LLM_BASE_URL -u LLM_API_KEY -u LLM_MODEL_NAME .venv/Scripts/python.exe -m pytest -q --no-header 2>&1 | tail -1 ) | tee /dev/stderr | sed 's/^/  /' >> "$SUMMARY"
echo "### aiedu-mcp" >> "$SUMMARY"
( cd packages/aiedu-mcp && .venv/Scripts/python.exe -m pytest -q --no-header 2>&1 | tail -1 ) | tee /dev/stderr | sed 's/^/  /' >> "$SUMMARY"
echo "### aiedu-player（Playwright）" >> "$SUMMARY"
( cd packages/aiedu-player && npx playwright test 2>&1 | tail -1 ) | tee /dev/stderr | sed 's/^/  /' >> "$SUMMARY"
echo "### 硬约束 1/2/3 独立断言" >> "$SUMMARY"
packages/aiedu-core/.venv/Scripts/python.exe scripts/check_constraints.py | tail -1 | tee /dev/stderr | sed 's/^/  /' >> "$SUMMARY"

step "5. wheel 形态：干净安装 + 真实调用（发布前自检）"
bash scripts/verify_wheel.sh 2>&1 | grep -E "^\[wheel\]" | tee /dev/stderr | sed 's/^/  /' >> "$SUMMARY"

step "6. 使用日志统计（E2E 调用产生的真实 JSONL）"
if [ -f "$E2E/e2e-usage.jsonl" ]; then
  packages/aiedu-mcp/.venv/Scripts/python.exe packages/aiedu-mcp/scripts/usage_summary.py "$E2E/e2e-usage.jsonl" 2>/dev/null | tee /dev/stderr | sed 's/^/  /' >> "$SUMMARY"
fi

echo "" >> "$SUMMARY"
echo "--- 完成，总报告：$SUMMARY ---"
