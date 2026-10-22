"""D3 测试：/register 与 /revoke（HTTP route，非 MCP tool）+ TokenAuthMiddleware 泛化。"""

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.middleware import Middleware

from aiedu_mcp.auth import AuthStore, TokenAuthMiddleware
from aiedu_mcp.server import build_server

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


def _app():
    return build_server().http_app(middleware=[])


async def test_register_returns_token_once(monkeypatch) -> None:
    monkeypatch.delenv("AIEDU_REGISTER_RATE", raising=False)
    async with _app().router.lifespan_context(_app()) as ctx:
        pass
    app = _app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/register", json={"nickname": "小高"})
            assert resp.status_code == 201
            body = resp.json()
            assert body["token"] and len(body["token"]) > 30
            assert body["quota_tier"] == "free"
            assert body["nickname"] == "小高"


async def test_revoke_self_and_lookup_gone(tmp_path, monkeypatch) -> None:
    """自服务吊销：以该 token 本身为凭据；吊销后 lookup 为 None（同一持久库）。"""
    db = tmp_path / "auth.db"
    monkeypatch.setenv("AIEDU_AUTH_DB", str(db))
    app = build_server().http_app(middleware=[])
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            reg = await client.post("/register", json={"nickname": "x"})
            raw = reg.json()["token"]
            resp = await client.post("/revoke", headers={"Authorization": f"Bearer {raw}"})
            assert resp.status_code == 200 and resp.json() == {"revoked": True}
            store = AuthStore(str(db))
            assert store.lookup_token(raw) is None
            store.close()
            resp2 = await client.post("/revoke", headers={"Authorization": f"Bearer {raw}"})
            assert resp2.status_code == 404


async def test_revoke_requires_bearer() -> None:
    app = build_server().http_app(middleware=[])
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/revoke")
            assert resp.status_code == 401


async def test_register_per_ip_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AIEDU_REGISTER_RATE", "3")
    from aiedu_mcp import auth_routes

    auth_routes._guard._hits.clear()
    app = build_server().http_app(middleware=[])
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(4):
                resp = await client.post("/register", json={})
            assert resp.status_code == 429


async def test_token_auth_middleware_valid_and_invalid() -> None:
    """D2：SQLite token 表鉴权——有效 200 / 无效 401（env 静态档之外的演示档默认）。"""
    store = AuthStore()
    raw, _ = store.create_token()
    app = build_server().http_app(middleware=[Middleware(TokenAuthMiddleware, store=store)])
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ok = await client.post("/mcp", json=INIT_BODY, headers={"Authorization": f"Bearer {raw}"})
            assert ok.status_code == 200
            bad = await client.post("/mcp", json=INIT_BODY, headers={"Authorization": "Bearer nope"})
            assert bad.status_code == 401
            assert bad.json()["detail"].startswith("token无效")
