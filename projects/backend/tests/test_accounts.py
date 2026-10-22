"""T2 验收测试：账号监护与孩子档案（规格 v2 §4/§5 + 任务包验收项）。

覆盖：dev 验证码登录（控制台打印+mode=dev）、验证码安全（错误/过期/限流/次数）、
监护同意（非必要默认不勾选/撤回/重新同意）、建档门禁（同意前置/必填事实）、
孩子 CRUD 与删除边界、跨家长隔离、时长设置持久化与隔离、child-scoped token。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts import service
from app.accounts.models import ParentUser, SmsVerification
from app.accounts.router import get_session
from app.api.main import create_app
from app.storage.db import Base

PHONE = "13800000001"
FIXED_CODE = "123456"


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture()
def factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture()
def db(factory):
    with factory() as session:
        yield session


@pytest.fixture()
def client(factory):
    def override():
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c


def send_code(client, phone=PHONE):
    return client.post("/v1/auth/sms/send", json={"phone": phone})


def login_sms(client, phone=PHONE, code=FIXED_CODE):
    return client.post("/v1/auth/parents/login-sms", json={"phone": phone, "code": code})


def register_parent(client, phone=PHONE) -> dict:
    resp = send_code(client, phone)
    assert resp.status_code == 200, resp.text
    resp = login_sms(client, phone)
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def grant_consents(client, token: str, parent_id: str) -> None:
    for key in ("guardian_rules", "privacy_notice"):
        resp = client.post(
            f"/v1/parents/{parent_id}/consents",
            json={"consent_key": key},
            headers=auth(token),
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------- 短信验证码

def test_send_sms_dev_mode_console_and_hash(client, db, capsys):
    resp = send_code(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "dev"
    assert body["sent"] is True
    assert body["expires_in_seconds"] > 0

    out = capsys.readouterr().out
    assert "[dev]" in out and FIXED_CODE in out and PHONE in out

    record = db.query(SmsVerification).filter_by(phone=PHONE).one()
    assert record.mode == "dev"
    assert record.code_hash != FIXED_CODE  # 只存哈希，不存明文


def test_send_sms_invalid_phone(client):
    resp = send_code(client, phone="12345")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_PHONE"


def test_send_sms_cooldown_rate_limited(client):
    assert send_code(client).status_code == 200
    resp = send_code(client)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "SMS_RATE_LIMITED"


def test_send_sms_daily_cap(client, monkeypatch):
    from app.core.config import Settings

    # 冷却置 0：连续发送只受日限额约束
    fast = Settings(sms_send_cooldown_seconds=0)
    monkeypatch.setattr(service, "get_settings", lambda: fast)
    for _ in range(10):
        assert send_code(client).status_code == 200
    resp = send_code(client)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "SMS_RATE_LIMITED"


# ---------------------------------------------------------------- 登录

def test_login_sms_happy_path(client, db):
    data = register_parent(client)
    assert data["token"]
    assert data["user"]["phone_masked"].startswith("138****")
    parent = db.query(ParentUser).filter_by(phone=PHONE).one()
    assert parent.last_login_at is not None


def test_login_sms_wrong_code(client):
    register_parent(client)
    resp = login_sms(client, code="999999")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_SMS_CODE"


def test_login_sms_expired(client, db):
    register_parent(client)
    record = db.query(SmsVerification).filter_by(phone=PHONE).one()
    record.expires_at = record.expires_at.replace(year=2020)
    db.commit()
    resp = login_sms(client)
    assert resp.status_code == 401


def test_login_sms_max_attempts_exhausted(client):
    register_parent(client)
    for _ in range(5):
        assert login_sms(client, code="999999").status_code == 401
    # 次数用尽后即使输入正确验证码也拒绝
    assert login_sms(client).status_code == 401


def test_wechat_login_unconfigured_explicit_failure(client):
    resp = client.post("/v1/auth/parents/login", json={"code": "wx-code"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WECHAT_NOT_CONFIGURED"


def test_wechat_login_mocked_success_and_dedup(client, monkeypatch, db):
    from app.core.config import Settings

    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: Settings(wechat_app_id="wxid", wechat_app_secret="secret"),
    )

    def fake_exchange(appid, secret, js_code):
        return {"openid": "openid-abc"}

    monkeypatch.setattr(service, "exchange_code2session", fake_exchange)
    r1 = client.post("/v1/auth/parents/login", json={"code": "wx-code-1"})
    r2 = client.post("/v1/auth/parents/login", json={"code": "wx-code-2"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["user"]["id"] == r2.json()["user"]["id"]
    parent = db.query(ParentUser).filter_by(wechat_openid="openid-abc").one()
    assert parent.id == r1.json()["user"]["id"]


# ---------------------------------------------------------------- 监护同意

def test_nonessential_default_unchecked_and_withdraw_regrant(client):
    data = register_parent(client)
    token, pid = data["token"], data["user"]["id"]
    me = client.get("/v1/parents/me", headers=auth(token)).json()
    assert me["consents"] == []  # 注册后无任何同意记录：非必要项默认不勾选

    # 授予非必要项
    resp = client.post(
        f"/v1/parents/{pid}/consents",
        json={"consent_key": "companion_ai_notice"},
        headers=auth(token),
    )
    assert resp.status_code == 200 and resp.json()["status"] == "granted"

    # 撤回 → 状态回读为 withdrawn
    resp = client.delete(
        f"/v1/parents/{pid}/consents/companion_ai_notice", headers=auth(token)
    )
    assert resp.status_code == 200 and resp.json()["status"] == "withdrawn"
    me = client.get("/v1/parents/me", headers=auth(token)).json()
    statuses = {c["key"]: c["status"] for c in me["consents"]}
    assert statuses["companion_ai_notice"] == "withdrawn"

    # 重新同意 → 恢复 granted
    resp = client.post(
        f"/v1/parents/{pid}/consents",
        json={"consent_key": "companion_ai_notice"},
        headers=auth(token),
    )
    assert resp.json()["status"] == "granted"


def test_unknown_consent_key_rejected(client):
    data = register_parent(client)
    token, pid = data["token"], data["user"]["id"]
    resp = client.post(
        f"/v1/parents/{pid}/consents",
        json={"consent_key": "not_a_real_key"},
        headers=auth(token),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNKNOWN_CONSENT_KEY"


# ---------------------------------------------------------------- 孩子档案

def test_child_create_requires_guardian_consent(client):
    data = register_parent(client)
    token = data["token"]
    resp = client.post(
        "/v1/children",
        json={"nickname": "小禾", "grade": "3"},
        headers=auth(token),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_child_create_missing_facts_rejected(client):
    data = register_parent(client)
    token, pid = data["token"], data["user"]["id"]
    grant_consents(client, token, pid)
    # 年级与年龄段均缺 → 显式失败，不自动挑选默认值
    resp = client.post("/v1/children", json={"nickname": "小禾"}, headers=auth(token))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "MISSING_REQUIRED_FACT"


def test_child_crud_delete_boundaries(client):
    data = register_parent(client)
    token, pid = data["token"], data["user"]["id"]
    grant_consents(client, token, pid)
    c1 = client.post(
        "/v1/children",
        json={"nickname": "小禾", "grade": "3", "textbook_version": "人教版"},
        headers=auth(token),
    ).json()
    c2 = client.post(
        "/v1/children", json={"nickname": "小川", "age_group": "6-8"}, headers=auth(token)
    ).json()

    listed = client.get("/v1/children", headers=auth(token)).json()
    assert len(listed) == 2

    # 更新昵称与教材版本
    updated = client.put(
        f"/v1/children/{c1['id']}",
        json={"nickname": "小禾苗", "textbook_version": "北师大版"},
        headers=auth(token),
    ).json()
    assert updated["nickname"] == "小禾苗" and updated["textbook_version"] == "北师大版"

    # 删除非当前孩子 → 列表减一；已删除孩子不可再读
    deleted = client.delete(f"/v1/children/{c1['id']}", headers=auth(token))
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True
    listed = client.get("/v1/children", headers=auth(token)).json()
    assert [c["id"] for c in listed] == [c2["id"]]
    assert (
        client.get(f"/v1/children/{c1['id']}", headers=auth(token)).status_code == 404
    )


def test_child_isolation_between_parents(client):
    p1 = register_parent(client)
    p2 = register_parent(client, phone="13800000002")
    token1, pid1 = p1["token"], p1["user"]["id"]
    token2, pid2 = p2["token"], p2["user"]["id"]
    grant_consents(client, token1, pid1)
    grant_consents(client, token2, pid2)
    child_id = client.post(
        "/v1/children", json={"nickname": "小禾", "grade": "3"}, headers=auth(token1)
    ).json()["id"]
    # 跨家长读取一律拒绝（规格 v2 §4.3）
    assert client.get(f"/v1/children/{child_id}", headers=auth(token2)).status_code == 404
    assert (
        client.put(
            f"/v1/children/{child_id}/settings",
            json={"daily_minutes": 10},
            headers=auth(token2),
        ).status_code
        == 404
    )


# ---------------------------------------------------------------- 时长设置

def test_time_settings_persist_and_isolated_per_child(client):
    data = register_parent(client)
    token, pid = data["token"], data["user"]["id"]
    grant_consents(client, token, pid)
    a = client.post(
        "/v1/children", json={"nickname": "小禾", "grade": "3"}, headers=auth(token)
    ).json()
    b = client.post(
        "/v1/children", json={"nickname": "小川", "grade": "7"}, headers=auth(token)
    ).json()

    # A：设置每日45/连续20/休息10/关闭陪伴 → 服务端持久化并可回读
    put_a = client.put(
        f"/v1/children/{a['id']}/settings",
        json={
            "daily_minutes": 45,
            "continuous_minutes": 20,
            "rest_minutes": 10,
            "companion_enabled": False,
        },
        headers=auth(token),
    )
    assert put_a.status_code == 200
    got_a = client.get(f"/v1/children/{a['id']}/settings", headers=auth(token)).json()
    assert got_a["daily_minutes"] == 45 and got_a["continuous_minutes"] == 20
    assert got_a["rest_minutes"] == 10 and got_a["companion_enabled"] is False

    # B：未设置 → 默认值；A 的设置不受影响（跨孩子隔离）
    got_b = client.get(f"/v1/children/{b['id']}/settings", headers=auth(token)).json()
    assert got_b["daily_minutes"] == 30 and got_b["continuous_minutes"] == 15
    assert got_b["rest_minutes"] == 5 and got_b["companion_enabled"] is True
    got_a_again = client.get(
        f"/v1/children/{a['id']}/settings", headers=auth(token)
    ).json()
    assert got_a_again["daily_minutes"] == 45


# ---------------------------------------------------------------- child-scoped token

def test_protected_endpoints_require_auth(client):
    assert client.get("/v1/children").status_code == 401


def test_logout_ok_with_token(client):
    data = register_parent(client)
    resp = client.post("/v1/auth/parents/logout", headers=auth(data["token"]))
    assert resp.status_code == 200 and resp.json()["ok"] is True


def test_switch_session_issues_child_scoped_token(client):
    data = register_parent(client)
    token, pid = data["token"], data["user"]["id"]
    grant_consents(client, token, pid)
    child_id = client.post(
        "/v1/children", json={"nickname": "小禾", "grade": "3"}, headers=auth(token)
    ).json()["id"]
    resp = client.post(f"/v1/children/{child_id}/switch-session", headers=auth(token))
    assert resp.status_code == 200
    child_token = resp.json()["token"]
    # child-scoped token 不能访问家长域接口（规格 v2 §4.3）
    me = client.get("/v1/parents/me", headers=auth(child_token))
    assert me.status_code == 401
