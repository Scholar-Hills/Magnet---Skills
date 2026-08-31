# 自批私教 · self-grader

> 先证明它不会白给分：三份假作答必须 0 分。

一份给 Claude Code / WorkBuddy / OpenClaw 等 Agent 用的 Skill。你贴一道题和**你自己带来的
评分标准**，它先让脚本生成三份假作答——空白、把题面抄一遍、一段与题目毫无关系的文字——
并各批一遍；三份都批出 0 分、条目全部未命中，脚本才盖章，之后才允许批你真正写的答案。

批的时候，每一条「这一点你做到了」都必须引用你答案里的原话，脚本把引文钉回原文核对：
锚不回去的当场降为未命中，分数因此变化就整份退回重批。最后给你一张可以截图的判题卡、
一句「哪一条没命中」，以及一份只增不删的进度记录。

## 为什么要有它

自批的难处不在「会不会批」，在于批的人和被批的人是同一个。让模型给刚读过的一段话打分，
它倾向于找优点；让它给自己写的话打分，更是如此。所以这份 Skill 不谈「批得准不准」，
只做一件能机器验证的事：**让分数承担代价**。

- **先做校准，再批答案。** 空白、抄题面、无关段落三份假作答必须全部 0 分。
  一份空作答能拿到分，说明这一轮的标准根本没在测你写了什么——那么你真作答的分数
  同样没有意义。这是唯一一条「不通过就整条流程停下」的闸门。
- **判定要有原文撑着。** 每条命中都要给引文，引文由锚定引擎在原文里定位（空白折叠、
  弯引号归一、大小写不敏感、头尾锚定，能给的宽容都给了）；仍然找不到，就是这句话
  答案里根本没有，判定降级。
- **分数从判定算出来。** 条目标了分值时，分数必须恰好等于命中给满、部分给一半、
  未命中给零的合计——不能先想好一个数再倒推理由。
- **一字未改的稿子不会评出两个分数。** 同一稿重批换分当场拒收；想改判先说清哪一条判错了。
- **进度不可手改。** `progress.md` 是逐字契约，`check` 会拿每份结果重新算出那一行去核对。

## 安装

**Claude Code**

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/<org>/<repo>.git /tmp/self-grader-src
cp -R /tmp/self-grader-src/self-grader ~/.claude/skills/self-grader
```

装完的样子是 `~/.claude/skills/self-grader/SKILL.md`。只想给某个项目用，就换成该项目下的
`.claude/skills/self-grader/`（同样要有 `self-grader` 这一层）。重开一个会话，输入 `/skills`
能看到 `self-grader` 就是装好了；然后贴上你的题目和评分标准，说一句「帮我自批这道题」。

**WorkBuddy（腾讯）**

```bash
git clone https://github.com/<org>/<repo>.git /tmp/self-grader-src
cp -R /tmp/self-grader-src/self-grader ~/.workbuddy-ai/skills/self-grader
```

WorkBuddy AI 5.4 的技能目录是 `~/.workbuddy-ai/skills/`；如果你的数据目录是 `~/.workbuddy/`，
就放到 `~/.workbuddy/skills/self-grader`。装完在对话框输入 `/skills`，列表里有 `self-grader` 即可。

**用之前先选一个固定工作区**（输入框下方「Select Workspace」→ Open Local Folder，选一个专门
放练习的文件夹）。不选的话 WorkBuddy 会给每个任务新建一个 `~/WorkBuddy AI/<时间戳>/` 目录，
练习和 `progress.md` 会散落在不同目录里，进度就积累不起来了。

**其他 Agent**（OpenClaw、Codex 等）：把 `self-grader` 目录放进各自的技能目录或工作区
（OpenClaw 为 `~/.openclaw/workspace/skills/`），让 Agent 先读 `SKILL.md`。

**（从小红书来的读者）** 笔记下方的 RED Skill 组件里可以一键复制安装口令，直接发给你的
Agent 即可，不用手动 clone。

本机需要 `python3`（3.8+），没有别的依赖。运行 `python3 scripts/selfgrade.py doctor` 查看。
脚本需要在你机器上运行，第一次会请求授权。

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

- **自批分数只供自查，不是任何考试或课程的成绩。** 它衡量的是「这一稿离你自己带来的
  那份标准还差什么」，换一份标准就是另一个数字。
- **评分标准由你自带。** 本 Skill 不内置任何学科的评分细则，也不会凭记忆替你报一份出来——
  记错了比没有更糟，而你没法验证。老师给的、考纲附的、自己总结的都行。
- **批基线的过程可能会被你看到。** 三份假作答是脚本生成的、给标准做校准用的，你不必看；
  但如果你的 Agent 宿主会显示思考过程，这几步的推理仍然会出现在屏幕上——那是校准，
  不是对你答案的评价，看到了不用当真。
- 给的是**自批的流程与闸门**，不是评分标准，也不是题库。判得准不准取决于模型与你带来的
  标准；闸门保证的是：不会给空白与抄题面的答案分、每条判定都能在原文里找到落点、
  同一稿不会评出两个分数。
- 图片形式的答案不支持，请先转成文字。

## 许可与维护

MIT。由学霸山丘技术团队维护。问题与建议请提 issue。
