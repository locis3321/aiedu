/**
 * DomainPlugin 运行时契约 + arithmetic 插件（凑十法切片）。
 *
 * R2 §7 固定接口：reduce(state, action) -> nextState；
 * validateTransition(before, action, after) -> violations。
 * 数学状态按领域定义：整数运算精确且离散，整数块不能在动画中变成 14.7 个。
 */

export interface DomainState {
  [key: string]: unknown;
}

export interface DomainAction {
  id: string; // 命名空间操作，如 arithmetic.transfer_units
  params?: Record<string, unknown>;
}

export interface DomainPlugin {
  domain: string;
  reduce(state: DomainState, action: DomainAction): DomainState;
  validateTransition(
    before: DomainState,
    action: DomainAction,
    after: DomainState,
  ): string[];
}

export const arithmeticPlugin: DomainPlugin = {
  domain: "arithmetic",

  reduce(state, action) {
    const left = Number(state.left ?? 0);
    const right = Number(state.right ?? 0);
    const transferred = Number(state.transferred ?? 0);

    switch (action.id) {
      case "arithmetic.transfer_units": {
        const k = Number(action.params?.k ?? 0);
        if (!Number.isInteger(k) || k <= 0 || k > left) {
          throw new Error(`invalid transfer amount k=${k}`);
        }
        // in_transit 是动画层概念（R2 §7），不进数学状态；
        // 数学状态直接 left-k / right+k，总量守恒。
        return {
          ...state,
          left: left - k,
          right: right + k,
          transferred: transferred + k,
        };
      }
      case "arithmetic.group_total": {
        return { ...state, total: left + right };
      }
      default:
        throw new Error(`unknown action: ${action.id}`);
    }
  },

  validateTransition(before, action, after) {
    const violations: string[] = [];
    const beforeTotal = Number(before.left ?? 0) + Number(before.right ?? 0);
    const afterTotal = Number(after.left ?? 0) + Number(after.right ?? 0);
    if (beforeTotal !== afterTotal) {
      violations.push(
        `total must be conserved: ${beforeTotal} -> ${afterTotal}`,
      );
    }
    for (const key of ["left", "right", "transferred"]) {
      if (!Number.isInteger(Number(after[key]))) {
        violations.push(`${key} must stay an integer`);
      }
    }
    return violations;
  },
};
