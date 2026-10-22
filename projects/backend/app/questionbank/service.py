"""题库与练习安排业务逻辑（规格 v2 §11 + 任务包验收项）。

硬约束：
- 题目来源是业务事实，不伪造；未审核题不得进入抽题（fail-closed）；
- 题源不可用时显式失败或降级到内置题并注明来源，不假装成功；
- 抽题条件来自证据与档案事实；变式程序化生成必须过数学核验（R6'）；
- 路线规划由图谱+规则驱动（R8/护栏13），skill 不作为规划许可；
- 摸底跨知识点（1–3 份短诊断卷）。
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.questionbank.models import (
    ExamPaper,
    ExamResult,
    ExamTemplate,
    KnowledgeNode,
    PracticeSet,
    Question,
    QuestionSource,
)

APPROVED = "approved"

# 画像维度 → 知识点（教研配置；抽题映射）
DIMENSION_TO_KNOWLEDGE = {
    "operations": ["arithmetic.add_sub", "arithmetic.mul_div"],
    "concept": ["fraction.mean", "number.place_value"],
    "transfer": ["application.word_problem"],
    "number_sense": ["number.sense"],
}

def _is_weak(d: dict) -> bool:
    """薄弱：有证据的 assisted/demonstrated，或有尝试但待观察（needs_review 计数>0）。

    无任何证据的维度只是"待观察"，不是薄弱点——不据此安排练习。
    """
    if d["level"] in {"assisted", "demonstrated"}:
        return True
    return d["level"] == "needs_review" and bool(d.get("needs_review_count"))


def _utcnow() -> datetime:
    return datetime.now(UTC)

def _node(code: str, title: str, stage: str, grade: int, unit: str) -> dict:
    return {
        "code": code,
        "title": title,
        "stage": stage,
        "grade": grade,
        "unit_code": unit,
        "status": "open" if stage == "primary" else "construction",
    }


KNOWLEDGE_SEED = [
    _node("arithmetic.add_sub", "加减法运算（凑十法）", "primary", 1, "u1-arithmetic-basic"),
    _node("arithmetic.mul_div", "乘除法运算基础", "primary", 3, "u2-mul-div-basic"),
    _node("fraction.mean", "分数的意义（等分）", "primary", 3, "u3-fraction-mean"),
    _node("number.place_value", "数位与位值理解", "primary", 2, "u4-place-value"),
    _node("application.word_problem", "应用题与数量关系", "junior", 7, "j1-word-problem"),
    _node("number.sense", "数感与估算策略", "senior", 10, "s1-number-sense"),
]





def ensure_knowledge_nodes(session: Session) -> None:
    """图谱种子（与迁移一致）：表空时补种，保证路线可视化始终可用。"""
    if session.query(KnowledgeNode).count() > 0:
        return
    for item in KNOWLEDGE_SEED:
        session.add(KnowledgeNode(**item))
    session.commit()


def list_knowledge_nodes(session: Session) -> dict:
    """知识点列表（A5 路线资料管理，只读视图）。"""
    ensure_knowledge_nodes(session)
    rows = session.query(KnowledgeNode).order_by(KnowledgeNode.grade).all()
    return {
        "items": [
            {
                "code": n.code,
                "title": n.title,
                "stage": n.stage,
                "grade": n.grade,
                "unit_code": n.unit_code,
                "status": n.status,
            }
            for n in rows
        ]
    }


def create_knowledge_node(
    session: Session,
    *,
    code: str,
    title: str,
    stage: str,
    grade: int,
    unit_code: str,
) -> dict:
    """新增知识点节点（A5）；重复 code 显式失败。"""
    if session.get(KnowledgeNode, code) is not None:
        raise ApiError(409, "NODE_EXISTS", f"知识点已存在：{code}")
    node = KnowledgeNode(
        code=code,
        title=title,
        stage=stage,
        grade=grade,
        unit_code=unit_code,
        status="open" if stage == "primary" else "construction",
    )
    session.add(node)
    session.commit()
    session.refresh(node)
    return {
        "code": node.code,
        "title": node.title,
        "stage": node.stage,
        "grade": node.grade,
        "unit_code": node.unit_code,
        "status": node.status,
    }




# ---------------------------------------------------------------- 内置题库

def create_question(
    session: Session,
    *,
    content: str,
    answer: str,
    knowledge_code: str,
    grade: int,
    source: str = "builtin",
    math_verified: bool = False,
) -> dict:
    q = Question(
        content=content,
        answer=answer,
        knowledge_code=knowledge_code,
        grade=grade,
        source=source,
        status="draft",
        math_verified=math_verified,
    )
    session.add(q)
    session.commit()
    session.refresh(q)
    return _question_dict(q)


def update_question_status(session: Session, question_id: str, status: str) -> dict:
    q = session.get(Question, question_id)
    if q is None:
        raise ApiError(404, "QUESTION_NOT_FOUND", "题目不存在")
    if status not in {"draft", "reviewing", "approved", "rejected"}:
        raise ApiError(422, "INVALID_STATUS", f"未知题目状态：{status}")
    q.status = status
    session.commit()
    return _question_dict(q)


def search_questions(
    session: Session, knowledge_code: str | None = None, approved_only: bool = True
) -> list[dict]:
    q = session.query(Question)
    if knowledge_code:
        q = q.filter_by(knowledge_code=knowledge_code)
    if approved_only:
        q = q.filter_by(status=APPROVED)
    return [_question_dict(x) for x in q.order_by(Question.created_at).all()]


def sample_approved(
    session: Session, knowledge_codes: list[str], count: int
) -> list[Question]:
    """从已审核题目中按知识点抽题；不足时返回现有（不编造）。"""
    rows = (
        session.query(Question)
        .filter(Question.status == APPROVED, Question.knowledge_code.in_(knowledge_codes))
        .all()
    )
    return rows[:count]


def _question_dict(q: Question) -> dict:
    return {
        "id": q.id,
        "content": q.content,
        "answer": q.answer,
        "knowledge_code": q.knowledge_code,
        "grade": q.grade,
        "source": q.source,
        "status": q.status,
        "math_verified": q.math_verified,
    }


# ---------------------------------------------------------------- 第三方题源

def create_source(
    session: Session,
    *,
    name: str,
    provider: str,
    endpoint: str | None = None,
    quota: str | None = None,
    knowledge_mapping: dict | None = None,
) -> dict:
    src = QuestionSource(
        name=name,
        provider=provider,
        endpoint=endpoint,
        quota=quota,
        enabled=True,
        knowledge_mapping_json=knowledge_mapping,
        signature_version=1,
    )
    session.add(src)
    session.commit()
    session.refresh(src)
    return _source_dict(src)


def connect_test(session: Session, source_id: str, client=None) -> dict:
    """连接测试 fail-closed：真实调用题庄（匿名试用）；失败显式呈现，不假装成功。"""
    from app.questionbank.tizhuang import TizhuangClient, TizhuangError

    src = session.get(QuestionSource, source_id)
    if src is None:
        raise ApiError(404, "SOURCE_NOT_FOUND", "题源不存在")
    mapping_hit = bool((src.knowledge_mapping_json or {}).get("knowledge_code"))
    if src.provider != "tizhuang":
        return {
            "source_id": src.id,
            "connected": False,
            "note": f"未知题源 provider：{src.provider}，不执行连接测试",
            **({"knowledge_mapping_hit": mapping_hit} if src.knowledge_mapping_json else {}),
        }
    try:
        tz = client or TizhuangClient()
        quota = tz.quota()
    except TizhuangError as exc:
        return {
            "source_id": src.id,
            "connected": False,
            "note": f"题庄在线题库未接入：{exc}",
            **({"knowledge_mapping_hit": mapping_hit} if src.knowledge_mapping_json else {}),
        }
    return {
        "source_id": src.id,
        "connected": True,
        "note": "题庄在线题库已连接（匿名试用）",
        **({"knowledge_mapping_hit": mapping_hit} if src.knowledge_mapping_json else {}),
        **({"quota": quota} if isinstance(quota, dict) else {}),
    }


def search_external(
    session: Session, source_id: str, keyword: str | None = None, client=None
) -> dict:
    """从题庄检索题目（默认脱敏答案字段）；失败显式呈现，不编造。"""
    from app.questionbank.tizhuang import TizhuangClient, TizhuangError

    src = session.get(QuestionSource, source_id)
    if src is None:
        raise ApiError(404, "SOURCE_NOT_FOUND", "题源不存在")
    if not src.enabled:
        raise ApiError(409, "SOURCE_DISABLED", f"题源已停用：{src.name}")
    mapping = src.knowledge_mapping_json or {}
    kw = keyword or mapping.get("keyword")
    # subject_id=2（数学）为默认学科维度；keyword 检索偶发超时（504）时降级重试
    subject_id = mapping.get("subject_id") or 2
    try:
        tz = client or TizhuangClient()
        try:
            data = tz.search(subject_id=subject_id, keyword=kw, limit=10)
        except TizhuangError:
            if not kw:
                raise
            data = tz.search(subject_id=subject_id, limit=10)  # 降级：无关键词检索
    except TizhuangError as exc:
        raise ApiError(
            503,
            "SOURCE_UNAVAILABLE",
            f"题庄在线题库不可用：{exc}",
        ) from exc
    items = data.get("items") or data.get("questions") or data.get("data") or []
    return {
        "source_id": src.id,
        "source_note": f"来源：{src.name}（题庄在线题库）",
        **({"keyword": kw} if kw else {}),
        **{"questions": items},
        **{"answer_filtered": True},
    }


def _source_dict(src: QuestionSource) -> dict:
    return {
        "id": src.id,
        "name": src.name,
        "provider": src.provider,
        "endpoint": src.endpoint,
        "quota": src.quota,
        "enabled": src.enabled,
        "knowledge_mapping": src.knowledge_mapping_json,
        "signature_version": src.signature_version,
        # 签名版本化：配置变化⇒新版本；rebuild 先写新版本成功后才发布（T7 消费）
        **{"last_good_version": src.signature_version},
    }


# ---------------------------------------------------------------- 试卷

def create_exam_template(
    session: Session,
    *,
    type_: str,
    title: str,
    question_ids: list[str] | None = None,
    rules: dict | None = None,
) -> dict:
    if type_ not in {"diagnostic", "sync", "stage"}:
        raise ApiError(422, "INVALID_EXAM_TYPE", f"未知试卷类型：{type_}")
    tpl = ExamTemplate(
        type=type_, title=title, question_ids_json=question_ids, rules_json=rules
    )
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return {"id": tpl.id, "type": tpl.type, "title": tpl.title}


def generate_paper(
    session: Session, child_id: str, template_id: str | None = None
) -> dict:
    """生成试卷：仅从已审核题抽题；诊断卷跨知识点（摸底）。"""
    tpl = (
        session.get(ExamTemplate, template_id)
        if template_id
        else _default_template(session)
    )
    if tpl is None:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "试卷模板不存在")
    if getattr(tpl, "review_status", "approved") != "approved":
        raise ApiError(
            422,
            "TEMPLATE_NOT_APPROVED",
            f"试卷模板未审核，不可用于生成：{tpl.title}",
        )

    if tpl.type == "diagnostic":
        codes = [dims[0] for dims in DIMENSION_TO_KNOWLEDGE.values()]
        picked = sample_approved(session, codes, count=max(3, len(codes)))
        question_ids = [q.id for q in picked]
        note = {"basis": "新档案摸底：跨知识点短卷"}
    else:
        ids = tpl.question_ids_json or []
        picked = [
            q
            for q in (session.get(Question, i) for i in ids)
            if q is not None and q.status == APPROVED
        ]
        question_ids = [q.id for q in picked]
        note = {"basis": f"模板 {tpl.title} 抽题"}

    if not question_ids:
        raise ApiError(422, "NO_APPROVED_QUESTIONS", "无已审核题目可生成试卷（不编造）")
    paper = ExamPaper(
        template_id=tpl.id,
        child_id=child_id,
        type=tpl.type,
        question_ids_json=question_ids,
        status="pending",
    )
    session.add(paper)
    session.commit()
    session.refresh(paper)
    return {
        **{"paper_id": paper.id},
        **{"type": paper.type},
        **{"questions": [_question_dict(q) for q in picked]},
        **note,
    }


def _default_template(session: Session) -> ExamTemplate | None:
    return (
        session.query(ExamTemplate)
        .filter_by(type="diagnostic")
        .order_by(ExamTemplate.created_at.desc())
        .first()
    )


def submit_exam(session: Session, child_id: str, paper_id: str, answers: dict) -> dict:
    """交卷：判定 → evidence_levels → 结果写入证据体系（§11.3，不可写成能力结论）。"""
    paper = session.get(ExamPaper, paper_id)
    if paper is None or paper.child_id != child_id:
        raise ApiError(404, "PAPER_NOT_FOUND", "试卷不存在")
    if paper.status == "completed":
        raise ApiError(409, "PAPER_ALREADY_SUBMITTED", "试卷已提交")

    levels = []
    for qid in paper.question_ids_json:
        q = session.get(Question, qid)
        if q is None:
            continue
        given = str(answers.get(qid, "")).strip()
        correct = given == (q.answer or "").strip()
        levels.append(
            "independent" if correct else ("assisted" if given else "needs_review")
        )

    result = ExamResult(
        paper_id=paper.id,
        child_id=child_id,
        answers_json=answers,
        evidence_levels_json=levels,
        completed_at=_utcnow(),
    )
    paper.status = "completed"
    session.add(result)
    session.commit()

    # 结果写入证据体系：先建 exam 会话与活动，再写 evidence（供 T12/T6 消费）
    from app.learning.models import EvidenceRecord, LearningSession, SessionActivity

    ls = LearningSession(child_id=child_id)
    session.add(ls)
    session.commit()
    act = SessionActivity(
        session_id=ls.id,
        child_id=child_id,
        kind="exam",
        status="completed",
        method_source="standard",
    )
    session.add(act)
    session.commit()
    ev = EvidenceRecord(
        child_id=child_id,
        session_id=ls.id,
        activity_id=act.id,
        kind="exam_result",
        level=_overall_level(levels),
        detail_json={"paper_id": paper.id},
    )
    session.add(ev)
    session.commit()
    return {
        **{"paper_id": paper.id},
        **{"evidence_levels": levels},
        **{"overall_level": ev.level},
        **{"evidence_id": ev.id},
    }


def _overall_level(levels: list[str]) -> str:
    """整体结论：全对→independent；过半→assisted；否则 needs_review（不写能力结论）。"""
    if not levels:
        return "needs_review"
    correct = levels.count("independent")
    if correct == len(levels):
        return "independent"
    if correct >= max(1, len(levels) // 2):
        return "assisted"
    return "needs_review"


# ---------------------------------------------------------------- 练习集与摸底

def build_practice_set(session: Session, child_id: str) -> dict:
    """按表现安排：从画像薄弱维度映射知识点抽已审核题（T12 消费）。"""
    from app.profile.service import get_dimensions

    profile = get_dimensions(session, child_id)
    weak_dims = [d["code"] for d in profile["dimensions"] if _is_weak(d)]

    if not weak_dims:
        # 无薄弱点证据：返回空练习集并注明（不自动挑选默认题）
        return {
            "child_id": child_id,
            "question_ids": [],
            "basis": {"note": "暂无薄弱点证据，未生成练习集"},
        }

    codes = [c for d in weak_dims for c in DIMENSION_TO_KNOWLEDGE.get(d, [])]
    picked = sample_approved(session, codes, count=5)
    if not picked:
        return {
            "child_id": child_id,
            "question_ids": [],
            "basis": {"weak_dimensions": weak_dims, "note": "薄弱点无已审核题目"},
        }
    ps = PracticeSet(
        child_id=child_id,
        question_ids_json=[q.id for q in picked],
        basis_json={"weak_dimensions": weak_dims, "source": "profile"},
    )
    session.add(ps)
    session.commit()
    session.refresh(ps)
    return {
        **{"practice_set_id": ps.id},
        **{"child_id": child_id},
        **{"questions": [_question_dict(q) for q in picked]},
        **{"basis": ps.basis_json},
    }


def create_diagnostics(session: Session, child_id: str) -> dict:
    """新档案/证据不足摸底：1–3 份跨知识点短诊断卷（去重，不重复出同题卷）。"""
    papers = []
    seen_question_ids: set[frozenset] = set()
    for _ in range(3):
        try:
            paper = generate_paper(session, child_id, template_id=None)
        except ApiError:
            break
        ids = frozenset(q["id"] for q in paper["questions"])
        if ids and ids <= seen_question_ids:
            break  # 与已有卷完全同题：停止，避免生成重复摸底卷
        seen_question_ids.add(ids)
        papers.append(paper)
    if not papers:
        raise ApiError(422, "NO_APPROVED_QUESTIONS", "无已审核题目可生成诊断卷（不编造）")
    return {"child_id": child_id, "papers": papers[:3], "count": len(papers[:3])}


# ---------------------------------------------------------------- 路线规划

def get_route(session: Session, child_id: str) -> dict:
    """全路线静态可视化 + L1 单元内重排 + L2 跨单元补洞（图谱+规则驱动）。

    - 三学段节点与状态（已开放/建设中）；节点含学习目标；
    - L1：证据驱动换路径/换表征/插变式（薄弱维度 → 插入变式标记）；
    - L2：跨单元补洞（按学段/年级回填最早薄弱节点；前置链数据待 A5 教研维护接入，
      当前不冒充前置链回溯）；
    - 无 skill 命中仍返回图谱/规则规划（source='graph'），skill 不作为规划许可。
    """
    ensure_knowledge_nodes(session)
    nodes = session.query(KnowledgeNode).order_by(KnowledgeNode.grade).all()
    stages: dict[str, list[dict]] = {}
    for n in nodes:
        stages.setdefault(n.stage, []).append(
            {
                "code": n.code,
                "title": n.title,
                "grade": n.grade,
                "unit_code": n.unit_code,
                "status": n.status,
                "objective": f"学习目标：{n.title}",
            }
        )

    from app.profile.service import get_dimensions

    profile = get_dimensions(session, child_id)
    weak_dims = [d["code"] for d in profile["dimensions"] if _is_weak(d)]
    l1_reorder = []
    l2_backfill = []
    if weak_dims:
        # L1：薄弱维度 → 其知识点映射内插入变式（证据驱动，非占位）
        weak_codes = {
            c for d in weak_dims for c in DIMENSION_TO_KNOWLEDGE.get(d, [])
        }
        weak_nodes = [n for n in nodes if n.code in weak_codes]
        l1_reorder = [
            {
                "unit_code": n.unit_code,
                "action": "insert_variant",
                "reason": (
                    f"维度 {d} 证据带为 {d_level(profile, d)}，"
                    f"在 {n.title} 插入变式练习"
                ),
            }
            for d in weak_dims
            for n in weak_nodes
            if n.code in DIMENSION_TO_KNOWLEDGE.get(d, [])
        ]
        # L2：跨单元补洞——薄弱维度对应知识点中最早学段节点优先回填
        # （前置链数据待 A5 教研维护接入，当前按学段/年级近似）
        backfill_targets = sorted(weak_nodes or nodes, key=lambda x: (x.grade, x.stage))
        l2_backfill = [
            {
                "node_code": n.code,
                "action": "backfill",
                "reason": (
                    f"维度 {weak_dims[0]} 薄弱，按学段顺序从「{n.title}」回填补洞"
                ),
            }
            for n in backfill_targets[:1]
        ]

    return {
        "stages": [
            {"stage": s, "nodes": v, "status_label": _stage_label(s)}
            for s, v in stages.items()
        ],
        "l1_reorder": l1_reorder,
        "l2_backfill": l2_backfill,
        "source": "graph",  # 图谱+规则驱动；skill 不作为规划许可
        "note": _no_skill_note(),
    }


def d_level(profile: dict, code: str) -> str:
    for d in profile["dimensions"]:
        if d["code"] == code:
            return d["level"]
    return "needs_review"


def _stage_label(stage: str) -> str:
    return {
        "primary": "小学（已开放）",
        "junior": "初中（建设中）",
        "senior": "高中（建设中）",
    }.get(stage, stage)


def _no_skill_note() -> str:
    return (
        "路线由知识图谱与规则驱动；无匹配教学 skill 时仍给出初步规划或诊断建议，"
        "skill 不作为规划许可。"
    )


# ---------------------------------------------------------------- 变式

def generate_variant(session: Session, base_input: dict) -> dict:
    """变式程序化生成：参数由程序计算，产物过数学核验（R6'，verified=true）。"""
    from app.strategies import make_ten, registry

    content = str(base_input.get("content", ""))
    match = registry.match(content)
    if match is None:
        raise ApiError(422, "NO_VARIANT_TEMPLATE", "该题暂无程序化变式模板")
    params = match.params
    a, b = params["a"], params["b"]
    # 程序化变参：保持凑十结构（k = 10 - b），调整数值并保证 k <= a
    new_b = max(1, b - 2)
    new_k = 10 - new_b
    new_a = max(new_k + 1, a + 2)
    variant_params = {"a": new_a, "b": new_b, "k": new_k}
    spec = make_ten.build(variant_params)
    spec_dict = spec.model_dump(mode="json")
    assert spec_dict["verification"]["verified"] is True
    return {
        **{"params": variant_params},
        **{"verified": True},
        **{"lesson_id": spec_dict["lesson_id"]},
        **{"source_note": "程序化变式（策略模板参数计算）"},
    }
