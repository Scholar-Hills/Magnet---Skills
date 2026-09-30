# Magnet Skills｜学霸山丘教育工作流

**把出题、批改、写作反馈与备课，变成有步骤、有证据、能复核的 Agent 工作流。**

由学霸山丘技术团队维护。每个 Skill 都包含工作流说明、本机校验脚本、格式契约与示例。你提供知识点、稿子或评分标准，Agent 按步骤处理，脚本检查结果，再交付可查看的报告。

[快速安装](#快速安装) · [选择一个-skill](#选择一个-skill) · [手动安装](#手动安装) · [贡献指南](CONTRIBUTING.md) · [问题反馈](https://github.com/Scholar-Hills/Magnet---Skills/issues)

## 快速安装

在终端运行，按提示选择 Skill 和目标 Agent：

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills
```

只装一个，先从你的实际任务开始：

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills --skill red-pen
```

默认安装到当前项目；加 `--global` 可跨项目使用。安装器需要 Node.js 与 npm；Skill 脚本需要 Python 3.8 或更高版本。支持的客户端与安装选项见 [skills CLI 官方说明](https://github.com/vercel-labs/skills#install-a-skill)。

先浏览列表，再决定装哪些：

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills --list
```

安装后重开 Agent 会话，选一个固定工作区，再说「使用 red-pen 帮我看看这篇稿子」。不同客户端的调用入口可能不同，也可以直接要求 Agent 读取已安装 Skill 的 `SKILL.md`。首次使用先按文档运行环境检查。

## 选择一个 Skill

| 你想做什么 | Skill | 你会拿到什么 |
| --- | --- | --- |
| 按知识点练编程，写完再判 | [刷题私教 · coding-drill](coding-drill/) | 练习题、起步骨架、判题卡与错题记录 |
| 看清稿子哪一句有问题 | [红笔改稿 · red-pen](red-pen/) | 对应原句的批注、短改法与红笔页 |
| 检查长文每段的论证 | [分段写作教练 · essay-sections](essay-sections/) | 分段卡、逐段评审与版本记录 |
| 围绕学习目标准备一节课 | [备课工作流 · lesson-prep](lesson-prep/) | 作业、投屏课件、教师讲稿与验收报告 |
| 按自己的评分标准批一批简答 | [按标准批改 · rubric-grader](rubric-grader/) | 校准记录、个人判题卡与全班汇总 |
| 自查答案离评分标准还差什么 | [自批私教 · self-grader](self-grader/) | 未命中条目、判题卡与多稿进度 |

### 刷题私教 · coding-drill

说出知识点、语言和难度，让 Agent 出一道标准输入输出练习题。期望输出由参考解实际运行生成；出题时检查既定非解基线与错解，作答后本机判题，默认只揭开第一条失败的隐藏用例。支持 Python、JavaScript 与 Java。

**试一句：**「出题 二分查找 Python 中等」。

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills --skill coding-drill
```

[用法与边界](coding-drill/README.md) · [示例题包](coding-drill/examples/drills/)

### 红笔改稿 · red-pen

交一篇邮件、周报、推文或说明文档，先明确给谁看、希望达到什么，再逐句批注。脚本把引文定位到原文，未能定位的条目单列。提供针对原句的短改法，原稿由你自己改；下一版可对照旧引文的变化。

**试一句：**「用 red-pen 看看这篇稿子，给同行看，希望他们愿意试用」。

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills --skill red-pen
```

[用法与边界](red-pen/README.md) · [示例红笔稿](red-pen/examples/drafts/newsletter-01/)

### 分段写作教练 · essay-sections

把已有长文按原文拆成分段卡，逐段看语言、有没有回答子问题、有没有推进主论点。评审引用该段原文，修改后旧评审会标记过期。也可以从题目拆子问题开始，正文由你自己写。

**试一句：**「用 essay-sections 帮我看看每段有没有回答自己的问题」。

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills --skill essay-sections
```

[用法与边界](essay-sections/README.md) · [示例分段卡](essay-sections/examples/essays/remote-work-cities-01/)

### 备课工作流 · lesson-prep

从课题、课时和学习目标开始，默认按「出作业 → 规划阶段 → 逐页写正文与讲稿 → 生成成品」推进。每步经脚本检查，投屏课件与教师讲稿分开交付，报告列出题目与页面的覆盖关系。覆盖检查不替代老师判断教学质量。

**试一句：**「用 lesson-prep 备一节城市湿地保护课，４５分钟，先确认学习目标」。

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills --skill lesson-prep
```

[用法与边界](lesson-prep/README.md) · [示例课件与讲稿](lesson-prep/examples/lessons/city-wetland/)

### 按标准批改 · rubric-grader

老师提供评分标准与一批简答，先确认条目表，再用满分范例与残缺版校准。每条命中判定引用作答原文，脚本核对证据与分值，交付个人判题卡和全班汇总。评分标准由老师提供，判定仍需老师复核。

**试一句：**「用 rubric-grader 按我的标准批这批简答，先确认条目表」。

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills --skill rubric-grader
```

[用法与边界](rubric-grader/README.md) · [示例批次](rubric-grader/examples/grading/short-answer-01/)

### 自批私教 · self-grader

带上题目与自己的评分标准，先用空白、抄题面和无关文字做基线检查，再批真实答案。每条判定附原文证据，改完可交下一稿，记录未命中条目与进度。自批分数用于自查，不是考试或课程成绩。

**试一句：**「用 self-grader 帮我自批这道题，题目和评分标准如下」。

```bash
npx skills@latest add Scholar-Hills/Magnet---Skills --skill self-grader
```

[用法与边界](self-grader/README.md) · [示例练习与两稿记录](self-grader/examples/practice/opportunity-cost-01/)

## 为什么采用这些工作流

教育任务常需要回答三个问题：结果怎么来的、证据在哪、改过之后是否还有效。这里把这些要求写进步骤，再交给脚本检查。

- **先验证，再交付。** 出题先跑参考解与非解检查；批改先校准或验证基线；备课逐步验收。
- **反馈指向原文。** 批注与判定带引文，脚本核对位置；定位失败会明确报告。
- **保留修改记录。** 按各 Skill 的契约记录版本、哈希、评审或进度，支持复核。
- **各 Skill 可独立安装。** 每个顶层目录都是完整安装单元，不需要下载全部技能。

脚本检查的是既定规则，不能证明模型理解正确或教学有效。这里提供工作流与校验机制，不提供学科评分标准、题库或课程知识库。

## 手动安装

不使用命令行安装器时，可以下载仓库 ZIP 并解压，或克隆仓库：

```bash
git clone https://github.com/Scholar-Hills/Magnet---Skills.git
cd Magnet---Skills
```

例如安装红笔改稿到 Claude Code：

```bash
mkdir -p ~/.claude/skills
cp -R red-pen ~/.claude/skills/
```

完成后应有 `~/.claude/skills/red-pen/SKILL.md`、`scripts/`、`references/` 与 `examples/`。安装其他 Skill 时，把 `red-pen` 换成对应目录名。目标已有同名目录时先备份，避免覆盖或套出第二层目录。

Claude Code 的项目安装目录为 `.claude/skills/`。Codex 建议使用上方安装器并加 `--agent codex`，由安装器选择路径。WorkBuddy 可按当前客户端的技能目录设置复制；常见目录为 `~/.workbuddy-ai/skills/` 或 `~/.workbuddy/skills/`。其他客户端以其当前文档为准。

从小红书下载 Skill 文件夹时，同样复制完整目录；下载包必须包含脚本和参考文档。安装成功后，再按 Skill 文档运行环境检查。

## 更新与反馈

通过 skills CLI 安装的副本可运行：

```bash
npx skills@latest update
```

此命令可能更新其他已安装技能，请核对交互提示。手动安装的副本先备份本地修改，再重新下载并复制对应目录。练习、稿子与课程产物放在独立工作区，便于持续积累。

发现问题请提交 [Issue](https://github.com/Scholar-Hills/Magnet---Skills/issues)，说明 Skill、客户端、模型、复现步骤与完整报错。公开反馈只使用合成材料。想贡献改进，请先看[贡献指南](CONTRIBUTING.md)。

## 验证与使用边界

每个 Skill 都有 `scripts/selftest.py` 与示例，供维护者在本机复核。**可安装不等于已通过发布验收。** 正式发布需要同时通过脚本自测、示例验证与至少两个非 Codex 模型的实测；详细要求见[贡献指南](CONTRIBUTING.md#发布验收)。本首页不宣称六个 Skill 已全部通过跨模型验收。本次检查结果与 WARN 说明见[验证记录](docs/VALIDATION.md)。

多数文本处理脚本不联网，报告可在本机查看；Agent 使用模型时的联网与数据处理方式由宿主平台决定。`coding-drill` 会执行代码，具备超时与静态检查，但没有隔离网络和文件系统的沙箱，使用前需阅读其安全说明。

## 许可

采用 [MIT 许可](LICENSE)。维护与署名：**学霸山丘技术团队**。

## English summary

Magnet Skills is a collection of six educational agent workflows for coding practice, editorial feedback, section-level writing review, lesson preparation, rubric-based grading, and self-grading. Each skill includes instructions, local validation scripts, format references, and examples. Install only the skills you need. Validation checks workflow rules and evidence consistency; it does not guarantee educational quality or grading accuracy.
