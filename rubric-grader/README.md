# 按标准批改 · rubric-grader

老师提供评分标准和一批简答，Agent 整理条目表供老师确认，再用满分范例与残缺版校准。通过后逐份批改，生成个人判题卡和全班汇总。评分标准由老师提供。

## 评分检查

- 命中或部分命中的判定需引用作答原句。引文无法定位时，该条降为未命中；影响总分时需要重新提交结果。
- 满分范例与残缺版通过校准后才能开始批改。
- 每批包含空白、抄题面和无关文字三份基线，均需批为零分。
- 不同作答的总评完全相同，或批语集合重合度达到 0.8，后一份结果会被拒收。
- 评分标准、题干或校准材料修改后，需要重新校准和批改。

脚本核对引文、分值和材料版本，评分是否合理仍需老师复核。

## 安装

[仓库首页](../README.md#快速安装)提供在线安装命令。也可以先从首页下载仓库，或下载本 Skill 的完整文件夹，在该文件夹的上一级目录打开终端，再按提示选择目标 Agent：

```bash
npx skills@latest add ./rubric-grader --skill rubric-grader
```

需要 Node.js 与 npm。默认安装到当前项目；希望跨项目使用时加 `--global`。这一步安装的是完整 Skill 目录，包括脚本与参考文档。

也可指定客户端：

```bash
npx skills@latest add ./rubric-grader --skill rubric-grader --agent claude-code
npx skills@latest add ./rubric-grader --skill rubric-grader --agent codex
```

不使用命令行安装器，或使用 WorkBuddy、小红书下载包时，请看[仓库安装指南](../README.md#手动安装)。复制整个 `rubric-grader/` 文件夹，不能只复制 `SKILL.md`。已有同名安装时先备份，避免形成嵌套目录。

下载后手动安装到 Claude Code，也可以直接复制完整目录：

```bash
mkdir -p ~/.claude/skills
cp -R ./rubric-grader ~/.claude/skills/
```

WorkBuddy 用户按客户端设置选择技能目录，例如：

```bash
mkdir -p ~/.workbuddy-ai/skills
cp -R ./rubric-grader ~/.workbuddy-ai/skills/
```

安装后重开会话，让 Agent 使用 `rubric-grader`。选一个固定工作区保存后续产物，第一次使用时让 Agent 先读 `SKILL.md` 并运行其中的环境检查。运行脚本需要 Python 3.8 或更高版本，无第三方 Python 依赖。

## 开始试用

适合老师按自己提供的评分标准批改一批简答。先确认条目表，再用满分范例与残缺版校准；每条判定引用作答原文，交付个人判题卡与全班汇总。

```text
用 rubric-grader 按我提供的评分标准批改这批简答，先确认条目表。
```

[查看完整工作流](SKILL.md) · [浏览示例](examples/) · [反馈问题](../README.md#更新与反馈)

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

`examples/grading/short-answer-01/` 是一个跑完整流程的示例批次（合成题目解释机会成本并举一例，三条目共 5 分，两份学生作答 + 三份对抗基线），可以直接 `python3 scripts/grader.py check examples/grading/short-answer-01` 试手。

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

- 评分标准由你提供，判定由模型给出，脚本核对原文证据与分值。
- **判题卡右栏未定位那一节，脚本不会擅自把批注摆到原文上**——引文没有从作答里原样复制时就会落到这里，请人工看一眼再决定要不要留。
- **批注条数以结果 JSON 为准。** `results/<学号>.json` 里的 `marks` 是真相，判题卡 HTML 只是按它重新渲染出来的一份缓存；要统计、要对账，读 JSON，不要数 HTML 上的标记。
- **老师题干里的排版 class 会被清掉。** 题干与作答进入引擎时会先消毒：脚本、样式、事件属性一律丢弃，`class` 属性一律不保留（它和引擎钉批注用的属性同名，留着就能伪造批注），`span`、`a` 这类内联标签的标签本身也会去掉、文字照留。判题卡上的样式由脚本自己出，从富文本编辑器粘过来的排版不会照搬。
- 支持文本作答（Markdown / 纯文本 / HTML / `docx` 段落文字）；**图片作答不支持**，抽不到文字会直接报错。
- 不带分值的条目表也能用，但脚本能拦的闸门会变少（分数与条目判定的一致性核不了），建议每条都标分值。
- 脚本零依赖，Python 3.8+。

## 许可与维护

采用 [MIT 许可](../LICENSE)。由学霸山丘技术团队维护。问题与建议请到 [Issues](../README.md#更新与反馈)。
