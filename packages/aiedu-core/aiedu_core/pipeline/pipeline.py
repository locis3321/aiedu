"""教学生成流水线（intent-first）。

顺序（用户最新要求，不可倒置）：
1. analyze_intent —— 内置意图识别，先于一切检索；
2. verify —— 数学核验（硬前提，verified==true 才能继续）；
3. retrieve skills —— 基于 TeachingIntent 检索 Claude-style Teaching Skill；
4. plan —— 内置全局教学政策 + skill 特殊方法 → 活动草案；
5. compile & validate —— LessonSpec 语义校验（两轮修复上限）；
6. review & gate —— 全局教学政策门禁 + reviewer。

旧「strategy classifier-first」路径已废弃：Python strategy registry 只作为
已审核教学方法的兼容实现（如 make-ten），不再决定主流程。
"""

import json

from pydantic import ValidationError

from aiedu_core.intent import analyze_intent
from aiedu_core.models.lesson_v2 import LessonSpecV2
from aiedu_core.models.semantics import validate_activity_graph
from aiedu_core.tracing import get_tracer
from aiedu_core.policy import check_teaching_policy
from aiedu_core.verify.evidence import VerificationRecord
from aiedu_core.services.llm_router import ModelRouter, default_router
from aiedu_core.verify.sympy_verify import verify_arithmetic
from aiedu_core.skills import SkillRetriever, TeachingSkill, load_all_skills
from aiedu_core.strategies import registry


class PipelineError(RuntimeError):
    """流水线终止：需要澄清 / 数学核验失败 / 结构错误超修复上限 / 能力缺口。"""


def _trunc(data, limit: int = 4000) -> str:
    """span attribute 用：dict/json → 截断字符串。"""
    import json

    try:
        text = (
            json.dumps(data, ensure_ascii=False, sort_keys=True)
            if not isinstance(data, str)
            else data
        )
    except Exception:  # noqa: BLE001
        text = str(data)
    return text[:limit]


def _skills_root():
    """定位 teaching-skills/ 目录：env 覆盖 → 仓库向上查找 → 包内资源。

    - 开发态（仓库/可编辑安装）：从包位置向上找 <repo>/teaching-skills（唯一真源）；
    - 已安装的 wheel：包内随包携带 aiedu_core/teaching_skills（importlib.resources）。
    """
    import os
    from pathlib import Path

    env = os.environ.get("AIEDU_SKILLS_DIR")
    if env:
        root = Path(env)
        return root if root.is_dir() else None
    cur = Path(__file__).resolve().parent
    for parent in cur.parents:
        candidate = parent / "teaching-skills"
        if candidate.is_dir():
            return candidate
    try:  # 已安装的包：skill 资产随包携带
        from importlib.resources import files

        packaged = files("aiedu_core").joinpath("teaching_skills")
        if packaged.is_dir():
            return Path(str(packaged))
    except (ModuleNotFoundError, FileNotFoundError, TypeError):
        pass
    return None


def _load_skills() -> list[TeachingSkill]:
    """加载 teaching-skills/ 目录；目录不存在时返回空列表（能力缺口由上游标记）。"""
    root = _skills_root()
    if root is None:
        return []
    return load_all_skills(root)


async def _verify(intent, input_json: dict) -> VerificationRecord:
    """verifier：按声明输入类型分流（意图识别结果与客户端声明任一判定为题目即核验）。

    - problem（用户声明为题目，或意图识别判定为 problem）：SymPy 程序化核验，
      requires_review → 能力缺口终止（不假装覆盖非算术题）；
    - 其余（概念/定理/主题/目标/误区）：无单一数值主张，走教研审核模式
      （claims/covers 为空），具体断言由 reviewer/门禁把关。
    护栏9：核验触发不单看客户端 kind——意图识别结果同样触发，防止把题目
    声明成 concept 跳过核验。
    """
    is_problem = input_json.get("kind") == "problem" or intent.input_kind == "problem"
    if not is_problem:
        return VerificationRecord(
            verifier_version="0.1.0",
            normalized_problem_hash=None,
            assumptions=(),
            claims=(),
            covered_claim_ids=(),
            result="verified",
        )
    content = input_json.get("content", "")
    return verify_arithmetic(content)


def _retrieve_skills(intent) -> list[TeachingSkill]:
    """skill 检索：只接受 TeachingIntent，不接受原始输入。"""
    return SkillRetriever(_load_skills()).retrieve(intent)


# 已审核教学方法的确定性实现映射：skill.name → strategy template.id。
# 常见的三类题型（凑十/破十/分数等分）命中映射后必须走模板库，
# 即使 LLM 可用也不得自由创作（AGENTS 护栏：常见计算策略不走 LLM 创意）。
SKILL_TO_TEMPLATE = {
    "make-ten": "make_ten",
    "borrow-ten": "borrow_ten",
    "fraction-equal-parts": "fraction_equal_parts",
}


async def _plan(
    intent,
    input_json: dict,
    skills: list[TeachingSkill],
    router: ModelRouter,
    record: VerificationRecord,
) -> LessonSpecV2:
    """planner：skill + 兼容实现优先；否则 LLM 受控规划；均不可用则能力缺口。

    兼容层说明：make-ten / borrow-ten / fraction-equal-parts 等已审核教学方法
    当前由 Python strategy 实现，通过 skill_refs 关联到 Claude-style skill；
    这不是主路径，只是过渡。映射之外或模板不适配的输入才走 LLM。
    """
    content = str(input_json.get("content") or "")
    for skill in skills:
        template_id = SKILL_TO_TEMPLATE.get(skill.name)
        if template_id is None:
            continue
        template = registry.get(template_id)
        if template is None:
            continue
        if not template.applies_to(content):
            continue
        params = template.extract_params(content)
        spec = template.build(params)
        design = spec.teaching_design.model_copy(
            update={"skill_refs": [skill.name]}
        )
        return spec.model_copy(update={"teaching_design": design})

    # 无匹配 skill：LLM 受控规划（内置全局教学政策 + skill 上下文）
    model = router.get("plan")
    if model is None:
        raise PipelineError(
            "no teaching skill matched and LLM not configured (capability gap)"
        )
    from aiedu_core.agents.prompts import DESIGNER_PROMPT
    from aiedu_core.policy import GLOBAL_TEACHING_POLICY

    skill_context = "\n".join(
        f"- {s.summary()}\n{s.content}" for s in skills
    ) or "（无匹配 skill，按通用教学框架设计）"
    policy_text = "\n".join(
        f"{i+1}. {k}：{v}" for i, (k, v) in enumerate(GLOBAL_TEACHING_POLICY.items())
    )
    prompt = (
        DESIGNER_PROMPT
        .replace("{skill_context}", skill_context)
        .replace("{intent_json}", intent.model_dump_json())
        .replace("{content}", json.dumps(input_json, ensure_ascii=False))
    )
    prompt = f"【全局教学规范】\n{policy_text}\n\n" + prompt
    # 结构化输出约束（json_schema strict）+ 带错误反馈的定向修复循环：
    # 业界标准方案（OpenAI Structured Outputs / outputguard repair-loop），2026-10-10 落地。
    # 最多 3 次调用（首次 + 2 次修复）；每次把具体校验错误回传给模型。
    from aiedu_core.services.structured import build_repair_prompt

    last_error: Exception | None = None
    for _attempt in range(3):
        text = await _call_designer(model, prompt)
        payload = _extract_json(text)
        if "activity_graph" not in payload:
            last_error = PipelineError("LLM output missing activity_graph")
            prompt = build_repair_prompt(prompt, text, "缺少 activity_graph 字段")
            continue
        try:
            return LessonSpecV2.model_validate(
                {
                    "schema_version": "2.0",
                    "lesson_id": "free-design",
                    "revision": 1,
                    "teaching_request": input_json,
                    "learning_objectives": [
                        {"id": "lo1", "description": intent.teaching_goal}
                    ],
                    "teaching_design": payload.get("teaching_design", {"modes": ["引导"]}),
                    "verification": {
                        "verified": record.result == "verified",
                        "verifier_version": record.verifier_version,
                        "normalized_problem_hash": record.normalized_problem_hash,
                        "assumptions": list(record.assumptions),
                        "claims": [vars(c) for c in record.claims],
                        "covered_claim_ids": list(record.covered_claim_ids),
                        # 无数值主张的类型显式标注：发布门禁可区分"核验通过"与"核验不适用"
                        "mode": (
                            "math_verified_applicable"
                            if (
                                input_json.get("kind") == "problem"
                                or intent.input_kind == "problem"
                            )
                            else "no_math_claims"
                        ),
                    },
                    "activity_graph": payload["activity_graph"],
                    "render": {"runtime_version": "0.1.0"},
                }
            )
        except ValidationError as exc:
            last_error = exc
            prompt = build_repair_prompt(prompt, text, str(exc))
    raise PipelineError("LLM planning output invalid after repair attempts") from last_error


def _extract_json(text: str) -> dict:
    """容错提取 LLM 输出中的 JSON 对象。

    模型可能输出 ```json 代码块、前后杂散文字、未加引号的键、
    键后缺失冒号或字符串内裸控制字符；
    依次尝试：剥代码块 → 截取首尾花括号 → 剥离控制字符 → 修复无引号键 → 修复缺冒号。
    """
    import re

    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise PipelineError(f"LLM output contains no JSON object: {text[:120]!r}")
    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        sanitized = re.sub(r"[\x00-\x1f\x7f]", "", candidate)
        try:
            return json.loads(sanitized)
        except json.JSONDecodeError:
            fixed = re.sub(
                r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:',
                r'\1"\2":',
                sanitized,
            )
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                # 模型偶发丢失键后的冒号：`"key" {...}` → `"key": {...}`
                fixed2 = re.sub(r'("(?:[^"\\]|\\.)*")\s*(?=[{\[])', r'\1:', fixed)
                try:
                    return json.loads(fixed2)
                except json.JSONDecodeError as exc:
                    raise PipelineError(f"LLM output is not valid JSON: {exc}") from exc


async def _call_model(model, prompt: str, response_format: dict | None = None) -> str:
    """调用 AgentScope ChatModel；返回文本。

    防御：AgentScope ChatResponse.content 是 block 列表，
    必须提取 TextBlock；任何异常包装为可读 PipelineError。
    可观测：独立 llm 子 span，记录 prompt/响应/token/耗时（OTel）。
    response_format：透传给 API（如 json_schema strict），供应商不支持时由调用方降级。
    """
    import time

    from agentscope.message import Msg, TextBlock

    started = time.time()
    msgs = [Msg(name="user", content=[TextBlock(text=prompt)], role="user")]
    _tracer = get_tracer()
    with _tracer.start_as_current_span("llm") as _sp:
        _sp.set_attribute("aiedu.llm.prompt", _trunc(prompt))
        _sp.set_attribute("aiedu.llm.model", getattr(model, "model", "") or "")
        try:
            call_kwargs: dict = {}
            if response_format is not None:
                call_kwargs["response_format"] = response_format
            resp = await model(msgs, **call_kwargs)
        except Exception as exc:  # noqa: BLE001 —— 供应商故障统一可控失败
            _sp.set_attribute("aiedu.llm.error", f"{type(exc).__name__}")
            raise PipelineError(f"LLM call failed: {type(exc).__name__}") from exc
        blocks = getattr(resp, "content", None)
        if not isinstance(blocks, list):
            raise PipelineError(
                f"unexpected LLM response type: {type(resp).__name__}"
            )
        texts = [
            b.text for b in blocks if isinstance(b, TextBlock) and getattr(b, "text", None)
        ]
        text = chr(10).join(texts).strip()
        if not text:
            raise PipelineError("empty LLM response")
        usage = getattr(resp, "usage", None)
        _sp.set_attribute("aiedu.llm.response", _trunc(text))
        _sp.set_attribute("aiedu.llm.tokens_in", getattr(usage, "input_tokens", 0) or 0)
        _sp.set_attribute("aiedu.llm.tokens_out", getattr(usage, "output_tokens", 0) or 0)
        _sp.set_attribute("aiedu.llm.duration_ms", int((time.time() - started) * 1000))
    return text


async def _call_designer(model, prompt: str) -> str:
    """结构化设计调用：json_schema strict 解码约束（业界方案）。

    供应商不支持 json_schema（API 报错）时降级为普通文本调用，
    由 _extract_json 容错解析兜底；空响应走修复循环重试。
    """
    from aiedu_core.services.structured import build_designer_schema

    try:
        return await _call_model(
            model,
            prompt,
            response_format={
                "type": "json_schema",
                "json_schema": build_designer_schema(),
            },
        )
    except PipelineError as exc:
        if "LLM call failed" not in str(exc):
            raise
        # 供应商不支持 json_schema → 普通调用
        return await _call_model(model, prompt)


def _compile_and_validate(spec: LessonSpecV2, max_repairs: int = 2) -> LessonSpecV2:
    """builder：编译 + 语义校验；结构错误最多两轮修复（超出即终止）。"""
    errors = validate_activity_graph(spec)
    repairs = 0
    while errors and repairs < max_repairs:
        repairs += 1
        # 定向修复：补全 next_ids / gate（确定性修复，不自动改写业务内容）
        spec = _repair_spec(spec, errors)
        errors = validate_activity_graph(spec)
    if errors:
        raise PipelineError(
            f"activity graph invalid after {repairs} repairs: {errors}"
        )
    return spec


def _repair_spec(spec: LessonSpecV2, errors: list[str]) -> LessonSpecV2:
    """确定性修复已知结构问题：next_ids 缺失/未知引用。"""
    nodes = list(spec.activity_graph)
    ids = {n.id for n in nodes}
    for i, node in enumerate(nodes):
        if node.next_ids is None:
            node.next_ids = (
                [nodes[i + 1].id] if i + 1 < len(nodes) else ["__end__"]
            )
        elif node.next_ids:
            node.next_ids = [
                ref for ref in node.next_ids if ref == "__end__" or ref in ids
            ]
            if not node.next_ids:
                node.next_ids = ["__end__"]
    return spec.model_copy(update={"activity_graph": nodes})


async def _review(spec: LessonSpecV2, intent) -> list[str]:
    """reviewer：程序化全局教学政策门禁（LLM 复核为扩展点）。"""
    return check_teaching_policy(spec, intent)


async def run_pipeline(
    input_json: dict,
    curriculum_context: dict | None = None,
    objectives: list[str] | None = None,
    router: ModelRouter | None = None,
    stage_cb=None,
    gate_cb=None,
) -> LessonSpecV2:
    """流水线入口：返回已核验、已校验的 LessonSpec v2。

    全链路 trace：intent → verify → retrieve → plan → compile → review，
    每步记录耗时/输入/输出；LLM 调用记录 prompt/响应/token。
    stage_cb：可选回调，每阶段完成时调用（六阶段进度透出，T3）。
    gate_cb：可选回调，门禁结果（含 MAJOR 违规）在 BLOCKER 阻断前回调，
    供上层落库作为发布证据（门禁结果服务端产生，不由前端自证）。
    """
    router = router or default_router()
    tracer = get_tracer()
    with tracer.start_as_current_span("pipeline"):
        # 1. 意图识别（第一步；需要澄清时终止）
        with tracer.start_as_current_span("intent") as _sp:
            _sp.set_attribute("aiedu.input", _trunc(input_json))
            intent = analyze_intent(input_json, curriculum_context)
        if intent.requires_clarification:
            raise PipelineError(
                "needs clarification: " + "; ".join(intent.clarification_questions)
            )
        if stage_cb is not None:
            stage_cb("intent")

        # 2. 数学核验（硬前提；problem 类必须有数值核验）
        with tracer.start_as_current_span("verify") as _sp:
            _sp.set_attribute("aiedu.input", _trunc(input_json))
            record = await _verify(intent, input_json)
        if record.result != "verified":
            raise PipelineError(
                f"verification failed ({record.result}): {record.claims[0].statement}"
            )
        if stage_cb is not None:
            stage_cb("verify")

        # 3. skill 检索（基于意图，不直接读原始输入）
        with tracer.start_as_current_span("retrieve") as _sp:
            _sp.set_attribute("aiedu.intent", _trunc(intent.model_dump()))
            skills = _retrieve_skills(intent)
        if stage_cb is not None:
            stage_cb("retrieve")

        # 4. 规划活动草案（skill + 兼容层 / LLM）
        with tracer.start_as_current_span("plan") as _sp:
            _sp.set_attribute("aiedu.skills", ",".join(sk.name for sk in skills))
            spec = await _plan(intent, input_json, skills, router, record)
        if stage_cb is not None:
            stage_cb("plan")

        # 5. 编译 + 语义校验
        with tracer.start_as_current_span("compile"):
            spec = _compile_and_validate(spec)
        if stage_cb is not None:
            stage_cb("compile")

        # 6. 全局教学政策门禁 + reviewer
        with tracer.start_as_current_span("review"):
            issues = await _review(spec, intent)
        if gate_cb is not None:
            # 先回调后阻断：MAJOR 违规也可以被记录（发布证据用）
            gate_cb(issues)
        blockers = [i for i in issues if i.startswith("BLOCKER")]
        if blockers:
            raise PipelineError("review blockers: " + "; ".join(blockers))
        if stage_cb is not None:
            stage_cb("review")

        return spec
