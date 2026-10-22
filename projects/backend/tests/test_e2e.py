"""T9 E2E：完整用户旅程（需要本地栈：compose PG16 + Redis）。

运行：uv run pytest -m e2e -v
默认 pytest 通过 addopts 排除 e2e（见 pyproject）。
"""

import os

import pytest

from app.jobs.service import cancel_job, create_job, get_revision
from app.jobs.tasks import generate_lesson
from app.models.lesson_v2 import LessonSpecV2
from app.pipeline import pipeline
from app.storage.db import create_session_factory

pytestmark = pytest.mark.e2e


def test_full_journey_make_ten() -> None:
    """POST job(16+8) → worker生成 → SUCCEEDED → revision → validate通过。

    验证 intent-first 产物：skill_refs（make-ten skill）、先想后看门槛、
    儿童友好呈现（presentation）。
    """
    factory = create_session_factory()
    with factory() as session:
        job = create_job(
            session,
            kind="problem",
            input_json={"kind": "problem", "content": "16+8"},
            curriculum_context_json={"stage": "primary", "grade": 1},
            objectives_json=["用凑十法计算"],
            idempotency_key=None,
        )
        job_id = job.id

    result = generate_lesson.run(job_id)
    assert result["status"] == "SUCCEEDED", result

    with factory() as session:
        rev = get_revision(session, "make-ten-16-plus-8", result["revision"])
        assert rev is not None, "revision must be published"
        spec = LessonSpecV2.model_validate(rev.spec_json)
        assert spec.verification.verified is True
        # intent-first：skill_refs 记录 make-ten skill（兼容层关联）
        assert spec.teaching_design.skill_refs == ["make-ten"]
        assert spec.teaching_design.strategy_refs == ["make_ten@0.1.0"]
        # 「先想后看」门槛存在
        gates = [n.gate.mode for n in spec.activity_graph if hasattr(n, "gate")]
        assert gates.count("require_attempt") >= 3
        # 儿童友好呈现：低年级 + 场景隐喻 + 温和反馈
        pres = spec.presentation
        assert pres is not None
        assert pres.age_band == "lower_primary"
        assert pres.scene_metaphor == "berry_basket"
        assert pres.feedback_tone == "encouraging"


@pytest.mark.real_llm
@pytest.mark.skipif(
    not (
        os.environ.get("LLM_BASE_URL")
        and os.environ.get("LLM_API_KEY")
        and os.environ.get("LLM_MODEL_NAME")
    ),
    reason="real LLM not configured",
)
def test_full_journey_concept_free_design() -> None:
    """概念课（自由设计路径）：job → 真实LLM规划 → SUCCEEDED → revision。"""
    factory = create_session_factory()
    with factory() as session:
        job = create_job(
            session,
            kind="concept",
            input_json={"kind": "concept", "content": "理解分数的意义"},
            curriculum_context_json={"stage": "primary", "grade": 3},
            objectives_json=["理解分数表示等分"],
            idempotency_key=None,
        )
        job_id = job.id

    result = generate_lesson.run(job_id)
    assert result["status"] == "SUCCEEDED", result

    with factory() as session:
        rev = get_revision(session, "free-design", result["revision"])
        assert rev is not None
        spec = LessonSpecV2.model_validate(rev.spec_json)
        assert spec.verification.verified is True
        # 先想后看：至少一个 attempt-gated 节点
        gates = [n.gate.mode for n in spec.activity_graph if hasattr(n, "gate")]
        assert any(g in {"require_attempt", "require_correct_or_assisted"} for g in gates)


async def test_verification_failure_terminates() -> None:
    """负路径：数学核验失败 → pipeline终止，不产出课程。"""
    with pytest.raises(pipeline.PipelineError):
        await pipeline.run_pipeline({"kind": "problem", "content": "2+2=5"})


def test_cancel_no_publish() -> None:
    """负路径：取消后无后续发布。"""
    factory = create_session_factory()
    with factory() as session:
        job = create_job(
            session,
            kind="problem",
            input_json={"kind": "problem", "content": "15+7"},
            curriculum_context_json=None,
            objectives_json=None,
        )
        cancel_job(session, job)
        job_id = job.id

    result = generate_lesson.run(job_id)
    assert result["status"] == "CANCELED"

    with factory() as session:
        assert get_revision(session, "make-ten-15-plus-7", 1) is None


def test_half_product_not_accessible() -> None:
    """负路径：未发布 revision 不可访问（半成品）。"""
    factory = create_session_factory()
    with factory() as session:
        assert get_revision(session, "does-not-exist", 1) is None
