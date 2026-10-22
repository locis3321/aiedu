# OpenCode 真实会话记录（transcript）

> 环境：`opencode run`（OpenCode 1.19.1，模型 MiniMax-M3，真实调用）｜ 记录于 2026-10-21
> 本目录下所有记录均来自**真实执行**（工具调用、报错、模型措辞均为原文摘录），无剧本。
> ⚠️ 如实标注：opencode 会话中 aiedu 本地 MCP server 的注册不稳定（有时成功、有时丢失），
> 且该模型工具发现能力偏弱——两者都是**真实摩擦**，也是本阶段最重要的观测结果。

## 记录 1：成功半程（真实生成课程并交付第一关，未先看答案）

用户（家长）："请用 teaching-math 技能（数芽 aiedu MCP server）带我学 16-9……"（完整提示原文见对话记录）

```
⚙ use_skill {"skill":"teaching-math"}
⚙ aiedu_generate_lesson {"question":"16-9","age":7}
⚙ aiedu_get_lesson {"spec":{"learning_objectives":[...],"lesson_id":"borrow-ten-16-minus-9",
                     "schema_version":2,"verification":{"verified":true}},"reveal":"filtered","unlocked_ids":[]}  ← 第一次
✗ aiedu_get_lesson {...} failed
  Error: 11 validation errors for call[get_lesson]  ← 它把自己构造的损坏 spec 传入，**被 MCP 入参校验显式拒绝** ✓
⚙ aiedu_get_lesson {"reveal":"filtered","unlocked_ids":[],"spec":{...完整原始 spec...}}   ← 第二次，成功
　
我已生成破十法拆解 16-9 的四关课堂。先把第一关交给孩子——
**第 1 关：** 小松鼠有 16 颗松果，每 10 颗装成一捆。零散着（不够一捆）的有几颗？
先把你想的答案告诉我。
```

**判定**：✅ 真实出课（`borrow-ten-16-minus-9`，verified=true）→ ✅ `filtered` 投影交出第一关 → ✅ **Agent 没有先看答案**（skill 纪律生效）。
**真实摩擦 1**：Agent 第一次传 spec 时把 schema 字段改型（`schema_version: 2` 整数、部分节点改写成 `{item:[...]}`），被 `get_lesson` 的入参校验拒绝；第二次传**原始 spec** 才过。→ 证明校验在真实调用中拦住了坏数据。

## 记录 2：题面被改写 → 模板不命中 → LLM 依赖缺失（已修）

```
⚙ aiedu_generate_lesson {"question":"16-9 = ?（小学一年级退位减法，用破十法）","age":7} failed
  Error: ... LLM configured but agentscope not installed (install aiedu-core[llm])
⚙ aiedu_generate_lesson {"question":"16-9 用破十法怎么算？"} failed（同上）
服务器问题，无法生成课程……我**不会**自编课程代替编排。
```

**判定**：⚠️ 诚实失败 ✓（模型没有编课）。**真实摩擦 2**：Agent 往往把题面扩写成自然语言（"16-9 = ?（…退位减法…）"），
确定性模板只认纯算式 → 模板不命中 → 走 LLM 分支 → 依赖缺失报错。
**根因已查明并处理**：mcp venv 缺 agentscope（本仓 venv 的 `[llm]` 从未真正安装成功——因为 D13–D14 查明
**agentscope 2.0.9 与 fastmcp 4.1.3 硬冲突**：前者要 `mcp<2.0.0`，后者要 mcp≥2.0.0）。已在 mcp venv 用
`pip install --no-deps agentscope==2.0.9` 实测通（mcp SDK 保持 2.3.0，LLM 自由设计出课成功）。

## 记录 3：工具未连接 → 模型拒绝编造（最佳证据）

```
⚙ use_skill {"skill":"teaching-math"}
⚙ read_skill_file {"skill":"teaching-math","filename":"references/mcp-tools.md"}
⚙ list_mcp_resources MCP resources   ← 返回空
**无法开始：`aiedu` MCP server 没有连到当前会话。** ……按 teaching-math 的纪律，判分、提示阶梯、
independent/assisted 证据词都只能由服务端产出。我不会自己心算 16-9 去"判"你那 5 个答案，
也不会假装跑了一遍流程——那等于编造教学证据，比不做更糟。
```

**判定**：✅ 这是 skill 纪律在真实模型上的最佳表现：**拒绝编造**，并指出要修的是连接。

## 主理人复现步骤（本地已装好）

```bash
cd /tmp/aiedu-session2        # 或任意目录，放下面 opencode.json
cat > opencode.json <<'EOF'
{"$schema":"https://opencode.ai/config.json",
 "mcp":{"aiedu":{"type":"local","enabled":true,
   "command":["D:/work/aiedu/packages/aiedu-mcp/.venv/Scripts/python.exe","-m","aiedu_mcp.server","--transport","stdio"]}}}
EOF
opencode run "我是家长，请用 teaching-math 技能带我学 16-9……（完整提示见本文件开头，含学生五关答案）"
```
