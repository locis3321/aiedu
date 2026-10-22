"""能力画像业务逻辑：程序化聚合引擎（规格 v2 §10）。

硬约束：
- 画像是证据的聚合投影，不制造新事实；LLM 只解释不判定（R8）；
- 证据带枚举与 T3 全链路一致（independent/assisted/demonstrated/needs_review）；
- needs_review 不升级任何证据带，仅补充计数（R2'）；
- 无证据维度 = needs_review（"待观察"展示文案），不是 0 分或百分比；
- 聚合规则版本化：改版前留存快照，历史轨迹不追改；
- banned-phrase guard：禁止绝对化断言写入画像。
"""

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.learning.models import EvidenceRecord
from app.profile.models import (
    ProfileDimension,
    ProfileHistory,
    ProfileState,
)

# ---------------------------------------------------------------- 教研配置

AGGREGATION_RULE_VERSION = 1

DIMENSIONS = [
    {"code": "operations", "name": "运算"},
    {"code": "concept", "name": "概念理解"},
    {"code": "transfer", "name": "应用迁移"},
    {"code": "number_sense", "name": "数感"},
]

# evidence.kind → 归属维度（教研配置；改版=递增 AGGREGATION_RULE_VERSION）
EVIDENCE_TO_DIMENSIONS = {
    "gate_complete": ["operations", "concept"],
    "variant_correct": ["operations", "transfer"],
    "transfer_correct": ["transfer", "concept"],
    # abandoned（有尝试未完成）不归属任何维度，仅作为补充计数
}

LEVEL_RANK = {"needs_review": 0, "assisted": 1, "demonstrated": 2, "independent": 3}

BANNED_PHRASES = [
    "已掌握",
    "深度掌握",
    "完全掌握",
    "总是",
    "永远",
    "mastered",
    "always",
    "fully understood",
]


def assert_no_banned(text: str) -> None:
    """banned-phrase guard：绝对化断言运行时拦截并回喂（护栏2）。"""
    lowered = (text or "").lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in lowered:
            raise ApiError(
                422,
                "BANNED_PHRASE",
                f"输出包含绝对化断言：{phrase}，已拦截，不写入画像",
            )


# ---------------------------------------------------------------- 聚合引擎

def ensure_dimensions(session: Session) -> None:
    for dim in DIMENSIONS:
        if session.get(ProfileDimension, dim["code"]) is None:
            session.add(ProfileDimension(code=dim["code"], name=dim["name"]))
    session.commit()


def aggregate_child(session: Session, child_id: str) -> None:
    """按当前规则版本重算孩子×维度证据带（幂等；改版前先留存快照）。"""
    ensure_dimensions(session)

    latest_state = (
        session.query(ProfileState)
        .filter_by(child_id=child_id)
        .order_by(ProfileState.as_of_version.desc())
        .first()
    )
    if latest_state is not None and latest_state.as_of_version != AGGREGATION_RULE_VERSION:
        _snapshot(session, child_id, latest_state.as_of_version)

    evidence_rows = (
        session.query(EvidenceRecord).filter_by(child_id=child_id).all()
    )
    result: dict[str, dict] = {}
    for ev in evidence_rows:
        for dim_code in EVIDENCE_TO_DIMENSIONS.get(ev.kind, []):
            info = result.setdefault(
                dim_code,
                {"level": "needs_review", "count": 0, "nr": 0, "evidence_ids": []},
            )
            info["evidence_ids"].append(ev.id)
            if ev.level == "needs_review":
                info["nr"] += 1
                continue
            info["count"] += 1
            if LEVEL_RANK[ev.level] > LEVEL_RANK[info["level"]]:
                info["level"] = ev.level

    for dim in DIMENSIONS:
        info = result.get(
            dim["code"],
            {"level": "needs_review", "count": 0, "nr": 0, "evidence_ids": []},
        )
        row = (
            session.query(ProfileState)
            .filter_by(child_id=child_id, dimension_code=dim["code"])
            .first()
        )
        if row is None:
            row = ProfileState(child_id=child_id, dimension_code=dim["code"])
            session.add(row)
        row.level = info["level"]
        row.evidence_count = info["count"]
        row.needs_review_count = info["nr"]
        row.as_of_version = AGGREGATION_RULE_VERSION
        # L3→L2(evidence)→L1(trace) 证据链引用：可审计可回放
        row.detail_json = {
            "rule_version": AGGREGATION_RULE_VERSION,
            "evidence_ids": info["evidence_ids"],
        }
    session.commit()


def _snapshot(session: Session, child_id: str, version: int) -> None:
    """规则改版前留存画像快照（历史轨迹不追改）。"""
    rows = session.query(ProfileState).filter_by(child_id=child_id).all()
    snapshot_json = {
        "as_of_version": version,
        "dimensions": [
            {
                "code": r.dimension_code,
                "level": r.level,
                "evidence_count": r.evidence_count,
                "needs_review_count": r.needs_review_count,
            }
            for r in rows
        ],
    }
    session.add(
        ProfileHistory(
            child_id=child_id,
            as_of_version=version,
            snapshot_json=snapshot_json,
        )
    )
    session.commit()


# ---------------------------------------------------------------- 消费接口

def get_dimensions(session: Session, child_id: str) -> dict:
    """画像视图：{dimensions:[{code,name,level,evidence_count}], as_of_version}。"""
    aggregate_child(session, child_id)
    rows = (
        session.query(ProfileState)
        .filter_by(child_id=child_id)
        .order_by(ProfileState.dimension_code)
        .all()
    )
    dims = []
    for r in rows:
        dim = session.get(ProfileDimension, r.dimension_code)
        dims.append(
            {
                "code": r.dimension_code,
                "name": dim.name if dim else r.dimension_code,
                # needs_review 展示文案为"待观察"，枚举值仍为 needs_review（全链路统一）
                "level_display": _level_display(r.level),
                "level": r.level,
                "evidence_count": r.evidence_count,
                **({"needs_review_count": r.needs_review_count} if r.needs_review_count else {}),
            }
        )
    has_any = any(d["evidence_count"] or d.get("needs_review_count") for d in dims)
    return {
        "dimensions": dims,
        "as_of_version": AGGREGATION_RULE_VERSION,
        **({"note": _no_evidence_note(dims)} if not has_any else {}),
    }


def _level_display(level: str) -> str:
    return {
        "independent": "独立完成",
        "assisted": "提示后完成",
        "demonstrated": "示范后完成",
        "needs_review": "待观察",
    }.get(level, level)


def _no_evidence_note(dims: list[dict]) -> str:
    return (
        f"尚无学习记录：{len(dims)} 个维度均为待观察状态；"
        "这不是能力结论，继续学习后再看。"
    )


def get_history(session: Session, child_id: str) -> dict:
    """画像轨迹：{history:[{as_of,snapshot}]}。"""
    rows = (
        session.query(ProfileHistory)
        .filter_by(child_id=child_id)
        .order_by(ProfileHistory.created_at)
        .all()
    )
    return {
        "history": [
            {
                "as_of_version": r.as_of_version,
                "snapshot_json": r.snapshot_json,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


def append_trace(
    session: Session,
    *,
    child_id: str,
    activity_id: str | None,
    kind: str,
    payload: dict | None,
) -> None:
    """L1 trace append-only：写入永不抛错（调研 DeepTutor L1）。"""
    from app.profile.models import TraceEvent

    try:
        session.add(
            TraceEvent(
                child_id=child_id,
                activity_id=activity_id,
                kind=kind,
                payload_json=payload,
            )
        )
        session.commit()
    except Exception:  # noqa: BLE001 —— L1 trace 失败不阻断主链路
        session.rollback()
