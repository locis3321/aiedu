# 阶段交付范围声明（DELIVERY.md）

## 阶段信息

- 阶段名称: product-redesign-p0（产品重设计首版）
- 阶段目标: 数芽家庭数学学习产品 P0 全链路——账号监护、学习闭环与证据、积分成长、题库与练习安排、能力画像、足迹与家长报告、运营后台（后端+Web前端）、小程序端骨架（课堂承载 spike）
- 对应需求条目: T2-T9 + T12（任务包 docs/memory/tasks-2609-2817-13）
- 替代关系: 本声明替代旧阶段 `python-service-migration`（DELIVERY.md 旧版），旧阶段为内核能力基线，已归档于 c00d186；新实现恢复内核并扩展产品层

## 构建与运行

- 构建命令: `cd projects/backend && uv sync`；player `cd projects/app/player && npm install && npm run build`
- 启动命令: `cd projects/backend && uv run uvicorn app.api.main:app --port 8000`；
  `uv run celery -A app.workers worker -l info --pool=solo`；`uv run python -m app.jobs.dispatcher`
- Web 运营后台: http://127.0.0.1:8000/admin/（FastAPI 挂载 projects/admin，同源）
- 服务端口: `8000`
- 健康检查端点: `/healthz`
- 依赖服务: PostgreSQL16（compose postgres）+ Redis（宿主6380）+ LLM（环境变量）+ Playwright chromium

## 功能清单（本阶段声明范围）

| 功能 ID | 描述 | 端点/模块 | 实现状态 |
|---|---|---|---|
| T2 | 账号监护与孩子档案（短信dev登录/监护同意/档案CRUD/切换/时长设置） | projects/backend/app/accounts + sms | 已实现 |
| T3 | 学习闭环与证据（会话/尝试判定/答案过滤/提示阶梯/证据分级/六阶段进度/hash复用/Gate契约/**发布门禁**） | projects/backend/app/learning | 已实现 |
| T4 | 积分与成长（账本/R7'幂等/规则版本化/上限；兑换P2预留） | projects/backend/app/points | 已实现 |
| T5 | 题库与练习安排（内置题审核态/题庄在线题库接入/三类试卷/按画像安排/L1L2路线/变式核验） | projects/backend/app/questionbank + tizhuang | 已实现 |
| T6 | 足迹与家长报告（四级分列/画像投影/试卷解释/导出删除/分享脱敏预览） | projects/backend/app/reports | 已实现 |
| T7 | 运营后台（角色矩阵/发布门禁/Skill安全门/提示词/AI形象/短信模板/**题库·题源·积分规则·安全反馈管理**/**TTS 配置（MiMo 主 + edge-tts 备，供应商/音色可配 + 试听）**/**模型配置（API Key 加密入库、模型名/base_url/温度/超时，路由 DB 优先）**/**系统参数与凭据面板（短信防刷/Token有效期/Grafana/题庄URL/存储/微信/MiMo/S3 凭据，DB 优先 env 回退）**/试卷治理/审计/Trace） | projects/backend/app/admin_api + projects/admin + app/tts + app/services/llm_router + app/core/runtime_config | 已实现 |
| T8 | 小程序儿童端骨架 + **课堂承载 spike**（web-view/iframe选定）+ 伙伴导航占位 | projects/app/miniprogram + h5-lesson-spike | 骨架已实现（spike 浏览器验证通过；端上未接入项见未实现清单；真机项待验证） |
| T9 | 小程序家长端骨架（登录短信dev/学习报告·显式选孩子） | projects/app/miniprogram/pages/parent | 骨架已实现（其余端上未接入项见未实现清单；真机项待验证） |
| T12 | 能力画像（四维度×证据带/程序化聚合/版本化快照/banned-phrase） | projects/backend/app/profile | 已实现 |
| T11 | 集成 E2E（三条跨端旅程）+ DELIVERY.md | tests/test_journey.py | 已实现 |

> 状态仅允许：已实现 / 未实现（未实现不得纳入本阶段交付）。

## 未实现（明确排除，不纳入声明）

- P2：商城兑换目录、第三方题源实际接入验证后启用、订阅消息接入——仅预留模块与"未接入"呈现
- **TTS 端上播放**——TTS 服务已接入（MiMo-V2.5-TTS 主，官方免费期；edge-tts 备，可选依赖 `uv sync --extra tts`；管理端可切供应商/音色/语速并试听；key 优先从后台"凭据"面板读取（Fernet 加密入库，仅显示尾号），未配置回退环境变量 `MIMO_API_KEY`），课程讲解端上播放未接入
- **AI形象/成长挚友的端上实现**——原型与配置界面已有，端上未接入；小程序伙伴页显式"待接入"，不假装可用
- OCR拍题识别、语音输入——入口预留，显式"待接入"
- 家长周报——暂缓候选
- **小程序端上缺口**：课堂页为 spike（本地 H5，未对接 T3 session/answer-filtered API）；时长保护端上执行与家长时长设置 UI；分享 UI（链接分享含访问范围/有效期/撤销）；诊断卷/试卷入口；R4 方法来源标识端上展示；成长页积分流水；陪伴使用管理；数据导出/删除入口
- **链接分享（访问范围/有效期/撤销）**——`share_preview` 仅返回脱敏预览快照并显式 `link_sharing: not_connected`，不伪造可撤销令牌；创建/撤销需分享链接表（DDL 授权后）
- **A5 知识点前置关系**——`knowledge_nodes` 无前置字段，L2 补洞按学段/年级近似；edges 表待教研数据接入（DDL 授权后）

## 测试账号与本地验收

- **运营后台**：`ADMIN_DEV_LOGIN_ENABLED=true`（仅本地）→ `POST /v1/admin/login {"role":"admin"}` 取 token；角色按钮登录无需密码。
- **家长登录（开发态）**：`APP_ENV=development` + 电话任意 → 验证码固定 `123456`（`SMS_DEV_FIXED_CODE`）；生产无凭据时显式 503，不假成功。
- **生产硬校验**：`APP_ENV=production` 时默认 `SECURITY_SECRET_KEY` 直接拒绝启动；短信无凭据 503；后台 dev 登录需显式关闭。

## 已知 BLOCKED / 待验证（环境型，详见 E2E-验收记录.md）

小程序端 UI 真机验证；外部服务真实接入（题庄正式账号/短信/OCR/订阅消息）；Celery worker+dispatcher 进程级联调；TTS/AI形象/成长挚友端上实现；链接分享与 A5 前置关系 edges（DDL 授权后）。

## 安全基线（2026-10-09 审查修复后）

- **后台登录默认关闭**：`ADMIN_DEV_LOGIN_ENABLED` 缺省为 false，生产必须接 SSO；本地开发在 `.env` 设 true。
- **孩子侧仅可用已人工审核发布的课程**：`start_activity` / hash 复用路径校验 `ReviewRecord.status == published`，未发布返回 `LESSON_NOT_PUBLISHED`。
- **跨家长隔离**：交卷接口校验家长归属；数据删除仅家长权限且清理会话/尝试等全部关联数据。
