"""足迹与家长报告 API（规格 v2 §4.2 资源清单）。

鉴权：家长 token（拥有该孩子）或 child token（本人）——报告是家长视角，
足迹是孩子视角；跨孩子访问一律 403/404。
"""

import json

import jwt as pyjwt
from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.accounts.models import ChildProfile, ParentUser
from app.core.errors import ApiError
from app.core.security import decode_token
from app.learning.router import get_session
from app.reports import service

router = APIRouter(prefix="/v1")


def get_child_context(
    child_id: str,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> str:
    """返回有权限访问该孩子的身份：家长拥有者或孩子本人（否则 403）。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少登录凭证")
    try:
        payload = decode_token(authorization.removeprefix("Bearer ").strip())
    except pyjwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "登录状态无效或已过期") from None

    role = payload.get("role")
    if role == "child":
        if payload.get("sub") != child_id:
            raise ApiError(403, "FORBIDDEN", "无权访问该孩子的数据")
        return child_id
    if role == "parent":
        parent = session.get(ParentUser, payload.get("sub"))
        if parent is None:
            raise ApiError(401, "UNAUTHORIZED", "家长账号不存在")
        child = session.get(ChildProfile, child_id)
        if child is None or child.parent_id != parent.id or child.deleted_at is not None:
            raise ApiError(404, "CHILD_NOT_FOUND", "孩子档案不存在")
        return child_id
    raise ApiError(401, "UNAUTHORIZED", "需要家长或孩子身份")


def get_parent_context(
    child_id: str,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> str:
    """家长专属上下文：仅孩子的拥有者家长可执行（数据管理类操作）。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少登录凭证")
    try:
        payload = decode_token(authorization.removeprefix("Bearer ").strip())
    except pyjwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "登录状态无效或已过期") from None
    if payload.get("role") != "parent":
        raise ApiError(403, "FORBIDDEN", "该操作仅家长可执行")
    parent = session.get(ParentUser, payload.get("sub"))
    if parent is None:
        raise ApiError(401, "UNAUTHORIZED", "家长账号不存在")
    child = session.get(ChildProfile, child_id)
    if child is None or child.parent_id != parent.id or child.deleted_at is not None:
        raise ApiError(404, "CHILD_NOT_FOUND", "孩子档案不存在")
    return child_id


@router.get("/children/{child_id}/footprints")
def footprints(
    child_id: str,
    days: int = 30,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_footprints(session, child_id, days)


@router.get("/children/{child_id}/reports/summary")
def summary(
    child_id: str,
    days: int = 30,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_summary(session, child_id, days)


@router.get("/children/{child_id}/reports/profile-view")
def profile_view(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_profile_view(session, child_id)


@router.post("/children/{child_id}/data-exports")
def create_export(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> Response:
    """导出：返回可下载 JSON 文件（内容与证据一致，真实操作）。"""
    payload = service.create_export(session, child_id)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="aiedu-export-{child_id[:8]}.json"'
        },
    )


@router.delete("/children/{child_id}/data")
def delete_data(
    child_id: str,
    _ctx: str = Depends(get_parent_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.delete_data(session, child_id)


@router.post("/children/{child_id}/share/preview")
def share_preview(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.share_preview(session, child_id)
