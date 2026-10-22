"""OpenAI 兼容 Chat 客户端（httpx 直连，零 agentscope 依赖）。

为什么存在（决策 B，2026-10-21）：agentscope 2.0.9 硬性要求 `mcp<2.0.0`，与
fastmcp 4.1.3（需 `mcp>=2.0.0`）同环境不可共存——导致 MCP server 无法携带 LLM
路径。改用 httpx 直连 OpenAI 兼容接口（`/chat/completions`）后：
- LLM 与 MCP 可共存于同一环境（演示档/托管档可开启 LLM 自由设计）；
- 依赖面收缩：agentscope（含大量第三方 SDK 传递依赖）→ 仅 `httpx>=0.27`（可选 extra）；
- 对外协议不变：`model(msgs, **kwargs)` → `{content:[TextBlock], usage}`，
  pipeline._call_model 与结构化输出（json_schema strict）行为保持不变。

说明：本模块模拟 AgentScope 的极小接口面（Message/TextBlock/ChatResponse），
只为让下游 `_call_model` 的防御逻辑零改动；LLM 仍只讲解、不判定——
`verified=true` 依旧只可能来自 SymPy 核验。
"""

import json
from dataclasses import dataclass, field

import httpx


@dataclass
class TextBlock:
    text: str


@dataclass
class Message:
    """最小消息结构：role + 文本内容（替代 agentscope.message.Msg）。"""

    role: str
    content: str


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ChatResponse:
    content: list[TextBlock] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


class CompatChatModel:
    """OpenAI 兼容聊天模型：`await model(msgs, **kwargs)` → ChatResponse。

    - msgs：aiedu_core.llm_client.Message 列表（role/text）；
    - kwargs 透传为请求体字段（如 response_format 的 json_schema strict）；
    - 供应商返回异常统一抛 llm.ChatCallError（由 _call_model 包装为 PipelineError）。
    """

    def __init__(self, model: str, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def __call__(self, msgs, **kwargs) -> ChatResponse:
        body = {
            "model": self.model,
            "messages": [
                {"role": m.role, "content": m.content if isinstance(m, Message) else str(m)}
                for m in msgs
            ],
            **kwargs,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions", json=body, headers=headers
            )
            if resp.status_code != 200:
                raise ChatCallError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            try:
                data = resp.json()
            except ValueError as exc:
                raise ChatCallError(f"响应不是 JSON：{resp.text[:200]!r}") from exc
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ChatCallError(f"响应结构异常：{str(data)[:200]}") from exc
        usage = data.get("usage") or {}
        return ChatResponse(
            content=[TextBlock(text=text)],
            usage=Usage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
        )


class ChatCallError(RuntimeError):
    """供应商层失败（HTTP/结构）；由上游包装为 PipelineError，不泄露密钥。"""


def messages_from_text(text: str, role: str = "user") -> list[Message]:
    return [Message(role=role, content=text)]
