"""领域插件与表示适配器契约 + 注册表。

R2 §4.1：DomainPlugin 声明模型 schema、操作 schema、支持的表示、状态验证器、
主张验证器以及评价能力；RepresentationAdapter 把领域模型映射为符号、二维、三维、
数据图表或证明步骤。渲染器不能反向定义课程范围。
"""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class DomainPlugin(Protocol):
    """领域能力插件：以已审核、版本化代码接入，不要求 LLM 每次创建插件。"""

    domain: str
    plugin_version: str
    model_schema: type[BaseModel]
    operation_schema: type[BaseModel]
    supported_representations: tuple[str, ...]

    def validate_state(self, state: dict) -> list[str]:
        """返回状态不变量违规列表；空列表表示合法。"""
        ...

    def validate_claim(self, claim_id: str, state: dict) -> str:
        """返回 verified / refuted / inconclusive / requires_review。"""
        ...

    def evaluate(self, response_kind: str, answer, state: dict) -> dict:
        """按回答形式评价：首次正确/提示后正确/示范后完成分别呈现。"""
        ...


@runtime_checkable
class RepresentationAdapter(Protocol):
    """把领域模型映射为一种表示；渲染器不得反向定义课程范围。"""

    kind: str

    def build(self, model_state: dict, viewport: dict, renderer_profile: dict) -> dict:
        """构建场景图/表示描述。"""
        ...

    def layout_invariants(self) -> list[str]:
        """本表示适用的布局不变量检查项名称（供 validate 复用）。"""
        ...


class DomainRegistry:
    """领域插件注册表：按 domain 名注册与查询。"""

    def __init__(self) -> None:
        self._plugins: dict[str, DomainPlugin] = {}
        self._adapters: dict[str, RepresentationAdapter] = {}

    def register_plugin(self, plugin: DomainPlugin) -> None:
        if plugin.domain in self._plugins:
            raise ValueError(f"domain already registered: {plugin.domain}")
        self._plugins[plugin.domain] = plugin

    def get_plugin(self, domain: str) -> DomainPlugin | None:
        return self._plugins.get(domain)

    def register_adapter(self, adapter: RepresentationAdapter) -> None:
        if adapter.kind in self._adapters:
            raise ValueError(f"adapter already registered: {adapter.kind}")
        self._adapters[adapter.kind] = adapter

    def get_adapter(self, kind: str) -> RepresentationAdapter | None:
        return self._adapters.get(kind)

    def domains(self) -> list[str]:
        return sorted(self._plugins)

    def capabilities(self) -> list[str]:
        """已实现、可组合的能力清单；未注册的领域显式标记为缺口。"""
        return [f"{d}@{self._plugins[d].plugin_version}" for d in self.domains()]


registry = DomainRegistry()
