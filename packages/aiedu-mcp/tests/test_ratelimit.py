"""C8 测试：RateLimiter 窗口语义 / runaway / 协议层执法 / 启动红线。"""

import asyncio
import time

import pytest

from aiedu_mcp import ratelimit
from aiedu_mcp.ratelimit import (
    ANON_GENERATE_PER_HOUR,
    DAILY_TOTAL,
    RUNAWAY_GENERATE_PER_HOUR,
    CallerContextMiddleware,
    RateLimiter,
)
from aiedu_mcp.server import _enforce_launch_policy
from aiedu_mcp.usage_log import CALLER


def test_exactly_n_passes_then_rejected() -> None:
    rl = RateLimiter()
    caller = "token:1"
    for _ in range(20):
        assert rl.check(caller, "generate_lesson") is None
    retry = rl.check(caller, "generate_lesson")  # 第 21 次
    assert retry is not None and 0 < retry <= 3600


def test_window_slides_recovery() -> None:
    rl = RateLimiter()
    caller = "token:9"
    for _ in range(20):
        rl.check(caller, "generate_lesson")
    # 把窗口内时间戳全部移到 2 小时前 → 恢复
    events = rl._hourly[caller]["generate_lesson"]
    for i in range(len(events)):
        events[i] -= 7200
    assert rl.check(caller, "generate_lesson") is None


def test_anon_tier_lower_generate_limit() -> None:
    rl = RateLimiter()
    caller = "anon:abcdef123456"
    for _ in range(ANON_GENERATE_PER_HOUR):
        assert rl.check(caller, "generate_lesson") is None
    assert rl.check(caller, "generate_lesson") is not None


def test_non_generate_tool_has_own_limit() -> None:
    rl = RateLimiter()
    caller = "token:2"
    for _ in range(200):
        assert rl.check(caller, "verify_math") is None
    assert rl.check(caller, "verify_math") is not None


def test_monthly_generate_cap() -> None:
    rl = RateLimiter()
    caller = "token:3"
    # 300 次/月：先逐小时放行 20 次并滑动窗口（月计数累加）
    for _ in range(300):
        # 逐小时消耗会触发小时限制——直接操纵：把小时窗口清零后继续
        rl._hourly[caller]["generate_lesson"].clear()
        rl._hourly[caller]["generate_lesson"].append(time.time())
        assert rl.check(caller, "generate_lesson") is None
    rl._hourly[caller]["generate_lesson"].clear()
    assert rl.check(caller, "generate_lesson") is not None  # 月配额 301 次


def test_runaway_marked_after_60_generate_hour() -> None:
    rl = RateLimiter()
    caller = "token:runaway"
    for _ in range(RUNAWAY_GENERATE_PER_HOUR + 1):
        rl.check(caller, "generate_lesson")
    assert rl.is_runaway(caller)
    assert rl.check(caller, "verify_math") is not None  # runaway 后全工具拒绝


def test_daily_total_breaker() -> None:
    rl = RateLimiter()
    for i in range(DAILY_TOTAL):
        rl.check(f"token:{i % 50}", "verify_math")
    assert rl.check("token:new", "verify_math") is not None


def test_caller_none_not_limited() -> None:
    """stdio/未识别（caller=None）不在演示站限流范围（本地无调用方概念）。"""
    rl = RateLimiter()
    for _ in range(1000):
        assert rl.check(None, "generate_lesson") is None


async def test_protocol_layer_enforces_quota() -> None:
    """fastmcp 协议层执法：CALLER 有值时按配额拦截 tools/call。"""
    from fastmcp import FastMCP

    from aiedu_mcp.ratelimit import RateLimitMiddleware

    mcp = FastMCP("rl-probe")
    mcp.add_middleware(RateLimitMiddleware())

    @mcp.tool
    def generate_lesson(question: str) -> dict:
        return {"ok": question}

    token = CALLER.set("anon:hash12345678")
    try:
        results = []
        for _ in range(ANON_GENERATE_PER_HOUR + 1):
            res = await mcp.call_tool("generate_lesson", {"question": "16+8"})
            results.append(res.content[0].text)
        # 第 N+1 次应是结构化 rate_limited 错误
        assert "rate_limited" in results[-1]
        assert all("rate_limited" not in r for r in results[:-1])
    finally:
        CALLER.reset(token)


def test_client_ip_respects_trust_proxy(monkeypatch) -> None:
    class FakeHeaders(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

    class FakeClient:
        host = "10.0.0.1"

    class FakeRequest:
        headers = FakeHeaders({"x-forwarded-for": "203.0.113.7, 10.0.0.2"})
        client = FakeClient()

    monkeypatch.setenv("AIEDU_TRUST_PROXY", "1")
    assert ratelimit._client_ip(FakeRequest()) == "203.0.113.7"
    monkeypatch.delenv("AIEDU_TRUST_PROXY")
    assert ratelimit._client_ip(FakeRequest()) == "10.0.0.1"


def test_launch_policy_rejects_demo_with_llm(monkeypatch) -> None:
    """红线：演示档（RATE_LIMIT=1）+ LLM env + 无 token → 拒绝启动。"""
    monkeypatch.setenv("AIEDU_RATE_LIMIT", "1")
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL_NAME", "m")
    monkeypatch.delenv("AIEDU_AUTH_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        _enforce_launch_policy("http")


def test_launch_policy_warns_only_for_local(monkeypatch) -> None:
    """(b) 档内网自建 + LLM + 无 token：仅告警不拦截。"""
    monkeypatch.delenv("AIEDU_RATE_LIMIT", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL_NAME", "m")
    monkeypatch.delenv("AIEDU_AUTH_TOKEN", raising=False)
    _enforce_launch_policy("http")  # 不抛


def test_launch_policy_no_llm_ok(monkeypatch) -> None:
    monkeypatch.setenv("AIEDU_RATE_LIMIT", "1")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    _enforce_launch_policy("http")  # 不抛
