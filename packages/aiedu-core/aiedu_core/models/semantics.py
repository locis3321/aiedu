"""LessonSpec v2 语义校验器。

JSON Schema 只检查结构；本模块检查语义：活动图可达、领域接口匹配、
主张依据、评价与学习目标对齐、预测门槛存在性。
"""

from aiedu_core.models.lesson_v2 import LessonSpecV2, PredictNode


def validate_activity_graph(spec: LessonSpecV2) -> list[str]:
    """返回违规列表；空列表表示合法。

    检查项：
    - next_ids / on_correct / on_incorrect / completion_refs / rubric_refs
      引用的 ID 必须存在；
    - activity_graph 必须可达（从首节点沿 next_ids BFS）；
    - predict 节点必须带 require_attempt 门槛（先想后看）。
    """
    errors: list[str] = []
    nodes = {n.id: n for n in spec.activity_graph}
    op_ids = {op.id for op in spec.operations}
    objective_ids = {o.id for o in spec.learning_objectives}
    assessment_ids = {a.id for a in spec.assessment}

    if not spec.activity_graph:
        errors.append("activity_graph must not be empty")
        return errors

    # ID 唯一性
    if len(nodes) != len(spec.activity_graph):
        errors.append("activity_graph node ids must be unique")

    # 引用完整性
    for node in spec.activity_graph:
        for ref in node.objective_refs:
            if ref not in objective_ids:
                errors.append(f"{node.id}: unknown objective_ref {ref}")
        for ref in node.completion_refs:
            if ref not in assessment_ids:
                errors.append(f"{node.id}: unknown completion_ref {ref}")
        if node.next_ids:
            for ref in node.next_ids:
                if ref != "__end__" and ref not in nodes:
                    errors.append(f"{node.id}: unknown next_id {ref}")
        if isinstance(node, PredictNode):
            if node.gate.mode != "require_attempt":
                errors.append(
                    f"{node.id}: predict node must use gate require_attempt "
                    f"(got {node.gate.mode})"
                )
            for ref in node.on_correct:
                if ref not in op_ids:
                    errors.append(f"{node.id}: on_correct references unknown action {ref}")
            if node.on_incorrect:
                for ref in node.on_incorrect:
                    if ref not in op_ids:
                        errors.append(
                            f"{node.id}: on_incorrect references unknown action {ref}"
                        )

    # 可达性：从首节点 BFS
    reachable: set[str] = set()
    queue = [spec.activity_graph[0].id]
    while queue:
        nid = queue.pop()
        if nid in reachable:
            continue
        reachable.add(nid)
        node = nodes.get(nid)
        if node is None:
            continue
        for ref in node.next_ids or []:
            if ref != "__end__":
                queue.append(ref)
    for node in spec.activity_graph:
        if node.id not in reachable:
            errors.append(f"{node.id}: unreachable from entry node")

    # 「先想后看」课程级门槛：解题类场景（problem）必须至少一个尝试类节点
    # 带 require_attempt / require_correct_or_assisted 门槛；概念课、探究课
    # 由教学目标决定，不把问答节奏强加给概念讲授与开放探究（R2 §6）。
    attempt_gates = {"require_attempt", "require_correct_or_assisted"}
    attempt_nodes = [
        n for n in spec.activity_graph
        if getattr(n, "gate", None) is not None and n.gate.mode in attempt_gates
    ]
    if spec.teaching_request.kind == "problem" and not attempt_nodes:
        errors.append(
            "problem lesson requires at least one attempt-gated interaction "
            "(先想后看)"
        )

    return errors
