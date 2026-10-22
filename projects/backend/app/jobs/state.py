"""Job 状态机：常量、合法迁移与校验。

后台生成状态机：QUEUED → RUNNING → VALIDATING → SUCCEEDED；
允许 RETRYING / FAILED / CANCELED。
"""

from app.storage.models import ALLOWED_JOB_STATUSES, JOB_TRANSITIONS

__all__ = ["ALLOWED_JOB_STATUSES", "JOB_TRANSITIONS", "validate_transition"]


def validate_transition(current: str, next_status: str) -> bool:
    """返回迁移是否合法；终态（SUCCEEDED/FAILED/CANCELED）不可再迁移。"""
    if current not in ALLOWED_JOB_STATUSES or next_status not in ALLOWED_JOB_STATUSES:
        return False
    if current in {"SUCCEEDED", "FAILED", "CANCELED"}:
        return False
    return next_status in JOB_TRANSITIONS.get(current, set())
