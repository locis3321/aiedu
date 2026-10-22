"""T5 测试：Job API（幂等/状态/取消/revision）+ service 状态机。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.jobs import get_session
from app.api.main import create_app
from app.core.config import get_settings
from app.jobs.service import create_job, transition_job
from app.storage.db import Base


@pytest.fixture(autouse=True)
def _admin_dev_login(monkeypatch):
    """内核 API 需管理 JWT：本地开发态登录签发（生产接 SSO）。"""
    monkeypatch.setenv("ADMIN_DEV_LOGIN_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def admin_headers(client) -> dict:
    resp = client.post("/v1/admin/login", json={"role": "admin"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": "Bearer " + resp.json()["token"]}


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override():
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c


PROBLEM = {"input": {"kind": "problem", "content": "16+8"}}


def test_create_job_returns_202(client) -> None:
    resp = client.post("/v1/lesson-jobs", json=PROBLEM, headers=admin_headers(client))
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "QUEUED"
    assert body["status_url"] == f"/v1/lesson-jobs/{body['job_id']}"


def test_jobs_api_requires_admin(client) -> None:
    """护栏1：内核接口暴露完整答案，匿名/孩子 token 一律拒绝。"""
    assert client.post("/v1/lesson-jobs", json=PROBLEM).status_code == 401


def test_idempotency_key_dedup(client) -> None:
    headers = admin_headers(client) | {"Idempotency-Key": "test-key-1"}
    r1 = client.post("/v1/lesson-jobs", json=PROBLEM, headers=headers)
    r2 = client.post("/v1/lesson-jobs", json=PROBLEM, headers=headers)
    assert r1.json()["job_id"] == r2.json()["job_id"]


def test_get_job_status_and_404(client) -> None:
    h = admin_headers(client)
    job_id = client.post("/v1/lesson-jobs", json=PROBLEM, headers=h).json()["job_id"]
    resp = client.get(f"/v1/lesson-jobs/{job_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "QUEUED"
    assert client.get("/v1/lesson-jobs/nonexistent", headers=h).status_code == 404


def test_cancel_flow(client) -> None:
    h = admin_headers(client)
    job_id = client.post("/v1/lesson-jobs", json=PROBLEM, headers=h).json()["job_id"]
    resp = client.post(f"/v1/lesson-jobs/{job_id}/cancel", headers=h)
    assert resp.status_code == 202
    assert client.get(f"/v1/lesson-jobs/{job_id}", headers=h).json()["status"] == "CANCELED"
    # 终态不可再取消
    assert client.post(f"/v1/lesson-jobs/{job_id}/cancel", headers=h).status_code == 409


def test_revision_not_found(client) -> None:
    h = admin_headers(client)
    assert client.get("/v1/lessons/none/revisions/1", headers=h).status_code == 404
    # 匿名不可读 revision（含完整答案的规格）
    assert client.get("/v1/lessons/none/revisions/1").status_code == 401


def test_generate_lesson_content_make_ten() -> None:
    from app.jobs.tasks import generate_lesson_content

    spec = generate_lesson_content({"kind": "problem", "content": "16+8"})
    assert spec["schema_version"] == "2.0"
    assert spec["verification"]["verified"] is True
    assert spec["lesson_id"] == "make-ten-16-plus-8"


def test_generate_lesson_content_unmatched_fails() -> None:
    """未支持题型：数学核验能力缺口 → PipelineError（不假装覆盖）。"""
    from app.jobs.tasks import generate_lesson_content
    from app.pipeline.pipeline import PipelineError

    with pytest.raises(PipelineError, match="verification failed"):
        generate_lesson_content({"kind": "problem", "content": "解方程2x+3=11"})


# ---------------------------------------------------------------------------
# service 层：状态机与取消语义（直接 session）
# ---------------------------------------------------------------------------

def test_transition_stale_object_cannot_rollback(session_factory) -> None:
    """跨进程状态回退防护：陈旧 ORM 对象不能把已成功 job 覆盖回 RUNNING。"""
    from app.jobs.service import get_job

    with session_factory() as s1, session_factory() as s2:
        job = create_job(
            s1,
            kind="problem",
            input_json={"kind": "problem", "content": "16+8"},
            curriculum_context_json=None,
            objectives_json=None,
        )
        transition_job(s1, job, "RUNNING")
        # 另一 worker 视角完成
        other = get_job(s2, job.id)
        transition_job(s2, other, "VALIDATING")
        transition_job(s2, other, "SUCCEEDED")
        # 陈旧对象尝试回退 → 必须失败（条件更新命中 0 行）
        with pytest.raises(ValueError):
            transition_job(s1, job, "FAILED")


def test_transition_validation(session_factory) -> None:
    with session_factory() as session:
        job = create_job(
            session,
            kind="problem",
            input_json={"kind": "problem", "content": "16+8"},
            curriculum_context_json=None,
            objectives_json=None,
        )
        transition_job(session, job, "RUNNING")
        transition_job(session, job, "VALIDATING")
        transition_job(session, job, "SUCCEEDED")
        # 终态不可再迁移
        with pytest.raises(ValueError):
            transition_job(session, job, "FAILED")


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
