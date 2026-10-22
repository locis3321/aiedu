"""限流与 caller 上下文（架构增量 v1 · C8 + D4）。

双层结构（架构文档 §3.4.1）：
- ASGI 层：`CallerContextMiddleware` 识别调用方（token / 匿名 IP 哈希）→ `CALLER` ContextVar；
- fastmcp 协议层：`RateLimitMiddleware.on_call_tool` 读 CALLER + tool 名 → `RateLimiter.check()`；
- 演示输入页：进程内直调 tools.* 前也走 `RateLimiter.check()`。

零新增依赖（stdlib only）。`AIEDU_RATE_LIMIT=1` 时才挂载；未设置 = 行为不变。
具体配额值（PM v1.x / 执行清单终审值；env `AIEDU_RATE_LIMITS` JSON 可覆盖）：
  per-token：generate ≤20/h、≤300/月；verify ≤200/h；get/submit ≤500/h；render ≤200/h
  匿名 IP：generate ≤10/h；全局日熔断 ≤20,000；单 caller 60 generate/h → runaway 标记
"""

import collections
import hashlib
import json
import os
import time

from fastmcp.server.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

from aiedu_mcp.usage_log import CALLER

DEFAULT_LIMITS = {
    "generate_lesson": 20,
    "verify_math": 200,
    "get_lesson": 500,
    "submit_attempt": 500,
    "render_lesson": 200,
}
ANON_GENERATE_PER_HOUR = 10
GENERATE_PER_MONTH = 300
DAILY_TOTAL = 20_000
RUNAWAY_GENERATE_PER_HOUR = 60

_HOUR = 3600
_MONTH = 30 * 24 * _HOUR
_RUNAWAY_RETRY = _HOUR


def _limits() -> dict:
    """env AIEDU_RATE_LIMITS（JSON）覆盖默认值；非法 JSON 静默回退默认。"""
    raw = os.environ.get("AIEDU_RATE_LIMITS", "").strip()
    if not raw:
        return dict(DEFAULT_LIMITS)
    try:
        return {**DEFAULT_LIMITS, **json.loads(raw)}
    except (ValueError, TypeError):
        return dict(DEFAULT_LIMITS)


def _client_ip(request) -> str:
    """取客户端 IP：AIEDU_TRUST_PROXY=1 时取 X-Forwarded-For 首跳；默认直连地址。"""
    if os.environ.get("AIEDU_TRUST_PROXY", "").strip() == "1":
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """进程内滑动窗口（单实例演示站足够；重启清零——可接受的治理状态）。

    check(caller, tool) -> float | None：超限返回建议重试秒数并计数（含被拒尝试，
    用于 runaway 检测）；未超限返回 None。
    """

    def __init__(self) -> None:
        self._hourly: dict[str, dict[str, list[float]]] = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )
        self._monthly: dict[str, list[float]] = collections.defaultdict(list)
        self._daily: list[float] = []
        self._runaway: set[str] = set()

    @staticmethod
    def _trim(events: list[float], cutoff: float) -> None:
        while events and events[0] < cutoff:
            events.pop(0)

    def check(self, caller: str | None, tool: str) -> float | None:
        if caller is None:
            return 0.0 if False else None  # stdio/未识别：不在演示站限流范围
        now = time.time()

        if caller in self._runaway:
            return _RUNAWAY_RETRY

        # 全局日熔断
        self._trim(self._daily, now - 24 * _HOUR)
        self._daily.append(now)
        if len(self._daily) > DAILY_TOTAL:
            return 24 * _HOUR

        hourly = self._hourly[caller][tool]
        self._trim(hourly, now - _HOUR)
        hourly.append(now)  # 计尝试（含被拒），runaway 依据

        # runaway：1h 内 generate 尝试 >60 → 标记待审，全拒绝到窗口结束
        if tool == "generate_lesson" and len(hourly) > RUNAWAY_GENERATE_PER_HOUR:
            self._runaway.add(caller)
            return _RUNAWAY_RETRY

        limit = _limits().get(tool, 60)
        if tool == "generate_lesson" and caller.startswith("anon:"):
            limit = min(limit, ANON_GENERATE_PER_HOUR)
        if len(hourly) > limit:
            return _HOUR

        if tool == "generate_lesson":
            monthly = self._monthly[caller]
            self._trim(monthly, now - _MONTH)
            monthly.append(now)
            if len(monthly) > GENERATE_PER_MONTH:
                return _MONTH
        return None

    def is_runaway(self, caller: str) -> bool:
        return caller in self._runaway


# 单实例（进程内共享；演示站限流窗口）
limiter = RateLimiter()


class CallerContextMiddleware(BaseHTTPMiddleware):
    """ASGI 层：识别调用方并写入 CALLER ContextVar（token 优先 / 匿名 IP 哈希）。

    在 TokenAuthMiddleware 之后执行（先解析出 request.state.token_record 再取）。
    """

    async def dispatch(self, request, call_next):
        record = getattr(request.state, "token_record", None)
        if record is not None:
            CALLER.set(f"token:{record.id}")
        else:
            ip = _client_ip(request)
            CALLER.set(f"anon:{hashlib.sha256(ip.encode('utf-8')).hexdigest()[:12]}")
        return await call_next(request)


def _rate_limited_result(retry_after: float, detail: str):
    """构造协议层结构化错误（与 capability_gap 同一错误分类学；不伪造传输层 429）。"""
    import json as _json

    from fastmcp.tools.base import ToolResult
    from mcp.types import TextContent

    payload = {"error": "rate_limited", "retry_after": int(retry_after), "detail": detail}
    return ToolResult(
        content=[TextContent(type="text", text=_json.dumps(payload, ensure_ascii=False))],
        is_error=True,
    )


class RateLimitMiddleware(Middleware):
    """fastmcp 协议层执法：on_call_tool 钩子（只拦 tools/call，不碰 initialize/list）。"""

    async def on_call_tool(self, context, call_next):
        caller = CALLER.get()
        if caller is None:
            return await super().on_call_tool(context, call_next)
        tool = context.message.name
        retry = limiter.check(caller, tool)
        if retry is not None:
            return _rate_limited_result(
                retry,
                "演示服务容量有限。自己部署只需三行配置：uvx aiedu-mcp --transport http --port 8000"
                "（教学编排见 examples/ 与 teaching-math 技能）。",
            )
        return await super().on_call_tool(context, call_next)
