"""T3 验收测试：学习闭环与证据（规格 v2 §2/§3/§4 + 任务包验收项）。

覆盖：先想后看双层（answer-filtered 无答案字段 / 未完成完整解答 403）、
错误提示阶梯（不给答案）、证据分级（independent/assisted/demonstrated/needs_review）、
session 多活动续接、method_source、Gate 契约校验、六阶段进度、hash 复用。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.router import get_session as accounts_get_session
from app.api.main import create_app
from app.jobs.service import create_job, publish_revision
from app.learning.models import EvidenceRecord, SessionActivity
from app.learning.router import get_session as learning_get_session
from app.learning.service import ensure_lesson
from app.storage.db import Base
from app.storage.models import JobStageRun, LessonJob
from app.strategies import make_ten

PHONE = "13800000011"
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


def _spec_dict() -> dict:
    spec = make_ten.build({"a": 16, "b": 8, "k": 2})
    return spec.model_dump(mode="json")


def _publish(db, spec_dict: dict) -> None:
    publish_revision(
        db,
        lesson_id=spec_dict["lesson_id"],
        revision=spec_dict.get("revision", 1),
        spec_json=spec_dict,
        runtime_version="0.1.0",
        asset_manifest_ref=None,
    )
    _mark_published(db, spec_dict)


def register_child(client) -> tuple[str, str]:
    """注册家长→同意→建档→签发 child token。"""
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


def start_gate_activity(client, child_token: str, spec_dict: dict) -> tuple[str, str]:
    """开始会话并启动 make-ten 课程活动，返回 (activity_id, session_id)。"""
    sid = client.post("/v1/sessions", json={"source": "home"}, headers=auth(child_token)).json()[
        "session_id"
    ]
    resp = client.post(
        f"/v1/sessions/{sid}/activities",
        json={
            "kind": "gate",
            "lesson_id": spec_dict["lesson_id"],
            "revision": spec_dict.get("revision", 1),
        },
        headers=auth(child_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["activity"]["activity_id"], sid


# ---------------------------------------------------------------- 先想后看

def test_answer_filtered_has_no_answer_fields(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, _ = start_gate_activity(client, child_token, spec_dict)

    resp = client.get(
        f"/v1/activities/{activity_id}/answer-filtered", headers=auth(child_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_filtered"] is True
    nodes = body["spec"]["activity_graph"]
    for n in nodes:
        if n.get("type") == "observe":
            assert n["narration"] == "" and n.get("locked") is True
        if n.get("response"):
            assert n["response"].get("expected") is None
            assert n["response"].get("correct_index") is None


def test_full_answer_locked_before_completion(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, _ = start_gate_activity(client, child_token, spec_dict)

    resp = client.get(f"/v1/activities/{activity_id}/answer", headers=auth(child_token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ANSWER_LOCKED"


# ---------------------------------------------------------------- 尝试与提示

def test_wrong_attempt_returns_hint_not_answer(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, _ = start_gate_activity(client, child_token, spec_dict)

    resp = client.post(
        f"/v1/activities/{activity_id}/attempts",
        json={"step_id": "find-complement", "value": 99},
        headers=auth(child_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is False
    assert body["hint"] and "10-8" in body["hint"]
    assert "answer" not in body and "expected" not in json_dumps(body)


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj)


def test_correct_first_try_writes_independent_evidence(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, _ = start_gate_activity(client, child_token, spec_dict)

    for step_id, value in (
        ("find-complement", 2),
        ("find-source", 2),
        ("find-sum", 24),
        ("transfer-practice", 33),
    ):
        resp = client.post(
            f"/v1/activities/{activity_id}/attempts",
            json={"step_id": step_id, "value": value},
            headers=auth(child_token),
        )
        assert resp.status_code == 200 and resp.json()["correct"] is True

    ev = db.query(EvidenceRecord).filter_by(activity_id=activity_id).all()
    kinds = {e.kind: e.level for e in ev}
    assert kinds.get("gate_complete") == "independent"
    assert kinds.get("transfer_correct") == "independent"
    act = db.get(SessionActivity, activity_id)
    assert act.status == "completed"

    # 完成后完整解答可读（回放用途）
    full = client.get(f"/v1/activities/{activity_id}/answer", headers=auth(child_token))
    assert full.status_code == 200


def test_assisted_level_after_wrong_then_correct(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, _ = start_gate_activity(client, child_token, spec_dict)

    client.post(
        f"/v1/activities/{activity_id}/attempts",
        json={"step_id": "find-complement", "value": 5},
        headers=auth(child_token),
    )
    for step_id, value in (
        ("find-complement", 2),
        ("find-source", 2),
        ("find-sum", 24),
        ("transfer-practice", 33),
    ):
        client.post(
            f"/v1/activities/{activity_id}/attempts",
            json={"step_id": step_id, "value": value},
            headers=auth(child_token),
        )
    ev = db.query(EvidenceRecord).filter_by(activity_id=activity_id).all()
    kinds = {e.kind: e.level for e in ev}
    assert kinds.get("gate_complete") == "assisted"


def test_transfer_demonstrated_with_two_hints(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, _ = start_gate_activity(client, child_token, spec_dict)

    for step_id, value in (
        ("find-complement", 2),
        ("find-source", 2),
        ("find-sum", 24),
    ):
        client.post(
            f"/v1/activities/{activity_id}/attempts",
            json={"step_id": step_id, "value": value},
            headers=auth(child_token),
        )
    # 迁移题请求两次提示后答对 → demonstrated
    for _ in range(2):
        client.post(
            f"/v1/activities/{activity_id}/hints",
            json={"step_id": "transfer-practice"},
            headers=auth(child_token),
        )
    client.post(
        f"/v1/activities/{activity_id}/attempts",
        json={"step_id": "transfer-practice", "value": 33},
        headers=auth(child_token),
    )
    ev = db.query(EvidenceRecord).filter_by(activity_id=activity_id).all()
    kinds = {e.kind: e.level for e in ev}
    assert kinds.get("transfer_correct") == "demonstrated"


def test_needs_review_on_abandoned_session(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, session_id = start_gate_activity(client, child_token, spec_dict)

    client.post(
        f"/v1/activities/{activity_id}/attempts",
        json={"step_id": "find-complement", "value": 5},
        headers=auth(child_token),
    )
    # 结束会话：有尝试未完成 → needs_review（R2'）
    resp = client.post(
        f"/v1/sessions/{session_id}/complete", headers=auth(child_token)
    )
    assert resp.status_code == 200
    ev = db.query(EvidenceRecord).filter_by(activity_id=activity_id).all()
    assert any(e.kind == "abandoned" and e.level == "needs_review" for e in ev)


def test_session_continues_with_next_task(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, session_id = start_gate_activity(client, child_token, spec_dict)

    for step_id, value in (
        ("find-complement", 2),
        ("find-source", 2),
        ("find-sum", 24),
        ("transfer-practice", 33),
    ):
        client.post(
            f"/v1/activities/{activity_id}/attempts",
            json={"step_id": step_id, "value": value},
            headers=auth(child_token),
        )
    # 单题完成后 session 仍可启动下一活动（变式/同步练习），不能停在一道题
    resp = client.post(
        f"/v1/sessions/{session_id}/activities",
        json={
            "kind": "variant",
            "lesson_id": spec_dict["lesson_id"],
            "revision": spec_dict.get("revision", 1),
        },
        headers=auth(child_token),
    )
    assert resp.status_code == 201
    detail = client.get(f"/v1/sessions/{session_id}", headers=auth(child_token)).json()
    assert len(detail["activities"]) == 2
    assert detail["activities"][0]["status"] == "completed"


def test_method_source_field(client, db):
    spec_dict = _spec_dict()
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, _ = start_gate_activity(client, child_token, spec_dict)
    filtered = client.get(
        f"/v1/activities/{activity_id}/answer-filtered", headers=auth(child_token)
    ).json()
    # make-ten 为策略族（strategy_refs）→ skill（R4：推荐方法·凑十法）
    assert filtered["method_source"] == "skill"


def test_gate_contract_invalid_type_rejected(client, db):
    spec_dict = _spec_dict()
    nodes = spec_dict["activity_graph"]
    nodes[0]["gate"] = {"type": "swipe", "mode": "require_attempt"}
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    sid = client.post("/v1/sessions", json={"source": "home"}, headers=auth(child_token)).json()[
        "session_id"
    ]
    resp = client.post(
        f"/v1/sessions/{sid}/activities",
        json={
            "kind": "gate",
            "lesson_id": spec_dict["lesson_id"],
            "revision": spec_dict.get("revision", 1),
        },
        headers=auth(child_token),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "GATE_CONTRACT_INVALID"


def test_no_programmatic_answer_fails_explicitly(client, db):
    spec_dict = _spec_dict()
    for n in spec_dict["activity_graph"]:
        if n.get("id") == "find-complement":
            n["response"]["expected"] = None
            n["response"]["kind"] = "number"
    _publish(db, spec_dict)
    child_token, _ = register_child(client)
    activity_id, _ = start_gate_activity(client, child_token, spec_dict)
    resp = client.post(
        f"/v1/activities/{activity_id}/attempts",
        json={"step_id": "find-complement", "value": 2},
        headers=auth(child_token),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_PROGRAMMATIC_ANSWER"


# ---------------------------------------------------------------- 六阶段与复用

def test_six_stages_endpoint_shape(client, db):
    job = create_job(
        db,
        kind="problem",
        input_json={"kind": "problem", "content": "16+8"},
        curriculum_context_json=None,
        objectives_json=None,
        idempotency_key="stages-test",
    )
    for stage in ("intent", "verify", "retrieve", "plan", "compile", "review"):
        db.add(
            JobStageRun(
                job_id=job.id,
                stage=stage,
                attempt=0,
                input_hash="h",
                status="SUCCEEDED",
            )
        )
    db.commit()

    child_token, _ = register_child(client)
    resp = client.get(f"/v1/jobs/{job.id}/stages", headers=auth(child_token))
    assert resp.status_code == 200
    body = resp.json()
    names = [s["stage"] for s in body["stages"]]
    assert names == ["intent", "verify", "retrieve", "plan", "compile", "review"]
    assert all(s["status"] == "SUCCEEDED" for s in body["stages"])


def test_hash_reuse_same_input_same_revision(client, db):
    input_json = {"kind": "problem", "content": "16+8"}
    first = ensure_lesson(db, input_json)
    job = first["job"]
    # 模拟生成完成：SUCCEEDED + lesson_id + revision
    job.status = "SUCCEEDED"
    job.lesson_id = "make-ten-16-plus-8"
    db.commit()
    spec_dict = _spec_dict()
    publish_revision(
        db,
        lesson_id="make-ten-16-plus-8",
        revision=1,
        spec_json=spec_dict,
        runtime_version="0.1.0",
        asset_manifest_ref=None,
    )
    _mark_published(db, spec_dict)

    second = ensure_lesson(db, input_json)
    assert second["job"].id == job.id  # 同输入复用同一 job（不重复调度）
    assert second["spec_dict"]["lesson_id"] == spec_dict["lesson_id"]
    assert (
        db.query(LessonJob)
        .filter_by(idempotency_key=first["job"].idempotency_key)
        .count()
        == 1
    )


def test_six_stages_written_during_generation():
    """生成 make-ten（策略路径，无 LLM）时六阶段回调依次触发。"""
    from app.jobs.tasks import generate_lesson_content

    recorded: list[str] = []
    spec_dict = generate_lesson_content(
        {"kind": "problem", "content": "16+8"},
        curriculum_context={"stage": "primary", "grade": 1},
        objectives=["用凑十法计算"],
        stage_cb=recorded.append,
    )
    assert recorded == ["intent", "verify", "retrieve", "plan", "compile", "review"]
    assert spec_dict["teaching_design"]["skill_refs"] == ["make-ten"]


# ---------------------------------------------------------------- 发布门禁（护栏5）

def _mark_published(db, spec_dict: dict) -> None:
    """模拟人工审核发布：写 ReviewRecord(published)（发布门禁验收）。"""
    from app.admin_api.models import ReviewRecord
    from app.storage.models import LessonRevision

    rev = (
        db.query(LessonRevision)
        .filter_by(
            lesson_id=spec_dict["lesson_id"],
            revision=spec_dict.get("revision", 1),
        )
        .first()
    )
    record = ReviewRecord(revision_id=rev.id, lesson_id=rev.lesson_id)
    record.math_verified = True
    record.teaching_gate_ok = True
    record.age_ok = True
    record.layout_ok = True
    record.human_reviewed = True
    record.status = "published"
    db.add(record)
    db.commit()


def test_unpublished_revision_rejected_on_start(client, db):
    """护栏5：未经人工审核发布的课程不得进入孩子课堂（服务端强制）。"""
    spec_dict = _spec_dict()
    publish_revision(
        db,
        lesson_id=spec_dict["lesson_id"],
        revision=1,
        spec_json=spec_dict,
        runtime_version="0.1.0",
        asset_manifest_ref=None,
    )
    child_token, _ = register_child(client)
    sid = client.post("/v1/sessions", json={"source": "home"}, headers=auth(child_token)).json()[
        "session_id"
    ]
    resp = client.post(
        f"/v1/sessions/{sid}/activities",
        json={"kind": "gate", "lesson_id": spec_dict["lesson_id"], "revision": 1},
        headers=auth(child_token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "LESSON_NOT_PUBLISHED"


def test_hash_reuse_unpublished_raises(client, db):
    """hash 复用：job SUCCEEDED 但 revision 未审核 → 不返回 spec，显式失败。"""
    input_json = {"kind": "problem", "content": "16+8"}
    first = ensure_lesson(db, input_json)
    job = first["job"]
    job.status = "SUCCEEDED"
    job.lesson_id = "make-ten-16-plus-8"
    db.commit()
    spec_dict = _spec_dict()
    publish_revision(
        db,
        lesson_id="make-ten-16-plus-8",
        revision=1,
        spec_json=spec_dict,
        runtime_version="0.1.0",
        asset_manifest_ref=None,
    )
    with pytest.raises(Exception) as excinfo:
        ensure_lesson(db, input_json)
    assert getattr(excinfo.value, "code", None) == "LESSON_NOT_PUBLISHED"


# ---------------------------------------------------------------- 答案过滤（护栏1 服务端）

def test_filtered_spec_scrubs_claims_replay_and_meta() -> None:
    """未完成门槛时：verification.claims.statement 置空、replay 移除、_meta 永不下发。"""
    from app.learning.service import _filtered_spec

    spec = {
        "lesson_id": "free-design",
        "verification": {
            "verified": True,
            "claims": [{"id": "c1", "statement": "16+8=24（凑十：14+10=24）"}],
        },
        "replay": {"steps": [{"action": "arithmetic.group_total"}]},
        "_meta": {"gate_report": {"issues": []}},
        "activity_graph": [
            {
                "id": "n1",
                "type": "predict",
                "gate": {"mode": "require_attempt"},
                "response": {"kind": "numeric", "expected": 24},
            },
            {
                "id": "n2",
                "type": "observe",
                "narration": "所以 16+8=24",
            },
        ],
    }
    filtered = _filtered_spec(spec, correct_ids=set(), all_gates_done=False)
    assert filtered["verification"]["claims"][0]["statement"] == ""
    assert "replay" not in filtered
    assert "_meta" not in filtered
    assert filtered["activity_graph"][0]["response"]["expected"] is None
    assert filtered["activity_graph"][1]["narration"] == ""

    # 门槛全部完成：答案字段恢复（回放可见），但 _meta 仍不下发
    done = _filtered_spec(spec, correct_ids={"n1"}, all_gates_done=True)
    assert done["verification"]["claims"][0]["statement"] != ""
    assert "replay" in done
    assert "_meta" not in done
    assert done["activity_graph"][0]["response"]["expected"] == 24
