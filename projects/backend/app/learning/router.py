"""学习闭环 API（规格 v2 §4.2 资源清单）。

鉴权：child-scoped token（T2 switch-session 签发）；跨孩子读取一律 403/404。
"""

import jwt as pyjwt
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.accounts.models import ChildProfile
from app.core.errors import ApiError
from app.core.security import decode_token
from app.learning import service
from app.learning.schemas import (
    CompleteActivityRequest,
    CreateSessionRequest,
    HintRequest,
    StartActivityRequest,
    SubmitAttemptRequest,
)
from app.storage.db import create_session_factory

router = APIRouter(prefix="/v1")


def get_session():
    factory = create_session_factory()
    with factory() as session:
        yield session


def get_current_child(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> tuple[ChildProfile, dict]:
    token = _extract_bearer(authorization)
    try:
        payload = decode_token(token)
    except pyjwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "登录状态无效或已过期") from None
    if payload.get("role") != "child":
        raise ApiError(401, "UNAUTHORIZED", "需要孩子身份")
    child = session.get(ChildProfile, payload.get("sub"))
    if child is None or child.deleted_at is not None:
        raise ApiError(401, "UNAUTHORIZED", "孩子档案不存在")
    return child, payload


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少登录凭证")
    return authorization.removeprefix("Bearer ").strip()


def _child_id(auth: tuple[ChildProfile, dict]) -> str:
    return auth[0].id


# ---------------------------------------------------------------- 会话

@router.post("/sessions", status_code=201)
def create_session(
    request: CreateSessionRequest,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.create_session(session, _child_id(auth), request.source)


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_session_detail(session, _child_id(auth), session_id)


@router.post("/sessions/{session_id}/complete")
def complete_session(
    session_id: str,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.complete_session(session, _child_id(auth), session_id)


# ---------------------------------------------------------------- 活动

@router.post("/sessions/{session_id}/activities", status_code=201)
def start_activity(
    session_id: str,
    request: StartActivityRequest,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.start_activity(
        session,
        _child_id(auth),
        session_id,
        request.kind,
        request.input,
        request.lesson_id,
        request.revision,
    )


@router.get("/activities/{activity_id}/answer")
def full_answer(
    activity_id: str,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_full_answer(session, _child_id(auth), activity_id)


@router.get("/activities/{activity_id}/answer-filtered")
def answer_filtered(
    activity_id: str,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_filtered_activity(session, _child_id(auth), activity_id)


@router.post("/activities/{activity_id}/attempts")
def submit_attempt(
    activity_id: str,
    request: SubmitAttemptRequest,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.submit_attempt(
        session, _child_id(auth), activity_id, request.step_id, request.value
    )


@router.post("/activities/{activity_id}/hints")
def request_hint(
    activity_id: str,
    request: HintRequest,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.request_hint(session, _child_id(auth), activity_id, request.step_id)


@router.post("/activities/{activity_id}/complete")
def complete_activity(
    activity_id: str,
    request: CompleteActivityRequest,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.complete_activity(session, _child_id(auth), activity_id, request.value)


# ---------------------------------------------------------------- 生成进度

@router.get("/jobs/{job_id}/stages")
def job_stages(
    job_id: str,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_job_stages(session, job_id)
