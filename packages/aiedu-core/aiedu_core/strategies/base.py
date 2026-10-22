"""策略模板契约：适用条件、参数提取、GuidedStep序列、变式生成器、错误模式。

AGENTS.md 护栏2：常见计算策略必须走策略模板库——分类 + 参数填充，
不允许 LLM 自由创作这类题型的讲解流程。
"""

from collections.abc import Callable
from dataclasses import dataclass

from aiedu_core.models.lesson_v2 import LessonSpecV2


@dataclass(frozen=True)
class GuidedStepTemplate:
    """引导步骤模板：提问话术占位符 + 回答形式 + 门槛 + state_delta action。"""

    id: str
    prompt_template: str
    response_kind: str = "number"
    gate_mode: str = "require_attempt"
    assistance: tuple[str, ...] = ()
    on_correct_actions: tuple[str, ...] = ()
    distractors_from: tuple[str, ...] = ()


@dataclass(frozen=True)
class Misconception:
    """常见错误模式：供干扰项生成与错题讲评。"""

    id: str
    description: str
    distractor_hint: str


@dataclass(frozen=True)
class StrategyTemplate:
    """策略模板：参数由程序计算，不由 LLM 猜。"""

    id: str
    version: str
    applies_to: Callable[[str], bool]
    extract_params: Callable[[str], dict]
    guided_steps: tuple[GuidedStepTemplate, ...]
    variants: Callable[[dict], list[dict]]
    misconceptions: tuple[Misconception, ...]
    build_fn: Callable[[dict], LessonSpecV2] | None = None

    def build(self, params: dict) -> LessonSpecV2:
        """按参数填充产出 LessonSpec v2。"""
        if self.build_fn is None:
            raise NotImplementedError(f"{self.id} has no build_fn")
        return self.build_fn(params)


@dataclass(frozen=True)
class StrategyMatch:
    """分类命中结果：模板 + 已提取参数。"""

    template_id: str
    version: str
    params: dict


class StrategyRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, StrategyTemplate] = {}

    def register(self, template: StrategyTemplate) -> None:
        if template.id in self._templates:
            raise ValueError(f"strategy already registered: {template.id}")
        self._templates[template.id] = template

    def get(self, template_id: str) -> StrategyTemplate | None:
        return self._templates.get(template_id)

    def match(self, problem_text: str) -> StrategyMatch | None:
        """分类命中：遍历已注册模板的适用条件谓词。"""
        for template in self._templates.values():
            if template.applies_to(problem_text):
                return StrategyMatch(
                    template_id=template.id,
                    version=template.version,
                    params=template.extract_params(problem_text),
                )
        return None

    def ids(self) -> list[str]:
        return sorted(self._templates)


registry = StrategyRegistry()
