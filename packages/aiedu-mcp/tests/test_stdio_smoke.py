"""D5–D6 测试：stdio 传输协议层冒烟（子进程 server + MCP 官方 client）。"""

import sys
from pathlib import Path

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_ARGS = ["-m", "aiedu_mcp.server", "--transport", "stdio"]


@pytest.mark.asyncio
async def test_stdio_transport_tool_call() -> None:
    """子进程启动 stdio server，走完整 MCP 协议调用两个 tool。"""
    params = StdioServerParameters(
        command=sys.executable,
        args=SERVER_ARGS,
        cwd=str(REPO_ROOT / "packages" / "aiedu-mcp"),
        env=None,  # 继承宿主 env：16-9/16+8 为模板覆盖题型，不依赖 LLM
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.server_info.name == "aiedu-mcp"

            gen = await session.call_tool("generate_lesson", {"question": "16-9"})
            import json

            gen_payload = json.loads(gen.content[0].text)
            assert gen_payload["lesson_id"] == "borrow-ten-16-minus-9"
            assert gen_payload["verification"]["verified"] is True
            spec = gen_payload["spec"]
            got = await session.call_tool(
                "get_lesson",
                {"spec": spec, "reveal": "filtered", "unlocked_ids": []},
            )
            got_payload = json.loads(got.content[0].text)
            for node in got_payload["spec"]["activity_graph"]:
                if node["type"] == "predict":
                    assert node["response"]["expected"] is None, node["id"]

            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {
                "verify_math",
                "generate_lesson",
                "get_lesson",
                "submit_attempt",
                "render_lesson",
            }
