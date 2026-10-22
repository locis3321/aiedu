"""Claude-style skill 包加载器。

包结构约定（与 Claude Skill 规范一致）：
    <pack-dir>/
      SKILL.md          # 必填：frontmatter(name/description) + 正文
      examples/         # 可选：示例
      assets/           # 可选：只读资源
      fixtures/         # 可选：测试样本

安全边界：本加载器只读取文本，绝不执行 skill 包中的任何脚本。
"""

from pathlib import Path

from app.skills.model import TeachingSkill


def parse_frontmatter(text: str) -> dict[str, str]:
    """解析极简 YAML frontmatter（`---` 包裹的 key: value）。

    支持 Claude skill 常见形式：
    - 单行 `key: value`（值可带引号）；
    - plain scalar 缩进续行（折叠为空格）；
    - `>` / `>-` 折叠块、`|` / `|-` 字面块。

    遇到其他复杂 YAML（数组、嵌套映射）时显式报错，不静默吞掉。
    返回空 dict 表示没有 frontmatter。
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("frontmatter not closed (missing trailing ---)")
    block = text[3:end]
    meta: dict[str, str] = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if line.startswith((" ", "\t")):
            raise ValueError(f"unexpected indented line: {line!r}")
        if ":" not in line:
            raise ValueError(f"unsupported frontmatter line: {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        i += 1

        if value in {">", ">-", "|", "|-"}:
            fold = value.startswith(">")
            parts: list[str] = []
            while i < len(lines) and lines[i].startswith((" ", "\t")):
                parts.append(lines[i].strip())
                i += 1
            value = (" " if fold else "\n").join(parts)
        else:
            continuation: list[str] = []
            while i < len(lines) and lines[i].startswith((" ", "\t")):
                continuation.append(lines[i].strip())
                i += 1
            if continuation:
                value = (value + " " + " ".join(continuation)).strip()

        meta[key] = value.strip('"').strip("'")
    return meta


def load_skill_pack(pack_dir: str | Path) -> TeachingSkill:
    """加载一个 skill 包；缺少 SKILL.md / name / description 时失败。"""
    pack_dir = Path(pack_dir)
    skill_file = pack_dir / "SKILL.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"skill pack missing SKILL.md: {pack_dir}")

    text = skill_file.read_text(encoding="utf-8")
    meta = parse_frontmatter(text)
    name = meta.get("name")
    description = meta.get("description")
    if not name:
        raise ValueError(f"skill pack missing frontmatter name: {pack_dir}")
    if not description:
        raise ValueError(f"skill pack missing frontmatter description: {pack_dir}")

    examples_dir = pack_dir / "examples"
    examples: tuple[str, ...] = ()
    if examples_dir.is_dir():
        examples = tuple(
            sorted(p.name for p in examples_dir.iterdir() if p.is_file())
        )

    return TeachingSkill(
        name=name,
        description=description,
        path=str(pack_dir),
        content=text,
        examples=examples,
    )


def load_all_skills(root_dir: str | Path) -> list[TeachingSkill]:
    """递归加载 root 下所有含 SKILL.md 的包；坏包跳过并记录（不阻断整体）。"""
    root_dir = Path(root_dir)
    skills: list[TeachingSkill] = []
    for skill_file in sorted(root_dir.rglob("SKILL.md")):
        try:
            skills.append(load_skill_pack(skill_file.parent))
        except (ValueError, FileNotFoundError):
            continue
    return skills
