# player 已迁出

课堂渲染器（player）已迁移到开源三包结构中的独立包：

- 位置：`packages/aiedu-player/`（包名 `@aiedu/player`）
- 浏览器侧 API：`renderLesson(container, spec, options?)`
- 渲染服务：`node server/serve.mjs`（`POST /lessons` → `{url}`）
- 断言：`npx playwright test`（含 48px / 一屏一任务等硬约束 5 断言）

本目录仅保留本说明，代码历史见 `git log --follow packages/aiedu-player/src/index.ts`。
