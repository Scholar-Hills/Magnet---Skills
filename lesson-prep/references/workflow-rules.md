# 备课纪律：四步、三把锁与每一条阈值

这份文件是 `scripts/lessonkit.py`、`scripts/selftest.py` 与文档三方共享的约定。**下面每一个数字都抄自 `scripts/lessonkit.py` 顶部的常量区；改常量就要在同一个 commit 里改这份文档与 selftest，反之亦然。** 字段与目录布局见 `references/lesson-format.md`，成品壳见 `references/shell-contract.md`。

## 0. 先说清楚哪些是真的机器判定（G0 分类声明）

这份 Skill 的闸门分三类，**对外只承诺前两类**：

**一、机器真值** —— 结果唯一，不随模型、不随心情：

- 结构校验：字段在不在、类型对不对、引用悬不悬空、数量在不在范围内。
- 哈希盖章与失效：每步的 sha256 记在 `.stamps/` 里，上游改一个字节，下游立刻判死。
- 页稿准入：标签白名单、`on*` 事件、危险 URL、图片来源、壳保留词。
- 壳字符串断言：`deck.html` 里 `<script` 恰好一次、无 `<svg`、`data-page-id` 数等于成品页数。
- 逐字节 diff：`repalette` 之后 `pages/` 一个字节都不许变。
- 静态闸：发布卫生扫描。

**二、文本启发式** —— 有阈值、会误判，用来挡住「敷衍」而不是保证「正确」：

- 讲稿字数下限（全课 `minutes×60`、单页不少于本页正文）。
- 题↔页实词重合 ≥ 2。
- 讲稿与正文 2-gram 重合 > 0.8 判「抄正文当讲稿」。
- 正文密度阈值、非中性色饱和度、重复题的 2-gram 重合。

**三、仍靠老师确认** —— 脚本一概管不了：

- 题目本身对不对、够不够、难不难。
- 阶段划分合不合理、时间分配现不现实。
- 讲稿能不能照着讲出来、讲得对不对。

**覆盖闸是文本重合启发式，不是执行真值。** 它挡得住「一页 `covers` 全部题」「给页贴个标签蒙混过去」「题干与页面毫不相干」；它挡不住「讲到了但讲错了」。后面这一类，只有老师这一步能挡。报告的页脚会把这段声明原样印出来。

## 1. 四步与三把锁

```
① 课纲卡 lesson.json  →  ② 作业 questions.json  →  ③ 阶段 phases.json  →  ④ 页稿 pages/  →  成品 build
                      锁一：没出作业，        锁二：没规划阶段，      锁三：没有一页过
                      不许规划阶段            不许写页稿              验收，不许出成品
```

三把锁**由盖章文件保证，不靠自觉**：下一步的 `check` 先看上游那张盖章在不在，不在就打印「锁住了：<该先跑哪一条>」并**退出 2**，连闸门都不跑。

刻意的顺序是：**先验锁 → 再对哈希 → 最后才跑闸门**。没出作业就想规划阶段，你该看到的是那句锁的话，而不是一串「作业不存在」。

每一步都是同一个循环：

> 动手前说一句要做什么 → 出草稿给老师看 → 老师确认 → 落盘 → 跑 `check` → 有 ERROR 就**改产物、不改脚本** → 重跑。

## 2. 路线：默认先出作业，`content-first` 是逃生口不是免除

`route` 在 `init` 时问一次，写进 `lesson.json`，之后不再改。

- **`homework-first`（默认）**：主链是 `lesson → questions → phases → pages`，规规矩矩四步。
- **`content-first`**：把出题从主链上摘下来单挂在课纲卡后面，主链变成 `lesson → phases → pages`。**出题只是被后置到 `build` 之前，不是被免除**：没有 `.stamps/questions.json`，`build` 会退出 2 并说「出题只能后置，不能跳过」。`build` 那一刻还会补跑一次覆盖闸。

走 `content-first` 时，`check <slug> pages`、`check <slug> --all` 与报告顶部都会印一句「**未先出作业**」。这句话不是说教，是给三个月后翻这节课的人看的：当时是按什么顺序做的，报告上写着。

## 3. `check <step>` 与 `check --all` 的盖章口径

| 命令 | 跑什么 | 盖什么章 |
|---|---|---|
| `check <slug> lesson` | G1 | 通过则写 `.stamps/lesson.json` |
| `check <slug> questions` | G1 → G2 | 通过则写 `.stamps/questions.json`（含上游哈希） |
| `check <slug> phases` | G1 → G2 → G4 | 通过则写 `.stamps/phases.json` |
| `check <slug> pages` | G1 → … → G5/G6/G7 | 通过则写 `.stamps/pages.json` |
| `check <slug> --all` | 四步**逐步**跑，每步过一步盖一步；末尾再做成品哈希对账 | 逐步盖章，不碰 `.stamps/deck.json` |
| `build <slug>` | 准入 + 壳断言 | 写 `.stamps/deck.json`（含成品哈希、配色、成品页与失败页） |

**只有 0 ERROR 才盖章**，有 WARN 照样盖。`--all` 的每一步是独立判定的：前一步不过就在那里停住，不会拿一份没过的上游去跑下游。

**上游改动 → 从 `<step>` 重新验收。** 下游 `check` 先比对上游哈希，对不上就是 ERROR：

```
[ERROR] G10 questions.json：questions.json 已改动，请从 check questions 重新验收
```

`<step>` 由文件名反推：`pages/` 下任何文件都归 `pages`，`deck.html` / `notes.html` 归 `deck`，其余是去掉扩展名的那个名字。改了作业就重跑 `check questions`，然后一路往下重跑，不要只补最后一步。

成品对账：`.stamps/deck.json` 不在而 `deck.html` 在、盖章在而文件不见了、或者两个成品文件的哈希对不上，一律判「**成品不是由 `build` 生成或生成后被手改**」。

## 4. 页稿准入（G5）：两道独立的闸

第一道按**原文**做词法预扫，第二道按**解析树**查。两道都过才算通过；`build` 时还会对消毒之后的成品体再扫一遍，免得消毒把问题盖住、也免得消毒本身引进新问题。

### 4.1 词法预扫（看原文）

- 这些标签名一出现就是 ERROR，**连注释与 CDATA 里也不放过**：
  `script` `style` `iframe` `object` `embed` `svg` `math` `link` `meta` `base` `form` `input` `button` `select` `textarea` `template` `frame` `frameset` `applet` `marquee` `audio` `video` `source`。
- `script` 与 `style` 的开闭标签数不配平 → ERROR「未闭合的 `<x>`：成对块没配平」。
- 任何一个 `<…>` 里出现 `on` 开头的事件属性 → ERROR，**用 `/` 当分隔符也算**（`<img src=x/onerror=…>` 是这道闸的经典绕过写法）。

### 4.2 解析树扫描

| 判据 | 结果 |
|---|---|
| 标签不在白名单里 | ERROR |
| 属性以 `on` 开头 | ERROR |
| 属性不在白名单且不是 `data-*` / `aria-*` | ERROR |
| 属性值经归一后以 `javascript:` / `vbscript:` / `data:` 开头 | ERROR（`data:image/…;base64,` 例外） |
| `class` 里出现壳保留类名 | ERROR，见 §6 |
| 出现 `data-page-id` / `data-talk-id` | ERROR，见 §6 |
| 任何属性值里出现外链协议字样（`http://` / `https://` / 协议相对 `//`） | ERROR，判据见 §5（合法 `data:image` 载荷除外） |
| `style` 里的 `url()` | 按危险 URL + 图片来源双重判据，见 §5 |
| `style` 里出现 `expression(` | ERROR |
| `img` 缺 `src`，或 `src` 不合格 | ERROR，见 §5 |
| `figure` 里既没有图也没有说明文字 | ERROR「空 figure」 |
| 正文或讲稿出现占位模式 | ERROR，见 §7 |

**URL 归一口径**：判协议之前先把值里所有空白与 `\x00–\x20`、`\x7f` 控制字符删掉再转小写。所以 `jAvAsCrIpT:`、`java&#9;script:`、带换行的写法都会被折回同一个形态。

### 4.3 消毒（`build` 时）

`build` 逐页做 `sanitize → enforceAccentVar → validate`。消毒会重拼一份只含白名单标签与排版属性的 HTML，顺手把标签配平。准入闸已经把不干净的页拦在外面了，所以正常流程里这一步等于恒等变换；**它真正防的是「一个没闭合的 `div` 把后面几页整个吞进去」这类版面事故。**

单页准入失败**只标页级**：那一页不进成品，报告里记 `failReason`，其余页照出。**全部页都失败才整版失败**，退出 2 且不写 `deck.html`（旧成品也不会被覆盖）。

## 5. 图片：只许 `assets/` 与 data:image

| 写法 | 判定 |
|---|---|
| `src="assets/xxx.png"` | 允许，**且文件必须真实存在**，否则 ERROR「找不到图片文件」 |
| `src="data:image/(png\|jpeg\|jpg\|gif\|webp);base64,…"` | 允许，base64 载荷折算原始字节 **不超过 2 MB** |
| `src="https://…"`、`src="//…"`、`src="../x.png"` | ERROR |
| `style="background:url(assets/x.png)"` | 与 `img` 的 `src` 走**同一套判据** |
| `style="background:url(https://…)"` | ERROR |
| `style="background:image-set('https://…' 1x)"` | ERROR（协议字样判据，与函数名无关） |

外链一旦从 CSS 溜进成品，投屏时就是一次对外请求：教室网络不通就是一块白，更别说它把上课这件事泄露给了第三方。所以 `url()` 与 `src` 同判。

### 外链判据：协议字样出现即拒，不按写法枚举

`url()`、`image-set()`、`cross-fade()`、`-webkit-image-set()`、`image()` 换个函数名就能绕开枚举，所以外链判据不认写法、只认协议字样本身：**任何属性值（`style` 在内）先压掉空白与控制字符、统一小写、抠掉合法 `data:image` 的 base64 载荷，剩下的内容里出现 `http:`、`https:` 或 `//`（协议相对，`http://` 与 `https://` 也都含它）就是 ERROR。**

这条判据刻意从严：CSS 注释里写个网址（`style="/* 见 https://… */color:red"`）同样被拒。属性里没有写网址的正当理由，网址请写进正文文字。合法的 `data:image` 内嵌图不受影响——判定之前它的 base64 载荷已经被抠掉，载荷里恰好出现的 `//` 不会误报。

`build` 之后还会用**同一条判据**把 `deck.html` 与 `notes.html` 的全部属性值再查一遍（G9）。

## 6. 壳保留词：这 13 个类名会被拒收

成品壳自己的结构名。页稿里再用一次，翻页脚本就会把假页当真页数进去——`rail` 上的页码变成 1/4，真页的内容被藏掉。所以**准入阶段直接拒收**，让老师在页稿里改名，而不是等 `build` 报一个看不懂的壳级错误。

| 保留类名 | 壳里干什么用 |
|---|---|
| `slide` | 1280×720 的页容器，翻页脚本按它认页 |
| `pad` | 页内 72/56 边距围出的内容区（1136×608） |
| `fit` | 页内超高时被缩放的那一层 |
| `stage` | `deck.html` 的全屏舞台，负责整页等比缩放居中 |
| `rail` | `deck.html` 右下角的页码 |
| `thumb` | `notes.html` 里 480×270 的页缩略框 |
| `talk` | `notes.html` 里讲稿那一栏 |
| `row` | `notes.html` 里一页一行的那张卡片 |
| `wrap` | `notes.html` 的正文容器 |
| `say` | `notes.html` 里讲稿正文段落 |
| `no` | `notes.html` 里「3 / 9 · p03 · 标题」那一行 |
| `hd` | `notes.html` 页首「教师讲稿 · 不投屏」 |
| `sub` | `notes.html` 页首的副标题行 |

**注意 `row`、`no`、`sub`、`wrap`、`talk` 这几个：它们是最常被随手用作类名的普通英文词。** 写一个两栏表格用 `class="row"`、写一个序号用 `class="no"`、写一个副标题用 `class="sub"`——全都会被拒收。这不是脚本挑剔：这几个名字在壳的 CSS 与翻页脚本里各有确定的含义，页稿里同名的元素会跟着壳的样式跑，或者被脚本当成结构的一部分。

换个名字就行，`cols` / `idx` / `subtitle` 都可以。这一条只管 `class`，**普通的 `data-*` 与 `aria-*` 不受影响**。

另外两个属性同样被保留，页稿里出现即 ERROR：

- `data-page-id`——`deck.html` 每页的标记，`build` 会断言它的出现次数等于成品页数。
- `data-talk-id`——`notes.html` 每行的标记。

## 7. 占位模式：正文与讲稿都不许有

命中任一即 ERROR。ASCII 的四条不区分大小写、按词边界匹配：

```
TODO      TBD      placeholder      lorem ipsum
```

中文六条按子串匹配：

```
此处插图    待补图    此处配图    待补充    [图]    ［图］
```

理由很直接：这些字样进了成品，就是老师站在讲台上、投影仪已经亮着的时候才发现这一页还没写完。**没想好就把那一段删掉，别留个记号。**

## 8. 讲稿（G6）与覆盖（G7）

### 8.1 讲稿

| 判据 | 阈值 | 级别 |
|---|---|---|
| 讲稿非空 | —— | ERROR |
| 讲稿里不许出现 HTML 标签 | 按已知标签名匹配（`a<b 且 b>c` 这类不等号不会误伤） | ERROR |
| 讲稿出现占位模式 | 见 §7 | ERROR |
| **单页讲稿字数 ≥ 该页正文去标签字数** | 比值 | ERROR |
| **全课讲稿总字数 ≥ `minutes × 60`** | `TALK_PER_MINUTE = 60` | ERROR |
| 讲稿与本页正文的 2-gram 重合率 | **> 0.80** → 「抄正文当讲稿」 | ERROR |

`minutes × 60` 的口径：语速按 150 字/分算，讲稿覆盖其中四成，余下六成留给活动、提问与板书。45 分钟的课就是 2700 字。

重合率的分母**取短的那一边**——正文被整段抄进讲稿时比值正好是 1.00，这正是要抓的形态。

### 8.2 覆盖

| 判据 | 阈值 | 级别 |
|---|---|---|
| 每道题至少被一页 `covers` | —— | ERROR，逐题点名 |
| 单页 `covers` 条数 | **≤ 3** | ERROR |
| 题干实词与其覆盖页（正文＋讲稿）的实词重合 | **≥ 2** | ERROR「页里没讲到这道题」 |
| choice 题正确项文本的实词出现在覆盖页 | 至少 1 个 | WARN |

覆盖矩阵（行＝题、列＝页、格＝重合实词数）会写进报告：哪道题没被讲到，红着摆在表里。

## 9. 实词与 2-gram 的口径

两套口径，用在不同地方，别混：

**`units()`——字数与 2-gram 的共同底座**：中文按**字**、英文按**词**，数字与标点一律丢掉。`bigrams()` 就是这串单位里相邻两项的集合。「讲稿字数」「正文字数」「重复题重合率」「抄正文重合率」都建在它上面。

**`content_words()`——实词集合**，只用于覆盖判据与「阶段 summary 是否呼应目标」：

- 中文：先把高频虚词从每段汉字里挖掉，剩下的连续片段取全部 **2-gram**。
- 英文：取长度 ≥ 2 的字母串、转小写、去 stopwords。
- 数字与标点：丢掉。

中文虚词表（逐字，改一个字就要同 commit 改脚本与 selftest）：

```
的了和与或是在有不也就都而及之其这那个为以对于从被把让使会要可应该
我你他她它们吗呢吧啊呀但却则因所由向并且又再还只若请各每些什么很更最等如
```

英文 stopwords 表：

```
a an the and or but if of to in on at for
with by from as is are was were be been being
do does did have has had it its this that these
those you your we our they their he she his her
not no so than then there here what which who how
why when where can could will would should may might
must shall also about into over under between during
such some any all each more most other only own
same too very up down out off again further because
while after before above below both few nor just now
```

### 语言口径的一句实话

`units()` 里**一个汉字算一个单位、一个英文单词也算一个单位**。所以凡是拿常量去比计数的闸门，**在英文课上实际更严**：

- `prompt` 至少 10 —— 中文是 10 个字，英文是 **10 个词**，后者要求的信息量大得多。
- 阶段 `summary` 至少 20 —— 中文 20 字是一句话，英文 **20 个词**是两三句。
- 全课讲稿 `minutes × 60` —— 45 分钟课的 2700，中文是四成语速的合理值，英文 **2700 个词**按 130 词/分算已经超过 20 分钟的净讲话量。

反过来，**上限类阈值在英文课上更松**：单页正文 350 这个 WARN 线，中文是 350 字（接近满版三分之一），英文是 350 个词（早就装不下了）。所以英文课请以「投影出来看得清吗」为准，别指望密度闸替你把关。

这两个方向的偏差都还没有跨模型实测数据支撑，属于待回调项；一旦回调，`scripts/lessonkit.py` 常量区、这份文档与 `scripts/selftest.py` 必须同 commit 一起改。

## 10. 阈值清单（逐条，与常量区一一对应）

| 常量 | 值 | 管什么 | 越界 |
|---|---|---|---|
| `MINUTES_SOFT` | 10–180 | `lesson.minutes` | 之外 WARN |
| `QUESTION_RANGE` | 3–20 | 题目数量 | 之外 ERROR |
| `KIND_CAP` | 10 | 每种 `kind` 的题数 | 超过 ERROR |
| `PROMPT_MIN` | 10 | 题干字数（中文按字／英文按词） | 不足 ERROR |
| `CHOICE_RANGE` | 2–6 | choice 题的选项数 | 之外 ERROR |
| `FOCUS_CAP` | 5 | `focus` 条数 | 超过 ERROR |
| `DUP_PROMPT_RATIO` | 0.6 | 两题 `prompt` 的 2-gram 重合率 | 超过 WARN |
| `PHASE_SOFT` | 2–6 | 阶段数 | 之外 WARN |
| `PHASE_HARD` | 10 | 阶段数硬上限 | 超过 ERROR |
| `SUMMARY_MIN` | 20 | 阶段 `summary` 字数（中文按字／英文按词） | 不足 ERROR |
| `MINUTES_DRIFT` | 0.10 | 各阶段 `minutes` 之和与课时的偏差 | 超过 WARN |
| `PAGE_SOFT` | 3–20 | 页数 | 之外 WARN |
| `PAGE_HARD` | 30 | 页数硬上限 | 超过 ERROR |
| `COVERS_CAP` | 3 | 单页 `covers` 条数 | 超过 ERROR |
| `OVERLAP_MIN` | 2 | 题干实词与覆盖页的重合数 | 不足 ERROR |
| `DENSITY_WARN` | 350 | 单页正文去标签字数 | 超过 WARN |
| `DENSITY_HARD` | 1000 | 单页正文去标签字数 | 超过 ERROR |
| `TALK_PER_MINUTE` | 60 | 全课讲稿字数下限系数 | 不足 ERROR |
| `COPY_RATIO` | 0.8 | 讲稿与本页正文的 2-gram 重合率 | 超过 ERROR |
| `SAT_WARN` | 0.25 | `style` 里非八色 hex 的 HSL 饱和度 | 超过 WARN |
| `IMG_CAP` | 2 MB | 内嵌 data:image 的原始字节 | 超过 ERROR |

**密度阈值的口径**：内容区 1136×608，字号 20px、行高 1.6 ≈ 每行 32px ≈ 19 行，每行约 56 个汉字，满版约 1060 字。所以 350 字是「开始要靠缩放了」，1000 字是「缩到最小也读不清」。这是按 CSS 推算的启发式：**真正不溢出由壳的运行时缩放保证，而最小缩放 0.5 之下仍会被裁**，见 `references/shell-contract.md`。

## 11. 主题色：一律 `var(--accent)`，不写死非中性色

八个主题色 key 与 hex（未知 key 回落 `cyan` 并给 WARN）：

| key | hex | key | hex |
|---|---|---|---|
| `cyan`（默认） | `#0891b2` | `violet` | `#7c3aed` |
| `indigo` | `#4f46e5` | `slate` | `#475569` |
| `emerald` | `#059669` | `teal` | `#0d9488` |
| `amber` | `#d97706` | `rose` | `#e11d48` |

- 壳里 `h1` / `h2` / `th` / `blockquote` **默认就吃 `var(--accent)`**，纯文本页什么都不用写就会跟着换色。
- `build` 会把页稿里写死的**八色任一 hex（大小写不敏感）自动换回 `var(--accent)`**——否则 `repalette` 就是空转。
- `style` 里出现不在八色表内、且 HSL 饱和度 > 0.25 的 hex → WARN「主题色一律走 `var(--accent)`」。中性灰不报。
- 一页里既没有 `h1` / `h2` / `h3` / `th` / `blockquote`、也没有用 `var(--accent)` → WARN「本页换色无可见变化」。

`repalette <slug> --palette <key>` 只重拼成品：跑完 `pages/` 下每个文件的哈希必须逐字节不变，变了脚本会自己报成 bug。

## 12. 编程题：转调 coding-drill 的老师模式

**本 Skill 不出编程题、不判编程题。** 这节课要留编程作业时：

1. 用 coding-drill 的老师模式把那道题出出来，得到一个 `<slug>`。
2. 在需要讲到它的那一页，把 `covers` 写成 `["drill:<slug>"]`。

`lessonkit.py` **只校验 `drill:<slug>` 的形态**（小写字母、数字、连字符，不超过 64 位），不会去调用 coding-drill 的判题脚本，也不会把它算进覆盖矩阵。两边是文档约定，不是代码依赖。

形态写错（`drill:` 后面为空、带大写、带斜杠）会是 ERROR。

## 13. 门禁（必须遵守）

- **没过 `check` 不许进下一步。** 撞上锁时脚本退 2，那是流程还没走到，不是环境坏了。不要绕过它，也不要先写下一步的草稿「等着补」。
- **不许手写、手改 `deck.html` 与 `notes.html`。** 页稿是唯一的 source of truth，成品只能由 `build` 派生。手改会被 `.stamps/deck.json` 的哈希当场对出来。
- **单页 `covers` 不许超过 3 道题。** 一页贴上四道题，就是在用标签冒充讲过了。
- **不许把正文复制成讲稿。** 讲稿是讲台上说的话，正文是投影上写的字，两者本来就该不一样。2-gram 重合超过 0.8 直接判死。
- **不许写占位图说明。** 「此处插图」这种字样一律 ERROR，见 §7。
- **`check` 报 ERROR 时改产物，不要改脚本。** 闸门是这份 Skill 唯一的价值；为了让某一页过关去调阈值，等于把它扔了。
- **报告由脚本渲染，模型不写报告。** `report.md` 与 `report.html` 里的每个数字都来自这一次体检，手写一份「看起来差不多」的报告就是在骗老师。
- **编程题转调 coding-drill 的老师模式**，在 `covers` 里以 `drill:<slug>` 引用，见 §12。
- **改了上游就一路重跑。** 改了作业，`check questions` → `check phases` → `check pages` → `build` 全部要重来，不要只补最后一步。
