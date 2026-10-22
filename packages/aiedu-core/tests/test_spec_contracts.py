"""LessonSpec v2 契约测试：跨领域样例、JSON Schema、语义校验器、answer-filtered 投影。

filtered 投影断言对应 AGENTS 硬约束 1：未解锁节点的 response.expected 必须为 None。
"""

import json
from pathlib import Path

import jsonschema
import pytest

from aiedu_core.models.filtering import filtered_spec, filtered_spec_from_model
from aiedu_core.models.lesson_v2 import LessonSpecV2
from aiedu_core.models.semantics import validate_activity_graph
from aiedu_core.strategies import make_ten

CASES_DIR = Path(__file__).parent / "fixtures" / "cases"
SCHEMAS_DIR = Path(__file__).parent / "fixtures" / "schemas"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "case_file",
    sorted(p.name for p in CASES_DIR.glob("*.json")),
)
def test_v2_cases_load_and_validate(case_file: str) -> None:
    spec = LessonSpecV2.model_validate(_load(CASES_DIR / case_file))
    assert validate_activity_graph(spec) == [], case_file


def test_v2_json_schema_validates_cases() -> None:
    schema = _load(SCHEMAS_DIR / "lesson-spec.v2.schema.json")
    for case_file in sorted(CASES_DIR.glob("*.json")):
        data = _load(CASES_DIR / case_file)
        jsonschema.validate(data, schema)


def _minimal_spec(**overrides) -> dict:
    spec = _load(CASES_DIR / "arithmetic-make-ten.json")
    spec.update(overrides)
    return spec


def test_semantics_unreachable_node() -> None:
    spec = _minimal_spec()
    spec["activity_graph"].append(
        {"id": "orphan", "type": "observe", "narration": "不可达"}
    )
    errors = validate_activity_graph(LessonSpecV2.model_validate(spec))
    assert any("orphan: unreachable" in e for e in errors)


def test_semantics_unknown_action_ref() -> None:
    spec = _minimal_spec()
    spec["activity_graph"][1]["on_correct"] = ["arithmetic.does_not_exist"]
    errors = validate_activity_graph(LessonSpecV2.model_validate(spec))
    assert any("unknown action" in e for e in errors)


def test_semantics_predict_requires_gate() -> None:
    spec = _minimal_spec()
    spec["activity_graph"][1]["gate"] = {"mode": "learner_continue"}
    errors = validate_activity_graph(LessonSpecV2.model_validate(spec))
    assert any("require_attempt" in e for e in errors)


def test_semantics_replay_needs_attempt() -> None:
    """有完整解法/评价时，课程级必须存在至少一个 require_attempt 交互。"""
    spec = _minimal_spec()
    spec["activity_graph"] = [
        {"id": "n1", "type": "observe", "narration": "演示完整解法"},
        {"id": "n2", "type": "reflect", "prompt": "回顾一下", "next_ids": ["__end__"]},
    ]
    errors = validate_activity_graph(LessonSpecV2.model_validate(spec))
    assert any("先想后看" in e or "require_attempt" in e for e in errors)


# ---------------------------------------------------------------------------
# answer-filtered 投影（AGENTS 硬约束 1：未解锁节点不得含答案字段）
# ---------------------------------------------------------------------------

def _make_ten_dict() -> dict:
    return make_ten.build({"a": 16, "b": 8, "k": 2}).model_dump(mode="json")


def test_filtered_projection_hides_all_unlocked_answers() -> None:
    """未解锁任何步骤时：predict 节点 expected/correct_index 为 None，
    observe narration 与 verification claims.statement（含答案）不下发。"""
    filtered = filtered_spec(_make_ten_dict(), unlocked_ids=set())
    for node in filtered["activity_graph"]:
        if node["type"] in ("predict", "construct", "manipulate"):
            assert node["response"]["expected"] is None, node["id"]
            assert node["response"].get("correct_index") is None, node["id"]
            assert node.get("locked") is True, node["id"]
        if node["type"] == "observe":
            assert node["narration"] == "", node["id"]
            assert node.get("locked") is True, node["id"]
    for claim in filtered["verification"]["claims"]:
        assert claim["statement"] == ""
    assert "replay" not in filtered


def test_filtered_projection_reveals_only_unlocked() -> None:
    """解锁 find-complement/find-source 后：已解锁节点保留 expected，
    未解锁节点（find-sum/transfer-practice）仍为 None。"""
    filtered = filtered_spec(_make_ten_dict(), unlocked_ids={"find-complement", "find-source"})
    nodes = {n["id"]: n for n in filtered["activity_graph"]}
    assert nodes["find-complement"]["response"]["expected"] == "2"
    assert nodes["find-source"]["response"]["expected"] == "2"
    assert nodes["find-sum"]["response"]["expected"] is None
    assert nodes["transfer-practice"]["response"]["expected"] is None


def test_filtered_projection_from_model() -> None:
    """LessonSpecV2 → dict 投影与 dict 入口行为一致。"""
    spec = make_ten.build({"a": 16, "b": 8, "k": 2})
    filtered = filtered_spec_from_model(spec, unlocked_ids=set())
    for node in filtered["activity_graph"]:
        if node["type"] == "predict":
            assert node["response"]["expected"] is None
