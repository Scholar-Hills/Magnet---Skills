# 课目录与脚本契约

这份文件是文档、`scripts/lessonkit.py` 与 `scripts/selftest.py` 三方共享的约定。**改契约就要在同一个 commit 里改脚本与自测，反之亦然。**

阈值一律以 `scripts/lessonkit.py` 顶部常量区为准，本文里出现的每一个数字都是从那里抄下来的；口径解释见 `references/workflow-rules.md`，成品壳的保证见 `references/shell-contract.md`。

## 1. 目录布局

一节课就是 `lessons/<slug>/` 一个目录。`lessons/` 建在**老师的工作区**里（不是 Skill 目录），`lessonkit.py --root <工作区>` 指的就是 `lessons/` 的父目录。

```
lessons/<slug>/
  lesson.json            课纲卡：课题、课时、学习目标、知识点、路线（第 1 步）
  questions.json         作业：3–20 道题（第 2 步）
  phases.json            阶段：2–6 段（第 3 步）
  pages/
    index.json           页的顺序表：id / phase / covers / title
    <id>.html            投屏正文，白名单 HTML 片段（不是整页文档）
    <id>.notes.md        教师讲稿，纯文本（第 4 步）
  materials/             老师自带的课文、材料；lesson.json 的 materials.path 指到这里
  assets/                页稿里 img 唯一允许的本地图片目录
  deck.html              成品投屏文件，只能由 build 产出
  notes.html             成品讲稿文件，只能由 build 产出，绝不进投屏
  report.md / report.html  验收报告，只能由 report 产出
  .stamps/               盖章：lesson / questions / phases / pages / deck / checks
```

`init <slug>` 会建出 `pages/`、`assets/`、`materials/`、`.stamps/` 四个子目录和一份 `lesson.json` 骨架。**`deck.html`、`notes.html`、`report.*`、`.stamps/*` 全部由脚本落盘，任何情况下不要手写、不要手改。**

`<slug>` 与所有 `id`（题、页）走同一条正则：小写字母、数字与连字符，首字符不能是连字符，长度不超过 64。

## 2. `lesson.json`（第 1 步 · G1）

```json
{
  "title": "城市为什么需要湿地",
  "minutes": 45,
  "goals": ["用自己的话说出湿地的定义，并举出城市里三种常见的湿地"],
  "keyPoints": ["削平洪峰：暴雨时存水、雨停后慢放"],
  "audience": "初中二年级，一个班约四十人",
  "materials": [{"name": "课文《城市为什么需要湿地》", "path": "materials/wetland-text.md"}],
  "route": "homework-first",
  "language": {"slides": "中文", "notes": "中文"}
}
```

| 键 | 必填 | 契约 |
|---|---|---|
| `title` | 是 | 非空字符串。成品与报告的标题都取它 |
| `minutes` | 是 | 正整数，课时分钟数。不在 10–180 之间只给 WARN，不拦 |
| `goals` | 见下 | 学习目标数组，题与阶段用 `g<序号>` 引用（`g1` 是第一条） |
| `keyPoints` | 见下 | 核心知识点数组，用 `k<序号>` 引用 |
| `audience` | 否 | 自由文本，脚本只透传 |
| `materials` | 否 | 数组，每条要么 `{name, path}`、要么 `{name, excerpt}` |
| `route` | 否 | `homework-first`（默认）或 `content-first`，见 workflow-rules §2 |
| `language` | 否 | 对象，只认 `slides` 与 `notes` 两个键，值是自由文本 |

- **`goals` 与 `keyPoints` 不能同时为空** —— 两个都空就没有出题依据，这条是 ERROR，后面几步都不用跑。
- `materials[].path` 相对课目录解析，脚本按 `<课目录>/<path>` 与 `<课目录>/materials/<path>` 两种方式各找一次，都不在就是 ERROR；`..` 与以 `/` 开头会被当场拦下。没有文件的材料写 `excerpt` 贴一段原文。
- `language` 只是写给你和老师看的，**脚本不预设任何语言政策**：投屏用什么语言、讲稿用什么语言，由老师在这里自己填，脚本不会因为它改变任何判定。多写的键给 WARN。

## 3. `questions.json`（第 2 步 · G2）

顶层是数组，3–20 道题。

```json
[
  {"id": "q1", "kind": "choice",
   "prompt": "下面哪一项最接近课文里对湿地的说法？",
   "choices": ["常年或季节性积水……", "城市里一切没有铺上水泥的空地", "……", "……"],
   "correct": [0],
   "focus": ["积水", "耐水植物", "水陆过渡"],
   "targets": ["g1"]},
  {"id": "q3", "kind": "short",
   "prompt": "一股带着泥沙和氮磷的雨水流进湿地，到再流出去为止，先后发生了哪几件事？",
   "focus": ["流速变慢", "泥沙沉降", "氮磷被吸收转化"],
   "targets": ["g2", "k2"]}
]
```

| 键 | 必填 | 契约 |
|---|---|---|
| `id` | 是 | slug 规则，全卷唯一 |
| `kind` | 是 | `choice` / `short` / `extended` 三选一；每种最多 10 道 |
| `prompt` | 是 | 题干，至少 10 字（中文按字、英文按词） |
| `choices` | choice 必填 | 2–6 项。非 choice 题带上它只给 WARN |
| `correct` | choice 必填 | 正确项**下标**数组，非空、下标合法，且不能占满全部选项 |
| `focus` | 否 | 最多 5 条考点短语。它是考点，**不是评分标准** |
| `targets` | 是 | 非空，每项写成 `g<序号>` 或 `k<序号>`，序号必须在课纲卡里存在 |

- 备课线**不产评分标准**。`short` / `extended` 只给题干和 `focus`，不带答案、不带打分细则；判分是批改线的事。
- `correct` 里若下标覆盖了全部选项，是 ERROR：那样学生没得选。
- 两题 `prompt` 的 2-gram 重合率超过 0.6 会给 WARN「疑似重复题」。
- 每条 `goals` 至少要被一道题的 `targets` 命中，否则逐条 WARN。
- 通过后写 `.stamps/questions.json`。

## 4. `phases.json`（第 3 步 · G4）

顶层是数组，2–6 段（之外 WARN，超过 10 段是 ERROR）。

```json
[
  {"title": "蓄水与净化",
   "summary": "顺着一场暴雨走一遍：先看管网为什么来不及，再看湿地怎样把水暂时存住……",
   "goals": ["g2", "k1", "k2"],
   "minutes": 18}
]
```

| 键 | 必填 | 契约 |
|---|---|---|
| `title` | 是 | 非空、两两不同，**不许带编号前缀**（见下） |
| `summary` | 是 | 至少 20 字，说清这一段在做什么 |
| `goals` | 是 | 非空，`g<序号>` / `k<序号>`，序号必须存在 |
| `minutes` | 否 | 正整数。若有任一阶段写了，各段之和与 `lesson.minutes` 相差超过 10% 给 WARN |

- **编号前缀一律拦下**：`第一阶段`、`第 2 讲`、`1.`、`一、`、`（3）`、`Phase 1`、`Step 2`、`Part 3`、`Unit 1` 这些写法都是 ERROR。顺序由数组本身表达，写进标题只会在改动顺序时变成错的。写纯阶段名就行。
- **每条 `g<n>` 学习目标至少要被一个阶段的 `goals` 引用**，否则逐条 ERROR「目标无阶段承接」。`k<n>` 不作硬要求。
- `summary` 与它承接的目标文本零实词重合会给 WARN。
- 阶段标题同时是 `pages/index.json` 里 `phase` 字段的取值，**改阶段名等于改页的归属**，改完要从 `check <slug> phases` 重新验收。
- 通过后写 `.stamps/phases.json`。

## 5. `pages/index.json` 与页稿（第 4 步 · G5–G7）

`index.json` 是**顺序数组**，投屏的翻页顺序就是它的顺序。页数 3–20 之外给 WARN，超过 30 是 ERROR。

```json
[
  {"id": "p05", "phase": "蓄水与净化", "title": "湿地像一块海绵", "covers": ["q2"]},
  {"id": "p09", "phase": "栖息地与取舍", "title": "为什么容易被填掉", "covers": ["q6", "q7"]}
]
```

| 键 | 必填 | 契约 |
|---|---|---|
| `id` | 是 | slug 规则，唯一。同时决定 `pages/<id>.html` 与 `pages/<id>.notes.md` 的文件名 |
| `phase` | 是 | 必须**逐字**等于 `phases.json` 里某个 `title` |
| `covers` | 否 | 这一页要讲到的题 id，最多 3 个；也可以写 `drill:<slug>`。缺省与空数组等价，**但每道题都必须被某一页认领**，所以全课不可能每页都空 |
| `title` | 否 | 页名。只出现在 `notes.html` 的行首，不进投屏 |

- **每个阶段至少要有一页**，否则 ERROR。
- `covers` 里的 id 必须在 `questions.json` 里存在；`drill:<slug>` 形态的编程题引用**只校验形态**，脚本不会去调用 coding-drill，见 workflow-rules §12。
- **单页 `covers` 最多 3 个**。一页塞进四道题是「贴标签蒙混」最常见的形态，直接 ERROR。

### `pages/<id>.html` —— 投屏正文

是一个 **HTML 片段**，不是整页文档：不要写 `<!DOCTYPE>`、`<html>`、`<head>`、`<body>`，壳会把它包进 `.slide > .pad > .fit` 三层里。

允许的标签只有这些：

```
h1 h2 h3 p ul ol li
table thead tbody tfoot tr td th caption colgroup col
blockquote div span strong em code pre
figure figcaption img br hr
```

允许的属性：`class` `id` `style` `alt` `src` `width` `height` `colspan` `rowspan` `scope` `lang` `dir` `title` `span`，另加任意 `data-*` 与 `aria-*`（两个壳保留的 data 属性除外，见下）。

准入的完整规则（白名单外标签、`on*` 事件、危险 URL、图片来源、壳保留词、占位模式、密度上限）写在 `references/workflow-rules.md` §4，那里是唯一权威。

### `pages/<id>.notes.md` —— 教师讲稿

**纯文本**，讲台上照着念的话。不许出现 HTML 标签。字数下限、不许抄正文的判据同样见 workflow-rules §8。

讲稿只进 `notes.html`，`build` 会断言每页讲稿的前 40 字不出现在 `deck.html` 里。

- 通过后写 `.stamps/pages.json`（含 `index.json` 与每一页的两个文件的哈希）。

## 6. 盖章 `.stamps/`

| 文件 | 由谁写 | 记了什么 |
|---|---|---|
| `lesson.json` | `check <slug> lesson` | `lesson.json` 的 sha256 + ISO 时间 |
| `questions.json` | `check <slug> questions` | 本步与全部上游文件的 sha256 |
| `phases.json` | `check <slug> phases` | 同上 |
| `pages.json` | `check <slug> pages` | 同上，含 `pages/` 下每一个文件 |
| `deck.json` | `build` | 上游全部文件 + `deck.html` + `notes.html` 的哈希，另记 `palette`、`readyPages`、`failedPages` |
| `checks.json` | `report` | 这一次体检的四步状态、三把锁、成品对账、逐条结果 |

盖章的结构是 `{"step": …, "at": ISO 时间, "hashes": {文件名: sha256}}`。下游 `check` 先比对上游哈希，对不上就是 ERROR「**`<文件>` 已改动，请从 `check <step>` 重新验收**」——`<step>` 由文件名反推：`pages/` 下的任何文件都归 `pages`，`deck.html` 与 `notes.html` 归 `deck`，其余就是去掉扩展名的那个名字。

`check <slug> --all` 会把四步重跑一遍并重新盖章，再拿 `.stamps/deck.json` 对一次成品：`deck.html` 或 `notes.html` 的哈希对不上，或者根本没有这张盖章而文件却在，都判「成品不是由 `build` 生成或生成后被手改」。

## 7. 成品与报告

- `deck.html`：单文件、自包含、无外链、恰好一个 `<script>`（翻页与缩放），每页一个 `<section class="slide" data-page-id="…">`。壳的保证见 `references/shell-contract.md`。
- `notes.html`：每页一行，左边是同一页缩到 480 宽的缩略、右边是讲稿，页首固定写着「教师讲稿 · 不投屏」，带打印 CSS，**不含任何脚本**。
- `report.md` / `report.html`：四步状态条、三把锁与锁的原话、题↔页覆盖矩阵、目标↔阶段表、每页讲稿字数与正文密度、失败页、逐条 ERROR / WARN、页脚的 G0 分类声明。**报告全部由脚本渲染，模型不写报告。**

## 8. 命令行契约

```
lessonkit.py [--root <工作区>] <子命令> …
```

| 子命令 | 作用 |
|---|---|
| `doctor` | Python 版本、壳参数、八色表、工作区、发布卫生自检 |
| `init <slug> [--route homework-first\|content-first]` | 建课骨架 |
| `check <slug> <lesson\|questions\|phases\|pages>` | 验收某一步，过了就盖章 |
| `check <slug> --all` | 四步复核 + 成品哈希对账 |
| `build <slug> [--palette <key>]` | 从 `pages/` 派生 `deck.html` 与 `notes.html` |
| `repalette <slug> --palette <key>` | 只换主题色重拼，页稿逐字节不动 |
| `report <slug>` | 渲染 `report.md` 与 `report.html` |

`<slug>` 里带路径分隔符时按路径直接解析（`check examples/lessons/city-wetland --all` 这种写法可用）；`init` 只收纯 slug。

**退出码**：`0` 通过 ／ `1` 闸门不过（有 ERROR）／ `2` 用法、环境或锁。

`2` 里最要紧的是**锁**：撞上锁时脚本打印「锁住了：<该先跑哪一条>」并退 2，这不是 bug，是流程还没走到。
