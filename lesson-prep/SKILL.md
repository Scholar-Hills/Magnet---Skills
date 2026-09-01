---
name: lesson-prep
description: 先把作业出出来，再让 AI 备课——老师交一张课纲卡（课题、课时、学习目标），按「出作业 → 规划阶段 → 逐页写投屏正文与教师讲稿 → 出成品」四步走，每步由零依赖脚本机器验收盖章；三把锁挡着：没出作业不许规划阶段，没规划阶段不许写页稿，没有一页过验收不许出成品。作业里每道题都要被某一页真讲到，脚本拿题干实词去正文与讲稿里对照，不看模型自报的标签。成品 deck.html 由脚本从页稿派生，教师讲稿另出 notes.html，绝不进投屏文件。Use when a teacher wants to prepare a lesson or build slides for a class, asks for a lesson plan with speaker notes, or wants the homework questions written first and every question provably covered by the deck (backward design / teaching-assessment alignment).
license: MIT
allowed-tools: Bash, Read, Write, Edit
---

# 先把作业出出来，再让 AI 备课（lesson-prep）

一句话：**出不来作业的课，讲了也白讲**——所以第一步就锁死，作业没出，阶段不许规划。

这份 Skill 给的是**备课的顺序与门控**，不是教学内容。课题、目标、题目、讲稿都由老师和模型一起写；脚本负责让「每道题都被某一页真讲到」「讲稿不是把正文抄一遍」「成品不是手搓出来的」这几件事**变成机器判定**。

## 你能对它说什么

| 老师说 | 它做 |
|---|---|
| `帮我备下周三那节课，45 分钟` | 先要一张课纲卡（课题、课时、学习目标或知识点），确认后建课 |
| `按这些目标出一份作业` | 出 3–20 道题请老师逐题确认，跑 `check questions` 盖章 |
| `分几个阶段讲` | 规划 2–6 个阶段，核对每条目标都有阶段承接 |
| `写页稿` | 逐页写投屏正文 + 教师讲稿，跑 `check pages` 核覆盖与字数 |
| `出成品` | `build` 派生 `deck.html` 与 `notes.html`，`report` 出验收报告 |
| `换个颜色` | `repalette` 一条命令换主题色，页稿一个字不动 |
| `哪道题没讲到` | 报告里的题↔页覆盖矩阵，格里是重合实词数，漏的一眼看见 |

## 前置检查（不可跳过）

0. **定位脚本。** 本 Skill 的脚本在 Skill 目录下，不在老师的工作区。按顺序找 `lesson-prep/scripts/lessonkit.py`，取第一个存在的绝对路径记作 `KIT`：
   ① 这份 SKILL.md 所在目录下的 `scripts/lessonkit.py`（你就是从那个目录读到本文件的）；② Claude Code：`~/.claude/skills/lesson-prep/`、当前项目 `.claude/skills/lesson-prep/`；③ WorkBuddy / CodeBuddy：`~/.workbuddy-ai/skills/lesson-prep/`、`~/.workbuddy/skills/lesson-prep/`、`~/.codebuddy/skills/lesson-prep/`、当前项目 `.codebuddy/skills/lesson-prep/`；④ OpenClaw：`~/.openclaw/workspace/skills/lesson-prep/`；⑤ 小红书 `redskill install` 的默认位置：当前目录 `./skills/lesson-prep/`；⑥ 老师在对话里指定的目录；⑦ 都没有就搜一次：`find . ~/.claude ~/.workbuddy ~/.workbuddy-ai ~/.codebuddy ~/.openclaw -path '*lesson-prep/scripts/lessonkit.py' 2>/dev/null | head -1`。
   本文后面所有 `python3 scripts/lessonkit.py …` 都读作 `python3 "$KIT" …`，并且始终在老师的工作区（`lessons/` 的父目录）下执行：`cd <工作区> && python3 "$KIT" check lessons/<slug> pages`。
   **七处都找不到就立即停止**，告诉老师「这份 Skill 的备课脚本缺失，请重新下载完整目录」。**任何情况下都不要自己写一个替代脚本**——手写的校验器没有这里的三把锁与覆盖判据，会让老师以为这节课是核过的。
1. 运行 `python3 "$KIT" doctor`。`python3` 不存在就试 `python`（Windows 常见）；两个都没有，告诉老师先装 Python 3.8+，不要继续。
2. 课都放在**当前工作区**（老师项目的根目录，不是 Skill 目录）的 `lessons/` 下。第一次建课前先 `pwd` 看一眼：如果当前目录是家目录、桌面或其它不像工作区的地方，先问老师一句「这节课的页稿、讲稿和成品我打算放在 `<当前路径>/lessons/`，可以吗？想换个地方现在告诉我」。定下来之后就别再换——盖章记的是相对这个目录的文件。
3. **回复语言跟随老师**：老师用中文就全程中文，用英文就全程英文，不要中英混着来。**投屏与讲稿用什么语言，由老师在 `lesson.json` 的 `language` 字段自己填**（`{"slides": …, "notes": …}`），脚本不预设任何语言政策，也不会因为它改变判定。
4. 第一次用之前，看一眼 Skill 目录里 `examples/lessons/city-wetland/` 这节已经跑完的示例课——四个 JSON 长什么样、页稿与讲稿分别写到什么程度、报告里的覆盖矩阵怎么读，照着它来比照着文字描述更不容易出错。格式以 `references/lesson-format.md` 为准，纪律与全部阈值以 `references/workflow-rules.md` 为准，成品壳以 `references/shell-contract.md` 为准，**动手前先读前两份**。

## 老师的角色

**每一步老师都是检验者，不是旁观者。** 题目对不对、阶段合不合理、讲稿能不能照着讲，脚本一概管不了——它只能保证你交上去的东西结构完整、互相对得上、没有敷衍。所以每一步都要先给草稿、等老师点头，再落盘。

不要一口气把四步做完再拿给老师看。**第二步的题目没确认，后面三步全是白做的。**

## 备课流程（按顺序做，不要跳步）

**动手前先说一句**：「我会先跟你要一张课纲卡，然后**先出作业**——作业没出，脚本不让我规划阶段。作业你逐题确认之后，我再分阶段、逐页写投屏正文和教师讲稿；每写完一步都跑一次验收，脚本会拿每道题的题干去每一页的正文和讲稿里对照，哪道题没被真讲到会红着列出来。最后成品由脚本从页稿生成，我不手写 `deck.html`。」非交互场景（批处理、子任务）就把这句写进最终报告的开头。

### 第 1 步　课纲卡：`lesson.json`

```bash
python3 "$KIT" init <slug>                          # 默认 homework-first
python3 "$KIT" init <slug> --route content-first    # 逃生口，见下
```

跟老师要四样：**课题、课时分钟数、学习目标（或核心知识点）、有没有自带材料**。目标建议 3–5 条，一条一件事、能拿去出题——「理解湿地」出不了题，「用自己的话说出湿地的定义并举出三种常见的湿地」可以。

老师没现成的目标就替他起草，**说清楚这是草稿、请他改**，改完再落盘。自带的课文、讲义放进 `lessons/<slug>/materials/`，在 `materials` 里写 `{"name": …, "path": "materials/xxx.md"}`；没有文件就写 `{"name": …, "excerpt": "一段原文"}`。

```bash
python3 "$KIT" check <slug> lesson
```

`goals` 与 `keyPoints` **不能同时为空**——两个都空就没有出题依据，后面几步都不用跑。

### 第 2 步　作业：`questions.json`（这一步决定后面讲什么）

**先出题，再想怎么讲。** 这是整份 Skill 的根：题目定下来，第三、四步就有了靶子；题目还没定就先写 PPT，写出来的每一页都没法验收。

出 3–20 道题（示例课用了 7 道），`choice` / `short` / `extended` 三种混着来，每种最多 10 道。逐题给老师看，**改到他点头为止**，然后落盘：

```json
{"id": "q1", "kind": "choice",
 "prompt": "题干，至少 10 字",
 "choices": ["2–6 项"], "correct": [0],
 "focus": ["最多 5 条考点短语"],
 "targets": ["g1", "k2"]}
```

- `targets` 写成 `g<序号>`（第几条 `goals`）或 `k<序号>`（第几条 `keyPoints`），**每道题都必须挂在某条上**。
- `focus` 是**考点短语，不是评分标准**。本 Skill 不产评分标准——`short` / `extended` 不带答案、不带打分细则，判分是批改线的事。
- 尽量让每条 `goals` 都被至少一道题考到，漏掉会给 WARN。

```bash
python3 "$KIT" check <slug> questions
```

**编程题不在这里出**：转调 coding-drill 的老师模式出题，然后在页的 `covers` 里以 `drill:<slug>` 引用。`lessonkit.py` 只校验这个 id 的格式，不会去跑判题。

### 第 3 步　阶段：`phases.json`

2–6 个阶段。每个阶段要有 `title`（纯阶段名）、`summary`（≥20 字，说清这一段在做什么）、`goals`（承接哪几条目标），`minutes` 可选但建议写。

**标题不许带编号前缀**：`第一阶段`、`1.`、`一、`、`（3）`、`Phase 1`、`Step 2` 全会被拦下。顺序由数组表达，写进标题只会在调整顺序时变成错的。

```bash
python3 "$KIT" check <slug> phases
```

**每条 `g<n>` 学习目标至少要被一个阶段承接**，否则逐条 ERROR「目标无阶段承接」。这一条挡的是「目标写了四条、实际只讲了两条」。

### 第 4 步　页稿：投屏正文 + 教师讲稿

先写 `pages/index.json`（顺序表），再逐页写两个文件：

```
pages/index.json      [{"id": "p05", "phase": "蓄水与净化", "title": "湿地像一块海绵", "covers": ["q2"]}]
pages/p05.html        投屏正文，白名单 HTML 片段（不是整页文档）
pages/p05.notes.md    教师讲稿，纯文本
```

- **`phase` 必须逐字等于某个阶段标题**；每个阶段至少要有一页。
- **单页 `covers` 最多 3 道题。** 一页贴四道题就是在用标签冒充讲过了。
- 页数建议 8–12（3–20 之外给 WARN，超过 30 是 ERROR）。
- 投屏正文一页一件事：一个 `h2` 加三到五条 `li`。**去标签超过 350 字给 WARN，超过 1000 字是 ERROR**——投出来读不清。
- **讲稿是讲台上说的话，不是正文的复述。** 单页讲稿字数要不少于本页正文；全课讲稿总字数不少于 `minutes × 60`（45 分钟课就是 2700）；讲稿与本页正文的 2-gram 重合超过 0.8 直接判死「抄正文当讲稿」。

```bash
python3 "$KIT" check <slug> pages
```

这一步跑的是三道闸：页稿准入（标签白名单、图片来源、占位模式、壳保留词）、讲稿下限、**题↔页覆盖**。覆盖不过时脚本会逐题点名：「页里没讲到这道题：题干实词与覆盖页最多只重合 N 个」——**去改那一页的正文与讲稿，把题真的讲进去，不要去改 `covers` 蒙混。**

### 第 5 步　成品与报告

```bash
python3 "$KIT" build <slug> [--palette cyan|indigo|emerald|amber|rose|violet|slate|teal]
python3 "$KIT" report <slug>
python3 "$KIT" check <slug> --all        # 四步复核 + 成品哈希对账，0 ERROR 才算交付
```

交付时告诉老师：投屏文件是 `lessons/<slug>/deck.html`（浏览器打开，方向键翻页，`Ctrl/Cmd + P` 可以打成 16:9 的 PDF），教师讲稿是 `notes.html`（左边页缩略、右边讲稿，页首写着「教师讲稿 · 不投屏」），验收报告是 `report.md` 与 `report.html`（**`report.html` 可以直接截图**：上半是四步状态条与三把锁，下半是题↔页覆盖矩阵和每页的讲稿字数条）。

想换主题色：`python3 "$KIT" repalette <slug> --palette rose`——只重拼成品，`pages/` 逐字节不动。

## 三把锁与逃生口

```
① 课纲卡  →  ② 作业  →  ③ 阶段  →  ④ 页稿  →  成品
          锁一：没出作业，  锁二：没规划阶段，  锁三：没有一页过
          不许规划阶段      不许写页稿          验收，不许出成品
```

锁**由盖章文件保证，不靠自觉**。撞上锁时脚本打印「锁住了：<该先跑哪一条>」并**退出 2**，连闸门都不跑。**这不是环境坏了，是流程还没走到——照它说的那一条去跑，不要绕。**

`--route content-first` 是给「习惯先备课」的老师的逃生口：把出题从主链上摘下来，主链变成 `课纲卡 → 阶段 → 页稿`。**但它只是把出题后置到 `build` 之前，不是免除**——没有作业盖章，`build` 会退出 2 说「出题只能后置，不能跳过」，并且在那一刻补跑一次覆盖闸。走这条路线时，`check` 与报告顶部都会印一句「未先出作业」。

**默认走 `homework-first`。** 只有老师明确要求先写内容时才用 `content-first`，用之前跟他说清楚出题不会被免掉。

## 上游改了，下游作废

每步 `check` 通过就写一张盖章（`.stamps/<step>.json`），记下本步与全部上游文件的 sha256。下游 `check` 先比对，对不上就是 ERROR：

```
[ERROR] G10 questions.json：questions.json 已改动，请从 check questions 重新验收
```

**看到这句就从它点名的那一步重新往下跑**，不要只补最后一步。改了作业，`check questions` → `check phases` → `check pages` → `build` 全都要重来。

`check <slug> --all` 是四步逐个重跑再加一次成品对账：`deck.html` 或 `notes.html` 的哈希与 `.stamps/deck.json` 对不上，判「成品不是由 `build` 生成或生成后被手改」。**交付前跑一次 `--all`，0 ERROR 才算完。**

## 页稿准入的几条硬规矩

完整规则见 `references/workflow-rules.md` §4–§7，写页稿前必读。最常撞的四条：

**一、图片只许两种来源。** `<img src="assets/xxx.png">`（文件必须真实存在）或者 `data:image/…;base64,`（≤ 2 MB）。外链一律 ERROR，`style` 里的 `url()` 同判——教室断网时外链就是一块白。
**外链判据不按写法枚举**：任何属性值里出现 `http://`、`https://` 或协议相对 `//` 就是 ERROR（合法 `data:image` 内嵌图的 base64 载荷除外），`image-set()`、`cross-fade()` 这类不带 `url(` 的 CSS 函数换个马甲也一样抓，CSS 注释里的网址同样被拒；成品侧还会用同一条判据复查一遍。

**二、13 个壳保留类名会被拒收。** `slide` `pad` `fit` `stage` `rail` `thumb` `talk` `row` `wrap` `say` `no` `hd` `sub`——这些是成品壳自己的结构名，页稿里再用一次，翻页脚本就会把假页当真页数进去（页码变成 1/4、真页内容被藏掉）。
**注意 `row`、`no`、`sub`、`wrap` 这几个是最容易随手写的普通英文词**：两栏布局写 `class="row"`、序号写 `class="no"`、副标题写 `class="sub"`，全都会被拒收。换成 `cols` / `idx` / `subtitle` 就行。`data-page-id` 与 `data-talk-id` 两个属性同样保留。普通的 `data-*` 与 `aria-*` 不受影响。

**三、占位模式一律判死。** `TODO`、`TBD`、`placeholder`、`lorem ipsum`、「此处插图」、「待补图」、「此处配图」、「待补充」、`[图]`——正文和讲稿都查。没想好就把那段删掉，别留记号，不然就是站在讲台上、投影已经亮着的时候才发现这页没写完。

**四、主题色一律 `var(--accent)`。** 壳的 `h1` / `h2` / `th` / `blockquote` 默认就吃它，纯文本页什么都不写也能换色。`style` 里写死非中性色会给 WARN。

## 门禁（必须遵守）

- **没过 `check` 不许进下一步。** 每一步都要看到「0 ERROR」再往下走。有 WARN 要**逐条念给老师听**，由他决定改不改，不要吞掉。
- **不许手写、手改 `deck.html` 与 `notes.html`。** 页稿是唯一的 source of truth，成品只能由 `build` 派生。手改会被哈希当场对出来。同理，`report.md` / `report.html` 由 `report` 渲染，**模型不写报告**。
- **不许一页 `covers` 超过三道题。**
- **不许把正文复制成讲稿。** 讲稿是讲台上说的话——举例、设问、预判学生会答错的地方、要不要停下来提问。正文是投影上的字。两者本来就该不一样。
- **不许只写正文不写讲稿**，也不许拿一个字充数：单页讲稿不得少于本页正文字数。
- **不许写占位图说明。**
- **`check` 报 ERROR 时改产物，不要改脚本，也不要调阈值。** 闸门是这份 Skill 唯一的价值。
- **编程题转调 coding-drill 的老师模式**，在 `covers` 里以 `drill:<slug>` 引用，不要在这里手写编程题。
- **覆盖不过时改内容，不要改 `covers`。** 把 `covers` 删掉确实能让那道题「不再报错」——它会立刻变成「没有任何一页覆盖这道题」，同样是 ERROR。真正的解法是把题讲进那一页。

## 哪些是机器判定，哪些不是（G0）

对外只承诺前两类，第三类始终是老师的活：

- **机器真值**：结构校验、哈希盖章与失效、页稿准入、壳字符串断言、`repalette` 逐字节 diff、发布卫生静态闸。结果唯一，不随模型。
- **文本启发式**：讲稿字数下限、题↔页实词重合 ≥ 2、讲稿抄正文的 2-gram 重合 > 0.8、正文密度阈值、非中性色饱和度。有阈值、会误判，用来挡敷衍，不保证正确。
- **仍靠老师确认**：题目对不对、阶段合不合理、讲稿能不能照着讲。

**覆盖判据是文本重合启发式，不是执行真值。** 它挡得住「一页 `covers` 全部题」「给页贴个标签蒙混过去」「题干与页面毫不相干」；**它挡不住「讲到了但讲错了」**。跟老师说清楚这一点，不要把覆盖矩阵全绿说成「这节课没问题」。

## 安全约束

- 脚本**只读写你指定的那个课目录**，不联网、不调用任何外部服务，也不读工作区以外的文件。
- 页稿里的 HTML **只做消毒与校验，不执行**：脚本、样式块、事件属性、危险 URL 一律在准入阶段判死，没有任何一处会把页稿当代码跑。
- 成品是自包含的单文件 HTML，无外链（属性值里出现协议字样即拒，准入与成品两侧同一条判据）、无品牌、无 logo。`deck.html` 里恰好一个脚本（翻页与缩放），`notes.html` 里一个都没有。

## 边界与承诺

- 给的是**备课的顺序与门控**，不是教学内容，也不是学科知识。内容质量随模型；纪律负责让每道题都有页讲、让讲稿不是正文的复印件、让成品不是手搓的。
- **没有配图生成、没有 PPTX 导出、没有第二遍自由排版。** 图片只能是老师自己放进 `assets/` 的本地文件；成品是 HTML，要 PDF 就用浏览器打印（壳自带 16:9 打印 CSS）。
- **成品不保证一定不溢出**：页内缩放的下限是 0.5，缩到一半还装不下就会被裁。`build` 完自己打开翻一遍。
- **宿主展示推理过程时，可能会把题目的正确答案在推理流里说出来。** 备课场景下无害，但如果屏幕正对着学生，注意一下。
- 脚本零依赖，Python 3.8+。

## 文件

- `scripts/lessonkit.py`——建课（`init`）、四步验收（`check`）、成品（`build`）、换色（`repalette`）、报告（`report`）、环境检查（`doctor`）
- `scripts/selftest.py`——脚本自测（闸门正反例、壳断言、消毒绕过回归、作弊课对抗基线、`build` 幂等、`repalette` 逐字节不变、示例课复核）
- `scripts/banned_words.py`——发布前的静态闸
- `references/lesson-format.md`——目录布局、四个 JSON 与页稿的逐键契约、盖章、命令行与退出码
- `references/workflow-rules.md`——四步纪律、三把锁、**全部阈值清单**、实词与 2-gram 口径、准入规则、G0 分类声明
- `references/shell-contract.md`——成品壳保证什么、不保证什么，浏览器打印 PDF 的步骤
- `examples/lessons/city-wetland/`——一节跑完的 45 分钟示例课（自撰说明文当课文，7 道题 / 3 阶段 / 9 页，`check --all` 0 ERROR）
- `docs/usage-log.md`——真课记录表

---

English summary: lesson-prep prepares one class session in four gated steps — lesson card, homework, phases, then per-page slide body plus separate teacher notes — with a zero-dependency Python script stamping each step. Three locks are enforced by hashes, not by good intent: no homework, no phase planning; no phases, no page drafting; no page passing review, no build. This is backward design made mechanical — the questions are written first and every question must be genuinely covered by some page, judged by overlapping content words between the question stem and that page's body plus notes, never by a label the model assigns itself. Speaker notes have a word floor (`minutes × 60` for the whole lesson, and at least the page's own body length per page) and are rejected when they overlap the slide body by more than 80% of bigrams. `deck.html` is derived from the page sources by the script alone — the model never writes a second copy of the HTML — and the teacher notes go to a separate `notes.html` that never enters the projected file. Page intake runs a tag allowlist, blocks `on*` handlers and dangerous URLs, and permits images only from `assets/` or `data:image` base64. Output is a self-contained 1280×720 deck with arrow-key navigation, two-stage scaling, 16:9 print CSS, an eight-key accent palette swappable in one command, and a screenshot-ready report carrying the four-step bar, the three locks, the question-to-page coverage matrix and per-page notes-length bars. Coverage is a text-overlap heuristic, not execution truth: it catches label-only coverage, not a page that covers the question and gets it wrong — that judgement stays with the teacher.
