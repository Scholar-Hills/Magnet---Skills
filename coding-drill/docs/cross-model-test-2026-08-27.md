# 跨模型实测记录 · 2026-08-27（WorkBuddy AI 5.4.2 + Claude Code 2.1.241）

发布闸第 3 项。宿主一：腾讯 WorkBuddy AI 5.4.2（macOS），Skill 装在 `~/.workbuddy-ai/skills/coding-drill/`，`/skills` 面板识别为 Installed 且启用；宿主二：Claude Code 2.1.241 无头模式（`claude -p`，`--setting-sources project` 隔离掉本机全局配置，Skill 以项目级 `.claude/skills/coding-drill/` 安装，工作区里预放了一道 `binary-search-01` 以考「排 02」）。提示词均为「出题 二分查找 Python 中等」。证据来自宿主的会话日志（每一次工具调用与参数）与落盘题包，题包另在干净副本里用 `export` / `judge` / `author` 复核。

| 盯的点 | Kimi-K3（WorkBuddy） | 腾讯混元 Hy3（WorkBuddy） | Claude Opus 5（Claude Code） |
|---|---|---|---|
| 定位脚本、跑 `doctor` | ✅ 第 2 步即跑 | ✅ 第 2 步即跑 | ✅ 第 2 步即跑 |
| 读 references（两份） | ✅ | ✅ | ✅ |
| 看示例题包 | ✅ 读了 4 个文件 | ⚠️ 只 `ls -R`，没读内容 | ⚠️ `ls` + 看了 tests.json 前 20 行 |
| 隐藏用例 `expected` 写成 `null` 交给脚本回填 | ✅（c2–c5 全 null） | ✅（c2–c5 全 null） | ✅（c2–c5 全 null） |
| 跑 `author`，一次通过 | ✅ 0 ERROR 0 WARN | ✅ 0 ERROR 0 WARN | ✅ 0 ERROR 0 WARN |
| 用第 9 步脚本回填样例（不手抄） | ✅ | ✅ | ✅ |
| 碰 `--refill` / 手改 expected | ❌ 没有 | ❌ 没有 | ❌ 没有 |
| 错解数 | 4 | 4 | 4 |
| 交题消息里贴参考解 / 隐藏用例 | 没有 | 没有 | 没有 |
| 可见推理流里出现隐藏用例数值 | ⚠️ 输入与答案都有 | ⚠️ 答案有、输入没有 | （无头模式不展示推理）|
| 说「我来出一道…」开场 | ✅ | ⚠️ 用英文说的（用户是中文） | ✅ |
| 误跑 `judge` 污染错题本 | 没有 | 没有 | 没有 |
| 耗时 | 9.3 分钟（推理约 35k 字符） | 4.5 分钟（推理约 57k 字符） | 4.8 分钟，12 次工具调用，$1.23 |
| 独立复核（export / 参考解 10 分 / 骨架 0 分 / 重跑 author） | 全过 | 全过 | 全过 |
| 同知识点第二题排 `02` | （drills/ 为空，排 01 正确） | （无工作区，未考到） | ✅ 排成 `binary-search-02` |
| 「找不到」用 `NONE` 而非 0/-1（§4.8） | 题型无此情形 | ⚠️ 用了 `-1 -1`（题面已声明，可接受） | ✅ `NONE` |

## 发现与处理

1. **WorkBuddy 不选工作区会把题放进 `~/WorkBuddy AI/<时间戳>/`**，每个任务一个新目录，错题本无法累积。→ README 的 WorkBuddy 段加「先选固定工作区」。
2. **会展示思考过程的宿主会把隐藏用例漏给学习者**（Kimi 把 5 条用例的输入和答案都在推理里推了一遍）。这是宿主行为，SKILL 管不到；对自学者来说是「自己看答案」，不是安全问题。README「边界」里如实写明。
3. **WorkBuddy 自动记忆**在工作区写了 `.workbuddy-ai/memory/<日期>.md`，把 4 个错解各抓什么误解记了进去（Kimi 那轮）。同上，宿主行为。
4. Hy3 首句用英文回复中文用户。→ SKILL.md 加「回复语言跟随用户」。
5. 两个模型都没在 cwd 不像项目时提问（Hy3 的 cwd 是 WorkBuddy 自动建的时间戳目录）。Claude Code 那轮 cwd 是明确的项目目录，考不到这一条。第 2 步的「问一句」措辞可以再硬一点，暂不改。

## 结论

三个模型、两个宿主都过了三道门禁（不跳 `author`、不手写 expected、不贴参考解），题包均通过独立复核。发布闸第 3 项通过。

## 未覆盖

- Claude Code 只跑了 Opus 5；Sonnet / Haiku 档未跑。
- 「同知识点第二题应排 02」只在 Kimi 那轮有前提（drills/ 为空→01 正确），Hy3 那轮因目录不同没考到。
- DeepSeek：WorkBuddy 5.4.2 的模型菜单里没有，未测。
