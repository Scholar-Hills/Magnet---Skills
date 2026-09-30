# 先把作业出出来，再让 AI 备课 · lesson-prep

> 默认先出作业，再围绕学习目标组织课堂内容，每一步都验收。

一份给 Claude Code / WorkBuddy / OpenClaw / Codex 等 Agent 用的 Skill：老师交一张课纲卡（课题、课时、学习目标），Agent 按「**出作业 → 规划阶段 → 逐页写投屏正文与教师讲稿 → 出成品**」四步走，每一步由一个零依赖的 Python 脚本机器验收、盖章存证。作业里每道题都要被某一页**真讲到**——脚本拿题干的实词去每页的正文和讲稿里对照，不看模型自报的标签。成品 `deck.html` 由脚本从页稿派生，模型不写第二遍 HTML；教师讲稿另出 `notes.html`，绝不进投屏文件。

## 为什么要有它

让模型写一份课件大纲很容易，让它**经得起核**很难。三件事最常出问题：

- **课备完了，作业还没影。** 讲的是一套，考的是另一套，学生课后翻开作业发现三道题没听过。
- **讲稿是正文的复印件。** 投影上写什么，讲稿上抄什么，等于没有讲稿。
- **成品是手搓的。** 模型直接写一份 `deck.html` 交差，跟前面几步的验收没有任何关系。

这份 Skill 把这三件事变成机器判定：

- **三把硬锁，由哈希盖章保证，不靠自觉。** 没出作业不许规划阶段；没规划阶段不许写页稿；没有一页过验收不许出成品。撞上锁脚本直接退出 2，连闸门都不跑。习惯先写内容的老师有 `--route content-first` 这个逃生口，但那只是把出题**后置**到出成品之前，不是免除。
- **每道题都要被某一页真讲到。** 判据是题干实词与该页正文＋讲稿的重合数，下限 2；单页最多认领 3 道题。报告里有一张题↔页覆盖矩阵，哪道题没被讲到红着摆在表里。
- **讲稿有硬下限，且不许抄正文。** 全课讲稿不少于 `课时 × 60` 字，单页讲稿不少于本页正文；讲稿与本页正文的 2-gram 重合超过 0.8 直接判死。
- **成品只能由脚本派生。** 页稿是唯一的 source of truth。手改 `deck.html`，下一次复核就会对出哈希不符：「成品不是由 build 生成或生成后被手改」。
- **上游改了，下游作废。** 改了一道题，脚本会点名「`questions.json` 已改动，请从 `check questions` 重新验收」。
- **讲稿绝不进投屏文件。** `build` 会逐页断言每页讲稿的前 40 字不出现在 `deck.html` 里。

主图就是脚本产出的 `report.html`，可以直接截图：上半是**四步状态条**与**三把锁**（锁住时印着该先跑哪一条），下半是**题↔页覆盖矩阵**（行是题、列是页、格里是重合的实词数）和**每页的讲稿字数条**。

## 安装

[仓库首页](../README.md#快速安装)提供在线安装命令。也可以先从首页下载仓库，或下载本 Skill 的完整文件夹，在该文件夹的上一级目录打开终端，再按提示选择目标 Agent：

```bash
npx skills@latest add ./lesson-prep --skill lesson-prep
```

需要 Node.js 与 npm。默认安装到当前项目；希望跨项目使用时加 `--global`。这一步安装的是完整 Skill 目录，包括脚本与参考文档。

也可指定客户端：

```bash
npx skills@latest add ./lesson-prep --skill lesson-prep --agent claude-code
npx skills@latest add ./lesson-prep --skill lesson-prep --agent codex
```

不使用命令行安装器，或使用 WorkBuddy、小红书下载包时，请看[仓库安装指南](../README.md#手动安装)。复制整个 `lesson-prep/` 文件夹，不能只复制 `SKILL.md`。已有同名安装时先备份，避免形成嵌套目录。

下载后手动安装到 Claude Code，也可以直接复制完整目录：

```bash
mkdir -p ~/.claude/skills
cp -R ./lesson-prep ~/.claude/skills/
```

WorkBuddy 用户按客户端设置选择技能目录，例如：

```bash
mkdir -p ~/.workbuddy-ai/skills
cp -R ./lesson-prep ~/.workbuddy-ai/skills/
```

安装后重开会话，让 Agent 使用 `lesson-prep`。选一个固定工作区保存后续产物，第一次使用时让 Agent 先读 `SKILL.md` 并运行其中的环境检查。运行脚本需要 Python 3.8 或更高版本，无第三方 Python 依赖。

## 开始试用

适合老师把课题、课时与学习目标变成可验收的课堂材料。默认先出作业，再规划阶段、写投屏正文与讲稿，交付 HTML 课件、独立教师讲稿和验收报告。

```text
用 lesson-prep 备一节城市湿地保护课，４５分钟，先确认学习目标。
```

[查看完整工作流](SKILL.md) · [浏览示例](examples/) · [反馈问题](../README.md#更新与反馈)

## 用法

跟 Agent 说话就行，下面这些是它替你跑的命令：

```bash
python3 scripts/lessonkit.py init <slug>                    # 建课骨架（默认先出作业）
python3 scripts/lessonkit.py check <slug> lesson            # 第 1 步：课纲卡
python3 scripts/lessonkit.py check <slug> questions         # 第 2 步：作业，过了才解锁第 3 步
python3 scripts/lessonkit.py check <slug> phases            # 第 3 步：阶段
python3 scripts/lessonkit.py check <slug> pages             # 第 4 步：页稿 + 讲稿 + 覆盖
python3 scripts/lessonkit.py build <slug> --palette rose    # 出成品
python3 scripts/lessonkit.py report <slug>                  # 验收报告
python3 scripts/lessonkit.py check <slug> --all             # 四步复核 + 成品哈希对账
python3 scripts/lessonkit.py repalette <slug> --palette teal  # 只换主题色，页稿一字不动
```

跑完你会拿到：

- `lessons/<slug>/deck.html`——投屏文件。浏览器打开，方向键翻页，`Ctrl/Cmd + P` 打成 16:9 的 PDF。单文件、无外链、无 logo，教室断网也照常放。
- `lessons/<slug>/notes.html`——教师讲稿。每页一行，左边是这一页的缩略、右边是要说的话，页首写着「教师讲稿 · 不投屏」，打印出来就能带上讲台。
- `lessons/<slug>/report.md` 与 `report.html`——验收报告。四步状态条、三把锁、题↔页覆盖矩阵、目标↔阶段表、每页讲稿字数与正文密度、逐条 ERROR / WARN。

八个主题色：`cyan`（默认）、`indigo`、`emerald`、`amber`、`rose`、`violet`、`slate`、`teal`。壳的 `h1` / `h2` / `th` / `blockquote` 默认吃主题色，纯文本页也看得出换了色。

`examples/lessons/city-wetland/` 是一节跑完整流程的示例课（自撰的八百字中文说明文当课文，45 分钟，7 道题 / 3 阶段 / 9 页正文与讲稿），可以试手。注意 `check --all` 每过一步都会更新课目录里的 `.stamps/` 盖章，直接对 `examples/` 跑会把示例目录改脏——先拷一份出来再跑：

```bash
cp -R examples/lessons/city-wetland lessons/city-wetland-try
python3 scripts/lessonkit.py check lessons/city-wetland-try --all
```

## 目录

```
SKILL.md                          Agent 读的说明
scripts/lessonkit.py              建课 / 四步验收 / 成品 / 换色 / 报告 / 环境检查（零依赖）
scripts/selftest.py               脚本自测
scripts/banned_words.py           发布前的静态闸
references/lesson-format.md       目录布局与四个 JSON 的逐键契约
references/workflow-rules.md      四步纪律、三把锁、全部阈值清单、实词口径
references/shell-contract.md      成品壳保证什么、不保证什么，打印 PDF 的步骤
examples/lessons/city-wetland/    一节跑完的 45 分钟示例课
docs/usage-log.md                 真课记录表
```

## 安全说明

脚本只读写你指定的那个课目录，不联网，不调用任何外部服务。页稿里的 HTML **只做消毒与校验，不执行**：脚本块、样式块、事件属性、`javascript:` 这类危险 URL 一律在准入阶段判死，图片只许 `assets/` 下的本地文件或 `data:image` base64（≤ 2 MB），没有任何一处会把页稿当代码跑。成品是自包含的单文件 HTML：`deck.html` 里恰好一个脚本（翻页与缩放），`notes.html` 里一个都没有，两个文件都不含品牌与 logo。

## 边界

- 给的是**备课的顺序与门控**，不是教学内容，也不是学科知识。课题、目标、题目、讲稿都是你和模型一起写的，内容质量随模型；纪律负责让每道题都有页讲、让讲稿不是正文的复印件、让成品不是手搓的。
- **覆盖判据是文本重合启发式，不是执行真值。** 它挡得住「一页认领全部题」「给页贴个标签蒙混过去」「题干与页面毫不相干」；**它挡不住「讲到了但讲错了」**。覆盖矩阵全绿不等于这节课没问题，最后一关仍然是你自己看一遍。
- **成品不保证一定不溢出。** 页内缩放的下限是 0.5，一页内容多到缩一半还装不下就会被裁。密度提示（350 字 WARN / 1000 字 ERROR）是按 CSS 推算的启发式，不是保证。`build` 完自己打开翻一遍。
- **无外链靠协议判据保证，不靠函数名枚举**：页稿任何属性值里出现 `http://`、`https://` 或协议相对 `//` 一律拒收（合法的 `data:image` 内嵌图除外），`image-set('https://…')` 这类不带 `url(` 的写法也拦，成品侧用同一条判据再查一遍。样式值经实体解码后不接受反斜杠转义；出现即拒收。代价是从严：`style` 注释里写网址也会被拒，网址请写进正文文字。
- **没有配图生成、没有 PPTX 导出、没有第二遍自由排版。** 图片只能是你自己放进 `assets/` 的本地文件；要 PDF 就用浏览器打印，壳自带 16:9 打印 CSS。
- **不产评分标准。** 选择题只带正确项下标，简答与论述只给题干和最多 5 条考点短语，判分是批改线的事。
- **编程题不在这里出**，转调 coding-drill 的老师模式，在页的 `covers` 里以 `drill:<slug>` 引用。
- **英文课的阈值偏严。** 字数一律「中文按字、英文按词」，所以题干 10 字、阶段说明 20 字、全课讲稿 `课时 × 60` 这几条下限，换成英文就是 10 个词、20 个词、2700 个词，实际要求高不少。这几个阈值还在实测回调中。
- **宿主展示推理过程时，可能会把题目的正确答案在推理流里说出来。** 备课场景下无害，但屏幕正对着学生时留意一下。
- 脚本零依赖，Python 3.8+。

## 许可与维护

采用 [MIT 许可](../LICENSE)。由学霸山丘技术团队维护。问题与建议请到 [Issues](../README.md#更新与反馈)。
