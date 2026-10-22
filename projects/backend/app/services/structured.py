"""LLM 结构化输出约束（业界标准方案，2026-10-10 调研落地）。

问题：Flash 模型对复杂 prompt 的结构输出偶发不合 schema（缺冒号/裸控制字符/缺字段），
导致真实 LLM 集成测试 flaky。方案组合（参考 OpenAI Structured Outputs / Mistral strict
json_schema / outputguard repair-loop）：

1. **解码级约束**：`response_format={"type":"json_schema","strict":true}`——模型只能产出
   符合 schema 的 token（本网关实测：简单 schema 3/3、复杂嵌套 schema 3/4，唯一失败为空响应）；
2. **验证-修复循环**：应用层仍做 Pydantic 校验（strict 也不是绝对保证），失败时把具体
   校验错误回传给模型做定向修复（bounded，最多2次修复）；
3. **空响应/语法残留兜底**：`_extract_json` 容错解析保留为最后手段。
"""

from pydantic import BaseModel

# Designer 输出载荷的顶层结构（与 pipeline._plan 消费的 payload 对应）
_NODE_TYPES = [
    "predict",
    "observe",
    "construct",
    "manipulate",
    "explain",
    "prove",
    "retrieve",
    "reflect",
]

_NODE_PROPERTIES = {
    "id": {"type": "string"},
    "type": {"type": "string", "enum": _NODE_TYPES},
    "prompt": {"type": ["string", "null"]},
    "narration": {"type": ["string", "null"]},
    "response": {
        "type": ["object", "null"],
        "properties": {
            "kind": {"type": ["string", "null"]},
            "options": {"type": ["array", "null"], "items": {"type": "string"}},
            "correct_index": {"type": ["integer", "null"]},
            "expected": {"type": ["string", "null"]},
            "unit": {"type": ["string", "null"]},
        },
        "required": ["kind"],
        "additionalProperties": False,
    },
    "gate": {
        "type": ["object", "null"],
        "properties": {
            "mode": {
                "type": ["string", "null"],
                "enum": [
                    "require_attempt",
                    "require_correct_or_assisted",
                    "learner_continue",
                    "exploration_condition",
                ],
            },
            "max_assists": {"type": ["integer", "null"]},
        },
        "required": ["mode"],
        "additionalProperties": False,
    },
    "assistance": {"type": ["array", "null"], "items": {"type": "string"}},
    "on_correct": {"type": ["array", "null"], "items": {"type": "string"}},
    "on_incorrect": {"type": ["array", "null"], "items": {"type": ["string", "null"]}},
    "next_ids": {"type": ["array", "null"], "items": {"type": ["string", "null"]}},
}


def build_designer_schema() -> dict:
    """OpenAI json_schema（strict）格式的 Designer 输出约束。

    覆盖全部节点类型的字段并集；解码级约束保证合法 JSON + 已知键集合，
    结构完整性仍由 LessonSpecV2.model_validate（应用层）把关。
    """
    return {
        "name": "lesson_design",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "teaching_design": {
                    "type": ["object", "null"],
                    "properties": {
                        "modes": {"type": ["array", "null"], "items": {"type": "string"}}
                    },
                    "required": ["modes"],
                    "additionalProperties": False,
                },
                "activity_graph": {
                    "type": ["array", "null"],
                    "items": {
                        "type": ["object", "null"],
                        **{"properties": dict(_NODE_PROPERTIES)},
                        # properties keys must match exactly; required only id/type
                        # （其余字段可缺省，由应用层校验补足语义）
                        **{"required": ["id", "type"]},
                        **{"additionalProperties": False},
                    },
                },
            },
            # teaching_design/activity_graph 可空时模型可能输出 null——应用层显式失败
            # （缺失必填事实不自动兜底），因此此处 required 仅约束顶层键存在。
            **{"required": ["teaching_design", "activity_graph"]},
            **{"additionalProperties": False},
        },
    }


def build_repair_prompt(original_prompt: str, raw_output: str, errors: str) -> str:
    """定向修复提示：把校验错误回传给模型（outputguard / repair-loop 模式）。"""
    return (
        original_prompt
        + "\n\n【上一次输出不符合要求】\n"
        + raw_output[:2000]
        + "\n\n【校验错误】\n"
        + errors[:2000]
        + "\n\n请修正以上问题后，只输出一个完整的 JSON 对象，不要任何解释或代码块标记。"
    )


def model_json_schema_strict(model_cls: type[BaseModel]) -> dict:
    """Pydantic → OpenAI strict json_schema（顶层包装）。

    注：OpenAI strict 要求 additionalProperties=false 且字段齐全；复杂判别联合
    建议手写 schema（见 build_designer_schema），此函数仅用于简单扁平模型。
    """
    js = model_cls.model_json_schema()
    return {
        "name": model_cls.__name__,
        "strict": True,
        # strict 模式要求所有属性出现在 required；此处按 pydantic required 推断，
        # optional 字段以 anyOf [T, null] 表达并保持非 required。
        **{"schema": js},
    }
