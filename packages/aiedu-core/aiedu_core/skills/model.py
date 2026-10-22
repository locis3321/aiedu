"""Teaching Skill 元数据模型。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TeachingSkill:
    """一个 Claude-style skill 包（只读教学材料，不执行其中脚本）。"""

    name: str
    description: str
    path: str
    content: str
    examples: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        """供 planner 使用的简短上下文（不包含完整正文）。"""
        return f"skill:{self.name} — {self.description}"
