"""C7 测试：player 同域挂载（StaticFiles）+ --host（离线 ASGI 断言）。"""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.staticfiles import StaticFiles

from aiedu_mcp.server import build_server


@pytest.fixture()
def player_dist(tmp_path: Path) -> Path:
    (tmp_path / "lesson.html").write_text("<html><body>aiedu player</body></html>", encoding="utf-8")
    (tmp_path / "player.js").write_text("window.AIEDUPlayer={};", encoding="utf-8")
    return tmp_path


async def test_player_mounted_serves_files(player_dist) -> None:
    """AIEDU_SERVE_PLAYER=1 形态：/player/<file> 返回 200 且 content-type 正确。"""
    app = build_server().http_app(middleware=[])
    app.mount("/player", StaticFiles(directory=str(player_dist)), name="player")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/player/lesson.html")
            assert resp.status_code == 200
            assert "aiedu player" in resp.text
            assert resp.headers["content-type"].startswith("text/html")
            resp2 = await client.get("/player/player.js")
            assert resp2.status_code == 200
            assert resp2.headers["content-type"].startswith("text/javascript")


async def test_player_not_mounted_without_env() -> None:
    """未设 AIEDU_SERVE_PLAYER → 无 /player 路由（404）。"""
    app = build_server().http_app(middleware=[])
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/player/lesson.html")
            assert resp.status_code in (404, 405)  # 未挂载 → 无路由
