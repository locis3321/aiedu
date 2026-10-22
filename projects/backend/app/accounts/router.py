"""账号域 API（规格 v2 §4.2 资源清单；统一错误语义 §4.1）。

鉴权：家长 JWT（Bearer）；child-scoped token 仅用于孩子端（T3/T8 消费）。
"""

import jwt as pyjwt
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.accounts import service
from app.accounts.models import ParentUser
from app.accounts.schemas import (
    ChildCreateRequest,
    ChildUpdateRequest,
    ConsentGrantRequest,
    ParentProfileUpdateRequest,
    SmsLoginRequest,
    SmsSendRequest,
    UsageSettingsRequest,
    WechatLoginRequest,
)
from app.core.errors import ApiError
from app.core.security import decode_token
from app.storage.db import create_session_factory

router = APIRouter(prefix="/v1")


def get_session():
    factory = create_session_factory()
    with factory() as session:
        yield session


def get_current_parent(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> ParentUser:
    token = _extract_bearer(authorization)
    try:
        payload = decode_token(token)
    except pyjwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "登录状态无效或已过期") from None
    if payload.get("role") != "parent":
        raise ApiError(401, "UNAUTHORIZED", "需要家长身份")
    user = session.get(ParentUser, payload.get("sub"))
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "家长账号不存在")
    return user


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少登录凭证")
    return authorization.removeprefix("Bearer ").strip()


def _require_self(parent_id: str, current: ParentUser) -> None:
    if parent_id != current.id:
        raise ApiError(403, "FORBIDDEN", "无权操作该家长账号")


# ---------------------------------------------------------------- 登录/登出

@router.post("/auth/parents/login")
def wechat_login(request: WechatLoginRequest, session: Session = Depends(get_session)) -> dict:
    return service.login_with_wechat(session, request.code)


@router.post("/auth/sms/send")
def send_sms(request: SmsSendRequest, session: Session = Depends(get_session)) -> dict:
    return service.send_sms_code(session, request.phone)


@router.post("/auth/parents/login-sms")
def sms_login(request: SmsLoginRequest, session: Session = Depends(get_session)) -> dict:
    return service.login_with_sms(session, request.phone, request.code)


@router.post("/auth/parents/logout")
def logout(_parent: ParentUser = Depends(get_current_parent)) -> dict:
    # 无状态 JWT：客户端丢弃 token 即完成登出；此处仅确认身份有效
    return {"ok": True}


# ---------------------------------------------------------------- 家长资料

@router.get("/parents/me")
def get_me(
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_parent_profile(session, parent.id)


@router.put("/parents/me")
def update_me(
    request: ParentProfileUpdateRequest,
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service.update_parent_profile(session, parent.id, request.nickname)


# ---------------------------------------------------------------- 监护同意

@router.post("/parents/{parent_id}/consents")
def grant_consent(
    parent_id: str,
    request: ConsentGrantRequest,
    current: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    _require_self(parent_id, current)
    return service.set_consent(session, parent_id, request.consent_key)


@router.put("/parents/{parent_id}/consents/{consent_key}")
def grant_consent_put(
    parent_id: str,
    consent_key: str,
    current: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    _require_self(parent_id, current)
    return service.set_consent(session, parent_id, consent_key)


@router.delete("/parents/{parent_id}/consents/{consent_key}")
def withdraw_consent(
    parent_id: str,
    consent_key: str,
    current: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    _require_self(parent_id, current)
    return service.withdraw_consent(session, parent_id, consent_key)


# ---------------------------------------------------------------- 孩子档案

@router.get("/children")
def list_children(
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> list[dict]:
    return service.list_children(session, parent.id)


@router.post("/children", status_code=201)
def create_child(
    request: ChildCreateRequest,
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service.create_child(
        session,
        parent.id,
        request.nickname,
        request.grade,
        request.age_group,
        request.textbook_version,
    )


@router.get("/children/{child_id}")
def get_child(
    child_id: str,
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service._child_summary(service.get_child(session, parent.id, child_id))


@router.put("/children/{child_id}")
def update_child(
    child_id: str,
    request: ChildUpdateRequest,
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service.update_child(
        session,
        parent.id,
        child_id,
        request.nickname,
        request.grade,
        request.age_group,
        request.textbook_version,
    )


@router.delete("/children/{child_id}")
def delete_child(
    child_id: str,
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service.delete_child(session, parent.id, child_id)


# ---------------------------------------------------------------- 时长设置与切换

@router.get("/children/{child_id}/settings")
def get_settings(
    child_id: str,
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_child_settings(session, parent.id, child_id)


@router.put("/children/{child_id}/settings")
def put_settings(
    child_id: str,
    request: UsageSettingsRequest,
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service.put_child_settings(
        session, parent.id, child_id, request.model_dump(exclude_none=True)
    )


@router.post("/children/{child_id}/switch-session")
def switch_session(
    child_id: str,
    parent: ParentUser = Depends(get_current_parent),
    session: Session = Depends(get_session),
) -> dict:
    return service.switch_child_session(session, parent.id, child_id)
