"""C9 测试：演示输入页与生成端点（匿名试用 + IP 限流 + gap 如实）。"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from aiedu_core.pipeline import pipeline as core_pipeline
from aiedu_core.services.llm_router import ModelRouter
from aiedu_mcp.server import build_server


def _disable_llm(monkeypatch) -> None:
    router = ModelRouter()
    monkeypatch.setattr(router, "get", lambda role: None)
    monkeypatch.setattr(core_pipeline, "default_router", lambda: router)


def _app():
    return build_server().http_app(middleware=[])


async def test_demo_page_returns_coverage(monkeypatch) -> None:
    app = _app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "数学可信教学引擎" in resp.text
            assert "凑十法" in resp.text and "覆盖" in resp.text  # 覆盖矩阵明示
            assert "aiedu-mcp" in resp.text and "Bearer" in resp.text  # 接入 MCP 复制块


async def test_demo_generate_quota_then_429(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    monkeypatch.setenv("AIEDU_RATE_LIMITS", json.dumps({"generate_lesson": 1}))
    from aiedu_mcp.ratelimit import limiter as _limiter

    _limiter._hourly.clear(); _limiter._monthly.clear(); _limiter._daily.clear(); _limiter._runaway.clear()
    app = _app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post("/demo/generate", json={"question": "16+8"})
            assert first.status_code == 200
            assert "lesson_id" in first.json()
            second = await client.post("/demo/generate", json={"question": "16+8"})
            assert second.status_code == 429
            assert second.json()["error"] == "rate_limited"
            assert "自己部署" in second.json()["detail"]


async def test_demo_gap_reported_honestly(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    from aiedu_mcp.ratelimit import limiter as _limiter

    _limiter._hourly.clear(); _limiter._monthly.clear(); _limiter._daily.clear(); _limiter._runaway.clear()
    monkeypatch.delenv("AIEDU_RATE_LIMITS", raising=False)
    app = _app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/demo/generate", json={"question": "52-37"})
            body = resp.json()
            assert body["error"] == "capability_gap"  # 如实，禁止兜底相近题
            assert "capability-gap" in body.get("hint", "")  # issue 链接引导
