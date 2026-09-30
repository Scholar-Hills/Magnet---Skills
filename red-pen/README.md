# 红笔改稿 · red-pen

逐句检查推文、周报、邮件和说明文档。先确认受众、目的和关注点，再指出具体问题、解释原因并提供短改法。批注对应原文中的句子，结果保存为可在浏览器打开的红笔页。原稿由你自己修改。

## 批注方式

- 每条批注引用原句，由脚本检查位置。无法定位的单列显示，定位成功的条目不足七成时需要重新提交。
- 改法只针对被引用的那一句。长度为引文字数的三倍，最少 20 字、最多 40 字；全部改法不超过稿子的一半，短稿的总预算至少为 60 字。长度检查不能识别所有代写情况，仍需遵守不整段重写的要求。
- 相同引文或相同批语不能重复提交。稿件有至少三块时，批注全部集中在前 20% 会收到提醒。

本 Skill 提供编辑意见，不打分或评级。修改后可以提交新版本，对照旧批注的变化。

## 安装

[仓库首页](../README.md#快速安装)提供在线安装命令。也可以先从首页下载仓库，或下载本 Skill 的完整文件夹，在该文件夹的上一级目录打开终端，再按提示选择目标 Agent：

```bash
npx skills@latest add ./red-pen --skill red-pen
```

需要 Node.js 与 npm。默认安装到当前项目；希望跨项目使用时加 `--global`。这一步安装的是完整 Skill 目录，包括脚本与参考文档。

也可指定客户端：

```bash
npx skills@latest add ./red-pen --skill red-pen --agent claude-code
npx skills@latest add ./red-pen --skill red-pen --agent codex
```

不使用命令行安装器，或使用 WorkBuddy、小红书下载包时，请看[仓库安装指南](../README.md#手动安装)。复制整个 `red-pen/` 文件夹，不能只复制 `SKILL.md`。已有同名安装时先备份，避免形成嵌套目录。

下载后手动安装到 Claude Code，也可以直接复制完整目录：

```bash
mkdir -p ~/.claude/skills
cp -R ./red-pen ~/.claude/skills/
```

WorkBuddy 用户按客户端设置选择技能目录，例如：

```bash
mkdir -p ~/.workbuddy-ai/skills
cp -R ./red-pen ~/.workbuddy-ai/skills/
```

安装后重开会话，让 Agent 使用 `red-pen`。选一个固定工作区保存后续产物，第一次使用时让 Agent 先读 `SKILL.md` 并运行其中的环境检查。运行脚本需要 Python 3.8 或更高版本，无第三方 Python 依赖。

如果稿件记录已经散落在多个工作区，让 Agent 按 `SKILL.md` 的说明检查；`doctor --scan` 只报告线索，不会搬动稿子或合并历史。

## 开始试用

适合检查邮件、周报、推文与说明文档。先明确受众和目的，再逐句指出问题、解释原因并给出短改法；交付批注对应原句的红笔页，原稿由你自己修改。

```text
用 red-pen 看看这篇稿子，给同行看，希望他们读完愿意试用。
```

[查看完整工作流](SKILL.md) · [浏览示例](examples/) · [反馈问题](../README.md#更新与反馈)

## 用法

丢一段稿子过去就行，剩下的它会问你：

```
（把稿子贴过来，或给一个文件路径）帮我看看
它先问：给谁看？要达到什么？最怕被读成什么样？
       ↓
一页红笔稿：drafts/<slug>/review.html
       ↓
（你自己改完，再交回来）再看一遍
它报出：上一版钉住的 7 条批注里有 4 条在新稿里消失了 —— 没定位的不算；引文找不到不等于问题已解决
```

想自己敲命令也可以（`--root` 写在子命令前面或后面都认，建议只给一次；前后各给一次时，按当前目录转成绝对路径后相同才接受，不同则退出 2）：

在选好的工作区运行。下面以 Claude Code 的安装路径为例；WorkBuddy 用户把 `~/.claude/skills/red-pen/` 换成 `~/.workbuddy-ai/skills/red-pen/`，其他安装位置也相应替换。先准备自己的 `稿子.md` 和 `brief.json`，brief 与批注的 JSON 格式见 [工作区契约](references/workspace-format.md)。这些是分步命令：拿到 `context` 输出后，须按它写好 `drafts/newsletter-01/inbox/marks.json`，再跑 `review`。

```bash
python3 ~/.claude/skills/red-pen/scripts/redpen.py doctor       # 查看环境与工作区
python3 ~/.claude/skills/red-pen/scripts/redpen.py init newsletter-01 --from 稿子.md   # 同名稿正文或目标后缀改变才升版；两者都相同不升版；稿子贴在对话里时用 --from - 从标准输入收
python3 ~/.claude/skills/red-pen/scripts/redpen.py brief set newsletter-01 --from brief.json
python3 ~/.claude/skills/red-pen/scripts/redpen.py context newsletter-01   # 上下文包，Agent 照着它写批注
# 先写好 inbox/marks.json，再运行下面几条。
python3 ~/.claude/skills/red-pen/scripts/redpen.py review newsletter-01    # 过闸 → 锚定 → 红笔页
python3 ~/.claude/skills/red-pen/scripts/redpen.py stats newsletter-01     # 与上一版对比
python3 ~/.claude/skills/red-pen/scripts/redpen.py check newsletter-01     # 离线复核整个工作区
python3 ~/.claude/skills/red-pen/scripts/redpen.py export newsletter-01    # 只导出计数与哈希
```

产物在 `drafts/<slug>/`：`review.html` 是可以截图的红笔稿，`marks.json` 是过闸之后的批注记录，`history/` 里存着每一版的稿子与每一轮的批注。`examples/drafts/newsletter-01/` 是一个跑通的示例，按安装平台选下面对应的一行就能离线复核试手：

```bash
python3 ~/.claude/skills/red-pen/scripts/redpen.py check ~/.claude/skills/red-pen/examples/drafts/newsletter-01
python3 ~/.workbuddy-ai/skills/red-pen/scripts/redpen.py check ~/.workbuddy-ai/skills/red-pen/examples/drafts/newsletter-01
```

## 边界

- **批注钉在原句上。** 每条批注必须带一句一字不差的原文引文；锚不到的自动标成未能定位单列一节，**脚本绝不擅自摆放**——摆错地方比不摆更糟。钉住的不足七成，整份退回重批。
- **不打分。** 没有分数、没有评级、没有整体印象。
- **改法只针对被引的那一句。** 给方向、给一个可以照抄的短句；长度按预算算：引文字数 × 3，最少 20 字、最多 40 字，全部改法加起来不超过稿子的一半（短稿另有 60 字的地板）。预算内也不许整段重写，或把几条改法拼成完整新稿。要整段重写请自己动笔，这份 Skill 不代笔。
- **稿子只读。** 脚本不改你的稿子，Agent 也不许改。新版本走 `init` 收成新一版，历史只增不改。
- 批语由 Agent 生成，脚本核对原文引用和批注位置；建议是否合适仍需你判断。
- 收 `.md` / `.html` / `.txt` / `.docx`。PDF、旧 Word、RTF、ODT、表格、演示、图片与压缩包等会被拒收，脚本会告诉你怎么转。Markdown 不解析（`##` 会当普通字符留在正文里）；docx 只读文字，表格按行读出、整行可以引，跨行引不了；图片不做文字识别，普通文字图注保留，修订痕迹与 Word 批注读不到。

## 安全说明

脚本只读写工作区，**不联网**，**不执行稿子里的任何代码**——稿子对它来说自始至终只是文本。红笔页是自包含单页 HTML，不加载任何外部资源；稿子里的 HTML 会先消毒再渲染，伪造的批注标记进不来。即便如此，别把不信任来源的 HTML 当稿子丢进来，红笔页最终要在浏览器里打开。

稿子、批注、红笔页全部留在本机，脚本不往任何地方发送。`export` 只导出计数与哈希，正文一个字都不带。

## 许可与维护

采用 [MIT 许可](../LICENSE)。由学霸山丘技术团队维护。问题与建议请到 [Issues](../README.md#更新与反馈)。
