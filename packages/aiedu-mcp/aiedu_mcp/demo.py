"""演示输入页（架构增量 v1 · C9）。

- `GET /`：内联单文件 HTML（无模板引擎/无构建步骤）：一句话定位 / 3 个预设题按钮 /
  自由输入框 / 覆盖矩阵明示 / “接入 MCP”复制块 / 限流提示文案位。
- `POST /demo/generate`：caller=anon:<sha256(ip)[:12]> → RateLimiter.check('generate_lesson')
  超限→HTTP 429+自部署转化文案；未超限→进程内直调 tools.generate_lesson + render_lesson
  （**同一份代码**，无复制）；capability_gap 如实返回“暂不支持”+ issue 链接（禁止弱化）。

与 MCP 端点共用同一 RateLimiter 计数器（演示档限流唯一真相来源）。
"""

import hashlib
import html
import json

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from aiedu_mcp import tools
from aiedu_mcp.ratelimit import _client_ip, limiter
from aiedu_mcp.usage_log import CALLER

# 覆盖矩阵（与 README / CI 覆盖矩阵打印保持同一口径）
COVERAGE_TEXT = "当前确定性覆盖：凑十法（16+8）/ 破十法（16-9）/ 分数等分概念（平均分成 N 份取 M 份）。"
GAP_HINT = "遇 capability_gap 请提 issue：.github/ISSUE_TEMPLATE/capability-gap.md（附返回 detail）"

DEMO_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>数芽 · 数学可信教学引擎（演示）</title>
<style>
 body{font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;margin:0;padding:24px;
   background:#fff8ef;color:#5b4636;max-width:760px;margin:0 auto}
 h1{color:#a3552e;font-size:26px;margin:0 0 6px}
 .sub{color:#a98a6f;margin-bottom:16px}
 .card{background:#fff;border:2px solid #f5d9b8;border-radius:16px;padding:16px;margin-bottom:14px}
 label{font-size:15px;color:#a3552e;display:block;margin-bottom:8px}
 input[type=text]{min-height:48px;font-size:18px;width:100%;box-sizing:border-box;border:2px solid #f5d9b8;
   border-radius:12px;padding:0 12px;margin-bottom:10px;background:#fffdf8}
 button{min-height:48px;font-size:16px;border-radius:12px;border:none;cursor:pointer;
   background:#ff8a5c;color:#fff;padding:0 18px;margin:0 6px 6px 0}
 button.secondary{background:#fff3e2;color:#a3552e}
 pre{background:#0f1115;color:#7ee787;padding:12px;border-radius:10px;font-size:13px;
   overflow-x:auto;white-space:pre-wrap;word-break:break-all}
 #result{margin-top:6px}
 .note{font-size:13px;color:#b09a84;margin-top:10px}
</style></head><body>
<h1>🌱 数芽 · 数学可信教学引擎</h1>
<div class="sub">给 AI Agent 的 MCP 能力：SymPy 级数学核验 + 教学门禁 + 答案门控渲染。<br>
把题交给 Agent 完成教学编排；这里是一次性匿名试用（generate ≤10 次/时/IP）。</div>
<div class="card">
<label>试试这些题（或输入任意题面）</label>
<button onclick="run('16+8')">16 + 8</button>
<button onclick="run('16-9')">16 - 9</button>
<button onclick="run('把一块披萨平均分成4份，取其中1份是多少？')">分蛋糕（1/4）</button>
<input type="text" id="q" placeholder="或输入题面，例如 7x8 / 52-37 / 1/2+1/4">
<button class="secondary" onclick="run(document.getElementById('q').value)">生成课堂</button>
<pre id="result">（结果将显示在这里）</pre>
<div class="note">{coverage}</div>
<div class="note">限流文案位：演示服务容量有限；已超过者请自部署（三行配置见下）。</div>
</div>
<div class="card">
<label>接入 MCP（自部署后 3 行配置）</label>
<pre>{mcp_snippet}</pre>
<div class="note">完整接入与教学技能见仓库 examples/ 与 teaching-math 技能。</div>
</div>
<script>
async function run(q){{
  if(!q||!q.trim()){{document.getElementById('result').textContent='请先输入题面';return}}
  document.getElementById('result').textContent='生成中…';
  const r=await fetch('/demo/generate',{{method:'POST',headers:{{'content-type':'application/json'}},
    body:JSON.stringify({{question:q.trim()}})}});
  const j=await r.json();
  document.getElementById('result').textContent=JSON.stringify(j,null,2);
}}
</script>
</body></html>"""

MCP_SNIPPET = """{"mcpServers":{"aiedu":{"command":"uvx","args":["aiedu-mcp"]}}}
# HTTP 端点 + Bearer（自服务注册 token）：
# {"mcpServers":{"aiedu":{"type":"http","url":"https://<demo域名>/mcp/",
#   "headers":{"Authorization":"Bearer <你的token>"}}}}"""


def install_demo_routes(server: FastMCP) -> None:
    @server.custom_route("/", methods=["GET"])
    async def demo_page(request: Request) -> HTMLResponse:
        return HTMLResponse(
            DEMO_HTML.replace("{coverage}", COVERAGE_TEXT).replace("{mcp_snippet}", html.escape(MCP_SNIPPET))
        )

    @server.custom_route("/demo/generate", methods=["POST"])
    async def demo_generate(request: Request) -> JSONResponse:
        ip = _client_ip(request)
        caller = f"anon:{hashlib.sha256(ip.encode('utf-8')).hexdigest()[:12]}"
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "invalid_input", "detail": "body 必须是 JSON"}, status_code=400)
        question = str(body.get("question") or "")
        if not question.strip():
            return JSONResponse({"error": "invalid_input", "detail": "缺少 question"}, status_code=400)
        retry = limiter.check(caller, "generate_lesson")
        if retry is not None:
            return JSONResponse(
                {
                    "error": "rate_limited",
                    "retry_after": int(retry),
                    "detail": "演示服务容量有限。自己部署只需三条命令："
                    "uvx aiedu-mcp --transport http --port 8000（教学编排见仓库 examples/ 与 teaching-math 技能）。",
                },
                status_code=429,
            )
        token = CALLER.set(caller)
        try:
            # tools.* 是同步函数（内部 asyncio.run）；ASGI 处理器已有事件循环，
            # 必须放到线程池执行（anyio 为既有依赖），否则 "asyncio.run from running loop"。
            import anyio

            out = await anyio.to_thread.run_sync(lambda: tools.generate_lesson(question))
            if "error" in out:
                # 能力缺口如实显示（禁止弱化/兜底相近题）
                out = dict(out)
                out.setdefault("hint", GAP_HINT)
                return JSONResponse(out, status_code=200)
            spec = out["spec"]
            rendered = await anyio.to_thread.run_sync(lambda: tools.render_lesson(spec))
            return JSONResponse(
                {
                    "lesson_id": out.get("lesson_id"),
                    "url": rendered.get("url"),
                    "verification": out.get("verification"),
                }
            )
        finally:
            CALLER.reset(token)
