/**
 * GSAP 动画封装：补间/时间线、暂停定位重播、run_id 失效机制、
 * prefers-reduced-motion 回退。
 *
 * R2 §7：GSAP 只驱动视图属性，不计算答案、不决定解锁；
 * GSAP 回调不能成为数学变换的唯一执行来源。
 */

import { gsap } from "gsap";

export class AnimationController {
  private runId = 0;
  private timeline: gsap.core.Timeline | null = null;
  readonly reducedMotion: boolean;

  constructor() {
    this.reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /** 重置：终止旧时间线并递增 run_id，使过期回调失效。返回新 run_id。 */
  reset(): number {
    this.runId += 1;
    if (this.timeline) {
      this.timeline.kill();
      this.timeline = null;
    }
    return this.runId;
  }

  get currentRunId(): number {
    return this.runId;
  }

  /** 创建补间；reduced-motion 时 duration=0（保留语义结果）。 */
  tween(
    target: object,
    props: gsap.TweenVars,
    duration = 0.6,
    runId = this.runId,
    onComplete?: () => void,
  ): gsap.core.Tween {
    const d = this.reducedMotion ? 0 : duration;
    const vars: gsap.TweenVars = { ...props, duration: d };
    if (onComplete) {
      vars.onComplete = () => {
        if (runId === this.runId) onComplete();
      };
    }
    return gsap.to(target, vars);
  }

  /** from-to 补间（新元素入场等）。 */
  fromTo(
    target: object,
    fromVars: gsap.TweenVars,
    toVars: gsap.TweenVars,
    duration = 0.6,
    runId = this.runId,
    onComplete?: () => void,
  ): gsap.core.Tween {
    const d = this.reducedMotion ? 0 : duration;
    const vars: gsap.TweenVars = { ...toVars, duration: d };
    if (onComplete) {
      vars.onComplete = () => {
        if (runId === this.runId) onComplete();
      };
    }
    return gsap.fromTo(target, fromVars, vars);
  }

  /** 创建时间线（供多步动作编排）。 */
  createTimeline(runId = this.runId): gsap.core.Timeline {
    this.timeline = gsap.timeline();
    const tl = this.timeline;
    // run_id 失效：时间线被 kill 后旧回调不再执行
    tl.eventCallback("onComplete", () => {
      if (runId !== this.runId) tl.kill();
    });
    return tl;
  }

  pause(): void {
    this.timeline?.pause();
  }

  play(): void {
    this.timeline?.play();
  }

  seek(time: number): void {
    this.timeline?.seek(time);
  }
}
