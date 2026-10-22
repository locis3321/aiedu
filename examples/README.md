# aiedu-mcp 接入示例

三行配置（Claude Desktop / 支持 mcpServers 的宿主）：

```json
{"mcpServers": {"aiedu": {"command": "uvx", "args": ["aiedu-mcp"]}}}
```

或用于 Claude Code（`.mcp.json` / `claude mcp add`）：

```json
{"mcpServers": {"aiedu": {"command": "uvx", "args": ["aiedu-mcp"]}}}
```

本地开发（未发布 PyPI 时）用 venv 直连：

```json
{"mcpServers": {"aiedu": {"command": "D:\\work\\aiedu\\packages\\aiedu-mcp\\.venv\\Scripts\\python.exe",
                           "args": ["-m", "aiedu_mcp.server", "--transport", "stdio"]}}}
```

工具面（5 个，冻结）：`verify_math` / `generate_lesson` / `get_lesson` / `submit_attempt` / `render_lesson`。

可选环境变量（LLM 为可选路径，未配置时已覆盖题型零 LLM 出课）：
`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_NAME`；`AIEDU_SKILLS_DIR`（teaching-skills 路径覆盖）；
`AIEDU_PLAYER_URL`（渲染服务地址，缺省 `http://127.0.0.1:8130`；未启动时 `render_lesson` 显式返回 `player_unavailable`）。

渲染服务（`render_lesson` 依赖）：

```bash
cd packages/aiedu-player && npm ci && npm run build && npm run serve   # http://127.0.0.1:8130
```

HTTP 传输：`python -m aiedu_mcp.server --transport http --port 8000`（MCP Streamable HTTP 端点 `/mcp`）。
