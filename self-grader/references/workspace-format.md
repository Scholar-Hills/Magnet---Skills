# 练习目录与脚本契约（self-grader）

这份文件是**文档、`scripts/selfgrade.py`、`scripts/selftest.py` 三方共享的约定**。
改这里的任何一条格式，同一个 commit 里必须同步改脚本与自测；反之亦然：脚本行为变了，
这份契约与对应断言一起改。不允许「先改脚本，文档以后补」。

以下所有相对路径都相对于一个练习目录。命令里的 `<slug>` 既可以是练习名（脚本按
`practice/<slug>` 找），也可以直接给一条路径（含 `/` 时按路径用）。

## 1. 目录布局

```
practice/<slug>/
  question.md                     题目原文（你贴进去，脚本只读不改）
  rubric.md                       评分标准原文（你自带，脚本只读不改，也不解析）
  criteria.json                   条目表（从 rubric 整理，你确认后写入）
  progress.md                     进度，只增不删；格式见 §5
  .stamps/baseline.json           基线盖章；见 §4
  attempts/01/answer.md           你的第一稿（脚本不代写）
                                  # 稿号只能是小写字母、数字与连字符（不超过 64 位，且以字母或数字开头）；建议两位数编号
  attempts/01/inbox/grade.json    Agent 写的评分结果；见 §3
  attempts/01/result.json         闸门全过之后脚本写的真相
  attempts/01/result.html         判题卡，可直接截图
  attempts/02/…                   第二稿，同样五个文件
  attempts/base-empty/…           对抗基线：空作答      ┐
  attempts/base-echo/…            对抗基线：题面回贴    ├ 由 baseline 生成，不许手改
  attempts/base-noise/…           对抗基线：无关段落    ┘
```

稿号用**两位数字**：`01`、`02`、`03`…。脚本按字符串排序找「上一稿」，用 `1`、`2`、`10`
会在第十稿时排错位置。三个基线目录名固定，不接受别的名字。

脚本只读写你指定的这一个练习目录，不联网，也不执行作答里的任何代码。

作答与题目里的 HTML 进引擎前先过白名单消毒：`script` / `style` / `iframe` 这类没有正文语义的标签**连内容一起丢**，其余标签脱掉外壳、文字保留。一条边界要知道：这类丢弃标签若**没有闭合**，按「到文件末尾自动闭合」处理——它之后的所有内容都会被当作该标签的内容一并丢掉（与浏览器的解析行为一致）。抽出来的正文突然变短时，先检查作答里有没有未闭合的 `<script>` / `<style>` / `<iframe>`。

## 2. `criteria.json`（条目表）

`criteria set <slug> --from <文件>` 写入；脚本落盘时补齐缺省字段，形状固定为：

```json
{
  "max": 5,
  "lang": "zh",
  "max_notes": 12,
  "min_anchored": 0.7,
  "criteria": [
    {"name": "定义准确", "points": 2},
    {"name": "用到本题", "points": 2},
    {"name": "自举例子", "points": 1}
  ]
}
```

| 字段 | 约束 |
|---|---|
| `max` | 满分，≥ 1 的整数，必填 |
| `lang` | `zh` 或 `en`，决定总评按字还是按词计数，默认 `zh` |
| `max_notes` | 每稿批注条数上限，≥ 1 的整数，默认 12 |
| `min_anchored` | 批注锚定率下限，0～1 的小数，默认 0.7 |
| `criteria[].name` | 非空字符串，同一张表里不许重名 |
| `criteria[].points` | 该条目的分值，非负整数；**要么每条都写，要么每条都不写** |

写了分值时，分值合计必须等于 `max` —— 合计小于满分意味着这份标准永远拿不到满分，
合计大于满分意味着分数会突破上限，两种都当场拒收。

**没标分值会弱多少**：脚本算不出「某一条降级该扣几分」，于是分值一致性那一闸整条让开，
只剩两条底线——引文一锚不到就整份退回、条目全部未命中就不许有分。所以**建议标分值**。

条目表被脚本每次加载时重新校验，不是只在写入时看一眼：手改 `criteria.json` 改坏了，
下一条命令就会停下来。

## 3. 评分结果契约（Agent 写进 `attempts/<NN>/inbox/grade.json`）

```json
{
  "context_hash": "sha256…",
  "points": 2,
  "summary": "一段 60–200 字（英文 60–200 词）的总评",
  "criteria": [
    {"name": "定义准确", "verdict": "hit", "quote": "支撑这条判定的作答原文引文"}
  ],
  "marks": [
    {"quote": "作答里的一句原话", "level": "major", "note": "至少 6 字的批语"}
  ]
}
```

顶层**恰好**这五个键，多一个少一个都拒收——换个字段名把契约绕过去这条路是堵死的。
条目对象只收 `name` / `verdict` / `quote`，批注对象只收 `quote` / `level` / `note`。

- `context_hash`：跑 `context <slug> <NN>` 拿到的那一个，原样抄进来。它是
  `sha256(规范 JSON{question_text, rubric_text, criteria, answer_text, max, lang})`，
  题目、评分标准、条目表、这一稿作答任一改动都会变。对不上就是没跑 `context`，
  或者材料改过还在用旧结果。
- `points`：整数，`0 <= points <= max`。条目标了分值时必须恰好等于
  `sum(hit → 分值, partial → 分值 // 2, miss → 0)`（部分命中取一半、向下取整）。
- `criteria`：与条目表**逐条对应，不多不少**。顺序不论，脚本按条目名对上后自己排回
  条目表的顺序；同一个条目名交两次算对不上。`verdict` 只能是 `hit` / `partial` / `miss`。
- `criteria[].quote`：判 `hit` 或 `partial` 时必须给，且必须能在这一稿作答里定位到。
  `miss` 时留空串。**引文锚不到就降为未命中**并记 `evidence_unanchored`；
  降完分数变了就整份退回重批——脚本不会替你把分数改小。
- `marks[].level`：`major` / `minor` / `remark` 三选一；别的值一律按 `remark` 处理并提示。
- `marks[].quote`：作答里的原话。锚定率（锚上的条数 ÷ 总条数）低于 `min_anchored` 就拒收。
- `marks[].note`：去掉首尾空白后至少 6 字；两条批语规范化后一字不差算重复，拒收。

`result.json` 是闸门全过之后脚本写的那一份，比提交的结果多出：`slug`、`attempt`、
`checkedAt`、`max`、`anchored_ratio`、`answer_hash`、`sameDraft`，以及每条批注被引擎
填上的 `id` / `anchored` / `partial` / `start` / `end` / `level_fixed` / `dropped_overlap`。
**`marks` 是真相，`result.html` 只是缓存**：判题卡每次都由脚本重新锚定后渲染。
`check` 会把落盘的 `anchored_ratio` 与每条 `anchored` 拿去和重新锚定的结论对账，
手改这些字段当场报错。

## 4. `.stamps/baseline.json`（基线盖章）

三份对抗基线全部批出 0 分、条目全部未命中之后，脚本才写这个文件：

```json
{
  "question": "sha256(题目纯文本)",
  "rubric":   "sha256(评分标准纯文本)",
  "criteria": "sha256(规范 JSON 条目表)",
  "checkedAt": "2026-08-31",
  "baselines": ["base-empty", "base-echo", "base-noise"]
}
```

没有这个文件，`grade` 一律不批真作答（退出 2）。盖章之后还有两道持续有效的闸：

1. **三哈希闸**：题目、评分标准、条目表任一改过，盖章作废，必须重跑 `baseline` 并把
   三份基线重批一遍。材料换了，之前那次「不会白给分」的证明就跟着失效。
2. **基线原样闸**：`attempts/base-*/answer.md` 必须与脚本此刻算出来的正身**逐字相同**
   （空文件 / 题面纯文本 + 换行 / 脚本里写死的那段无关文字），并且那份 `result.json`
   的 `answer_hash` 必须正是这份正身的哈希。把基线换成真作答再让它「过基线」这条路
   同样是堵死的。

## 5. `progress.md` 行格式（逐字契约）

首行是脚本建目录时写的标题行，其后每一次通过的批改追加一行，格式**逐字**为：

```
- <日期> · attempt <NN> · <points>/<max> · 未命中：<条目名，顿号分隔>[ · sameDraft]
```

- `<日期>` 取该次 `result.json` 里的 `checkedAt`（`YYYY-MM-DD`），不是运行 `progress` 的当天。
- 分隔符是全角间隔号 `·`，两侧各一个半角空格。
- 未命中条目按条目表顺序、用顿号 `、` 连接；一条都没漏时写「无」。
- 这一稿与上一稿作答一字不差时，行尾追加 ` · sameDraft`；否则没有这一段。

例：

```
# 进度（脚本只增不改，手改这里就对不上 result.json 了）

- 2026-08-31 · attempt 01 · 2/5 · 未命中：用到本题、自举例子
- 2026-08-31 · attempt 02 · 4/5 · 未命中：自举例子
```

**只增不删**。重批同一个 `attempt`：算出来的行与已有的某一行一字不差就不再追加；
判定变了（分数相同但漏的条目换了）或跨了一天，就会多出一行，旧行原样留着。

`check` 拿每份 `result.json` 重新算出这一行，在 `progress.md` 里逐字找：**找不到就报错**。
所以这个文件是硬契约，不是给人润色的笔记——想加备注就另开一个文件。

## 6. `export` 输出形状

`export <slug>` 把脱敏证据打到标准输出（不写文件）：

```json
{
  "slug": "opportunity-cost-01",
  "max": 5,
  "attempts": [
    {"id": "01", "points": 2, "verdicts": ["hit", "miss", "miss"],
     "anchored_ratio": 1.0, "sameDraft": false, "context_hash": "sha256…"}
  ],
  "baseline_stamp": { "…见 §4…" }
}
```

顶层四个键、每份六个字段，只有哈希、分数、判定与锚定率：题目、评分标准、作答、引文、
批语、条目名一个字都不带出去。想把练习记录贴给别人看时用它。

## 7. 退出码

| 码 | 含义 |
|---|---|
| 0 | 通过（可能有 WARN，WARN 不拦） |
| 1 | 闸门未过，有 ERROR。改 `inbox/grade.json`，别改作答 |
| 2 | 用法或前置条件不满足（目录不在、条目表没写、基线没过、盖章作废…） |
