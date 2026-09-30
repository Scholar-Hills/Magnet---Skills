# 分段写作教练 · essay-sections

检查长文的结构和论证。已有稿件会拆成开头、正文段和结论，每段单独评审；只有题目时，也可以先拆成子问题，再由你写正文。分段保留原文，不改写或代写。

## 分段评审

- 脚本按字节偏移拆分，再核对拼接结果与原文一致。未纳入分段的文字列在 `split-report.md` 中。
- 每条评审引用该段原文，检查语言、是否回答子问题、是否推进主论点，三个维度各为 1–5 分。单条与合计引文不超过该段的 40%。
- 两段评语完全相同会被拒收；分数相同且评语高度重合会标记为评审雷同。
- 段落修改后，旧评审会标记过期，方便区分不同版本的反馈。

不提供原创性检查或相似度结果。评审质量取决于模型，原文校验不能替代对意见本身的判断。

## 安装

[仓库首页](../README.md#快速安装)提供在线安装命令。也可以先从首页下载仓库，或下载本 Skill 的完整文件夹，在该文件夹的上一级目录打开终端，再按提示选择目标 Agent：

```bash
npx skills@latest add ./essay-sections --skill essay-sections
```

需要 Node.js 与 npm。默认安装到当前项目；希望跨项目使用时加 `--global`。这一步安装的是完整 Skill 目录，包括脚本与参考文档。

也可指定客户端：

```bash
npx skills@latest add ./essay-sections --skill essay-sections --agent claude-code
npx skills@latest add ./essay-sections --skill essay-sections --agent codex
```

不使用命令行安装器，或使用 WorkBuddy、小红书下载包时，请看[仓库安装指南](../README.md#手动安装)。复制整个 `essay-sections/` 文件夹，不能只复制 `SKILL.md`。已有同名安装时先备份，避免形成嵌套目录。

下载后手动安装到 Claude Code，也可以直接复制完整目录：

```bash
mkdir -p ~/.claude/skills
cp -R ./essay-sections ~/.claude/skills/
```

WorkBuddy 用户按客户端设置选择技能目录，例如：

```bash
mkdir -p ~/.workbuddy-ai/skills
cp -R ./essay-sections ~/.workbuddy-ai/skills/
```

安装后重开会话，让 Agent 使用 `essay-sections`。选一个固定工作区保存后续产物，第一次使用时让 Agent 先读 `SKILL.md` 并运行其中的环境检查。运行脚本需要 Python 3.8 或更高版本，无第三方 Python 依赖。

## 开始试用

适合检查长文的结构与论证。按原文拆出分段卡，逐段看语言、子问题与主论点，并保留评审和版本记录；也能从题目开始拆子问题，正文由你自己写。

```text
用 essay-sections 帮我看看这篇文章的每一段。
```

[查看完整工作流](SKILL.md) · [浏览示例](examples/) · [反馈问题](../README.md#更新与反馈)

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

产物在 `essays/<slug>/`：`report.html` 是可以截图的分段卡，`sections/` 是拆出来的每一段（**只有你能改**），`ledger/` 与 `reflections.jsonl` 是只增不改的账本，`versions/` 里存着每次快照。`examples/essays/remote-work-cities-01/` 是一个跑通的示例工作区，可以直接 `check` 试手；`fixtures/remote-work-cities/` 里是生成它用的三版合成稿，外加一份带表格的 `.docx`，拿它跑一遍就知道未纳入分段长什么样。

## 边界

- **拆开不改字。** 每一段都是原文按字节偏移切出来的连续切片；拼回去必须逐字节等于原文，不等就不落盘。没进任何一段的文字逐条列出原文，不静默丢。
- **不做原创性检查。** 没有相似度、没有比例、没有百分比。三个格子说的是这一段答没答自己的问题，跟比对外部文本没有关系。
- **不改稿、不代写。** `sections/` 只有你能动；Agent 只能往 `inbox/` 放载荷。第 3 段你帮我写了吧它会拒绝。
- **不给改写建议。** 评审里出现改写字段直接拒收。要改句子，把那一段丢给 **red-pen**——它逐句批注、把批注钉回原句、钉不住的老实标成未能定位，同样不代笔。
- **荐读一律标引用未核实。** 脚本不联网，也不替你核实任何出处；模型给的书名、作者、年份都可能是编的，引用前请自行检索确认。
- 评语由 Agent 生成。脚本检查原文引用、上下文与重复评语，意见是否合理仍需你判断。
- 收 `.md` / `.txt` / `.html` / `.docx`。Markdown 不解析（`##` 会当普通字符留在正文里）；docx 只读文字段落，**表格与文本框会被搬到正文之后的附录区，不在原来的位置，并且必然进未纳入分段清单**，图片、脚注与修订痕迹不支持。排版复杂的稿子建议先另存为 `.md` 再进来。

## 安全说明

脚本只读写工作区（`essays/` 下面），**不联网**，**不执行稿子里的任何代码**——稿子对它来说自始至终只是文本。分段卡是自包含单页 HTML，不加载任何外部资源，也不含脚本。稿子、评审、反思与版本快照全部留在本机，脚本不往任何地方发送；`export --evidence` 只导出哈希、分数与版本清单，正文、引用、评语一个字都不带。

关于账本，说清楚它挡得住什么、挡不住什么：评审、反思、拆题各是一条哈希链，每行带着上一行的摘要，`chains.json` 另记链尾。**账本挡的是不知情的手改；知道 `chains.json` 存在的人两处一起改就能过。它证明的是账本没被顺手改过，不是不可伪造。只要 `chains.json` 还在，行少了就是硬错——`--rebuild-index` 不会替你抹掉少掉的行，只修写盘被打断时落后的索引。**

## 许可与维护

采用 [MIT 许可](../LICENSE)。由学霸山丘技术团队维护。问题与建议请到 [Issues](../README.md#更新与反馈)。
