"""学习闭环业务逻辑：会话/活动/尝试判定/证据分级/答案过滤/提示阶梯。

硬约束（AGENTS.md 护栏 + 规格 v2 §2/§3）：
- 先想后看双层：服务端答案过滤为准（answer-filtered 不含答案字段）；
- 证据分级由服务端按交互事实判定，客户端不自报；
- expected 优先用 spec 程序化字段，缺失显式失败不猜；
- Gate 原语固定枚举，未知类型显式失败；
- 一次迁移题独立答对 ≠ 掌握知识点（证据粒度=单次活动）。
"""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.jobs.service import create_job
from app.learning.models import (
    Attempt,
    EvidenceRecord,
    LearningSession,
    SessionActivity,
    SessionEvent,
)
from app.storage.models import LessonJob, LessonRevision

GATE_PRIMITIVES = {"tap_target", "drag_to_slot", "drag_handle", "pick_one"}
GATE_MODES = {
    "require_attempt",
    "require_correct_or_assisted",
    "learner_continue",
    "exploration_condition",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- 会话

def create_session(session: Session, child_id: str, source: str) -> dict:
    s = LearningSession(child_id=child_id)
    session.add(s)
    session.commit()
    session.refresh(s)
    _emit(session, s.id, event_type="stage_start", stage="session", payload={"source": source})
    return {"session_id": s.id, "status": s.status}


def get_session_detail(session: Session, child_id: str, session_id: str) -> dict:
    s = _get_session(session, child_id, session_id)
    activities = (
        session.query(SessionActivity)
        .filter_by(session_id=s.id)
        .order_by(SessionActivity.order_index)
        .all()
    )
    return {
        "session_id": s.id,
        "status": s.status,
        "activities": [_activity_summary(a) for a in activities],
    }


def complete_session(session: Session, child_id: str, session_id: str) -> dict:
    """结束会话：有尝试但未完成的活动写入 needs_review（R2'）。"""
    s = _get_session(session, child_id, session_id)
    activities = session.query(SessionActivity).filter_by(session_id=s.id).all()
    for act in activities:
        if act.status != "completed":
            attempts = (
                session.query(func.count(Attempt.id)).filter_by(activity_id=act.id).scalar()
                or 0
            )
            if attempts > 0:
                _write_evidence(
                    session,
                    child_id=child_id,
                    session_id=s.id,
                    activity=act,
                    kind="abandoned",
                    level="needs_review",
                    detail={"reason": "有尝试但未完成，无法判定独立性"},
                )
            act.status = "abandoned"
    s.status = "completed"
    s.ended_at = _utcnow()
    session.commit()
    _emit(session, s.id, event_type="done", stage="session")
    return {"session_id": s.id, "status": s.status}


def _get_session(session: Session, child_id: str, session_id: str) -> LearningSession:
    s = session.get(LearningSession, session_id)
    if s is None or s.child_id != child_id:
        raise ApiError(404, "SESSION_NOT_FOUND", "学习会话不存在")
    return s


# ---------------------------------------------------------------- 活动

def _require_published(session: Session, lesson_id: str, revision: int) -> None:
    """护栏5：孩子侧仅可用已人工审核发布的课程版本（R5，服务端强制）。"""
    from app.admin_api.models import ReviewRecord

    rev = (
        session.query(LessonRevision)
        .filter_by(lesson_id=lesson_id, revision=revision)
        .first()
    )
    if rev is None:
        raise ApiError(404, "LESSON_NOT_FOUND", "课程版本不存在")
    review = session.query(ReviewRecord).filter_by(revision_id=rev.id).first()
    if review is None or review.status != "published":
        raise ApiError(
            409,
            "LESSON_NOT_PUBLISHED",
            "课程尚未通过人工审核发布，请稍后再试",
        )


def start_activity(
    session: Session,
    child_id: str,
    session_id: str,
    kind: str,
    input_json: dict | None,
    lesson_id: str | None,
    revision: int | None,
) -> dict:
    s = _get_session(session, child_id, session_id)
    if s.status != "active":
        raise ApiError(409, "SESSION_CLOSED", "会话已结束，请开始新的学习")

    spec_dict: dict | None = None
    job_status: str | None = None
    if lesson_id and revision is not None:
        rev = (
            session.query(LessonRevision)
            .filter_by(lesson_id=lesson_id, revision=revision)
            .first()
        )
        if rev is None:
            raise ApiError(404, "LESSON_NOT_FOUND", "课程版本不存在")
        _require_published(session, lesson_id, revision)
        spec_dict = rev.spec_json
    elif input_json is not None:
        result = ensure_lesson(session, input_json)
        if result.get("spec_dict") is None:
            return {"status": result["job"].status, "job_id": result["job"].id}
        spec_dict = result["spec_dict"]
        job_status = result["job"].status
    else:
        raise ApiError(422, "MISSING_REQUIRED_FACT", "缺少课程来源：input 或 lesson_id/revision")

    validate_gate_contract(spec_dict)

    order_index = (
        session.query(func.count(SessionActivity.id)).filter_by(session_id=s.id).scalar()
        or 0
    )
    act = SessionActivity(
        session_id=s.id,
        child_id=child_id,
        kind=kind,
        lesson_id=spec_dict.get("lesson_id"),
        revision=spec_dict.get("revision"),
        spec_json=spec_dict,
        status="in_progress",
        method_source=_method_source(spec_dict),
        order_index=order_index + 1,
    )
    session.add(act)
    session.commit()
    session.refresh(act)
    _emit(
        session,
        s.id,
        event_type="stage_start",
        stage="activity",
        payload={"activity_id": act.id},
    )
    return {"activity": _activity_summary(act), "job_status": job_status}


def ensure_lesson(session: Session, input_json: dict) -> dict:
    """同输入按 hash 复用已生成 revision（性能评审结论③）。

    实现：input_hash 作为 Idempotency-Key 传给 create_job；
    已 SUCCEEDED → 取最新 revision；否则返回 job 供轮询六阶段进度。
    生成失败的 job（FAILED/CANCELED）允许重新调度（不带幂等键）。
    """
    raw_hash = hashlib.sha256(
        json.dumps(input_json, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    existing = (
        session.query(LessonJob).filter_by(idempotency_key=raw_hash).first()
        if raw_hash
        else None
    )
    if existing is not None and existing.status in ("FAILED", "CANCELED"):
        # 失败任务允许重试：不带幂等键新建，避免复用失败结果
        job = create_job(
            session,
            kind=input_json.get("kind", "problem"),
            input_json=input_json,
            curriculum_context_json=None,
            objectives_json=None,
            idempotency_key=None,
        )
        return {"job": job}

    job = create_job(
        session,
        kind=input_json.get("kind", "problem"),
        input_json=input_json,
        curriculum_context_json=None,
        objectives_json=None,
        idempotency_key=raw_hash,
    )
    if job.status == "SUCCEEDED" and job.lesson_id:
        rev = (
            session.query(LessonRevision)
            .filter_by(lesson_id=job.lesson_id)
            .order_by(LessonRevision.revision.desc())
            .first()
        )
        if rev is not None:
            # 护栏5：未审核发布的生成结果不得直接进入孩子课堂（R5）
            _require_published(session, job.lesson_id, rev.revision)
            return {"job": job, "spec_dict": rev.spec_json}
    return {"job": job}


def _method_source(spec_dict: dict) -> str:
    """R4 来源透明：skill_refs（skill 命中）或 strategy_refs（策略族=凑十法等推荐方法）→ skill。"""
    design = spec_dict.get("teaching_design") or {}
    if design.get("skill_refs") or design.get("strategy_refs"):
        return "skill"
    return "standard"


def validate_gate_contract(spec_dict: dict) -> None:
    """Gate schema 校验：未知原语/模式显式失败（R4'）。"""
    for node in spec_dict.get("activity_graph") or []:
        gate = node.get("gate")
        if not gate:
            continue
        if gate.get("type") is not None and gate["type"] not in GATE_PRIMITIVES:
            raise ApiError(
                422,
                "GATE_CONTRACT_INVALID",
                f"未知 gate.type：{gate['type']}",
                {"allowed": sorted(GATE_PRIMITIVES)},
            )
        if gate.get("mode") is not None and gate["mode"] not in GATE_MODES:
            raise ApiError(
                422,
                "GATE_CONTRACT_INVALID",
                f"未知 gate.mode：{gate['mode']}",
                {"allowed": sorted(GATE_MODES)},
            )


def _activity_summary(act: SessionActivity) -> dict:
    return {
        "activity_id": act.id,
        "kind": act.kind,
        "lesson_id": act.lesson_id,
        "revision": act.revision,
        "status": act.status,
        "method_source": act.method_source,
        "order_index": act.order_index,
    }


# ---------------------------------------------------------------- 尝试与提示

def submit_attempt(
    session: Session,
    child_id: str,
    activity_id: str,
    step_id: str,
    value,
) -> dict:
    act = _get_activity(session, child_id, activity_id)
    spec_dict = act.spec_json or {}
    node = _find_node(spec_dict, step_id)

    correct = _judge(node, value)
    attempt_row = Attempt(
        activity_id=act.id,
        child_id=child_id,
        step_id=step_id,
        kind="answer",
        value_json={"value": value},
        correct=correct,
    )
    session.add(attempt_row)
    session.commit()

    if correct:
        _emit(
            session,
            act.session_id,
            event_type="content",
            stage="attempt",
            payload={"step_id": step_id, "correct": True},
        )
        written_kinds = _maybe_complete(session, act)
        return {
            "correct": True,
            "step_unlocked": step_id,
            **({"evidence_written": written_kinds} if written_kinds else {}),
            **{"activity_status": act.status},
        }

    wrong_before = (
        session.query(func.count(Attempt.id))
        .filter_by(activity_id=act.id, step_id=step_id, kind="answer", correct=False)
        .scalar()
        or 0
    )
    hint_text = _next_hint(node, wrong_before)
    _emit(
        session,
        act.session_id,
        event_type="error",
        stage="attempt",
        payload={"step_id": step_id},
    )
    return {"correct": False, "hint": hint_text}


def request_hint(
    session: Session,
    child_id: str,
    activity_id: str,
    step_id: str,
) -> dict:
    act = _get_activity(session, child_id, activity_id)
    spec_dict = act.spec_json or {}
    node = _find_node(spec_dict, step_id)

    hint_count = (
        session.query(func.count(Attempt.id))
        .filter_by(activity_id=act.id, step_id=step_id, kind="hint")
        .scalar()
        or 0
    )
    assistance = node.get("assistance") or []
    if not assistance:
        raise ApiError(422, "NO_HINTS", "该步骤没有可提供的提示")
    hint_text = assistance[min(hint_count, len(assistance) - 1)]
    hint_row = Attempt(
        activity_id=act.id,
        child_id=child_id,
        step_id=step_id,
        kind="hint",
        value_json={"hint_index": hint_count},
        correct=False,
    )
    session.add(hint_row)
    session.commit()
    _emit(
        session,
        act.session_id,
        event_type="tool_call",
        stage="hint",
        payload={"step_id": step_id, "hint_index": hint_count},
    )
    return {"hint": hint_text, "step_id": step_id}


# ---------------------------------------------------------------- 完成与证据

def complete_activity(
    session: Session,
    child_id: str,
    activity_id: str,
    value,
) -> dict:
    """显式完成（迁移题等）：写入对应证据；已自动完成的幂等返回。"""
    act = _get_activity(session, child_id, activity_id)
    written = _maybe_complete(session, act)
    if not written:
        return {"activity_status": act.status, "completed": False}
    return {"activity_status": act.status, "completed": True, "evidence_written": written}


def _maybe_complete(session: Session, act: SessionActivity) -> list[str]:
    """所有门槛步骤正确后写证据并置 completed；返回本次写入的证据 kind 列表。"""
    spec_dict = act.spec_json or {}
    nodes = spec_dict.get("activity_graph") or []
    correct_ids = _correct_step_ids(session, act.id)

    gate_nodes = [
        n for n in nodes if n.get("gate") and not str(n.get("id", "")).startswith("transfer")
    ]
    transfer_nodes = [
        n for n in nodes if n.get("gate") and str(n.get("id", "")).startswith("transfer")
    ]

    written: list[str] = []
    if gate_nodes and all(n["id"] in correct_ids for n in gate_nodes):
        kind = "gate_complete"
        if not _evidence_exists(session, act.id, kind):
            _write_evidence(
                session,
                child_id=act.child_id,
                session_id=act.session_id,
                activity=act,
                kind=kind,
                level=_grade_level(session, act.id, [n["id"] for n in gate_nodes]),
                detail={"steps": [n["id"] for n in gate_nodes]},
            )
            written.append(kind)

    for tn in transfer_nodes:
        if tn["id"] in correct_ids:
            kind = "transfer_correct"
            if not _evidence_exists(session, act.id, kind):
                _write_evidence(
                    session,
                    child_id=act.child_id,
                    session_id=act.session_id,
                    activity=act,
                    kind=kind,
                    level=_grade_transfer_level(session, act.id, tn["id"]),
                    detail={"step": tn["id"]},
                )
                written.append(kind)

    all_gated = [n["id"] for n in gate_nodes + transfer_nodes]
    if all_gated and all(g in correct_ids for g in all_gated):
        act.status = "completed"
        session.commit()
        _emit(
            session,
            act.session_id,
            event_type="result",
            stage="activity",
            payload={"activity_id": act.id, "status": "completed"},
        )
    return written


def _correct_step_ids(session: Session, activity_id: str) -> set[str]:
    rows = (
        session.query(Attempt.step_id)
        .filter_by(activity_id=activity_id, kind="answer", correct=True)
        .all()
    )
    return {r[0] for r in rows}


def _counts(session: Session, activity_id: str, step_ids: list[str]) -> tuple[int, int]:
    """返回 (错误作答数, 提示数)。"""
    wrong = (
        session.query(func.count(Attempt.id))
        .filter(
            Attempt.activity_id == activity_id,
            Attempt.kind == "answer",
            Attempt.correct.is_(False),
            Attempt.step_id.in_(step_ids),
        )
        .scalar()
        or 0
    )
    hints = (
        session.query(func.count(Attempt.id))
        .filter(
            Attempt.activity_id == activity_id,
            Attempt.kind == "hint",
            Attempt.step_id.in_(step_ids),
        )
        .scalar()
        or 0
    )
    return wrong, hints


def _grade_level(session: Session, activity_id: str, gate_ids: list[str]) -> str:
    """Gate 完成仅取 independent/assisted（规格 §3.1）。"""
    wrong, hints = _counts(session, activity_id, gate_ids)
    return "assisted" if (wrong > 0 or hints > 0) else "independent"


def _grade_transfer_level(session: Session, activity_id: str, step_id: str) -> str:
    """迁移题：提示>=2 → demonstrated；提示>=1 或 错误>1 → assisted；否则 independent。"""
    wrong, hints = _counts(session, activity_id, [step_id])
    if hints >= 2:
        return "demonstrated"
    if hints >= 1 or wrong > 1:
        return "assisted"
    return "independent"


def _evidence_exists(session: Session, activity_id: str, kind: str) -> bool:
    return (
        session.query(EvidenceRecord)
        .filter_by(activity_id=activity_id, kind=kind)
        .first()
        is not None
    )


def _write_evidence(
    session: Session,
    *,
    child_id: str,
    session_id: str,
    activity: SessionActivity,
    kind: str,
    level: str,
    detail: dict | None,
) -> EvidenceRecord:
    """写入证据（R7'：id=纯完成证据 ID，唯一约束防重复）。"""
    rec = EvidenceRecord(
        child_id=child_id,
        session_id=session_id,
        activity_id=activity.id,
        kind=kind,
        level=level,
        detail_json=detail,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


# ---------------------------------------------------------------- 判定与提示

def _find_node(spec_dict: dict, step_id: str) -> dict:
    for node in spec_dict.get("activity_graph") or []:
        if node.get("id") == step_id:
            return node
    raise ApiError(404, "STEP_NOT_FOUND", f"步骤不存在：{step_id}")


def _judge(node: dict, value) -> bool:
    """程序化判定：expected/correct_index 缺失时显式失败，不猜（T3 六问结论）。"""
    resp = node.get("response") or {}
    kind = resp.get("kind")
    if kind == "number":
        expected = resp.get("expected")
        if expected is None:
            raise ApiError(422, "NO_PROGRAMMATIC_ANSWER", "该步骤无程序化期望答案，服务端不猜测")
        return str(value).strip() == str(expected).strip()
    if kind == "choice":
        correct_index = resp.get("correct_index")
        options = resp.get("options") or []
        if correct_index is None or correct_index >= len(options):
            raise ApiError(422, "NO_PROGRAMMATIC_ANSWER", "该步骤无程序化期望答案，服务端不猜测")
        return str(value).strip() == str(options[correct_index]).strip()
    raise ApiError(422, "NO_PROGRAMMATIC_ANSWER", f"题型 {kind} 暂无程序化判定")


def _next_hint(node: dict, wrong_before: int) -> str | None:
    """错误后分层提示：按此前错误次数递进，最后一项为示范出口。"""
    assistance = node.get("assistance") or []
    if not assistance:
        return None
    return assistance[min(wrong_before, len(assistance) - 1)]


# ---------------------------------------------------------------- 答案过滤

def get_filtered_activity(session: Session, child_id: str, activity_id: str) -> dict:
    """先想后看出口：返回不含未解锁答案字段的课程规格（服务端过滤为准）。"""
    act = _get_activity(session, child_id, activity_id)
    spec_dict = act.spec_json or {}
    correct_ids = _correct_step_ids(session, act.id)
    all_gated_ids = [
        n["id"] for n in spec_dict.get("activity_graph") or [] if n.get("gate")
    ]
    all_gates_done = bool(all_gated_ids) and all(g in correct_ids for g in all_gated_ids)
    filtered = _filtered_spec(spec_dict, correct_ids, all_gates_done)
    return {
        "activity_id": act.id,
        "status": act.status,
        "method_source": act.method_source,
        "spec": filtered,
        "unlocked_steps": sorted(correct_ids),
        "answer_filtered": True,
    }


def _filtered_spec(spec_dict: dict, correct_ids: set[str], all_gates_done: bool) -> dict:
    """过滤规则：
    - predict/construct/manipulate：未答对的步骤 response.correct_index/expected 置空；
    - observe：全部门槛未完成前 narration 置空（结论文本不下发，护栏1双层）；
    - verification.claims[].statement / replay：均承载完整答案，未完成前不下发；
    - _meta（生成期门禁等内部元数据）永不下发给孩子。
    保留结构（locked 标记供客户端占位渲染）。
    """
    out_nodes = []
    for node in spec_dict.get("activity_graph") or []:
        n = dict(node)
        ntype = n.get("type")
        if ntype == "observe":
            if not all_gates_done:
                n["narration"] = ""
                n["locked"] = True
            out_nodes.append(n)
            continue
        resp = n.get("response")
        if isinstance(resp, dict) and n.get("id") not in correct_ids:
            resp = dict(resp)
            resp["correct_index"] = None
            resp["expected"] = None
            n["response"] = resp
            n["locked"] = True
        out_nodes.append(n)
    result = dict(spec_dict)
    result["activity_graph"] = out_nodes
    if not all_gates_done:
        ver = result.get("verification")
        if isinstance(ver, dict) and ver.get("claims"):
            result["verification"] = {
                **ver,
                "claims": [{**c, "statement": ""} for c in ver["claims"]],
            }
        # 完整回放 = 完整解法序列，未完成前不可见
        result.pop("replay", None)
    result.pop("_meta", None)
    return result


# ---------------------------------------------------------------- 事件与阶段

def get_job_stages(session: Session, job_id: str) -> dict:
    """六阶段进度透出（规格 §4：GET /v1/jobs/{id}/stages，轮询）。"""
    from app.storage.models import JobStageRun

    job = session.get(LessonJob, job_id)
    if job is None:
        raise ApiError(404, "JOB_NOT_FOUND", "生成任务不存在")
    runs = (
        session.query(JobStageRun)
        .filter_by(job_id=job_id)
        .order_by(JobStageRun.attempt.desc(), JobStageRun.started_at)
        .all()
    )
    stage_order = ["intent", "verify", "retrieve", "plan", "compile", "review"]
    stages = [
        {"stage": r.stage, "status": r.status, "attempt": r.attempt}
        for r in runs
        if r.stage != "generate"
    ]
    stages.sort(key=lambda s: stage_order.index(s["stage"]) if s["stage"] in stage_order else 99)
    return {"job_id": job_id, "job_status": job.status, "stages": stages}


# ---------------------------------------------------------------- 内部工具

def _get_activity(session: Session, child_id: str, activity_id: str) -> SessionActivity:
    act = session.get(SessionActivity, activity_id)
    if act is None or act.child_id != child_id:
        raise ApiError(404, "ACTIVITY_NOT_FOUND", "学习活动不存在")
    return act


def _emit(
    session: Session,
    session_id: str,
    event_type: str,
    stage: str | None = None,
    payload: dict | None = None,
) -> None:
    """StreamBus 事件持久化：seq 递增，断线重连按 seq 续传。"""
    next_seq = (
        session.query(func.max(SessionEvent.seq)).filter_by(session_id=session_id).scalar()
        or 0
    ) + 1
    ev = SessionEvent(
        session_id=session_id,
        turn_id=session_id,
        seq=next_seq,
        event_type=event_type,
        source="server",
        stage=stage,
        payload_json=payload,
    )
    session.add(ev)
    session.commit()


def get_full_answer(session: Session, child_id: str, activity_id: str) -> dict:
    """完整解答出口：仅活动完成后可读（先想后看，服务端为准）。

    未完成时 403 ANSWER_LOCKED——完整答案在孩子尝试前不可见（护栏1双层）。
    """
    act = _get_activity(session, child_id, activity_id)
    if act.status != "completed":
        raise ApiError(403, "ANSWER_LOCKED", "先完成尝试，再查看完整解答")
    return {"activity_id": act.id, "status": act.status, "spec": act.spec_json}
