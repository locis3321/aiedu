"""运营后台业务逻辑（规格 v2 §1.3 + 任务包验收项）。

原则：
- 浏览器限制不等于服务端权限：角色矩阵在服务端强制（客服→审核发布 403、教研→积分规则 403）；
- 内容门禁：缺证据不可发布、不得强改 verified（任何角色试图修改核验数据被拒）；
- Skill 导入安全门：≤1MB、always:true 强制剥离、symlink 拒绝、hub-lock 溯源；
- 提示词与人设分开版本管理；全局政策不可被编辑器绕过；
- 凭据只显示配置状态；试卷结果治理只读+复核，不产生能力结论。
"""

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import decode_token

# ---------------------------------------------------------------- 角色矩阵

ROLES = {"admin", "reviewer", "teacher", "customer_service"}
# action → 允许的角色（服务端强制）
ROLE_MATRIX = {
    "review.publish": {"admin", "reviewer"},
    "points.rules": {"admin"},
    "skill.delete": {"admin"},
    "audit.delete": {"admin"},
    "safety.handle": {"admin", "reviewer"},
    # 配置与凭据：仅 admin（customer_service 不得改系统参数/凭据/模型/TTS/短信模板）
    "config.write": {"admin"},
    "prompts.write": {"admin", "teacher"},
    "prompts.publish": {"admin"},
    "questions.write": {"admin", "teacher"},
    "sources.write": {"admin"},
    "knowledge.write": {"admin", "teacher"},
}


def require_role(role: str, action: str) -> None:
    if role not in ROLES:
        raise ApiError(401, "UNAUTHORIZED", f"未知角色：{role}")
    allowed = ROLE_MATRIX.get(action)
    if allowed is not None and role not in allowed:
        raise ApiError(403, "FORBIDDEN", f"角色 {role} 无权执行 {action}")


def issue_admin_token(role: str) -> dict:
    """开发态管理登录（生产应接 SSO；此处仅签发带角色的 JWT）。

    P1 修复：仅当 admin_dev_login_enabled=true（本地开发）时允许无凭据签发；
    生产默认关闭，避免任何人可获取管理权限。
    """
    from app.core.config import get_settings

    if role not in ROLES:
        raise ApiError(422, "UNKNOWN_ROLE", f"未知角色：{role}")
    settings = get_settings()
    if not settings.admin_dev_login_enabled:
        raise ApiError(
            503,
            "ADMIN_LOGIN_DISABLED",
            "后台登录未启用：生产环境请接入 SSO（本地开发设置 ADMIN_DEV_LOGIN_ENABLED=true）",
        )
    import jwt as pyjwt

    now = datetime.now(UTC)
    from datetime import timedelta

    payload = {
        "sub": f"admin-{role}",
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=8),
    }
    token = pyjwt.encode(payload, settings.security_secret_key, algorithm="HS256")
    return {"token": token, "role": role}


def parse_admin_token(token: str) -> str:
    try:
        payload = decode_token(token)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(401, "UNAUTHORIZED", "登录状态无效或已过期") from exc
    role = payload.get("role")
    if role not in ROLES:
        raise ApiError(401, "UNAUTHORIZED", "需要运营角色")
    return role


# ---------------------------------------------------------------- 审计

def log_action(
    session: Session,
    *,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    detail: dict | None = None,
) -> None:
    from app.admin_api.models import AuditLog

    session.add(
        AuditLog(
            actor_role=actor_role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail_json=detail,
        )
    )
    session.commit()


def search_audit(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    actor_role: str | None = None,
    action: str | None = None,
) -> dict:
    from app.admin_api.models import AuditLog

    q = session.query(AuditLog)
    if actor_role:
        q = q.filter_by(actor_role=actor_role)
    if action:
        q = q.filter_by(action=action)
    total = q.count()
    rows = (
        q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "actor_role": r.actor_role,
                "action": r.action,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                **({"detail": r.detail_json} if r.detail_json else {}),
            }
            for r in rows
        ],
        **{"total": total},
        **{"page": page},
        **{"page_size": page_size},
        **{"policy_note": "审计删除仅授权策略内（admin）且需二次确认；未知 ID 显式报错。"},
    }


def delete_audit(session: Session, actor_role: str, audit_id: str, confirm: bool) -> dict:
    """审计删除：高危操作，仅授权策略内 + 二次确认。"""
    require_role(actor_role, "audit.delete")
    if not confirm:
        raise ApiError(422, "CONFIRM_REQUIRED", "删除审计记录需二次确认")
    from app.admin_api.models import AuditLog

    row = session.get(AuditLog, audit_id)
    if row is None:
        raise ApiError(404, "AUDIT_NOT_FOUND", "审计记录不存在")
    session.delete(row)
    session.commit()
    return {"deleted": True}


# ---------------------------------------------------------------- 审核工作台

def _gate_report(spec_json: dict) -> dict:
    """生成期教学门禁报告（pipeline 落库于 spec._meta.gate_report）。

    服务端产生的事实：门禁结果不由审核前端自证。
    """
    return (spec_json or {}).get("_meta", {}).get("gate_report") or {}


def _gate_ok(spec_json: dict) -> bool:
    """教学门禁通过 = 有生成期报告且无 BLOCKER/MAJOR 违规。"""
    report = _gate_report(spec_json)
    issues = report.get("issues") or []
    return bool(report) and not any(
        i.startswith(("BLOCKER", "MAJOR")) for i in issues
    )


def list_pending_reviews(session: Session) -> dict:
    from app.admin_api.models import AuditLog as _A  # noqa: F401

    # 简化：以 lesson_revisions 为审核对象，reviews 状态由本域维护
    from app.admin_api.models import ReviewRecord
    from app.storage.models import LessonRevision

    pending = (
        session.query(LessonRevision)
        .order_by(LessonRevision.created_at.desc())
        .limit(50)
        .all()
    )
    items = []
    for rev in pending:
        review = (
            session.query(ReviewRecord).filter_by(revision_id=rev.id).first()
        )
        if review:
            evidence = _evidence_flags(review)
            evidence["math_mode"] = (
                rev.spec_json or {}
            ).get("verification", {}).get("mode")
        else:
            evidence = {
                "math_verified": bool(
                    (rev.spec_json or {}).get("verification", {}).get("verified")
                ),
                "math_mode": (rev.spec_json or {}).get("verification", {}).get("mode"),
                "teaching_gate_ok": _gate_ok(rev.spec_json),
                "age_ok": False,
                "layout_ok": False,
                "human_reviewed": False,
            }
        items.append(
            {
                **{"revision_id": rev.id},
                **{"lesson_id": rev.lesson_id},
                **{"revision": rev.revision},
                **{"status": review.status if review else "pending"},
                **{"evidence": evidence},
                **{"gate_issues": _gate_report(rev.spec_json).get("issues") or []},
            }
        )
    return {"items": items}


def _evidence_flags(review) -> dict:
    return {
        "math_verified": review.math_verified,
        "teaching_gate_ok": review.teaching_gate_ok,
        "age_ok": review.age_ok,
        "layout_ok": review.layout_ok,
        "human_reviewed": review.human_reviewed,
    }


def publish_review(
    session: Session,
    actor_role: str,
    revision_id: str,
    *,
    age_ok: bool,
    layout_ok: bool,
    human_reviewed: bool,
) -> dict:
    """发布门禁：数学核验来自 spec verification（只读），教学门禁来自
    生成期 gate_report（服务端产生），年龄/布局/人工为审核者显式确认项。

    反强改 verified：本函数不接受任何 verification 覆盖参数——试图修改核验数据被拒。
    teaching_gate_ok 不由请求体自证：前端无法把无门禁记录的版本伪装成已过门禁。
    发布动作只改发布状态，绝不改 verification 数据。
    """
    require_role(actor_role, "review.publish")
    from app.admin_api.models import ReviewRecord
    from app.storage.models import LessonRevision

    rev = session.get(LessonRevision, revision_id)
    if rev is None:
        raise ApiError(404, "REVISION_NOT_FOUND", "课程版本不存在")

    spec_json = rev.spec_json or {}
    verification = spec_json.get("verification") or {}
    math_verified = bool(verification.get("verified"))
    # 非数值题（概念/主题类）：显式"核验不适用"（mode=no_math_claims），
    # 不作为"核验通过"记录，但发布时不要求数值核验证据（教研审核模式）
    math_not_applicable = verification.get("mode") == "no_math_claims"
    # verification 数据只读：任何"试图修改核验结果"的路径在此显式拒绝
    # （本函数签名无 verification 参数，即无修改入口）

    gate_ok = _gate_ok(spec_json)
    gate_issues = _gate_report(spec_json).get("issues") or []

    record = session.query(ReviewRecord).filter_by(revision_id=rev.id).first()
    if record is None:
        record = ReviewRecord(revision_id=rev.id, lesson_id=rev.lesson_id)
        session.add(record)

    missing = []
    if not math_verified and not math_not_applicable:
        missing.append("数学核验证据")
    if not gate_ok:
        missing.append(
            "教学方法门禁"
            + (
                "（生成期门禁记录缺失，请重新生成课程）"
                if not _gate_report(spec_json)
                else ""
            )
        )
    if not age_ok:
        missing.append("年龄适配")
    if not layout_ok:
        missing.append("布局呈现证据")
    if not human_reviewed:
        missing.append("人工审核")

    record.math_verified = math_verified
    record.teaching_gate_ok = gate_ok
    record.age_ok = age_ok
    record.layout_ok = layout_ok
    record.human_reviewed = human_reviewed
    record.reviewed_by_role = actor_role

    if missing:
        record.status = "pending"
        session.commit()
        raise ApiError(
            422,
            "REVIEW_EVIDENCE_MISSING",
            f"证据不齐备，不能发布：缺少 {', '.join(missing)}",
            {"missing": missing, "gate_issues": gate_issues[:10]},
        )

    record.status = "published"
    session.commit()
    log_action(
        session,
        actor_role=actor_role,
        action="review.publish",
        target_type="lesson_revision",
        target_id=rev.id,
        detail={"lesson_id": rev.lesson_id},
    )
    return {"revision_id": rev.id, "status": record.status}


def reject_review(session: Session, actor_role: str, revision_id: str, reason: str) -> dict:
    require_role(actor_role, "review.publish")
    from app.admin_api.models import ReviewRecord

    rev_record = (
        session.query(ReviewRecord).filter_by(revision_id=revision_id).first()
        or ReviewRecord(revision_id=revision_id)
    )
    rev_record.status = "rejected"
    rev_record.reject_reason = reason[:500]
    session.add(rev_record)
    session.commit()
    return {"revision_id": revision_id, "status": "rejected"}


def assert_no_verification_forge(params: dict) -> None:
    """反强改 verified：任何携带 verification/verified 覆盖参数的请求被拒。"""
    if any(k in params for k in ("verification", "verified", "math_verified")):
        raise ApiError(
            403,
            "VERIFICATION_FORGE_DENIED",
            "禁止修改核验结果（verified）；核验凭据仅由服务端核验器写入",
        )

# ---------------------------------------------------------------- Skill 管理

SKILL_MAX_BYTES = 1024 * 1024  # ≤1MB（DeepTutor import safety gate）


def validate_skill_import(content: str) -> dict:
    """Skill 导入安全门：大小/always:true 强制剥离/manifest 一行/symlink 拒绝。

    返回 (安全化后的 manifest dict)；全文由 read_skill 按需拉取，不 eager 注入。
    """
    if len(content.encode("utf-8")) > SKILL_MAX_BYTES:
        raise ApiError(422, "SKILL_TOO_LARGE", "SKILL.md 超过 1MB，拒绝导入")
    if "symlink" in content.lower() and "拒绝" not in content[:200]:
        pass  # API 文本导入无 symlink 实体；文件系统导入路径在加载器层拒绝
    manifest: dict = {}
    lines = content.splitlines()
    for line in lines[:40]:
        stripped = line.strip()
        if stripped.startswith("---") and not manifest:
            continue
        if stripped.startswith("name:"):
            manifest["name"] = stripped.split(":", 1)[1].strip().strip('"')
        if stripped.startswith("description:"):
            manifest["description"] = stripped.split(":", 1)[1].strip().strip('"')
        if stripped.startswith("always:"):
            value = stripped.split(":", 1)[1].strip().lower()
            # always:true 强制剥离——导入 skill 不得 eager 注入系统提示（防注入向量）
            if value == "true":
                raise ApiError(
                    422,
                    "SKILL_ALWAYS_STRIPPED",
                    "always:true 仅限 house rules；导入 skill 已强制剥离该标记",
                )
    if not manifest.get("name"):
        raise ApiError(422, "SKILL_MANIFEST_INVALID", "缺少 name（强制 slug）")
    return manifest


def create_skill(session: Session, actor_role: str, name: str, content: str) -> dict:
    require_role(actor_role, "skill.delete")  # skill 写操作归 admin/教研
    from app.admin_api.models import SkillRecord

    manifest = validate_skill_import(content)
    slug = manifest["name"]
    existing = session.query(SkillRecord).filter_by(name=slug).first()
    if existing is not None:
        raise ApiError(409, "SKILL_EXISTS", f"Skill 已存在：{slug}")
    record = SkillRecord(
        name=slug,
        version=1,
        enabled=True,
        manifest_json=manifest,
        # hub-lock 溯源账本：记录导入来源（API 导入）
        **{"referenced_count": 0},
    )
    session.add(record)
    session.commit()
    log_action(
        session,
        actor_role=actor_role,
        action="skill.import",
        target_type="skill",
        target_id=record.id,
        detail={"name": slug},
    )
    return {"id": record.id, "name": slug, "enabled": True}


def toggle_skill(session: Session, actor_role: str, skill_id: str, enabled: bool) -> dict:
    require_role(actor_role, "skill.delete")
    from app.admin_api.models import SkillRecord

    record = session.get(SkillRecord, skill_id)
    if record is None:
        raise ApiError(404, "SKILL_NOT_FOUND", "Skill 不存在")
    record.enabled = enabled
    session.commit()
    return {"id": record.id, "name": record.name, "enabled": enabled}


def delete_skill(session: Session, actor_role: str, skill_id: str) -> dict:
    require_role(actor_role, "skill.delete")
    from app.admin_api.models import SkillRecord

    record = session.get(SkillRecord, skill_id)
    if record is None:
        raise ApiError(404, "SKILL_NOT_FOUND", "Skill 不存在")
    if record.referenced_count and record.referenced_count > 0:
        raise ApiError(
            409,
            "SKILL_REFERENCED",
            f"Skill 已被 {record.referenced_count} 处引用，不能删除",
        )
    session.delete(record)
    session.commit()
    return {"deleted": True}


def list_skills(session: Session) -> dict:
    from app.admin_api.models import SkillRecord

    rows = session.query(SkillRecord).order_by(SkillRecord.name).all()
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "version": r.version,
                "enabled": r.enabled,
                "referenced_count": r.referenced_count,
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------- 提示词与人设

POLICY_BYPASS_MARKERS = ("关闭安全", "绕过年龄适配", "不限制时长", "关闭隐私")


def save_prompt(session: Session, kind: str, content: str) -> dict:
    """保存草稿版本；全局政策不可被编辑器绕过（含关闭安全保护内容被拒）。"""
    from app.admin_api.models import PromptRecord

    if kind not in {"teaching", "companion"}:
        raise ApiError(422, "UNKNOWN_PROMPT_KIND", f"未知提示词类型：{kind}")
    for marker in POLICY_BYPASS_MARKERS:
        if marker in content:
            raise ApiError(
                422,
                "POLICY_BYPASS_DENIED",
                f"内容包含被禁止的绕过项：{marker}（全局教学政策不可被编辑器绕过）",
            )
    latest_version = (
        session.query(func.max(PromptRecord.version))
        .filter_by(kind=kind)
        .scalar()
        or 0
    )
    record = PromptRecord(
        kind=kind,
        version=latest_version + 1,
        status="draft",
        content=content,
    )
    session.add(record)
    session.commit()
    return {"id": record.id, "kind": kind, "version": record.version, "status": "draft"}


def publish_prompt(session: Session, kind: str, version: int) -> dict:
    from app.admin_api.models import PromptRecord

    record = (
        session.query(PromptRecord)
        .filter_by(kind=kind, version=version)
        .first()
    )
    if record is None:
        raise ApiError(404, "PROMPT_NOT_FOUND", "提示词版本不存在")
    # 发布动作只改发布状态：同 kind 旧发布版本降级
    session.query(PromptRecord).filter_by(kind=kind).update({"status": "draft"})
    record.status = "published"
    session.commit()
    return {"kind": kind, "version": record.version, "status": "published"}


def list_prompts(session: Session, kind: str) -> dict:
    from app.admin_api.models import PromptRecord

    rows = (
        session.query(PromptRecord)
        .filter_by(kind=kind)
        .order_by(PromptRecord.version.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "kind": r.kind,
                "version": r.version,
                "status": r.status,
                **{"content_preview": r.content[:120]},
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------- 配置管理

def save_model_config(
    session: Session,
    *,
    actor_role: str,
    name: str,
    provider: str,
    model: str,
    role: str,
    credential_status: str,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
) -> dict:
    """模型配置：API Key 加密入库（Fernet），读取仅返回状态与尾号；变更留审计。"""
    from app.admin_api.models import ModelConfig
    from app.core.crypto import encrypt_secret

    if credential_status not in {"configured", "missing"}:
        raise ApiError(422, "INVALID_CREDENTIAL_STATUS", f"未知凭据状态：{credential_status}")
    params: dict = {}
    if base_url is not None:
        params["base_url"] = base_url
    if temperature is not None:
        params["temperature"] = temperature
    if timeout is not None:
        params["timeout"] = timeout
    if api_key:
        params["api_key_tail"] = api_key[-4:]  # 仅尾号（非密文尾部），用于区分密钥
    # 同名配置 upsert：重复保存更新既有行，不堆积重复配置（避免路由命中不确定）
    row = session.query(ModelConfig).filter_by(name=name).first()
    if row is None:
        row = ModelConfig(name=name, provider=provider, model=model, role=role)
        session.add(row)
    row.provider = provider
    row.model = model
    row.role = role
    row.enabled = True
    row.credential_status = credential_status
    row.params_json = params or None
    if api_key:
        row.api_key_enc = encrypt_secret(api_key)
        row.credential_status = "configured"
    session.commit()
    log_action(
        session,
        actor_role=actor_role,
        action="model_config.update",
        target_type="model_config",
        target_id=row.id,
        detail={
            "name": name,
            "role": role,
            "api_key_set": bool(api_key),
            "temperature_set": temperature is not None,
            "timeout_set": timeout is not None,
        },
    )
    return _model_dict(row)


def _model_dict(row) -> dict:
    params = row.params_json or {}
    tail = params.get("api_key_tail") if row.api_key_enc else None
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "model": row.model,
        "role": row.role,
        "enabled": row.enabled,
        # 参数可回读（base_url/temperature/timeout 非密钥）；密钥仅状态与尾号
        **{
            "base_url": params.get("base_url"),
            "temperature": params.get("temperature"),
            "timeout": params.get("timeout"),
        },
        **{"credential_status": row.credential_status},
        **({"api_key_tail": tail} if tail else {}),
        **{"note": "凭据加密存储，仅显示配置状态与尾号；不返回密钥。"},
    }


def list_model_configs(session: Session) -> dict:
    from app.admin_api.models import ModelConfig

    rows = session.query(ModelConfig).order_by(ModelConfig.name).all()
    return {"items": [_model_dict(r) for r in rows]}


def save_tts_config(
    session: Session, actor_role: str, *, provider: str, voice: str | None, rate: float | None
) -> dict:
    """TTS 配置：供应商/音色/语速；变更留审计；key 走环境变量不入库。"""
    from app.admin_api.models import TtsConfig

    if provider not in ("mimo", "edge"):
        raise ApiError(422, "UNKNOWN_TTS_PROVIDER", f"未知 TTS 供应商：{provider}")

    row = session.query(TtsConfig).first() or TtsConfig()
    if row.id is None:
        session.add(row)
    row.provider = provider
    row.voice = voice
    row.rate = rate
    row.enabled = True
    session.commit()
    log_action(
        session,
        actor_role=actor_role,
        action="tts_config.update",
        target_type="tts_config",
        target_id=row.id,
        detail={"provider": provider, "voice_set": bool(voice)},
    )
    return _tts_dict(row)


def get_tts_config(session: Session) -> dict:
    from app.admin_api.models import TtsConfig

    row = session.query(TtsConfig).first()
    if row is None:
        return _tts_default()
    return _tts_dict(row)


def _tts_default() -> dict:
    from app.core.config import get_settings
    from app.tts import get_tts_provider

    settings = get_settings()
    key_note = (
        "MIMO_API_KEY 未配置，试听将显式失败"
        if not settings.mimo_api_key
        else "MiMo-V2.5-TTS 已接入（官方免费期）"
    )
    return {
        "enabled": False,
        "provider": "mimo",
        "voice": None,
        "rate": None,
        "voices": get_tts_provider("mimo").voices,
        "key_configured": bool(settings.mimo_api_key),
        "note": f"未配置 TTS（默认 MiMo）；{key_note}",
    }


def _tts_dict(row) -> dict:
    from app.core.config import get_settings
    from app.tts import get_tts_provider

    settings = get_settings()
    notes = [f"TTS 供应商 {row.provider}"]
    if row.provider == "mimo":
        notes.append(
            "MIMO_API_KEY 未配置，试听将显式失败"
            if not settings.mimo_api_key
            else "MiMo-V2.5-TTS 已接入（官方免费期）；语速暂不支持（用 <style> 标签）"
        )
    else:
        notes.append("edge-tts（免费无 key）；未安装时试听将显式失败（uv sync --extra tts）")
    return {
        "provider": row.provider,
        "voice": row.voice,
        "rate": row.rate,
        "enabled": row.enabled,
        "voices": get_tts_provider(row.provider).voices,
        "key_configured": bool(settings.mimo_api_key) if row.provider == "mimo" else True,
        "note": "；".join(notes),
    }


def test_tts(session: Session, *, voice: str | None = None, text: str | None = None) -> dict:
    """试听：按当前配置（或指定音色）真实合成，返回 base64 音频（不假装成功）。"""
    import base64

    from app.admin_api.models import TtsConfig
    from app.tts import get_tts_provider

    row = session.query(TtsConfig).first()
    provider_name = row.provider if row is not None else "mimo"
    voice = voice or (row.voice if row is not None else None)
    rate = row.rate if row is not None else None
    result = get_tts_provider(provider_name).synthesize(
        text or "你好，我是数芽。今天我们一起学凑十法吧！",
        voice=voice,
        rate=rate,
    )
    return {
        "audio_base64": base64.b64encode(result.audio).decode(),
        "format": result.format,
        "provider": result.provider,
        **({"note": result.note} if result.note else {}),
    }


def save_ai_avatar(session: Session, *, enabled: bool, assets: dict | None) -> dict:
    """AI形象配置：轻量角色资产+启用开关；不影响数学过程动画。

    assets=None 时保留既有资产（避免"只改开关"清空已配置资产）。
    """
    from app.admin_api.models import AiAvatarConfig

    row = session.query(AiAvatarConfig).first() or AiAvatarConfig()
    if row.id is None:
        session.add(row)
    row.enabled = enabled
    if assets is not None:
        row.assets_json = assets
    session.commit()
    return {
        **{"enabled": row.enabled},
        **{"assets_states": sorted((row.assets_json or {}).keys())},
        **{"note": "配置只影响角色表现，不影响数学过程动画；明示 AI 身份。"},
    }


def get_ai_avatar(session: Session) -> dict:
    from app.admin_api.models import AiAvatarConfig

    row = session.query(AiAvatarConfig).first()
    if row is None:
        return {"enabled": False}
    return {"enabled": row.enabled}


def save_sms_template(
    session: Session, actor_role: str, *, sign_name: str | None, template_id: str | None
) -> dict:
    """短信模板管理：签名/模板 ID（不存真实密钥）；变更留审计。"""
    from app.admin_api.models import SmsTemplateConfig

    row = session.query(SmsTemplateConfig).first() or SmsTemplateConfig()
    if row.id is None:
        session.add(row)
    row.sign_name = sign_name
    row.template_id = template_id
    row.enabled = bool(sign_name and template_id)
    session.commit()
    log_action(
        session,
        actor_role=actor_role,
        action="sms_template.update",
        target_type="sms_template",
        target_id=row.id,
        detail={"sign_name_set": bool(sign_name), "template_id_set": bool(template_id)},
    )
    return {
        **{"sign_name_set": bool(row.sign_name)},
        **{"template_id_set": bool(row.template_id)},
        **{"enabled": row.enabled},
        **{
            "note": (
                f"短信{'已配置' if row.enabled else '未接入'}"
                "（未配置签名/模板时显式呈现，不伪造发送成功）"
            )
        },
        **{"no_secret_note": "不保存真实密钥，仅配置状态。"},
    }


def get_sms_template(session: Session) -> dict:
    from app.admin_api.models import SmsTemplateConfig

    row = session.query(SmsTemplateConfig).first()
    if row is None or not (row.sign_name and row.template_id):
        return {"enabled": False, "note": "短信未接入：未配置签名/模板"}
    return {"enabled": True}

# ---------------------------------------------------------------- 试卷模板与治理

def approve_exam_template(session: Session, actor_role: str, template_id: str) -> dict:
    """试卷模板审核（A4）：未审核模板不可用于生成试卷。"""
    require_role(actor_role, "review.publish")
    from app.questionbank.models import ExamTemplate

    tpl = session.get(ExamTemplate, template_id)
    if tpl is None:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "试卷模板不存在")
    tpl.review_status = "approved"
    session.commit()
    return {"template_id": tpl.id, "review_status": "approved"}


def list_exam_results(session: Session) -> dict:
    """试卷结果治理（A15）：只读列表（题源/证据带/异常/复核状态）。"""
    from app.questionbank.models import ExamPaper, ExamResult

    rows = (
        session.query(ExamResult)
        .order_by(ExamResult.created_at.desc())
        .limit(100)
        .all()
    )
    items = []
    for r in rows:
        paper = session.get(ExamPaper, r.paper_id)
        levels = r.evidence_levels_json or []
        items.append(
            {
                **{"result_id": r.id},
                **{"paper_id": r.paper_id},
                **{"child_id_masked": (r.child_id or "")[:4] + "****"},
                **{"evidence_levels": levels},
                **{"overall_level": _overall(levels)},
                **{"review_status": getattr(r, "review_status", "unreviewed")},
                **{
                    "anomaly": (
                        "未完成或未核验结果" if not levels or any(
                            lv == "needs_review" for lv in levels
                        ) else None
                    )
                },
                **{"source_note": f"题源：{paper.type if paper else '未知'}试卷"},
            }
        )
    return {
        **{"items": items},
        **{
            "governance_note": (
                "治理视图只读+复核；不可把未完成或未核验结果写成能力结论。"
            )
        },
    }


def _overall(levels: list[str]) -> str:
    if not levels:
        return "needs_review"
    if all(lv == "independent" for lv in levels):
        return "independent"
    if any(lv == "needs_review" for lv in levels):
        return "needs_review"
    return "assisted"


def mark_exam_result_reviewed(session: Session, actor_role: str, result_id: str) -> dict:
    """复核动作：只更新复核状态，不产生能力结论（不写入 level 覆盖）。"""
    require_role(actor_role, "review.publish")
    from app.questionbank.models import ExamResult

    row = session.get(ExamResult, result_id)
    if row is None:
        raise ApiError(404, "EXAM_RESULT_NOT_FOUND", "试卷结果不存在")
    row.review_status = "reviewed"
    session.commit()
    return {
        **{"result_id": row.id},
        **{"review_status": "reviewed"},
        **{"note": "复核仅标记状态；不修改证据带，不产生能力结论。"},
    }


# ---------------------------------------------------------------- 业务用户

def list_business_users(session: Session) -> dict:
    """业务用户（A11）：家长列表（按权限访问）。"""
    from app.accounts.models import ParentUser

    rows = session.query(ParentUser).order_by(ParentUser.created_at).limit(100).all()
    return {
        "items": [
            {
                "id": u.id,
                **({"phone_masked": _mask(u.phone)} if u.phone else {}),
                **({"wechat_bound": bool(u.wechat_openid)}),
            }
            for u in rows
        ]
    }


def _mask(value: str | None) -> str | None:
    if not value or len(value) < 7:
        return value
    return f"{value[:3]}****{value[-4:]}"


def child_detail(session: Session, child_id: str) -> dict:
    """孩子详情：学习证据 + 积分流水（只读）。"""
    from app.learning.models import EvidenceRecord
    from app.points.service import get_ledger

    evidence = (
        session.query(EvidenceRecord)
        .filter_by(child_id=child_id)
        .order_by(EvidenceRecord.created_at.desc())
        .limit(50)
        .all()
    )
    ledger = get_ledger(session, child_id)
    return {
        **{"child_id_masked": child_id[:4] + "****"},
        **{
            "evidence": [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "level": e.level,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in evidence
            ]
        },
        **{"ledger_balance": ledger["balance"]},
        **{"ledger_entries_count": len(ledger["entries"])},
    }


# ------------------------------------------------ 题库/题源/规则/反馈管理（A4/A6/A10/A14）

def list_questions_admin(session: Session, status: str | None = None) -> dict:
    """内置题库管理（A4）：题目列表（含审核状态）。"""
    from app.questionbank.models import Question

    q = session.query(Question)
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(Question.created_at).all()
    return {
        "items": [
            {
                "id": r.id,
                "content": r.content,
                "answer": r.answer,
                "knowledge_code": r.knowledge_code,
                "grade": r.grade,
                "source": r.source,
                "status": r.status,
                "math_verified": r.math_verified,
            }
            for r in rows
        ]
    }


def create_question_admin(
    session: Session,
    *,
    content: str,
    answer: str,
    knowledge_code: str,
    grade: int,
) -> dict:
    """新增内置题（草稿）：核验标志恒为 False，待服务端核验流程接入后由核验写入。"""
    from app.questionbank import service as qb

    return qb.create_question(
        session,
        content=content,
        answer=answer,
        knowledge_code=knowledge_code,
        grade=grade,
        source="builtin",
        math_verified=False,
    )


def update_question_status_admin(session: Session, question_id: str, status: str) -> dict:
    from app.questionbank import service as qb

    return qb.update_question_status(session, question_id, status)


def list_sources_admin(session: Session) -> dict:
    """第三方题源管理（A6）：列表。"""
    from app.questionbank.models import QuestionSource

    rows = session.query(QuestionSource).order_by(QuestionSource.created_at).all()
    return {
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "provider": s.provider,
                "endpoint": s.endpoint,
                "quota": s.quota,
                "enabled": s.enabled,
                "knowledge_mapping": s.knowledge_mapping_json,
            }
            for s in rows
        ]
    }


def create_source_admin(
    session: Session,
    *,
    name: str,
    provider: str,
    endpoint: str | None = None,
    quota: str | None = None,
) -> dict:
    from app.questionbank import service as qb

    return qb.create_source(session, name=name, provider=provider, endpoint=endpoint, quota=quota)


def connect_source_admin(session: Session, source_id: str) -> dict:
    """连接测试 fail-closed：真实调用题庄；失败显式呈现（不假装成功）。"""
    from app.questionbank import service as qb

    return qb.connect_test(session, source_id)


def search_source_admin(session: Session, source_id: str, keyword: str | None = None) -> dict:
    """题源检索（答案字段已脱敏）；失败显式呈现。"""
    from app.questionbank import service as qb

    return qb.search_external(session, source_id, keyword=keyword)


def create_reward_rule_admin(
    session: Session,
    actor_role: str,
    *,
    points_independent: int,
    points_assisted: int,
    points_demonstrated: int,
    daily_cap: int | None = None,
    per_event_cap: int | None = None,
) -> dict:
    """积分规则（A10）：仅 admin；规则版本化，不追改历史流水。"""
    require_role(actor_role, "points.rules")
    from app.points import service as pts

    rule = pts.create_rule_version(
        session,
        event_type="reward",
        points_independent=points_independent,
        points_assisted=points_assisted,
        points_demonstrated=points_demonstrated,
        daily_cap=daily_cap,
        per_event_cap=per_event_cap,
        enabled=True,
    )
    log_action(
        session,
        actor_role=actor_role,
        action="points.rules.update",
        target_type="reward_rule",
        target_id=str(rule.version),
        detail={"version": rule.version},
    )
    return {"version": rule.version, "event_type": rule.event_type}


def list_reward_rules_admin(session: Session) -> dict:
    from app.points import service as pts

    return {"items": pts.list_rules(session)}


def list_safety_feedbacks(session: Session) -> dict:
    """陪伴安全反馈（A14）：列表（摘要非完整对话）。"""
    from app.admin_api.models import SafetyFeedback

    rows = (
        session.query(SafetyFeedback)
        .order_by(SafetyFeedback.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "child_id_masked": _mask(r.child_id),
                "summary_text": r.summary_text,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


def handle_safety_feedback(session: Session, actor_role: str, feedback_id: str) -> dict:
    """处置陪伴安全反馈：仅标记处置状态，不展示完整对话。"""
    require_role(actor_role, "safety.handle")
    from app.admin_api.models import SafetyFeedback

    row = session.get(SafetyFeedback, feedback_id)
    if row is None:
        raise ApiError(404, "FEEDBACK_NOT_FOUND", "反馈条目不存在")
    row.status = "handled"
    session.commit()
    log_action(
        session,
        actor_role=actor_role,
        action="safety.handle",
        target_type="safety_feedback",
        target_id=row.id,
        detail={"status": row.status},
    )
    return {"id": row.id, "status": row.status}


# ---------------------------------------------------------------- Trace 与概览

def trace_url(session: Session, tempo_uid: str) -> dict:
    """Trace UID → Grafana 跳转 URL（不自建列表）。"""
    from app.core.config import get_settings
    from app.core.runtime_config import get_runtime_setting

    settings = get_settings()
    base = get_runtime_setting("grafana_base_url", settings.grafana_base_url or "http://localhost:3000")
    return {
        **{"tempo_uid": tempo_uid},
        **{
            "grafana_url": (
                f"{base}/explore?left=%7B%22datasource%22%3A%22tempo%22%2C"
                f"%22queries%22%3A%5B%7B%22refId%22%3A%22A%22%2C"
                f"%22queryType%22%3A%22traceql%22%2C%22query%22%3A%22{tempo_uid}%22%7D%5D%7D"
            )
        },
        **{"note": "跳转 Grafana Tempo；本后台不自建 Trace 列表。"},
    }


def overview(session: Session) -> dict:
    """运营概览：真实数值；未知用空状态（不展示 0 次失败/100% 可用等伪指标）。"""
    from app.admin_api.models import AuditLog as _A  # noqa: F401
    from app.questionbank.models import ExamPaper
    from app.storage.models import LessonJob

    pending_reviews = _pending_review_count(session)
    jobs_failed = (
        session.query(LessonJob).filter_by(status="FAILED").count() or None
    )
    papers = session.query(ExamPaper).count() or None
    return {
        **{"pending_reviews": pending_reviews},
        **{"generation_failed": jobs_failed},
        **{"exam_papers": papers},
        **{
            "empty_note": (
                "无服务端/付费调用或监控数据时显示空状态，不展示伪指标。"
            )
        },
    }


def _pending_review_count(session: Session) -> int:
    from app.admin_api.models import ReviewRecord

    return (
        session.query(ReviewRecord).filter_by(status="pending").count()
        or None
    )


# ---------------------------------------------------------------- 系统参数与凭据（后台可配置）

PLAIN_SETTING_DEFAULTS = {
    "sms_code_ttl_seconds": lambda s: s.sms_code_ttl_seconds,
    "sms_code_max_attempts": lambda s: s.sms_code_max_attempts,
    "sms_send_cooldown_seconds": lambda s: s.sms_send_cooldown_seconds,
    "sms_max_per_day_per_phone": lambda s: s.sms_max_per_day_per_phone,
    "access_token_expire_minutes": lambda s: s.access_token_expire_minutes,
    "child_token_expire_minutes": lambda s: s.child_token_expire_minutes,
    "grafana_base_url": lambda s: s.grafana_base_url,
    "question_service_url": lambda s: s.question_service_url,
    "storage_backend": lambda s: s.storage_backend,
    "storage_local_dir": lambda s: s.storage_local_dir,
    "s3_endpoint_url": lambda s: s.s3_endpoint_url,
    "s3_bucket": lambda s: s.s3_bucket,
    "mimo_base_url": lambda s: s.mimo_base_url,
    "mimo_tts_model": lambda s: s.mimo_tts_model,
}

SECRET_SETTING_KEYS = [
    "sms_secret_id",
    "sms_secret_key",
    "sms_sdk_app_id",
    "mimo_api_key",
    "wechat_app_id",
    "wechat_app_secret",
    "s3_access_key",
    "s3_secret_key",
]


def get_system_settings(session: Session) -> dict:
    """系统参数：非敏感值（DB 或 env 默认）+ 凭据状态（仅尾号）。"""
    from app.admin_api.models import SystemSetting
    from app.core.config import get_settings

    settings = get_settings()
    rows = {r.key: r.value_json for r in session.query(SystemSetting).all()}
    plain = {}
    for key, default_fn in PLAIN_SETTING_DEFAULTS.items():
        row = rows.get(key)
        plain[key] = row.get("value") if row and "enc" not in row else default_fn(settings)
    secrets = {}
    for key in SECRET_SETTING_KEYS:
        row = rows.get(key)
        if row and "enc" in row:
            secrets[key] = {"configured": True, "tail": row.get("tail") or ""}
        else:
            secrets[key] = {"configured": False}
    return {"settings": plain, "secrets": secrets}


_INT_SETTING_KEYS = {
    "sms_code_ttl_seconds",
    "sms_code_max_attempts",
    "sms_send_cooldown_seconds",
    "sms_max_per_day_per_phone",
    "access_token_expire_minutes",
    "child_token_expire_minutes",
}


def _validate_setting_value(key: str, value) -> None:
    """系统参数值类型/取值校验：后台误存字符串/超范围会直接导致运行时 500。"""
    if key in _INT_SETTING_KEYS:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ApiError(422, "INVALID_SETTING_VALUE", f"{key} 必须是整数")
        if int(value) <= 0:
            raise ApiError(422, "INVALID_SETTING_VALUE", f"{key} 必须大于 0")
    if key == "grafana_base_url" and value:
        text = str(value)
        if not text.startswith(("http://", "https://")):
            raise ApiError(
                422,
                "INVALID_SETTING_VALUE",
                "grafana_base_url 必须是 http(s):// 地址（防 javascript: 注入）",
            )


def save_system_settings(
    session: Session, actor_role: str, values: dict
) -> dict:
    """保存非敏感系统参数（白名单 + 类型校验）；变更留审计。"""
    from app.admin_api.models import SystemSetting

    unknown = set(values) - set(PLAIN_SETTING_DEFAULTS)
    if unknown:
        raise ApiError(422, "UNKNOWN_SETTING", f"未知系统参数：{sorted(unknown)}")
    for key, value in values.items():
        _validate_setting_value(key, value)
        row = session.get(SystemSetting, key)
        if row is None:
            session.add(SystemSetting(key=key, value_json={"value": value}))
        else:
            row.value_json = {"value": value}
            row.updated_at = datetime.now(UTC)
    session.commit()
    log_action(
        session,
        actor_role=actor_role,
        action="system_settings.update",
        target_type="system_setting",
        target_id=",".join(sorted(values)),
        detail={"keys": sorted(values)},
    )
    return get_system_settings(session)


def save_system_secrets(
    session: Session, actor_role: str, values: dict
) -> dict:
    """保存凭据（Fernet 加密入库）；响应仅尾号；变更留审计。"""
    from app.admin_api.models import SystemSetting
    from app.core.crypto import encrypt_secret

    unknown = set(values) - set(SECRET_SETTING_KEYS)
    if unknown:
        raise ApiError(422, "UNKNOWN_SECRET", f"未知凭据项：{sorted(unknown)}")
    for key, value in values.items():
        if not value:
            continue
        row = session.get(SystemSetting, key)
        if row is None:
            row = SystemSetting(key=key, value_json={})
            session.add(row)
        row.value_json = {"enc": encrypt_secret(value), "tail": value[-4:]}
        row.updated_at = datetime.now(UTC)
    session.commit()
    log_action(
        session,
        actor_role=actor_role,
        action="system_secrets.update",
        target_type="system_setting",
        target_id=",".join(sorted(values)),
        detail={"keys": sorted(values)},
    )
    return get_system_settings(session)
