"""C1 测试：HTTP 静态 Bearer token 中间件（离线，ASGI 直连，无网络）。"""

import pytest
from httpx import ASGITransport, AsyncClient

from aiedu_mcp.server import BearerTokenMiddleware, _http_middleware, build_server

INIT_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0.0.1"},
    },
}


def _asgi_app():
    return build_server().http_app(middleware=_http_middleware())


async def _client(app):
    """ASGI 直连客户端；手动进入 lifespan（httpx ASGITransport 不自动跑）。"""
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def test_no_env_no_middleware(monkeypatch) -> None:
    """未设置 AIEDU_AUTH_TOKEN → 不挂中间件（行为与现状逐字节相同）。"""
    monkeypatch.delenv("AIEDU_AUTH_TOKEN", raising=False)
    assert _http_middleware() == []


def test_env_set_mounts_middleware(monkeypatch) -> None:
    monkeypatch.setenv("AIEDU_AUTH_TOKEN", "secret-token")
    assert len(_http_middleware()) == 1


async def test_missing_header_401(monkeypatch) -> None:
    monkeypatch.setenv("AIEDU_AUTH_TOKEN", "secret-token")
    async for client in _client(_asgi_app()):
        resp = await client.post("/mcp", json=INIT_BODY)
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthorized"
        assert "WWW-Authenticate" not in resp.headers  # 静态 token 非 OAuth（架构 §3.2）


async def test_wrong_header_401(monkeypatch) -> None:
    monkeypatch.setenv("AIEDU_AUTH_TOKEN", "secret-token")
    async for client in _client(_asgi_app()):
        resp = await client.post(
            "/mcp", json=INIT_BODY, headers={"Authorization": "Bearer wrong"}
        )
        assert resp.status_code == 401


async def test_correct_header_200(monkeypatch) -> None:
    monkeypatch.setenv("AIEDU_AUTH_TOKEN", "secret-token")
    async for client in _client(_asgi_app()):
        resp = await client.post(
            "/mcp", json=INIT_BODY, headers={"Authorization": "Bearer secret-token"}
        )
        assert resp.status_code == 200
        # streamable-http 的 initialize 响应是 SSE（event: message + data: {...}）
        assert '"serverInfo"' in resp.text and 'aiedu-mcp' in resp.text


async def test_no_env_no_auth_200(monkeypatch) -> None:
    """未设置 env 时（无中间件）initialize 照常通过。"""
    monkeypatch.delenv("AIEDU_AUTH_TOKEN", raising=False)
    async for client in _client(_asgi_app()):
        resp = await client.post("/mcp", json=INIT_BODY)
        assert resp.status_code == 200
