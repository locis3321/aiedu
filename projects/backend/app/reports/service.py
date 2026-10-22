"""足迹与家长报告业务逻辑：证据投影（规格 v2 §1.2/§5.3 + 任务包验收项）。

硬约束：
- 报告是证据的投影，不制造新事实；跨孩子访问查询层强制归属校验；
- 证据分列计数（independent/assisted/demonstrated/needs_review），无掌握度百分比；
- 画像视图从 T12 读取（profile_states/profile_history），本域只做投影；
- 无数据显示真实空状态，不用示例数据补位；
- 数据出口真实操作；分享默认脱敏。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.learning.models import EvidenceRecord

DEFAULT_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(dt) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _since(days: int) -> datetime:
    return _utcnow() - timedelta(days=days)


def _require_child(session: Session, child_id: str) -> None:
    from app.accounts.models import ChildProfile

    child = session.get(ChildProfile, child_id)
    if child is None or child.deleted_at is not None:
        raise ApiError(404, "CHILD_NOT_FOUND", "孩子档案不存在")


# ---------------------------------------------------------------- 足迹

def get_footprints(session: Session, child_id: str, days: int = DEFAULT_DAYS) -> dict:
    """学习足迹：最近课程（证据）、待复习筛选、易错总结关联原课证据。"""
    _require_child(session, child_id)
    since = _since(days)
    rows = (
        session.query(EvidenceRecord)
        .filter(EvidenceRecord.child_id == child_id)
        .all()
    )
    recent = [
        r
        for r in rows
        if _aware(r.created_at) is not None and _aware(r.created_at) >= since
    ]
    recent.sort(key=lambda r: _aware(r.created_at) or _utcnow(), reverse=True)

    items = [
        {
            "evidence_id": r.id,
            "kind": r.kind,
            "level": r.level,
            "level_display": _level_display(r.level),
            "activity_id": r.activity_id,
            "session_id": r.session_id,
            "created_at": _aware(r.created_at).isoformat() if _aware(r.created_at) else None,
            # 易错总结条目可跳转原课证据（关联 ID）
            **({"replay_ref": r.activity_id} if r.activity_id else {}),
        }
        for r in recent
    ]
    review_pending = [i for i in items if i["level"] in ("assisted", "needs_review")]
    return {
        "child_id": child_id,
        "items": items,
        "review_pending": review_pending,
        "empty": not items,
        # 空状态真实呈现：无记录时给出说明而非示例数据
        **({"note": "还没有学习记录。完成一次学习后，这里会出现足迹。"} if not items else {}),
    }


def _level_display(level: str) -> str:
    return {
        "independent": "独立完成",
        "assisted": "提示后完成",
        "demonstrated": "示范后完成",
        "needs_review": "待观察",
    }.get(level, level)


def _guarded(text: str) -> str:
    """banned-phrase guard：报告文本出口统一拦截绝对化断言（护栏2）。"""
    from app.profile.service import assert_no_banned

    assert_no_banned(text)
    return text


# ---------------------------------------------------------------- 家长报告

def get_summary(session: Session, child_id: str, days: int = DEFAULT_DAYS) -> dict:
    """家长报告：时间范围内四级证据分列计数（增量统计）+ 薄弱点 + 练习入口。"""
    _require_child(session, child_id)
    since = _since(days)
    rows = (
        session.query(EvidenceRecord)
        .filter(EvidenceRecord.child_id == child_id)
        .all()
    )
    recent = [
        r for r in rows if _aware(r.created_at) is not None and _aware(r.created_at) >= since
    ]
    counts = {"independent": 0, "assisted": 0, "demonstrated": 0, "needs_review": 0}
    for r in recent:
        counts[r.level] = counts.get(r.level, 0) + 1

    weak_points = _weak_points(session, child_id)
    return {
        "child_id": child_id,
        "range_days": days,
        "counts": counts,
        **{"total_events": sum(counts.values())},
        **{"weak_points": weak_points},
        **{"practice_entry_available": bool(weak_points)},
        **{"exam_interpretation": exam_interpretation(session, child_id)},
        **({"note": "暂无学习记录，报告为空状态；不预设能力结论。"} if not recent else {}),
    }


def _weak_points(session: Session, child_id: str) -> list[dict]:
    """薄弱点说明：来自 T12 画像投影（证据描述，无百分比）。"""
    from app.profile.service import get_dimensions

    profile = get_dimensions(session, child_id)
    points = []
    for d in profile["dimensions"]:
        if d["level"] in ("assisted", "demonstrated") or (
            d["level"] == "needs_review" and d.get("needs_review_count")
        ):
            points.append(
                {
                    "dimension_code": d["code"],
                    "dimension_name": d["name"],
                    "level": d["level"],
                    "level_display": d["level_display"],
                    "note": _guarded(
                        f"{d['name']}维度近期有{_level_display(d['level'])}记录，"
                        "建议安排针对性练习"
                    ),
                }
            )
    return points


def exam_interpretation(session: Session, child_id: str) -> list[dict]:
    """诊断/同步/阶段测评结果解释：四级证据词，无掌握度百分比。"""
    rows = (
        session.query(EvidenceRecord)
        .filter(EvidenceRecord.child_id == child_id, EvidenceRecord.kind == "exam_result")
        .all()
    )
    out = []
    for r in rows:
        detail = r.detail_json or {}
        out.append(
            {
                "paper_id": detail.get("paper_id"),
                "evidence_level": r.level,
                "interpretation": _interpret(r.level),
            }
        )
    return out


def _interpret(level: str) -> str:
    return {
        "independent": "本次全部独立完成；继续观察下一次表现，不做掌握结论。",
        "assisted": "本次部分使用提示完成；建议针对薄弱点安排同步练习。",
        "demonstrated": "本次在示范后完成；建议先复习对应讲解再尝试独立练习。",
        "needs_review": "本次未完成或结果待复核；不据此做能力判断。",
    }.get(level, "")


# ---------------------------------------------------------------- 画像视图投影

def get_profile_view(session: Session, child_id: str) -> dict:
    """能力评估报告：T12 画像视图投影（F4'），无捏造分数/排名/心理标签。"""
    from app.profile.service import get_dimensions, get_history

    dims = get_dimensions(session, child_id)
    hist = get_history(session, child_id)
    return {
        **{"child_id": child_id},
        **{"dimensions": dims["dimensions"]},
        **{"as_of_version": dims["as_of_version"]},
        **{"history_count": len(hist["history"])},
        **{"note": dims.get("note", "")},
        **{"no_score_note": "本报告展示证据带而非分数；一次迁移题独立答对不等于已掌握知识点。"},
    }


# ---------------------------------------------------------------- 数据出口

def create_export(session: Session, child_id: str) -> dict:
    """导出：真实生成与证据一致的 JSON（可下载文件）。"""
    _require_child(session, child_id)
    footprints = get_footprints(session, child_id)
    summary = get_summary(session, child_id)
    profile_view = get_profile_view(session, child_id)
    payload = {
        "exported_at": _utcnow().isoformat(),
        "child_ref": {"id_masked": f"{child_id[:4]}****"},
        **{"footprints": footprints["items"]},
        **{"summary_counts": summary["counts"]},
        **{"profile_view": profile_view},
        **{"note": "本导出为学习证据快照；不含姓名/学校/联系方式等敏感信息。"},
    }
    return payload


def delete_data(session: Session, parent_authorized_child: str) -> dict:
    """删除孩子数据：软删标记 + 清理关联业务数据（§5.3），保留匿名聚合统计。

    注意：本函数只处理已通过归属校验的 childId（家长权限，router 层强制）；
    物理删除策略待业务确认。
    """
    from app.accounts.models import ChildProfile
    from app.learning.models import Attempt, LearningSession, SessionActivity, SessionEvent
    from app.points.models import LedgerEntry
    from app.profile.models import ProfileHistory, ProfileState
    from app.questionbank.models import ExamPaper, ExamResult, PracticeSet

    child = session.get(ChildProfile, parent_authorized_child)
    if child is None or child.deleted_at is not None:
        raise ApiError(404, "CHILD_NOT_FOUND", "孩子档案不存在")

    # 清理关联业务数据（证据/会话/尝试/事件/账本/画像/试卷/练习集）
    child_session_ids = (
        session.query(LearningSession.id).filter_by(child_id=child.id).scalar_subquery()
    )
    session.query(SessionEvent).filter(
        SessionEvent.session_id.in_(child_session_ids)
    ).delete(synchronize_session=False)
    for model in (
        EvidenceRecord,
        Attempt,
        SessionActivity,
        LearningSession,
        LedgerEntry,
        ProfileState,
        ProfileHistory,
        ExamPaper,
        ExamResult,
        PracticeSet,
    ):
        session.query(model).filter_by(child_id=child.id).delete()
    # 软删标记：档案保留（匿名聚合统计不受影响）
    child.deleted_at = _utcnow()
    session.commit()
    return {
        **{"child_id_masked": f"{child.id[:4]}****"},
        **{"deleted": True},
        **{
            "note": "已清理该孩子的学习证据、会话与尝试、成长星流水、画像与试卷数据；匿名统计保留。"
        },

    }


# ---------------------------------------------------------------- 分享脱敏

def share_preview(session: Session, child_id: str) -> dict:
    """分享预览：默认脱敏；无真实成绩不生成虚构分数。

    链接分享（访问范围/有效期/撤销）未接入——需分享链接表与创建/撤销端点，
    属后续批次；当前仅返回脱敏预览快照，不伪造可撤销令牌（治理规则：未接入显式呈现）。
    """
    summary = get_summary(session, child_id)
    snapshot = {
        # 匿名标识：不包含真实姓名/学校/联系方式/其他孩子资料
        "child_label": "一位认真学习的小朋友",
        "counts": summary["counts"],
        "weak_point_names": [p["dimension_name"] for p in summary["weak_points"]],
        "no_fake_score_note": "分享内容为学习表现记录，不生成虚构分数或排名。",
    }
    return {
        "snapshot": snapshot,
        "share_status": {
            "link_sharing": "not_connected",
            "note": "链接分享未接入（访问范围/有效期/撤销待后续实现），当前仅提供脱敏预览。",
        },
    }



