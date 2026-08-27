# 刷题私教 · coding-drill

> 它出的题，交一个 `print(42)` 拿不到分。

一份给 Claude Code / Codex / OpenClaw 等 Agent 用的 Skill：说一个编程知识点，它出一道标准输入/输出的练习题，参考解和隐藏用例先藏起来；你写完它在本机真跑判题，只揭开第一条没过的用例，告诉你那条抓的是什么误解，并记进你的错题本。老师也能用它出“薅不到分”的题并导出题包。

## 为什么要有它

让 AI 出编程题很容易，让它出的题**判得住**很难。我们拿自己早期批量生成的一批练习题做过实测（数百道，stdin → stdout 形态）：在**没有这套纪律**的情况下，一个只打印常量、根本不读输入的程序平均能拿 **48.8%** 的分；按这套规则重出之后，常量拿 0 分——但“把输入原样打印一个 token”仍能在 **11.2%** 的题上得分，直到补上“至少一条隐藏用例的答案不在输入里”这条规则才归零。问题从来不在模型，在于没人替出题过程设闸门。这份 Skill 把这些闸门写成了 Agent 能执行的步骤，并用一个零依赖脚本机器验证：

- 期望输出只许由参考解**实跑**得到，绝不手写、绝不回填修正；
- 打印常量、什么都不打印、原样回显输入、原样提交起步骨架——四个非解**必须全部 0 分**；
- 每条隐藏用例写明它抓的是什么误解，并附 2～3 个错解，**每个错解都必须丢分**；
- 阈值上必须坐着一条计分用例，`>` 和 `>=` 才分得开。

## 安装

**Claude Code**

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/<org>/<repo>.git /tmp/coding-drill-src
cp -R /tmp/coding-drill-src/coding-drill ~/.claude/skills/coding-drill
```

装完的样子是 `~/.claude/skills/coding-drill/SKILL.md`。只想给某个项目用，就换成该项目下的 `.claude/skills/coding-drill/`（同样要有 `coding-drill` 这一层）。重开一个会话，输入 `/skills` 能看到 `coding-drill` 就是装好了；然后说一句“出题 二分查找 Python 中等”。

**其他 Agent**：把 `coding-drill` 目录放进工作区，让 Agent 先读 `SKILL.md`。

**（从小红书来的读者）** 笔记下方的 RED Skill 组件里可以一键复制安装口令，直接发给你的 Agent 即可，不用手动 clone。

本机需要 `python3`（3.8+）；做 JavaScript 题需要 `node`，做 Java 题需要 `javac` 和 `java`。运行 `python3 scripts/judge.py doctor` 查看。它需要在你机器上运行 `python3` 来判题，第一次会请求授权。

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

- 给的是出题与判题的**纪律**，不是题库。题由你的 Agent 现出，质量取决于模型；纪律保证它薅不到分、抓得到错。
- 只做“完整程序、stdin → stdout”这一种形态；输出只用整数、布尔、单词。
- Python 无第三方库；JavaScript 为 CommonJS 无 npm 包；Java 公开类必须是 `Main`。

## 许可与维护

MIT。由学霸山丘技术团队维护。问题与建议请提 issue。
