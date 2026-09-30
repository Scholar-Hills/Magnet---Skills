# 刷题私教 · coding-drill

> 参考解实际运行，非解与错解先检查，再把题交给你。

一份给 Claude Code / Codex / OpenClaw 等 Agent 用的 Skill：说一个编程知识点，它出一道标准输入/输出的练习题，参考解和隐藏用例先藏起来；你写完它在本机真跑判题，只揭开第一条没过的用例，告诉你那条抓的是什么误解，并记进你的错题本。老师也能用它出“薅不到分”的题并导出题包。

## 为什么要有它

让 AI 出编程题很容易，让它出的题**判得住**很难。这份 Skill 把参考解实跑、非解基线与错解检查写成 Agent 能执行的步骤，再由零依赖脚本验证。通过这些检查说明题包满足当前闸门，不代表任意投机程序都无法得分：

- 期望输出只许由参考解**实跑**得到，绝不手写、绝不回填修正；
- 打印常量、什么都不打印、原样回显输入、原样提交起步骨架——四个非解**必须全部 0 分**；
- 每条隐藏用例写明它抓的是什么误解，并附 2～3 个错解，**每个错解都必须丢分**；
- 阈值上必须坐着一条计分用例，`>` 和 `>=` 才分得开。

## 安装

[仓库首页](../README.md#快速安装)提供在线安装命令。也可以先从首页下载仓库，或下载本 Skill 的完整文件夹，在该文件夹的上一级目录打开终端，再按提示选择目标 Agent：

```bash
npx skills@latest add ./coding-drill --skill coding-drill
```

需要 Node.js 与 npm。默认安装到当前项目；希望跨项目使用时加 `--global`。这一步安装的是完整 Skill 目录，包括脚本与参考文档。

也可指定客户端：

```bash
npx skills@latest add ./coding-drill --skill coding-drill --agent claude-code
npx skills@latest add ./coding-drill --skill coding-drill --agent codex
```

不使用命令行安装器，或使用 WorkBuddy、小红书下载包时，请看[仓库安装指南](../README.md#手动安装)。复制整个 `coding-drill/` 文件夹，不能只复制 `SKILL.md`。已有同名安装时先备份，避免形成嵌套目录。

下载后手动安装到 Claude Code，也可以直接复制完整目录：

```bash
mkdir -p ~/.claude/skills
cp -R ./coding-drill ~/.claude/skills/
```

WorkBuddy 用户按客户端设置选择技能目录，例如：

```bash
mkdir -p ~/.workbuddy-ai/skills
cp -R ./coding-drill ~/.workbuddy-ai/skills/
```

安装后重开会话，让 Agent 使用 `coding-drill`。选一个固定工作区保存后续产物，第一次使用时让 Agent 先读 `SKILL.md` 并运行其中的环境检查。运行脚本需要 Python 3.8 或更高版本；编程练习按语言另需 Node.js 或 JDK。

## 开始试用

适合学习者练编程，也适合老师准备练习题。说出知识点、语言和难度，得到题面与起步骨架；作答后在本机运行判题，生成判题卡与错题记录。

```text
出题 二分查找 Python 中等
```

[查看完整工作流](SKILL.md) · [浏览示例](examples/) · [反馈问题](../README.md#更新与反馈)

## 用法

```
出题 二分查找 Python 中等      # 出一道题，给你题面、骨架、示例
（改 drills/<slug>/solution.py，不用跟它说话）
判我                           # 本机跑全部用例，只揭开第一条没过的
给点提示                       # 只说方向，不给代码
再来一道 / 难一点
给学生出题 递归 Java 中等 3 道   # 老师模式：完整验证后导出题包 JSON
```

判完会生成 `drills/<slug>/report.html`——一张可以截图的判题卡。错题本在 `drills/misconceptions.md`，下次出题它会先读。

## 目录

```
SKILL.md                      Agent 读的说明
scripts/judge.py              出题验证 / 判题 / 试跑 / 导出 / 环境检查（零依赖）
scripts/selftest.py           脚本自测
references/problem-format.md  题包格式与脚本契约
references/authoring-rules.md 出题纪律全文
examples/                     两道验证过的示例题（Python、JavaScript）
```

## 安全说明

脚本在临时目录里用超时运行程序，但**没有沙箱**，不隔离网络与文件系统。SKILL.md 要求 Agent 只运行本次生成的代码和你自己写的作答文件，且运行前通读一遍。请不要把它当成在线评测系统用。

## 边界

- 给的是出题与判题的**纪律**，不是题库。题由你的 Agent 现出，质量取决于模型；脚本检查既定非解与错解；题目质量与未覆盖的错误仍需复核。
- 只做“完整程序、stdin → stdout”这一种形态；输出只用整数、布尔、单词。
- Python 无第三方库；JavaScript 为 CommonJS 无 npm 包；Java 公开类必须是 `Main`。

## 许可与维护

采用 [MIT 许可](../LICENSE)。由学霸山丘技术团队维护。问题与建议请到 [Issues](../README.md#更新与反馈)。
