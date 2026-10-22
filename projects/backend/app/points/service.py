"""积分与成长业务逻辑：规则版本化、幂等发放、账本查询、兑换预留。

硬约束（AGENTS.md 护栏 + 规格 v2 §2 R7'）：
- 发放幂等键 = 纯完成证据 ID；规则版本仅作流水属性，改版不追溯改写历史流水；
- 流水是业务事实只增不改；余额由流水推导，缺失显式失败，不用 NULL=0 兜底；
- 规则是配置：无启用规则时显式失败，不自动挑选默认值；
- 兑换目录 P2 随商城立项，首版仅展示+明细（显式未接入，不伪造成功）。
"""

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.learning.models import EvidenceRecord
from app.points.models import LedgerEntry, RewardRule

REWARD_EVENT = "reward"
LEVEL_POINTS_KEY = {
    "independent": "points_independent",
    "assisted": "points_assisted",
    "demonstrated": "points_demonstrated",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


# ---------------------------------------------------------------- 规则（配置）

def create_rule_version(
    session: Session,
    *,
    event_type: str,
    points_independent: int,
    points_assisted: int,
    points_demonstrated: int,
    daily_cap: int | None = None,
    per_event_cap: int | None = None,
    enabled: bool = True,
) -> RewardRule:
    """新建规则版本（version 递增）；历史版本保留只读（规则改版不追改流水）。"""
    latest = (
        session.query(func.max(RewardRule.version))
        .filter_by(event_type=event_type)
        .scalar()
        or 0
    )
    rule = RewardRule(
        version=latest + 1,
        event_type=event_type,
        points_independent=points_independent,
        points_assisted=points_assisted,
        points_demonstrated=points_demonstrated,
        daily_cap=daily_cap,
        per_event_cap=per_event_cap,
        enabled=enabled,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def get_active_rule(session: Session, event_type: str) -> RewardRule | None:
    """当前启用规则：该事件最新 enabled 版本。"""
    return (
        session.query(RewardRule)
        .filter_by(event_type=event_type, enabled=True)
        .order_by(RewardRule.version.desc())
        .first()
    )


def list_rules(session: Session, event_type: str | None = None) -> list[dict]:
    q = session.query(RewardRule).order_by(RewardRule.event_type, RewardRule.version)
    if event_type:
        q = q.filter_by(event_type=event_type)
    return [
        {
            "id": r.id,
            "version": r.version,
            "event_type": r.event_type,
            "points": {
                "independent": r.points_independent,
                "assisted": r.points_assisted,
                "demonstrated": r.points_demonstrated,
            },
            "daily_cap": r.daily_cap,
            "per_event_cap": r.per_event_cap,
            "enabled": r.enabled,
        }
        for r in q.all()
    ]


# ---------------------------------------------------------------- 发放（幂等）

def grant_reward(session: Session, child_id: str, evidence_id: str) -> dict:
    """按完成证据发放成长星；重复请求返回首次结果（R7'）。"""
    evidence = session.get(EvidenceRecord, evidence_id)
    if evidence is None or evidence.child_id != child_id:
        raise ApiError(404, "EVIDENCE_NOT_FOUND", "完成证据不存在或不属于该孩子")

    existing = (
        session.query(LedgerEntry)
        .filter_by(evidence_id=evidence_id, event_type=REWARD_EVENT)
        .first()
    )
    if existing is not None:
        # 幂等：重复领取不重复发放，返回首次结果
        return {"entry": _entry_dict(existing), "idempotent": True}

    rule = get_active_rule(session, REWARD_EVENT)
    if rule is None:
        raise ApiError(
            422, "RULE_NOT_CONFIGURED", "无启用中的成长星发放规则，不发放"
        )
    if evidence.level not in LEVEL_POINTS_KEY:
        raise ApiError(
            422,
            "LEVEL_NOT_REWARDED",
            f"证据级别 {evidence.level} 不发放成长星",
            {"rewarded_levels": sorted(LEVEL_POINTS_KEY)},
        )

    now = _utcnow()
    if rule.daily_cap is not None:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = sum(
            1
            for e in session.query(LedgerEntry)
            .filter_by(child_id=child_id, event_type=REWARD_EVENT)
            .all()
            if _aware(e.created_at) is not None and _aware(e.created_at) >= day_start
        )
        if today_count >= rule.daily_cap:
            raise ApiError(
                429,
                "REACHED_DAILY_CAP",
                "今日成长星发放已达上限",
                {"daily_cap": rule.daily_cap},
            )
    if rule.per_event_cap is not None:
        total_count = (
            session.query(func.count(LedgerEntry.id))
            .filter_by(child_id=child_id, event_type=REWARD_EVENT)
            .scalar()
            or 0
        )
        if total_count >= rule.per_event_cap:
            raise ApiError(
                429,
                "REACHED_EVENT_CAP",
                "该事件成长星发放已达累计上限",
                {"per_event_cap": rule.per_event_cap},
            )

    points = getattr(rule, LEVEL_POINTS_KEY[evidence.level])
    balance_before = _balance(session, child_id)
    entry = LedgerEntry(
        child_id=child_id,
        evidence_id=evidence_id,
        event_type=REWARD_EVENT,
        rule_version=rule.version,
        points=points,
        balance_after=balance_before + points,
        reason=f"完成学习：{evidence.level}",
    )
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:
        # 并发重复领取：唯一约束 (evidence_id, event_type) 兜底，回滚后返回首次结果（R7'）
        session.rollback()
        existing = (
            session.query(LedgerEntry)
            .filter_by(evidence_id=evidence_id, event_type=REWARD_EVENT)
            .first()
        )
        if existing is not None:
            return {"entry": _entry_dict(existing), "idempotent": True}
        raise
    session.refresh(entry)
    return {"entry": _entry_dict(entry), "idempotent": False}


def _balance(session: Session, child_id: str) -> int:
    """余额由流水推导；无流水时显式返回 0（首笔前余额为 0，非 NULL 兜底）。"""
    total = (
        session.query(func.sum(LedgerEntry.points))
        .filter_by(child_id=child_id)
        .scalar()
    )
    return int(total or 0)


def _entry_dict(e: LedgerEntry) -> dict:
    return {
        "id": e.id,
        "child_id": e.child_id,
        "evidence_id": e.evidence_id,
        "event_type": e.event_type,
        "rule_version": e.rule_version,
        "points": e.points,
        "balance_after": e.balance_after,
        "reason": e.reason,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ---------------------------------------------------------------- 查询与兑换

def get_ledger(session: Session, child_id: str) -> dict:
    entries = (
        session.query(LedgerEntry)
        .filter_by(child_id=child_id)
        .order_by(LedgerEntry.created_at.desc())
        .all()
    )
    return {
        "child_id": child_id,
        "balance": _balance(session, child_id),
        "entries": [_entry_dict(e) for e in entries],
    }


def redeem_reserved() -> dict:
    """兑换目录 P2 随商城立项；首版仅展示成长星与明细（显式未接入）。"""
    raise ApiError(
        503,
        "REDEEM_NOT_AVAILABLE",
        "兑换目录随商城立项（P2），当前仅展示成长星与明细",
    )
