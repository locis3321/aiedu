# aiedu

给 AI Agent 的数学教学引擎：输入一道数学题，输出经 **SymPy 独立核验**、**答案门控（先想后看）**、可交互渲染的课程规格（LessonSpec v2）。

## 快速开始（自建部署）

PyPI 尚未发布，从仓库安装：

```bash
git clone https://github.com/locis3321/aiedu.git && cd aiedu
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -e packages/aiedu-core -e packages/aiedu-mcp
# 其它:    .venv/bin/python -m pip install -e packages/aiedu-core -e packages/aiedu-mcp
# 可选：LLM 路径（配置后未覆盖题型走受控自由设计，而非 capability_gap）
#   （同上 pip 命令，包名加 [llm]：packages/aiedu-core[llm] 与 packages/aiedu-mcp[llm]）

# 启动 stdio（Claude Code / 任意 MCP 宿主）
.venv/bin/python -m aiedu_mcp.server --transport stdio
# 或 HTTP：
.venv/bin/python -m aiedu_mcp.server --transport http --port 8000
```

Claude Code `.mcp.json`（命令用你的安装路径）：

```json
{"mcpServers": {"aiedu": {
  "command": "/path/to/aiedu/.venv/bin/python",
  "args": ["-m", "aiedu_mcp.server", "--transport", "stdio"]}}}
```

![演示](docs/assets/readme-demo.gif)

## 工具

| 工具 | 说明 |
|---|---|
| `verify_math` | 表达式精确计算核验（加减乘除，支持 `× · ÷ x/X` 写法归一化） |
| `generate_lesson` | 生成已核验课程，返回 `{lesson_id, spec, verification}` |
| `get_lesson` | `reveal="filtered"` 时未解锁节点 `response.expected` 为 `null`（先想后看） |
| `submit_attempt` | 服务端判分（`evidence` 仅 `independent`/`assisted`）+ 提示阶梯 |
| `render_lesson` | spec → 可分享课堂 URL（spec 自包含，无服务端状态） |

注意：`generate_lesson` 返回的是信封 `{lesson_id, spec, verification}`；其余工具接收其中的 `spec` 字段。

## 能力边界

确定性覆盖：凑十法（`16+8`）、破十法（`16-9`）、分数等分概念（"平均分成 N 份取 M 份"）。
其余题型（如 `52-37`、`1/2+1/4`、乘法出课）：未配置 LLM 时显式返回 `capability_gap`；配置 LLM（`[llm]` extra）时走受控自由设计（计算与结构仍经核验与门禁），均不猜测。

## HTTP 传输与鉴权（可选）

```bash
.venv/bin/python -m aiedu_mcp.server --transport http --port 8000
```

- `AIEDU_AUTH_TOKEN`：静态 Bearer token（未设置则不启用）
- 托管档：`POST /register` 自服务注册 token（仅昵称可选、零密码），`POST /revoke` 自吊销；配额与限流见 `deploy/`

## 仓库结构

```
packages/aiedu-core     内核（pipeline / intent / verify / strategies / policy / skills）
packages/aiedu-mcp      MCP server（FastMCP，stdio + HTTP）
packages/aiedu-player   课堂渲染器（TS + GSAP）+ 渲染服务
skills/teaching-math    教学编排技能（~/.claude/skills/ 等，三端同构）
```

## 开发

```bash
cd packages/aiedu-core && pip install -e ".[dev]" && pytest -q
cd packages/aiedu-mcp && pip install -e ../aiedu-core -e ".[dev]" && pytest -q
cd packages/aiedu-player && npm ci && npm run build && npx playwright test
```

## License

[Apache-2.0](LICENSE)

