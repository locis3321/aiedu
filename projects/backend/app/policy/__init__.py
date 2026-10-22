"""全局教学政策模块：内置通用规范与程序化门禁。"""

from app.policy.teaching_policy import (
    GLOBAL_TEACHING_POLICY,
    check_teaching_policy,
)

__all__ = ["GLOBAL_TEACHING_POLICY", "check_teaching_policy"]
