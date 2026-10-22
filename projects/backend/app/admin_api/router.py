"""运营后台 API（规格 v2 §1.3/§4.2）。

鉴权：admin JWT（开发态 POST /admin/login 签发；生产接 SSO）。
角色矩阵在服务端强制（浏览器限制不等于服务端权限）。
"""

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.admin_api import service
from app.core.errors import ApiError
from app.learning.router import get_session

router = APIRouter(prefix="/v1/admin")


def get_admin_role(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少登录凭证")
    return service.parse_admin_token(authorization.removeprefix("Bearer ").strip())


def _guard(action: str):
    """角色矩阵端点级依赖：服务端强制（如 config.write 仅 admin）。"""

    def dep(role: str = Depends(get_admin_role)) -> str:
        service.require_role(role, action)
        return role

    return dep


class LoginRequest(BaseModel):
    role: str = Field(min_length=1, max_length=24)


class PublishRequest(BaseModel):
    # extra=allow：让反强改 verified 守卫能看见请求中的覆盖参数（否则 pydantic 静默丢弃）
    model_config = ConfigDict(extra="allow")

    teaching_gate_ok: bool = False
    age_ok: bool = False
    layout_ok: bool = False
    human_reviewed: bool = False


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SkillCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1)


class PromptSaveRequest(BaseModel):
    content: str = Field(min_length=1)


class ModelConfigRequest(BaseModel):
    name: str
    provider: str
    model: str
    role: str = "generate"
    credential_status: str = "missing"
    # API Key：write-only（加密入库，响应仅返回尾号）；None 不覆盖既有密钥
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    timeout: float | None = None


class TtsConfigRequest(BaseModel):
    provider: str = "mimo"
    voice: str | None = None
    rate: float | None = None


class TtsTestRequest(BaseModel):
    text: str | None = None
    voice: str | None = None


class AiAvatarRequest(BaseModel):
    enabled: bool = False
    assets: dict | None = None


class SmsTemplateRequest(BaseModel):
    sign_name: str | None = None
    template_id: str | None = None


class QuestionCreateRequest(BaseModel):
    # extra=forbid：内置题核验标志由服务端核验流程写入，管理端不得直传（护栏5语义）
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    knowledge_code: str = Field(min_length=1)
    grade: int


class QuestionStatusRequest(BaseModel):
    status: str


class SourceCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    endpoint: str | None = None
    quota: str | None = None


class RewardRuleCreateRequest(BaseModel):
    points_independent: int
    points_assisted: int
    points_demonstrated: int
    daily_cap: int | None = None
    per_event_cap: int | None = None


class ExamTemplateCreateRequest(BaseModel):
    type_: str = Field(min_length=1)
    title: str = Field(min_length=1)


class KnowledgeNodeCreateRequest(BaseModel):
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    grade: int
    unit_code: str = Field(min_length=1)


# ---------------------------------------------------------------- 登录与概览

@router.post("/login")
def login(request: LoginRequest) -> dict:
    return service.issue_admin_token(request.role)


@router.get("/overview")
def overview(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.overview(session)


# ---------------------------------------------------------------- 审核工作台

@router.get("/reviews")
def list_reviews(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_pending_reviews(session)


@router.post("/reviews/{revision_id}/publish")
def publish_review(
    revision_id: str,
    request: PublishRequest,
    role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    # 反强改 verified：请求体不含 verification 字段；任何携带覆盖参数的请求被拒
    service.assert_no_verification_forge(request.model_dump())
    # teaching_gate_ok 不由请求体自证：服务端从生成期 gate_report 派生
    return service.publish_review(
        session,
        role,
        revision_id,
        age_ok=request.age_ok,
        layout_ok=request.layout_ok,
        human_reviewed=request.human_reviewed,
    )


@router.post("/reviews/{revision_id}/reject")
def reject_review(
    revision_id: str,
    request: RejectRequest,
    role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.reject_review(session, role, revision_id, request.reason)


# ---------------------------------------------------------------- Skill

@router.get("/skills")
def list_skills(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_skills(session)


@router.post("/skills")
def create_skill(
    request: SkillCreateRequest,
    role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.create_skill(session, role, request.name, request.content)


@router.post("/skills/{skill_id}/toggle")
def toggle_skill(
    skill_id: str,
    enabled: bool,
    role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.toggle_skill(session, role, skill_id, enabled)


@router.delete("/skills/{skill_id}")
def delete_skill(
    skill_id: str,
    role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.delete_skill(session, role, skill_id)


# ---------------------------------------------------------------- 提示词与人设

@router.get("/prompts/{kind}")
def list_prompts(kind: str, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_prompts(session, kind)


@router.post("/prompts/{kind}")
def save_prompt(kind: str, request: PromptSaveRequest, role: str = Depends(_guard("prompts.write")),
    session: Session = Depends(get_session),
) -> dict:
    return service.save_prompt(session, kind, request.content)


@router.post("/prompts/{kind}/{version}/publish")
def publish_prompt(kind: str, version: int, role: str = Depends(_guard("prompts.publish")),
    session: Session = Depends(get_session),
) -> dict:
    return service.publish_prompt(session, kind, version)


# ---------------------------------------------------------------- 配置管理

@router.get("/models-configs")
def list_models(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_model_configs(session)


@router.post("/models-configs")
def save_model(request: ModelConfigRequest, role: str = Depends(_guard("config.write")),
    session: Session = Depends(get_session),
) -> dict:
    return service.save_model_config(
        session,
        actor_role=role,
        name=request.name,
        provider=request.provider,
        model=request.model,
        role=request.role,
        credential_status=request.credential_status,
        api_key=request.api_key,
        base_url=request.base_url,
        temperature=request.temperature,
        timeout=request.timeout,
    )


@router.get("/tts-config")
def get_tts(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_tts_config(session)


@router.put("/tts-config")
def put_tts(request: TtsConfigRequest, role: str = Depends(_guard("config.write")),
    session: Session = Depends(get_session),
) -> dict:
    return service.save_tts_config(
        session, role, provider=request.provider, voice=request.voice, rate=request.rate
    )


@router.post("/tts-config/test")
def test_tts(request: TtsTestRequest, role: str = Depends(_guard("config.write")),
    session: Session = Depends(get_session),
) -> dict:
    """试听：真实合成示例文本，返回 base64 音频（未接入显式失败）。"""
    return service.test_tts(session, voice=request.voice, text=request.text)


@router.get("/ai-avatar")
def get_avatar(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_ai_avatar(session)


@router.put("/ai-avatar")
def put_avatar(request: AiAvatarRequest, role: str = Depends(_guard("config.write")),
    session: Session = Depends(get_session),
) -> dict:
    return service.save_ai_avatar(session, enabled=request.enabled, assets=request.assets)


@router.get("/sms-template")
def get_sms(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_sms_template(session)


@router.put("/sms-template")
def put_sms(request: SmsTemplateRequest, role: str = Depends(_guard("config.write")),
    session: Session = Depends(get_session),
) -> dict:
    return service.save_sms_template(
        session, role, sign_name=request.sign_name, template_id=request.template_id
    )


# ---------------------------------------------------------------- 试卷治理

@router.post("/exam-templates/{template_id}/approve")
def approve_template(template_id: str, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.approve_exam_template(session, role, template_id)


@router.get("/exam-results")
def list_exam_results(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_exam_results(session)


@router.post("/exam-results/{result_id}/review")
def review_result(result_id: str, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.mark_exam_result_reviewed(session, role, result_id)


# ------------------------------------------------ 题库/题源/规则/反馈（A4/A6/A10/A14）

@router.get("/questions")
def list_questions(status: str | None = None, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_questions_admin(session, status=status)


@router.post("/questions", status_code=201)
def create_question(request: QuestionCreateRequest, role: str = Depends(_guard("questions.write")),
    session: Session = Depends(get_session),
) -> dict:
    return service.create_question_admin(
        session,
        content=request.content,
        answer=request.answer,
        knowledge_code=request.knowledge_code,
        grade=request.grade,
    )


@router.post("/questions/{question_id}/status")
def update_question_status(question_id: str, request: QuestionStatusRequest,
    role: str = Depends(_guard("questions.write")), session: Session = Depends(get_session),
) -> dict:
    return service.update_question_status_admin(session, question_id, request.status)


@router.get("/sources")
def list_sources(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_sources_admin(session)


@router.post("/sources", status_code=201)
def create_source(request: SourceCreateRequest, role: str = Depends(_guard("sources.write")),
    session: Session = Depends(get_session),
) -> dict:
    return service.create_source_admin(
        session,
        name=request.name,
        provider=request.provider,
        endpoint=request.endpoint,
        quota=request.quota,
    )


@router.post("/sources/{source_id}/connect-test")
def connect_source(source_id: str, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.connect_source_admin(session, source_id)


@router.post("/sources/{source_id}/search")
def search_source(source_id: str, keyword: str | None = None,
    role: str = Depends(get_admin_role), session: Session = Depends(get_session),
) -> dict:
    return service.search_source_admin(session, source_id, keyword=keyword)


@router.get("/reward-rules")
def list_reward_rules(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_reward_rules_admin(session)


@router.post("/reward-rules", status_code=201)
def create_reward_rule(request: RewardRuleCreateRequest, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.create_reward_rule_admin(
        session,
        role,
        points_independent=request.points_independent,
        points_assisted=request.points_assisted,
        points_demonstrated=request.points_demonstrated,
        daily_cap=request.daily_cap,
        per_event_cap=request.per_event_cap,
    )


@router.get("/safety-feedbacks")
def list_safety_feedbacks(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_safety_feedbacks(session)


@router.post("/safety-feedbacks/{feedback_id}/handle")
def handle_safety_feedback(feedback_id: str, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.handle_safety_feedback(session, role, feedback_id)


@router.get("/knowledge-nodes")
def list_knowledge_nodes(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    from app.questionbank import service as qb

    return qb.list_knowledge_nodes(session)


@router.post("/knowledge-nodes", status_code=201)
def create_knowledge_node(request: KnowledgeNodeCreateRequest,
    role: str = Depends(_guard("knowledge.write")), session: Session = Depends(get_session),
) -> dict:
    from app.questionbank import service as qb

    return qb.create_knowledge_node(
        session,
        code=request.code,
        title=request.title,
        stage=request.stage,
        grade=request.grade,
        unit_code=request.unit_code,
    )


@router.post("/exam-templates", status_code=201)
def create_exam_template(request: ExamTemplateCreateRequest,
    role: str = Depends(get_admin_role), session: Session = Depends(get_session),
) -> dict:
    from app.questionbank import service as qb

    return qb.create_exam_template(session, type_=request.type_, title=request.title)


# ---------------------------------------------------------------- 业务用户/审计/Trace

@router.get("/users")
def list_users(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.list_business_users(session)


@router.get("/users/children/{child_id}")
def child_detail(child_id: str, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.child_detail(session, child_id)


@router.get("/audit")
def search_audit(
    page: int = 1,
    page_size: int = 20,
    actor_role_filter: str | None = None,
    action_filter: str | None = None,
    role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.search_audit(
        session,
        page=page,
        page_size=page_size,
        actor_role=actor_role_filter,
        action=action_filter,
    )


@router.delete("/audit/{audit_id}")
def delete_audit(
    audit_id: str,
    confirm: bool = False,
    role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.delete_audit(session, role, audit_id, confirm)


@router.get("/trace")
def trace(uid: str, role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.trace_url(session, uid)


class SystemSettingsRequest(BaseModel):
    """系统参数/凭据批量保存（key 白名单在 service 校验）。"""

    values: dict


@router.get("/system-settings")
def get_system_settings(role: str = Depends(get_admin_role),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_system_settings(session)


@router.put("/system-settings")
def put_system_settings(request: SystemSettingsRequest,
    role: str = Depends(_guard("config.write")), session: Session = Depends(get_session),
) -> dict:
    return service.save_system_settings(session, role, request.values)


@router.post("/system-settings/secrets")
def post_system_secrets(request: SystemSettingsRequest,
    role: str = Depends(_guard("config.write")), session: Session = Depends(get_session),
) -> dict:
    """凭据保存（write-only）：加密入库，响应仅尾号。"""
    return service.save_system_secrets(session, role, request.values)
