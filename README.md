# 数芽 aiedu · 数学可信教学引擎（给 AI Agent 用）

**一句话定位**：给 AI Agent 的数学教学引擎——**SymPy 独立核验** + **教学门禁** + **答案门控渲染**：
输入一道题，输出经过数学核验、先想后看、可交互渲染的课程规格（LessonSpec v2）。
LLM 只负责讲解，**数学对错不由模型判定**。

![数芽演示：真实 MCP 调用 → 真实渲染课堂](docs/assets/readme-demo.gif)

> GIF 为真实操作录制：浏览器里显示的是 MCP server 的**实际返回**（`verify_math` / `generate_lesson` /
> `render_lesson`），最后打开的是**真实渲染的课堂页**并真实作答。

## 快速开始（三行）

```bash
uvx aiedu-mcp                    # stdio：给 Claude Code / 任意 MCP 宿主用
uvx aiedu-mcp --transport http --port 8000   # HTTP：Streamable HTTP 端点 /mcp
```

接入配置（Claude Code `.mcp.json`）：

```json
{"mcpServers": {"aiedu": {"command": "uvx", "args": ["aiedu-mcp"]}}}
```

> **发布状态**：本仓库尚未发布到 PyPI（见文末「发布状态」）。想现在就试，走下面的「本地 5 分钟跑通」。

<details>
<summary>本地 5 分钟跑通（不依赖 PyPI）</summary>

```bash
git clone https://github.com/locis3321/aiedu && cd aiedu
python -m venv .venv && .venv/Scripts/python -m pip install -e packages/aiedu-core -e "packages/aiedu-mcp[dev]"
.venv/Scripts/python -m aiedu_mcp.server --transport stdio     # 或 --transport http --port 8000
```

渲染课堂（可选，`render_lesson` 用）：`cd packages/aiedu-player && npm ci && npm run build && npm run serve`

</details>

## 为什么需要它

AI 生成数学内容时，**"看起来对"是最危险的失败模式**。数芽把三条工程保证做成可机器验证的契约：

| 保证 | 机制 | 谁来验 |
|---|---|---|
| 数学对错不由模型判 | 受限 AST + SymPy 精确计算，输出核验凭据（verifier_version / claims / content_hash） | `verify_math`；`verified=true` 只能由核验产生 |
| 不编造 | 覆盖不了的题型**显式失败**（capability gap），不返回似是而非的课 | `generate_lesson` |
| 先想后看 | 未解锁节点的 `response.expected` 在服务端投影时置空 | `get_lesson(reveal="filtered")`，CI 独立 job 断言 |
| 儿童界面可用 | 可点元素 ≥48px、一屏一任务 | `aiedu-player` 的 Playwright 断言（真实渲染页） |

## 5 个 tool（工具面冻结）

⚠️ **层级约定（最容易踩的坑）**：`generate_lesson` 返回的是**信封** `{lesson_id, spec, verification}`；
`get_lesson` / `render_lesson` / `submit_attempt` 接收的是**信封里的 `spec` 本体**，不是整个信封。
传错会得到 `{"error":"invalid_input","hint":...}`（显式报错，不会静默返回坏数据）。

| tool | 入参 | 出参 | 说明 |
|---|---|---|---|
| `verify_math` | `expression: str`, `expected: str\|float` | `{result, verifier_version, claims, covered_claim_ids}` | `result` ∈ `verified / refuted / inconclusive / requires_review`；`claims` 是核验凭据（statement/status/method） |
| `generate_lesson` | `question: str`, `age: int?` | `{lesson_id, spec, verification}`（信封） | 调内核六阶段流水线；未覆盖题型 → `{error:"capability_gap", detail}` |
| `get_lesson` | `spec: dict`（**spec 本体**）, `reveal: "filtered"\|"full"`, `unlocked_ids: list[str]?` | `{spec, reveal}` | `filtered` 走 answer-filtered 投影：未解锁节点 `response.expected` 为 `null` |
| `submit_attempt` | `spec: dict`（**spec 本体**）, `node_id: str`, `answer: str`, `wrong_before: int=0` | `{correct, evidence, hint?}` | 服务端判分；`evidence` 仅两级 `independent` / `assisted`；答错给提示阶梯下一条 |
| `render_lesson` | `spec: dict`（**spec 本体**） | `{url, lesson_id}` | 交给 `aiedu-player` 渲染服务，返回可分享课堂 URL；服务不可用 → `{error:"player_unavailable"}`（**不返回假 URL**） |

## 能力覆盖与 capability gap（如实声明）

**当前零 LLM 覆盖 3 类题型**（确定性模板，答案由程序计算并经 SymPy 复验）：

| 题型 | 例 | 状态 |
|---|---|---|
| 凑十法（两位数 + 一位数，进位） | `16+8`、`23+9` | ✅ 出课 |
| 破十法（两位数 − 一位数，个位不够减） | `16-9`、`23-8`、`13-5` | ✅ 出课 |
| 分数等分概念（平均分成 N 份取 M 份） | "把蛋糕平均分成 4 份，取 1 份" | ✅ 出课 |

**未覆盖题型按环境如实处理**（这是特性不是缺陷——宁可说不会，也不编）：

- **无 LLM env**：未覆盖题型一律**显式失败**（`capability_gap`）：两位数 ± 两位数（`52-37`）、
  分数四则（`1/2+1/4`）、乘法**出课**（`7x8` 核验能过、出课不能）等。
- **配置了 LLM env**（可选路径）：模板外题面会走 LLM 自由设计出课（受控设计 + 语义校验 + 门禁），
  此时 `verified=true` 仍只来自 SymPy 核验——**LLM 只可能增加课程，不可能降低核验标准**。
- `verify_math` 本身覆盖加减乘除与 `× · ÷ x/X` 写法归一化（`7x8` / `7×8` / `7·8` 都能核验为 `56`）。

覆盖矩阵会随版本更新；未列出的题型请预期得到 `capability_gap`。

## Skills：教学编排知识（教 Agent 怎么教）

[`skills/teaching-math/`](skills/teaching-math/) 是给 Agent 的**教学编排技能包**：MCP 提供原子能力，
Skill 提供编排知识——什么时候调 `verify_math`、怎么把 `get_lesson(filtered)` 交给学生、
如何沿 `submit_attempt` 提示阶梯推进、拿到 `capability_gap` 怎么如实告知。
核心纪律（SKILL.md 内为显式禁止项）：**Agent 永不先看答案**、不绕过 MCP 直接 import 内核、
不内嵌题库、不预置答案、不夸大证据（坏例子：把 `refuted` 说成"不太对"）。

安装（三端同一份内容）：
- Claude Code：`cp -r skills/teaching-math ~/.claude/skills/`
- OpenCode：`cp -r skills/teaching-math ~/.config/opencode/skills/`
- WorkBuddy：`cp -r skills/teaching-math ~/.workbuddy/skills/`

## Examples：三个真实接入示例

| 示例 | 内容 | 真实转录 |
|---|---|---|
| [Claude Code](examples/claude_code_mcp.json) | `.mcp.json`（stdio）+ skill 安装 | [transcript](examples/transcripts/claude-code.md)：本机 API 连接失败（真实输出），复现步骤已备 |
| [OpenCode](examples/opencode.json) | `opencode.json` local MCP + skill | [transcript](examples/transcripts/opencode.md)：**真实会话 3 段**（成功半程/诚实失败/拒绝编造） |
| [WorkBuddy](examples/workbuddy-mcp.json) | `~/.workbuddy/mcp.json` 片段 + 用户级 skill | [transcript](examples/transcripts/workbuddy.md)：skill 已装，界面会话待主理人补登 |
| [协议级完整流程](examples/transcripts/protocol-level-full-flow.md) | 五关全链路（含一次答错取提示） | 由真实 MCP 调用逐条生成，可对照 Agent 会话 |

### 真实摩擦（转录里是证据，不是吐槽）

1. Agent 常把题面扩写成自然语言（"16-9 = ?（…退位减法…）"）——确定性模板只认纯算式 → 走 LLM 分支；
2. 且 **agentscope 与 fastmcp 硬冲突**（`mcp<2.0.0` vs `mcp>=2.0.0`），LLM 依赖不能与 MCP server 同环境，
   详见 `packages/aiedu-mcp/pyproject.toml` 注释（mcp venv 已用 `--no-deps` 实测可跑）。
   这是"模型想要自由设计、但工程上 LLM 路径与 MCP 层互斥"的核心摩擦，已列入遗留。
3. Agent 第一次传 `get_lesson` 的 spec 时改型损坏，**被 MCP 入参校验显式拒绝**（校验价值实证）。

## 仓库结构（三包）

```
packages/
  aiedu-core/    pip 库：意图识别 → SymPy 核验 → skill 检索 → 规划 → 编译 → 教学门禁
  aiedu-mcp/     MCP server（FastMCP）：5 个 tool，stdio + HTTP 双传输
  aiedu-player/  课堂渲染器（TS + GSAP，运行时依赖仅 gsap）+ 渲染服务
teaching-skills/ Claude-style 教学 skill 包（只读不执行）
examples/        接入示例（Claude Code / Claude Desktop 配置）
scripts/         CI 断言、发布与录制脚本
docs/            方案、任务书与决策记录
```

## 开发与 CI

```bash
# 内核
cd packages/aiedu-core && pip install -e ".[dev]" && pytest -q
# MCP 层
cd packages/aiedu-mcp && pip install -e ../aiedu-core -e ".[dev]" && pytest -q
# 渲染器（CI 内会自起渲染服务）
cd packages/aiedu-player && npm ci && npm run build && npx playwright test
# 硬约束断言（CI 独立 job）
python scripts/check_constraints.py
```

CI（`.github/workflows/ci.yml`）分 5 个 job：`aiedu-core · pytest`、**`硬约束断言（1/2/3）`**（独立可见，
逐条打印证据）、`aiedu-mcp · pytest + stdio 冒烟`、`aiedu-player · Playwright（硬约束 5）`、`构建 wheel 并校验`。
任何 job 失败都直接失败，不用 `continue-on-error` 掩盖。

## Roadmap

- **已发布能力**：见上（3 类确定性题型、5 个 tool、双传输、可分享课堂）
- **进行中**：确定性题型扩展（两位数 ± 两位数、乘法出课、分数四则）——按真实使用日志里的 `capability_gap` 频次排序
- **计划中**：MCP Registry 提交、PyPI 发布与 `uvx` 一条命令接入、外部用户反馈闭环
- **不做**：账号/积分/画像/报告/后台等外围域；OCR/TTS/题库接入；无核验的"看起来对"的内容

## 发布状态（诚实记录）

- PyPI：⏳ **未发布**。两个包（`aiedu-core`、`aiedu-mcp`）元数据完整、`twine check` 全 PASS；
  **wheel 安装自检已通过**（`bash scripts/verify_wheel.sh`：把 dist 里的 wheel 装进干净 venv，
  用已安装产物经 MCP 协议真实调用——三类题型全部出课、工具面为 5 个）。
  发布只差一个 API token：`bash scripts/release.sh testpypi` → `bash scripts/release.sh pypi`
  （token 只从环境变量读，不进代码、不进 git）。
- GitHub Actions：⏳ **未跑**。CI 配置已就绪（5 个 job，含硬约束独立断言 job），
  但本仓库尚未在 GitHub 建仓，因此暂无 run 链接。
- MCP Registry：⏳ **未提交**（提交素材见 `examples/mcp-registry-submission.md`；需仓库已在 GitHub）。
- 真实使用数据（D9–D10 观测期）：⏳ 尚未开始（引擎主理人自用观测，结果不随本仓库发布）。

## 安全模型与部署（无界面运行形态 v1）

**鉴权三档（按集成场景，未配置即不启用——零行为变化）**：

| 档 | 形态 | 鉴权 |
|---|---|---|
| (a) 本地 stdio | `uvx aiedu-mcp` / `python -m aiedu_mcp.server`（默认） | **零 token**。MCP 规范要求 stdio 不遵循 OAuth，凭据从 env 取；安全边界 = 操作系统进程本身。**勿把 stdio 暴露给不受信任的调用方** |
| (b) 小团队自建 HTTP | `--transport http --port 8000` | `AIEDU_AUTH_TOKEN` env 静态 Bearer。**注意：静态 token 模式不完全符合 MCP 规范对 HTTP 授权的完整要求（OAuth 2.1），适用于受信任网络；面向公网用演示档**。401 不带 `WWW-Authenticate` |
| (c) 托管演示档 | `AIEDU_RATE_LIMIT=1` + systemd/Caddy（见 `deploy/`） | **自服务注册制拿 token**：`POST /register`（零邮箱/密码，仅可选昵称，token 明文仅显示一次、服务端只存 SHA-256 哈希）→ Agent 配 Bearer 连 `/mcp`；`POST /revoke` 以该 token 本身为凭据自吊销；无账号概念（每次注册=一个新 token）。网页 demo 页（`/`）匿名可浏览 + IP 限流一次性试用（generate ≤10 次/时/IP） |

**红线（启动时硬拒绝）**：演示档 + LLM env + 未设 `AIEDU_AUTH_TOKEN` = 拒绝启动（防把 LLM 成本暴露给全互联网）；删 LLM env 或设 token 即恢复。
**配额**（per-token）：generate ≤20 次/时、≤300 次/月；verify ≤200/h；get/submit ≤500/h；render ≤200/h；全局日熔断 ≤20,000；单 token runaway >60 generate/h → rate_limited。超限返回结构化 `{"error":"rate_limited","retry_after":N}`——**capability_gap 语义不变**：无论匿名还是注册调用，未覆盖题型一律显式失败。

**env 一览**：`AIEDU_AUTH_TOKEN`（静态 token/拔网线）｜`AIEDU_PLAYER_URL`（渲染源，最高优先）｜`AIEDU_PUBLIC_URL`（跨代理/CDN 确定性 URL，拼 `{base}/player`）｜`AIEDU_RATE_LIMIT`（演示档总开关）｜`AIEDU_TRUST_PROXY`（XFF 首跳）｜`AIEDU_SERVE_PLAYER`/`AIEDU_PLAYER_DIST`（同域挂载 player）｜`AIEDU_AUTH_DB`（SQLite token 库）｜`AIEDU_REGISTER_RATE`、`AIEDU_RATE_LIMITS`（注册/配额覆盖）｜`AIEDU_USAGE_LOG`（调用日志）。`AIEDU_PLAYER_TIMEOUT` 已弃用（`render_lesson` 本地拼 URL，无服务端依赖）。

**部署 checklist**：① stdio：三行配置（见快速开始）；② 自建 HTTP：`AIEDU_AUTH_TOKEN` + 一行 header；③ 演示档：`deploy/` 四件套（systemd 最小硬化 + Caddy 自动 HTTPS + logrotate + `deploy-demo.sh`，`--dry-run` 自检）。`render_lesson` 的 URL 指向 player 静态托管（同域挂载），`POST /lessons` 仅保留给本地 serve 用户。

## 分享边界（诚实声明）

- **课堂 URL 是自包含的**：spec 以 base64url 编进查询串，静态页渲染、无服务端状态、不过期。
- **URL 含答案数据**（自习课堂）：请仅发给信任的学习者；"先想后看"由交互层保障（答对才推进），
  数据层可解码是**已知且接受的边界**（威胁模型：受众是 6–9 岁孩子，`base64` 解码率趋近于零）。
- **无答案预览**（发给不打算让孩子看的人）：先 `get_lesson(filtered)` 再 `render_lesson`——页面顶部
  有诚实横幅"本预览不含答案与自动判定"，作答不判定。
- 超长链接（约 5–6KB）在部分 IM 中无预览卡片，链接本身可点击打开，属正常。

## 商业化透明（现在就预告，不做 surprise）

- 本仓库**永久开源、功能等价承诺**：你自建部署跑的每一行代码与托管演示服务是**同一份代码**
  （Apache-2.0）；商业版卖的是运维面（托管容量/配额/SLA/支持），**不拥有任何私有教学功能**——
  题型模板、核验逻辑、教学门禁全部跟 core 开源。
- License：Apache-2.0 不变；按 Apache-2.0 授权的贡献可同时用于商业托管，无需 CLA。
- 路线图已写明本仓库包含托管演示服务与自服务注册制 token 发放；商业托管在路线图上（阶段触发
  用可观测数字：连续 2 周去重活跃注册 token ≥50/周等，详见引擎主理人文档）。
- **数据透明**：调用日志仅以 token 哈希 / IP 哈希（`anon:<sha256(ip)[:12]>`）形式记录，用于配额、
  去重与 gap 排序；**不存原文 IP、不做画像、不售卖、不收集未成年人个人信息**（与 README 免责口径一致）。

## License

[Apache-2.0](LICENSE) © 2026 aiedu contributors
