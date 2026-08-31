# 红笔改稿 · red-pen

> 它只在稿子边上写字。

一份给 Claude Code / WorkBuddy / OpenClaw 等 Agent 用的 Skill：把一段稿子交给它——公众号推文、周报、邮件、说明文档都行——它先问清给谁看、要达到什么、最怕什么，再逐句批注：哪一句有问题、为什么、怎么改。批注由零依赖脚本钉回原文，产出一页可以截图的红笔稿。**稿子它一个字都不改。**

## 为什么要有它

让模型点评一段稿子很容易，让它的点评**站得住**很难。三件事最常出问题，这份 Skill 把它们各变成一道机器闸门：

- **批注飘在半空。** 「第三段有点啰嗦」——哪一句？模型说不出，或者说出来的那句原文里根本没有。这里每条批注必须带一句一字不差的原文引文，脚本拿去原文里定位；**钉不住的老实标成「未能定位」单列一节，绝不硬贴到某个位置**。钉住的不足七成，整份退回重批。
- **点评变成代笔。** 用户拿来 600 字，模型返回一份 400 字的「建议版本」——用户既看不出原来哪里不好，下次还是写成一样。这里的改法只许针对被引的那一句，长度不超过引文的三倍；所有改法加起来超过稿子的一半，整份拒收。
- **同一句评语贴满全篇。** 两条引文相同、或两条批语相同，整份拒收。批注全挤在开头 20% 的篇幅里会被提醒。

另外它**不打分**：没有分数、没有评级、没有整体印象。稿子好不好由你自己判断，红笔的职责是把可改的地方指出来。

## 安装

**Claude Code**

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/<org>/<repo>.git /tmp/red-pen-src
cp -R /tmp/red-pen-src/red-pen ~/.claude/skills/red-pen
```

装完的样子是 `~/.claude/skills/red-pen/SKILL.md`。只想给某个项目用，就换成该项目下的 `.claude/skills/red-pen/`（同样要有 `red-pen` 这一层）。重开一个会话，输入 `/skills` 能看到 `red-pen` 就是装好了；然后丢一段稿子过去说「帮我看看」。

**WorkBuddy（腾讯）**

```bash
git clone https://github.com/<org>/<repo>.git /tmp/red-pen-src
cp -R /tmp/red-pen-src/red-pen ~/.workbuddy-ai/skills/red-pen
```

WorkBuddy AI 5.4 的技能目录是 `~/.workbuddy-ai/skills/`；如果你的数据目录是 `~/.workbuddy/`，就放到 `~/.workbuddy/skills/red-pen`。装完在对话框输入 `/skills`，列表里有 `red-pen` 即可。

**用之前先选一个固定工作区**（输入框下方「Select Workspace」→ Open Local Folder，选一个专门放稿子的文件夹）。不选的话 WorkBuddy 会给每个任务新建一个 `~/WorkBuddy AI/<时间戳>/` 目录，同一篇稿子的历轮批注会散落在不同目录里，`stats` 就比不出「上一版的哪几条这次消失了」。

**其他 Agent**（OpenClaw、Codex 等）：把 `red-pen` 目录放进各自的技能目录或工作区（OpenClaw 为 `~/.openclaw/workspace/skills/`），让 Agent 先读 `SKILL.md`。

**（从小红书来的读者）** 笔记下方的 RED Skill 组件里可以一键复制安装口令，直接发给你的 Agent 即可，不用手动 clone。

本机需要 `python3`（3.8+），没有别的依赖。运行 `python3 scripts/redpen.py doctor` 查看。它需要在你机器上运行 `python3` 来锚定批注，第一次会请求授权。

## 用法

丢一段稿子过去就行，剩下的它会问你：

```
（把稿子贴过来，或给一个文件路径）帮我看看
它先问：给谁看？要达到什么？最怕被读成什么样？
       ↓
一页红笔稿：drafts/<slug>/review.html
       ↓
（你自己改完，再交回来）再看一遍
它报出：上一版 7 条批注里有 4 条在新稿里消失了 —— 那 4 处就是你真正改动到的地方
```

想自己敲命令也可以（`--root` 是顶层选项，写在子命令前面）：

```bash
python3 scripts/redpen.py init newsletter-01 --from 稿子.md   # 收稿；同名再跑一次算新版本
python3 scripts/redpen.py brief set newsletter-01 --from brief.json
python3 scripts/redpen.py context newsletter-01               # 上下文包，Agent 照着它写批注
python3 scripts/redpen.py review newsletter-01                # 过闸 → 锚定 → 红笔页
python3 scripts/redpen.py stats newsletter-01                 # 与上一版对比
python3 scripts/redpen.py check newsletter-01                 # 离线复核整个工作区
```

产物在 `drafts/<slug>/`：`review.html` 是可以截图的红笔稿，`marks.json` 是过闸之后的批注记录，`history/` 里存着每一版的稿子与每一轮的批注。`examples/drafts/newsletter-01/` 是一个跑通的示例，可以直接 `check` 试手。

## 边界

- **批注钉在原句上。** 每条批注必须带一句一字不差的原文引文；锚不到的自动标成「未能定位」单列一节，**脚本绝不擅自摆放**——摆错地方比不摆更糟。钉住的不足七成，整份退回重批。
- **不打分。** 没有分数、没有评级、没有整体印象。
- **改法只针对被引的那一句。** 给方向、给一个可以照抄的短句；不超过引文的三倍，全部改法加起来不超过稿子的一半。要整段重写请自己动笔，这份 Skill 不代笔。
- **稿子只读。** 脚本不改你的稿子，Agent 也不许改。新版本走 `init` 收成新一版，历史只增不改。
- 给的是**批注的纪律**，不是文笔：批语由你的 Agent 现写，质量取决于模型；纪律保证它引的是原文、钉得住位置、不越界替你写。
- 收 `.md` / `.html` / `.txt` / `.docx`。Markdown 不解析（`##` 会当普通字符留在正文里）；docx 只读文字段落，表格按段落读出、表结构会丢，图片与修订痕迹不支持。

## 安全说明

脚本只读写工作区，**不联网**，**不执行稿子里的任何代码**——稿子对它来说自始至终只是文本。红笔页是自包含单页 HTML，不加载任何外部资源；稿子里的 HTML 会先消毒再渲染，伪造的批注标记进不来。即便如此，别把不信任来源的 HTML 当稿子丢进来，红笔页最终要在浏览器里打开。

稿子、批注、红笔页全部留在本机，脚本不往任何地方发送。`export` 只导出计数与哈希，正文一个字都不带。

## 许可与维护

MIT。由学霸山丘技术团队维护。问题与建议请提 issue。
