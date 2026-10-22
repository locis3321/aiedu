---
name: sum-diff
description: Use when teaching the sum-difference method to find two numbers from their sum and difference (和差倍问题).
---

# 和差倍问题（和差法）

## 核心思想
已知两数和 S 与差 D：大数=(S+D)÷2，小数=(S-D)÷2。先求大数，再求小数（用和−大数）。

## 使用条件
- 题目给出两数和与差（和>差、和与差同奇偶才有整数解）。
- 问两数各是多少。

## 特有误差
- 把 (和−差)÷2 当大数（大小角色颠倒）。
- 不检查和与差奇偶性，直接除出非整数。

## 一句话
大数补一份就和成两个大数：(和+差)÷2。
