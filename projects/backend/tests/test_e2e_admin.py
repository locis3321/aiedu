"""2026-10-13 审查修复批次交付级 E2E（真实本地栈 PG16+Redis，非 mock）。

覆盖：后台登录默认关闭（P1）、孩子侧发布门禁（护栏5）、A4 建题审核（核验标志不可直传）、
A10 积分规则版本化、A14 安全反馈处置（脱敏摘要）。
积分幂等发放已在 tests/test_journey.py 覆盖，此处不重复。

运行：uv run pytest -m e2e -v
"""

import random

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.jobs.service import create_job, get_revision
from app.jobs.tasks import generate_lesson
from app.storage.db import create_session_factory

pytestmark = pytest.mark.e2e

FIXED_CODE = "123456"


def _phone():
    return "138" + str(random.randint(10000000, 99999999))


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def db():
    factory = create_session_factory()
    with factory() as session:
        yield session


@pytest.fixture(autouse=True)
def _admin_dev_login(monkeypatch):
    """e2e 默认开启开发态后台登录；生产默认关闭（见 test_admin.py）。"""
    monkeypatch.setenv("ADMIN_DEV_LOGIN_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def auth(token):
    return {"Authorization": "Bearer " + token}


def _register_parent(client, phone=None):
    phone = phone or _phone()
    client.post("/v1/auth/sms/send", json={"phone": phone})
    resp = client.post(
        "/v1/auth/parents/login-sms", json={"phone": phone, "code": FIXED_CODE}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _grant_consents(client, token, pid):
    for key in ("guardian_rules", "privacy_notice"):
        r = client.post(
            "/v1/parents/" + pid + "/consents",
            json={"consent_key": key},
            headers=auth(token),
        )
        assert r.status_code == 200, r.text


def _create_child(client, token, nickname, grade):
    r = client.post(
        "/v1/children", json={"nickname": nickname, "grade": grade}, headers=auth(token)
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _admin_login(client):
    resp = client.post("/v1/admin/login", json={"role": "admin"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


# ---------------------------------------------------------------- P1：登录门禁


def test_admin_login_disabled_by_default_e2e(client, monkeypatch):
    """P1：无凭据签发管理 token 默认关闭——未启用返回 503（生产接 SSO）。"""
    monkeypatch.setenv("ADMIN_DEV_LOGIN_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    resp = client.post("/v1/admin/login", json={"role": "admin"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "ADMIN_LOGIN_DISABLED"


# ---------------------------------------------------------------- 护栏5：发布门禁


def test_publish_gate_e2e(client, db):
    """护栏5：未人工审核发布 → 孩子课堂 409；发布后 → 可开始（201）。"""
    data = _register_parent(client)
    token, pid = data["token"], data["user"]["id"]
    _grant_consents(client, token, pid)
    child_id = _create_child(client, token, "小禾", "3")

    job = create_job(
        db,
        kind="problem",
        input_json={"kind": "problem", "content": "16+8"},
        curriculum_context_json={"stage": "primary", "grade": 1},
        objectives_json=["用凑十法计算"],
        idempotency_key=None,
    )
    result = generate_lesson.run(job.id)
    assert result["status"] == "SUCCEEDED", result

    factory = create_session_factory()
    with factory() as s:
        rev = get_revision(s, "make-ten-16-plus-8", result["revision"])
        assert rev is not None
        revision_id = rev.id

    switch = client.post(
        "/v1/children/" + child_id + "/switch-session", headers=auth(token)
    ).json()
    ct = switch["token"]
    sid = client.post(
        "/v1/sessions", json={"source": "home"}, headers=auth(ct)
    ).json()["session_id"]

    # 未发布：服务端拦截（前端隐藏可被绕过，服务端过滤为准）
    blocked = client.post(
        "/v1/sessions/" + sid + "/activities",
        json={
            "kind": "gate",
            "lesson_id": "make-ten-16-plus-8",
            "revision": result["revision"],
        },
        headers=auth(ct),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "LESSON_NOT_PUBLISHED"

    # 人工审核发布（证据齐备）
    pub = client.post(
        "/v1/admin/reviews/" + revision_id + "/publish",
        json={
            "teaching_gate_ok": True,
            "age_ok": True,
            "layout_ok": True,
            "human_reviewed": True,
        },
        headers=auth(_admin_login(client)),
    )
    assert pub.status_code == 200

    # 发布后孩子可开始课堂
    ok = client.post(
        "/v1/sessions/" + sid + "/activities",
        json={
            "kind": "gate",
            "lesson_id": "make-ten-16-plus-8",
            "revision": result["revision"],
        },
        headers=auth(ct),
    )
    assert ok.status_code == 201
    assert ok.json()["activity"]["activity_id"]


# ---------------------------------------------------------------- A4/A10：题库与积分规则


def test_admin_question_and_reward_rule_e2e(client):
    """A4：建题核验标志不可直传（422）；审核通过可入列表；A10：规则版本化。"""
    admin_token = _admin_login(client)

    created = client.post(
        "/v1/admin/questions",
        json={
            "content": "7+5=?",
            "answer": "12",
            "knowledge_code": "arithmetic.add_sub",
            "grade": 1,
        },
        headers=auth(admin_token),
    )
    assert created.status_code == 201
    qid = created.json()["id"]
    # 核验标志由服务端核验流程写入：管理端创建恒为 False
    assert created.json()["math_verified"] is False

    forged = client.post(
        "/v1/admin/questions",
        json={
            "content": "3+2=?",
            "answer": "5",
            "knowledge_code": "arithmetic.add_sub",
            "grade": 1,
            "math_verified": True,
        },
        headers=auth(admin_token),
    )
    assert forged.status_code == 422

    approved = client.post(
        f"/v1/admin/questions/{qid}/status",
        json={"status": "approved"},
        headers=auth(admin_token),
    )
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    listed = client.get("/v1/admin/questions?status=approved", headers=auth(admin_token))
    assert any(q["id"] == qid for q in listed.json()["items"])

    rule = client.post(
        "/v1/admin/reward-rules",
        json={
            "points_independent": 5,
            "points_assisted": 3,
            "points_demonstrated": 1,
            "daily_cap": None,
            "per_event_cap": None,
        },
        headers=auth(admin_token),
    )
    assert rule.status_code == 201
    assert rule.json()["event_type"] == "reward"
    rules = client.get("/v1/admin/reward-rules", headers=auth(admin_token)).json()
    assert any(r["version"] == rule.json()["version"] for r in rules["items"])


# ---------------------------------------------------------------- A14：安全反馈处置


def test_admin_safety_feedback_e2e(client, db):
    """A14：安全反馈处置——列表仅脱敏摘要，处置后状态更新。"""
    from app.admin_api.models import SafetyFeedback

    fb = SafetyFeedback(
        child_id="c-e2e-demo",
        summary_text="孩子表达情绪低落，建议家长关注",
        status="open",
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    admin_token = _admin_login(client)
    listed = client.get("/v1/admin/safety-feedbacks", headers=auth(admin_token))
    assert listed.status_code == 200
    row = next(r for r in listed.json()["items"] if r["id"] == fb.id)
    # 脱敏：不展示完整对话与真实标识
    assert row["child_id_masked"] != fb.child_id
    assert "*" in row["child_id_masked"]
    assert row["summary_text"] == fb.summary_text
    assert row["status"] == "open"

    handled = client.post(
        f"/v1/admin/safety-feedbacks/{fb.id}/handle", headers=auth(admin_token)
    )
    assert handled.status_code == 200
    assert handled.json()["status"] == "handled"
