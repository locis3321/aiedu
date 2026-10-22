"""LessonSpec v2：课程数据契约（Pydantic v2）。

设计依据 R2 §6：
- activity_graph 节点使用判别联合（type 为 discriminator）；
- 引导问答节点含 prompt/response/gate/on_correct/on_incorrect/assistance；
- 展示概念的节点无需伪造一道选择题；
- on_correct 只允许引用已有 action ID，不允许任意状态补丁；
- verification 由服务端核验器写入，LLM 的 verified=true 不具备发布权限。
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from aiedu_core.models.teaching_request import TeachingRequestInput

# ---------------------------------------------------------------------------
# verification：核验凭据（服务端核验器生成）
# ---------------------------------------------------------------------------

class ClaimEvidence(BaseModel):
    """单条数学主张的核验证据。"""

    id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    status: Literal["verified", "refuted", "inconclusive", "requires_review"]
    method: str = Field(
        min_length=1,
        description="证据类型：精确计算 / 形式推导 / 数值实验 / 教研审核等",
    )


class Verification(BaseModel):
    """核验凭据：全部必需主张被覆盖且均为 verified 时才允许 verified=True。"""

    verified: bool = False
    verifier_version: str = Field(min_length=1)
    normalized_problem_hash: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    claims: list[ClaimEvidence] = Field(default_factory=list)
    covered_claim_ids: list[str] = Field(default_factory=list)
    report_ref: str | None = None
    mode: Literal["math_verified_applicable", "no_math_claims"] = (
        "math_verified_applicable"
    )


# ---------------------------------------------------------------------------
# objectives / assessment / teaching design / domain models / operations
# ---------------------------------------------------------------------------

class LearningObjective(BaseModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)


class AssessmentItem(BaseModel):
    """按学习目标定义评价证据、答案规则或论证量规。"""

    id: str = Field(min_length=1)
    objective_refs: list[str] = Field(default_factory=list)
    evidence_kind: Literal[
        "numeric_answer", "expression", "classification", "construction",
        "proof_step", "explanation", "dataset",
    ]
    rubric_refs: list[str] = Field(default_factory=list)


class TeachingDesign(BaseModel):
    """选用教学模式、资源、策略及其适用条件；计算策略可选。"""

    modes: list[str] = Field(
        default_factory=list,
        description="教学模式：讲授 / 引导 / 探究 / 论证 / 练习 / 复习等",
    )
    strategy_refs: list[str] = Field(
        default_factory=list,
        description="策略模板引用，如 make_ten@v1；未命中策略时为空",
        examples=[["make_ten@v1"]],
    )
    skill_refs: list[str] = Field(
        default_factory=list,
        description="使用的 Claude-style Teaching Skill ID（如 make-ten）",
        examples=[["make-ten"]],
    )


class DomainModelDef(BaseModel):
    """领域模型声明：带领域名与插件版本。"""

    id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    plugin_version: str = Field(min_length=1)


class OperationDef(BaseModel):
    """命名空间领域操作，例如 arithmetic.transfer_units。"""

    id: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_.]*$",
        description="命名空间操作 ID，如 arithmetic.transfer_units",
        examples=["arithmetic.transfer_units"],
    )


# ---------------------------------------------------------------------------
# response spec：回答形式（判别联合）
# ---------------------------------------------------------------------------

class ResponseChoice(BaseModel):
    kind: Literal["choice"]
    options: list[str] = Field(min_length=2)
    correct_index: int | None = Field(
        default=None,
        description="干扰项应基于常见错误模式；开放讨论时可无正确答案",
    )
    distractors_from: list[str] = Field(
        default_factory=list, description="关联的常见错误模式 ID"
    )


class ResponseNumber(BaseModel):
    kind: Literal["number"]
    unit: str | None = None
    allow_expression: bool = False
    expected: str | None = Field(
        default=None,
        description="程序化计算的期望答案（策略模板填充，不由LLM猜）",
    )


class ResponseExpression(BaseModel):
    kind: Literal["expression"]
    variables: list[str] = Field(default_factory=list)


class ResponseConstruction(BaseModel):
    kind: Literal["construction"]
    allowed_ops: list[str] = Field(default_factory=list)


class ResponseManipulation(BaseModel):
    kind: Literal["manipulation"]
    allowed_actions: list[str] = Field(default_factory=list)


class ResponseProofStep(BaseModel):
    kind: Literal["proof_step"]
    allowed_rules: list[str] = Field(default_factory=list)


class ResponseExplanation(BaseModel):
    kind: Literal["explanation"]
    rubric_refs: list[str] = Field(default_factory=list)


class ResponseDataset(BaseModel):
    kind: Literal["dataset"]
    n_samples: int | None = Field(default=None, ge=1)


ResponseSpec = Annotated[
    ResponseChoice
    | ResponseNumber
    | ResponseExpression
    | ResponseConstruction
    | ResponseManipulation
    | ResponseProofStep
    | ResponseExplanation
    | ResponseDataset,
    Field(discriminator="kind"),
]


class Gate(BaseModel):
    """解锁门槛：由教学目标决定，不强制全课预测优先。"""

    mode: Literal[
        "require_attempt",
        "require_correct_or_assisted",
        "learner_continue",
        "exploration_condition",
    ]
    max_assists: int = Field(default=3, ge=0)


# ---------------------------------------------------------------------------
# activity_graph：判别联合节点（type 为 discriminator）
# ---------------------------------------------------------------------------

class ActivityNodeBase(BaseModel):
    id: str = Field(min_length=1)
    type: str
    objective_refs: list[str] = Field(default_factory=list)
    model_refs: list[str] = Field(default_factory=list)
    representation_refs: list[str] = Field(default_factory=list)
    completion_refs: list[str] = Field(
        default_factory=list, description="完成条件引用的 assessment id"
    )
    next_ids: list[str] | None = Field(
        default=None, description="后继 step ID；None 或 ['__end__'] 表示结束"
    )


class ObserveNode(ActivityNodeBase):
    """展示概念/例子——无需伪造一道选择题。"""

    type: Literal["observe"]
    narration: str = Field(min_length=1)


class PredictNode(ActivityNodeBase):
    """预测/尝试节点：「先想后看」门槛所在。"""

    type: Literal["predict"]
    prompt: str = Field(min_length=1)
    response: ResponseSpec
    gate: Gate
    assistance: list[str] = Field(
        default_factory=list,
        description="提示序列；最后一项为示范出口（示范后标记 assisted）",
    )
    on_correct: list[str] = Field(
        default_factory=list,
        description="引用已有 action ID（不允许任意状态补丁）；无状态转移时可空",
    )
    on_incorrect: list[str] | None = None


class ConstructNode(ActivityNodeBase):
    """构造节点：完成满足约束的构造（几何作图、表达式构造等）。"""

    type: Literal["construct"]
    prompt: str = Field(min_length=1)
    response: ResponseSpec
    gate: Gate
    on_correct: list[str] = Field(default_factory=list)


class ManipulateNode(ActivityNodeBase):
    """操作节点：拖动滑块/参数等可操作探索。"""

    type: Literal["manipulate"]
    prompt: str = Field(min_length=1)
    allowed_actions: list[str] = Field(default_factory=list)
    gate: Gate


class ExplainNode(ActivityNodeBase):
    """解释节点：开放回答保留量规与不确定性，不强行压成单一布尔正确。"""

    type: Literal["explain"]
    prompt: str = Field(min_length=1)
    rubric_refs: list[str] = Field(default_factory=list)


class ProveNode(ActivityNodeBase):
    """证明节点：补充论据、判断合法步骤或提交论证。"""

    type: Literal["prove"]
    prompt: str = Field(min_length=1)
    response: ResponseProofStep
    gate: Gate


class RetrieveNode(ActivityNodeBase):
    """检索/练习节点：选择题作为一种支架，按需使用。"""

    type: Literal["retrieve"]
    prompt: str = Field(min_length=1)
    response: ResponseChoice
    gate: Gate


class ReflectNode(ActivityNodeBase):
    """反思节点：回顾推理步骤或学习过程。"""

    type: Literal["reflect"]
    prompt: str = Field(min_length=1)


ActivityNode = Annotated[
    ObserveNode
    | PredictNode
    | ConstructNode
    | ManipulateNode
    | ExplainNode
    | ProveNode
    | RetrieveNode
    | ReflectNode,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# representations / replay / render / LessonSpec v2
# ---------------------------------------------------------------------------

class RepresentationBinding(BaseModel):
    """领域模型到符号/图形/图表/表格/文字的绑定。"""

    id: str = Field(min_length=1)
    model_refs: list[str] = Field(default_factory=list)
    kind: Literal["symbolic", "diagram_2d", "geometry_3d", "chart", "table", "text"]
    adapter_version: str | None = None


class ReplaySpec(BaseModel):
    """可回放活动的事件及检查点；保存探究输入与随机种子，不另造演示逻辑。"""

    checkpoints: list[str] = Field(default_factory=list)
    random_seed: int | None = None


class RenderSpec(BaseModel):
    """渲染配置：运行时版本、适配器、资源清单、布局策略。"""

    runtime_version: str = Field(min_length=1)
    representation_adapter_versions: dict[str, str] = Field(default_factory=dict)
    asset_manifest_ref: str | None = None
    layout_strategy: str = Field(
        default="responsive",
        description="布局策略：responsive / fixed；生产门禁按视口检查",
    )


class PresentationSpec(BaseModel):
    """儿童友好呈现配置：由意图/全局政策决定，不由 LLM 自由写 UI。

    受控枚举 + 场景隐喻标识；播放器按主题渲染安全组件，不允许任意样式代码。
    """

    age_band: Literal[
        "lower_primary", "upper_primary", "middle_school", "high_school", "unknown"
    ] = "unknown"
    visual_theme: Literal[
        "storybook", "candy_shop", "space_adventure",
        "lab_exploration", "clean_school", "geometry_board",
    ] = "clean_school"
    scene_metaphor: str | None = Field(
        default=None,
        description="场景隐喻标识，如 berry_basket / star_energy / candy_box",
    )
    feedback_tone: Literal["encouraging", "exploratory", "challenge"] = (
        "encouraging"
    )
    motion_style: Literal["playful", "calm", "precise"] = "calm"
    interaction_affordances: list[str] = Field(
        default_factory=list,
        description="交互方式：type / tap / drag / arrange",
    )


class LessonSpecV2(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    lesson_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    revision: int = Field(ge=1)
    teaching_request: TeachingRequestInput
    curriculum_context: dict | None = None
    learning_objectives: list[LearningObjective] = Field(min_length=1)
    domain_models: list[DomainModelDef] = Field(default_factory=list)
    teaching_design: TeachingDesign
    verification: Verification
    initial_states: dict[str, dict] = Field(
        default_factory=dict,
        description="各领域模型初始状态；避免重复派生量",
    )
    operations: list[OperationDef] = Field(default_factory=list)
    activity_graph: list[ActivityNode] = Field(min_length=1)
    assessment: list[AssessmentItem] = Field(default_factory=list)
    replay: ReplaySpec | None = None
    representations: list[RepresentationBinding] = Field(default_factory=list)
    render: RenderSpec
    presentation: PresentationSpec | None = Field(
        default=None,
        description="儿童友好呈现配置；缺省时播放器使用安全默认主题",
    )
