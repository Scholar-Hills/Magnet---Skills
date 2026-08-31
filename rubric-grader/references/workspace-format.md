# 题批次目录与脚本契约

本文是 `scripts/grader.py`、`scripts/selftest.py` 与 SKILL.md 共同遵守的唯一格式定义。Agent 按此落盘，脚本按此读取，自测按此断言。

> **改本契约必须在同一个 commit 里改 `scripts/grader.py` 与 `scripts/selftest.py`**，反之亦然：脚本行为变了，本文与对应断言一起改。不允许「先改脚本，文档以后补」。

## 1. 目录布局

一批作答一个目录，放在**老师工作区**（不是 Skill 目录）的 `grading/` 下。目录名就是批次名（`slug`）。

```
grading/
  <slug>/                          # 一个题批次，例如 short-answer-01
    job.json                       # 批次元数据与条目表（见 §2）
    question.md                    # 题干原文，可含 HTML；脚本只读不改
    rubric.md                      # 老师给的评分标准原文，逐字保存；脚本不解析、不改
    oracle/
      full.md                      # 满分范例作答（老师给，或老师改过的草稿）
      broken.md                    # 残缺版：删掉了某一条对应的内容
      broken.json                  # {"missing": ["条目名", ...]}，残缺版缺哪几条
    answers/
      <学号>.md                     # 学生作答；也支持 .txt / .html / .docx
      base-empty.md                # 对抗基线：空白（文件名以 base- 开头即被强制 0 分）
      base-echo.md                 # 对抗基线：把题面原样贴回
      base-noise.md                # 对抗基线：与题目无关的段落
    inbox/                         # Agent 唯一可写的目录
      criteria.json                # 条目表草稿，rubric set 从这里读
      grade-oracle-full.json       # 满分范例的评分结果
      grade-oracle-broken.json     # 残缺版的评分结果
      grade-<学号>.json             # 每份作答的评分结果（见 §3）
    results/
      <学号>.json                   # 闸门通过后由脚本落盘（见 §4）；不许手写、手改
      <学号>.html                   # 判题卡，自包含单页
    summary.md / summary.html      # 全班汇总（summary 生成）
    export.json                    # 脱敏证据（export 生成，可选；见 §6）
    .stamps/
      oracle.json                  # 校准盖章（见 §5）
```

三条边界：

- **`inbox/` 是 Agent 唯一可写的目录。** `results/`、`summary.*`、`.stamps/` 全由脚本落盘。
- **`answers/` 是证据，不是参数。** 闸门没过要改的是 `inbox/` 里的评分结果，不是学生写的东西。
- **文件名以 `base-` 开头的作答是对抗基线**，`grade` 与 `check` 都强制它 0 分且条目全部未命中；汇总与平均分不计入它们。

作答文件扩展名按 `.md`、`.txt`、`.html`、`.htm`、`.docx` 的顺序查找。`.docx` 只用标准库解包抽段落文字，图片、图表、公式里的内容抽不出来也不猜；抽不到任何文字会直接报错。

作答与题干里的 HTML 进引擎前先过白名单消毒：`script` / `style` / `iframe` 这类没有正文语义的标签**连内容一起丢**，其余标签脱掉外壳、文字保留。一条边界要知道：这类丢弃标签若**没有闭合**，按「到文件末尾自动闭合」处理——它之后的所有内容都会被当作该标签的内容一并丢掉（与浏览器的解析行为一致）。抽出来的正文突然变短时，先检查作答里有没有未闭合的 `<script>` / `<style>` / `<iframe>`。

## 2. `job.json`

`init` 建好骨架，`rubric set` 只改写 `criteria` 一个键，其余字段可以由老师手改。注意 `max` 与 `lang` 也参与上下文哈希：手改任一个都会让所有已批结果过期，须逐份重跑 `grade`。

| 键 | 类型 | 说明 |
|---|---|---|
| `slug` | 字符串 | 批次名，默认取目录名 |
| `max` | 整数 ≥ 1 | 这道题的满分 |
| `lang` | `"zh"` / `"en"` | 作答语言；决定总评按字还是按词计数 |
| `max_notes` | 整数 ≥ 1 | 每份作答的批注条数上限，**默认 12**，老师可改 |
| `min_anchored` | 0～1 的小数 | 批注锚定率下限，**默认 0.7**，老师可改 |
| `criteria` | 数组 | 条目表，见下 |
| `created` | 字符串 | `init` 写下的时间戳，仅供人看 |

条目表每项只接受两个键：

```json
{"name": "定义准确", "points": 2}
```

- `name` 非空、互不重复；`points` 是不小于 0 的整数，可省略。
- **要么每条都带 `points` 且合计等于 `max`，要么每条都不带**；一半带一半不带，`rubric set` 退出 1 并保留旧表。
- 不带分值时「分数与条目判定一致」这条闸门失效，`points` 只受 `0 <= points <= max` 约束，外加两条底线：`hit` / `partial` 的引文锚不回作答就**整份退回**（算不出降级该扣多少）；条目全部 `miss` 而 `points > 0` 拒收（分数没有任何条目撑着）。

`rubric set --from` 读的文件可以是 `{"criteria": [...]}`，也可以直接是数组。

## 3. 评分结果契约（Agent 写进 `inbox/` 的 JSON）

```json
{
  "context_hash": "sha256…",
  "points": 4,
  "summary": "一段 60–200 字的总评",
  "criteria": [
    {"name": "定义准确", "verdict": "hit", "quote": "支撑这条判定的作答原句"}
  ],
  "marks": [
    {"quote": "作答原句", "level": "major", "note": "至少 6 个字的批语"}
  ]
}
```

**顶层五个键，多一个少一个都拒收。**

| 键 | 契约 |
|---|---|
| `context_hash` | `context` 命令输出里的那一串，原样抄。必须等于当前重算值，否则拒收 |
| `points` | 整数，`0 <= points <= max`；条目带分值时必须等于合计（见下），不带分值时条目全部 `miss` 就必须是 0 |
| `summary` | 字符串，`lang: zh` 按字、`lang: en` 按词计，长度须在 **60–200** 之间；不得出现「第 N 题」式逐题复述 |
| `criteria` | 数组，与条目表**一一对应，不多不少不重复**；每项只接受 `name` / `verdict` / `quote` |
| `marks` | 数组，条数 ≤ `max_notes`；每项只接受 `quote` / `level` / `note` |

`criteria[]`：

- `verdict` ∈ `hit` / `partial` / `miss`。
- `quote` 从作答里**原样复制**。判 `hit` 或 `partial` 必须给非空引文，且引文必须能锚回作答原文；锚不上时该条降为 `miss` 并记 `evidence_unanchored: true`，若因此分数变了就整份退回重批。条目表不带分值时算不出「降级该扣多少」，锚不上直接整份退回。判 `miss` 时 `quote` 可以是空串。
- 分数合计：`hit` 拿该条满分、`partial` 拿一半向下取整、`miss` 拿 0。

`marks[]`：

- `quote` 非空，从作答里原样复制；`note` 去掉首尾空白后至少 6 个字；两条 `note` 完全相同则拒收。
- `level` ∈ `major` / `minor` / `remark`，缺省为 `remark`；白名单外的值会被改成 `remark` 并记一条 WARN，不会原样进 HTML。
- 锚定率（锚上的条数 ÷ 总条数）必须 ≥ `min_anchored`，否则拒收；`marks` 为空数组时不检查锚定率。

`context_hash` 的定义：`sha256` 取规范 JSON（键排序、不转义非 ASCII、无多余空白）的 UTF-8 字节，对象是

```
{"answer_text", "criteria", "lang", "max", "question_text", "rubric_text"}
```

其中 `question_text`、`rubric_text`、`answer_text` 都是引擎抽出来的纯文本。所以**题干、评分标准、条目表、作答四样材料任一改动，或 `max` / `lang` 任一变化，哈希都会变**，旧结果自动过期。

`context` 命令另外输出 `job` / `max_notes` / `min_anchored` / `context_hash` 四个键，它们不参与哈希，只是给 Agent 看的。

## 4. 落盘结果 `results/<学号>.json`

闸门全过之后由 `grade` 写入。在评分结果的基础上加了六个字段，并把 `criteria` 与 `marks` 规范化：

| 键 | 说明 |
|---|---|
| `job` / `student` / `max` | 批次名、学号、满分 |
| `graded_at` | 落盘时间戳 |
| `cautions` | WARN 列表（引文降级、等级被改、批注重叠让位、空心批注） |
| `context_hash` / `points` / `summary` | 原样保留 |
| `criteria[]` | `name` / `verdict` / `quote` / `evidence_unanchored`；`verdict` 是**降级之后**的结论 |
| `marks[]` | `id`（1 起）/ `quote` / `level` / `note` / `anchored` / `partial` / `start` / `end` / `level_fixed` / `dropped_overlap` |
| `anchored_ratio` | 锚定率，汇总与导出直接读这个字段 |

**`marks` 是真相，`results/<学号>.html` 只是按它重新锚定渲染出来的缓存。** 要统计、要对账，读 JSON。

`marks[].anchored` 与 `anchored_ratio` **不许手改**：`check` 会重新锚定一遍并逐条对账，对不上就报 ERROR。锚不上的条目照样留在列表里（`anchored: false`），判题卡右栏单列一节「未定位」，脚本不擅自把它摆到原文上。

## 5. 校准盖章 `.stamps/oracle.json`

`oracle check` 通过后写入：

```json
{
  "job": "short-answer-01",
  "stamped_at": "2026-08-31 16:31:45",
  "hashes": {
    "rubric": "sha256(rubric.md)",
    "question": "sha256(question.md)",
    "oracle_full": "sha256(oracle/full.md)",
    "oracle_broken": "sha256(oracle/broken.md)",
    "oracle_missing": "sha256(oracle/broken.json)"
  }
}
```

**五个哈希，一个都不能少。** 残缺版「缺哪几条」也算材料：改了 `broken.json` 等于换了一份校准，盖章必须跟着作废。

盖章不在、或五份材料任一哈希对不上时：`grade` 退出 2 拒绝开批，`summary` 与 `export` 拒绝生成，`check` 报 ERROR。这时要重跑 `oracle check`，再逐份重跑 `grade`。

`oracle check` 的判据：满分范例必须 `points == max` 且每条都是 `hit`；残缺版必须 `points < max`，且 `broken.json` 里列出的每个条目都是 `miss` 或 `partial`。两份范例同样要过 §3 的全部闸门。

## 6. 汇总与导出

`summary` 生成 `summary.md` 与 `summary.html`，只统计已通过、未过期、且**不以 `base-` 开头**的结果，三张表：按条目看命中／部分／未命中人数、按等级看批注条数、每份的得分与锚定率与未定位条数。

`export` 生成脱敏证据，**不含任何正文**：

```json
{
  "job": "short-answer-01",
  "max": 5,
  "criteria_names": ["定义准确", "例子贴切", "表述清楚"],
  "students": [
    {"id": "s01", "points": 4, "verdicts": ["hit", "partial", "hit"],
     "anchored_ratio": 1.0, "marks_count": 2, "context_hash": "sha256…"}
  ],
  "oracle_stamp": {"job": "…", "stamped_at": "…", "hashes": {"…": "…"}}
}
```

作答原文、引文、批语、总评一个字都不带出去。默认写到 `<job-dir>/export.json`，`--out` 可改。

`summary` 与 `export` 共用同一道新鲜度前置：盖章有效 + 没有过期结果，任一不满足就拒绝生成。

## 7. 退出码

| 码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 闸门未过（`rubric set` / `oracle check` / `grade` / `summary` / `check` / `export`）——逐条打印 ERROR，`inbox/` 里的文件原样保留供 Agent 修 |
| 2 | 用法或前置条件错误（目录不对、缺文件、没盖章、盖章作废、JSON 解析失败） |

`check` 的输出分三档：`[OK]` 通过项、`[WARN]` 提醒（不影响退出码）、`[ERROR]` 失败项（退出 1）。发布前要求 `check` **0 ERROR**，WARN 逐条说明。
