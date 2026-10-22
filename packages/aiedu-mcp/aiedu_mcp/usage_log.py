"""结构化使用日志（可选、零侵入）。

- 落盘路径由环境变量 `AIEDU_USAGE_LOG` 指定；**未设置 → 完全不落盘、不改变任何行为**。
- 每行一个 JSON：`{ts, tool, args(摘要), result, duration_ms}`。
- args 只记摘要（题型 / 长度 / 节点数 / reveal 等），**不记完整题面、不记完整 spec、不记密钥**。
- result 取值：ok / capability_gap / invalid_input / player_unavailable / error 等，
  由 tool 返回体的 error 字段归类（未归一化前保留原始错误码）。
- 日志写入失败一律静默：观测不得影响主链路。
"""

import functools
import json
import os
import time
from contextvars import ContextVar
from datetime import datetime, timezone

LOG_ENV = "AIEDU_USAGE_LOG"

# caller 上下文（架构增量 v1 · C3）：ASGI 层（鉴权/限流）写入，工具日志读取。
# 取值枚举：stdio/未识别 → None（字段缺省）；HTTP 匿名 → "anon:<sha256(ip)[:12]>"；
# 有 Bearer token → "token:<id>"。定义在本模块，ratelimit.py 单向引用（避免循环依赖）。
CALLER = ContextVar("aiedu_caller", default=None)


def log_path() -> str | None:
    """日志路径；未配置或为空 → None（不落盘）。"""
    raw = os.environ.get(LOG_ENV)
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _kind_of(text: str) -> str:
    """题型摘要：只分类，不留原文。"""
    lowered = text.replace(" ", "")
    if any(word in lowered for word in ("分数", "等分", "平均分", "几分之一")):
        return "fraction"
    if any(op in lowered for op in ("+", "-", "×", "÷", "*", "x")) and any(
        ch.isdigit() for ch in lowered
    ):
        return "arith"
    return "text"


def _node_count(spec) -> int:
    if isinstance(spec, dict):
        graph = spec.get("activity_graph")
        if isinstance(graph, list):
            return len(graph)
    return 0


def summarize(tool: str, args: tuple, kwargs: dict) -> dict:
    """参数摘要：题型/长度/节点数，绝不含完整题面或 spec 内容。"""
    summary: dict = {}
    if tool == "generate_lesson":
        question = kwargs.get("question") or (args[0] if args else "")
        question = str(question)
        summary["kind"] = _kind_of(question)
        summary["question_len"] = len(question)
        if kwargs.get("age") is not None:
            summary["age"] = kwargs.get("age")
    elif tool == "verify_math":
        expression = str(kwargs.get("expression") or (args[0] if args else ""))
        summary["kind"] = _kind_of(expression)
        summary["expression_len"] = len(expression)
    elif tool == "get_lesson":
        spec = kwargs.get("spec") or (args[0] if args else None)
        summary["nodes"] = _node_count(spec)
        summary["reveal"] = kwargs.get("reveal", "filtered")
        unlocked = kwargs.get("unlocked_ids") or []
        summary["unlocked"] = len(unlocked)
    elif tool == "submit_attempt":
        spec = kwargs.get("spec") or (args[0] if args else None)
        summary["nodes"] = _node_count(spec)
        summary["node_id"] = kwargs.get("node_id")
        answer = str(kwargs.get("answer") or "")
        summary["answer_len"] = len(answer)
    elif tool == "render_lesson":
        spec = kwargs.get("spec") or (args[0] if args else None)
        summary["nodes"] = _node_count(spec)
    return summary


def classify(result) -> str:
    """结果状态：ok / capability_gap / invalid_input / player_unavailable / error 等。

    约定（任务书口径）：result ∈ {ok, capability_gap, invalid_input, error}；
    数学结论（verified/refuted/...）不是工具失败，另记在 detail 字段。
    """
    if isinstance(result, dict):
        error = result.get("error")
        if error:
            return str(error)
    return "ok"


def detail_of(result) -> str | None:
    """可选细节：verify_math 的数学结论（verified/refuted/inconclusive/requires_review）。"""
    if isinstance(result, dict):
        value = result.get("result")
        if value in {"verified", "refuted", "inconclusive", "requires_review"}:
            return str(value)
    return None


def append_line(path: str, payload: dict) -> None:
    """追加一行 JSONL；失败静默（观测不得影响主链路）。"""
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 —— 落盘失败不影响 tool 行为
        pass


def logged(func):
    """tool 调用记录装饰器；未配置 AIEDU_USAGE_LOG 时是零开销直通。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        path = log_path()
        if path is None:
            return func(*args, **kwargs)
        started = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 —— 记录后原样抛出
            append_line(
                path,
                {
                    "ts": _now_iso(),
                    "tool": func.__name__,
                    "v": 1,
                    "args": summarize(func.__name__, args, kwargs),
                    "result": "error",
                    "error_type": type(exc).__name__,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    **({"caller": CALLER.get()} if CALLER.get() is not None else {}),
                },
            )
            raise
        append_line(
            path,
            {
                "ts": _now_iso(),
                "tool": func.__name__,
                "v": 1,
                "args": summarize(func.__name__, args, kwargs),
                "result": classify(result),
                "duration_ms": int((time.perf_counter() - started) * 1000),
                **({"detail": detail_of(result)} if detail_of(result) else {}),
                **({"caller": CALLER.get()} if CALLER.get() is not None else {}),
            },
        )
        return result

    return wrapper
