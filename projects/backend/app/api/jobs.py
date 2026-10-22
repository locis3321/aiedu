"""Job API：异步生成入口（R2 §11 契约）。

POST /v1/lesson-jobs（Idempotency-Key）→ 202
GET  /v1/lesson-jobs/{job_id}
POST /v1/lesson-jobs/{job_id}/cancel → 202
GET  /v1/lessons/{lesson_id}/revisions/{revision}

鉴权：管理端角色 JWT。这些端点暴露生成内核与**含完整答案的课程规格**
（revision 原样返回 spec），孩子侧学习一律走 /sessions/* 的 answer-filtered
出口（服务端过滤为准），因此对匿名/孩子 token 关闭。护栏1/护栏5。
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.admin_api.router import get_admin_role
from app.jobs.service import (
    cancel_job,
    create_job,
    get_job,
    get_revision,
)
from app.models.teaching_request import CreateLessonJobRequest
from app.storage.db import create_session_factory

router = APIRouter(prefix="/v1")


def get_session():
    factory = create_session_factory()
    with factory() as session:
        yield session


@router.post("/lesson-jobs", status_code=202)
def create_lesson_job(
    request: CreateLessonJobRequest,
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _role: str = Depends(get_admin_role),
) -> dict:
    job = create_job(
        session,
        kind=request.input.kind,
        input_json=request.input.model_dump(mode="json"),
        curriculum_context_json=(
            request.curriculum_context.model_dump(mode="json")
            if request.curriculum_context
            else None
        ),
        objectives_json=request.objectives or None,
        idempotency_key=idempotency_key,
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "status_url": f"/v1/lesson-jobs/{job.id}",
    }


@router.get("/lesson-jobs/{job_id}")
def get_job_status(
    job_id: str,
    session: Session = Depends(get_session),
    _role: str = Depends(get_admin_role),
) -> dict:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "stage_version": job.stage_version,
        "attempt": job.attempt,
        "lesson_id": job.lesson_id,
        "error_code": job.error_code,
        "clarification": job.clarification_json,
    }


@router.post("/lesson-jobs/{job_id}/cancel", status_code=202)
def cancel(
    job_id: str,
    session: Session = Depends(get_session),
    _role: str = Depends(get_admin_role),
) -> dict:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        cancel_job(session, job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job_id": job.id, "status": "cancel_requested"}


@router.get("/lessons/{lesson_id}/revisions/{revision}")
def get_lesson_revision(
    lesson_id: str,
    revision: int,
    session: Session = Depends(get_session),
    _role: str = Depends(get_admin_role),
) -> dict:
    rev = get_revision(session, lesson_id, revision)
    if rev is None:
        raise HTTPException(status_code=404, detail="revision not found")
    return {
        "lesson_spec": rev.spec_json,
        "runtime_version": rev.runtime_version,
        "asset_manifest_ref": rev.asset_manifest_ref,
    }
