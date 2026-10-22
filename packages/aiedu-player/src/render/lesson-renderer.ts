/**
 * renderLesson：LessonSpec v2 → 可交互课堂（纯浏览器侧渲染 API）。
 *
 * 关键约束（AGENTS 硬约束 1 / 5）：
 * - 答案门控只存在于 spec 投影层：渲染层只忠实呈现 spec，不自己判断"要不要显示答案"，
 *   也不在前端派生答案（judgeMode 默认 declared：spec 未声明 expected 时不判分，
 *   交服务端 submit_attempt 判定）。
 * - 一屏一任务：同一时刻只有当前 activity 节点可见。
 * - 儿童界面可用性：可点元素 ≥48px、单指可操作。
 */

import { ActivityRuntime, type JudgeMode, type LessonSpecJson } from "../core/activity-runtime";
import { AnimationController } from "../core/animation";
import { checkLayoutInvariants } from "../core/layout";
import { BlocksRenderer } from "./blocks-renderer";

export interface RenderLessonOptions {
  /** 判分模式：declared（默认，只用 spec 声明的 expected）/ derived（旧行为，本地 demo） */
  judgeMode?: JudgeMode;
  /** 提交作答回调：宿主可转发到服务端 submit_attempt 拿判定结果 */
  onAttempt?: (nodeId: string, answer: string) => void;
  /** 是否渲染算术块图（有 arithmetic 初始状态时） */
  showBlocks?: boolean;
}

export interface LessonView {
  runtime: ActivityRuntime;
  container: HTMLElement;
  /** 当前可见节点 id（渲染层只呈现当前任务） */
  activeNodeId: string | null;
  destroy(): void;
}

const INTERACTIVE_TYPES = ["predict", "construct", "manipulate", "retrieve", "prove"];

const STYLES = `
.aiedu-lesson { font-family: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif; color: #5b4636; }
.aiedu-lesson .lesson-question { font-size: 20px; margin-bottom: 8px; }
.aiedu-lesson .lesson-node { background: #fffdf8; border: 2px solid #f5d9b8; border-radius: 20px; padding: 16px; margin-bottom: 12px; }
.aiedu-lesson .lesson-node[hidden] { display: none !important; }
.aiedu-lesson .node-prompt { font-size: 18px; margin-bottom: 10px; }
.aiedu-lesson .node-narration { font-size: 17px; line-height: 1.7; }
.aiedu-lesson .lesson-controls { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; align-items: center; }
.aiedu-lesson button {
  min-width: 48px; min-height: 48px; font-size: 16px; border-radius: 14px;
  border: none; cursor: pointer; padding: 0 16px;
  background: #fff3e2; color: #a3552e; box-shadow: inset -1px -2px 0 rgba(163,85,46,.12);
}
.aiedu-lesson button.primary { background: #ff8a5c; color: #fff; }
.aiedu-lesson input {
  min-height: 48px; font-size: 18px; width: 140px; border-radius: 14px;
  border: 2px solid #f5d9b8; padding: 0 10px; background: #fffdf8; color: #5b4636;
}
.aiedu-lesson .lesson-feedback { min-height: 48px; display: flex; align-items: center; font-size: 17px; }
.aiedu-lesson .lesson-status { font-size: 13px; color: #b09a84; margin-top: 8px; }
`;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

/** renderLesson：在 container 内渲染一节完整可交互课堂。 */
export function renderLesson(
  container: HTMLElement,
  spec: LessonSpecJson,
  options: RenderLessonOptions = {},
): LessonView {
  const judgeMode: JudgeMode = options.judgeMode ?? "declared";
  const showBlocks = options.showBlocks ?? true;

  container.classList.add("aiedu-lesson");
  container.innerHTML = "";
  if (!document.getElementById("aiedu-lesson-styles")) {
    const style = el("style", { id: "aiedu-lesson-styles" });
    style.textContent = STYLES;
    document.head.appendChild(style);
  }

  const questionText =
    (spec as { teaching_request?: { content?: string } }).teaching_request?.content ?? "";
  const question = el("div", { class: "lesson-question", "data-question": "" });
  question.textContent = questionText;
  container.appendChild(question);

  // 节点容器：每个 activity 节点一个 section，同时只有当前节点可见（一屏一任务）
  const nodesWrap = el("div", { class: "lesson-nodes", "data-lesson-nodes": "" });
  const nodeEls = new Map<string, HTMLElement>();
  for (const node of spec.activity_graph ?? []) {
    const section = el("section", {
      class: "lesson-node",
      "data-activity-node": "",
      "data-node-id": node.id,
      "data-node-type": node.type,
    });
    section.hidden = true;
    const prompt = el("div", { class: "node-prompt", "data-node-prompt": "" });
    prompt.textContent = node.prompt ?? "";
    section.appendChild(prompt);
    if (node.narration !== undefined) {
      const narration = el("div", { class: "node-narration", "data-node-narration": "" });
      narration.textContent = node.narration ?? "";
      section.appendChild(narration);
    }
    nodesWrap.appendChild(section);
    nodeEls.set(node.id, section);
  }
  container.appendChild(nodesWrap);

  // 算术块图：仅当 spec 的 arithmetic 状态用 left/right 语义时渲染
  // （如破十法用 tens/ones，渲染块图会显示误导性的 "0 + 0"）
  let blocksMount: HTMLElement | null = null;
  const arithmeticState = spec.initial_states?.["m-arithmetic"];
  const blocksApplicable =
    showBlocks &&
    !!arithmeticState &&
    ("left" in arithmeticState || "right" in arithmeticState);
  if (blocksApplicable) {
    blocksMount = el("div", { id: "blocks-stage", "data-layout-check": "" });
    container.appendChild(blocksMount);
  }

  const controls = el("div", { class: "lesson-controls", "data-controls": "" });
  const input = el("input", {
    id: "answer-input",
    class: "answer-input",
    "data-answer-input": "",
    type: "text",
    inputmode: "numeric",
    placeholder: "输入答案",
  });
  const submitBtn = el("button", { id: "submit-btn", class: "primary", "data-action": "submit" });
  submitBtn.textContent = "提交✨";
  const hintBtn = el("button", { id: "hint-btn", "data-action": "hint" });
  hintBtn.textContent = "提示💡";
  const continueBtn = el("button", { id: "continue-btn", "data-action": "continue" });
  continueBtn.textContent = "继续➡️";
  const replayBtn = el("button", { id: "replay-btn", "data-action": "replay" });
  replayBtn.textContent = "重播🔁";
  const resetBtn = el("button", { id: "reset-btn", "data-action": "reset" });
  resetBtn.textContent = "重置🔄";
  controls.append(input, submitBtn, hintBtn, continueBtn, replayBtn, resetBtn);
  container.appendChild(controls);

  const feedback = el("div", { id: "feedback", class: "lesson-feedback", "data-feedback": "" });
  container.appendChild(feedback);
  const status = el("div", { id: "status", class: "lesson-status", "data-status": "" });
  container.appendChild(status);

  const anim = new AnimationController();
  const theme = spec.presentation?.scene_metaphor ?? "clean_school";
  const renderer = blocksMount ? new BlocksRenderer(blocksMount, theme) : null;
  const runtime = new ActivityRuntime(
    spec,
    anim,
    undefined,
    (state) => renderer?.render(state, anim),
    judgeMode,
  );

  // 无答案预览形态（架构增量 v1 · C4）：filtered spec 的判据是任一节点
  // locked===true 或 response.expected/correct_index 为 null 且带 gate。
  // 该形态下不做任何判定（渲染层不派生答案）：提交按钮=免判定推进，observe 空讲解占位。
  const filteredMode = (spec.activity_graph ?? []).some(
    (n) =>
      n.locked === true ||
      ((n.response?.expected === null || n.response?.correct_index === null) && !!n.gate),
  );

  const refresh = () => {
    const node = runtime.current;
    for (const [id, section] of nodeEls) {
      section.hidden = id !== runtime.current?.id;
    }
    if (node) {
      const section = nodeEls.get(node.id);
      const promptEl = section?.querySelector<HTMLElement>("[data-node-prompt]");
      if (promptEl) promptEl.textContent = node.prompt ?? "";
      const narrationEl = section?.querySelector<HTMLElement>("[data-node-narration]");
      if (narrationEl) {
        // observe 空讲解（filtered 投影清空 narration）：诚实占位，不冒充讲解
        narrationEl.textContent =
          node.narration && node.narration.length > 0
            ? node.narration
            : node.type === "observe"
              ? "（完成全部步骤后由学习伙伴为你讲解）"
              : "";
      }
      continueBtn.style.display = INTERACTIVE_TYPES.includes(node.type) ? "none" : "inline-block";
      input.style.display = INTERACTIVE_TYPES.includes(node.type) ? "inline-block" : "none";
      submitBtn.textContent = filteredMode
        ? "记下答案，继续 ➡️"
        : INTERACTIVE_TYPES.includes(node.type)
          ? "提交✨"
          : "继续➡️";
    }
    status.textContent = `节点：${node?.id ?? "-"}（${node?.type ?? "-"}）｜会话：${runtime.sessionStatus}`;
    const violations = checkLayoutInvariants(
      container,
      { width: window.innerWidth, height: window.innerHeight },
    );
    if (violations.length > 0) {
      status.textContent += "｜布局违规：" + violations.map((v) => v.issue).join("；");
    }
  };

  submitBtn.addEventListener("click", () => {
    const node = runtime.current;
    if (filteredMode) {
      // 无答案预览：免判定推进（诚实标注"未经判定"），不判分、不派生答案
      if (node) {
        runtime.continue();
        feedback.textContent = "已记录（未经判定）";
        feedback.style.color = "#1565c0";
      }
      refresh();
      input.value = "";
      return;
    }
    if (node && !INTERACTIVE_TYPES.includes(node.type)) {
      runtime.continue();
      refresh();
      return;
    }
    const value = input.value;
    const result = runtime.answer(value);
    if (!result.judged) {
      // spec 未声明期望答案（filtered 形态）：不在前端判定，交给服务端
      feedback.textContent = result.feedback;
      feedback.style.color = "#1565c0";
      options.onAttempt?.(node?.id ?? "", value);
    } else if (result.correct) {
      feedback.textContent = result.feedback + " 🎉";
      feedback.style.color = "#2e7d32";
    } else {
      feedback.textContent = result.feedback + " 💪再想想，你离答案很近啦！";
      feedback.style.color = "#c62828";
    }
    refresh();
    input.value = "";
  });
  hintBtn.addEventListener("click", () => {
    const hint = runtime.assist();
    feedback.textContent = hint ?? "没有更多提示了";
    feedback.style.color = "#1565c0";
  });
  continueBtn.addEventListener("click", () => {
    runtime.continue();
    refresh();
  });
  replayBtn.addEventListener("click", () => {
    runtime.replay();
    refresh();
  });
  resetBtn.addEventListener("click", () => {
    runtime.reset();
    feedback.textContent = "";
    refresh();
  });

  runtime.start();
  refresh();

  return {
    runtime,
    container,
    get activeNodeId() {
      return runtime.current?.id ?? null;
    },
    destroy() {
      container.innerHTML = "";
      container.classList.remove("aiedu-lesson");
    },
  };
}
