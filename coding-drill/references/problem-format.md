# 题包格式与判题脚本契约

本文是 `scripts/judge.py` 与 SKILL.md 共同遵守的唯一格式定义。Agent 出题时按此落盘；脚本按此读取。

## 1. 目录布局

每道题一个目录，放在工作区的 `drills/` 下。

**Python / JavaScript**（平铺）：

```
drills/
  misconceptions.md              # 错题本（所有题共用，脚本追加，用户可编辑）
  <slug>/                        # 一道题；slug = 知识点-序号，例如 binary-search-01
    problem.md                   # 题面（学生可见）：任务、输入格式、输出格式、示例
    meta.json                    # 元数据（见 §2）
    starter.py | starter.js      # 起步骨架（学生可见，可直接运行，必须 0 分）
    solution.py | solution.js    # 学生作答文件（由 starter 复制而来，学生编辑）
    .hidden/                     # 学生不看；Agent 出题时写入，判题时读取
      reference.py | reference.js    # 参考解
      tests.json                 # 用例（见 §3）
      mutants/                   # 错解：m1.py、m2.py …
      mutants.json               # 每个错解对应的误解（见 §4）
      author-report.json         # author 验证结果（脚本生成）
    author-report.md             # 验证结果的可见版（不含隐藏用例内容）
    report.json / report.md / report.html      # 判题输出（脚本生成，可覆盖）
```

**Java**：类名固定为 `Main`（`public class Main`，无 `package`），所以每个 Java 程序独占一个目录：

```
  <slug>/
    problem.md · meta.json
    starter/Main.java            # 起步骨架
    Main.java                    # 学生作答文件（由 starter/Main.java 复制而来）
    .hidden/
      reference/Main.java        # 参考解
      tests.json · mutants.json
      mutants/m1/Main.java · mutants/m2/Main.java
```

## 2. meta.json

```json
{
  "slug": "binary-search-01",
  "title": "有序数组里第一个不小于目标的位置",
  "topic": "二分查找",
  "language": "python",
  "difficulty": 2,
  "difficultyReason": "一个循环加一个需要推理的边界（目标恰好等于某元素）",
  "timeLimitMs": 2000,
  "compareMode": "trim",
  "createdAt": "2026-08-27",
  "mode": "learner"
}
```

- `language`：`python` | `javascript` | `java`。
- `difficulty`：数字 `1 / 2 / 3`（简单 / 中等 / 困难，见 authoring-rules §7），不是中文。
- `compareMode`：固定 `trim`——只去整段输出首尾空白后比较。
- `mode`：`learner`（自己练）| `teacher`（给学生出题）。

## 3. .hidden/tests.json

```json
{
  "cases": [
    { "id": "c1", "isSample": true,  "score": 0, "job": "sample",    "input": "5\n1 3 5 7 9\n5",      "expected": "2",  "catches": "" },
    { "id": "c2", "isSample": false, "score": 2, "job": "typical",   "input": "6\n2 4 6 8 10 12\n11", "expected": null, "catches": "只在靠前位置查找，答案在末尾时找不到" },
    { "id": "c3", "isSample": false, "score": 3, "job": "boundary",  "input": "4\n1 2 3 4\n4",        "expected": null, "catches": "用 > 代替 >=，恰好等于目标的元素被跳过" },
    { "id": "c4", "isSample": false, "score": 2, "job": "empty",     "input": "7\n1 2 3 4 5 6 7\n10", "expected": null, "catches": "找不到时没有返回 n，而是返回 -1" },
    { "id": "c5", "isSample": false, "score": 3, "job": "saturated", "input": "1\n5\n1",              "expected": null, "catches": "单元素数组时循环边界写错，返回 1 而非 0" }
  ]
}
```

`expected` 的规则分两种：

- **隐藏用例一律写 `null`**，由 `judge.py author` 运行参考解回填。
- **样例用例（`isSample: true`）允许手写你预期的输出**，作用是交叉校验参考解：脚本发现参考解在样例上跑出别的值，报 `ERROR solution_fail` 并且**绝不覆盖**——这时要改的是参考解或题面，不是这个值。样例也可以写 `null` 让脚本回填。

其他字段：

- `input` 是精确的 stdin 内容，不带末尾换行；`expected` 回填后不带末尾换行。题包文件一律用 LF；脚本比对时 `\r\n` 会归一为 `\n`，Windows 上不必特意转换。
- `problem.md` 出题时示例块用 `<待回填输入>` 与 `<待回填输出>` 占位，`author` 通过后再由样例用例回填（见 SKILL.md 第 9 步）；`export` 会拒绝仍含 `<待回填…>` 的题面。
- `job` 取值：`sample`（仅样例）/ `typical` / `boundary` / `empty` / `saturated` / `order`（含义见 authoring-rules §3）。
- `catches`：这条隐藏用例抓的是什么误解，写具体的错法，样例可留空。

## 4. .hidden/mutants.json

```json
{
  "mutants": [
    { "file": "m1.py", "misconception": "用 > 代替 >=，恰好等于目标的元素被跳过" },
    { "file": "m2.py", "misconception": "找不到时返回 -1 而不是 n" }
  ]
}
```

Java 时 `file` 写目录名（如 `m1`），脚本在 `.hidden/mutants/m1/Main.java` 找文件。

## 5. judge.py 命令行契约

零依赖（Python 3.8+ 标准库），单文件。所有命令的退出码：0 = 通过，1 = 未通过（有 ERROR），2 = 用法或环境错误。

### `judge.py doctor`

打印本机可用运行时（python3 / node / javac+java）与版本；缺 Java 只警告不报错。

### `judge.py author <drill-dir> [--refill]`

出题验证。按顺序：

1. **回填期望输出**：对每条用例运行参考解，`expected` 为 `null` 的写入实跑输出；已有值的比对，不一致 → `ERROR solution_fail`。参考解运行失败（超时 / 非零退出 / 编译失败）→ `ERROR solution_fail`。`--refill` 允许覆盖已有值并在报告里标明——它只供**人**在刻意重做参考解、需要整体重算期望输出时使用；Agent 永远不加这个开关。
2. **静态闸门**：
   - `difficulty`（ERROR）：`meta.difficulty` 不是 `1 / 2 / 3` 的整数
   - `sample_count`（ERROR）：恰好 1 条 `isSample: true`，且 `score` 为 0，且 `job` 为 `sample`
   - `hidden_count`（ERROR）：隐藏用例为 4 条或 5 条；`hidden_jobs`（ERROR）：隐藏用例的 `job` 两两不同且不为 `sample`
   - `hidden_score`（ERROR）：每条隐藏用例 `score` ≥ 1；`score_sum`（ERROR）：隐藏用例分之和 > 0
   - `dup_id`（ERROR）：用例 id 两两不同
   - `dup_output`（ERROR）：所有用例 `expected` 两两不同
   - `dup_input` / `empty_input`（ERROR）：所有用例 `input` 两两不同且非空
   - `echo_case`（ERROR）：没有任何用例的 `expected` 等于其 `input`（trim 后比较）
   - `empty_expected`（ERROR）：没有任何用例的 `expected` 为空
   - `catches_missing`（ERROR）：任一隐藏用例的 `catches` 为空
   - `catches_generic`（WARN）：`catches` 短于 8 个字，或只由“边界 / 特殊情况 / 测试”这类词构成
   - `float_out`（ERROR）：`expected` 里出现小数点数字（浮点输出跨语言不稳，改问整数）
   - `trailing_ws`（WARN）：`expected` 任一行以空格结尾
3. **四个非解**（全部 ERROR，每个程序的得分必须为 0）：
   - `baseline_constant`：打印样例的期望输出
   - `baseline_empty`：什么都不打印
   - `baseline_echo`：把 stdin 原样打印
   - `baseline_starter`：起步骨架原样提交
   前三个由脚本按语言自动生成，不需要出题者写。
   **“只打印输入的一部分”四个非解**：`baseline_first_token` / `baseline_last_token` / `baseline_first_line` / `baseline_last_line`（分别打印 stdin 的第一个 / 最后一个空白分隔 token、第一行 / 最后一行）——任一得分 ≥ 总分一半 → ERROR，> 0 → WARN（附通过的用例 id）。
   **常量可猜**：`constant_guessable`（WARN）——分别打印 `0`、`-1`、`1`、样例输入的第一个 token，任一得分 > 0 即 WARN，并提示把 `empty` 用例的答案改成不那么好猜的值。
   任何基线程序编译失败或全部 runtime_error 时，报 WARN“该基线未能运行，闸门未证明”，不得当作通过。
4. **错解**（`mutants.json` 里每一个）：
   - `mutants_count`：错解少于 2 个 → ERROR；恰好 2 个 → WARN（建议 3 个）
   - `mutant_missing`：文件不存在 → ERROR
   - `mutant_compile`：编译或运行全部失败（每条用例都 runtime_error / compile_error）→ WARN（错解得像人写的，不该是坏程序）
   - `mutant_full`：错解拿满分 → ERROR（用例集看不见这个误解）
   - `mutant_zero`：错解在每条用例上都挂 → WARN（只证明它错，不证明用例有针对性）
5. 写出 `.hidden/author-report.json`（含 `tests.json`、参考解、起步骨架、每个错解文件的 sha256，供 `export` 核对）与题目目录下的 `author-report.md`（可见，供出题者/老师看，**不含隐藏用例输入输出**，只含闸门结果与每个错解的得分）。

`tests.json` / `meta.json` 的字段校验：`catches`、`job` 必须是字符串，`score` 必须是有限数，`timeLimitMs` 为 100～60000 的整数；不满足 → 用法错误（退出 2）。

### `judge.py judge <drill-dir> [--file <path>] [--reveal-all] [--allow-io]`

判学生作答（默认作答文件为 `solution.*` / `Main.java`）：

0. **静态扫描**作答文件：命中读写文件、联网、启动子进程、探查父进程之类的调用（Python 如 `subprocess` / `os.system` / `os.fork` / `os.setsid` / `os.getppid` / `/proc/` / `lsof` / `socket` / `urllib` / `open(` / `pathlib` / `shutil`；JavaScript 如 `child_process` / `process.ppid` / `net` / `http` / `dns` / 除 `readFileSync(0` 与 `readFileSync('/dev/stdin'` 以外的 `fs` 调用；Java 如 `ProcessBuilder` / `Runtime.getRuntime` / `ProcessHandle` / `java.io.File` / `java.nio.file` / `java.net`）则**不运行**，退出 2，打印命中的行，提示“确认无害后加 `--allow-io`”。
1. 逐条运行用例，计分 = Σ通过用例分 / Σ全部用例分 × 10，保留 1 位小数；verdict：`accepted` / `partial` / `wrong_answer` / `compile_error` / `time_limit_exceeded` / `output_limit_exceeded` / `runtime_error`。编译失败短路，整题 0 分。
2. 终端输出一张表：用例 id、职责（job）、通过/未通过、用时；样例用例显示输入与输出；隐藏用例默认**只显示第一条未通过用例**的输入、期望与实际输出，其余隐藏用例只显示通过/未通过与 `catches`（“这条用例抓的是：…”）；`--reveal-all` 全部展开。
3. 错题本追加：只对 verdict 为 `wrong_answer` 的用例，且整题不是 `compile_error`，且作答文件内容与起步骨架不相同，把一行追加到 `drills/misconceptions.md`：`- <日期> · <slug> · <catches>`（`catches` 折成单行；同一题同一条不重复追加；文件不存在则创建）。超时、运行错误、原样骨架不算误解，不追加。
4. 写出 `report.json`、`report.md`，以及 `report.html`（自包含、无外链、深浅色都可读的一张判题卡：题目、得分、每条用例的通过状态与 `catches`，被揭开的那条显示输入输出，其余隐藏用例不显示输入输出；本次新增错题本条目）。 `report.json` 里的 `file` 是作答文件**相对工作区**的路径（工作区外的文件只留文件名），不含本机绝对路径——报告会被截图、导出、放进仓库。

### `judge.py run <drill-dir> <program-file>`

对任意程序跑全部用例并打印得分与逐用例结果（出题者调试错解用；会显示全部输入输出）。

## 6. 运行约束（脚本必须实现）

- 每个程序在**临时目录**里运行，工作目录不是题目目录；运行前把程序文件复制过去，脚本自身也在运行期间切换到临时目录（避免被作答程序通过父进程的工作目录定位题目目录），运行后删除临时目录。
- 每条用例的墙钟超时 = `timeLimitMs`（默认 2000ms），超时即杀整棵进程树（递归收集后代进程一并结束，不等管道关闭），判 `time_limit_exceeded`；编译超时 15 秒。脚本被 Ctrl-C 或异常中断时同样先清理子进程。
- stdout / stderr 各以流式方式读取，累计超过 256 KB 立即停止保存并结束进程，判 `output_limit_exceeded`（判题进程自身的内存不随程序输出增长）。
- 环境变量只保留 `PATH`（以及 Java 需要的 `JAVA_HOME` 若存在）。
- 不做网络与文件系统隔离——脚本无法做到，SKILL.md 里明示，并要求 Agent 在运行前先审阅生成的代码。
- 语言命令：python → `python3 main.py`（找不到 `python3` 时退化为 `python`）；javascript → `node main.js`；java → `javac Main.java` 再 `java -cp . Main`。
- 比对模式只实现 `trim`：整段输出去首尾空白后与 `expected` 比较（`\r\n` 归一为 `\n`）。

## 7. 教师模式导出：`judge.py export <drill-dir> [--out <file>]`

把通过 `author` 验证的题包导出为一份自包含的 JSON，便于导入到你自己的作业或评测系统（字段含义见注释，与任何具体平台无关）：

```json
{
  "stem": "<problem.md 转成的 HTML>",          // 题面
  "difficulty": 2,                              // 1 / 2 / 3
  "point": 10,                                  // 本题总分
  "coding": {
    "languages": ["python"], "defaultLanguage": "python",
    "starterCode": { "python": "..." },         // 起步骨架
    "solutionCode": { "python": "..." },        // 参考解
    "judgeMode": "testcases", "ioMode": "stdin_stdout", "compareMode": "trim",
    "testCases": [ { "input": "...", "expectedOutput": "...", "isSample": true, "score": 0 } ],
    "timeLimitMs": 2000, "memoryLimitMb": 256,  // 内存上限只是给导入方的提示
    "totalScore": 10
  },
  "authoring": {
    "caseIntent": ["sample", "typical: …", "boundary: …", "empty: …", "saturated: …"],
    "mutants": ["…", "…"],
    "difficultyReason": "…"
  }
}
```

拒绝导出的情形：没有 `.hidden/author-report.json` 或其中有 ERROR；`tests.json`、参考解、起步骨架、任一错解在验证后被改动（sha256 与报告不符，提示重跑 `author`）；`difficulty` 非法；`problem.md` 仍含 `<待回填>`；`problem.md` 未逐字包含样例用例的 `input` 与 `expected`（`stem_sample_mismatch`）。
