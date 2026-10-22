"""D3–D4 测试：pipeline 级出课与能力边界（零 LLM 覆盖矩阵的回归）。"""

import pytest

from aiedu_core.pipeline import pipeline
from aiedu_core.services.llm_router import ModelRouter


def _no_llm_router(monkeypatch) -> ModelRouter:
    """禁用 LLM：模拟无 LLM env 环境（能力缺口语义）。"""
    router = ModelRouter()
    monkeypatch.setattr(router, "get", lambda role: None)
    return router


async def test_pipeline_borrow_ten_16_minus_9(monkeypatch) -> None:
    """16-9：破十法模板出课，verified + require_attempt 门槛。"""
    spec = await pipeline.run_pipeline(
        {"kind": "problem", "content": "16-9"},
        router=_no_llm_router(monkeypatch),
    )
    assert spec.lesson_id == "borrow-ten-16-minus-9"
    assert spec.verification.verified is True
    assert spec.teaching_design.skill_refs == ["borrow-ten"]
    assert spec.teaching_design.strategy_refs == ["borrow_ten@0.1.0"]
    gates = [n.gate.mode for n in spec.activity_graph if hasattr(n, "gate")]
    assert gates.count("require_attempt") >= 3


async def test_pipeline_borrow_ten_23_minus_8(monkeypatch) -> None:
    spec = await pipeline.run_pipeline(
        {"kind": "problem", "content": "23-8"},
        router=_no_llm_router(monkeypatch),
    )
    assert spec.lesson_id == "borrow-ten-23-minus-8"
    assert spec.verification.verified is True


async def test_pipeline_fraction_concept_lesson(monkeypatch) -> None:
    """概念型分数输入（取自 fraction-equal-parts examples）：模板出课且 verified。"""
    spec = await pipeline.run_pipeline(
        {"kind": "concept", "content": "一块披萨平均分成4份，取其中1份"},
        router=_no_llm_router(monkeypatch),
    )
    assert spec.lesson_id == "fraction-equal-parts-1-over-4"
    assert spec.verification.verified is True
    assert spec.teaching_design.skill_refs == ["fraction-equal-parts"]
    assert any(
        getattr(n, "gate", None) is not None and n.gate.mode == "require_attempt"
        for n in spec.activity_graph
    )


async def test_pipeline_two_digit_minus_two_digit_capability_gap(monkeypatch) -> None:
    """52-37（两位数减两位数）：本期不覆盖 → 显式 capability gap，不编造。"""
    with pytest.raises(pipeline.PipelineError, match="capability gap"):
        await pipeline.run_pipeline(
            {"kind": "problem", "content": "52-37"},
            router=_no_llm_router(monkeypatch),
        )


async def test_pipeline_fraction_arithmetic_capability_gap(monkeypatch) -> None:
    """1/2+1/4（分数四则）：本期明确不做 → 显式失败。"""
    with pytest.raises(pipeline.PipelineError, match="capability gap"):
        await pipeline.run_pipeline(
            {"kind": "concept", "content": "1/2+1/4"},
            router=_no_llm_router(monkeypatch),
        )


async def test_pipeline_make_ten_regression_23_plus_9(monkeypatch) -> None:
    """回归：凑十法 23+9 仍出课（模板映射泛化后不受影响）。"""
    spec = await pipeline.run_pipeline(
        {"kind": "problem", "content": "23+9"},
        router=_no_llm_router(monkeypatch),
    )
    assert spec.lesson_id == "make-ten-23-plus-9"
    assert spec.verification.verified is True
    assert spec.teaching_design.skill_refs == ["make-ten"]
