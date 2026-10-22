"""T6 验收测试：足迹与家长报告（规格 v2 §1.2/§5.3 + 任务包验收项）。

覆盖：证据分列计数（增量/30天）、画像视图投影、试卷结果解释（四级词无百分比）、
导出真实文件、删除清理关联数据、跨孩子隔离、空状态、易错跳转、分享脱敏。
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.router import get_session as accounts_get_session
from app.api.main import create_app
from app.learning.models import EvidenceRecord, LearningSession, SessionActivity
from app.learning.router import get_session as learning_get_session
from app.profile.models import ProfileState
from app.storage.db import Base

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
    app.dependency_overrides[accounts_get_session] = override
    app.dependency_overrides[learning_get_session] = override
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_parent(client, phone: str) -> tuple[str, str]:
    client.post("/v1/auth/sms/send", json={"phone": phone})
    data = client.post(
        "/v1/auth/parents/login-sms", json={"phone": phone, "code": FIXED_CODE}
    ).json()
    token, pid = data["token"], data["user"]["id"]
    for key in ("guardian_rules", "privacy_notice"):
        client.post(
            f"/v1/parents/{pid}/consents",
            json={"consent_key": key},
            headers=auth(token),
        )
    return token, pid


def register_child(client, phone: str) -> tuple[str, str, str]:
    """返回 (parent_token, child_id, child_token)。"""
    token, pid = register_parent(client, phone)
    child_id = client.post(
        "/v1/children",
        json={"nickname": "小禾", "grade": "3"},
        headers=auth(token),
    ).json()["id"]
    switch = client.post(
        f"/v1/children/{child_id}/switch-session", headers=auth(token)
    ).json()
    return token, child_id, switch["token"]


def make_evidence(db, child_id: str, level: str, kind: str = "gate_complete") -> str:
    s = LearningSession(child_id=child_id)
    db.add(s)
    db.commit()
    act = SessionActivity(
        session_id=s.id, child_id=child_id, kind="gate", status="completed"
    )
    db.add(act)
    db.commit()
    ev = EvidenceRecord(
        child_id=child_id,
        session_id=s.id,
        activity_id=act.id,
        kind=kind,
        level=level,
        detail_json={"paper_id": "paper-1"} if kind == "exam_result" else None,
    )
    db.add(ev)
    db.commit()
    return ev.id


# ---------------------------------------------------------------- 报告分列

def test_summary_counts_by_level_and_range(client, db):
    parent_token, child_id, _ = register_child(client, "13800000051")
    make_evidence(db, child_id, "independent")
    make_evidence(db, child_id, "assisted")
    make_evidence(db, child_id, "needs_review")

    resp = client.get(
        f"/v1/children/{child_id}/reports/summary?days=30", headers=auth(parent_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == {
        "independent": 1,
        "assisted": 1,
        "demonstrated": 0,
        "needs_review": 1,
    }
    assert body["total_events"] == 3
    assert "%" not in json.dumps(body) and "掌握度" not in json.dumps(body)


def test_summary_empty_state_no_sample_data(client):
    parent_token, child_id, _ = register_child(client, "13800000052")
    resp = client.get(
        f"/v1/children/{child_id}/reports/summary", headers=auth(parent_token)
    )
    body = resp.json()
    assert body["counts"] == {
        "independent": 0,
        "assisted": 0,
        "demonstrated": 0,
        "needs_review": 0,
    }
    assert body["note"] and "空状态" in body["note"]


# ---------------------------------------------------------------- 画像与试卷解释

def test_profile_view_projection(client, db):
    parent_token, child_id, _ = register_child(client, "13800000053")
    make_evidence(db, child_id, "independent")
    resp = client.get(
        f"/v1/children/{child_id}/reports/profile-view", headers=auth(parent_token)
    )
    body = resp.json()
    dims = {d["code"]: d for d in body["dimensions"]}
    assert dims["operations"]["level"] == "independent"
    assert dims["number_sense"]["level"] == "needs_review"  # 无证据维度=待观察
    assert body["no_score_note"] and "%" not in json.dumps(body)


def test_exam_interpretation_four_level_words(client, db):
    parent_token, child_id, _ = register_child(client, "13800000054")
    make_evidence(db, child_id, "independent", kind="exam_result")
    make_evidence(db, child_id, "needs_review", kind="exam_result")
    resp = client.get(
        f"/v1/children/{child_id}/reports/summary", headers=auth(parent_token)
    )
    interps = resp.json()["exam_interpretation"]
    assert len(interps) == 2
    assert all("掌握度" not in i["interpretation"] for i in interps)
    assert all(i["interpretation"] for i in interps)


# ---------------------------------------------------------------- 数据出口与隔离

def test_export_downloadable_and_delete_real(client, db):
    parent_token, child_id, _ = register_child(client, "13800000055")
    make_evidence(db, child_id, "independent")
    # 导出：真实可下载文件，内容与证据一致
    export_resp = client.post(
        f"/v1/children/{child_id}/data-exports", headers=auth(parent_token)
    )
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("application/json")
    payload = json.loads(export_resp.content)
    assert payload["summary_counts"]["independent"] == 1
    assert payload["note"] and "不含姓名" in payload["note"]

    # 删除：关联业务数据清理 + 确认；档案软删
    del_resp = client.delete(f"/v1/children/{child_id}/data", headers=auth(parent_token))
    assert del_resp.status_code == 200 and del_resp.json()["deleted"] is True
    assert db.query(EvidenceRecord).filter_by(child_id=child_id).count() == 0
    assert db.query(ProfileState).filter_by(child_id=child_id).count() == 0


def test_cross_child_access_forbidden(client):
    _, child_a, _ = register_child(client, "13800000056")
    token_b, _, _ = register_child(client, "13800000057")
    resp = client.get(
        f"/v1/children/{child_a}/reports/summary", headers=auth(token_b)
    )
    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------- 足迹与分享

def test_footprints_and_replay_ref(client, db):
    parent_token, child_id, _ = register_child(client, "13800000058")
    ev_id = make_evidence(db, child_id, "assisted")
    resp = client.get(
        f"/v1/children/{child_id}/footprints?days=30", headers=auth(parent_token)
    )
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["evidence_id"] == ev_id
    # 易错总结条目可跳转原课证据（关联 ID）
    assert item["replay_ref"] == item["activity_id"]
    assert body["review_pending"][0]["level"] == "assisted"


def test_share_preview_desensitized(client):
    parent_token, child_id, _ = register_child(client, "13800000059")
    resp = client.post(
        f"/v1/children/{child_id}/share/preview", headers=auth(parent_token)
    )
    body = resp.json()
    snap = body["snapshot"]
    assert snap["child_label"].startswith("一位")  # 匿名标识，无真实姓名/学校
    assert "no_fake_score_note" in snap
    # 链接分享未接入：显式呈现 not_connected，不伪造可撤销令牌（治理规则）
    status = body["share_status"]
    assert status["link_sharing"] == "not_connected"
    assert "未接入" in status["note"]
    assert "revoke_token" not in body and "share_params" not in body


# ---------------------------------------------------------------- 删除权限与清理完整

def test_delete_data_child_forbidden(client, db):
    """数据删除是家长权限：孩子本人 token 不得删除自己的数据。"""
    _, child_id, child_token = register_child(client, "13800000061")
    make_evidence(db, child_id, "independent")
    resp = client.delete(f"/v1/children/{child_id}/data", headers=auth(child_token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_delete_data_cleans_sessions_and_attempts(client, db):
    """删除清理完整：会话/活动/尝试一并清理，不留孤儿行。"""
    from app.learning.models import Attempt

    token, child_id, _ = register_child(client, "13800000062")
    make_evidence(db, child_id, "independent")
    act_id = db.query(SessionActivity).filter_by(child_id=child_id).first().id
    db.add(
        Attempt(
            activity_id=act_id,
            child_id=child_id,
            step_id="s1",
            kind="answer",
            value_json={},
            correct=True,
        )
    )
    db.commit()
    resp = client.delete(f"/v1/children/{child_id}/data", headers=auth(token))
    assert resp.status_code == 200 and resp.json()["deleted"] is True
    assert db.query(LearningSession).filter_by(child_id=child_id).count() == 0
    assert db.query(SessionActivity).filter_by(child_id=child_id).count() == 0
    assert db.query(Attempt).filter_by(child_id=child_id).count() == 0


def test_banned_phrase_guard_on_report_text(client, db):
    """banned-phrase guard 接入报告文本出口：绝对化断言被拦截（护栏2）。"""
    from app.profile.models import ProfileDimension

    parent_token, child_id, _ = register_child(client, "13800000063")
    make_evidence(db, child_id, "assisted")
    from app.profile import service as profile_service

    profile_service.ensure_dimensions(db)
    dim = db.get(ProfileDimension, "operations")
    dim.name = "已掌握运算"
    db.commit()
    resp = client.get(
        f"/v1/children/{child_id}/reports/summary?days=30", headers=auth(parent_token)
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "BANNED_PHRASE"
