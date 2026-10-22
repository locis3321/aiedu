"""MCP server：FastMCP（4.x）封装内核 5 个 tool，stdio（默认）/ HTTP 双传输。

入口：
- python -m aiedu_mcp.server --transport stdio
- python -m aiedu_mcp.server --transport http --port 8000
- uvx aiedu-mcp（console script → main()）

HTTP 传输鉴权（架构增量 v1 · C1/D2）：
- `AIEDU_AUTH_TOKEN` env 设置 → 静态 Bearer token（可信局域网自建档，零 DB）；
- 未设置 → 无中间件（行为与未配置 env 前逐字节相同）；（D2 将追加 SQLite token 表档）。
"""

import argparse
import hmac
import os

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from aiedu_mcp import tools
from aiedu_mcp.ratelimit import RateLimitMiddleware

VERSION = "0.1.0"
AUTH_TOKEN_ENV = "AIEDU_AUTH_TOKEN"


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """env 单静态 Token 校验：仅挂载于 HTTP 传输（main() 条件注入），stdio 不受影响。

    注意：401 不带 `WWW-Authenticate` 头——静态 token 模式不是 OAuth 2.1，
    伪造该头会让规范客户端进入授权发现循环（架构文档 §3.2 取舍说明）。
    """

    def __init__(self, app):
        super().__init__(app)
        self._tok = os.environ.get(AUTH_TOKEN_ENV, "").strip().encode()

    async def dispatch(self, request, call_next):
        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            value.strip().encode("utf-8"), self._tok
        ):
            return JSONResponse(
                {"error": "unauthorized", "detail": "缺少或错误的 Bearer token"},
                status_code=401,
            )
        return await call_next(request)


def _http_middleware() -> list:
    """鉴权中间件优先级（架构文档 §3.5.2 对齐）：
    ① AIEDU_AUTH_TOKEN env → 静态 Bearer（自建档默认，零 DB）；
    ② 否则 AIEDU_RATE_LIMIT=1（演示档）→ SQLite token 表（自服务注册制）；
    ③ 两者都未设置 → 空（(a) stdio / (b) localhost HTTP，行为不变）。

    集中在一个函数（架构文档 §3.3 接口抽象）：将来 OAuth 档只改这一个返回值。
    """
    if os.environ.get(AUTH_TOKEN_ENV, "").strip():
        return [Middleware(BearerTokenMiddleware)]
    if os.environ.get("AIEDU_RATE_LIMIT", "").strip() == "1":
        from aiedu_mcp.auth import TokenAuthMiddleware

        return [Middleware(TokenAuthMiddleware)]
    return []


def build_server() -> FastMCP:
    """构建并注册 5 个 tool（工具面冻结：verify/generate/get/submit/render）。"""
    server = FastMCP(
        name="aiedu-mcp",
        version=VERSION,
        instructions=(
            "数学可信教学引擎：数学核验（verify_math）、课程生成（generate_lesson）、"
            "答案门控获取（get_lesson）、服务端判分（submit_attempt）、"
            "课堂渲染（render_lesson）。verification.verified 仅由 SymPy 核验产生；"
            "get_lesson(filtered) 不返回未解锁答案字段（先想后看）；"
            "generate_lesson 返回 {lesson_id, spec, verification}，后续工具请传其中的 spec 本体。"
        ),
    )
    server.tool()(tools.verify_math)
    server.tool()(tools.generate_lesson)
    server.tool()(tools.get_lesson)
    server.tool()(tools.submit_attempt)
    server.tool()(tools.render_lesson)
    # D3：自服务注册/吊销 HTTP routes（custom_route，非 MCP tool——工具面冻结保持）
    from aiedu_mcp.auth_routes import install_auth_routes

    install_auth_routes(server)
    # C9：演示输入页（同一进程同一 app，进程内直调 tools.*——单一事实来源）
    from aiedu_mcp.demo import install_demo_routes

    install_demo_routes(server)
    return server


def _enforce_launch_policy(transport: str) -> None:
    """红线（架构文档 §3.4.3）：匿名 + LLM env + HTTP 传输 = 启动硬拒绝。

    判据：http 传输 + LLM 已配置 + 演示档已开启（AIEDU_RATE_LIMIT=1）且未设
    AIEDU_AUTH_TOKEN（拔网线开关）→ stderr 显著告警并拒绝启动（防把 LLM 成本
    暴露给全互联网）。(b) 档内网自建 + LLM + 无 token 仅告警不拦截。
    """
    if transport != "http":
        return
    llm_configured = all(
        os.environ.get(k, "").strip()
        for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_NAME")
    )
    if not llm_configured:
        return
    import sys

    if os.environ.get("AIEDU_RATE_LIMIT", "").strip() == "1" and not os.environ.get(
        AUTH_TOKEN_ENV, ""
    ).strip():
        print(
            "拒绝启动：演示档（AIEDU_RATE_LIMIT=1）不得配置 LLM env——"
            "会免费暴露 LLM 成本给互联网。请删除 LLM_* 环境变量，或设 AIEDU_AUTH_TOKEN。",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        "告警：HTTP 传输配置了 LLM env 且未设 AIEDU_AUTH_TOKEN——"
        "若该服务面向公网请设静态 token 或关闭 LLM（仅内网自建可继续）。",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="aiedu-mcp MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="传输协议：stdio（默认，Claude Code / WorkBuddy 接入用）或 http",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 绑定地址（仅 http 传输）")
    parser.add_argument("--port", type=int, default=8000, help="HTTP 端口（仅 http 传输）")
    args = parser.parse_args(argv)

    _enforce_launch_policy(args.transport)

    server = build_server()
    if args.transport == "http":
        # 演示档限流（C8）：协议层 RateLimitMiddleware + ASGI 层 CallerContextMiddleware
        if os.environ.get("AIEDU_RATE_LIMIT", "").strip() == "1":
            server.add_middleware(RateLimitMiddleware())
        middleware = list(_http_middleware())
        if os.environ.get("AIEDU_RATE_LIMIT", "").strip() == "1":
            from aiedu_mcp.ratelimit import CallerContextMiddleware

            middleware.append(CallerContextMiddleware())
        app = server.http_app(middleware=middleware)
        # C7：同域挂载 player（AIEDU_SERVE_PLAYER=1）
        if os.environ.get("AIEDU_SERVE_PLAYER", "").strip() == "1":
            from starlette.staticfiles import StaticFiles

            dist = os.environ.get("AIEDU_PLAYER_DIST", "").strip() or "./player_dist"
            app.mount("/player", StaticFiles(directory=dist), name="player")
        import uvicorn

        uvicorn.run(app, host=args.host, port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
