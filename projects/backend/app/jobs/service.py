"""Job service：创建/查询/取消/状态迁移 + outbox 同事务写入。

R2 §11：job创建和outbox写入在同一事务；worker以job_id+stage+input_hash幂等领取；
阶段输出持久化后再推进；取消采用协作检查；旧attempt不能覆盖新结果。
"""

import hashlib
import json

from sqlalchemy.orm import Session

from app.jobs.state import validate_transition
from app.storage.models import (
    DispatchOutbox,
    JobStageRun,
    LessonJob,
    LessonRevision,
)


def _input_hash(input_json: dict) -> str:
    raw = json.dumps(input_json, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_job(
    session: Session,
    *,
    kind: str,
    input_json: dict,
    curriculum_context_json: dict | None,
    objectives_json: list | None,
    idempotency_key: str | None = None,
) -> LessonJob:
    """创建 job + outbox（同一事务）；Idempotency-Key 去重返回已有 job。"""
    if idempotency_key:
        existing = (
            session.query(LessonJob)
            .filter_by(idempotency_key=idempotency_key)
            .first()
        )
        if existing is not None:
            return existing

    job = LessonJob(
        kind=kind,
        input_json=input_json,
        curriculum_context_json=curriculum_context_json,
        objectives_json=objectives_json,
        status="QUEUED",
        idempotency_key=idempotency_key,
    )
    session.add(job)
    session.flush()  # 获取 job.id

    outbox = DispatchOutbox(
        job_id=job.id,
        payload_json={
            "job_id": job.id,
            "input_hash": _input_hash(input_json),
            "stage": "generate",
        },
    )
    session.add(outbox)
    session.commit()
    session.refresh(job)
    return job


def get_job(session: Session, job_id: str) -> LessonJob | None:
    return session.get(LessonJob, job_id)


def transition_job(session: Session, job: LessonJob, next_status: str) -> LessonJob:
    """校验合法迁移后更新状态；非法迁移或状态已被并发改变时抛 ValueError。

    条件更新（WHERE status = :old）跨进程防状态回退：worker 持有陈旧 ORM 对象时
    不会把已 SUCCEEDED/CANCELED 的 job 覆盖回 RUNNING/FAILED。
    """
    if not validate_transition(job.status, next_status):
        raise ValueError(
            f"illegal transition {job.status} -> {next_status} for job {job.id}"
        )
    updated = (
        session.query(LessonJob)
        .filter(LessonJob.id == job.id, LessonJob.status == job.status)
        .update({LessonJob.status: next_status}, synchronize_session=False)
    )
    if updated == 0:
        session.rollback()
        raise ValueError(
            f"job {job.id} status was changed concurrently (expected {job.status})"
        )
    job.status = next_status
    session.commit()
    return job


def cancel_job(session: Session, job: LessonJob) -> LessonJob:
    """协作式取消：QUEUED/RUNNING/VALIDATING → CANCELED。

    - worker 运行中：worker 在阶段检查点看到 CANCELED 后停止后续发布；
    - 条件更新：DB 已是终态（SUCCEEDED/FAILED/CANCELED）时拒绝，防覆盖已发布结果。
    """
    if job.status in {"SUCCEEDED", "FAILED", "CANCELED"}:
        raise ValueError(f"job {job.id} already terminal ({job.status})")
    updated = (
        session.query(LessonJob)
        .filter(
            LessonJob.id == job.id,
            LessonJob.status.in_({"QUEUED", "RUNNING", "VALIDATING"}),
        )
        .update({LessonJob.status: "CANCELED"}, synchronize_session=False)
    )
    if updated == 0:
        session.rollback()
        raise ValueError(f"job {job.id} already terminal")
    job.status = "CANCELED"
    session.commit()
    return job


def claim_stage_run(
    session: Session, job_id: str, stage: str, input_hash: str, attempt: int
) -> JobStageRun | None:
    """worker 幂等领取阶段运行记录；同 (job_id, stage, attempt) 已存在则复用。"""
    run = (
        session.query(JobStageRun)
        .filter_by(job_id=job_id, stage=stage, attempt=attempt)
        .first()
    )
    if run is None:
        run = JobStageRun(
            job_id=job_id,
            stage=stage,
            attempt=attempt,
            input_hash=input_hash,
            status="RUNNING",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
    return run


def next_revision(session: Session, lesson_id: str) -> int:
    """同一课程可重新生成新版本（R2「课程版本」语义）：revision 递增。"""
    latest = (
        session.query(LessonRevision)
        .filter_by(lesson_id=lesson_id)
        .order_by(LessonRevision.revision.desc())
        .first()
    )
    return (latest.revision + 1) if latest else 1


def publish_revision(
    session: Session,
    *,
    lesson_id: str,
    revision: int,
    spec_json: dict,
    runtime_version: str,
    asset_manifest_ref: str | None,
) -> LessonRevision:
    """发布课程版本：DB事务引用最终 manifest；旧 attempt 不覆盖新结果由唯一约束保证。"""
    rev = LessonRevision(
        lesson_id=lesson_id,
        revision=revision,
        spec_json=spec_json,
        runtime_version=runtime_version,
        asset_manifest_ref=asset_manifest_ref,
    )
    session.add(rev)
    session.commit()
    session.refresh(rev)
    return rev


def get_revision(session: Session, lesson_id: str, revision: int) -> LessonRevision | None:
    return (
        session.query(LessonRevision)
        .filter_by(lesson_id=lesson_id, revision=revision)
        .first()
    )
