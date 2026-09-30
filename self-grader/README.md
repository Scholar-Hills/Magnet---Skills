# 自批私教 · self-grader

用自己提供的题目和评分标准检查文字答案。先确认评分条目，再用空白、抄题面和无关文字验证基线；三份均为零分后，才批改真实作答。结果包含判题卡、未命中条目和多稿进度记录。

## 自批步骤

- 每条命中判定引用答案原文。无法定位的引文会导致判定降级，影响分数时需要重新提交结果。
- 条目标明分值时，命中得满分、部分命中得一半、未命中得零分，脚本检查总分与条目是否一致。
- 同一稿重批不能直接换分。需要改判时，先说明原判定的问题。
- 进度由脚本追加，`check` 会按评分结果核对记录。

自批分数用于检查答案与所给标准的差距，不作为考试或课程成绩。

## 安装

[仓库首页](../README.md#快速安装)提供在线安装命令。也可以先从首页下载仓库，或下载本 Skill 的完整文件夹，在该文件夹的上一级目录打开终端，再按提示选择目标 Agent：

```bash
npx skills@latest add ./self-grader --skill self-grader
```

需要 Node.js 与 npm。默认安装到当前项目；希望跨项目使用时加 `--global`。这一步安装的是完整 Skill 目录，包括脚本与参考文档。

也可指定客户端：

```bash
npx skills@latest add ./self-grader --skill self-grader --agent claude-code
npx skills@latest add ./self-grader --skill self-grader --agent codex
```

不使用命令行安装器，或使用 WorkBuddy、小红书下载包时，请看[仓库安装指南](../README.md#手动安装)。复制整个 `self-grader/` 文件夹，不能只复制 `SKILL.md`。已有同名安装时先备份，避免形成嵌套目录。

下载后手动安装到 Claude Code，也可以直接复制完整目录：

```bash
mkdir -p ~/.claude/skills
cp -R ./self-grader ~/.claude/skills/
```

WorkBuddy 用户按客户端设置选择技能目录，例如：

```bash
mkdir -p ~/.workbuddy-ai/skills
cp -R ./self-grader ~/.workbuddy-ai/skills/
```

安装后重开会话，让 Agent 使用 `self-grader`。选一个固定工作区保存后续产物，第一次使用时让 Agent 先读 `SKILL.md` 并运行其中的环境检查。运行脚本需要 Python 3.8 或更高版本，无第三方 Python 依赖。

## 开始试用

适合学习者按自带评分标准检查自己的文字答案。先用空白、抄题面与无关文字验证基线，再批真实作答；交付判题卡、未命中条目和多稿进度记录。

```text
用 self-grader 帮我自批这道题，题目和评分标准如下。
```

[查看完整工作流](SKILL.md) · [浏览示例](examples/) · [反馈问题](../README.md#更新与反馈)

## 用法

```
帮我自批这道题            # 贴上题目 + 你自己带来的评分标准
条目表可以                # 确认它整理出来的条目表（建议给每条标分值）
                          # 它接着跑基线：三份假作答各批一遍，全 0 分才盖章
（自己写 practice/<slug>/attempts/01/answer.md，不用跟它说话）
批我                      # 交付判题卡、哪一条没命中、进度记录
给点提示                  # 只说方向，不给答案
（改进后写进 attempts/02/）
我改好了，再批一次        # 批新一稿，并给出两稿之间的走势
看看进度                  # 打印 progress.md 与一句走势
```

批完会生成 `practice/<slug>/attempts/<NN>/result.html`——一张可以截图的判题卡，
左栏是带批注的原文，右栏按条列出等级、引文与批语。进度在 `practice/<slug>/progress.md`。

想把练习记录给别人看，用 `python3 scripts/selfgrade.py export <slug>`：它只带哈希、分数、
条目判定与锚定率，题目、标准、作答、引文、批语一个字都不带出去。

## 目录

```
SKILL.md                            Agent 读的说明
scripts/selfgrade.py                建目录 / 条目表 / 基线 / 上下文 / 批改 / 进度 / 复核 / 导出
scripts/anchor.py                   锚定批注引擎（零依赖）
scripts/selftest.py                 脚本自测
references/workspace-format.md      练习目录布局与 JSON / Markdown 契约
references/rules.md                 闸门纪律全文与每条闸门的理由
examples/practice/opportunity-cost-01/   一个实跑出来的完整练习包（三份基线 + 两稿）
```

## 安全说明

脚本只读写你指定的那一个练习目录，不联网，**也不执行你答案里的任何代码**——它把答案当
文本处理。答案里如果带 HTML，会先经引擎消毒（去掉脚本与事件属性、剥掉伪造的批注标记）
再进判题卡；判题卡是自包含单页 HTML，不引用任何外部资源，可以离线打开。

## 边界

- **自批分数只供自查，不是任何考试或课程的成绩。** 它衡量的是这一稿离你自己带来的
  那份标准还差什么，换一份标准就是另一个数字。
- **评分标准由你自带。** 本 Skill 不内置任何学科的评分细则，也不会凭记忆替你报一份出来——
  记错了比没有更糟，而你没法验证。老师给的、考纲附的、自己总结的都行。
- **批基线的过程可能会被你看到。** 三份假作答是脚本生成的、给标准做校准用的，你不必看；
  但如果你的 Agent 宿主会显示思考过程，这几步的推理仍然会出现在屏幕上——那是校准，
  不是对你答案的评价，看到了不用当真。
- 评分质量取决于模型和你提供的标准。脚本检查基线分数、原文证据和同稿评分是否一致。
- 图片形式的答案不支持，请先转成文字。

## 许可与维护

采用 [MIT 许可](../LICENSE)。由学霸山丘技术团队维护。问题与建议请到 [Issues](../README.md#更新与反馈)。
