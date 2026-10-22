"""aiedu-mcp：内核能力（aiedu-core）的 MCP 封装。

工具面冻结为 4 个（render_lesson 依赖 D7–D8 player，不在本期）。
判定全部由内核完成：verified 仅由 SymPy 产生，filtered 投影即硬约束 1。
"""

from aiedu_mcp import server
from aiedu_mcp import tools

__all__ = ["tools", "server"]
