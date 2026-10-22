"""T12 验收测试：能力画像（规格 v2 §10 + 任务包验收项）。

覆盖：混合证据聚合（最高等级）、needs_review 不升级仅计数、无证据维度=待观察、
规则改版快照不追改、跨孩子隔离 403、证据链可审计、banned-phrase guard。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.router import get_session as accounts_get_session
from app.api.main import create_app
from app.learning.models import EvidenceRecord, LearningSession, SessionActivity
from app.learning.router import get_session as learning_get_session
from app.profile import service as profile_service
from app.profile.models import ProfileHistory, ProfileState, TraceEvent
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


def register_child(client, phone: str) -> tuple[str, str]:
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
    child_id = client.post(
        "/v1/children",
        json={"nickname": "小禾", "grade": "3"},
        headers=auth(token),
    ).json()["id"]
    switch = client.post(
        f"/v1/children/{child_id}/switch-session", headers=auth(token)
    ).json()
    return switch["token"], child_id


def make_evidence(db, child_id: str, kind: str, level: str) -> str:
    s = LearningSession(child_id=child_id)
    db.add(s)
    db.commit()
    act = SessionActivity(
        session_id=s.id,
        child_id=child_id,
        kind="gate",
        status="completed",
        method_source="skill",
    )
    db.add(act)
    db.commit()
    ev = EvidenceRecord(
        child_id=child_id,
        session_id=s.id,
        activity_id=act.id,
        kind=kind,
        level=level,
    )
    db.add(ev)
    db.commit()
    return ev.id


def dims_of(resp_body: dict) -> dict:
    return {d["code"]: d for d in resp_body["dimensions"]}


# ---------------------------------------------------------------- 聚合规则

def test_mixed_evidence_highest_level_wins(client, db):
    child_token, child_id = register_child(client, "13800000031")
    # gate_complete assisted + transfer_correct independent → operations/concept/transfer 取最高
    make_evidence(db, child_id, "gate_complete", "assisted")
    make_evidence(db, child_id, "transfer_correct", "independent")

    resp = client.get(
        f"/v1/children/{child_id}/profile/dimensions", headers=auth(child_token)
    )
    assert resp.status_code == 200
    dims = dims_of(resp.json())
    assert dims["operations"]["level"] == "assisted"
    assert dims["concept"]["level"] == "independent"
    assert dims["transfer"]["level"] == "independent"
    assert dims["number_sense"]["level"] == "needs_review"  # 无证据维度


def test_needs_review_does_not_upgrade_only_counts(client, db):
    child_token, child_id = register_child(client, "13800000032")
    make_evidence(db, child_id, "gate_complete", "needs_review")

    resp = client.get(
        f"/v1/children/{child_id}/profile/dimensions", headers=auth(child_token)
    )
    dims = dims_of(resp.json())
    assert dims["operations"]["level"] == "needs_review"
    assert dims["operations"].get("needs_review_count") == 1
    assert dims["operations"]["evidence_count"] == 0


def test_no_evidence_dimension_is_needs_review_not_zero(client, db):
    child_token, child_id = register_child(client, "13800000033")
    resp = client.get(
        f"/v1/children/{child_id}/profile/dimensions", headers=auth(child_token)
    )
    body = resp.json()
    assert body["as_of_version"] == profile_service.AGGREGATION_RULE_VERSION
    for d in body["dimensions"]:
        assert d["level"] == "needs_review"
        assert d["level_display"] == "待观察"
        assert d["evidence_count"] == 0
        assert "%" not in str(d) and "掌握度" not in str(d)


# ---------------------------------------------------------------- 版本化与隔离

def test_rule_version_change_snapshot_preserved(client, db, monkeypatch):
    child_token, child_id = register_child(client, "13800000034")
    make_evidence(db, child_id, "gate_complete", "independent")
    client.get(f"/v1/children/{child_id}/profile/dimensions", headers=auth(child_token))

    # 规则改版（模拟版本递增）→ 历史轨迹快照留存，不追改
    monkeypatch.setattr(profile_service, "AGGREGATION_RULE_VERSION", 2)
    client.get(f"/v1/children/{child_id}/profile/dimensions", headers=auth(child_token))

    hist = client.get(
        f"/v1/children/{child_id}/profile/history", headers=auth(child_token)
    ).json()
    assert len(hist["history"]) >= 1
    snap = hist["history"][0]
    assert snap["as_of_version"] == 1
    assert snap["snapshot_json"]["dimensions"][0]["level"] == "independent"

    rows = db.query(ProfileHistory).filter_by(child_id=child_id).all()
    assert len(rows) >= 1


def test_cross_child_read_forbidden(client, db):
    _, child_a = register_child(client, "13800000035")
    token_b, _ = register_child(client, "13800000036")
    make_evidence(db, child_a, "gate_complete", "independent")

    resp = client.get(
        f"/v1/children/{child_a}/profile/dimensions", headers=auth(token_b)
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_evidence_chain_auditable(client, db):
    child_token, child_id = register_child(client, "13800000037")
    evidence_id = make_evidence(db, child_id, "gate_complete", "independent")
    profile_service.append_trace(
        db,
        child_id=child_id,
        activity_id=None,
        kind="attempt",
        payload={"step_id": "find-complement", "correct": True},
    )
    client.get(f"/v1/children/{child_id}/profile/dimensions", headers=auth(child_token))

    state = db.query(ProfileState).filter_by(
        child_id=child_id, dimension_code="operations"
    ).one()
    # L3 → L2(evidence) → L1(trace) 链引用可回溯
    assert evidence_id in state.detail_json["evidence_ids"]
    trace_rows = db.query(TraceEvent).filter_by(child_id=child_id).all()
    assert len(trace_rows) == 1 and trace_rows[0].kind == "attempt"


def test_banned_phrase_guard():
    from app.core.errors import ApiError

    with pytest.raises(ApiError) as exc:
        profile_service.assert_no_banned("该孩子已掌握凑十法")
    assert exc.value.code == "BANNED_PHRASE"
    # 允许的表述不拦截
    profile_service.assert_no_banned("完成了一次独立练习，继续观察下一次表现。")
