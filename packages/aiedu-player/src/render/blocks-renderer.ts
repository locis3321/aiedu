/**
 * 算术状态 → 可交互块图渲染器；每个单位块保留稳定 ID。
 *
 * 主题来自 LessonSpec.presentation.scene_metaphor（受控枚举），
 * 渲染器只切换安全样式，不执行任何主题代码。
 */

import { AnimationController } from "../core/animation";
import type { DomainState } from "../core/domain-plugin";

export class BlocksRenderer {
  private mount: HTMLElement;
  private blockEls = new Map<string, HTMLElement>();
  private theme: string;

  constructor(mount: HTMLElement, theme = "clean_school") {
    this.mount = mount;
    this.theme = theme;
    this.mount.classList.add("blocks-stage");
    this.mount.style.position = "relative";
    this.mount.style.minHeight = "160px";
    this.mount.dataset.layoutCheck = "";
    this.mount.id = "blocks-stage";
    this.mount.dataset.theme = theme;
  }

  render(state: DomainState, anim: AnimationController): void {
    const left = Number(state.left ?? 0);
    const right = Number(state.right ?? 0);
    const inTransit = Number(state.inTransit ?? 0);
    this.syncGroup("left", left, anim);
    this.syncGroup("right", right, anim);
    this.syncGroup("in-transit", inTransit, anim);
    this.updateReadout(state);
  }

  private syncGroup(group: string, count: number, anim: AnimationController): void {
    const container = this.groupContainer(group);
    const existing = new Set<string>();
    for (let i = 0; i < count; i++) {
      const id = `block-${group}-${i}`;
      existing.add(id);
      let el = this.blockEls.get(id);
      if (!el) {
        el = document.createElement("span");
        el.className = `unit-block block-${group}`;
        el.id = id;
        el.dataset.layoutCheck = "";
        container.appendChild(el);
        this.blockEls.set(id, el);
        // 新块从源位置飞入（GSAP 补间）
        anim.fromTo(el, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1 }, 0.5);
      }
    }
    // 移除多余块（带淡出补间）
    for (const [id, el] of Array.from(this.blockEls)) {
      if (id.startsWith(`block-${group}-`) && !existing.has(id)) {
        anim.tween(el, { opacity: 0 }, 0.3, anim.currentRunId, () => el.remove());
        this.blockEls.delete(id);
      }
    }
    container.dataset.count = String(count);
    container.dataset.layoutCheck = "";
    container.id = `group-${group}`;
    if (this.theme === "berry_basket") {
      // 莓果篮主题：容器由 CSS class 驱动，不写内联样式
      container.className = "group-basket";
      container.style.border = "";
      container.style.borderRadius = "";
      container.style.marginBottom = "";
      container.style.padding = "";
      container.style.minHeight = "";
      container.style.minWidth = "";
      container.style.display = "flex";
      container.style.flexWrap = "wrap";
      container.style.gap = "4px";
      container.style.alignItems = "center";
    } else {
      container.className = "";
      container.style.display = "flex";
      container.style.flexWrap = "wrap";
      container.style.gap = "4px";
      container.style.minHeight = "44px";
      container.style.padding = "4px";
      container.style.border = "1px dashed #888";
      container.style.borderRadius = "6px";
      container.style.marginBottom = "8px";
      container.style.alignItems = "center";
      container.style.minWidth = "44px";
    }
    if (!container.querySelector(".group-label")) {
      const label = document.createElement("span");
      label.className = "group-label";
      label.textContent =
        group === "left" ? (this.theme === "berry_basket" ? "小熊的篮子" : "左边")
          : group === "right" ? (this.theme === "berry_basket" ? "小兔的篮子" : "右边")
          : "转移中";
      label.style.fontSize = "12px";
      label.style.marginRight = "6px";
      container.appendChild(label);
    }
  }

  private groupContainer(group: string): HTMLElement {
    let el = this.mount.querySelector<HTMLElement>(`#group-${group}`);
    if (!el) {
      el = document.createElement("div");
      el.id = `group-${group}`;
      this.mount.appendChild(el);
    }
    return el;
  }

  private updateReadout(state: DomainState): void {
    let readout = this.mount.querySelector<HTMLElement>("#readout");
    if (!readout) {
      readout = document.createElement("div");
      readout.id = "readout";
      readout.dataset.layoutCheck = "";
      readout.style.fontSize = "18px";
      readout.style.fontWeight = "bold";
      readout.style.padding = "8px";
      readout.style.minHeight = "44px";
      this.mount.appendChild(readout);
    }
    const left = Number(state.left ?? 0);
    const right = Number(state.right ?? 0);
    // 只显示 spec 状态里已有的 total；没有就不自行计算（渲染层不派生答案，
    // 答案门控与答案计算都只在 spec 投影层/服务端）。
    const total = state.total !== undefined ? Number(state.total) : null;
    const tail = state.inTransit ? ` (+${state.inTransit}转移中)` : "";
    readout.textContent =
      total === null
        ? `${left} + ${right}${tail} = ?`
        : `${left} + ${right}${tail} = ${total}`;
  }
}
