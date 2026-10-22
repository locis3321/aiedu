/**
 * 活动图运行时：会话状态、节点执行、gate 判定、assistance 提示、
 * 事件记录；教学操作与回放执行同一组 action（R2 §7）。
 */

import { AnimationController } from "./animation";
import { arithmeticPlugin, type DomainAction, type DomainPlugin, type DomainState } from "./domain-plugin";

export type SessionStatus =
  | "ready"
  | "active"
  | "awaiting_response"
  | "feedback"
  | "completed"
  | "suspended";

export interface LessonSpecNode {
  id: string;
  type: string;
  prompt?: string;
  response?: { kind: string; [k: string]: unknown };
  gate?: { mode: string; max_assists?: number };
  assistance?: string[];
  on_correct?: string[];
  on_incorrect?: string[];
  narration?: string;
  next_ids?: string[] | null;
}

export interface LessonSpecJson {
  schema_version: string;
  lesson_id: string;
  revision: number;
  verification: { verified: boolean };
  operations?: { id: string }[];
  initial_states?: Record<string, DomainState>;
  activity_graph: LessonSpecNode[];
  presentation?: {
    age_band?: string;
    visual_theme?: string;
    scene_metaphor?: string;
    feedback_tone?: string;
    motion_style?: string;
    interaction_affordances?: string[];
  };
}

export interface FeedbackResult {
  correct: boolean;
  feedback: string;
  assisted: boolean;
  nextNodeId: string | null;
  /** judged=false：spec 未声明程序化期望答案（filtered 形态），交服务端判定 */
  judged?: boolean;
}

/** 判分模式：
 * - derived：spec 未声明 expected 时按领域状态派生期望值（旧行为，本地 demo 用）；
 * - declared：只用 spec 声明的 expected；未声明则不判分，等待服务端 submit_attempt。
 * 答案门控只存在于 spec 投影层：渲染层不得自己派生答案（避免第二真相来源）。
 */
export type JudgeMode = "derived" | "declared";

export interface RuntimeEvent {
  nodeId: string;
  kind: "enter" | "answer" | "assist" | "replay" | "reset";
  detail: unknown;
}

export class ActivityRuntime {
  private status: SessionStatus = "ready";
  private currentNodeId = "";
  private state: DomainState = {};
  private assistsUsed = 0;
  private answered = new Set<string>();
  readonly events: RuntimeEvent[] = [];
  private plugin: DomainPlugin;

  constructor(
    private spec: LessonSpecJson,
    private anim: AnimationController,
    plugin: DomainPlugin = arithmeticPlugin,
    private onRender?: (state: DomainState, nodeId: string) => void,
    private judgeMode: JudgeMode = "derived",
  ) {
    this.plugin = plugin;
    this.state = { ...(spec.initial_states?.["m-arithmetic"] ?? {}) };
    this.currentNodeId = spec.activity_graph[0]?.id ?? "";
  }

  start(): void {
    this.status = "active";
    this.emit("enter", this.currentNodeId, null);
    this.onRender?.(this.state, this.currentNodeId);
  }

  get sessionStatus(): SessionStatus {
    return this.status;
  }

  get current(): LessonSpecNode | undefined {
    return this.spec.activity_graph.find((n) => n.id === this.currentNodeId);
  }

  /** gate 判定：require_attempt / require_correct_or_assisted / learner_continue。 */
  private gateAllowsAnswer(): boolean {
    const node = this.current;
    if (!node?.gate) return true;
    const mode = node.gate.mode;
    if (mode === "require_attempt") return true;
    if (mode === "require_correct_or_assisted") return true;
    return true; // learner_continue / exploration_condition：直接继续
  }

  /** assistance：提示序列；最后一项为示范出口（示范后标记 assisted）。 */
  assist(): string | null {
    const node = this.current;
    if (!node?.assistance?.length) return null;
    if (this.assistsUsed >= (node.gate?.max_assists ?? node.assistance.length)) {
      return null;
    }
    const hint = node.assistance[this.assistsUsed];
    this.assistsUsed += 1;
    this.emit("assist", node.id, hint);
    return hint;
  }

  /** 回答：gate + on_correct action（与回放同源）；返回反馈与下一节点。 */
  answer(value: unknown): FeedbackResult {
    const node = this.current;
    if (!node) {
      return {
        correct: false,
        feedback: "no active node",
        assisted: false,
        nextNodeId: null,
        judged: false,
      };
    }
    if (!this.gateAllowsAnswer()) {
      return {
        correct: false,
        feedback: "请先尝试作答",
        assisted: false,
        nextNodeId: null,
        judged: false,
      };
    }
    const verdict = this.evaluate(node, value);
    const assisted = this.assistsUsed > 0;
    this.answered.add(node.id);
    this.emit("answer", node.id, { value, correct: verdict === true, assisted });

    if (verdict === null) {
      // spec 未声明期望答案（filtered 形态）：不在前端判定，交服务端 submit_attempt
      return {
        correct: false,
        feedback: "已提交，等待服务端判定",
        assisted,
        nextNodeId: null,
        judged: false,
      };
    }

    if (verdict) {
      for (const actionId of node.on_correct ?? []) {
        this.applyAction(actionId);
      }
      const next = this.nextOf(node);
      if (next) {
        this.currentNodeId = next;
        this.emit("enter", next, null);
        this.onRender?.(this.state, next);
      } else {
        this.status = "completed";
      }
      return {
        correct: true,
        feedback: "答对了！",
        assisted,
        nextNodeId: next ?? null,
        judged: true,
      };
    }
    return {
      correct: false,
      feedback: "再想想，需要提示吗？",
      assisted,
      nextNodeId: null,
      judged: true,
    };
  }

  /** evaluate：数字/表达式回答按领域规则判定。
   * 返回 null = 无法判定（declared 模式下 spec 未声明 expected）。
   */
  private evaluate(node: LessonSpecNode, value: unknown): boolean | null {
    const kind = node.response?.kind ?? "number";
    if (kind === "number") {
      const declared = (node.response as { expected?: unknown })?.expected;
      if (declared !== undefined && declared !== null) {
        return Number(value) === Number(declared);
      }
      if (this.judgeMode === "declared") return null;
      return Number(value) === Number(this.expectedFor(node.id));
    }
    if (kind === "choice") {
      const options = node.response?.options as string[] | undefined;
      const idx = node.response?.correct_index;
      if (options && idx !== undefined && idx !== null) {
        return Number(value) === Number(idx);
      }
      if (this.judgeMode === "declared") return null;
      return false; // construction/proof_step/dataset：由领域插件扩展
    }
    return false; // construction/proof_step/dataset：由领域插件扩展
  }

  /** expectedFor：从领域状态派生期望值（凑十：补数/拆后left/总和）。 */
  private expectedFor(nodeId: string): number {
    const left = Number(this.state.left ?? 0);
    const right = Number(this.state.right ?? 0);
    switch (nodeId) {
      case "find-complement":
        return Math.max(10 - right, 0);
      case "find-source":
        // “借出几颗”＝补数；转移动作执行后 left/right 更新
        return Math.max(10 - right, 0);
      case "find-sum":
        return left + right + Number(this.state.inTransit ?? 0);
      default:
        return Number(this.state.total ?? left + right);
    }
  }

  /** continue：非交互节点（observe/explain/reflect）由学习者点击继续。 */
  continue(): void {
    const node = this.current;
    if (!node) return;
    const next = this.nextOf(node);
    if (next) {
      this.currentNodeId = next;
      this.emit("enter", next, null);
      this.onRender?.(this.state, next);
    } else {
      this.status = "completed";
    }
  }

  /** applyAction：教学操作与回放共用同一组 action。 */
  applyAction(actionId: string): void {
    const [domain, ...rest] = actionId.split(".");
    void domain;
    let action: DomainAction;
    if (actionId === "arithmetic.transfer_units") {
      const k = Math.max(10 - Number(this.state.right ?? 0), 0);
      action = { id: actionId, params: { k } };
    } else {
      action = { id: actionId };
    }
    const before = { ...this.state };
    const after = this.plugin.reduce(this.state, action);
    const violations = this.plugin.validateTransition(before, action, after);
    if (violations.length > 0) {
      throw new Error(`invalid transition ${actionId}: ${violations.join("; ")}`);
    }
    this.state = after;
    this.onRender?.(this.state, this.currentNodeId);
    void rest;
  }

  /** replay：从初始状态按相同 action 序列播放（同源，不修改作答成绩）。 */
  replay(): void {
    const runId = this.anim.reset();
    const initial = { ...(this.spec.initial_states?.["m-arithmetic"] ?? {}) };
    this.state = initial;
    const tl = this.anim.createTimeline(runId);
    // transfer → group_total（演示动画序列）
    tl.add(() => {
      const k = Math.max(10 - Number(initial.right ?? 0), 0);
      const after = arithmeticPlugin.reduce(initial, { id: "arithmetic.transfer_units", params: { k } });
      this.state = after;
      this.onRender?.(this.state, this.currentNodeId);
    });
    tl.add(() => {
      const after = arithmeticPlugin.reduce(this.state, { id: "arithmetic.group_total" });
      this.state = after;
      this.onRender?.(this.state, this.currentNodeId);
      this.status = "active";
    });
    tl.play();
    this.emit("replay", this.currentNodeId, runId);
  }

  /** reset：终止旧时间线、递增 run_id，使过期回调失效。 */
  reset(): void {
    this.anim.reset();
    this.status = "ready";
    this.state = { ...(this.spec.initial_states?.["m-arithmetic"] ?? {}) };
    this.answered.clear();
    this.assistsUsed = 0;
    this.currentNodeId = this.spec.activity_graph[0]?.id ?? "";
    this.emit("reset", "", null);
  }

  private nextOf(node: LessonSpecNode): string | null {
    const next = node.next_ids ?? [];
    if (next.length === 0 || next[0] === "__end__") return null;
    return next[0];
  }

  private emit(kind: RuntimeEvent["kind"], nodeId: string, detail: unknown): void {
    this.events.push({ nodeId, kind, detail });
  }
}
