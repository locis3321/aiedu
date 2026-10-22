"""D9–D10 测试：使用日志设施（可选落盘、零侵入、不记录敏感内容）。"""

import json

import pytest

from aiedu_mcp import tools
from aiedu_core.pipeline import pipeline as core_pipeline
from aiedu_core.services.llm_router import ModelRouter


def _disable_llm(monkeypatch) -> None:
    router = ModelRouter()
    monkeypatch.setattr(router, "get", lambda role: None)
    monkeypatch.setattr(core_pipeline, "default_router", lambda: router)


def test_no_log_file_when_env_unset(tmp_path, monkeypatch) -> None:
    """未设置 AIEDU_USAGE_LOG → 完全不落盘、行为不变。"""
    monkeypatch.delenv("AIEDU_USAGE_LOG", raising=False)
    target = tmp_path / "usage.jsonl"
    monkeypatch.setenv("AIEDU_USAGE_LOG", "")  # 空值同样视为未配置
    out = tools.verify_math("7x8", 56)
    assert out["result"] == "verified"
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_log_written_when_env_set(tmp_path, monkeypatch) -> None:
    """设置 AIEDU_USAGE_LOG → 每次调用写一行合法 JSONL。"""
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("AIEDU_USAGE_LOG", str(log))
    out = tools.verify_math("7x8", 56)
    assert out["result"] == "verified"
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "verify_math"
    assert record["v"] == 1  # 架构增量 v1 · C3：JSONL schema 版本字段
    assert record["result"] == "ok"
    assert record["args"]["kind"] == "arith"
    assert isinstance(record["duration_ms"], int)
    assert record["ts"].endswith("Z")


def test_log_appends_multiple_calls(tmp_path, monkeypatch) -> None:
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("AIEDU_USAGE_LOG", str(log))
    tools.verify_math("7x8", 56)
    tools.verify_math("7x8", 57)
    records = [json.loads(l) for l in log.read_text(encoding="utf-8").strip().splitlines()]
    # 工具调用本身成功 → result=ok；数学结论另记 detail
    assert [r["result"] for r in records] == ["ok", "ok"]
    assert [r.get("detail") for r in records] == ["verified", "refuted"]


def test_log_classifies_capability_gap(tmp_path, monkeypatch) -> None:
    """能力缺口 → result=capability_gap（可统计 gap 触发率）。"""
    _disable_llm(monkeypatch)
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("AIEDU_USAGE_LOG", str(log))
    out = tools.generate_lesson("52-37")
    assert out["error"] == "capability_gap"
    record = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["tool"] == "generate_lesson"
    assert record["result"] == "capability_gap"
    assert record["args"]["kind"] == "arith"


def test_log_classifies_invalid_input(tmp_path, monkeypatch) -> None:
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("AIEDU_USAGE_LOG", str(log))
    out = tools.get_lesson({"lesson_id": "x", "spec": {"activity_graph": []}})
    assert out["error"] == "invalid_input"
    record = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["result"] == "invalid_input"


def test_log_does_not_store_question_text_or_keys(tmp_path, monkeypatch) -> None:
    """日志不含完整题面与密钥（只留题型/长度摘要）。"""
    _disable_llm(monkeypatch)
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("AIEDU_USAGE_LOG", str(log))
    secret = "孩子作业-7x8-绝密"
    monkeypatch.setenv("LLM_API_KEY", "sk-should-never-be-logged")
    tools.generate_lesson(secret)
    raw = log.read_text(encoding="utf-8")
    assert secret not in raw
    assert "sk-should-never-be-logged" not in raw
    record = json.loads(raw.strip().splitlines()[-1])
    assert record["args"]["kind"] == "arith"
    assert record["args"]["question_len"] == len(secret)
    assert "question" not in record["args"]


def test_log_records_spec_node_count_not_content(tmp_path, monkeypatch) -> None:
    """spec 类入参只记节点数，不记 spec 内容。"""
    _disable_llm(monkeypatch)
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("AIEDU_USAGE_LOG", str(log))
    spec = tools.generate_lesson("16+8")["spec"]
    tools.get_lesson(spec, reveal="filtered")
    record = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["tool"] == "get_lesson"
    assert record["args"]["nodes"] == len(spec["activity_graph"])
    assert record["args"]["reveal"] == "filtered"
    # args 摘要里只有计数与枚举，没有 spec 内容
    assert set(record["args"]) == {"nodes", "reveal", "unlocked"}
