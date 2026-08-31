# 按你的评分标准批 · rubric-grader

> 空白卷、把题面贴回来、和题目无关的一段话——这三份必须批出 0 分，否则这一批分数不算数。

一份给 Claude Code / Codex / OpenClaw 等 Agent 用的 Skill：老师给评分标准和一叠简答作答，它先把评分标准整理成条目表请老师确认，再用老师给的满分范例与残缺版做一次校准，校准不过就不许开批；之后逐份批改，每条判定都要引用作答里的原句，一个零依赖的 Python 脚本把引文钉回原文、核分数与条目判定一致、核批注没有一份贴全班，最后出可截图的判题卡和全班汇总。

## 为什么要有它

让模型批作业很容易，让它批得**核得住**很难。三件事最常出问题：给了分却说不出是作答里哪一句撑着；批得越顺手越像同一份评语贴给全班；作答明明是空白或者跑题，还能拿到「结构基本完整」的分。这份 Skill 把这三件事变成机器判定：

- **判定必须有原句撑着。** 判命中或部分命中却给不出引文，拒收；引文钉不回作答原文，这一条自动降为未命中，降完分数变了就整份退回重批。
- **开批前先校准。** 老师给一份满分范例、一份删掉某条内容的残缺版。批不出满分，或者残缺版里被删掉的那条还判成命中，说明这一轮要么太紧要么在无中生有——不盖章就不许开批。
- **对抗基线必须 0 分。** 每批放三份假作答（空白、题面原样贴回、无关段落），批出任何分数都会被脚本拦下。
- **一份评语贴全班拦得住。** 两份结果总评一字不差，或者批语集合重合度 ≥ 0.8，后一份拒收。
- **材料改过，旧结果全部作废。** 评分标准、题干、两份范例、残缺版清单，五份材料任一改动，校准盖章立刻失效，汇总拒绝生成。

## 安装

**Claude Code**

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/<org>/<repo>.git /tmp/rubric-grader-src
cp -R /tmp/rubric-grader-src/rubric-grader ~/.claude/skills/rubric-grader
```

装完的样子是 `~/.claude/skills/rubric-grader/SKILL.md`。只想给某个项目用，就换成该项目下的 `.claude/skills/rubric-grader/`（同样要有 `rubric-grader` 这一层）。重开一个会话，输入 `/skills` 能看到 `rubric-grader` 就是装好了；然后说一句「按我这份评分标准批一下这批简答」。

**WorkBuddy（腾讯）**

```bash
git clone https://github.com/<org>/<repo>.git /tmp/rubric-grader-src
cp -R /tmp/rubric-grader-src/rubric-grader ~/.workbuddy-ai/skills/rubric-grader
```

WorkBuddy AI 5.4 的技能目录是 `~/.workbuddy-ai/skills/`；如果你的数据目录是 `~/.workbuddy/`，就放到 `~/.workbuddy/skills/rubric-grader`。装完在对话框输入 `/skills`，列表里有 `rubric-grader` 即可。

**用之前先选一个固定工作区**（输入框下方「Select Workspace」→ Open Local Folder，选一个专门放批改的文件夹）。不选的话 WorkBuddy 会给每个任务新建一个 `~/WorkBuddy AI/<时间戳>/` 目录，同一批作答会散落在不同目录里，校准盖章和全班汇总就凑不到一块了。

**其他 Agent**（OpenClaw、Codex 等）：把 `rubric-grader` 目录放进各自的技能目录或工作区（OpenClaw 为 `~/.openclaw/workspace/skills/`），让 Agent 先读 `SKILL.md`。

**（从小红书来的读者）** 笔记下方的 RED Skill 组件里可以一键复制安装口令，直接发给你的 Agent 即可，不用手动 clone。

本机只需要 `python3`（3.8+），没有第三方依赖。运行 `python3 scripts/grader.py doctor` 查看。它需要在你机器上运行 `python3` 来核分，第一次会请求授权。

## 用法

跟 Agent 说话就行，下面这些是它替你跑的命令：

```bash
python3 scripts/grader.py init grading/<slug> --max 10      # 建一个题批次
python3 scripts/grader.py rubric set grading/<slug> --from grading/<slug>/inbox/criteria.json
python3 scripts/grader.py oracle check grading/<slug>       # 校准，不过不许开批
python3 scripts/grader.py context grading/<slug> <学号>      # 取上下文包
python3 scripts/grader.py grade grading/<slug> <学号>        # 批一份，跑闸门
python3 scripts/grader.py check grading/<slug>              # 离线复核（出汇总前先跑）
python3 scripts/grader.py summary grading/<slug>            # 全班汇总
python3 scripts/grader.py export grading/<slug>             # 脱敏证据
```

跑完你会拿到：

- `grading/<slug>/results/<学号>.html`——每人一张判题卡，左栏是他自己的作答、批注钉在原句上，右栏按条目列判定与批语，浏览器打开就能截图；
- `grading/<slug>/summary.md` 与 `summary.html`——按条目看谁没命中、按等级看批注、每份的得分与锚定率；
- `grading/<slug>/export.json`（可选）——存档用的脱敏证据，只有哈希、分数、条目判定与锚定率。

`examples/grading/short-answer-01/` 是一个跑完整流程的示例批次（合成题目「解释机会成本并举一例」，三条目共 5 分，两份学生作答 + 三份对抗基线），可以直接 `python3 scripts/grader.py check examples/grading/short-answer-01` 试手。

## 目录

```
SKILL.md                          Agent 读的说明
scripts/grader.py                 建批次 / 条目表 / 上下文 / 校准 / 批改 / 汇总 / 复核 / 导出（零依赖）
scripts/anchor.py                 锚定批注引擎
scripts/selftest.py               脚本自测
scripts/banned_words.py           发布前的静态闸
references/workspace-format.md    目录布局与 JSON 契约
references/rules.md               闸门纪律全文
examples/grading/short-answer-01/ 一个跑完的示例批次
```

## 安全说明

脚本只读写你指定的那个题批次目录，不联网，不调用任何外部服务。它**不执行作答内容**：作答里的 HTML 只做消毒与文本抽取，`docx` 只用标准库解包抽段落文字，没有任何一处会把学生写的东西当代码跑。判题卡与汇总是自包含的单页 HTML，无外链、无脚本。导出的证据只带哈希、分数、条目判定与锚定率，作答原文、引文与评语一个字都不带出去。

## 边界

- 给的是**批改的纪律**，不是评分标准，也不是学科知识。标准是你的，判定由模型给，纪律负责让每条判定有据可查、让白给分批不出来。
- **判题卡右栏「未定位」那一节，脚本不会擅自把批注摆到原文上**——引文没有从作答里原样复制时就会落到这里，请人工看一眼再决定要不要留。
- **批注条数以结果 JSON 为准。** `results/<学号>.json` 里的 `marks` 是真相，判题卡 HTML 只是按它重新渲染出来的一份缓存；要统计、要对账，读 JSON，不要数 HTML 上的标记。
- **老师题干里的排版 class 会被清掉。** 题干与作答进入引擎时会先消毒：脚本、样式、事件属性一律丢弃，`class` 属性一律不保留（它和引擎钉批注用的属性同名，留着就能伪造批注），`span`、`a` 这类内联标签的标签本身也会去掉、文字照留。判题卡上的样式由脚本自己出，从富文本编辑器粘过来的排版不会照搬。
- 支持文本作答（Markdown / 纯文本 / HTML / `docx` 段落文字）；**图片作答不支持**，抽不到文字会直接报错。
- 不带分值的条目表也能用，但脚本能拦的闸门会变少（分数与条目判定的一致性核不了），建议每条都标分值。
- 脚本零依赖，Python 3.8+。

## 许可与维护

MIT。由学霸山丘技术团队维护。问题与建议请提 issue。
