"""LLM 客户端（httpx 直连）测试：解析/透传/错误包装（全部离线，MockTransport）。"""

import json

import httpx
import pytest

from aiedu_core.llm_client import ChatCallError, CompatChatModel, Message


def _model(handler):
    model = CompatChatModel(model="test-model", base_url="http://llm.test/v1", api_key="k")
    original = httpx.AsyncClient

    class _Patched(original):
        def __init__(self, *a, **kw):
            super().__init__(*a, transport=httpx.MockTransport(handler), **kw)

    return model, _Patched


async def test_completion_parsed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer k"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][0]["content"] == "只回复两个字：正常"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "正常"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    model, Patched = _model(handler)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(httpx, "AsyncClient", Patched)
        resp = await model([Message(role="user", content="只回复两个字：正常")])
        assert resp.content[0].text == "正常"
        assert resp.usage.input_tokens == 12
        assert resp.usage.output_tokens == 3


async def test_response_format_passthrough() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "response_format" in body
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    model, Patched = _model(handler)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(httpx, "AsyncClient", Patched)
        await model(
            [Message(role="user", content="x")],
            response_format={"type": "json_schema", "json_schema": {"strict": True}},
        )


async def test_http_error_wrapped() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    model, Patched = _model(handler)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(httpx, "AsyncClient", Patched)
        with pytest.raises(ChatCallError, match="HTTP 500"):
            await model([Message(role="user", content="x")])


async def test_malformed_response_wrapped() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"weird": True})

    model, Patched = _model(handler)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(httpx, "AsyncClient", Patched)
        with pytest.raises(ChatCallError, match="响应结构异常"):
            await model([Message(role="user", content="x")])


async def test_missing_extra_fails_explicitly(monkeypatch) -> None:
    """未装 httpx → _build 显式失败（不静默降级）。"""
    monkeypatch.setitem(__import__("sys").modules, "httpx", None)
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from aiedu_core.services.llm_router import ModelRouter
    from aiedu_core.config import Settings

    router = ModelRouter(
        settings=Settings(llm_base_url="http://x", llm_api_key="k", llm_model_name="m")
    )
    with pytest.raises(RuntimeError, match="httpx not installed"):
        router.get("plan")
