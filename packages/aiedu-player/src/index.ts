/**
 * 播放器入口：加载 LessonSpec v2 → ActivityRuntime → SVG/div 渲染。
 * 导出为 classic-script bundle（file:// 双击可用），挂载 window.AIEduPlayer。
 */

import { adaptV01, type LessonSpecV01Json } from "./adapters/legacy-v01";
import { ActivityRuntime, type LessonSpecJson } from "./core/activity-runtime";
import { AnimationController } from "./core/animation";
import { checkLayoutInvariants } from "./core/layout";
import { BlocksRenderer } from "./render/blocks-renderer";
import { renderLesson, type LessonView, type RenderLessonOptions } from "./render/lesson-renderer";

export interface PlayerHandle {
  runtime: ActivityRuntime;
  renderer: BlocksRenderer;
}

/** loadSpec：加载 v2 spec，挂载运行时与渲染器（主题来自 presentation）。 */
export function loadSpec(spec: LessonSpecJson, mount: HTMLElement): PlayerHandle {
  const anim = new AnimationController();
  const theme = spec.presentation?.scene_metaphor ?? "clean_school";
  const renderer = new BlocksRenderer(mount, theme);
  const runtime = new ActivityRuntime(
    spec,
    anim,
    undefined,
    (state) => renderer.render(state, anim),
  );
  runtime.start();
  return { runtime, renderer };
}

/** loadV01：v0.1 spec → adapter → loadSpec（legacy）。 */
export function loadV01(spec: LessonSpecV01Json, mount: HTMLElement): PlayerHandle {
  return loadSpec(adaptV01(spec), mount);
}

/** checkLayout：布局不变量检查（供 validate/测试复用）。 */
export function checkLayout(mount: HTMLElement, viewport?: { width: number; height: number }) {
  return checkLayoutInvariants(
    mount,
    viewport ?? { width: window.innerWidth, height: window.innerHeight },
  );
}

export { renderLesson };
export type { LessonView, RenderLessonOptions };
export { BlocksRenderer };
export { adaptV01 };
export type { LessonSpecJson, LessonSpecV01Json };

declare global {
  interface Window {
    AIEduPlayer: {
      loadSpec: typeof loadSpec;
      loadV01: typeof loadV01;
      checkLayout: typeof checkLayout;
      adaptV01: typeof adaptV01;
      renderLesson: typeof renderLesson;
    };
  }
}

window.AIEduPlayer = { loadSpec, loadV01, checkLayout, adaptV01, renderLesson };
