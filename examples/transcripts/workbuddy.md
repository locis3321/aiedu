# WorkBuddy 会话记录（transcript）

> 状态：**本机无 workbuddy CLI**（无法脚本化会话），因此本期完成「skill 安装 + 配置」并给出复现步骤；
> 真实会话转录待主理人在 WorkBuddy 界面复现后补登。

## 已就绪的部分（真实证据）

1. **Skill 已安装到用户级**：`~/.workbuddy/skills/teaching-math/SKILL.md` + `references/mcp-tools.md` ✓
   （与仓库内既有技能 `agent-browser-core`、`arxiv-reader` 同目录，格式一致）。
2. **MCP 配置格式已按本机实证**：`~/.workbuddy/mcp.json` 使用 `mcpServers` + `type: "stdio"` + command/args/env
   （与 Claude Desktop 同构）。

## 配置片段（加入 `~/.workbuddy/mcp.json` 的 `mcpServers`）

```json
"aiedu": {
  "type": "stdio",
  "command": "D:/work/aiedu/packages/aiedu-mcp/.venv/Scripts/python.exe",
  "args": ["-m", "aiedu_mcp.server", "--transport", "stdio"],
  "env": {"AIEDU_PLAYER_URL": "http://127.0.0.1:8130"}
}
```

## 主理人复现步骤

1. 把上面片段合并进 `~/.workbuddy/mcp.json`（注意 JSON 逗号）；
2. 确认 `~/.workbuddy/skills/teaching-math/SKILL.md` 存在；
3. 在 WorkBuddy 对话里说：“用 teaching-math 带我学 16-9，先别给答案”；
4. 把完整会话（用户提问 → agent 调 tool → 判分 → 反馈 → 完整讲解）贴回本文件并登记日期。

> 会话记录位置（待补）：
> 日期：＿＿＿＿ ｜ 场景：＿＿＿＿ ｜ 结果是否符合预期：＿＿＿＿ ｜ 不爽的点：＿＿＿＿（如实）
