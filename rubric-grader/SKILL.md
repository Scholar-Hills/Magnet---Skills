---
name: rubric-grader
description: 按你自己的评分标准批一叠简答题——先把评分标准整理成条目表让你确认，再用你给的满分范例与残缺版校准（校准不过不许开批），然后逐份批：每条判定必须引用作答里的原句，脚本把引文钉回原文、核分数与条目一致，最后出判题卡和全班汇总。Use when a teacher wants to grade a batch of short answers or essays against their own rubric, needs per-criterion verdicts backed by quotes from the student's own text, or wants a class-level summary of which rubric items were missed.
license: MIT
allowed-tools: Bash, Read, Write, Edit
---

# 按你的评分标准批（rubric-grader）

一句话：**空白卷、把题面贴回来、和题目无关的一段话，这三种作答必须批出 0 分**，否则这一轮的分数全部不算数。评分标准是老师的，判定由模型给，但每一条判定都要有作答里的原句撑着——引文钉不回原文，这一条就自动降为未命中。

## 你能对它说什么

| 老师说 | 它做 |
|---|---|
| `按我这份评分标准批一下这批简答` | 先把评分标准整理成条目表（条目名 + 分值 + 判据）请老师确认 |
| `满分范例我给你，残缺版你自己删` | 用满分范例与残缺版跑校准；校准不过就停下，不许开批 |
| `开始批` | 逐份：取上下文 → 写评分结果 → 跑闸门 → 出判题卡 |
| `谁没答出定义那一条` | 出全班汇总：按条目看未命中人数、按等级看批注、每份的得分与锚定率 |
| `给我一份能存档的证据` | 导出脱敏证据（只有哈希、分数、条目判定、锚定率，不含正文） |

## 前置检查（不可跳过）

0. **定位脚本**。本 Skill 的脚本在 Skill 目录下，不在老师的工作区。按顺序找 `rubric-grader/scripts/grader.py`，取第一个存在的绝对路径记作 `GRADER`：
   ① 这份 SKILL.md 所在目录下的 `scripts/grader.py`（你就是从那个目录读到本文件的）；② Claude Code：`~/.claude/skills/rubric-grader/`、当前项目 `.claude/skills/rubric-grader/`；③ WorkBuddy / CodeBuddy：`~/.workbuddy/skills/rubric-grader/`、`~/.workbuddy-ai/skills/rubric-grader/`、`~/.codebuddy/skills/rubric-grader/`、当前项目 `.codebuddy/skills/rubric-grader/`；④ OpenClaw：`~/.openclaw/workspace/skills/rubric-grader/`；⑤ 小红书 `redskill install` 的默认位置：当前目录 `./skills/rubric-grader/`；⑥ 老师在对话里指定的目录；⑦ 都没有就搜一次：`find . ~/.claude ~/.workbuddy ~/.workbuddy-ai ~/.codebuddy ~/.openclaw -path '*rubric-grader/scripts/grader.py' 2>/dev/null | head -1`。
   本文后面所有 `python3 scripts/grader.py …` 都读作 `python3 "$GRADER" …`，并且始终在老师的工作区（`grading/` 的父目录）下执行：`cd <工作区> && python3 "$GRADER" grade grading/<slug> <学号>`。
   **七处都找不到就立即停止**，告诉老师「这份 Skill 的判卷脚本缺失，请重新下载完整目录」。**任何情况下都不要自己写一个替代脚本**——手写的校验器没有本 Skill 的校准闸门与引文锚定，会让老师以为这一批分数是核过的。
1. 运行 `python3 "$GRADER" doctor`。`python3` 不存在就试 `python`（Windows 常见）；两个都没有，告诉老师先装 Python 3.8+，不要继续。
2. 题批次都放在**当前工作区**（老师项目的根目录，不是 Skill 目录）的 `grading/` 下。第一次建批次前先 `pwd` 看一眼：如果当前目录是家目录、桌面或其它不像工作区的地方，先问老师一句「这一批的作答、判题卡和汇总我打算放在 `<当前路径>/grading/`，可以吗？想换个地方现在告诉我」。定下来之后就别再换。
3. **回复语言跟随老师**：老师用中文就全程中文，用英文就全程英文，不要中英混着来。作答语言写进 `job.json` 的 `lang`（`zh` / `en`），它决定总评按字还是按词计数。
4. 第一次用之前，看一眼 Skill 目录里 `examples/grading/short-answer-01/` 这个已经跑完的示例批次——条目表怎么写、评分结果 JSON 长什么样、对抗基线怎么放，照着它来比照着文字描述更不容易出错。格式以 `references/workspace-format.md` 为准，纪律以 `references/rules.md` 为准，**开批前先读这两份**。

## 批改流程（按顺序做，不要跳步）

**动手前先说一句**：「我会先把你的评分标准整理成条目表请你确认，再拿一份满分范例和一份删掉某条的残缺版做校准——校准不过我不会开批。之后每份作答我都会引用他自己写的句子来说明每条给没给分，脚本会把引文钉回原文核一遍。」非交互场景（批处理、子任务）就把这句写进最终报告的开头。

### 第 1 步　把评分标准整理成条目表，请老师确认

建批次：

```bash
python3 "$GRADER" init grading/<slug> --max 10
```

`--max` 是这道题的满分；可选 `--lang zh|en`、`--max-notes 12`（每份批注条数上限）、`--min-anchored 0.7`（批注锚定率下限）。

把题干逐字粘进 `grading/<slug>/question.md`，把老师给的评分标准逐字粘进 `rubric.md`——**一个字都不要改写**，脚本不解析它，它是给你和老师看的原文。

然后读一遍评分标准，整理成条目表写进 `grading/<slug>/inbox/criteria.json`：

```json
{"criteria": [{"name": "定义准确", "points": 2},
              {"name": "例子贴切", "points": 2},
              {"name": "表述清楚", "points": 1}]}
```

**把这张表念给老师听，逐条确认，改到他点头为止。** 确认之后再写入：

```bash
python3 "$GRADER" rubric set grading/<slug> --from grading/<slug>/inbox/criteria.json
```

条目要么每条都带分值、加起来等于满分，要么每条都不带（见文末「评分标准怎么写才可批」）。

### 第 2 步　请老师给满分范例与残缺版

- `oracle/full.md`：一份**能拿满分**的范例作答。老师手上没有现成的，就照着评分标准替他起草一份，**说清楚这是草稿、请他改**，改完再落盘。
- `oracle/broken.md`：把满分范例里**某一条对应的内容整段删掉**得到的残缺版。**删哪一条由老师指定**，不要替他决定——他指定的那一条才是他最在意、最怕批漏的。
- `oracle/broken.json`：`{"missing": ["例子贴切"]}`，列出残缺版缺掉的条目名（必须在条目表里）。

### 第 3 步　校准：`oracle check` 不过不许批

对两份范例各跑一次 `context`，照着上下文包写两份评分结果，分别存成 `inbox/grade-oracle-full.json` 与 `inbox/grade-oracle-broken.json`，然后：

```bash
python3 "$GRADER" oracle check grading/<slug>
```

脚本要求：满分范例必须批出满分且条条命中；残缺版在 `broken.json` 列出的条目上必须判未命中或部分命中，且总分低于满分。通过才盖章（`.stamps/oracle.json`，记下 `rubric.md`、`question.md`、`oracle/full.md`、`oracle/broken.md`、`oracle/broken.json` **五份材料的哈希**）。

退出 1 就是没过：**改你写的那两份评分结果，或者请老师改范例——不许开批。** 满分范例批不出满分，通常是你批得太紧或者条目表跟评分标准对不上；残缺版批出命中，说明你在无中生有，这时候整批作答都不能开始。

### 第 4 步　逐份批：`context` → 写 inbox → `grade`

作答放在 `answers/<学号>.md`（也支持 `.txt` / `.html` / `.docx`；图片作答不支持）。**除了老师的学生，还要放三份对抗作答**，文件名以 `base-` 开头：一份空白、一份把题面原样贴回、一份与题目无关的段落。它们必须批出 0 分且条目全部未命中，脚本会强制。

每一份：

```bash
python3 "$GRADER" context grading/<slug> <学号>      # 拿上下文包（含 context_hash）
# —— 照着上下文包批，把评分结果写进 grading/<slug>/inbox/grade-<学号>.json
python3 "$GRADER" grade grading/<slug> <学号>
```

评分结果只有五个顶层键，多一个少一个都会被拒收（逐键说明见 `references/workspace-format.md` §3）：

```json
{
  "context_hash": "刚才 context 输出里的那一串，原样抄",
  "points": 4,
  "summary": "一段 60–200 字的总评（英文按词计）",
  "criteria": [{"name": "定义准确", "verdict": "hit", "quote": "作答里支撑这条判定的原句"}],
  "marks": [{"quote": "作答里的原句", "level": "major", "note": "至少 6 个字的批语"}]
}
```

- `verdict` 只能是 `hit` / `partial` / `miss`；判 `hit` 或 `partial` 必须给引文，`miss` 可以留空。
- `quote` 一律**从作答里原样复制**，不要改标点、不要缩写、不要跨段落拼接。
- `level` 只能是 `major` / `minor` / `remark`。
- 带分值的条目表：`points` 必须等于 `hit` 拿满、`partial` 拿一半向下取整、`miss` 拿 0 的合计，脚本会算。

**如实报告每一份的闸门结果。** `grade` 退出 0 就照它打印的那行说：得分、条目命中情况、批注条数与锚定率；有 WARN 就把 WARN 一起说，不要吞掉。退出 1 就说「第 N 份没过闸门：〈哪一条〉，我改一下评分结果再核一次」，然后**只改 `inbox/grade-<学号>.json`**，改完重跑，不要静默重试。

### 第 5 步　汇总

出汇总或导出之前，**先跑一次离线复核**：

```bash
python3 "$GRADER" check grading/<slug>          # 0 ERROR 才往下走
python3 "$GRADER" summary grading/<slug>
python3 "$GRADER" export grading/<slug>         # 需要存档证据时才跑
```

`check` 会把每份结果重新跑一遍闸门、重新锚定一遍引文，并检查校准盖章还有没有效。有 ERROR 就先修，不要出汇总。

交付时告诉老师：判题卡在 `grading/<slug>/results/<学号>.html`（浏览器打开可直接截图），汇总在 `summary.md` 与 `summary.html`；**判题卡右栏「未定位」那一节里的批注，脚本没有把它摆到原文上，请人工看一眼**——那通常是引文没有原样复制。

## 门禁（必须遵守）

- **没跑 `context` 就不许写评分结果。** `context_hash` 是它算出来的，手编一个会被当场拒收；这道闸挡的正是「凭印象批、批完再补哈希」。
- **`oracle check` 没通过就不许开批。** 没盖章 `grade` 会直接退出 2。也不要为了让校准过关去改残缺版删掉的内容——那是老师定的。
- **`grade` 退出 1 时，改 `inbox/` 里的评分结果，不要改作答。** 学生写的东西是证据，不是可以调整的参数。改作答会让 `context_hash` 变掉，旧结果全部作废。
- **不要手写或手改 `results/` 下的任何文件。** 那里的每一个字段都由脚本落盘：分数、条目判定、每条批注锚没锚上、锚定率。手改过的 `anchored` 与 `anchored_ratio` 会被 `check` 当场对出来。
- **出 `summary` / `export` 之前先跑 `check`，0 ERROR 才往下走。** 汇总和导出只读已通过的结果，读之前不复核，等于把没核过的数字端上桌。
- **改了 `rubric.md`、`question.md` 或 `oracle/` 里任何一份，盖章立刻作废。** 这时要重跑 `oracle check`，再逐份重跑 `grade`；`summary` 会拒绝生成，不要绕过它。
- **不要为了让某一份通过而修改脚本本身。** 闸门是这份 Skill 唯一的价值。
- **不要把评分标准逐条抄进 `note`。** 批注是对这一句话说的话；老师要看标准会自己去看 `rubric.md`。
- **不要一份评语贴全班。** 脚本会比总评是否一字不差、批语集合重合度是否超过 0.8，重了就拒收后一份。

## 评分标准怎么写才可批

老师给的评分标准是散文也没关系，你的任务是把它整理成一张表请老师确认。每一条三样东西：

| 条目名 | 分值 | 一句判据 |
|---|---|---|
| 定义准确 | 2 | 说出机会成本是放弃的选项里价值最高的那一个；只说「放弃的东西」给 1 分 |
| 例子贴切 | 2 | 举了具体例子，并点明这个例子里被放弃的最优选择 |
| 表述清楚 | 1 | 句子通顺、结论明确，通篇同义反复的不给分 |

- **条目名**要短、要互不重叠，一个条目只问一件事。「定义准确」和「例子贴切」是两条；「内容完整」不是一条，它没法判。
- **判据要写成一句可以指着作答说是或不是的话**。判据写不出来，说明这一条还没想清楚，先问老师。判据落进条目表里只是给你自己看的备忘（`criteria.json` 只收 `name` 与 `points` 两个键），真正的原文在 `rubric.md` 里逐字保存着。
- **建议标分值**：每条都标、加起来等于满分，脚本就能核「分数与条目判定一致」这条硬闸。**不标分值时脚本能拦的只剩两条**：引文锚不回原文（该条降为未命中），以及对抗作答给了分（条目全未命中却拿到分）。中间那些「条目都判了部分命中，分数却给满」的错法，不标分值就拦不住。
- 满分是 `--max` 定的，条目分值合计必须与它相等，对不上 `rubric set` 会退出 1 并保留旧表。

## 安全约束

- 脚本**只读写你指定的那个题批次目录**，不联网、不调用任何外部服务，也不读工作区以外的文件。
- 脚本**不执行作答内容**：作答里的 HTML 只做消毒与文本抽取，不渲染脚本、不发请求；`docx` 只用标准库解包抽段落文字。这里没有沙箱，但也没有任何一处会把学生写的东西当代码跑。
- 判题卡与汇总是自包含的单页 HTML，无外链、无脚本，可以直接发给老师或截图。
- 导出的证据只带哈希、分数、条目判定与锚定率，作答原文、引文与评语一个字都不带出去。

## 边界与承诺

- 这份 Skill 给的是**批改的纪律**，不是评分标准，也不是学科知识：标准是老师的，判定由模型给，纪律负责让每条判定有据可查、让白给分批不出来。
- 支持文本作答（Markdown / 纯文本 / HTML / `docx` 段落文字）。**图片作答不支持**，脚本抽不到文字会直接报错，请老师先转成文字。
- 脚本零依赖，Python 3.8+。

## 文件

- `scripts/grader.py`——建批次（`init`）、条目表（`rubric set`）、上下文包（`context`）、校准（`oracle check`）、批一份（`grade`）、汇总（`summary`）、离线复核（`check`）、脱敏导出（`export`）、环境检查（`doctor`）
- `scripts/anchor.py`——锚定批注引擎（抽文本、把引文钉回原文、渲染判题卡）
- `scripts/selftest.py`——脚本自测；`scripts/banned_words.py`——发布前的静态闸
- `references/workspace-format.md`——目录布局、`job.json`、评分结果 JSON、盖章与导出的逐键契约
- `references/rules.md`——闸门纪律全文
- `examples/grading/short-answer-01/`——一个跑完的示例批次（三条目、5 分、两份学生作答 + 三份对抗基线）

---

English summary: rubric-grader grades a batch of short answers against the teacher's own rubric. Step one turns the rubric into a criteria table the teacher signs off on. Step two calibrates: the teacher supplies a full-credit exemplar and a version with one criterion's content deleted, and the model must score the exemplar full marks on every criterion and must mark the deleted criterion as missed — otherwise `oracle check` refuses to stamp and grading cannot start. Each grade payload names a verdict per criterion plus a quote from the student's own text; `scripts/grader.py` re-anchors every quote into the original answer, downgrades unanchorable evidence to a miss, checks the total against the per-criterion weights, caps annotations and requires a 0.7 anchoring ratio, and rejects one set of comments pasted across the class. Three adversarial answers (blank, question echoed back, unrelated prose) must score zero. Output is a self-contained HTML card per student plus a class summary; `export` emits hashes and verdicts only, never text.
