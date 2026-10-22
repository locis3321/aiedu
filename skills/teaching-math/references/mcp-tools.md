# 数芽 MCP 工具速查（本技能唯一可用的 5 个工具）

工具 ID 以 MCP server 名称为前缀：`aiedu_verify_math`、`aiedu_generate_lesson`、
`aiedu_get_lesson`、`aiedu_submit_attempt`、`aiedu_render_lesson`
（若你的宿主把 server 命名为其它名字，前缀随之变化；工具本体永远只有这 5 个）。

| 工具 | 入参 | 出参要点 |
|---|---|---|
| `aiedu_verify_math` | `expression`（如 "16-9"）、`expected`（数值或字符串） | `result`: verified / refuted / inconclusive / requires_review；`claims` 为核验凭据 |
| `aiedu_generate_lesson` | `question`（题面或教学请求）、`age` 可选 | **信封** `{lesson_id, spec, verification}`；未覆盖题型 → `{error:"capability_gap", detail}` |
| `aiedu_get_lesson` | `spec`（**信封里的 spec 本体**，不是信封）、`reveal: "filtered"\|"full"`、`unlocked_ids` 可选 | `{spec, reveal}`；filtered 下未解锁节点的 `response.expected` 为 null |
| `aiedu_submit_attempt` | `spec`（spec 本体）、`node_id`、`answer`、`wrong_before` 可选 | `{correct, evidence: "independent"\|"assisted", hint?}`；答错时 `hint` 是提示阶梯下一句 |
| `aiedu_render_lesson` | `spec`（spec 本体） | `{url, lesson_id}` 可分享课堂；服务不可用 → `{error:"player_unavailable"}` |

## 编排流程（照此执行）

1. `aiedu_generate_lesson({question})` → 若 `error:"capability_gap"`，如实告知用户"这个题型暂不支持"，结束。
2. 取返回里的 **`spec` 字段**（不要整个信封）→ `aiedu_get_lesson({spec, reveal:"filtered", unlocked_ids:[]})` 交给学生。
3. 学生作答 → `aiedu_submit_attempt({spec, node_id, answer, wrong_before})`；
   - `correct:true, evidence:"independent"` → 反馈"独立答对"，把该节点 id 加入 unlocked_ids，进入下一节点；
   - `correct:false, evidence:"assisted"` → 转述 `hint`（不要自己解释/说答案），wrong_before +1 后再试；
   - `error:"no_programmatic_answer"` → 如实说该步需人工看，不猜。
4. 全部节点达标 → `aiedu_get_lesson({spec, reveal:"full"})` 给学生看完整讲解。
5. 收束抽查：换一个数对用 `aiedu_verify_math` 确认学生不是背的。

服务器名示例（Claude Code / OpenCode 配置见仓库 `examples/`）。
