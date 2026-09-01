# essay-sections 工作区与脚本契约

这份文件是**文档、`scripts/essayctl.py`、`scripts/selftest.py` 三方共享的约定**。改了这里的任何一个键名、数字或口径，同一个 commit 里必须同步改脚本与自测；反之脚本行为变了，也要回头改这份文件。不允许「先改脚本，文档以后补」。

全部路径都相对**工作区的父目录**——也就是你 `cd` 进去跑脚本的那个目录。`<slug>` 可以直接写稿名（解析成 `essays/<slug>/`），也可以写一个目录路径（含 `/` 时按目录处理，`check` 复核别人的工作区就是这么用的）。

## 1. 目录布局

```
essays/<slug>/
  essay.json          题目、文体、级别、场景、目标字数、背景、主论点、分区表、未纳入片段
                      只由脚本写（init / meta / import / assemble / outline add）
  source.txt          import 落进来的原文，脚本此后一个字节都不改
  blocks.json         切块结果：每个原子的字节区间与角色，assemble 靠它把原文切回去
  sections/
    intro.md          开头段
    body-01.md …      正文段，两位序号
    conclusion.md     结论段
                      这三类文件由**用户自己写**，脚本只在 assemble / outline add 建骨架时落地
  outline.jsonl       拆题账本，一行一轮，只增不改
  reflections.jsonl   反思账本，一行一条，只增不改
  ledger/
    <分区>.jsonl      该分区的评审账本，一行一条，只增不改
  chains.json         三类账本的链尾索引：每条链记「共几行 + 末行的 sha256」
  readings/
    <分区>-NN.json    荐读卡片
  versions/
    v1/  v2/ …        sections/ 的逐文件快照 + manifest.json
  inbox/              Agent 唯一可写的目录；脚本消费掉载荷之后立刻删除
  split-report.md     拆分报告，含「未纳入分段」片段的原文
  report.html         分段卡，自包含单页，不加载任何外部资源
```

`<slug>` 只能是小写字母、数字与连字符，不超过 64 位，且必须以字母或数字开头（`^[a-z0-9][a-z0-9-]{0,63}$`）。

分区名只有三种形状：`intro`、`body-NN`（两位数字）、`conclusion`（`^(intro|conclusion|body-\d{2})$`）。别的名字一律退出 2。

## 2. `essay.json`

```json
{
  "slug": "remote-work-cities-01",
  "title": "远程办公者该怎么选城市",
  "genre": "议论文",
  "level": "本科通识写作课",
  "setting": "untimed",
  "targetWords": 1200,
  "background": "写作课的期末长作业，允许查资料，交之前可以改三稿。",
  "thesis": "远程办公只是把「离公司多近」从选城市的清单上划掉，并没有替你补上新的一条。",
  "createdAt": "2026-09-01T01:55:32Z",
  "segments": [
    {"name": "intro", "subquestion": "开头段：交代题目、给出主论点。",
     "start": 37, "end": 484, "blocks": [2]}
  ],
  "outside": [{"start": 0, "end": 35, "role": "block"},
              {"start": 35, "end": 37, "role": "space"}],
  "fallback": false,
  "sourceFile": "source.txt"
}
```

- `setting` 只能是 `timed` 或 `untimed`；`targetWords` 是 0 以上的整数。两者都进上下文哈希，改了它们，之前写的评审全部作废。
- `thesis`、`background`、`genre`、`level` 同样进上下文哈希。
- `segments` 的顺序就是文章的顺序。从已有稿进来的分区带 `start` / `end` / `blocks`（`source.txt` 里的字节区间与块号）；从题目进来的分区只有 `name` 与 `subquestion`。
- `subquestion`：`intro` 与 `conclusion` 由脚本填一句固定的结构说明，正文段填拆题给的那条子问题。
- `outside`：没有进任何一段的片段，`role` 是 `block`（没分到段的块）/ `space`（纯空白分隔）/ `outside`（块外文字）/ `table`（表格）/ `textbox`（文本框）。
- `fallback`：分组载荷不合格、被整段导入时为 `true`。
- 全部字段由脚本写。**手改这个文件会让 `check` 的保真校验或上下文复算失败**，不要手改。

## 3. `source.txt` 与 `blocks.json`

`import` 做两件事：把原文原样存成 `source.txt`，再把它切成**原子**，每个原子记下 UTF-8 字节区间。

- md / txt：空行分段；段与段之间的空白单独成原子。
- html：块级标签断块，行内标签（`a` `b` `em` `strong` `span` `code` …）接着算同一块；包裹层与裸文本各自成原子。
- docx：只用 `zipfile` + `xml.etree` 读 `word/document.xml`。正文段落进块；**表格与文本框的文字被搬到正文之后的附录区**，不在原来的位置，也不参与分段。图片、脚注、修订痕迹读不了。
- 读文本文件时把 `\r\n` 与 `\r` 归一成 `\n`，之后一个字节都不改。docx 没有原始文本文件，`source.txt` 是脚本按「段落 + 两个换行」重新拼出来的那一份，偏移都相对它算。

```json
{"file": "v1.md", "format": "md", "chars": 1265, "bytes": 3757, "blockCount": 9,
 "atoms": [{"i": 0, "start": 0, "end": 35, "role": "block", "no": 1,
            "heading": true, "preview": "# 远程办公者该怎么选城市"},
           {"i": 1, "start": 35, "end": 37, "role": "space"}]}
```

`role` 取值同上。只有 `role` 为 `block` 的原子有 `no`（从 1 开始的块号）、`heading`、`preview`（46 字预览）。

`import` 打印给 Agent 看的是精简视图，**不含原文**：

```json
{"slug": "…", "format": "md", "blockCount": 9, "outsideBlocks": 0,
 "blocks": [{"no": 1, "heading": true, "chars": 13, "preview": "# 远程办公者该怎么选城市"}]}
```

`import` 在已经有分区的工作区上直接退出 2：**两个入口不可中途换向**，要重来请另起一个 slug。

## 4. `inbox/groups.json`（分组载荷）

```json
{"intro": [2], "body": [[3], [4], [5], [6], [7], [8]], "conclusion": [9]}
```

- `body` 必填，是「一组组块号」；`intro` 与 `conclusion` 可省。
- 每个块号只能用一次；重复号、越界号、不是整数的号一律丢弃并写进拆分报告的「丢弃的段号」。
- `body` 缺失、不是数组、或者一个有效块号都没有 → **整段导入**（`fallback: true`），全文归成一段，一个字节也不切。
- 没被分到任何一段、但落在某段跨度里面的块，并进那一段；落在最后一段之后的块，并进最后一段。两种情况都逐条写进拆分报告的「已并入的未分配块」。
- **保真恒等式**：把全部分段的字节区间与全部「未纳入」片段按偏移拼回来，必须逐字节等于 `source.txt`。不等就退出 1 且**一个字都不落盘**。

## 5. `inbox/outline.json`（拆题载荷）

```json
{"items": ["房租与生活成本的差价，摊到一年之后还剩多少？", "…"]}
```

三种模式由脚本判定，Agent 不能指定：

| 模式 | 什么时候进 | 条数 |
|---|---|---|
| `initial` | `outline.jsonl` 还是空的，而且正文段都还没写字 | 必须 6–10 条 |
| `bind` | `outline.jsonl` 还是空的，但正文段已经有字（先贴稿后补子问题） | **必须正好等于正文段数** |
| `extra` | 已经有过至少一轮 | ≤4 条 |

- 空串或非字符串的条目 → 整轮拒收。
- 小写去重：跟已有条目重复的会被丢掉并在输出里报 WARN；一条新的都不剩 → 拒收。
- `outline.jsonl` 的行数就是轮数，**合计封顶 4 轮**，到顶不再叫模型。

## 6. `context <slug> <分区>` 的输出

`stdout` 只有一份 JSON，别的话都不打印：

```json
{
  "segment": "body-04",
  "text": "（这一段剥掉标签、压过空白之后的纯文本）",
  "subquestion": "一年算下来的真实成本与退出成本各是多少？",
  "thesis": "…",
  "background": {"genre": "议论文", "level": "本科通识写作课",
                 "setting": "untimed", "targetWords": 1200, "text": "…"},
  "reflections": [{"scope": "segment", "when": "…", "atScore": 2, "text": "…"}],
  "previousReview": {"scores": {"language": 4, "answersSubquestion": 3,
                                "advancesThesis": 4}, "segmentChanged": false},
  "contextHash": "71318a9b…"
}
```

- 分区纯文本不足 **10 字** 时 `context` 直接退出 1，不给上下文包，`review add` 也不收。
- `reflections` 最多 3 条，顺序固定：**同段 > 总反思 > 其他段**，组内新→旧。
- `previousReview` 是这一段账本里最后一条评审；`segmentChanged` 为 `true` 表示原文在那次评审之后动过，上面的分数已经过期。没评过就是 `null`。
- `contextHash = sha256(canonical({segmentText, subquestion, thesis, background, reflectionPack}))`。`canonical` 指 `json.dumps(…, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`。原文、子问题、主论点、背景（含文体 / 级别 / 场景 / 目标字数）、反思包，任何一样变了，哈希就变。

## 7. `inbox/review.json`（评审载荷）

```json
{
  "contextHash": "（从上一步的输出里原样取）",
  "scores": {"language": 2, "answersSubquestion": 1, "advancesThesis": 2},
  "note": "整段没有一个可以照着做的判据……",
  "quotes": ["所以最重要的还是要结合自身实际，全面权衡，理性判断"]
}
```

- **顶层只认这四个键，多一个就整份拒收**（白名单，不是黑名单）。综合分与反思触发分都由脚本从三维分算，手填一律不认。
- 出现 `improved` 或 `rewrite` 键 → 拒收，并提示「要改句子，把这一段丢给 red-pen」。
- `scores` 只认三个维度，各一个 **1–5 的整数**；布尔、小数、字符串、负号、越界都不算，多一个维度也拒收。三个维度的含义见 `workflow-rules.md`。
- `note` 是一段评语，不能空着。
- `quotes` 至少 1 条，每条**空白归一之后必须是该段纯文本的子串**，彼此不重复。
- **引用长度上限 40%**：单条与合计都不许超过。**分母是「该段纯文本去掉全部空白之后的长度」**，跟 `status` / `report` 上显示的「字数」不是一个口径——那个字数是压过空白但保留词间空格的纯文本长度，中文两者几乎相等，英文稿会明显更长。拿不准就少引一点。

## 8. 账本行

三条链的行都由 `append_row` 写，共有三个字段：`seq`（从 1 开始，等于行号）、`when`（UTC，秒精度）、`prevHash`（上一行整行的 sha256；第一行是空串的 sha256）。行的字节形状是 `canonical` 的输出，**改一个字节 `check` 就报出来**。

### 8.1 `ledger/<分区>.jsonl`（评审）

```json
{"background": {…}, "composite": 2, "contextHash": "…", "flags": [],
 "note": "…", "prevHash": "…", "quotes": ["…"], "reflectionPack": [],
 "sameDraft": false, "scores": {…}, "segment": "body-04", "segmentHash": "…",
 "segmentText": "…", "seq": 1, "stage": "review", "subquestion": "…",
 "thesis": "…", "versionNumber": 0, "when": "…"}
```

- `composite`：三维均值四舍五入（`int(均值 + 0.5)`）。**这是综合分，脚本算，载荷里不许出现。**
- `segmentHash`：当刻分区纯文本的 sha256。`sameDraft` 为 `true` 表示跟上一条评审是同一稿。
- `segmentText` / `subquestion` / `thesis` / `background` / `reflectionPack`：算 `contextHash` 用的那五样材料，原样带在行里。**`check` 只凭这一行就能离线复算 `contextHash` 与 `segmentHash`，不依赖当前的 `sections/`**——所以用户后来改了稿，旧行照样复算得过。
- `flags`：空心闸打的标记，`thin-quote`（未引用原文）与 `look-alike:<分区>`（评审雷同）。它们是 WARN，不拦入账。
- `versionNumber`：写这一行时最新的版本号，还没拍过快照就是 0。

### 8.2 `reflections.jsonl`

```json
{"atScore": 2, "atSeq": 1, "noDiff": false, "prevHash": "…", "scope": "segment",
 "segment": "body-04", "segmentHash": "…", "seq": 1, "snapshot": "…",
 "stage": "reflect", "text": "…", "versionNumber": 0, "when": "…"}
```

- `scope` 为 `segment`（钉在某一段某一稿上）或 `essay`（总反思，随时可写）。
- 区域反思要求该段**最新一条评审的综合分 ≤2 或 =5**，否则拒收；`atScore` 与 `atSeq` 由脚本从那一行取，载荷里带 `atScore` 直接拒收。
- `snapshot` 是当刻的分区纯文本；超过 20000 字就不存快照、`noDiff` 记 `true`（避免永久误报「原文已修改」）。总反思固定 `noDiff: true`。
- 载荷只认一个键：`{"text": "…"}`。文本剥掉标签之后上限 4000 字；`x<0` 这类符号不会被当成标签吞掉。

### 8.3 `outline.jsonl`

```json
{"dropped": [], "items": ["…"], "mode": "bind", "prevHash": "…", "seq": 1,
 "stage": "outline", "when": "…"}
```

### 8.4 `chains.json`

```json
{"outline.jsonl": {"seq": 1, "hash": "…"},
 "reflections.jsonl": {"seq": 2, "hash": "…"},
 "ledger/body-04.jsonl": {"seq": 2, "hash": "…"}}
```

每条链记「共几行 + 末行整行的 sha256」。`append_row` 是**先追加行、再写索引**，所以写盘被打断只可能让索引落后一格。

**这套账本能证明什么、不能证明什么，说清楚**：账本挡的是不知情的手改；知道 `chains.json` 存在的人两处一起改就能过。它证明的是账本没被顺手改过，不是不可伪造。只要 `chains.json` 还在，行少了就是硬错——`--rebuild-index` 不会替你抹掉少掉的行，只修写盘被打断时落后的索引。

## 9. `readings/<分区>-NN.json`

```json
{"segment": "body-01", "title": "…", "authors": "…", "year": "2024",
 "summary": "…", "url": "", "verified": false, "addedAt": "…"}
```

- 载荷只认 `title` / `authors` / `year` / `summary` / `url` / `verified` 六个键，多一个拒收。
- `title` / `authors` / `year` 必填且非空。
- `verified` 缺省 `false`，`status`、`report` 与 `check` 都会标「引用未核实」。**脚本不联网，不会替你核实任何出处。**
- 同一分区里 `title` 小写相同的材料拒收。

## 10. `versions/vN/`

`version` 把 `sections/` 逐文件拷进去，再写一份 `manifest.json`：

```json
{"version": 1, "createdAt": "…", "files": {"intro.md": "sha256…"}}
```

编号按**已有的最大号 + 1**，只增不回收：中间那一版被删掉了，下一版也接着最大号往后排，绝不撞号。`check` 会逐个复核 manifest 里的哈希。

## 11. `export --evidence` 的脱敏证据包

```json
{"slug": "…",
 "rows": [{"seq": 1, "when": "…", "stage": "review", "segment": "body-04",
           "segmentHash": "…", "contextHash": "…", "scores": {…},
           "sameDraft": false, "segmentChanged": true}],
 "versions": [{"version": 1, "files": {"intro.md": "sha256…"}}]}
```

只有这九个行字段与版本清单，**正文、引用、评语一个字都不带**。给别人看「我确实按纪律跑过」用这个，不要直接发工作区。

不带 `--evidence` 的 `export` 是另一回事：它把各段原文按顺序拼成整篇，再把各段最新评审作为侧注附在文末，那份是带正文的。

## 12. 退出码

| 码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 闸门不过（分值、引用、新鲜度、账本链、拆题轮数、保真校验…） |
| 2 | 用法或前置条件不满足（工作区不存在、文件找不到、JSON 解析失败、分区名非法…） |

`check` 的 WARN 不影响退出码；只要有 ERROR 就退出 1。

## 13. `check` 复核了什么

- `essay.json` 的分区表与 `sections/` 一一对应，两边都不许有对方没有的。
- `source.txt` 存在时跑保真恒等式：分段偏移 + 未纳入片段拼回来必须等于原文。
- 三类账本逐行复算：`seq` 与行号对得上、`prevHash` 接得上上一行、行的字节形状就是 `canonical` 的输出。
- 每条评审行的 `contextHash` / `segmentHash` 用行内自带的材料重算、三维分合法、`composite` 是均值四舍五入、引用仍是该段原文的子串且没超 40%、评语没有跟别的分区一模一样。
- 每条区域反思的 `atSeq` 指得到对应的评审行，`atScore` 与那一行的综合分相等。
- 荐读字段齐全；`versions/vN/manifest.json` 里的哈希与快照文件相符；`inbox/` 已经空了。
- WARN（不拦）：某段「原文已修改」、评审行上的 `flags`、荐读仍标「引用未核实」。

### `--rebuild-index` 什么时候能用

只有一种情况：`check` 报出「链尾索引落后 / 索引缺失」，而且每条链自身逐行复算都自洽。这时 `check` 会主动提示你可以跑 `check <slug> --rebuild-index`，它按账本的实际内容重写 `chains.json`。

其余情况一律拒绝重建，也不给任何指路：

- **索引超前**（记着第 N 行，账本里没有对得上的那一行）或**账本被删空而索引还记着行**——脚本是先落行再写索引，打断做不出这种状态，只可能是行没了。行没了只能自己从 `versions/` 快照、备份或版本管理里找回来，不许靠改索引把它抹平。
- **链自身就是断的**（行被改写、`seq` 跳号、`prevHash` 接不上）——重建只会把篡改盖过去，先照报出来的行号把账本查清楚。
