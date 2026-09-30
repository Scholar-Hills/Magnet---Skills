# Magnet Skills 对外介绍素材

以下文案介绍现有能力，不宣称已通过正式发布验收。发布前按[贡献指南](../CONTRIBUTING.md#发布验收)核对证据；截图使用仓库合成示例或新生成的合成任务，并标注「合成示例」。

## GitHub 仓库简介

学霸山丘教育 Agent Skills：编程练习、逐句批注、分段评审、备课、按标准批改与自批，附本机校验脚本和可复现示例。

建议 Topics：`agent-skills`、`education`、`coding-practice`、`writing-feedback`、`lesson-planning`、`claude-code`、`codex`。

首页按「快速安装 → 场景选择 → 单项介绍 → 使用边界」组织，参考 [mattpocock/skills](https://github.com/mattpocock/skills) 的入口方式。安装命令依据 [skills CLI 官方文档](https://github.com/vercel-labs/skills)。

## 短介绍

我们把六类教育任务整理成了可安装的 Agent Skills：练编程、看稿子、检查长文论证、备课、按评分标准批改，以及自查自己的答案。

每个 Skill 都带工作流说明、本机校验脚本和示例。出题先验证，批注要对应原文，批改先校准，备课逐步验收。你可以只安装当前需要的一个，让 Agent 按步骤处理，再查看生成的报告。

仓库：https://github.com/Scholar-Hills/Magnet---Skills

维护：学霸山丘技术团队。

## 小红书介绍草稿

### 标题备选

- 给教育任务装一套可复核的 AI 工作流
- AI 出题、批稿、备课：我们把验证步骤做成了 Skills
- 六个教育 Agent Skills，按你的任务挑一个

### 正文

让 AI 出一道题、批一篇稿子或备一节课，拿到一份结果只是开始。我们还希望知道：结果怎么来的，反馈指向哪里，改过之后旧记录是否仍然有效。

学霸山丘技术团队把这些要求整理成了 Magnet Skills，每个 Skill 都附工作流、本机校验脚本与合成示例：

- 刷题私教：按知识点出题，参考解实际运行后再验题，写完代码再判。
- 红笔改稿：逐句指出问题，批注对应原句，给短改法，原稿由你自己改。
- 分段写作教练：按原文拆成卡片，逐段检查子问题与主论点，保留版本记录。
- 备课工作流：默认先出作业，再准备课堂阶段、投屏正文与独立教师讲稿。
- 按标准批改：老师自带评分标准，先校准，再交付个人判题卡与全班汇总。
- 自批私教：按自带标准自查答案，看到未命中条目，改完再交下一稿。

安装后，把题目、稿子或评分标准交给你的 Agent，明确说使用哪一个 Skill。脚本核对既定规则与证据，判断质量仍需要你复核。

开源仓库：https://github.com/Scholar-Hills/Magnet---Skills

署名：学霸山丘技术团队。

### 配图建议

第一张展示「六类任务怎么选」；后续按单个 Skill 展示合成输入、生成的报告与关键验证结果。最后一张给仓库地址和安装方式。每张图只解释一个任务，保留未定位条目与 WARN 的说明。

## 演示与更新节奏

每次介绍一个实际场景：准备合成输入，按 SKILL.md 跑完整流程，展示报告，再解释一条验证规则和一个使用边界。功能改变后先更新 README、完成适用验收，再发布演示。

仓库管理使用 Issues 收集最小复现，PR 记录改动与验证，GitHub Release 描述本次行为变化与验收证据。README 保持安装入口与能力目录，具体使用步骤留在各 Skill README。

正式发布时逐项注明本次通过验收的 Skill 与版本；未验收的其他 Skill 不借用本次结论。宣传数字只引用可核对的实测来源。

## English summary

Magnet Skills provides six educational agent workflows with local validators and synthetic examples. Public demonstrations should show an actual workflow, its generated report, and its limitations. Release claims require documented acceptance checks.
