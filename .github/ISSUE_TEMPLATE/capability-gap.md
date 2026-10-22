---
name: 能力缺口（capability gap）反馈
about: 数芽对某个题型/请求显式返回 capability_gap——告诉我们你期望覆盖什么
title: "[gap] <题型/题面描述>"
labels: ["capability-gap", "triage"]
---

## 你输入的题面

<原样粘贴，例如：52-37 / 1/2+1/4 / 一段想学的数学内容>

## 返回的原始 error

```
{"error": "capability_gap", "detail": "..."}
```

（请照抄 `generate_lesson` 返回中的 `detail`，不要改写）

## 你期望

- [ ] 出一节课（期望的教学方法：____，如退位减法/分数四则/乘法）
- [ ] 只需核验答案（`verify_math` 应能覆盖）

## 当前覆盖（README 覆盖矩阵为准确认）

凑十法（16+8）/ 破十法（16-9）/ 分数等分概念（"平均分成 N 份取 M 份"）。
其它题型一律显式失败——我们的规则是**宁可说不会，也不编**；这条 issue 会按频次进入覆盖扩展排期。
