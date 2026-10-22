---
name: chicken-rabbit
description: Use when teaching the chicken-and-rabbit cage problem with the assumption method (鸡兔同笼假设法).
---

# 鸡兔同笼（假设法）

## 核心思想
设全为鸡：脚数 2×头；多出的脚来自兔子（每只多 2 只脚）→ 兔=(足−2×头)÷2，鸡=头−兔。

## 使用条件
- 已知头数与足数；足数在 2×头 与 4×头 之间且为偶数（有整数解）。

## 特有误差
- 假设全为兔再反推，差值方向写反。
- 未检查足数范围/奇偶，得出非法结果。

## 一句话
假设全是鸡，多出的脚 ÷ 2 就是兔子数。
