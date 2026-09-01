# 分段写作教练 · essay-sections

> 一个字没改，只是拆开了。

一份给 Claude Code / WorkBuddy / OpenClaw 等 Agent 用的 Skill：把一篇写好的稿子贴进去，它拆成「开头 / 若干子问题段 / 结论」，一段一张卡；每张卡右上角三个 1–5 的小格子，卡底一行灰字是它从这一段里逐字引的那句话。**稿子它一个字都不改，也不替你写任何一段。**

## 为什么要有它

让模型点评一篇长稿很容易，让它的点评**落到段**上、并且**站得住**很难。四件事最常出问题，这份 Skill 把它们各变成一道机器闸门：

- **拆的时候悄悄丢字。** 让模型「把这篇分成几段」，它常常顺手改标点、合并句子，或者把某一段整个漏掉。这里模型只回块号，脚本按字节偏移把原文切回来，然后把全部分段与全部落在段外的片段拼回去，**逐字节比对原文，不等就一个字都不落盘**。没进任何一段的文字连原文一起列在 `split-report.md` 里，绝不静默丢。
- **评审飘在半空。** 「第三段有点散」——哪一句？这里每条评审至少带一句一字不差的原文引文，空白归一之后必须真是那一段的子串；引用超过该段 40% 也拒收，因为那是复读不是评审。
- **一份评语贴满八段。** 两个分区的评语一模一样，整份拒收；三维分相同、评语高度重合会打上「评审雷同」的标记。
- **改完稿旧分数还在那儿装新的。** 每条评审入账时带着当刻的段落全文与哈希；你改了那一段，`status`、上下文包与分段卡三处同时标出「原文已修改」，那张卡的分数灰下去。

还有一条是刻意不做的：**它不做原创性检查，不给任何相似度、比例或百分比**。卡片上只有三个格子和一段评语，说的是这一段答没答自己的问题。

## 安装

**Claude Code**

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/<org>/<repo>.git /tmp/essay-sections-src
cp -R /tmp/essay-sections-src/essay-sections ~/.claude/skills/essay-sections
```

装完的样子是 `~/.claude/skills/essay-sections/SKILL.md`。只想给某个项目用，就换成该项目下的 `.claude/skills/essay-sections/`（同样要有 `essay-sections` 这一层）。重开一个会话，输入 `/skills` 能看到 `essay-sections` 就是装好了；然后丢一篇稿子过去说「帮我看看每段」。

**WorkBuddy（腾讯）**

```bash
git clone https://github.com/<org>/<repo>.git /tmp/essay-sections-src
cp -R /tmp/essay-sections-src/essay-sections ~/.workbuddy-ai/skills/essay-sections
```

WorkBuddy AI 5.4 的技能目录是 `~/.workbuddy-ai/skills/`；如果你的数据目录是 `~/.workbuddy/`，就放到 `~/.workbuddy/skills/essay-sections`。装完在对话框输入 `/skills`，列表里有 `essay-sections` 即可。

**用之前先选一个固定工作区**（输入框下方「Select Workspace」→ Open Local Folder，选一个专门放稿子的文件夹）。不选的话 WorkBuddy 会给每个任务新建一个 `~/WorkBuddy AI/<时间戳>/` 目录，同一篇稿子的账本、版本快照会散落在不同目录里，改稿之后就接不上前面几轮的评审了。

**其他 Agent**（OpenClaw、Codex 等）：把 `essay-sections` 目录放进各自的技能目录或工作区（OpenClaw 为 `~/.openclaw/workspace/skills/`），让 Agent 先读 `SKILL.md`。

**（从小红书来的读者）** 笔记下方的 RED Skill 组件里可以一键复制安装口令，直接发给你的 Agent 即可，不用手动 clone。

本机需要 `python3`（3.8+），没有别的依赖。运行 `python3 scripts/essayctl.py doctor` 查看。它需要在你机器上运行 `python3` 来拆段与记账本，第一次会请求授权。**回复语言跟随你**：你用中文它全程中文，你用英文它全程英文。

## 用法

丢一篇写好的稿子过去就行：

```
（把稿子贴过来，或给一个文件路径）帮我看看每段
       ↓
它先拆：8 张分段卡（开头 / 6 个子问题段 / 结论）——一个字没改，只是按字节偏移切开
       没进任何一段的文字逐条列在 split-report.md 里
       ↓
它再评：每段三个格子（句子 / 有没有答自己的问题 / 有没有推进主论点），各 1–5
       每条评审都从那一段里逐字引一句话
       ↓
一页分段卡：essays/<slug>/report.html
       ↓
（你自己改完某几段，再交回来）再看一遍
       改过的段落走势上多一个实心点；没改的画空心点，不算进步
       某段评到 2 分或满分时，它请你写一句反思——那句话会钉在那一稿上
```

只有一个题目、还没动笔也可以：它拆出 6–10 条子问题、建好分区骨架，**然后等你自己写**。

想自己敲命令也可以（**先 `cd` 进放稿子的工作区**，每个子命令的第一个位置参数都是稿名）：

```bash
python3 scripts/essayctl.py init remote-work-cities-01 --title "…" --setting untimed
python3 scripts/essayctl.py import remote-work-cities-01 稿子.md      # 切块编号 + 记字节偏移
python3 scripts/essayctl.py assemble remote-work-cities-01 \
    --from essays/remote-work-cities-01/inbox/groups.json
python3 scripts/essayctl.py context remote-work-cities-01 body-03     # 上下文包，Agent 照着它写评审
python3 scripts/essayctl.py review add remote-work-cities-01 body-03 \
    --from essays/remote-work-cities-01/inbox/review.json
python3 scripts/essayctl.py status remote-work-cities-01              # 每段的哈希、最新分、过期标记
python3 scripts/essayctl.py report remote-work-cities-01              # 生成分段卡
python3 scripts/essayctl.py check remote-work-cities-01               # 离线复核整个工作区
```

产物在 `essays/<slug>/`：`report.html` 是可以截图的分段卡，`sections/` 是拆出来的每一段（**只有你能改**），`ledger/` 与 `reflections.jsonl` 是只增不改的账本，`versions/` 里存着每次快照。`examples/essays/remote-work-cities-01/` 是一个跑通的示例工作区，可以直接 `check` 试手；`fixtures/remote-work-cities/` 里是生成它用的三版合成稿，外加一份带表格的 `.docx`，拿它跑一遍就知道「未纳入分段」长什么样。

## 边界

- **拆开不改字。** 每一段都是原文按字节偏移切出来的连续切片；拼回去必须逐字节等于原文，不等就不落盘。没进任何一段的文字逐条列出原文，不静默丢。
- **不做原创性检查。** 没有相似度、没有比例、没有百分比。三个格子说的是这一段答没答自己的问题，跟比对外部文本没有关系。
- **不改稿、不代写。** `sections/` 只有你能动；Agent 只能往 `inbox/` 放载荷。「第 3 段你帮我写了吧」它会拒绝。
- **不给改写建议。** 评审里出现改写字段直接拒收。要改句子，把那一段丢给 **red-pen**——它逐句批注、把批注钉回原句、钉不住的老实标成「未能定位」，同样不代笔。
- **荐读一律标「引用未核实」。** 脚本不联网，也不替你核实任何出处；模型给的书名、作者、年份都可能是编的，引用前请自行检索确认。
- **给的是纪律，不是判断力。** 评语由你的 Agent 现写，质量取决于模型。闸门能证明它读了原文、跑过上下文、没有拿同一份评语贴满全篇；**它不证明评得对**。
- 收 `.md` / `.txt` / `.html` / `.docx`。Markdown 不解析（`##` 会当普通字符留在正文里）；docx 只读文字段落，**表格与文本框会被搬到正文之后的附录区，不在原来的位置，并且必然进「未纳入分段」清单**，图片、脚注与修订痕迹不支持。排版复杂的稿子建议先另存为 `.md` 再进来。

## 安全说明

脚本只读写工作区（`essays/` 下面），**不联网**，**不执行稿子里的任何代码**——稿子对它来说自始至终只是文本。分段卡是自包含单页 HTML，不加载任何外部资源，也不含脚本。稿子、评审、反思与版本快照全部留在本机，脚本不往任何地方发送；`export --evidence` 只导出哈希、分数与版本清单，正文、引用、评语一个字都不带。

关于账本，说清楚它挡得住什么、挡不住什么：评审、反思、拆题各是一条哈希链，每行带着上一行的摘要，`chains.json` 另记链尾。**账本挡的是不知情的手改；知道 `chains.json` 存在的人两处一起改就能过。它证明的是账本没被顺手改过，不是不可伪造。只要 `chains.json` 还在，行少了就是硬错——`--rebuild-index` 不会替你抹掉少掉的行，只修写盘被打断时落后的索引。**

## 许可与维护

MIT。由学霸山丘技术团队维护。问题与建议请提 issue。
