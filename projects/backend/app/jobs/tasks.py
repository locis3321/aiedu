"""Celery 任务定义：生成主任务（分钟级，永远异步）。

生成逻辑走 intent-first pipeline（app.pipeline.run_pipeline）：
意图识别 → 数学核验 → skill 检索 → 规划 → 编译 → 政策门禁。
"""

import asyncio

from celery import Celery
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.storage.models import JobStageRun

settings = get_settings()
celery_app = Celery("aiedu", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
)


def generate_lesson_content(
    input_json: dict,
    curriculum_context: dict | None = None,
    objectives: list[str] | None = None,
    stage_cb=None,
    gate_cb=None,
) -> dict:
    """生成课程内容：intent-first pipeline → LessonSpec v2。

    stage_cb：六阶段进度回调（intent/verify/retrieve/plan/compile/review）。
    gate_cb：门禁结果回调（含 MAJOR 违规，供发布证据落库）。
    """
    from app.pipeline.pipeline import run_pipeline

    spec = asyncio.run(
        run_pipeline(
            input_json, curriculum_context, objectives, stage_cb=stage_cb, gate_cb=gate_cb
        )
    )
    return spec.model_dump(mode="json")


@celery_app.task(bind=True, name="aiedu.generate_lesson")
def generate_lesson(self, job_id: str) -> dict:
    """生成主任务：幂等领取 → 生成 → 发布 revision → SUCCEEDED。"""
    from app.jobs.service import (
        claim_stage_run,
        get_job,
        next_revision,
        publish_revision,
        transition_job,
    )
    from app.storage.db import create_session_factory

    factory = create_session_factory()
    with factory() as session:
        job = get_job(session, job_id)
        if job is None:
            return {"job_id": job_id, "status": "NOT_FOUND"}
        # 协作取消检查点
        if job.status == "CANCELED":
            return {"job_id": job_id, "status": "CANCELED"}

        try:
            run = claim_stage_run(
                session, job_id, "generate", _input_hash_of(job), job.attempt
            )
        except IntegrityError:
            # 并发 worker 已领取同一阶段：不重复生成（幂等）
            session.rollback()
            with factory() as other:
                run = (
                    other.query(JobStageRun)
                    .filter_by(job_id=job_id, stage="generate", attempt=job.attempt)
                    .first()
                )
                if run is None or run.status == "SUCCEEDED":
                    return {"job_id": job_id, "status": "SUCCEEDED"}
            return {"job_id": job_id, "status": "RUNNING"}
        if run.status == "SUCCEEDED":
            # 旧 attempt 已成功：重复消息直接返回，不覆盖结果
            return {"job_id": job_id, "status": "SUCCEEDED"}

        try:
            transition_job(session, job, "RUNNING")

            def _write_stage(stage: str) -> None:
                """六阶段进度落库（intent/verify/retrieve/plan/compile/review）。"""
                stage_run = JobStageRun(
                    job_id=job_id,
                    stage=stage,
                    attempt=job.attempt,
                    input_hash=_input_hash_of(job),
                    status="SUCCEEDED",
                )
                session.add(stage_run)
                session.commit()

            gate_issues: list[str] = []

            def _write_gate(issues: list[str]) -> None:
                gate_issues.extend(issues)

            spec_dict = generate_lesson_content(
                job.input_json,
                curriculum_context=job.curriculum_context_json,
                objectives=job.objectives_json,
                stage_cb=_write_stage,
                gate_cb=_write_gate,
            )
            # 生成期门禁结果作为发布证据落库（服务端产生，不由前端自证）
            spec_dict["_meta"] = {
                "gate_report": {
                    "issues": gate_issues,
                    "passed": not any(i.startswith("BLOCKER") for i in gate_issues),
                }
            }
            transition_job(session, job, "VALIDATING")
            rev = publish_revision(
                session,
                lesson_id=spec_dict["lesson_id"],
                revision=next_revision(session, spec_dict["lesson_id"]),
                spec_json=spec_dict,
                runtime_version=spec_dict["render"]["runtime_version"],
                asset_manifest_ref=None,
            )
            # 回写 job.lesson_id：job → 产物关联（GET /v1/lesson-jobs/{id} 契约字段）
            job.lesson_id = spec_dict["lesson_id"]
            transition_job(session, job, "SUCCEEDED")
            run.status = "SUCCEEDED"
            run.output_ref = rev.id
            session.commit()
            return {"job_id": job_id, "status": "SUCCEEDED", "revision": rev.revision}
        except Exception as exc:  # noqa: BLE001 —— 任务级兜底：显式 FAILED
            try:
                if job.status in ("QUEUED", "RUNNING", "VALIDATING"):
                    transition_job(session, job, "FAILED")
            except ValueError:
                # job 已被并发取消/完成（终态）：不再覆盖
                pass
            run.status = "FAILED"
            run.error_code = type(exc).__name__
            session.commit()
            return {"job_id": job_id, "status": "FAILED", "error": type(exc).__name__}


def _input_hash_of(job) -> str:
    import hashlib
    import json

    raw = json.dumps(job.input_json, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
