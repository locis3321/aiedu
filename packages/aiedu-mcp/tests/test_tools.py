"""D5–D6 测试：4 个 MCP tool 的直接函数调用（不走网络）。"""

import json

import pytest

from aiedu_mcp import tools
from aiedu_core.pipeline import pipeline as core_pipeline
from aiedu_core.services.llm_router import ModelRouter


def _disable_llm(monkeypatch) -> None:
    """测试内模拟无 LLM env：default_router 返回 get()→None 的 router。

    pass 在宿主（有真实 LLM env）与干净环境行为一致，保证可复现。
    """
    router = ModelRouter()
    monkeypatch.setattr(router, "get", lambda role: None)
    monkeypatch.setattr(core_pipeline, "default_router", lambda: router)


# ---------------------------------------------------------------------------
# verify_math
# ---------------------------------------------------------------------------

def test_verify_math_verified() -> None:
    out = tools.verify_math("7x8", 56)
    assert out["result"] == "verified"
    assert out["claims"][0]["status"] == "verified"
    assert out["covered_claim_ids"] == ["arithmetic-eq"]
    assert out["verifier_version"]


def test_verify_math_refuted_not_claiming_true() -> None:
    """refuted 如实返回，绝不可写成 verified。"""
    out = tools.verify_math("7x8", 57)
    assert out["result"] == "refuted"
    assert out["claims"][0]["status"] == "refuted"
    assert out["covered_claim_ids"] == []


def test_verify_math_requires_review() -> None:
    out = tools.verify_math("__import__('os')", 1)
    assert out["result"] == "requires_review"
    assert "受限解析拒绝" in out["claims"][0]["method"]


# ---------------------------------------------------------------------------
# generate_lesson
# ---------------------------------------------------------------------------

def test_generate_lesson_make_ten(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    out = tools.generate_lesson("16+8")
    assert out["lesson_id"] == "make-ten-16-plus-8"
    assert out["verification"]["verified"] is True
    assert out["spec"]["schema_version"] == "2.0"


def test_generate_lesson_borrow_ten(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    out = tools.generate_lesson("16-9")
    assert out["lesson_id"] == "borrow-ten-16-minus-9"
    assert out["verification"]["verified"] is True


def test_generate_lesson_capability_gap_no_spec(monkeypatch) -> None:
    """硬约束 3：未覆盖题型返回结构化 capability_gap，不编造 spec。"""
    _disable_llm(monkeypatch)
    out = tools.generate_lesson("52-37")
    assert out["error"] == "capability_gap"
    assert "capability gap" in out["detail"]
    assert "spec" not in out and "lesson_id" not in out


# ---------------------------------------------------------------------------
# get_lesson（硬约束 1）
# ---------------------------------------------------------------------------

def _make_ten_spec() -> dict:
    out = tools.generate_lesson("16+8")
    return out["spec"]


def test_get_lesson_filtered_hides_unlocked(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    spec = _make_ten_spec()
    out = tools.get_lesson(spec, reveal="filtered", unlocked_ids=[])
    assert out["reveal"] == "filtered"
    for node in out["spec"]["activity_graph"]:
        if node["type"] == "predict":
            assert node["response"]["expected"] is None, node["id"]
        if node["type"] == "observe":
            assert node["narration"] == ""


def test_get_lesson_full_reveals_answers(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    spec = _make_ten_spec()
    out = tools.get_lesson(spec, reveal="full")
    expected_values = [
        n["response"]["expected"]
        for n in out["spec"]["activity_graph"]
        if n["type"] == "predict" and n["response"].get("expected")
    ]
    assert expected_values, "full 模式下应能看到程序化答案"
    assert all(v is not None for v in expected_values)


def test_get_lesson_unlocked_nodes_visible(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    spec = _make_ten_spec()
    unlocked = {"find-complement", "find-source"}
    out = tools.get_lesson(spec, reveal="filtered", unlocked_ids=list(unlocked))
    nodes = {n["id"]: n for n in out["spec"]["activity_graph"]}
    assert nodes["find-complement"]["response"]["expected"] == "2"
    assert nodes["find-sum"]["response"]["expected"] is None


# ---------------------------------------------------------------------------
# get_lesson 输入验证（信封 / 缺 activity_graph / 合法）
# ---------------------------------------------------------------------------

def test_get_lesson_rejects_envelope(monkeypatch) -> None:
    """信封入参（generate_lesson 的整个返回对象）必须显式报错，不能静默通过。"""
    _disable_llm(monkeypatch)
    envelope = tools.generate_lesson("16+8")
    assert "spec" in envelope and "activity_graph" not in envelope
    out = tools.get_lesson(envelope)
    assert out["error"] == "invalid_input"
    assert "spec 字段内容" in out["hint"]


def test_get_lesson_rejects_missing_activity_graph() -> None:
    out = tools.get_lesson({"schema_version": "2.0", "lesson_id": "x"})
    assert out["error"] == "invalid_input"
    assert "activity_graph" in out["detail"]


def test_get_lesson_rejects_bad_node() -> None:
    out = tools.get_lesson(
        {"schema_version": "2.0", "activity_graph": [{"type": "predict"}]}
    )
    assert out["error"] == "invalid_input"


def test_get_lesson_accepts_valid_spec(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    out = tools.get_lesson(_make_ten_spec())
    assert out["reveal"] == "filtered"
    assert "error" not in out


# ---------------------------------------------------------------------------
# render_lesson（真实渲染服务；不可用时显式失败）
# ---------------------------------------------------------------------------

def _make_ten_spec_for_render() -> dict:
    # 借用 generate_lesson 的真实 spec（_make_ten_spec 已有；此处直接复用其结构）
    spec = _make_ten_spec()
    return spec


def test_render_lesson_url_roundtrip(monkeypatch) -> None:
    """D5：本地拼 URL——spec 以 base64url 自包含，可解码还原（契约不变）。"""
    import base64 as _b64

    _disable_llm(monkeypatch)
    monkeypatch.setenv("AIEDU_PLAYER_URL", "http://127.0.0.1:8130")
    spec = _make_ten_spec_for_render()
    out = tools.render_lesson(spec)
    assert out["lesson_id"] == spec["lesson_id"]
    assert out["url"].startswith("http://127.0.0.1:8130/lesson.html?spec=")
    encoded = out["url"].split("?spec=")[1]
    decoded = json.loads(_b64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert decoded == spec  # JSON 往返相等
    assert "player_unavailable" not in out  # 错误类型消亡（无服务端依赖）


def test_render_lesson_public_url_resolution(monkeypatch) -> None:
    """D5：AIEDU_PUBLIC_URL → {base}/player（确定性绝对 URL）。"""
    _disable_llm(monkeypatch)
    monkeypatch.delenv("AIEDU_PLAYER_URL", raising=False)
    monkeypatch.setenv("AIEDU_PUBLIC_URL", "https://demo.example.com")
    out = tools.render_lesson(_make_ten_spec_for_render())
    assert out["url"].startswith("https://demo.example.com/player/lesson.html?spec=")


def test_render_lesson_prefers_player_url(monkeypatch) -> None:
    """AIEDU_PLAYER_URL 显式设置时优先级最高。"""
    _disable_llm(monkeypatch)
    monkeypatch.setenv("AIEDU_PLAYER_URL", "http://127.0.0.1:8130")
    monkeypatch.setenv("AIEDU_PUBLIC_URL", "https://demo.example.com")
    out = tools.render_lesson(_make_ten_spec_for_render())
    assert out["url"].startswith("http://127.0.0.1:8130/")


def test_render_lesson_rejects_envelope() -> None:
    out = tools.render_lesson({"lesson_id": "x", "spec": {"activity_graph": []}})
    assert out["error"] == "invalid_input"


# ---------------------------------------------------------------------------
# submit_attempt（服务端判分，证据两级）
# ---------------------------------------------------------------------------

def test_submit_attempt_correct_independent(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    spec = _make_ten_spec()
    nodes = {n["id"]: n for n in spec["activity_graph"]}
    expected = nodes["find-sum"]["response"]["expected"]
    out = tools.submit_attempt(spec, "find-sum", expected)
    assert out == {"correct": True, "evidence": "independent"}


def test_submit_attempt_wrong_assisted_with_hint(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    spec = _make_ten_spec()
    nodes = {n["id"]: n for n in spec["activity_graph"]}
    assistance = nodes["find-sum"]["assistance"]
    out = tools.submit_attempt(spec, "find-sum", "999")
    assert out["correct"] is False
    assert out["evidence"] == "assisted"
    assert out["hint"] == assistance[0]
    # 多次答错 → 取提示阶梯末项（示范出口），不越界
    out2 = tools.submit_attempt(spec, "find-sum", "999", wrong_before=99)
    assert out2["hint"] == assistance[-1]


def test_submit_attempt_no_programmatic_answer(monkeypatch) -> None:
    _disable_llm(monkeypatch)
    spec = _make_ten_spec()
    # 把某节点 expected 置空（模拟无程序化答案步骤）
    nodes = {n["id"]: n for n in spec["activity_graph"]}
    nodes["find-sum"]["response"]["expected"] = None
    out = tools.submit_attempt(spec, "find-sum", "5")
    assert out["error"] == "no_programmatic_answer"


def test_submit_attempt_node_not_found() -> None:
    spec = {
        "schema_version": "2.0",
        "lesson_id": "x",
        "activity_graph": [{"id": "n1", "type": "observe", "narration": "hi"}],
    }
    out = tools.submit_attempt(spec, "ghost", "1")
    assert out["error"] == "node_not_found"
