#!/usr/bin/env bash
# 本地演示档（体验用）：demo 页匿名试用 + 自服务注册 token 接 MCP + 同域渲染课堂。
#
# 形态与线上演示档一致（同一代码同一配置语义）：
#   AIEDU_RATE_LIMIT=1（演示档开关）｜ AIEDU_SERVE_PLAYER=1（/player 同域挂载）｜
#   无 LLM env（红线：演示档不得配 LLM；未覆盖题型如实 capability_gap）
# 用法：bash scripts/run-demo-local.sh [port]   （默认 8000）
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${1:-8000}"
PLAYER_DIST="$PWD/.stage-player-site"  # Windows Python 需要 Windows 路径（mktemp 的 /tmp 不可见）

if [ ! -f "$PWD/packages/aiedu-player/dist/player.js" ]; then
  echo "== 构建 player dist =="
  (cd packages/aiedu-player && npm ci >/dev/null && npm run build)
fi
# 站点布局与 serve.mjs 一致：dist/player.js + lesson.html（模板相对引用 dist/player.js，
# 同域挂载下解析为 /player/dist/player.js，8130 形态下为 /dist/player.js）
rm -rf "$PLAYER_DIST" && mkdir -p "$PLAYER_DIST/dist"
cp -r "$PWD/packages/aiedu-player/dist/." "$PLAYER_DIST/dist/"
cp "$PWD/packages/aiedu-player/templates/lesson/index.html" "$PLAYER_DIST/lesson.html"

echo "== 启动演示档 http://127.0.0.1:$PORT =="
echo "   演示页:    http://127.0.0.1:$PORT/            （匿名可浏览，generate ≤10 次/时/IP）"
echo "   注册 token: curl -X POST http://127.0.0.1:$PORT/register -H 'content-type: application/json' -d '{}'"
echo "   MCP 端点:  http://127.0.0.1:$PORT/mcp          （Bearer <token>；initialize/tools 需 token）"
echo "   停止:      Ctrl+C 或 kill 本进程"

env \
  -u LLM_BASE_URL -u LLM_API_KEY -u LLM_MODEL_NAME \
  AIEDU_RATE_LIMIT=1 \
  AIEDU_SERVE_PLAYER=1 \
  AIEDU_PLAYER_DIST="$PLAYER_DIST" \
  AIEDU_PLAYER_URL="http://127.0.0.1:$PORT/player" \
  AIEDU_PLAYER_TIMEOUT=5 \
  packages/aiedu-mcp/.venv/Scripts/python.exe -m aiedu_mcp.server --transport http --host 127.0.0.1 --port "$PORT"
