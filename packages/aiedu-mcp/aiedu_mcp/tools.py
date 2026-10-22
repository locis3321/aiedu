"""MCP 工具实现：纯函数，直接调用 aiedu-core 内核。

设计约束：
- 判定全部由内核完成，本层只透传与转 dict（不弱化 verified / filtered 语义）；
- 未覆盖题型把 PipelineError 转成结构化 error，绝不编造 spec；
- 判分在服务端（submit_attempt），不使用客户端传入的判定结果；
- 入参层级：所有 tool 接收/返回的都是**LessonSpec v2 的 spec 本体**，
  不是 generate_lesson 的整包返回（那是信封：{lesson_id, spec, verification}）。

注意：这些函数以普通函数暴露，由 server.build_server() 用 @mcp.tool 注册，
因此单元测试可直接调用，无需走网络。
"""

import asyncio
import base64
import json
import os
from dataclasses import asdict

from aiedu_core.models.filtering import filtered_spec
from aiedu_core.pipeline.pipeline import PipelineError, run_pipeline
from aiedu_core.verify.sympy_verify import verify_math as verify_math_core
from aiedu_mcp.usage_log import logged

# 官方渲染地址（架构增量 v1 · D5/C2：本地拼 URL，无需渲染服务在线）。
# 注：这是 stdio 用户无可请求上下文时的唯一残留硬编码点（架构文档 §4.2），
# 部署演示站时替换为真实域名；AIEDU_PLAYER_URL / AIEDU_PUBLIC_URL 优先级更高。
OFFICIAL_PLAYER_URL = "https://aiedu-play.example.com"


def _resolve_render_base() -> str:
    """URL base 解析（优先级从高到低，架构文档 §4.2）：
    1. AIEDU_PLAYER_URL 显式设置（向后兼容本地 serve.mjs 用户）；
    2. AIEDU_PUBLIC_URL 显式设置（跨代理/CDN 确定性正确交接，拼 {base}/player）；
    3. AIEDU_SERVE_PLAYER=1 时按当前请求推导 {scheme}://{host}/player（零配置兜底）；
    4. 包内兜底常量（stdio 用户）。
    """
    if os.environ.get("AIEDU_PLAYER_URL", "").strip():
        return os.environ["AIEDU_PLAYER_URL"].strip().rstrip("/")
    if os.environ.get("AIEDU_PUBLIC_URL", "").strip():
        return os.environ["AIEDU_PUBLIC_URL"].strip().rstrip("/") + "/player"
    if os.environ.get("AIEDU_SERVE_PLAYER", "").strip() == "1":
        try:
            from fastmcp.server.dependencies import get_http_request

            req = get_http_request()
            if req is not None:
                scheme = (
                    "https" if req.headers.get("x-forwarded-proto") == "https" else req.url.scheme
                )
                host = req.headers.get("x-forwarded-host") or req.headers.get("host")
                return f"{scheme}://{host}/player"
        except Exception:  # noqa: BLE001 —— stdio/无请求上下文：落到兜底常量
            pass
    return OFFICIAL_PLAYER_URL


def _invalid_spec(spec) -> dict | None:
    """校验入参是否为 LessonSpec v2 本体；非法返回结构化错误，合法返回 None。"""
    if not isinstance(spec, dict):
        return {
            "error": "invalid_input",
            "detail": "spec 必须是 LessonSpec v2 的对象（dict）",
            "hint": "传入 generate_lesson 返回中的 spec 字段内容，而非整个返回对象",
        }
    if "spec" in spec and "activity_graph" not in spec:
        return {
            "error": "invalid_input",
            "detail": "检测到信封形状：顶层有 spec 键但没有 activity_graph",
            "hint": "传入 generate_lesson 返回中的 spec 字段内容，而非整个返回对象",
        }
    version = spec.get("schema_version")
    if version is not None and version != "2.0":
        return {
            "error": "invalid_input",
            "detail": f"spec.schema_version 必须是 '2.0'，收到 {version!r}",
        }
    graph = spec.get("activity_graph")
    if not isinstance(graph, list) or not graph:
        return {
            "error": "invalid_input",
            "detail": "spec.activity_graph 必须是非空数组",
            "hint": "传入 generate_lesson 返回中的 spec 字段内容，而非整个返回对象",
        }
    for node in graph:
        if not isinstance(node, dict) or not node.get("id") or not node.get("type"):
            return {
                "error": "invalid_input",
                "detail": "activity_graph 的每个节点必须含 id 与 type",
            }
    return None


@logged
def verify_math(expression: str, expected: str | float) -> dict:
    """数学核验：expression 精确求值是否等于 expected。

    入参：expression（如 "7x8"、"16+8"）、expected（数值或数字字符串）。
    返回：{result: verified|refuted|inconclusive|requires_review, verifier_version,
    claims: [{id, statement, status, method}], covered_claim_ids}。
    verified 只可能由 SymPy 核验产生；refuted / requires_review 如实返回。
    """
    record = verify_math_core(expression, expected)
    return {
        "result": record.result,
        "verifier_version": record.verifier_version,
        "claims": [asdict(c) for c in record.claims],
        "covered_claim_ids": list(record.covered_claim_ids),
    }


@logged
def generate_lesson(question: str, age: int | None = None) -> dict:
    """生成课程：输入题面 → 已核验、答案门控的 LessonSpec v2。

    入参：question（题面或教学内容文本）、age（可选年级）。
    返回：{lesson_id, spec, verification}——其中 **spec 是 LessonSpec v2 本体**，
    后续 get_lesson / render_lesson / submit_attempt 请传 spec 字段（不要传整个信封）。
    未覆盖题型返回 {error: "capability_gap"|"verification_failed"|..., detail}，不编造。
    """
    try:
        spec = asyncio.run(
            run_pipeline(
                {"kind": "concept", "content": question},
                curriculum_context={"grade": age} if age else None,
            )
        )
    except PipelineError as exc:
        message = str(exc)
        if "capability gap" in message:
            return {"error": "capability_gap", "detail": message}
        if "verification failed" in message:
            return {"error": "verification_failed", "detail": message}
        if "needs clarification" in message:
            return {"error": "needs_clarification", "detail": message}
        return {"error": "pipeline_error", "detail": message}
    return {
        "lesson_id": spec.lesson_id,
        "spec": spec.model_dump(mode="json"),
        "verification": spec.verification.model_dump(mode="json"),
    }


@logged
def get_lesson(
    spec: dict,
    reveal: str = "filtered",
    unlocked_ids: list[str] | None = None,
) -> dict:
    """课程获取：返回 LessonSpec v2 的投影。

    入参：**spec 本体**（generate_lesson 返回里的 spec 字段，不是整个返回对象）；
    reveal="filtered"（默认）经 answer-filtered 投影（硬约束 1：未解锁节点
    response.expected 为 null），reveal="full" 返回原始 spec。
    unlocked_ids = 已答对节点 id 集合。
    返回：{spec: <LessonSpec v2 投影>, reveal: "filtered"|"full"}。
    """
    invalid = _invalid_spec(spec)
    if invalid is not None:
        return invalid
    if reveal == "full":
        return {"spec": spec, "reveal": "full"}
    if reveal != "filtered":
        return {
            "error": "invalid_input",
            "detail": f"reveal 只能是 'filtered' 或 'full'，收到 {reveal!r}",
        }
    return {
        "spec": filtered_spec(spec, set(unlocked_ids or [])),
        "reveal": "filtered",
    }


@logged
def render_lesson(spec: dict) -> dict:
    """渲染课堂：spec 本体 → 可分享的课堂 URL（本地拼 URL，零服务端依赖）。

    入参：**spec 本体**（generate_lesson 返回里的 spec 字段）。
    返回：{url, lesson_id}——url 指向渲染页（spec 以 base64url 自包含进查询串，
    静态页渲染、可分享、不过期、无服务端状态）。
    URL base 解析顺序见 _resolve_render_base()（环境变量可完全控制渲染源）。
    """
    invalid = _invalid_spec(spec)
    if invalid is not None:
        return invalid
    payload = json.dumps(spec, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    url = f"{_resolve_render_base()}/lesson.html?spec={encoded}"
    return {"url": url, "lesson_id": spec.get("lesson_id")}


@logged
def submit_attempt(spec: dict, node_id: str, answer: str, wrong_before: int = 0) -> dict:
    """提交作答：服务端程序化判分（expected/correct_index），不信任客户端。

    入参：**spec 本体**（generate_lesson 返回里的 spec 字段）、node_id、answer、
    wrong_before（此前答错次数，用于取提示阶梯下一条）。
    返回：{correct, evidence: "independent"|"assisted", hint?}——evidence 仅两级；
    答错给提示阶梯下一条（最后一项为示范出口）。
    无程序化期望答案时返回 {error: "no_programmatic_answer"}，不猜测。
    """
    invalid = _invalid_spec(spec)
    if invalid is not None:
        return invalid
    node = next(
        (n for n in spec.get("activity_graph") or [] if n.get("id") == node_id),
        None,
    )
    if node is None:
        return {"error": "node_not_found", "detail": f"activity_graph 中不存在节点 {node_id!r}"}

    response = node.get("response") or {}
    kind = response.get("kind")
    if kind == "number":
        expected = response.get("expected")
        if expected is None:
            return {
                "error": "no_programmatic_answer",
                "detail": "该步骤无程序化期望答案，服务端不猜测",
            }
        correct = str(answer).strip() == str(expected).strip()
    elif kind == "choice":
        correct_index = response.get("correct_index")
        options = response.get("options") or []
        if correct_index is None or correct_index >= len(options):
            return {
                "error": "no_programmatic_answer",
                "detail": "该步骤无程序化正确选项，服务端不猜测",
            }
        correct = str(answer).strip() == str(options[correct_index]).strip()
    else:
        return {
            "error": "no_programmatic_answer",
            "detail": f"题型 {kind} 暂无程序化判定",
        }

    result = {"correct": correct, "evidence": "independent" if correct else "assisted"}
    if not correct:
        assistance = node.get("assistance") or []
        if assistance:
            result["hint"] = assistance[min(wrong_before, len(assistance) - 1)]
    return result
