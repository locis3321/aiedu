"""answer-filtered 投影：先想后看的 API 语义（AGENTS 硬约束 1）。

对 LessonSpec v2 的 dict 形式做服务端过滤投影（移植自原
learning/service.py `_filtered_spec`，本项目最好的实现）：
- predict/construct/manipulate：未解锁节点的 response.expected / correct_index 置空；
- observe：全部门槛未完成前 narration 置空（结论文本不下发）；
- verification.claims[].statement / replay：均承载完整答案，未完成前不下发；
- _meta（生成期门禁等内部元数据）永不下发。

保留结构（locked 标记供客户端占位渲染）。
"""

from aiedu_core.models.lesson_v2 import LessonSpecV2


def filtered_spec(spec_dict: dict, unlocked_ids: set[str]) -> dict:
    """过滤规则见模块 docstring；unlocked_ids = 已答对步骤 id 集合。"""
    all_gated_ids = [
        n["id"] for n in spec_dict.get("activity_graph") or [] if n.get("gate")
    ]
    all_gates_done = bool(all_gated_ids) and all(g in unlocked_ids for g in all_gated_ids)

    out_nodes = []
    for node in spec_dict.get("activity_graph") or []:
        n = dict(node)
        ntype = n.get("type")
        if ntype == "observe":
            if not all_gates_done:
                n["narration"] = ""
                n["locked"] = True
            out_nodes.append(n)
            continue
        resp = n.get("response")
        if isinstance(resp, dict) and n.get("id") not in unlocked_ids:
            resp = dict(resp)
            resp["correct_index"] = None
            resp["expected"] = None
            n["response"] = resp
            n["locked"] = True
        out_nodes.append(n)

    result = dict(spec_dict)
    result["activity_graph"] = out_nodes
    if not all_gates_done:
        ver = result.get("verification")
        if isinstance(ver, dict) and ver.get("claims"):
            result["verification"] = {
                **ver,
                "claims": [{**c, "statement": ""} for c in ver["claims"]],
            }
        # 完整回放 = 完整解法序列，未完成前不可见
        result.pop("replay", None)
    result.pop("_meta", None)
    return result


def filtered_spec_from_model(spec: LessonSpecV2, unlocked_ids: set[str]) -> dict:
    """LessonSpecV2 → answer-filtered dict 投影。"""
    return filtered_spec(spec.model_dump(mode="json"), unlocked_ids)
