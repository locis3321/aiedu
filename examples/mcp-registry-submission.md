# MCP Registry 提交素材（aiedu-mcp）

> 用途：向 `modelcontextprotocol/servers`（官方 community registry）提交 PR 时直接引用。
> 当前状态：**未提交**（需仓库已在 GitHub，且 aiedu-mcp 已发布到 PyPI）。
> 提交前请把下面 `<占位>` 替换为真实值，并核对最新提交规范（registry 会变）。

## 仓库

- 源码：`https://github.com/locis3321/aiedu`
- MCP server 包：`https://pypi.org/project/aiedu-mcp/`
- 内核库：`https://pypi.org/project/aiedu-core/`

## 名称与描述

- **name**: `aiedu`
- **description**:
  > 数学可信教学引擎（中文）：给 AI Agent 的 MCP server。SymPy 独立核验数学对错（模型只讲解、不判定），
  > 教学门禁保证"先想后看"与不编造，答案门控渲染成可分享的可交互课堂。未覆盖题型显式 capability gap。

## 安装与运行

```bash
# stdio（Claude Code / Claude Desktop / 任意 MCP 宿主）
uvx aiedu-mcp
# 或
pip install aiedu-mcp && aiedu-mcp --transport stdio

# HTTP（Streamable HTTP，端点 /mcp）
uvx aiedu-mcp --transport http --port 8000
```

宿主配置示例（Claude Code `.mcp.json`）：

```json
{"mcpServers": {"aiedu": {"command": "uvx", "args": ["aiedu-mcp"]}}}
```

可选环境变量：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_NAME`（LLM 为**可选**路径；
未配置时已覆盖题型零 LLM 出课）、`AIEDU_PLAYER_URL`（课堂渲染服务地址）、`AIEDU_USAGE_LOG`（使用日志 JSONL）。

## 工具（5 个，工具面冻结）

| tool | 入参 | 出参 | 说明 |
|---|---|---|---|
| `verify_math` | `expression: str`, `expected: str\|float` | `{result, verifier_version, claims, covered_claim_ids}` | SymPy 精确核验；`result` ∈ verified/refuted/inconclusive/requires_review |
| `generate_lesson` | `question: str`, `age?: int` | `{lesson_id, spec, verification}` | 生成已核验的 LessonSpec v2；未覆盖题型 → `{error:"capability_gap"}` |
| `get_lesson` | `spec: dict`, `reveal: "filtered"\|"full"`, `unlocked_ids?: list[str]` | `{spec, reveal}` | filtered 投影：未解锁节点不含答案字段（先想后看） |
| `submit_attempt` | `spec: dict`, `node_id: str`, `answer: str`, `wrong_before?: int` | `{correct, evidence, hint?}` | 服务端判分；证据两级 independent/assisted |
| `render_lesson` | `spec: dict` | `{url, lesson_id}` | 可分享的可交互课堂 URL（需 aiedu-player 渲染服务） |

⚠️ 层级约定：`generate_lesson` 返回信封 `{lesson_id, spec, verification}`；其余 tool 接收 `spec` 本体。

## 依赖与许可

- 依赖：`fastmcp==4.1.3`、`aiedu-core>=0.1.0`（运行时依赖仅 `sympy` + `pydantic`）
- License：Apache-2.0
- 支持：Python ≥3.12；stdio 与 HTTP 双传输

## 提交检查清单（提交前逐项确认）

- [ ] 仓库已在 GitHub 公开且 `README.md` 首屏可用
- [ ] `aiedu-core` / `aiedu-mcp` 已发布到 PyPI，且 `uvx aiedu-mcp` 实测可调用
- [ ] 上表所有占位已替换为真实链接
- [ ] registry 当前提交规范（目录结构 / README 字段）已核对
- [ ] 提交后在本文件登记 PR 链接与状态
