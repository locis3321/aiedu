"""意图识别模块：生成链路第一步。

用户输入第一时间识别为结构化 TeachingIntent，再决定是否检索 Teaching Skill、
使用哪种教学模式与呈现风格。禁止把 skill 检索或策略匹配放在本阶段之前。
"""

from app.intent.analyzer import analyze_intent
from app.intent.contract import (
    AgeBand,
    GoalKind,
    InputKind,
    SubjectDomain,
    TeachingIntent,
)

__all__ = [
    "AgeBand",
    "GoalKind",
    "InputKind",
    "SubjectDomain",
    "TeachingIntent",
    "analyze_intent",
]
