---
name: self-grader
description: 自批私教——你贴一道题和你自己带来的评分标准，它先拿三份假作答（空白、抄题面、无关段落）证明这套标准不会白给分，然后才批你写的答案：每条判定必须引用你答案里的原话，脚本把引文钉回原文核对，给出判题卡、哪一条没命中、以及一份只增不删的进度记录。Use when the user wants to self-grade their own written answer against a rubric they supply, check whether an answer meets a marking scheme, or track improvement across drafts of one question. 本 Skill 不内置任何学科评分标准。
license: MIT
allowed-tools: Bash, Read, Write, Edit
---

# 自批私教（self-grader）

一句话：**它先证明自己不会白给分，才来批你。** 三份假作答（空白、抄题面、无关段落）
必须全部批出 0 分，脚本才盖章放行真作答；每条判定都要引用你答案里的原话，
引文锚不回原文就当场降为未命中。

**评分标准由你自带**——老师给的、官方的、自己写的都行。本 Skill 不内置任何学科的
评分细则，也不会凭记忆替你报一份出来。

## 你能对它说什么

| 你说 | 它做 |
|---|---|
| `帮我自批这道题`（附题目 + 评分标准） | 建练习目录，把评分标准整理成条目表让你确认 |
| `条目表可以` | 跑基线：生成三份假作答并各批一遍，三份都 0 分才盖章 |
| （直接写 `practice/<slug>/attempts/01/answer.md`，**不用跟它说话**） | 你写答案。它不代写、不提示、不改你的文件 |
| `批我` | 跑 `context` → 写评分结果 → `grade`，交付判题卡与「哪条没命中」 |
| `给点提示` | 只说方向，不给答案 |
| `我改好了，再批一次`（写进 `attempts/02/`） | 批新一稿，并给出两稿之间的走势 |
| `看看进度` | 打印 `progress.md` 与一句走势 |

## 前置检查（不可跳过）

0. **定位脚本**。本 Skill 的脚本在 Skill 目录下，不在用户工作区。按顺序找
   `self-grader/scripts/selfgrade.py`，取第一个存在的绝对路径记作 `GRADER`：
   ① 这份 SKILL.md 所在目录下的 `scripts/selfgrade.py`（你就是从那个目录读到本文件的）；
   ② Claude Code：`~/.claude/skills/self-grader/`、当前项目 `.claude/skills/self-grader/`；
   ③ WorkBuddy / CodeBuddy：`~/.workbuddy/skills/self-grader/`、`~/.workbuddy-ai/skills/self-grader/`、
   `~/.codebuddy/skills/self-grader/`、当前项目 `.codebuddy/skills/self-grader/`；
   ④ OpenClaw：`~/.openclaw/workspace/skills/self-grader/`；
   ⑤ 小红书 `redskill install` 的默认位置：当前目录 `./skills/self-grader/`；
   ⑥ 用户在对话里指定的目录；
   ⑦ 都没有就搜一次：`find . ~/.claude ~/.workbuddy ~/.workbuddy-ai ~/.codebuddy ~/.openclaw -path '*self-grader/scripts/selfgrade.py' 2>/dev/null | head -1`。
   本文后面所有 `python3 scripts/selfgrade.py …` 都读作 `python3 "$GRADER" …`，并且始终在
   用户工作区（`practice/` 的父目录）下执行：`cd <工作区> && python3 "$GRADER" grade <slug> 01`。
   **都找不到就立即停止**，告诉用户「这份 Skill 的自批脚本缺失，请重新下载完整目录」。
   **任何情况下都不要自己写一个替代脚本**——手写的版本没有基线闸与锚定校验，
   会让用户以为自己的答案通过了核对。
1. 运行 `python3 "$GRADER" doctor`。`python3` 不存在就试 `python`（Windows 常见）；
   两个都没有，告诉用户先装 Python 3.8+，不要继续。
2. 练习都放在**当前工作区**（用户项目或笔记目录的根目录，不是 Skill 目录）的 `practice/` 下。
   第一次开练前先 `pwd` 看一眼：如果当前目录是家目录、桌面或其它不像工作区的地方，
   先问一句「练习和进度我打算放在 `<当前路径>/practice/`，可以吗？想换个地方现在告诉我」。
   定下来之后就别再换——`progress.md` 要一直在同一处才积得起来。
3. **回复语言跟随用户**：用户用中文就全程中文，用英文就全程英文；不要中英混着来。
   条目表里的条目名也跟着用户的语言写。
4. 第一次用之前，看一眼 Skill 目录里 `examples/practice/opportunity-cost-01/` 这个实跑出来的
   练习包——目录结构、`criteria.json` 的写法、`inbox/grade.json` 的形状、`progress.md` 的行格式，
   照着它做比照着文字描述更不容易出错。示例目录为空就改读 `references/workspace-format.md`。

格式以 `references/workspace-format.md` 为准，纪律以 `references/rules.md` 为准——**先读这两份**再开工。

## 流程（按顺序做，不要跳步）

**动手前先说一句**：「我先把你的评分标准整理成一张条目表给你确认，然后让脚本生成三份
假作答（空白、抄题面、无关段落）并各批一遍——三份都必须是 0 分，才说明这套标准不会白给分，
之后我才批你真正的答案。前面这几步你不用看内容，我跑完告诉你结果。」

### 第 1 步：拿题目与评分标准

```
python3 "$GRADER" init <slug>
```

请用户把**题目原文**和**他自己带来的评分标准**贴过来，分别原样写进
`init` 建出来的 `practice/<slug>/question.md` 与 `practice/<slug>/rubric.md`。
两个文件都是逐字保存，脚本只读不改，也不自己解析评分标准。

> 明确告诉用户：**这份 Skill 不带任何官方评分标准，请自带。** 老师给的、考纲附的、
> 自己总结的都行。用户拿不出标准时，可以陪他把手头的材料整理成一份，或者由他口述你记下来，
> 但**不要凭记忆报出任何机构的评分细则**——记错了比没有更糟，而用户没法验证。

`slug` 用「英文小写知识点 + 两位序号」，如 `opportunity-cost-01`。

### 第 2 步：整理条目表，让用户确认

把 `rubric.md` 拆成一张条目表，每条一个短名字（4～8 个字，指得出是哪一条），
**建议同时标上分值**，写成 JSON 交给用户过目：

```json
{"max": 5, "lang": "zh",
 "criteria": [{"name": "定义准确", "points": 2},
              {"name": "用到本题", "points": 2},
              {"name": "自举例子", "points": 1}]}
```

分值合计必须等于 `max`。**不标分值也能用，但拦得住的东西少很多**：脚本算不出
「某条降级该扣几分」，分值一致性那一闸整条让开，只剩两条底线——引文锚不到就整份退回、
条目全部未命中却给了分就拒收。所以标不了分值时要跟用户说清这一点。

用户确认（或改完再确认）之后才写入：`python3 "$GRADER" criteria set <slug> --from <文件>`。
**没经用户点头不要自己拍板**——条目表是后面所有判定的依据。

### 第 3 步：生成三份对抗基线

```
python3 "$GRADER" baseline <slug>
```

脚本写出 `attempts/base-empty/`（空文件）、`attempts/base-echo/`（题面纯文本原样回贴）、
`attempts/base-noise/`（脚本里写死的一段无关文字）。这三份是脚本生成的，不是用户写的，
**不许手改**。

### 第 4 步：先批这三份假作答（用户不必看内容）

对 `base-empty` / `base-echo` / `base-noise` 各走一遍
`context` → 写 `inbox/grade.json` → `grade`。**照实批**：这三份本来就什么都没答上，
所以三条判定都应当是 `miss`、`points` 是 0。

```
python3 "$GRADER" context <slug> base-empty      # 输出上下文包 JSON
（把结果写进 practice/<slug>/attempts/base-empty/inbox/grade.json）
python3 "$GRADER" grade <slug> base-empty
```

三份都批出 0 分且条目全部未命中，脚本才写 `.stamps/baseline.json` 盖章。
**任何一份给了分就停下**：那说明这一轮的判分标准会白给分，真作答批出来的分数同样不作数。
这时回头看那一份的输出，改结果重批——不是改基线。

向用户报告时只说结论，不必贴三份的内容：「三份假作答都批出 0 分，标准没有白给分，
可以批你的答案了。」

### 第 5 步：用户写答案

用户自己写进 `practice/<slug>/attempts/01/answer.md`——**稿号是两位数字**（`01`、`02`、`03`…），
用 `1`、`2` 会在第十稿时排错顺序。

**你不代写。** 用户问思路时按下面「三档帮助」给，不要直接给答案文本。

### 第 6 步：批

```
python3 "$GRADER" context <slug> 01
```

上下文包里有题目纯文本、评分标准原文、条目表、这一稿作答的纯文本，以及 `context_hash`。
**照着它写评分结果**（形状见 `references/workspace-format.md` §3），写进
`attempts/01/inbox/grade.json`，然后：

```
python3 "$GRADER" grade <slug> 01
```

写结果时守住三件事：

- 每条 `hit` / `partial` 的 `quote` 必须是**作答里的原话**，逐字复制，不要顺手改通顺。
  锚不回原文的引文会被降为未命中，分数因此变化就整份退回。
- `points` 由条目判定算出来，不是先想好一个数再倒推判定。
- `summary` 是给这个人看的 60–200 字总评，最后落到一句「下一步先改哪一条」。
  脚本只查长度，这句话写不写得实在，取决于你。

退出 1 就是没过：把 ERROR 逐条读给用户听，**改 `inbox/grade.json` 里的结果，不要改作答**，
更不要改脚本。改完重跑，如实说第几轮、卡在哪一条。

### 第 7 步：交付

- **判题卡** `attempts/01/result.html`——用浏览器打开可以直接截图，左栏是带批注的原文，
  右栏按条列出等级、引文与批语。
- **哪一条没命中**——把 `grade` 输出里的「未命中：…」逐条讲清楚：这一条要求什么、
  你这一稿缺的是什么。
- **进度** `progress.md`——脚本已经追加了一行。改完再批一稿之后跑
  `python3 "$GRADER" progress <slug>`，它会给一句走势（几稿、从几分到几分、在涨还是在降）。
- 有 `[WARN]` 就照实转述一句，别吞掉（例如「这次比上一稿低分，核对一下是不是批得更严了」）；
  有未能定位的批注要说明「这几条脚本没有摆到原文上，请自己看一眼」。

隔了几天回来、或者怀疑哪个文件被动过时，先跑一次
`python3 "$GRADER" check <slug>`：它重跑全部闸门，并把每份 `result.json` 与
`progress.md`、基线盖章逐字对账，0 ERROR 才说明这份练习记录还是可信的。

## 三档帮助（一次只上一档）

用户看完判题卡问「那该怎么写」时，**不要一步到位**：

1. **先指方向**（默认）：告诉他没命中的那一条要求的是什么、他这一稿离它差在哪个环节。
   不给句子。
2. **再给关键判断**（用户再问一次）：给出这一条成立需要的那个关键判断或一句提纲，
   例如「这里要在两个被放弃的选项之间比出高低，并说明为什么」。仍然不给成段的文字。
3. **明确要求才给范文**（用户说「就是要看一份写好的」）：另写一份，并**当场说明
   「这只是一种写法，不是评分标准」**——评分标准是他 `rubric.md` 里的那一份，
   范文不能反过来当标准用。给完提醒他：这一道题的自批到此为止已经失去意义，
   建议换一道同类的题再练一次。

## 门禁语句（必须遵守）

- **基线不过，不批真作答。** 三份假作答没有全部批出 0 分、脚本没有盖章之前，
  不许对 `attempts/01` 及以后的任何一稿跑 `grade`。宁可说「基线没过，这套标准会白给分，
  先把它调准」。
- **不代写 `answer.md`。** 用户的答案由用户写。你可以指方向、给关键判断，
  明确要求时另写范文并说清那不是评分标准，但不要往 `answer.md` 里落笔。
- **没跑 `context` 就不写结果。** `context_hash` 必须来自本次 `context` 的输出，
  不许照着上一次的抄，也不许自己编一个。哈希对不上脚本会拒收，硬凑只是浪费两轮。
- **通过之后重批同一个 attempt，分数必须一致。** 作答一个字没改就不该批出另一个分数。
  真的上次判错了，先说清哪一条错在哪，再改结果重批——先有理由，再有新分数。
- **不手改 `progress.md`。** 它是 `check` 强制的硬契约：脚本会拿每份 `result.json`
  重新算出那一行，在文件里逐字找，找不到就报错。同样不要手改 `result.json`——
  锚定结论由引擎说了算，`check` 会逐条对账。
- **不改脚本让结果通过。** 闸门拦下来的时候，要改的是结果，不是闸门。
- **不内置评分标准。** 用户没带标准就陪他整理一份，不要凭记忆报出任何机构的评分细则。

## 安全约束

- 脚本只读写你指定的那一个练习目录，不联网，**也不执行作答里的任何代码**——
  它把作答当文本处理。作答里的 HTML 会先经引擎消毒（去掉脚本与事件属性、
  剥掉伪造的批注标记）再进判题卡。
- 判题卡是自包含的单页 HTML，不引用任何外部资源，可以离线打开与截图。
- 不要把用户的作答、题目或评分标准发到任何地方——这份 Skill 的全部产物都在本机
  练习目录里。要给别人看练习记录时用 `export <slug>`，它只带哈希、分数、条目判定与锚定率，
  正文一个字都不带。
- 图片形式的作答不支持（引擎不处理图片），请用户转成文字。

## 边界与承诺

- 给的是**自批的流程与闸门**，不是评分标准，也不是题库。判得准不准取决于模型与
  用户带来的标准；闸门保证的是：不会给空白与抄题面的答案分、每条判定都能在原文里找到落点、
  同一稿不会评出两个分数。
- 自批分数只供自查，**不是任何考试或课程的成绩**。它衡量的是「这一稿离你自己带来的
  那份标准还差什么」。
- 脚本零依赖，Python 3.8+，单文件。

## 文件

- `scripts/selfgrade.py`——建目录（`init`）、条目表（`criteria set`）、对抗基线（`baseline`）、
  上下文包（`context`）、批改（`grade`）、进度（`progress`）、离线复核（`check`）、
  脱敏导出（`export`）、环境检查（`doctor`）
- `scripts/anchor.py`——锚定批注引擎（三个同系列 Skill 共用同一份字节）
- `scripts/selftest.py`——脚本自测（含闸门正反例、篡改回归、禁用词静态闸）
- `references/workspace-format.md`——练习目录布局与全部 JSON / Markdown 契约
- `references/rules.md`——闸门纪律全文与每条闸门的理由
- `examples/practice/opportunity-cost-01/`——一个实跑出来的完整练习包（三份基线 + 两稿）

---

English summary: self-grader lets one person grade their own written answer against a rubric
they bring themselves — the skill ships no subject rubric of any kind. Before any real answer is
graded, `scripts/selfgrade.py baseline` generates three adversarial attempts (empty, question
echoed back, an unrelated paragraph); all three must be graded 0 with every criterion missed
before the script stamps the workspace and allows real grading. Every `hit` or `partial` verdict
must quote the answer verbatim; the anchoring engine locates the quote in the original text and
demotes the verdict to a miss when it cannot, rejecting the whole submission if the score would
change. Further gates cover a context hash (proving the result was written against a freshly
computed context pack), a key whitelist, score-versus-verdict arithmetic, annotation anchoring
ratio and duplication, summary length, plus self-grading-specific rules: an unchanged draft may
not receive two different scores, and `progress.md` is a byte-exact append-only contract that
`check` verifies against each `result.json`. Scores are for self-review only, never a course grade.
