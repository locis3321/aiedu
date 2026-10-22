# AGENTS.md — aiedu · 开源数学教学引擎（MCP/Skill）

本文件供 AI 编程助手（Claude Code / Cursor / OpenCode / 其他 agentic 工具）在本仓库工作时读取。它只承载**定位与硬约束**；重组计划与排期见 [`docs/开源转型方案-v1.md`](docs/开源转型方案-v1.md)，转型依据见 `deliverables/software-company/aiedu-review-2026-10-20.md`。

## 项目是什么

**一句话**：给 AI Agent 的"数学可信教学引擎"——输入一道题，输出**经过独立数学核验的、答案门控的（先想后看）、可交互渲染的课程规格（LessonSpec v2）**。

- **交付形态**：三个开源包 + 一个 skill 集：
  - `packages/aiedu-core`：pip 库，六阶段生成流水线（intent → SymPy 核验 → skill 检索 → 规划 → 编译 → 教学门禁）。依赖仅 sympy / pydantic / httpx(可选)。
  - `packages/aiedu-mcp`：MCP server（FastMCP，stdio + HTTP），暴露 5 个 tool：`verify_math` / `generate_lesson` / `get_lesson` / `submit_attempt` / `render_lesson`。
  - `packages/aiedu-player`：TS + GSAP 播放器，spec → 可分享可交互课堂 URL。
  - `teaching-skills/`：Claude-style Teaching Skill 包（make-ten / borrow-ten / fraction-equal-parts）。
- **核心原则**：LLM 只解释、不判定；数学对错由 SymPy 独立核验；教学方法由确定性模板与程序化门禁驱动。
- **不宣称**：不宣称覆盖 K12 数学路线（当前确定性覆盖 3 个知识点，覆盖矩阵在 README 明示）；不输出"掌握度百分比"式伪精确；不处理未成年人数据与合规（README 免责，集成方承担）。

不做：C 端小程序产品、账号/积分/画像/报告/运营后台、OCR/TTS/题库接入、无核验的"看起来对"的内容、绕过尝试直接吐完整解法的接口。

## 历史与归档

- **本方向**：2026-10-20 用户确认，取代 C 端产品路线（旧 C 端方案与任务包原文件保留在本地归档分支 `archive/pre-opensource-2026-10-20`，不在公开分支）。
- **归档分支**：`archive/pre-opensource-2026-10-20` 保存转型前完整代码（含 accounts/points/admin_api/miniprogram 等外围域）；重组时从该分支按需取回，不在主分支复活外围域。

## 硬约束（5 条，全部 CI 可验证，违者视为未完成）

1. **先想后看 = API 语义**：`get_lesson(reveal="filtered")` 返回的 spec 中，未解锁节点的 `response.expected` 必须为 `null`。CI 断言：对任意生成的 spec 做 filtered 投影，断言未解锁节点不含答案字段。
2. **verified 仅由核验产生**：`verified == true` 只能出自 SymPy 核验（附核验凭据：verifier_version / claims / content_hash）；LLM 输出与外部输入都无权置 true；`verified == true` 的数学内容视为只读，改动必须重新核验。
3. **不编造、不发明来源**：确定性模板覆盖外的题型，无 LLM key 时显式报能力缺口（capability gap），不降级、不猜测；核验失败就返回 `verified: false` 与原因。
4. **证据只用两级**：independent / assisted；一次答对 ≠ 已掌握，任何输出不得表述为掌握度数值。
5. **儿童界面可用性断言**：player 渲染页面所有可点元素 ≥48px、单指可操作、一屏一个学习任务；作为 Playwright 断言进 CI。

## 生成链路原则（intent-first，保持不变）

用户输入 → 内置意图识别（规则，先于一切 skill 检索）→ SymPy 核验（解题类硬前提）→ skill 检索 → 全局教学政策 + skill 方法 → 编译 LessonSpec v2（语义校验两轮修复上限）→ 程序化教学门禁（先想后看门槛/选择题退化/年龄适配，BLOCKER/MAJOR/MINOR 分级）。

- 通用教学规范内置在系统政策中，不散落在 skill 里；生成式检查优先于选择题。
- skill 加载器**只读文本，不执行** skill 中任何脚本。
- 新增确定性 strategy 时必须附带：该题型的核验用例 + filtered 投影断言（硬约束 1）；缺任一视为未完成。

## AI 协作规则

- 修改 `aiedu-core` 任何生成/核验逻辑，必须跑通对应 pytest 后再提交；CI = pytest + filtered-null 断言 + Playwright。
- 不要引入新依赖（核心库锁定 sympy/pydantic/httpx）；MCP 层锁定 fastmcp。重大选型先记入 `docs/开源转型方案-v1.md` 的决策更新。
- 涉及 LLM Provider/密钥的代码不得把密钥写入日志、prompt 或提交历史；LLM 永远是可选路径，删除 LLM env 后全链路（已覆盖题型）必须可跑。
- 不要修改已核验的数学内容；不要新增第 6 个 MCP tool（工具面冻结，扩展需先更新方案文档）。
- 修改动画渲染逻辑时，必须包含"值变化时是否有插值动画"的验证；修改交互问答逻辑时，必须包含"是否存在预测优先门槛"的验证。
- 文档纪律：全项目文档 ≤5 个文件；规范即 CI 断言，不新增流程性文档（任务/决策记录只保留在本地，不随本仓库发布）。
