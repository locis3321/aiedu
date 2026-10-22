"""LLM 配置：全部从环境变量读取，不硬编码任何凭据。

开源内核不依赖 pydantic-settings（避免新增依赖）：LLM 为可选路径，
未配置时相关能力显式不可用（router.get 返回 None → capability gap）。
"""

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    llm_base_url: str | None = Field(
        default_factory=lambda: os.environ.get("LLM_BASE_URL")
    )
    llm_api_key: str | None = Field(
        default_factory=lambda: os.environ.get("LLM_API_KEY")
    )
    llm_model_name: str | None = Field(
        default_factory=lambda: os.environ.get("LLM_MODEL_NAME")
    )

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model_name)

    @property
    def llm_base_url_normalized(self) -> str | None:
        """规范化 OpenAI 兼容 base_url：确保带 /v1 路径。

        内网兼容服务（如 one-api/new-api/vLLM）通常暴露 /v1/chat/completions；
        若只配置了服务根地址（如 http://host:port），请求会打到 Web UI 并返回
        HTML，SDK 解析成 str 导致 'str' object has no attribute 'choices'。
        """
        if not self.llm_base_url:
            return None
        url = self.llm_base_url.rstrip("/")
        if url.endswith("/v1"):
            return url
        return f"{url}/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
