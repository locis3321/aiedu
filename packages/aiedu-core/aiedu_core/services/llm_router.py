"""LLM 供应商路由（可选路径）：按 parse/plan/review 三类职责路由。

R2 §3：模型配置按职责路由，记录 provider、model、参数与 prompt_version；
切换供应商不改变领域数据结构。开源内核只从环境变量读取配置（不依赖管理端
DB/加密域），密钥不硬编码、不写日志。未配置 LLM env 时 get() 返回 None，
由上游显式报能力缺口。
"""

from dataclasses import dataclass

from aiedu_core.config import Settings, get_settings

ROLES = ("parse", "plan", "review")


@dataclass(frozen=True)
class ModelRoute:
    """一次职责路由的记录。"""

    role: str
    provider: str
    model: str
    prompt_version: str
    budget: str | None = None


class ModelRouter:
    """按职责提供 ChatModel；未配置 LLM 时 get() 返回 None（显式能力缺口）。"""

    def __init__(self, settings=None) -> None:
        self.settings = settings or get_settings()
        self._models: dict = {}
        self._routes: dict[str, ModelRoute] = {}

    def _build(self, role: str):
        s = self.settings
        if not s.llm_configured:
            return None
        try:
            from agentscope.credential import OpenAICredential
            from agentscope.model import OpenAIChatModel
        except ImportError as exc:  # [llm] extra 未安装：显式失败，不静默降级
            raise RuntimeError(
                "LLM configured but agentscope not installed "
                "(install aiedu-core[llm])"
            ) from exc
        from pydantic import SecretStr

        model = OpenAIChatModel(
            credential=OpenAICredential(
                api_key=SecretStr(s.llm_api_key),
                base_url=s.llm_base_url_normalized,
            ),
            model=s.llm_model_name or "",
            stream=False,
        )
        self._routes[role] = ModelRoute(
            role=role,
            provider="openai_compatible",
            model=s.llm_model_name or "",
            prompt_version="v1",
        )
        self._models[role] = model
        return model

    def get(self, role: str):
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        if role not in self._models:
            return self._build(role)
        return self._models[role]

    def route(self, role: str) -> ModelRoute | None:
        return self._routes.get(role)

    def routes(self) -> dict[str, ModelRoute]:
        return dict(self._routes)


def default_router() -> ModelRouter:
    return ModelRouter()
