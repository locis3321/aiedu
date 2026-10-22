"""账号域业务逻辑：短信/微信登录、监护同意、孩子档案 CRUD、时长设置、会话切换。

硬约束（AGENTS.md 护栏 + 规格 v2 §2/§6）：
- 缺失必填事实显式失败，不自动挑选默认值；
- 微信身份缺失显式失败，不用模拟账号兜底；
- 未接入渠道显式呈现，不伪造成功；
- 14 岁以下处理需监护同意（建档前置门禁）。
"""

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.accounts.models import (
    ChildProfile,
    ConsentRecord,
    ParentUser,
    SmsVerification,
    UsageSettings,
)
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.runtime_config import get_runtime_setting
from app.core.security import create_child_token, create_parent_token
from app.sms import get_sms_provider

PHONE_RE = re.compile(r"^1\d{10}$")

# 同意项清单：essential=建档前必须 granted；非必要项默认不勾选（规格 §6.1）
ESSENTIAL_CONSENTS = {"guardian_rules", "privacy_notice"}
NONESSENTIAL_CONSENTS = {"companion_ai_notice"}
ALL_CONSENT_KEYS = ESSENTIAL_CONSENTS | NONESSENTIAL_CONSENTS

USAGE_DEFAULTS = {
    "daily_minutes": 30,
    "continuous_minutes": 15,
    "rest_minutes": 5,
    "companion_enabled": True,
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite 返回 naive datetime，统一视为 UTC 后再比较。"""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _hash_code(phone: str, code: str) -> str:
    settings = get_settings()
    digest = hmac.new(
        settings.security_secret_key.encode("utf-8"),
        f"{phone}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest


def _mask_phone(phone: str | None) -> str | None:
    if not phone or len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


# ---------------------------------------------------------------- 短信验证码

def send_sms_code(session: Session, phone: str) -> dict:
    settings = get_settings()
    cooldown = get_runtime_setting(
        "sms_send_cooldown_seconds", settings.sms_send_cooldown_seconds
    )
    max_per_day = get_runtime_setting(
        "sms_max_per_day_per_phone", settings.sms_max_per_day_per_phone
    )
    code_ttl = get_runtime_setting(
        "sms_code_ttl_seconds", settings.sms_code_ttl_seconds
    )
    if not PHONE_RE.match(phone):
        raise ApiError(422, "INVALID_PHONE", "手机号格式不正确")

    now = _utcnow()
    latest = (
        session.query(SmsVerification)
        .filter_by(phone=phone)
        .order_by(SmsVerification.created_at.desc())
        .first()
    )
    if latest and _aware(latest.created_at) is not None:
        elapsed = (now - _aware(latest.created_at)).total_seconds()
        if elapsed < cooldown:
            raise ApiError(
                429,
                "SMS_RATE_LIMITED",
                "发送过于频繁，请稍后再试",
                {"retry_after_seconds": int(cooldown - elapsed)},
            )

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Python 侧统计：避免 aware datetime 与 SQLite naive 列直接比较的方言差异
    sent_today = sum(
        1
        for r in session.query(SmsVerification).filter_by(phone=phone).all()
        if _aware(r.created_at) is not None and _aware(r.created_at) >= day_start
    )
    if sent_today >= max_per_day:
        raise ApiError(
            429,
            "SMS_RATE_LIMITED",
            "该手机号今日发送次数已达上限",
            {"max_per_day": max_per_day},
        )

    provider = get_sms_provider()
    code = (
        settings.sms_dev_fixed_code
        if provider.mode == "dev"
        else f"{secrets.randbelow(1000000):06d}"
    )
    result = provider.send_verification_code(phone, code)
    if not result.sent:
        raise ApiError(
            503,
            "SMS_NOT_CONFIGURED",
            "短信服务未接入：" + (result.note or "未知原因"),
        )

    record = SmsVerification(
        phone=phone,
        code_hash=_hash_code(phone, code),
        mode=result.mode,
        expires_at=now + timedelta(seconds=code_ttl),
    )
    session.add(record)
    session.commit()
    return {
        "mode": result.mode,
        "sent": result.sent,
        "expires_in_seconds": code_ttl,
        "cooldown_seconds": cooldown,
    }


def login_with_sms(session: Session, phone: str, code: str) -> dict:
    settings = get_settings()
    max_attempts = get_runtime_setting("sms_code_max_attempts", settings.sms_code_max_attempts)
    if not PHONE_RE.match(phone):
        raise ApiError(422, "INVALID_PHONE", "手机号格式不正确")

    record = (
        session.query(SmsVerification)
        .filter_by(phone=phone)
        .order_by(SmsVerification.created_at.desc())
        .first()
    )
    now = _utcnow()
    if (
        record is None
        or record.used_at is not None
        or _aware(record.expires_at) < now
        or record.attempts >= max_attempts
    ):
        raise ApiError(401, "INVALID_SMS_CODE", "验证码错误或已过期")

    if record.code_hash != _hash_code(phone, code):
        record.attempts += 1
        if record.attempts >= max_attempts:
            record.used_at = now
        session.commit()
        raise ApiError(401, "INVALID_SMS_CODE", "验证码错误或已过期")

    record.used_at = now
    user = session.query(ParentUser).filter_by(phone=phone).first()
    if user is None:
        user = ParentUser(phone=phone)
        session.add(user)
    user.last_login_at = now
    session.commit()
    return {"token": create_parent_token(user.id), "user": _parent_summary(user)}


def login_with_wechat(session: Session, code: str) -> dict:
    settings = get_settings()
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise ApiError(
            503, "WECHAT_NOT_CONFIGURED", "微信登录未接入：未配置小程序 AppID/AppSecret"
        )
    data = exchange_code2session(
        appid=settings.wechat_app_id,
        secret=settings.wechat_app_secret,
        js_code=code,
    )
    if data.get("errcode"):
        raise ApiError(
            401, "WECHAT_LOGIN_FAILED", f"微信登录失败：{data.get('errmsg', '未知错误')}"
        )
    openid = data.get("openid")
    if not openid:
        raise ApiError(401, "WECHAT_LOGIN_FAILED", "微信登录失败：未返回 openid")
    user = session.query(ParentUser).filter_by(wechat_openid=openid).first()
    if user is None:
        user = ParentUser(wechat_openid=openid)
        session.add(user)
    user.last_login_at = _utcnow()
    session.commit()
    return {"token": create_parent_token(user.id), "user": _parent_summary(user)}


def exchange_code2session(appid: str, secret: str, js_code: str) -> dict:
    """微信 code2session；独立函数便于测试 monkeypatch。"""
    resp = httpx.get(
        "https://api.weixin.qq.com/sns/jscode2session",
        params={
            "appid": appid,
            "secret": secret,
            "js_code": js_code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------- 家长资料

def _parent_summary(user: ParentUser) -> dict:
    return {
        "id": user.id,
        "nickname": user.nickname,
        "phone_masked": _mask_phone(user.phone),
        "wechat_bound": bool(user.wechat_openid),
    }


def get_parent_profile(session: Session, parent_id: str) -> dict:
    user = session.get(ParentUser, parent_id)
    if user is None:
        raise ApiError(404, "PARENT_NOT_FOUND", "家长账号不存在")
    consents = (
        session.query(ConsentRecord)
        .filter_by(parent_id=parent_id)
        .order_by(ConsentRecord.created_at)
        .all()
    )
    children = (
        session.query(ChildProfile)
        .filter_by(parent_id=parent_id)
        .filter(ChildProfile.deleted_at.is_(None))
        .order_by(ChildProfile.created_at)
        .all()
    )
    return {
        **_parent_summary(user),
        "consents": [{"key": c.consent_key, "status": c.status} for c in consents],
        "children": [_child_summary(c) for c in children],
    }


def update_parent_profile(session: Session, parent_id: str, nickname: str | None) -> dict:
    user = session.get(ParentUser, parent_id)
    if user is None:
        raise ApiError(404, "PARENT_NOT_FOUND", "家长账号不存在")
    if nickname is not None:
        user.nickname = nickname.strip() or None
    session.commit()
    return _parent_summary(user)


# ---------------------------------------------------------------- 监护同意

def set_consent(session: Session, parent_id: str, key: str) -> dict:
    _validate_consent_key(key)
    record = (
        session.query(ConsentRecord)
        .filter_by(parent_id=parent_id, consent_key=key)
        .first()
    )
    now = _utcnow()
    if record is None:
        record = ConsentRecord(parent_id=parent_id, consent_key=key)
        session.add(record)
    record.status = "granted"
    record.granted_at = now
    record.withdrawn_at = None
    session.commit()
    return {"key": key, "status": record.status}


def withdraw_consent(session: Session, parent_id: str, key: str) -> dict:
    _validate_consent_key(key)
    record = (
        session.query(ConsentRecord)
        .filter_by(parent_id=parent_id, consent_key=key)
        .first()
    )
    now = _utcnow()
    if record is None:
        record = ConsentRecord(parent_id=parent_id, consent_key=key)
        session.add(record)
    record.status = "withdrawn"
    record.withdrawn_at = now
    session.commit()
    return {"key": key, "status": record.status}


def _validate_consent_key(key: str) -> None:
    if key not in ALL_CONSENT_KEYS:
        raise ApiError(
            422,
            "UNKNOWN_CONSENT_KEY",
            f"未知同意项：{key}",
            {"allowed": sorted(ALL_CONSENT_KEYS)},
        )


def _essential_consents_granted(session: Session, parent_id: str) -> bool:
    rows = (
        session.query(ConsentRecord.consent_key)
        .filter_by(parent_id=parent_id, status="granted")
        .all()
    )
    granted_keys = {row[0] for row in rows}
    return ESSENTIAL_CONSENTS <= granted_keys


# ---------------------------------------------------------------- 孩子档案

def _child_summary(child: ChildProfile) -> dict:
    return {
        "id": child.id,
        "nickname": child.nickname,
        "grade": child.grade,
        "age_group": child.age_group,
        "textbook_version": child.textbook_version,
    }


def create_child(
    session: Session,
    parent_id: str,
    nickname: str,
    grade: str | None,
    age_group: str | None,
    textbook_version: str | None,
) -> dict:
    if not _essential_consents_granted(session, parent_id):
        raise ApiError(
            422,
            "CONSENT_REQUIRED",
            "请先完成监护规则与隐私政策同意后再建档",
            {"required": sorted(ESSENTIAL_CONSENTS)},
        )
    nickname = (nickname or "").strip()
    if not nickname:
        raise ApiError(422, "MISSING_REQUIRED_FACT", "孩子昵称必填")
    if not grade and not age_group:
        raise ApiError(422, "MISSING_REQUIRED_FACT", "年级或年龄段必填其一")
    child = ChildProfile(
        parent_id=parent_id,
        nickname=nickname[:32],
        grade=(grade or "").strip() or None,
        age_group=(age_group or "").strip() or None,
        textbook_version=(textbook_version or "").strip() or None,
    )
    session.add(child)
    session.commit()
    return _child_summary(child)


def list_children(session: Session, parent_id: str) -> list[dict]:
    children = (
        session.query(ChildProfile)
        .filter_by(parent_id=parent_id)
        .filter(ChildProfile.deleted_at.is_(None))
        .order_by(ChildProfile.created_at)
        .all()
    )
    return [_child_summary(c) for c in children]


def get_child(session: Session, parent_id: str, child_id: str) -> ChildProfile:
    child = session.get(ChildProfile, child_id)
    if child is None or child.parent_id != parent_id or child.deleted_at is not None:
        raise ApiError(404, "CHILD_NOT_FOUND", "孩子档案不存在")
    return child


def update_child(
    session: Session,
    parent_id: str,
    child_id: str,
    nickname: str | None,
    grade: str | None,
    age_group: str | None,
    textbook_version: str | None,
) -> dict:
    child = get_child(session, parent_id, child_id)
    if nickname is not None:
        value = nickname.strip()
        if not value:
            raise ApiError(422, "MISSING_REQUIRED_FACT", "孩子昵称必填")
        child.nickname = value[:32]
    if grade is not None:
        child.grade = grade.strip() or None
    if age_group is not None:
        child.age_group = age_group.strip() or None
    if textbook_version is not None:
        child.textbook_version = textbook_version.strip() or None
    if not child.grade and not child.age_group:
        raise ApiError(422, "MISSING_REQUIRED_FACT", "年级或年龄段必填其一")
    session.commit()
    return _child_summary(child)


def delete_child(session: Session, parent_id: str, child_id: str) -> dict:
    """软删标记（§5.3）；关联业务数据清理策略待业务确认，默认保留。"""
    child = get_child(session, parent_id, child_id)
    child.deleted_at = _utcnow()
    session.commit()
    return {"id": child.id, "deleted": True}


# ---------------------------------------------------------------- 时长设置

def get_child_settings(session: Session, parent_id: str, child_id: str) -> dict:
    get_child(session, parent_id, child_id)
    row = session.get(UsageSettings, child_id)
    if row is None:
        return {"child_id": child_id, **USAGE_DEFAULTS}
    return {
        "child_id": row.child_id,
        "daily_minutes": row.daily_minutes,
        "continuous_minutes": row.continuous_minutes,
        "rest_minutes": row.rest_minutes,
        "companion_enabled": row.companion_enabled,
    }


def put_child_settings(
    session: Session,
    parent_id: str,
    child_id: str,
    values: dict,
) -> dict:
    get_child(session, parent_id, child_id)
    row = session.get(UsageSettings, child_id)
    if row is None:
        row = UsageSettings(child_id=child_id)
        session.add(row)
    # 仅更新传入字段；未传字段保持现有值/默认值
    for key in ("daily_minutes", "continuous_minutes", "rest_minutes", "companion_enabled"):
        if values.get(key) is not None:
            setattr(row, key, values[key])
    session.commit()
    return {
        "child_id": row.child_id,
        "daily_minutes": row.daily_minutes,
        "continuous_minutes": row.continuous_minutes,
        "rest_minutes": row.rest_minutes,
        "companion_enabled": row.companion_enabled,
    }


# ---------------------------------------------------------------- 会话切换

def switch_child_session(session: Session, parent_id: str, child_id: str) -> dict:
    """家长为孩子签发 child-scoped token（规格 v2 §4.3：只能访问自己孩子域数据）。"""
    get_child(session, parent_id, child_id)
    return {"token": create_child_token(child_id, child_id), "child_id": child_id}
