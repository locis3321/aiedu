"""使用日志汇总：JSONL → 统计（总调用数 / tool 分布 / 成功率 / gap 触发率 / 耗时）。

用法：
    python packages/aiedu-mcp/scripts/usage_summary.py <usage.jsonl>

只读日志，不改任何东西；输出可直接贴进止损报告作为证据。
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# 视为"失败"的 result 值（其余算成功）
FAILURE_RESULTS = {"error"}


def load(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法：python usage_summary.py <usage.jsonl>")
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"日志文件不存在：{path}")
        return 1
    records = load(path)
    # 版本分发（架构增量 v1 · C3）：v==1 正常解析；v≠1 跳过并警告（避免破坏兼容）
    recognized = [r for r in records if r.get("v") == 1]
    skipped = len(records) - len(recognized)
    if skipped:
        print(f"警告：跳过 {skipped} 条非 v1 记录（不兼容 schema）")
    records = recognized
    total = len(records)
    if total == 0:
        print("日志为空（0 次调用）")
        return 0

    by_tool = Counter(r.get("tool", "?") for r in records)
    by_result = Counter(r.get("result", "?") for r in records)
    by_day = Counter(str(r.get("ts", ""))[:10] for r in records)
    kinds = Counter(r.get("args", {}).get("kind", "?") for r in records)
    details = Counter(r.get("detail") for r in records if r.get("detail"))
    callers = [r.get("caller") for r in records if r.get("caller")]

    failures = sum(count for result, count in by_result.items() if result in FAILURE_RESULTS)
    gaps = by_result.get("capability_gap", 0)
    invalid = by_result.get("invalid_input", 0)
    durations = [r.get("duration_ms", 0) for r in records if isinstance(r.get("duration_ms"), int)]

    print(f"总调用数: {total}")
    print(f"成功率: {(total - failures) / total:.1%}（失败 {failures} 次）")
    print(f"capability_gap 触发率: {gaps / total:.1%}（{gaps} 次）")
    print(f"invalid_input 率: {invalid / total:.1%}（{invalid} 次）")
    print(f"平均耗时: {sum(durations) / len(durations):.0f}ms" if durations else "平均耗时: 无数据")
    print("\n各 tool 分布:")
    for tool, count in by_tool.most_common():
        print(f"  {tool:16s} {count}")
    print("\n结果分布:")
    for result, count in by_result.most_common():
        print(f"  {result:16s} {count}")
    print("\n题型分布:")
    for kind, count in kinds.most_common():
        print(f"  {kind:16s} {count}")
    if details:
        print("\n数学结论（verify_math detail）:")
        for detail, count in details.most_common():
            print(f"  {detail:16s} {count}")
    if callers:
        # 按 caller 聚合去重（架构增量 v1 · C3：阶段触发指标的观测口径）
        generate_calls = sum(1 for r in records if isinstance(r.get("tool"), str) and r["tool"] == "generate_lesson")
        by_caller = Counter(callers)
        print("\n按 caller 聚合（去重/日均/生成占比）:")
        print(f"  去重 caller 数: {len(by_caller)}")
        print(f"  generate_lesson 占比: {generate_calls / total:.1%}（计费单位锚定）")
        for caller, count in by_caller.most_common(8):
            print(f"  {caller:20s} {count}")
    print("\n按天分布:")
    for day, count in sorted(by_day.items()):
        print(f"  {day} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
