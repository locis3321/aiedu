"""题库与练习安排 API（规格 v2 §4.2 资源清单）。

鉴权：child-scoped token（孩子侧）；后台管理端点（questions/sources/templates
管理）由 T7 admin_api 消费同一 service，不在此重复暴露。
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.learning.router import get_current_child, get_session
from app.questionbank import service
from app.reports.router import get_child_context

router = APIRouter(prefix="/v1")


@router.post("/children/{child_id}/practice-sets")
def build_practice_set(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.build_practice_set(session, child_id)


@router.get("/children/{child_id}/practice-sets")
def list_practice_sets(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    from app.questionbank.models import PracticeSet

    rows = (
        session.query(PracticeSet)
        .filter_by(child_id=child_id)
        .order_by(PracticeSet.created_at.desc())
        .all()
    )
    return {
        "child_id": child_id,
        "practice_sets": [
            {
                "id": r.id,
                "question_ids": r.question_ids_json,
                "basis": r.basis_json,
            }
            for r in rows
        ],
    }


@router.post("/children/{child_id}/diagnostics")
def create_diagnostics(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.create_diagnostics(session, child_id)


@router.post("/children/{child_id}/exams/generate")
def generate_exam(
    child_id: str,
    template_id: str | None = None,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.generate_paper(session, child_id, template_id)


@router.post("/exams/{paper_id}/submit")
def submit_exam(
    paper_id: str,
    answers: dict,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict:
    """交卷鉴权：child token（本人）或 parent token（拥有该孩子）。"""
    from app.questionbank.models import ExamPaper

    paper = session.get(ExamPaper, paper_id)
    if paper is None:
        raise ApiError(404, "PAPER_NOT_FOUND", "试卷不存在")
    child_id = _resolve_child(authorization, paper.child_id, session)
    return service.submit_exam(session, child_id, paper_id, answers)


def _resolve_child(authorization: str | None, paper_child_id: str, session: Session) -> str:
    import jwt as pyjwt

    from app.accounts.models import ChildProfile, ParentUser
    from app.core.security import decode_token

    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少登录凭证")
    try:
        payload = decode_token(authorization.removeprefix("Bearer ").strip())
    except pyjwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "登录状态无效或已过期") from None
    role = payload.get("role")
    if role == "child":
        if payload.get("sub") != paper_child_id:
            raise ApiError(403, "FORBIDDEN", "无权提交该试卷")
        return paper_child_id
    if role == "parent":
        # 归属校验：仅试卷孩子的拥有者家长可代交（跨家长隔离）
        parent = session.get(ParentUser, payload.get("sub"))
        child = session.get(ChildProfile, paper_child_id)
        if (
            parent is None
            or child is None
            or child.parent_id != parent.id
            or child.deleted_at is not None
        ):
            raise ApiError(403, "FORBIDDEN", "无权提交该试卷")
        return paper_child_id
    raise ApiError(401, "UNAUTHORIZED", "需要家长或孩子身份")


@router.get("/children/{child_id}/route")
def get_route(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_route(session, child_id)


@router.post("/variants/generate")
def generate_variant(
    base_input: dict,
    _auth: tuple = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.generate_variant(session, base_input)
