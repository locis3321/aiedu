"""T1 冒烟测试：应用可启动且健康检查可达。"""

from fastapi.testclient import TestClient

from app.api.main import create_app


def test_healthz() -> None:
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
