"""T2 契约测试：LessonSpec v0.1/v2 模型、JSON Schema、语义校验器。"""

import json
from pathlib import Path

import jsonschema
import pytest

from app.models.lesson_v01 import LessonSpecV01
from app.models.lesson_v2 import LessonSpecV2
from app.models.semantics import validate_activity_graph

CASES_DIR = Path(__file__).parent / "fixtures" / "cases"
V01_DIR = Path(__file__).parent / "fixtures" / "v01"
SCHEMAS_DIR = Path(__file__).parent.parent / "app" / "models" / "schemas"
PROTOTYPE_LESSONS = Path(r"D:\aiedu\lessons")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# LessonSpec v2：跨领域样例
# ---------------------------------------------------------------------------

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
        data = _load(case_file)
        jsonschema.validate(data, schema)


# ---------------------------------------------------------------------------
# LessonSpec v0.1：兼容层
# ---------------------------------------------------------------------------

def test_v01_sample_loads() -> None:
    data = _load(V01_DIR / "baskets-ratio-43.json")
    spec = LessonSpecV01.model_validate(data)
    assert spec.version == "0.1"
    assert spec.solution.verified is True


def test_v01_prototype_lessons_load() -> None:
    """原型 14 节课程样例必须能被 v0.1 模型加载（路径存在时验证）。"""
    if not PROTOTYPE_LESSONS.exists():
        pytest.skip("prototype lessons dir not present")
    specs = sorted(PROTOTYPE_LESSONS.glob("*/lesson-spec.json"))
    assert specs, "no prototype lessons found"
    for p in specs:
        LessonSpecV01.model_validate(_load(p))


# ---------------------------------------------------------------------------
# 语义校验器负例
# ---------------------------------------------------------------------------

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
    # 把唯一的 predict 节点换成无门槛的 observe
    spec["activity_graph"] = [
        {"id": "n1", "type": "observe", "narration": "演示完整解法"},
        {"id": "n2", "type": "reflect", "prompt": "回顾一下", "next_ids": ["__end__"]},
    ]
    errors = validate_activity_graph(LessonSpecV2.model_validate(spec))
    assert any("先想后看" in e or "require_attempt" in e for e in errors)
