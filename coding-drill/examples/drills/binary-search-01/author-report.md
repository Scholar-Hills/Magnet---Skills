# 出题验证报告：有序数组里第一个不小于阈值的位置

- 题号：`binary-search-01` · 语言：Python · 时限：2000ms · 检查时间：2026-08-27T13:29:41
- 结论：**通过**（0 ERROR，0 WARN）

## 闸门

| 闸门 | 结果 | 说明 |
|---|---|---|
| solution_fail | OK | 参考解跑通全部用例，期望输出均由实跑得到 |
| difficulty | OK | 难度 2 |
| sample_count | OK | 恰好 1 条样例，分值 0，job 为 sample |
| hidden_count | OK | 隐藏用例 4 条 |
| hidden_jobs | OK | 隐藏用例职责两两不同：typical boundary order empty |
| hidden_score | OK | 每条隐藏用例分值 ≥ 1 |
| score_sum | OK | 隐藏用例总分 10 |
| dup_id | OK | 用例 id 两两不同 |
| dup_output | OK | 所有用例期望输出两两不同 |
| dup_input | OK | 所有用例输入两两不同 |
| empty_input | OK | 没有空输入 |
| echo_case | OK | 没有用例的输出等于输入 |
| empty_expected | OK | 没有空的期望输出 |
| catches_missing | OK | 每条隐藏用例都写明了抓的误解 |
| float_out | OK | 期望输出不含小数 |
| trailing_ws | OK | 期望输出没有行尾空格 |
| baseline_constant | OK | 打印样例输出得 0 分 |
| baseline_empty | OK | 什么都不打印得 0 分 |
| baseline_echo | OK | 原样回显输入得 0 分 |
| baseline_starter | OK | 起步骨架原样提交得 0 分 |
| baseline_first_token | OK | 只打印输入的第一个 token得 0 分 |
| baseline_last_token | OK | 只打印输入的最后一个 token得 0 分 |
| baseline_first_line | OK | 只打印输入的第一行得 0 分 |
| baseline_last_line | OK | 只打印输入的最后一行得 0 分 |
| constant_guessable | OK | 打印 0 / -1 / 1 / 样例首个 token 都得 0 分 |
| mutants_count | OK | 错解 3 个 |
| mutant_m1.py | OK | 错解 m1.py 得 4.0 分（过 c2 c5；挂 c1 c3 c4） |
| mutant_m2.py | OK | 错解 m2.py 得 5.0 分（过 c1 c3 c5；挂 c2 c4） |
| mutant_m3.py | OK | 错解 m3.py 得 8.0 分（过 c1 c2 c3 c4；挂 c5） |
| case_uncaught | OK | 每条隐藏用例都至少被一个错解挂掉 |

## 参考解

| 用例 | 职责 | 结果 | 用时 |
|---|---|---|---|
| c1 | sample | ok | 30ms |
| c2 | typical | ok | 31ms |
| c3 | boundary | ok | 32ms |
| c4 | order | ok | 31ms |
| c5 | empty | ok | 32ms |

## 基线（非解程序的得分；前四个必须 0 分，token / 行基线过半即不合格，常量基线 > 0 提醒）

| 基线 | 得分 | 通过的用例 |
|---|---|---|
| constant | 0.0 | c1 |
| empty | 0.0 | 无 |
| echo | 0.0 | 无 |
| starter | 0.0 | 无 |
| first_token | 0.0 | 无 |
| last_token | 0.0 | 无 |
| first_line | 0.0 | 无 |
| last_line | 0.0 | 无 |
| const:0 | 0.0 | 无 |
| const:-1 | 0.0 | 无 |
| const:1 | 0.0 | 无 |
| const:5 | 0.0 | 无 |

## 错解

| 文件 | 误解 | 得分 | 通过 | 未通过 |
|---|---|---|---|---|
| m1.py | 用 > 代替 >=：找的是第一个严格大于 goal 的元素，等于 goal 的元素被跳过 | 4.0 | c2 c5 | c1 c3 c4 |
| m2.py | 写成精确查找：撞上相等元素立刻返回该位置（不再往左收），数组里没有 goal 时直接报 NONE | 5.0 | c1 c3 c5 | c2 c4 |
| m3.py | “没找到”输出 0 而不是 NONE | 8.0 | c1 c2 c3 c4 | c5 |

本报告不含隐藏用例的输入与期望输出。
