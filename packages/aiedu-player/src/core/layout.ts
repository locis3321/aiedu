/**
 * 布局引擎 + 不变量检查（R2 §8）。
 * 生产门禁：SVG/DOM 标签包围盒、边界和遮挡检查；排除有意叠放；
 * 验证 360/390/768/1280px 视口。失败即阻断（返回违规列表，不 console.warn）。
 */

export interface Viewport {
  width: number;
  height: number;
}

export interface LayoutViolation {
  element: string;
  issue: string;
}

/** 检查元素是否越出视口边界。 */
export function checkBounds(
  root: HTMLElement,
  viewport: Viewport,
): LayoutViolation[] {
  const violations: LayoutViolation[] = [];
  const margin = 4;
  for (const el of Array.from(root.querySelectorAll<HTMLElement>("[data-layout-check]"))) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue; // 隐藏元素不检查
    if (rect.left < -margin || rect.top < -margin) {
      violations.push({ element: el.id || el.className, issue: "element outside viewport (top/left)" });
    }
    if (rect.right > viewport.width + margin || rect.bottom > viewport.height + margin) {
      violations.push({ element: el.id || el.className, issue: "element outside viewport (bottom/right)" });
    }
  }
  return violations;
}

/** 检查关键控件是否相互遮挡（中心点重叠检测；父子包含关系不算遮挡）。 */
export function checkOverlap(root: HTMLElement): LayoutViolation[] {
  const violations: LayoutViolation[] = [];
  const controls = Array.from(
    root.querySelectorAll<HTMLElement>("[data-layout-check]"),
  );
  for (let i = 0; i < controls.length; i++) {
    for (let j = i + 1; j < controls.length; j++) {
      const a = controls[i];
      const b = controls[j];
      // 父子包含关系（如容器与内部块）是正常布局，不算遮挡
      if (a.contains(b) || b.contains(a)) continue;
      const ra = a.getBoundingClientRect();
      const rb = b.getBoundingClientRect();
      const overlapX = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
      const overlapY = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
      if (overlapX > 8 && overlapY > 8) {
        violations.push({
          element: `${a.id || i} vs ${b.id || j}`,
          issue: "controls overlap",
        });
      }
    }
  }
  return violations;
}

/** 触摸目标 ≥44px。 */
export function checkTouchTargets(root: HTMLElement): LayoutViolation[] {
  const violations: LayoutViolation[] = [];
  for (const el of Array.from(root.querySelectorAll<HTMLElement>("button, [role=button], input, .touch-target"))) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    if (rect.width < 44 || rect.height < 44) {
      violations.push({ element: el.id || el.className, issue: "touch target smaller than 44px" });
    }
  }
  return violations;
}

/** 汇总全部布局不变量；空数组表示通过。 */
export function checkLayoutInvariants(
  root: HTMLElement,
  viewport: Viewport,
): LayoutViolation[] {
  return [
    ...checkBounds(root, viewport),
    ...checkOverlap(root),
    ...checkTouchTargets(root),
  ];
}
