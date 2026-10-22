"""T5 验收测试：题库与练习安排（规格 v2 §11 + 任务包验收项）。

覆盖：内置题 CRUD/审核态/检索、未审核不入抽题、题源未接入显式呈现、
按薄弱点安排、全路线可视化、L1 重排、变式程序化+核验、摸底跨知识点、
测评结果写入证据体系、无 skill 仍可规划。
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
from app.questionbank import service as qb_service
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


def register_child(client, phone: str = "13800000041") -> tuple[str, str]:
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


def seed_questions(db, n=3, knowledge_code="arithmetic.add_sub", approved=True):
    ids = []
    for i in range(n):
        q = qb_service.create_question(
            db,
            content=f"题目{i}：16+8=?",
            answer=f"{24 + i}",
            knowledge_code=knowledge_code,
            grade=1,
            math_verified=True,
        )
        if approved:
            qb_service.update_question_status(db, q["id"], "approved")
        ids.append(q["id"])
    return ids


def make_weak_evidence(db, child_id: str, level: str = "assisted") -> str:
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
        kind="gate_complete",
        level=level,
    )
    db.add(ev)
    db.commit()
    return ev.id


# ---------------------------------------------------------------- 题库

def test_question_crud_review_and_search(client, db):
    q = qb_service.create_question(
        db,
        content="16+8=?",
        answer="24",
        knowledge_code="arithmetic.add_sub",
        grade=1,
        math_verified=True,
    )
    assert q["status"] == "draft"
    qb_service.update_question_status(db, q["id"], "approved")
    hits = qb_service.search_questions(db, knowledge_code="arithmetic.add_sub")
    assert len(hits) == 1 and hits[0]["status"] == "approved"


def test_unapproved_questions_excluded_from_sampling(client, db):
    seed_questions(db, n=2, approved=True)
    seed_questions(db, n=2, approved=False)  # draft 不入抽题
    qb_service.create_exam_template(
        db, type_="sync", title="同步练习", question_ids=None, rules={}
    )
    # 直接以模板抽题路径验证：仅已审核题
    picked = qb_service.sample_approved(db, ["arithmetic.add_sub"], count=10)
    assert len(picked) == 2
    assert all(p.status == "approved" for p in picked)


# ---------------------------------------------------------------- 题源

def _tizhuang_mock_transport(quota_ok: bool = True, with_solution: bool = False):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/v1/trials"):
            return httpx.Response(
                200,
                json={
                    "trial_token": "trial-abc",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            )
        if path.endswith("/v1/trial/quota"):
            if not quota_ok:
                return httpx.Response(403, json={"detail": "配额用尽"})
            return httpx.Response(200, json={"remaining": 100})
        if path.endswith("/v1/trial/questions"):
            item = {
                "id": 1,
                "content": "16+8=?",
                "answer": "24",
                "analysis": "凑十法",
                "knowledge": "arithmetic.add_sub",
            }
            return httpx.Response(
                200,
                json={"items": [item] if not with_solution else [item]},
            )
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def test_source_connect_via_tizhuang_mock(client, db):
    from app.questionbank.tizhuang import TizhuangClient

    src = qb_service.create_source(
        db,
        name="题庄在线题库",
        provider="tizhuang",
        endpoint="https://tizhuang.qcscience.cc/api",
        quota="100/day",
        knowledge_mapping={"keyword": "凑十法"},
    )
    client_inst = TizhuangClient(transport=_tizhuang_mock_transport())
    result = qb_service.connect_test(db, src["id"], client=client_inst)
    assert result["connected"] is True
    assert "已连接" in result["note"]
    assert result["knowledge_mapping_hit"] is False  # mapping 无 knowledge_code


def test_source_search_redacts_solutions(client, db):
    from app.questionbank.tizhuang import TizhuangClient

    src = qb_service.create_source(
        db,
        name="题庄在线题库",
        provider="tizhuang",
        knowledge_mapping={"keyword": "凑十法"},
    )
    client_inst = TizhuangClient(transport=_tizhuang_mock_transport())
    result = qb_service.search_external(db, src["id"], client=client_inst)
    assert result["source_note"].startswith("来源：题庄在线题库")
    assert result["answer_filtered"] is True
    q0 = result["questions"][0]
    assert "answer" not in q0 and "analysis" not in q0  # 脱敏（先想后看）


def test_source_failure_fail_closed(client, db):
    from app.questionbank.tizhuang import TizhuangClient

    src = qb_service.create_source(
        db, name="题庄在线题库", provider="tizhuang"
    )
    client_inst = TizhuangClient(transport=_tizhuang_mock_transport(quota_ok=False))
    result = qb_service.connect_test(db, src["id"], client=client_inst)
    assert result["connected"] is False
    assert "未接入" in result["note"]


# ---------------------------------------------------------------- 练习安排

def test_practice_set_from_weak_profile(client, db):
    child_token, child_id = register_child(client)
    seed_questions(db, n=3)
    make_weak_evidence(db, child_id, level="assisted")  # operations 维度薄弱

    resp = client.post(
        f"/v1/children/{child_id}/practice-sets", headers=auth(child_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["questions"]) > 0
    assert "operations" in body["basis"]["weak_dimensions"]
    assert body["basis"]["source"] == "profile"


# ---------------------------------------------------------------- 路线

def test_route_static_visualization_and_l1(client, db):
    child_token, child_id = register_child(client)
    make_weak_evidence(db, child_id, level="assisted")
    resp = client.get(f"/v1/children/{child_id}/route", headers=auth(child_token))
    assert resp.status_code == 200
    body = resp.json()
    stages = {s["stage"]: s for s in body["stages"]}
    assert set(stages.keys()) >= {"primary", "junior", "senior"}
    primary_nodes = stages["primary"]["nodes"]
    assert any(n["code"] == "arithmetic.add_sub" for n in primary_nodes)
    assert any("objective" in n for n in primary_nodes)
    # L1：证据驱动插变式
    assert body["l1_reorder"] and body["l1_reorder"][0]["action"] == "insert_variant"
    # L2：跨单元补洞（沿前置链回溯）
    assert body["l2_backfill"] and body["l2_backfill"][0]["action"] == "backfill"
    # 无 skill 仍可规划：source=graph（skill 不作为规划许可）
    assert body["source"] == "graph"


# ---------------------------------------------------------------- 试卷与变式

def test_diagnostic_cross_knowledge_and_exam_result_evidence(client, db):
    child_token, child_id = register_child(client)
    for code in ("arithmetic.add_sub", "fraction.mean", "application.word_problem"):
        seed_questions(db, n=1, knowledge_code=code)
    tpl = qb_service.create_exam_template(db, type_="diagnostic", title="摸底")
    from app.questionbank.models import ExamTemplate as _ET

    _tpl_row = db.get(_ET, tpl["id"])
    _tpl_row.review_status = "approved"
    db.commit()
    resp = client.post(
        f"/v1/children/{child_id}/exams/generate?template_id={tpl['id']}",
        headers=auth(child_token),
    )
    assert resp.status_code == 200
    paper = resp.json()
    codes = {q["knowledge_code"] for q in paper["questions"]}
    assert len(codes) >= 2  # 摸底跨知识点

    answers = {q["id"]: q["answer"] for q in paper["questions"]}
    submit = client.post(
        f"/v1/exams/{paper['paper_id']}/submit",
        json=answers,
        headers=auth(child_token),
    )
    assert submit.status_code == 200
    body = submit.json()
    assert body["overall_level"] == "independent"
    # 结果写入证据体系（T3 evidence）
    ev_rows = db.query(EvidenceRecord).filter_by(kind="exam_result").all()
    assert len(ev_rows) == 1 and ev_rows[0].level == "independent"


def test_variant_programmatic_and_verified(client):
    child_token, _ = register_child(client)
    resp = client.post(
        "/v1/variants/generate",
        json={"kind": "problem", "content": "16+8"},
        headers=auth(child_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["params"]["a"] != 16 or body["params"]["b"] != 8  # 参数程序化变化


# ---------------------------------------------------------------- 归属校验

def test_submit_exam_other_parent_forbidden(client, db):
    """跨家长隔离：非拥有者家长 token 不得提交他人孩子的试卷。"""
    child_token, child_a = register_child(client, "13800000041")
    seed_questions(db, n=1, knowledge_code="arithmetic.add_sub")
    tpl = qb_service.create_exam_template(db, type_="diagnostic", title="摸底")
    from app.questionbank.models import ExamTemplate as _ET

    _tpl_row = db.get(_ET, tpl["id"])
    _tpl_row.review_status = "approved"
    db.commit()
    paper = client.post(
        f"/v1/children/{child_a}/exams/generate?template_id={tpl['id']}",
        headers=auth(child_token),
    ).json()
    # 另一个家长（非拥有者）
    client.post("/v1/auth/sms/send", json={"phone": "13800000099"})
    other_login = client.post(
        "/v1/auth/parents/login-sms",
        json={"phone": "13800000099", "code": FIXED_CODE},
    ).json()
    resp = client.post(
        f"/v1/exams/{paper['paper_id']}/submit",
        json={"answers": {}},
        headers=auth(other_login["token"]),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
