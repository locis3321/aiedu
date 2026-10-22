"""T4 验收测试：积分与成长（规格 v2 §2 R7' + 任务包验收项）。

覆盖：幂等发放（同证据仅一条流水）、规则改版后旧证据不重复发放、
历史流水不改写、每日/每事件上限、各级奖励值配置断言、兑换预留显式未接入、
无孩子上下文显式失败。
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
from app.points import service as points_service
from app.points.models import LedgerEntry
from app.storage.db import Base

PHONE = "13800000021"
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


def register_child(client) -> tuple[str, str]:
    client.post("/v1/auth/sms/send", json={"phone": PHONE})
    data = client.post(
        "/v1/auth/parents/login-sms", json={"phone": PHONE, "code": FIXED_CODE}
    ).json()
    token, pid = data["token"], data["user"]["id"]
    for key in ("guardian_rules", "privacy_notice"):
        client.post(
            f"/v1/parents/{pid}/consents",
            json={"consent_key": key},
            headers={"Authorization": f"Bearer {token}"},
        )
    child_id = client.post(
        "/v1/children",
        json={"nickname": "小禾", "grade": "3"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]
    switch = client.post(
        f"/v1/children/{child_id}/switch-session",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    return switch["token"], child_id


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_evidence(db, child_id: str, level: str = "independent") -> str:
    """直接构造一条完成证据（session/activity/evidence）。"""
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
        kind="gate_complete",
        level=level,
    )
    db.add(ev)
    db.commit()
    return ev.id


def seed_rule(db, **overrides) -> None:
    points_service.create_rule_version(
        db,
        event_type="reward",
        points_independent=overrides.get("independent", 8),
        points_assisted=overrides.get("assisted", 4),
        points_demonstrated=overrides.get("demonstrated", 2),
        daily_cap=overrides.get("daily_cap"),
        per_event_cap=overrides.get("per_event_cap"),
        enabled=overrides.get("enabled", True),
    )


def grant(client, child_token: str, evidence_id: str):
    return client.post(
        "/v1/rewards/grant", json={"evidence_id": evidence_id}, headers=auth(child_token)
    )


# ---------------------------------------------------------------- 幂等与改版

def test_grant_idempotent_same_evidence(client, db):
    child_token, child_id = register_child(client)
    evidence_id = make_evidence(db, child_id)
    seed_rule(db)

    r1 = grant(client, child_token, evidence_id)
    assert r1.status_code == 200 and r1.json()["idempotent"] is False
    r2 = grant(client, child_token, evidence_id)
    assert r2.status_code == 200 and r2.json()["idempotent"] is True
    assert r1.json()["entry"]["points"] == r2.json()["entry"]["points"]

    rows = db.query(LedgerEntry).filter_by(evidence_id=evidence_id).all()
    assert len(rows) == 1  # 唯一约束 + 幂等：仅一条流水
    ledger = client.get(
        f"/v1/children/{child_id}/ledger", headers=auth(child_token)
    ).json()
    assert ledger["balance"] == rows[0].points


def test_rule_version_change_no_double_grant(client, db):
    child_token, child_id = register_child(client)
    evidence_id = make_evidence(db, child_id)
    seed_rule(db, independent=8)

    r1 = grant(client, child_token, evidence_id)
    assert r1.json()["entry"]["rule_version"] == 1

    # 规则改版（新版本，值不同）→ 旧证据再请求：幂等返回，不产生第二条流水
    seed_rule(db, independent=10)
    r2 = grant(client, child_token, evidence_id)
    assert r2.status_code == 200 and r2.json()["idempotent"] is True
    assert r2.json()["entry"]["rule_version"] == 1  # 历史流水保留原版本值

    rows = db.query(LedgerEntry).filter_by(evidence_id=evidence_id).all()
    assert len(rows) == 1 and rows[0].points == 8  # 历史流水不改写


def test_levels_reward_values_per_rule(client, db):
    child_token, child_id = register_child(client)
    seed_rule(db, independent=8, assisted=4, demonstrated=2)

    amounts = {}
    for level in ("independent", "assisted", "demonstrated"):
        ev = make_evidence(db, child_id, level=level)
        resp = grant(client, child_token, ev)
        assert resp.status_code == 200
        amounts[level] = resp.json()["entry"]["points"]
    assert amounts["independent"] > amounts["assisted"] > amounts["demonstrated"]
    assert amounts == {"independent": 8, "assisted": 4, "demonstrated": 2}


# ---------------------------------------------------------------- 上限

def test_daily_cap_blocks_grant(client, db):
    child_token, child_id = register_child(client)
    seed_rule(db, daily_cap=1)
    ev1 = make_evidence(db, child_id)
    ev2 = make_evidence(db, child_id)

    assert grant(client, child_token, ev1).status_code == 200
    resp = grant(client, child_token, ev2)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "REACHED_DAILY_CAP"
    rows = db.query(LedgerEntry).filter_by(child_id=child_id).all()
    assert len(rows) == 1


def test_per_event_cap_blocks_grant(client, db):
    child_token, child_id = register_child(client)
    seed_rule(db, per_event_cap=2)
    evs = [make_evidence(db, child_id) for _ in range(3)]

    assert grant(client, child_token, evs[0]).status_code == 200
    assert grant(client, child_token, evs[1]).status_code == 200
    resp = grant(client, child_token, evs[2])
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "REACHED_EVENT_CAP"


# ---------------------------------------------------------------- 显式失败

def test_grant_without_auth_fails(client):
    resp = client.post("/v1/rewards/grant", json={"evidence_id": "x"})
    assert resp.status_code == 401


def test_grant_missing_evidence_fails_explicitly(client):
    child_token, _ = register_child(client)
    resp = grant(client, child_token, "nonexistent-evidence")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_grant_without_active_rule_fails_explicitly(client, db):
    child_token, child_id = register_child(client)
    evidence_id = make_evidence(db, child_id)
    # 未配置任何规则：显式失败，不自动挑选默认值
    resp = grant(client, child_token, evidence_id)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RULE_NOT_CONFIGURED"


def test_needs_review_not_rewarded(client, db):
    child_token, child_id = register_child(client)
    seed_rule(db)
    evidence_id = make_evidence(db, child_id, level="needs_review")
    resp = grant(client, child_token, evidence_id)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "LEVEL_NOT_REWARDED"


def test_redeem_reserved_explicit_not_available(client):
    child_token, _ = register_child(client)
    resp = client.post("/v1/rewards/redeem", json={}, headers=auth(child_token))
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "REDEEM_NOT_AVAILABLE"
