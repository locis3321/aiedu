"""LLM 供应商路由：按 parse/plan/review 三类职责路由。

R2 §3：模型配置按职责路由，记录 provider、model、参数、prompt_version 与预算；
切换供应商不改变领域数据结构。密钥优先取管理端配置（加密入库，解密后使用），
未配置时回退环境变量；密钥不硬编码、不写日志。
"""

from dataclasses import dataclass

from agentscope.credential import OpenAICredential
from agentscope.model import ChatModelBase, OpenAIChatModel
from pydantic import SecretStr

from app.core.config import get_settings

ROLES = ("parse", "plan", "review")


@dataclass(frozen=True)
class ModelRoute:
    """一次职责路由的记录。"""

    role: str
    provider: str
    model: str
    prompt_version: str
    budget: str | None = None


def _db_config(role: str) -> dict | None:
    """按角色读取管理端模型配置（enabled）；无行返回 None。

    DB 不可达（如单元测试无真实库）时回退环境变量——与 runtime_config 同策略。
    """
    from app.admin_api.models import ModelConfig
    from app.storage.db import create_session_factory

    try:
        factory = create_session_factory()
        with factory() as session:
            row = (
                session.query(ModelConfig)
                .filter_by(role=role, enabled=True)
                .first()
            )
            if row is None or not row.api_key_enc:
                return None
            return {
                "model": row.model,
                "api_key_enc": row.api_key_enc,
                "params": row.params_json or {},
            }
    except Exception:  # noqa: BLE001 —— DB 不可达：回退环境变量配置
        return None


class ModelRouter:
    """按职责提供 ChatModel；未配置 LLM 时 get() 返回 None（显式能力缺口）。"""

    def __init__(self, settings=None) -> None:
        self.settings = settings or get_settings()
        self._models: dict[str, ChatModelBase] = {}
        self._routes: dict[str, ModelRoute] = {}

    def _build(self, role: str) -> ChatModelBase | None:
        s = self.settings
        cfg = _db_config(role)
        if cfg is not None:
            # 管理端配置优先：密钥解密失败显式抛错（SECRET_KEY 变更不静默回退）
            from app.core.crypto import decrypt_secret

            api_key = decrypt_secret(cfg["api_key_enc"])
            params = cfg["params"]
            base_url = params.get("base_url") or s.llm_base_url_normalized
            parameters = None
            if params.get("temperature") is not None:
                parameters = OpenAIChatModel.Parameters(
                    temperature=float(params["temperature"])
                )
            client_kwargs = None
            if params.get("timeout") is not None:
                client_kwargs = {"timeout": float(params["timeout"])}
            model: ChatModelBase = OpenAIChatModel(
                credential=OpenAICredential(
                    api_key=SecretStr(api_key),
                    base_url=base_url,
                ),
                model=cfg["model"],
                stream=False,
                parameters=parameters,
                client_kwargs=client_kwargs,
            )
            self._routes[role] = ModelRoute(
                role=role,
                provider="admin_config",
                model=cfg["model"],
                prompt_version="v1",
            )
        elif s.llm_configured:
            model = OpenAIChatModel(
                credential=OpenAICredential(
                    api_key=s.llm_api_key,
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
        else:
            return None
        self._models[role] = model
        return model

    def get(self, role: str) -> ChatModelBase | None:
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
