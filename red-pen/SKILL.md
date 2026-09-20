---
name: red-pen
description: 红笔改稿——把一段稿子（公众号推文、周报、邮件、说明文档）交给它，先问清给谁看、要达到什么、最怕什么，再逐句批注：哪一句有问题、为什么、怎么改。批注由脚本钉回原文，钉不住的老实标成「未能定位」，绝不硬贴；稿子一个字都不改，也不给整段重写。产出一页可截图的红笔稿。Use when the user wants feedback on a draft, an article, a newsletter, a report or an email, wants line-level editorial comments anchored to the original text, or wants to compare a revised draft against the previous round of comments.
license: MIT
allowed-tools: Bash, Read, Write, Edit
---

# 红笔改稿（red-pen）

一句话：**它只在稿子边上写字。** 每条批注必须指向原文里真实存在的一句话，脚本负责把它钉回去；钉不住的老实标成「未能定位」，不擅自摆放。改法只针对被引的那一句——`fix` 加起来超过稿子的一半（短稿至少给到 60 字）就会被拒收。这是长度约束，不能识别所有整段或整篇短稿重写，过闸后仍须遵守不代笔的纪律。

## 你能对它说什么

| 你说 | 它做 |
|---|---|
| （丢一段稿子）「帮我看看」 | 先问三个问题（给谁看 / 要达到什么 / 最怕什么），再批 |
| （丢稿子 + 说明在意什么） | 直接写进 brief，跑一轮批注，交一页红笔稿 |
| 「这条我不同意」 | 讨论，改 `inbox/marks.json` 重跑；稿子不动 |
| 「你直接帮我改好一版发我」 | 不写。说清红笔只给逐条批注和针对那一句的短改法，你改完再交回来看下一版 |
| （自己改完稿）「再看一遍」 | 收成新一版，重新批，并报出「上一版的 N 条这次消失了」 |
| 「哪几条没定位」 | 念「未能定位」那一节，说明脚本为什么不摆它 |

## 前置检查（不可跳过）

0. **定位脚本**。本 Skill 的脚本在 Skill 目录下，不在用户工作区。按顺序找 `red-pen/scripts/redpen.py`，取第一个存在的绝对路径记作 `REDPEN`：
   ① 这份 SKILL.md 所在目录下的 `scripts/redpen.py`（你就是从那个目录读到本文件的）；② Claude Code：`~/.claude/skills/red-pen/`、当前项目 `.claude/skills/red-pen/`；③ WorkBuddy / CodeBuddy：`~/.workbuddy/skills/red-pen/`、`~/.workbuddy-ai/skills/red-pen/`、`~/.codebuddy/skills/red-pen/`、当前项目 `.codebuddy/skills/red-pen/`；④ OpenClaw：`~/.openclaw/workspace/skills/red-pen/`；⑤ 小红书 `redskill install` 的默认位置：当前目录 `./skills/red-pen/`；⑥ 用户在对话里指定的目录；⑦ 都没有就搜一次：`find . ~/.claude ~/.workbuddy ~/.workbuddy-ai ~/.codebuddy ~/.openclaw -path '*red-pen/scripts/redpen.py' 2>/dev/null | head -1`。
   本文后面所有 `python3 scripts/redpen.py …` 都读作 `python3 "$REDPEN" …`，并且始终在用户工作区（`drafts/` 的父目录）下执行：`cd <工作区> && python3 "$REDPEN" review <slug>`。
   **七处都找不到就立即停止**，告诉用户「这份 Skill 的改稿脚本缺失，请重新下载完整目录」。**任何情况下都不要自己写一个替代脚本**，也不要「先手工批一版」——手写的批注没有锚定与闸门，会把钉不住的引文当成原文摆给用户看，那正是这份 Skill 存在的理由。
1. 运行 `python3 "$REDPEN" doctor`。`python3` 不存在就试 `python`（Windows 常见）；两个都没有，告诉用户先装 Python 3.8+，不要继续。
2. 稿子都放在**当前工作区**（用户项目或文稿目录，不是 Skill 目录）的 `drafts/` 下。第一次收稿前先 `pwd` 看一眼：如果当前目录是家目录、桌面或其它不像工作目录的地方，先问用户一句「稿子和批注我打算放在 `<当前路径>/drafts/`，可以吗？想换个地方现在告诉我」。定下来之后就别再换——同一篇稿子的历轮批注要在同一处才比得出来。
3. **`--root` 是顶层选项，必须写在子命令前面**：`python3 "$REDPEN" --root <工作区> review <slug>` 对，`… review <slug> --root <工作区>` 会报错。默认值是当前目录，所以只要你已经 `cd` 进工作区，就不用加这个选项。子命令的位置参数也别写反：`brief set <slug> --from <文件>`（`set` 在 slug 前面），`init <slug> --from <稿子>`。
4. 第一次用之前，翻一眼 Skill 目录里 `examples/drafts/newsletter-01/` 这个示例工作区：`inbox/marks.json` 是提交的样子，`marks.json` 是过闸之后的样子，`review.html` 是交付的样子。照着它写比照着文字描述不容易出错。

**回复语言跟随用户**：用户用中文就全程中文，用英文就全程英文，不要中英混着来。这与 `brief.json` 里的 `lang` 是两件事——`lang` 指的是写进批注里的语言。

## 流程

格式契约以 `references/workspace-format.md` 为准，纪律以 `references/rules.md` 为准，**先读这两份**再动手。

**动手前先说一句**：「我来逐句批一遍。批注会由脚本钉回原文，钉不住的我会老实标出来，不给你整段重写——对话里也不写。稿子我一个字都不动。」非交互场景（批处理、子任务）就把这句写进最终报告的开头。

### 1. 收稿

用户给的是文件就用原文件路径（`.md` / `.html` / `.txt` / `.docx` 都收），然后：

```
python3 scripts/redpen.py init <slug> --from <稿子文件>
```

`<slug>` 用小写英文加两位序号，能看出是哪篇（如 `newsletter-01`）。同一篇稿子的新版本用**同一个 slug 再跑一次** `init`，脚本会把上一版整个归进 `history/v<N>/`。稿子没改就跑不出新版本，脚本会直接说（目标后缀也须相同）。

只有用户把稿子贴在对话里时，才用 `init <slug> --from -`，把原文原样送入标准输入；它统一存成 `draft.txt`，与文件走同一准入与解码通道，不另加格式选项。用户给的是文件就用路径，不能拿标准输入绕过格式拒收。

原稿先认 BOM，再试严格 UTF-8，最后只猜一次 GB18030（兼容 GBK）；脚本会说明猜测并打印开头两行，**读出来是乱码就停下，不要接着批**。brief 与批注 JSON 仍须严格 UTF-8。PDF、旧 Word、RTF、ODT、表格、演示、图片、压缩包等会被拒收，照脚本给的办法导出正文再来。

DOCX 表格按行读出、整行可以整句引，跨行引不了；一格多段用空格相连。文本框按位置读一次，图片不做文字识别，普通文字图注仍会读到；修订只按正文文字节点读取，不替用户处理修订，也不读 Word 批注。**脚本会按这份文档实际结构打印提醒，你把它原样转述**，别让用户以为批到了图片里的字。

### 2. 问清标准，写进 brief

用户丢稿时如果已经说了在意什么（「太啰嗦」「怕像广告」「投给同行看」），直接整理进 brief。**没说就先问这三个问题**，问完再批：

1. **给谁看？**——同行、客户、家长、老板，还是完全不认识的人？在什么场合读（手机上划过、坐下来细读、开会前扫一眼）？
2. **要达到什么？**——读完之后你希望他做什么、记住什么、改变什么看法？
3. **最怕什么？**——最怕被读成什么样（推销、说教、含糊、没依据）？

三个问题一次问完，不要一条一条挤牙膏。`init` 不会替你猜批语语言，按用户要求把 `lang` 写进 brief。答案写成 JSON 交进去：

```
python3 scripts/redpen.py brief set <slug> --from <brief.json>
```

`brief.json` 只认 `audience` / `purpose` / `worries` / `lang` 四个键。**brief 进 `context_hash`**：之后再改 brief，之前的批注就全作废，要重跑 `context`。

用户不愿意回答就照默认批，但要说一句「没有标准我只能按通用文章的标准挑毛病，有些意见可能不合你的场合」——不要自己替他编一个受众填进去。

### 3. 拿上下文包

```
python3 scripts/redpen.py context <slug>
```

它打印一份 JSON：`draft_text`（脚本抽出来的纯文本，**你批的就是这一份**）、`brief`、`version`、`context_hash`。

**批注只许照着 `draft_text` 里的句子引。** 不要照着用户在对话里贴的原文引——两者可能差一个空格或一个标点，钉不住。`context_hash` 从这份输出里原样取，不要自己算、不要手抄。

哈希对得上只说明稿子和 brief 没换过，**不说明你读过这份 `draft_text`，也不说明引文抄对了**——那两件事得靠下一步自己核。

### 4. 写批注

把批注写进 `drafts/<slug>/inbox/marks.json`：

```json
{
  "context_hash": "（从上一步的输出里原样取）",
  "marks": [
    {"quote": "问不清楚的先不报",
     "level": "major",
     "note": "这是全篇最能直接照做的一句，却被塞在长句尾巴上，手机上一划就过去了。",
     "fix": "拎出来单独成段，前面加一句「这条最省钱」。"}
  ]
}
```

写的时候盯住这几条（完整闸门见 `references/rules.md`）：

- **`quote` 从 `draft_text` 里一字不差地抄**，包括标点。用户在对话里贴过的那一版不算数——同一句话在对话里和 `draft_text` 里常差一个字或一个标点。不许顺手润色引文；脚本保留规范化与头尾锚定兜底，定位成功也不能代替逐字核对。引一句就够，不要整段抄（上限 200 字，且原串不超过 400 个字符）。不要引横跨两个段落的句子——脚本不做跨块锚定。
- **`level` 只有三档**：`major`（不改会出问题）、`minor`（改了更好）、`remark`（一点想法）。写别的会被改判成 `remark`。
- **`note` 说清这一句出了什么问题**，至少 6 个字（英文按词算，就是六个词）。不要写「不好」「再改改」，也不要在这里给稿子打分。
- **`fix` 可选，只针对被引的那一句**：给方向、给一个可以照抄的短句。不超过预算——引文字数 × 3，最少 20 字、最多 40 字；也不能与引文相同。不给改法就把这个键去掉，别留空串。
- **不替用户编事实**：稿子里没写、你也无从知道的具体信息（时间、地点、报名方式、数字、谁说过什么）不能当成确定的事写进 `fix` 或 `note`。需要这类信息就在 `note` 里问一句，或者把 `fix` 写成条件句、留一个让用户自己填的空。
- **一条批注一个毛病**：两条引文相同、或两条批语相同，整份会被拒收。
- **从头批到尾**：批注全挤在开头 20% 的篇幅里会被提醒（稿子分得出三块时才提醒）。
- 顶层只认 `context_hash` 与 `marks`，单条只认 `quote` / `level` / `note` / `fix`。不要自己另造键名，也不要塞分数、总评、标签。

**交进去之前，逐条对一次来源**：拿这一轮 `context` 输出里的 `draft_text`，把每条 `quote` 原样搜一遍，确认它在这份文本里逐字出现。搜不到，或者说不清是从哪一句抄来的，就当它来路不明——记不清不等于它一定抄自对话，但一样不能这么交。

对不上的那条**回 `draft_text` 里把那一句重抄一遍**：改的只是抄错的字，批的仍是同一个问题、同一处原文。批的是两段接不上，就把引文挪到 `draft_text` 里那个接口上真实存在的那一句，`note` 跟着改成针对这一句。**不许换成另一句去批另一个问题**，不许凭感觉改两个字凑上去，不许靠删掉它把问题盖过去，更不要动稿子。

### 5. 过闸

```
python3 scripts/redpen.py review <slug>
```

退出 0 才算数。它会打印批注条数、锚定率、等级分布，并写出 `marks.json`、`review.html` 与 `history/review-NNNN.json`。

**退出 1 就照着报出来的原因改 `inbox/marks.json`，一条一条改，然后重跑。** 每轮说一句「第 N 轮没过：＜哪条闸门＞，我把＜哪几条＞改了再试一次」，不要静默重试。锚定率不够时要做的是**回 `draft_text` 里重新抄一遍那几条引文**，不是删掉它们凑比例。

报出来的未定位条目要一条条看来源：抄错了就回 `draft_text` 重抄。确实是从 `draft_text` 逐字抄下来的（最常见是那一句横跨了两个段落），就看这一轮的结果：`review` 已经退出 0 的，照实留着，交付时报成未定位；还卡在退出 1 的，把跨块那几条缩到其中一段再重跑（`references/rules.md` 闸门三是这个口径），批的仍是同一个问题、同一处原文——缩不动就照实说这一轮没过闸、卡在哪几条，**不交半成品**，也不拿另一句顶上去凑比例。反过来也要留神：**锚定率过线不代表每条引文都抄对了**，它只说明钉住的够多。

### 6. 交付

只有 `review` 退出 0 之后才把结果给用户。交付时说清三件事：

1. **红笔页在哪**：`drafts/<slug>/review.html`，用浏览器打开可以直接截图；左栏原文带下划线，右栏按编号列批注。
2. **锚定率**：「7 条批注钉住 6 条（86%）」。**条数一律以 `marks.json` 里的 `marks` 为准**——一条批注在正文里可能画成好几段下划线（引文横跨行内标签时），数页面上的下划线会数多。
3. **未定位的条目**：逐条把引文和批语念给用户听，并说明「这一句我在稿子里没找到，脚本不擅自摆放，请你自己对一下位置」。不要把它当成正常批注混在里面报。

对话里可以挑两三条最要紧的展开讲，但**不要把整份批注复述一遍**——用户打开红笔页看得更清楚。

### 7. 用户改完，再看一版

用户改完稿子交回来：`init <slug> --from <新稿>`（同一个 slug）→ `context` → 写批注 → `review`，然后：

```
python3 scripts/redpen.py stats <slug>
```

它会报「上一版 N 条批注里有 M 条在新稿里消失了」，并列出消失的那几条。把这句原样转述给用户——**消失的条目就是这一轮真正改动到的地方**，这比对着两版稿子凭感觉说「改得不错」有用得多。还在的那些也要说一句：要么还没改，要么改动没碰到这些句子。

## 门禁（必须遵守）

- **不改用户的稿子。** `draft.*` 从 `init` 落地就是只读的。批注不合格就改 `inbox/marks.json`，永远不是改稿子去迁就批注。用户要改稿让用户自己改。
- **不给整段重写——写在哪儿都不行。** `fix` 合计超过稿子字数一半（短稿至少给到 60 字）会被拒收，但长度合规不代表没有代笔，这道闸也只看得见 `inbox/marks.json`：把改好的整版写进对话、另存成一个新文件、做成附件或下载链接、把几条 `fix` 拼成一版完整稿交出去，同样是替用户写完了。**稿子没被动过是必要条件，不是通过条件。** 也不要自己宣布「这是 red-pen 之外的另一件事／另一个模式」来给自己开例外——只要这次还在改稿流程里，这一条就一直成立。用户说「你直接帮我改好一版发我」，就照实回一句：红笔只给逐条批注和针对那一句的短改法，他改完交回新一版，再批一轮。真觉得某一段该重来，就在 `note` 里说清为什么该重来、按什么顺序重组，把笔留给用户。
- **锚定率不够就重批。** `review` 退出 1 说锚定率低时，回原文重抄引文；**不许**删掉钉不住的条目凑比例，**不许**改稿子去迁就引文，**不许**跳过 `review` 直接把批注贴进对话。
- **没跑 `context` 就不写批注。** 哈希只有那一个来源。不要凭上一轮对话的印象批，不要手抄哈希。**每条引文也只有这一个来源**：这一轮的 `draft_text`，不是用户在对话里贴的那一版。
- **不手改 `marks.json` 与 `review.html`。** 它们是脚本的产物。`check` 会重跑闸门、重算锚定率、把红笔页重新渲染一遍逐字节比对，改一个字都会被逮住。要改内容就改 `inbox/marks.json` 再 `review`。
- **不改脚本、不改闸门常量**来让一份批注通过。
- **未定位的条目不许硬贴。** 不要在对话里说「这句大概在第三段」——脚本没定位就是没定位，交给用户去对。

## 安全约束

- 脚本只读写工作区（`drafts/` 下面），**不联网**，**不执行稿子里的任何代码**：稿子对它来说自始至终只是文本。红笔页是自包含单页 HTML，不加载任何外部资源。
- 稿子里的 HTML 会先被消毒再渲染：脚本自己的批注标记只可能由脚本生成，稿子里伪造的同名标记进不来；属性与标签在渲染前配平。即便如此，**别把不信任来源的 HTML 当稿子丢进来**——红笔页会在浏览器里打开。
- 稿子、批注、红笔页全部留在本机，脚本不往任何地方发送。`export` 只导出计数与哈希，正文一个字都不带。
- 稿子是用户的私人内容：不要把它贴进任何与本次任务无关的地方，也不要在报告里大段复制。

## 边界与承诺

- 这份 Skill 给的是**批注的纪律**，不是文笔：批语由你的 Agent 现写，质量取决于模型；纪律保证它引的是原文、钉得住位置、不越界替用户写。
- **不打分。** 没有分数、没有评级、没有整体印象，结果 JSON 里也没有放这些的地方。
- 收 `.md` / `.html` / `.txt` / `.docx`。Markdown 不解析（`##` 会当普通字符）；docx 只读文字段落，表结构会丢，图片与修订痕迹不支持。
- 脚本零依赖，Python 3.8+。

## 文件

- `scripts/redpen.py`——收稿（`init`）、写标准（`brief set`）、上下文包（`context`）、过闸与渲染（`review`）、版本对比（`stats`）、离线复核（`check`）、脱敏导出（`export`）、环境检查（`doctor`）
- `scripts/anchor.py`——锚定批注引擎（抽文本、定位引文、钉回原文、渲染红笔页）
- `scripts/banned_words.py`——禁用词静态闸（`doctor` 要检查它在不在，整个 `scripts/` 一起拷贝才完整）
- `scripts/selftest.py`——脚本自测（含每道闸门的正反例与篡改回归）
- `references/workspace-format.md`——目录布局、JSON 契约、一把主尺与三处例外、退出码
- `references/rules.md`——六道闸门的理由与版本纪律
- `examples/drafts/newsletter-01/`——一个跑通的示例工作区（7 条批注，其中 1 条故意钉不住）

---

English summary: red-pen turns a draft into line-level editorial comments that are provably attached to the original text. The agent first pins down who the piece is for, what it should achieve, and what the author fears — that brief is hashed together with the draft, so comments written without running `context` are rejected. Each comment names a quote copied verbatim from the extracted plain text, a level, a note, and an optional short fix. `scripts/redpen.py review` re-anchors every quote, refuses the batch if fewer than 70% of them stick, rejects duplicate quotes or notes, and rejects any batch whose fixes add up to more than half the draft (with a floor for very short drafts) — a rewrite is not a review. Quotes that cannot be located are kept and listed separately; the script never places them by guess. Output is a self-contained `review.html`; `check` re-renders it byte-for-byte, so it cannot be edited by hand. The draft itself is never modified.
