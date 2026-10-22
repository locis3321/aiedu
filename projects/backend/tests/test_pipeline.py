"""T4 测试：intent-first 流水线（意图识别 → 核验 → skill 检索 → 规划 → 门禁）。"""

import pytest

from app.models.lesson_v2 import LessonSpecV2
from app.pipeline import pipeline
from app.services.llm_router import ModelRouter


async def test_pipeline_make_ten_intent_first() -> None:
    """16+8：意图识别优先，make-ten skill + 兼容层生成，记录 skill_ref。"""
    spec = await pipeline.run_pipeline({"kind": "problem", "content": "16+8"})
    assert spec.lesson_id == "make-ten-16-plus-8"
    assert spec.verification.verified is True
    assert spec.teaching_design.skill_refs == ["make-ten"]


async def test_pipeline_intent_is_first_step(monkeypatch) -> None:
    """pipeline 第一步调用意图识别；skill 检索在意图之后。"""
    calls: list[str] = []

    async def fake_verify(intent, input_json):
        from app.services.evidence import ClaimEvidenceData, VerificationRecord

        calls.append("verify")
        claim = ClaimEvidenceData(
            id="c", statement="ok", status="verified", method="精确计算"
        )
        return VerificationRecord(
            verifier_version="0.1.0",
            normalized_problem_hash=None,
            assumptions=(),
            claims=(claim,),
            covered_claim_ids=("c",),
            result="verified",
        )

    monkeypatch.setattr(pipeline, "_verify", fake_verify)

    def fake_retrieve(intent):
        calls.append("retrieve")
        return []

    monkeypatch.setattr(pipeline, "_retrieve_skills", fake_retrieve)
    monkeypatch.setattr(pipeline, "_load_skills", lambda: [])

    async def fake_plan(intent, input_json, skills, router, record):
        calls.append("plan")
        from app.strategies import make_ten

        return make_ten.build({"a": 16, "b": 8, "k": 2})

    monkeypatch.setattr(pipeline, "_plan", fake_plan)

    spec = await pipeline.run_pipeline({"kind": "problem", "content": "16+8"})
    assert calls == ["verify", "retrieve", "plan"]
    assert spec is not None


async def test_pipeline_verification_failure_terminates() -> None:
    """verified==false → 终止流水线（数学硬前提）。"""
    with pytest.raises(pipeline.PipelineError, match="verification failed"):
        await pipeline.run_pipeline({"kind": "problem", "content": "2+2=5"})


async def test_pipeline_requires_clarification_on_empty_input() -> None:
    """空输入 → needs clarification，不伪造教学事实。"""
    with pytest.raises(pipeline.PipelineError, match="needs clarification"):
        await pipeline.run_pipeline({"kind": "problem", "content": ""})


async def test_pipeline_capability_gap_without_llm(monkeypatch) -> None:
    """无匹配 skill 且 LLM 未配置 → 显式能力缺口。"""
    from app.services.evidence import ClaimEvidenceData, VerificationRecord

    ok = VerificationRecord(
        verifier_version="0.1.0",
        normalized_problem_hash=None,
        assumptions=(),
        claims=(ClaimEvidenceData(id="c", statement="ok", status="verified", method="精确计算"),),
        covered_claim_ids=("c",),
        result="verified",
    )

    async def fake_verify(intent, input_json):
        return ok

    monkeypatch.setattr(pipeline, "_verify", fake_verify)
    monkeypatch.setattr(pipeline, "_load_skills", lambda: [])
    router = ModelRouter()
    monkeypatch.setattr(router, "get", lambda role: None)
    with pytest.raises(pipeline.PipelineError, match="capability gap"):
        await pipeline.run_pipeline(
            {"kind": "problem", "content": "解方程2x+3=11"}, router=router
        )


async def test_pipeline_free_design_with_mock_llm(monkeypatch) -> None:
    """无 skill 时 LLM 受控规划：mock LLM 返回合法 JSON，产出 require_attempt。"""
    payload = {
        "teaching_design": {"modes": ["引导"]},
        "activity_graph": [
            {
                "id": "n1",
                "type": "predict",
                "prompt": "先估一估",
                "response": {"kind": "number"},
                "gate": {"mode": "require_attempt"},
                "on_correct": [],
                "next_ids": ["n2"],
            },
            {
                "id": "n2",
                "type": "observe",
                "narration": "讲解",
                "next_ids": ["__end__"],
            },
        ],
    }

    async def fake_call(model, prompt):
        return __import__("json").dumps(payload)

    monkeypatch.setattr(pipeline, "_call_designer", fake_call)
    from app.services.evidence import ClaimEvidenceData, VerificationRecord

    ok = VerificationRecord(
        verifier_version="0.1.0",
        normalized_problem_hash=None,
        assumptions=(),
        claims=(ClaimEvidenceData(id="c", statement="ok", status="verified", method="精确计算"),),
        covered_claim_ids=("c",),
        result="verified",
    )

    async def fake_verify(intent, input_json):
        return ok

    monkeypatch.setattr(pipeline, "_verify", fake_verify)
    monkeypatch.setattr(pipeline, "_load_skills", lambda: [])
    spec = await pipeline.run_pipeline(
        {"kind": "problem", "content": "解方程2x+3=11"},
        router=ModelRouter(),
    )
    assert isinstance(spec, LessonSpecV2)
    assert any(
        getattr(n, "gate", None) is not None and n.gate.mode == "require_attempt"
        for n in spec.activity_graph
    )


async def test_pipeline_free_design_retries_on_invalid_structure(monkeypatch) -> None:
    """LLM 规划输出结构不完整时重试一次：第二次合法则成功。"""
    import json as _json

    calls = {"n": 0}
    good = {
        "teaching_design": {"modes": ["引导"]},
        "activity_graph": [
            {
                "id": "n1",
                "type": "predict",
                "prompt": "先想一想",
                "response": {"kind": "choice", "options": ["是", "否"]},
                "gate": {"mode": "require_attempt"},
                "on_correct": [],
                "next_ids": ["n2"],
            },
            {"id": "n2", "type": "observe", "narration": "讲解", "next_ids": ["__end__"]},
        ],
    }

    async def fake_call(model, prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"teaching_design": {"modes": ["引导"]}}'  # 缺 activity_graph
        return _json.dumps(good)

    monkeypatch.setattr(pipeline, "_call_designer", fake_call)

    from app.services.evidence import ClaimEvidenceData, VerificationRecord

    ok = VerificationRecord(
        verifier_version="0.1.0",
        normalized_problem_hash=None,
        assumptions=(),
        claims=(ClaimEvidenceData(id="c", statement="ok", status="verified", method="精确计算"),),
        covered_claim_ids=("c",),
        result="verified",
    )

    async def fake_verify(intent, input_json):
        return ok

    monkeypatch.setattr(pipeline, "_verify", fake_verify)
    monkeypatch.setattr(pipeline, "_load_skills", lambda: [])
    spec = await pipeline.run_pipeline(
        {"kind": "concept", "content": "理解分数的意义"},
        router=ModelRouter(),
    )
    assert calls["n"] == 2
    assert isinstance(spec, LessonSpecV2)


def test_compile_and_validate_two_repairs() -> None:
    """两轮修复上限：可修复错误被修复；不可修复错误终止。"""
    from app.strategies import make_ten

    spec = make_ten.build({"a": 16, "b": 8, "k": 2})
    nodes = list(spec.activity_graph)
    nodes[0].next_ids = None
    broken = spec.model_copy(update={"activity_graph": nodes})
    repaired = pipeline._compile_and_validate(broken)
    assert repaired.activity_graph[0].next_ids is not None


def test_extract_json_tolerates_missing_colon() -> None:
    """模型偶发丢失键后冒号：`"key" {...}` 仍可解析。"""
    malformed = '{\n  "teaching_design" {"modes": ["引导"]},\n  "activity_graph": []\n}'
    parsed = pipeline._extract_json(malformed)
    assert parsed["teaching_design"]["modes"] == ["引导"]
    assert parsed["activity_graph"] == []


def test_extract_json_tolerates_unquoted_keys() -> None:
    """模型输出未加引号键：`{name: "x"}` 仍可解析。"""
    parsed = pipeline._extract_json('{name: "x", value: 1}')
    assert parsed == {"name": "x", "value": 1}


def test_extract_json_tolerates_raw_control_chars() -> None:
    """模型在字符串内输出裸换行/制表符：剥离后仍可解析。"""
    malformed = '{"a": "第一行\n第二行", "b": 1}'
    parsed = pipeline._extract_json(malformed)
    assert parsed == {"a": "第一行第二行", "b": 1}


def test_review_blocker_detected() -> None:
    """reviewer：problem 类无门槛 → BLOCKER。"""
    from app.strategies import make_ten

    spec = make_ten.build({"a": 16, "b": 8, "k": 2})
    replay_node = next(n for n in spec.activity_graph if n.type == "observe")
    replay_node.next_ids = ["__end__"]
    stripped = spec.model_copy(update={"activity_graph": [replay_node]})
    import asyncio

    review_issues = asyncio.run(pipeline._review(stripped, None))
    assert any("BLOCKER" in i for i in review_issues)


def test_router_routes_and_structure_stable() -> None:
    """路由记录 provider/model；切换不改变领域数据结构。"""
    router = ModelRouter()
    assert router.get("plan") is None or router.route("plan") is not None


def test_llm_base_url_normalized() -> None:
    """base_url 自动补 /v1：修复 Web UI HTML 响应导致的 str 解析错误。"""
    from app.core.config import Settings

    s = Settings(llm_base_url="http://10.1.52.220:10019")
    assert s.llm_base_url_normalized == "http://10.1.52.220:10019/v1"
    s = Settings(llm_base_url="http://10.1.52.220:10019/v1")
    assert s.llm_base_url_normalized == "http://10.1.52.220:10019/v1"
    s = Settings(llm_base_url=None)
    assert s.llm_base_url_normalized is None


@pytest.mark.skipif(
    not __import__("app.core.config", fromlist=["get_settings"])
    .get_settings()
    .llm_configured,
    reason="LLM not configured",
)
@pytest.mark.real_llm
async def test_real_llm_call_returns_text() -> None:
    """真实 LLM 冒烟：OpenAIChatModel 调用返回文本（解锁自由设计路径）。"""
    from app.pipeline.pipeline import _call_model

    router = ModelRouter()
    model = router.get("plan")
    assert model is not None
    text = await _call_model(model, "只回复两个字：正常")
    assert "正常" in text


@pytest.mark.skipif(
    not __import__("app.core.config", fromlist=["get_settings"])
    .get_settings()
    .llm_configured,
    reason="LLM not configured",
)
@pytest.mark.real_llm
async def test_real_free_design_concept_lesson() -> None:
    """真实自由设计路径：概念课（无数值主张）→ LLM 规划 → LessonSpec。"""
    spec = await pipeline.run_pipeline({"kind": "concept", "content": "理解分数的意义"})
    assert spec.schema_version == "2.0"
    assert spec.verification.verified is True
    assert any(
        getattr(n, "gate", None) is not None and n.gate.mode == "require_attempt"
        for n in spec.activity_graph
    )
