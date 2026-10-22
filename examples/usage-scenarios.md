# 主理人自用（D9–D10）：接入配置与日常场景

## 1. 接入（Claude Code）

把 `claude_code_mcp.json` 内容合并到项目的 `.mcp.json`（或用户级 `~/.claude.json`），
或直接用命令：

```bash
claude mcp add aiedu --env AIEDU_USAGE_LOG=D:/work/aiedu/.aiedu-usage.jsonl -- uvx aiedu-mcp
```

本地开发（未发布 PyPI 时）用 `aiedu-local` 那条（指向仓库 venv）。
渲染课堂需另起渲染服务（`render_lesson` 用）：

```bash
cd packages/aiedu-player && npm ci && npm run build && npm run serve   # 127.0.0.1:8130
```

未设 `AIEDU_USAGE_LOG` 时**不落盘**、行为完全不变；设了则每次 tool 调用写一行 JSONL。

## 2. 三个日常场景

| 场景 | 怎么用 | 期望 |
|---|---|---|
| ① 教孩子作业：核验一道退位减法 | `verify_math("16-9", 7)` | `result=verified`，claims 给出算式依据 |
| ② 生成一节分数等分课 | `generate_lesson("把一个蛋糕平均分成4份，取1份是多少？")` → 拿 `spec` → `render_lesson(spec)` | 出课（verified=true）并拿到可分享课堂 url |
| ③ 抽查 AI 生成的数学解释 | `verify_math("1/2+1/4", "3/4")` | `result=verified`；若解释算错则 `refuted` |

每天把当天的真实使用记进 `docs/memory/usage-log-YYYY-MM-DD.md`（模板见同目录）。
**禁止为了凑数造调用**——表演性使用会让止损判据失去意义（RC7）。

## 3. 周期结束时怎么出数

```bash
python packages/aiedu-mcp/scripts/usage_summary.py D:/work/aiedu/.aiedu-usage.jsonl
```

输出：总调用数 / 成功率 / capability_gap 触发率 / 各 tool 与题型分布 / 耗时 / 按天分布。
把这张表贴进 `docs/memory/D9-D10-stoploss-report.md` 作为 P0/P1/P2 的证据。
