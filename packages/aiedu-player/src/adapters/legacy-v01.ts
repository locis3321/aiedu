/**
 * v0.1 spec → v2 spec 适配器（legacy）。
 * R2 §13D：v0.1 经适配继续作为演示课程，不自动标为符合 v2 的引导教学。
 * scenes（orient/model/connect/check/summary）→ activity_graph：
 * orient→observe；model/connect→observe；check→predict(choice)；summary→reflect。
 */

import type { LessonSpecJson } from "../core/activity-runtime";

export interface LessonSpecV01Json {
  version: "0.1";
  id: string;
  audience?: { grade?: number };
  question?: string;
  solution?: { answer?: string; verified?: boolean };
  teachingPlan?: {
    scenes?: Array<{
      id: string;
      kind: string;
      title?: string;
      narration?: string;
      interaction?: {
        prompt?: string;
        options?: string[];
        correctIndex?: number;
        feedback?: { correct?: string; incorrect?: string };
      };
    }>;
  };
}

export function adaptV01(spec: LessonSpecV01Json): LessonSpecJson {
  const scenes = spec.teachingPlan?.scenes ?? [];
  const nodes = scenes.map((scene) => {
    const base = {
      id: scene.id,
      next_ids: [] as string[] | null,
    };
    if (scene.kind === "check" && scene.interaction) {
      return {
        ...base,
        type: "predict",
        prompt: scene.interaction.prompt ?? scene.title ?? "",
        response: {
          kind: "choice",
          options: scene.interaction.options ?? [],
          correct_index: scene.interaction.correctIndex ?? -1,
        },
        gate: { mode: "require_attempt" },
        on_correct: [],
      };
    }
    if (scene.kind === "summary") {
      return { ...base, type: "reflect", prompt: scene.narration ?? "" };
    }
    return { ...base, type: "observe", narration: scene.narration ?? "" };
  });
  for (let i = 0; i < nodes.length; i++) {
    nodes[i].next_ids =
      i === nodes.length - 1 ? ["__end__"] : [nodes[i + 1].id];
  }
  return {
    schema_version: "2.0",
    lesson_id: spec.id,
    revision: 1,
    verification: { verified: Boolean(spec.solution?.verified) },
    initial_states: {},
    activity_graph: nodes,
    operations: [],
  };
}
