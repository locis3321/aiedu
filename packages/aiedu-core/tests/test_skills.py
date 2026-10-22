"""T3 测试：Claude-style Teaching Skill 加载与检索。"""

from pathlib import Path

import pytest

from aiedu_core.intent import analyze_intent
from aiedu_core.skills import SkillRetriever, load_all_skills, load_skill_pack
from aiedu_core.skills.loader import parse_frontmatter

SKILL_MD = """---
name: make-ten
description: Use when teaching students to simplify addition by decomposing one
  addend to compose the other to 10 while preserving the total.
---

# 凑十法

## 核心思想
通过拆分一个加数，把另一个加数补成 10。
"""

SKILL_MD_BLOCK = """---
name: make-ten
description: >-
  Use when teaching students to simplify addition by decomposing one addend
  to compose the other to 10 while preserving the total.
---

# 凑十法
"""


def _write_pack(root: Path, name: str = "make-ten") -> Path:
    pack = root / name
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (pack / "examples").mkdir()
    (pack / "examples" / "16-plus-8.md").write_text("# 示例", encoding="utf-8")
    return pack


def test_parse_frontmatter() -> None:
    meta = parse_frontmatter(SKILL_MD)
    assert meta["name"] == "make-ten"
    assert "simplify addition" in meta["description"]


def test_parse_frontmatter_block_scalar() -> None:
    """`>-` 折叠块：多行 description 折叠为空格连接。"""
    meta = parse_frontmatter(SKILL_MD_BLOCK)
    assert "simplify addition" in meta["description"]
    assert "preserving the total" in meta["description"]


def test_parse_frontmatter_missing() -> None:
    assert parse_frontmatter("# no frontmatter") == {}


def test_parse_frontmatter_unclosed_raises() -> None:
    with pytest.raises(ValueError, match="not closed"):
        parse_frontmatter("---\nname: x")


def test_load_skill_pack(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    skill = load_skill_pack(pack)
    assert skill.name == "make-ten"
    assert skill.examples == ("16-plus-8.md",)
    assert "核心思想" in skill.content


def test_load_skill_pack_missing_name_raises(tmp_path: Path) -> None:
    pack = tmp_path / "bad"
    pack.mkdir()
    (pack / "SKILL.md").write_text("# no frontmatter", encoding="utf-8")
    with pytest.raises(ValueError, match="missing frontmatter name"):
        load_skill_pack(pack)


def test_load_skill_pack_missing_skill_md_raises(tmp_path: Path) -> None:
    pack = tmp_path / "empty"
    pack.mkdir()
    with pytest.raises(FileNotFoundError, match="missing SKILL.md"):
        load_skill_pack(pack)


def test_load_all_skills_skips_bad_packs(tmp_path: Path) -> None:
    _write_pack(tmp_path, "make-ten")
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "SKILL.md").write_text("# no frontmatter", encoding="utf-8")
    skills = load_all_skills(tmp_path)
    assert [s.name for s in skills] == ["make-ten"]


def test_retriever_accepts_intent_not_raw_input(tmp_path: Path) -> None:
    """检索器只接受 TeachingIntent；原始字符串输入不是合法调用。"""
    _write_pack(tmp_path)
    skills = load_all_skills(tmp_path)
    retriever = SkillRetriever(skills)
    intent = analyze_intent({"kind": "problem", "content": "16+8"})
    hits = retriever.retrieve(intent)
    assert [s.name for s in hits] == ["make-ten"]


def test_retriever_no_query_returns_empty(tmp_path: Path) -> None:
    _write_pack(tmp_path)
    retriever = SkillRetriever(load_all_skills(tmp_path))
    intent = analyze_intent({"kind": "concept", "content": "什么是分数"})
    assert retriever.retrieve(intent) == []


# ---------------------------------------------------------------------------
# 真实 teaching-skills 包（T6：make-ten skill 迁移）
# ---------------------------------------------------------------------------

def test_real_make_ten_skill_pack_loads() -> None:
    """仓库内 teaching-skills/make-ten 包可被加载。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "teaching-skills"
    skills = load_all_skills(root)
    names = [s.name for s in skills]
    assert "make-ten" in names
    skill = next(s for s in skills if s.name == "make-ten")
    assert "核心思想" in skill.content
    assert skill.examples


def test_real_make_ten_skill_matches_intent() -> None:
    """16+8 意图能检索到 make-ten skill（正文中文匹配）。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "teaching-skills"
    retriever = SkillRetriever(load_all_skills(root))
    intent = analyze_intent({"kind": "problem", "content": "16+8"})
    hits = retriever.retrieve(intent)
    assert [s.name for s in hits] == ["make-ten"]


def test_real_borrow_ten_skill_matches_intent() -> None:
    """13-5 意图能检索到 borrow-ten skill（破十法/退位减法）。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "teaching-skills"
    retriever = SkillRetriever(load_all_skills(root))
    intent = analyze_intent({"kind": "problem", "content": "13-5"})
    hits = retriever.retrieve(intent)
    assert any(s.name == "borrow-ten" for s in hits)


def test_real_fraction_skill_matches_intent() -> None:
    """分数概念请求能检索到 fraction-equal-parts skill。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "teaching-skills"
    retriever = SkillRetriever(load_all_skills(root))
    intent = analyze_intent({"kind": "concept", "content": "理解分数的意义"})
    hits = retriever.retrieve(intent)
    assert any(s.name == "fraction-equal-parts" for s in hits)


def test_pipeline_records_skill_ref() -> None:
    """pipeline 生成 make-ten 课程时记录 skill_ref（兼容层 + skill 关联）。"""
    import asyncio

    from aiedu_core.pipeline.pipeline import run_pipeline

    spec = asyncio.run(run_pipeline({"kind": "problem", "content": "16+8"}))
    assert spec.teaching_design.skill_refs == ["make-ten"]
    assert spec.teaching_design.strategy_refs == ["make_ten@0.1.0"]


def test_pipeline_does_not_match_before_intent() -> None:
    """旧路线回归防护：pipeline 不再直接调用 strategy registry.match。"""
    import inspect

    from aiedu_core.pipeline import pipeline

    src = inspect.getsource(pipeline.run_pipeline)
    assert "registry.match" not in src
    assert "analyze_intent" in src
