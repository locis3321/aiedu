"""任务包记录校验脚本（零依赖）。

用法：
    python scripts/validate_task_pack.py <task-pack-directory>

检查：
- 存在 需求总览.md；
- 每个 T*.md 包含必需章节；
- E2E-验收记录.md 存在时检查必需章节。

退出码：0 = 无错误；1 = 存在错误。
"""

import sys
from pathlib import Path

REQUIRED_SECTIONS = (
    "## 任务定位",
    "## 上下文",
    "## 需求描述",
    "## 改动详情",
    "## 输入",
    "## 输出",
    "## 影响分析",
    "## 验收方式",
    "## 依赖任务",
    "## 后续任务",
    "## 决策记录",
    "## 时间记录",
    "## 状态记录表",
)

OVERVIEW_SECTIONS = (
    "## 背景",
    "## 现状盘点",
    "## 需求定位",
    "## 任务树",
    "## 子任务列表",
    "## 验收方式",
    "## 当前状态",
)


def check_file(path: Path, sections: tuple[str, ...]) -> list[str]:
    if not path.is_file():
        return [f"missing file: {path.name}"]
    text = path.read_text(encoding="utf-8")
    return [f"{path.name}: missing section {s}" for s in sections if s not in text]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/validate_task_pack.py <task-pack-directory>")
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"FAIL: directory not found: {root}")
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    overview = root / "需求总览.md"
    errors += check_file(overview, OVERVIEW_SECTIONS)

    task_files = sorted(root.glob("T*.md"))
    if not task_files:
        errors.append("no T*.md task files found")
    for tf in task_files:
        errors += check_file(tf, REQUIRED_SECTIONS)

    e2e = root / "E2E-验收记录.md"
    if e2e.is_file():
        errors += check_file(e2e, ("## 验收目标",))
        text = e2e.read_text(encoding="utf-8")
        # 兼容两种形态：进行中（待验证主路径/待运行命令）与已完成（验收结果/已运行命令）
        if "## 待验证主路径" not in text and "## 验收结果" not in text:
            errors.append(
                "E2E-验收记录.md: missing section ## 待验证主路径 or ## 验收结果"
            )
        if "## 待运行命令" not in text and "## 已运行命令" not in text:
            errors.append(
                "E2E-验收记录.md: missing section ## 待运行命令 or ## 已运行命令"
            )
    else:
        warnings.append("E2E-验收记录.md not found (optional for non-cross-boundary packs)")

    for err in errors:
        print(f"[ERROR] {err}")
    for warn in warnings:
        print(f"[WARN] {warn}")
    print(f"SUMMARY: {len(task_files)} task files, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
