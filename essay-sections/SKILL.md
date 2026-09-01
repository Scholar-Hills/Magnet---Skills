---
name: essay-sections
description: 分段写作教练——把一篇已经写好的稿子（或者一个还没动笔的题目）拆成「开头 / 若干子问题段 / 结论」，一段一张卡。贴稿进去一个字不改，只是按字节偏移拆开；每段单独评审，三个 1–5 的格子加一段评语，每条评审必须逐字引用该段原文；评审连同当刻原文追加进只增不改的账本，你改了原文它标「原文已修改」，某段评得极端时它让你写一句反思钉在那一稿上。不改稿、不代写、不给改写建议。Use when the user wants section-by-section feedback on an essay or long-form draft, wants to break a topic into sub-questions before writing, wants to see which paragraph fails to answer its own question, or wants a per-paragraph record that survives revisions.
license: MIT
allowed-tools: Bash, Read, Write, Edit
---

# 分段写作教练（essay-sections）

一句话：**它把一篇文章拆成八张卡，然后一段一段地问「这段答了自己那个问题吗」。** 拆开这一步一个字都不改——脚本按字节偏移把原文切回来，切不进任何一段的文字逐条列给你看。每条评审必须从该段里逐字引一句话，证明确实读过。分数只有三个 1–5 的格子，没有比例、没有百分比、没有整体评级。

## 你能对它说什么

| 你说 | 它做 |
|---|---|
| （丢一篇写好的稿子）「帮我看看每段」 | 贴稿 → 拆成八张分段卡 → 逐段评审 → 一页可截图的卡片 |
| （只有一个题目）「先帮我拆问题」 | 拆出 6–10 条子问题，建好分区骨架，**正文你自己写** |
| 「第 3 段你帮我写了吧」 | 拒绝，并说明这份 Skill 从设计上就不代写正文 |
| 「这段为什么只有 2 分」 | 念出那一段的三维分与逐字引用，讨论；不同意就重跑一次评审 |
| （自己改完某几段）「再看一遍」 | 重跑 `context`，只有改过的段落才在走势上多一个点 |
| 「这句话该怎么改」 | 交给 red-pen——本 Skill 只判分与举证，不改句子 |

## 前置检查（不可跳过）

0. **定位脚本**。本 Skill 的脚本在 Skill 目录下，不在用户工作区。按顺序找 `essay-sections/scripts/essayctl.py`，取第一个存在的绝对路径记作 `ESSAYCTL`：
   ① 这份 SKILL.md 所在目录下的 `scripts/essayctl.py`（你就是从那个目录读到本文件的）；② Claude Code：`~/.claude/skills/essay-sections/`、当前项目 `.claude/skills/essay-sections/`；③ WorkBuddy / CodeBuddy：`~/.workbuddy-ai/skills/essay-sections/`、`~/.workbuddy/skills/essay-sections/`、`~/.codebuddy/skills/essay-sections/`、当前项目 `.codebuddy/skills/essay-sections/`；④ OpenClaw：`~/.openclaw/workspace/skills/essay-sections/`；⑤ 小红书 `redskill install` 的默认位置：当前目录 `./skills/essay-sections/`；⑥ 用户在对话里指定的目录；⑦ 都没有就搜一次：`find . ~/.claude ~/.workbuddy ~/.workbuddy-ai ~/.codebuddy ~/.openclaw -path '*essay-sections/scripts/essayctl.py' 2>/dev/null | head -1`。
   本文后面所有 `python3 scripts/essayctl.py …` 都读作 `python3 "$ESSAYCTL" …`，并且**始终在用户工作区（`essays/` 的父目录）下执行**：`cd <工作区> && python3 "$ESSAYCTL" status <slug>`。脚本没有 `--root` 选项，工作区就是当前目录。
   **七处都找不到就立即停止**，告诉用户「这份 Skill 的脚本缺失，请重新下载完整目录」。**任何情况下都不要自己写一个替代脚本**，也不要「先手工拆一版」——手拆的分段没有偏移校验，会把丢掉的段落当成没丢，那正是这份 Skill 存在的理由。
1. 运行 `python3 "$ESSAYCTL" doctor`。`python3` 不存在就试 `python`（Windows 常见）；两个都没有，告诉用户先装 Python 3.8+，不要继续。
2. 稿子都放在**当前工作区**（用户项目或文稿目录，不是 Skill 目录）的 `essays/` 下。第一次收稿前先 `pwd` 看一眼：如果当前目录是家目录、桌面或其它不像工作目录的地方，先问用户一句「稿子、评审和版本我打算放在 `<当前路径>/essays/`，可以吗？想换个地方现在告诉我」。定下来之后就别再换——同一篇稿子的账本要在同一处才连得起来。
3. 位置参数别写反：**每个子命令的第一个位置参数都是 `<slug>`**（`review add <slug> <分区> --from …`、`reading add <slug> <分区> --from …`、`reflect add <slug> [--segment <分区>] --from …`）。`--from` 指向的载荷要放在 `essays/<slug>/inbox/` 下，脚本消费完会把它删掉。
4. 第一次用之前，翻一眼 Skill 目录里 `examples/essays/remote-work-cities-01/` 这个示例工作区：`ledger/*.jsonl` 是评审入账之后的样子，`split-report.md` 是拆分报告的样子，`report.html` 是交付的样子。照着它写比照着文字描述不容易出错。

**回复语言跟随用户**：用户用中文就全程中文，用英文就全程英文，不要中英混着来。稿子是什么语言与你用什么语言回复是两件事。

## 流程

格式契约以 `references/workspace-format.md` 为准，纪律以 `references/workflow-rules.md` 为准，**先读这两份**再动手。

**动手前先说一句**：「我先把你的稿子拆成分段卡——拆的时候一个字都不改，切不进任何一段的文字我会逐条列给你。然后一段一段评，每条评审我都会从那一段里逐字引一句话。我不改你的稿子，也不替你写任何一段。」非交互场景（批处理、子任务）就把这句写进最终报告的开头。

### 入口 A：从已有稿（主入口）

**1. 建工作区**

```
python3 scripts/essayctl.py init <slug> --title "<题目>" --genre "<文体>" \
    --level "<级别>" --setting untimed --target-words 1200 --background "<背景>"
```

`<slug>` 用小写英文加两位序号（如 `remote-work-cities-01`）。`--setting` 只有 `timed` / `untimed` 两种。题目背景以后要改用 `meta <slug> --…`，**但改了背景之前跑过的 `context` 就全过期了**，所以尽量一次填好；主论点可以等读完稿再用 `meta <slug> --thesis "…"` 补。

**2. 贴稿**

```
python3 scripts/essayctl.py import <slug> <稿子文件>
```

收 `.md` / `.txt` / `.html` / `.docx`。用户是在对话里贴的稿子就先存成文件（放工作区里，别放 `essays/<slug>/` 下面），**存的时候一个字都不许改**——那份文件是后面所有偏移与引用的依据。

它把原文原样存成 `source.txt`，切成块并记住每块的字节区间，然后打印一份**只有块号、字数与 46 字预览**的清单给你。

`.docx` 只读得到文字段落：**表格与文本框里的字会被搬到正文之后的附录区，不在原来的位置，并且必然出现在「未纳入分段」清单里**；图片、脚注与修订痕迹读不了。收到 docx 时把这句先告诉用户，排版复杂的稿子建议他先在 Word 里另存为 `.md` 或 `.txt` 再进来。

**同一篇不能拆第二次**：`import` 在已经有分区的工作区上会直接拒收。要重来请另起一个 slug。

**3. 回分组**

把清单读一遍，判断哪几块是开头、哪几块各自成一个正文段、哪几块是结论，写进 `essays/<slug>/inbox/groups.json`：

```json
{"intro": [2], "body": [[3], [4], [5], [6], [7], [8]], "conclusion": [9]}
```

```
python3 scripts/essayctl.py assemble <slug> --from essays/<slug>/inbox/groups.json
```

脚本按偏移把原文切回来，跑一遍保真校验（全部分段 + 全部未纳入片段拼回来必须逐字节等于原文），写出 `sections/*.md` 与 `split-report.md`。

**输出里的「未纳入分段 N 条」要念给用户听**，并告诉他有字的片段连原文一起列在 `split-report.md` 里，脚本不替他决定这些字该去哪。标题行通常就在里面，那是正常的。

**4. 补子问题（可选但推荐）**

这一篇还没拆过题、正文段又已经有字（也就是刚从已有稿进来）时，`outline add` 自动走 **bind 模式**：**条数必须正好等于正文段数**，按位置绑上去，给多给少都拒收。以后再补角度就是增补模式，每轮 ≤4 条。

```json
{"items": ["房租与生活成本的差价，摊到一年之后还剩多少？", "…（正好 N 条）"]}
```

```
python3 scripts/essayctl.py outline add <slug> --from essays/<slug>/inbox/outline.json
```

子问题写「这一段**应该**回答的那个问题」，不是「这一段现在在讲什么」——`answersSubquestion` 这个维度量的就是两者的差距。

**5. 逐段拿上下文包**

```
python3 scripts/essayctl.py context <slug> <分区>
```

`stdout` 只有一份 JSON：这一段的纯文本、子问题、主论点、背景、最多 3 条相关反思、上一次评审与它是否已经过期、还有 `contextHash`。**你评的就是 `text` 里的那一份**，不要照着用户在对话里贴的原文评——两者可能差一个空格，引用会对不上。`contextHash` 从这份输出里原样取，不要自己算、不要手抄。

**6. 写评审**

写进 `essays/<slug>/inbox/review.json`：

```json
{
  "contextHash": "（从上一步的输出里原样取）",
  "scores": {"language": 2, "answersSubquestion": 1, "advancesThesis": 2},
  "note": "整段没有一个可以照着做的判据：综合考虑、因人而异，都是把选择权原样还给读者。子问题问的是一年的真实成本，这里一个数字都没有出现。",
  "quotes": ["所以最重要的还是要结合自身实际，全面权衡，理性判断"]
}
```

```
python3 scripts/essayctl.py review add <slug> <分区> --from essays/<slug>/inbox/review.json
```

写的时候盯住这几条（完整闸门见 `references/workflow-rules.md`）：

- **顶层只认 `contextHash` / `scores` / `note` / `quotes` 四个键，多一个整份拒收。** 综合分由脚本从三维分算，别自己塞一个进去。
- **三个维度各一个 1–5 的整数**：`language`（句子本身立不立得住）、`answersSubquestion`（有没有回答自己那条子问题）、`advancesThesis`（有没有把主论点往前推）。布尔、小数、字符串、越界都不算。
- **`note` 说清这一段出了什么问题或者好在哪**，指着具体的句子说，不要写「还行」「再改改」。
- **`quotes` 至少 1 条，从 `text` 里一字不差地抄**，彼此不重复；单条与合计都不许超过该段的 40%（分母是去掉全部空白的纯文本长度，比卡片上显示的字数口径更严，拿不准就少引一点）。
- **不写 `improved` / `rewrite`**：出现即拒收。要改句子，把这一段丢给 red-pen。
- **每段一份自己的评语**：两个分区的评语一模一样会整份拒收。

**退出 1 就照着报出来的原因改载荷，最多重出一次。** 两次还不过，如实告诉用户「这一段我没评成，卡在哪一条」，不要改闸门、不要挑一个能过的说法糊过去。

**7. 反思（评到 2 分以下或满分时）**

`review add` 打印「这一段评到了 N 分，可以写一条反思」时，问用户要不要写一句——**反思是用户写的，不是你写的**。区域反思只在该段最新评审的综合分 ≤2 或 =5 时才收；总反思随时可写。

```
python3 scripts/essayctl.py reflect add <slug> --segment <分区> --from essays/<slug>/inbox/reflect.json
python3 scripts/essayctl.py reflect add <slug> --from essays/<slug>/inbox/reflect.json
```

载荷只认一个键 `{"text": "…"}`；触发分由脚本从账本取。反思自带当刻的段落快照，所以它**钉在那一稿上**，以后改了稿它还在。**写完反思之后，之前跑过的 `context` 就过期了**（反思会进上下文包），要重新跑。

**8. 荐读（可选）**

```
python3 scripts/essayctl.py reading add <slug> <分区> --from essays/<slug>/inbox/reading.json
```

载荷认 `title` / `authors` / `year` / `summary` / `url` / `verified`，前三个必填。`verified` 缺省 `false`，卡片上标「引用未核实」。**交付时必须明说一句「这几条我没有核实，请自行检索确认之后再引用」**——脚本不联网，也不会替任何人核实出处。

**9. 交付**

```
python3 scripts/essayctl.py version <slug>     # 给当前 sections/ 拍一张快照
python3 scripts/essayctl.py status <slug>      # 每段一行：字数、哈希、mtime、最新分、走势、过期标记
python3 scripts/essayctl.py report <slug>      # 生成 report.html 分段卡
```

交付时说清三件事：

1. **分段卡在哪**：`essays/<slug>/report.html`，用浏览器打开可以直接截图。
2. **哪几段的分数已经过期**：`status` 里标着 `** 原文已修改` 的那几段，说明它们在最近一次评审之后动过。
3. **未纳入分段有几条**：有字的那几条在 `split-report.md` 里，请用户自己决定要不要补进某一段。

对话里挑两三段最要紧的展开讲，**不要把八段评语整份复述一遍**——用户打开分段卡看得更清楚。

### 入口 B：从题目（还没动笔）

```
python3 scripts/essayctl.py init <slug> --title "<题目>" --genre "<文体>" --setting untimed
python3 scripts/essayctl.py outline add <slug> --from essays/<slug>/inbox/outline.json
```

初始模式**必须给 6–10 条**子问题，判据是「能独立成段、能一步步把论证搭起来、彼此接得上」。脚本会建出 `intro` + N 个正文段 + `conclusion` 的骨架，`sections/*.md` 是空文件。

**接下来是用户写正文，不是你写。** 用户说「你先写一段我改」时，明确拒绝：这份 Skill 的价值就在于账本里记的是他自己的文字与他自己的改动过程，代写会让整套记录失去意义。

想不出角度可以再叫一轮增补（**每轮 ≤4 条，合计封顶 4 轮**，到顶脚本不再收）。写完某一段就走入口 A 的第 5 步开始评。

## 门禁（必须遵守）

- **没跑 `context` 就不写评审。** 哈希只有那一个来源，不许手抄、不许凭上一轮对话的印象评。
- **不填综合分。** 载荷顶层只有四个键，综合分与反思触发分都由脚本从三维分算。
- **不给改写。** `improved` / `rewrite` 出现即拒收。要改句子，把那一段丢给 red-pen。
- **不写 `sections/`。** 正文永远是用户的。「第 3 段你帮我写了吧」一律拒绝，并解释为什么。从题目入口建出来的空文件也一样，等用户填。
- **账本只经脚本写。** 工作区 `essays/<slug>/` 里你只能写 `inbox/`，别的一个文件都不碰：不手改 `essay.json`、`*.jsonl`、`chains.json`、`report.html`、`split-report.md`。（用户贴过来的稿子存成文件是例外，但那份文件放在工作区外面，`import` 之后就不再动它。）
- **不改脚本、不改闸门常量**来让一份评审通过。
- **荐读一律标未核实。** 交付时把「请自行检索确认」这句说出来，不要把模型给的书名当成查过的出处。
- **未纳入分段不许瞒着。** 拆完就报条数，别等用户发现少了一段才说。

## 排障

**`check` 说链尾索引对不上**：先看它是哪一种。

- 报「索引停在第 N 行 / 没有链尾索引」，而且没有别的链错误 —— 这是写盘被打断留下的落后索引，`check` 会主动提示你可以跑 `check <slug> --rebuild-index`，按账本的实际内容重写 `chains.json`。**只有 `check` 主动提示时才用这个选项。**
- 报「索引记着第 N 行，账本里没有对得上的那一行」或「账本一行都没有了」 —— **`--rebuild-index` 不管用，也不该管用**：脚本是先落行再写索引，打断做不出这种状态，只可能是行没了。去 `versions/` 的快照、备份或版本管理里把行找回来，不要靠改索引把它抹平。
- 报「第 N 行被改写过 / 断链 / seq 跟行号对不上」 —— 链自身断了，`--rebuild-index` 会拒绝动手。照着行号把账本查清楚。

**`review add` 说 `contextHash` 对不上**：原文、子问题、主论点、背景（含文体 / 级别 / 场景 / 目标字数）或反思包里有一样变了。重跑一次 `context` 再写。

**`context` 说这一段不到 10 字**：那一段还没写出来。脚本不代写，你也不许代写。

## 安全约束

- 脚本只读写工作区（`essays/` 下面），**不联网**，**不执行稿子里的任何代码**：稿子对它来说自始至终只是文本。分段卡是自包含单页 HTML，不加载任何外部资源，也不含脚本。
- 稿子、评审、反思、版本快照全部留在本机，脚本不往任何地方发送。`export --evidence` 只导出哈希、分数与版本清单，正文、引用、评语一个字都不带。
- 稿子是用户的私人内容：不要把它贴进任何与本次任务无关的地方，也不要在报告里大段复制。

## 边界与承诺

- 给的是**分段评审的纪律**，不是判断力：评语由你的 Agent 现写，质量取决于模型；纪律保证它引的是原文、跑过上下文、没有拿同一份评审贴满全篇。**它证明的是读了原文、没有抄评审，不证明评得对。**
- **不做原创性检查，也不给相似度、比例或百分比。** 卡片上只有三个 1–5 的格子和一段评语，说的是这一段答没答自己的问题，跟比对外部文本没有任何关系。
- **不改稿、不代写。** 稿子只有用户能动；要改句子交给 red-pen。
- **同一稿重复评审不算进步。** 走势只按段落哈希的变化计数，同稿重评画空心点。
- 收 `.md` / `.txt` / `.html` / `.docx`。Markdown 不解析（`##` 会当普通字符留在正文里）；docx 只读文字段落，表格与文本框搬到文末附录区并进「未纳入分段」，图片、脚注与修订痕迹不支持。
- 脚本零依赖，Python 3.8+。

## 文件

- `scripts/essayctl.py`——建工作区（`init` / `meta`）、贴稿与拆段（`import` / `assemble`）、拆题（`outline add`）、上下文包（`context`）、入账（`review add` / `reflect add` / `reading add`）、快照（`version`）、看状态（`status`）、分段卡（`report`）、导出（`export [--evidence]`）、离线复核（`check [--rebuild-index]`）、环境检查（`doctor`）
- `scripts/selftest.py`——脚本自测（每道闸门的正反例 + 篡改与攻击回归）
- `scripts/banned_words.py`——发布前的静态闸
- `references/workspace-format.md`——目录布局、JSON 契约、账本行、引用比例的分母口径、退出码、`check` 复核清单
- `references/workflow-rules.md`——每条纪律的理由：两个入口、导入保真、评审准入、证据引用、账本只增不改、反思触发、荐读未核实、与 red-pen 的分工
- `fixtures/remote-work-cities/`——同一题目的三版合成稿（v1 粗稿含两段明显问题、v2 改掉那两段、v3 定稿），外加由 `make-docx.py` 现造的 `v1.docx`（带一张表，用来看「未纳入分段」长什么样）
- `examples/essays/remote-work-cities-01/`——由那三版稿实跑生成的示例工作区：8 段、18 条评审（每段 2–3 条，跨 v1→v2→v3）、1 条区域反思 + 1 条总反思、1 份标未核实的荐读、2 个版本快照，`check` 0 ERROR（2 条 WARN 是故意留的：`body-01` 在最后一次评审之后又改过一次，分数已过期；荐读没核实）

---

English summary: essay-sections splits a finished draft — or a topic you have not started — into an intro, a set of sub-question sections, and a conclusion, one card each. Pasting a draft in changes nothing: the script records byte offsets for every block, the model returns only block numbers, and the script slices the original back out, then proves it by reassembling every section plus every unassigned fragment and comparing byte-for-byte against the source. Anything that did not land in a section is listed verbatim in `split-report.md` rather than silently dropped; for `.docx`, tables and text boxes are moved to an appendix after the body and always show up there. Each review must carry the `contextHash` printed by `context`, three integer scores from 1 to 5, a note, and at least one quote copied verbatim from that section — quotes may not exceed 40% of it. The composite score is computed by the script and rejected if submitted. Reviews are appended to a hash-chained, append-only ledger together with the section text as it stood at that moment, so old rows still verify after the author revises. When a section's text changes, its old score is marked stale everywhere. A section reflection is accepted only when that section's latest composite is 2 or below, or exactly 5, and it is pinned to that draft. The Skill never rewrites sentences and never writes the author's sections — sentence-level edits go to red-pen — and it produces no similarity or originality figure of any kind.
