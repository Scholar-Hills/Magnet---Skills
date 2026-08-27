---
name: coding-drill
description: 刷题私教——说一个编程知识点，出一道标准输入/输出的练习题（题面、起步骨架、隐藏用例），你写完它在本机真跑判题，错了告诉你错在哪条用例、抓的是什么误解，并记进你的错题本；也能替老师出“薅不到分”的题并导出题包。Use when the user wants a coding practice problem on a topic, wants their solution judged, or a teacher wants judge-proof stdin/stdout programming exercises. Python / JavaScript / Java.
license: MIT
allowed-tools: Bash, Read, Write, Edit
---

# 刷题私教（coding-drill）

一句话：**它出的题，交一个 `print(42)` 拿不到分。** 参考解和隐藏用例先藏起来，你写完它才判；期望输出只许由参考解实跑得到，绝不手写；每条隐藏用例都知道自己在抓哪种错误。

## 你能对它说什么

| 你说 | 它做 |
|---|---|
| `出题 二分查找 Python 中等` | 出一道题：题面、起步骨架、一组示例；参考解、隐藏用例、错解藏进 `.hidden/` |
| （直接改 `drills/<slug>/solution.py`，**不用跟它说话**） | 你写代码。它不看、不提示、不改你的文件 |
| `判我` | 在本机跑全部用例；只揭开第一条没过的隐藏用例；把抓到的误解追加进错题本 |
| `给点提示` | 只说你可能想错了哪一步，不给代码 |
| `再来一道` / `难一点` | 同知识点换一道，或升一档难度 |
| `给学生出题 递归 Java 中等 3 道` | 老师模式：每道题走完整验证（四个非解 0 分、错解必挂），导出题包 JSON |

## 前置检查（不可跳过）

0. **定位脚本**。本 Skill 的脚本在 Skill 目录下，不在用户工作区。按顺序找，取第一个存在的绝对路径记作 `JUDGE`：
   ① `~/.claude/skills/coding-drill/scripts/judge.py`；② 当前项目的 `.claude/skills/coding-drill/scripts/judge.py`；③ 用户在对话里指定的 Skill 目录下的 `scripts/judge.py`；④ 都没有就 `find . ~/.claude -path '*coding-drill/scripts/judge.py' 2>/dev/null | head -1` 搜一次。
   本文后面所有 `python3 scripts/judge.py …` 都读作 `python3 "$JUDGE" …`，并且始终在用户工作区（`drills/` 的父目录）下执行：`cd <工作区> && python3 "$JUDGE" author drills/<slug>`。
   **四处都找不到就立即停止**，告诉用户“这份 Skill 的判题脚本缺失，请重新下载完整目录”。**任何情况下都不要自己写一个替代脚本**——手写的判题器没有本 Skill 的回填与基线闸门，会让用户误以为题目通过了验证。
1. 运行 `python3 "$JUDGE" doctor`。`python3` 不存在就试 `python`（Windows 常见）；两个都没有，告诉用户先装 Python 3.8+，不要继续。JavaScript 题需要 `node`，Java 题需要 `javac` 与 `java`；缺哪个就不出那种语言的题。
2. 题都放在**当前工作区**（用户项目的根目录，不是 Skill 目录）的 `drills/` 下。第一次出题前先 `pwd` 看一眼：如果当前目录是家目录、桌面或其它不像项目的地方，先问用户一句“题目和错题本我打算放在 `<当前路径>/drills/`，可以吗？想换个地方现在告诉我”。定下来之后就别再换——错题本要一直在同一处才有意义。
3. **出题前先读一遍 `drills/misconceptions.md`**：这个人之前在哪些地方错过，新题的隐藏用例里至少有一条要再抓一次他最近的误解——这就是“越用越像你的老师”。错题本里的误解与本次知识点无关时（上次错的是字符串比较，这次出二分查找）就跳过并说一句，不要硬塞。第一次用时它还不存在，跳过即可；不要为此创建空文件，脚本判题时会自动创建。
4. 第一次出题前，看一眼 Skill 目录里 `examples/drills/` 的两道示例题包——目录结构、`tests.json` 的写法、`catches` 的粒度，照着它来，比照着文字描述更不容易出错。示例目录为空就改读 `references/problem-format.md` §1～§4。

## 出题流程（学习者模式）

格式以 `references/problem-format.md` 为准，规则以 `references/authoring-rules.md` 为准——**先读这两份**再出题。按顺序做，不要跳步。

**动手前先说一句**：“我来出一道 ＜知识点＞ 的题，会先写好参考解和隐藏用例，然后在你机器上真跑一遍自检（打印常量、空程序、回显输入、原样骨架四个非解必须全部 0 分）。大概要一两分钟，中间没有输出是正常的。”非交互场景（批处理、子任务）就把这句写进最终报告的开头。

1. **定题**：知识点、语言、难度。用户说的“简单 / 中等 / 困难”分别对应 `1 / 2 / 3`，`meta.json` 的 `difficulty` **必须是数字**；用户没说难度就默认 `2` 并告知。难度按 authoring-rules §7 的表取，写一句理由。题必须是“完整程序、stdin → stdout”，输出只用整数 / `true`/`false` / 单词，不用浮点数。`slug` = 英文小写知识点 + 两位序号（如 `binary-search-01`），先 `ls drills/` 看同知识点已有几道，接着排。
2. **写题面骨干** `problem.md`：任务、输入格式、输出格式、并列规则，最后是示例块。**示例的输入与输出都先写占位，不要自己算**，格式固定如下（围栏代码块不缩进；导出时会校验题面逐字包含样例）：

   ```
   ## 示例

   输入
   ```
   <待回填输入>
   ```
   输出
   ```
   <待回填输出>
   ```
   ```
3. **写起步骨架**（Python / JavaScript 为 `starter.py` / `starter.js`；Java 为 `starter/Main.java`）：含读输入的代码，原样运行必须 0 分，不泄露算法。把骨架复制一份作为学生作答文件（`solution.py` / `solution.js` / `<slug>/Main.java`）。
4. **写参考解**到 `.hidden/`（`reference.py` / `reference.js` / `reference/Main.java`）：像好学生的答案。Java 类名必须是 `Main`。
5. **设计 5 条用例**写进 `.hidden/tests.json`：1 条样例（0 分）+ 4 条隐藏（2+3+2+3），四条隐藏各取一个**不同**职责（typical / boundary / empty / saturated / order），每条写明 `catches`。**隐藏用例的 `expected` 一律写 `null`**，由脚本回填；只有样例那条可以手写你预期的输出，用来交叉校验参考解。题面里有阈值，就必须有一条用例恰好坐在阈值上。`catches` 要写**具体的错法**，不是用例的类别：写“用 `>` 代替 `>=`，恰好相等时被跳过”，不要写“测试边界情况”。
6. **写至少 2 个、最好 3 个错解**到 `.hidden/mutants/`，每个实现一种真实误解，并在 `mutants.json` 里写明。
7. **运行验证**：`python3 "$JUDGE" author drills/<slug>`。脚本回填期望输出，然后跑闸门：输出两两不同、输入不等于输出、无空输出、四个非解（打印样例输出 / 什么都不打印 / 回显输入 / 起步骨架原样提交）全部 0 分、每个错解都拿不到满分。
8. **有 ERROR 就改题不改数据**：回到第 4～6 步调整用例数据、错解或参考解，重新验证，直到通过。每轮说一句“第 N 轮自检没过：＜哪条闸门＞，我调一下用例数据再验一次”，不要静默重试。**不要**手改隐藏用例的 `expected` 让它通过；**永远不要加 `--refill`**——那是出题者重做参考解时由人执行的开关。遇到 `solution_fail` 先分清是谁错：报告里是**样例那条**手写值与实跑不符，多半是你手算错了或题面描述有歧义，改那个手写值或题面；是**参考解**自己跑挂了（超时、报错、隐藏用例已有值不符），改参考解。自己试跑错解或某个想法用 `python3 "$JUDGE" run drills/<slug> <文件>`——它不写错题本、不覆盖判题报告；`judge` 只留给用户的真实作答。
9. **回填题面示例**：`author` 通过后，用下面这段把样例用例的 `input` 与 `expected` **原样写进** `problem.md`，不要手抄（靠复制保证，不靠眼力；多行输入手抄最容易错）：

   ```
   python3 - <<'EOF'
   import json, pathlib
   d = pathlib.Path('drills/<slug>')
   s = [c for c in json.load(open(d/'.hidden/tests.json', encoding='utf-8'))['cases'] if c.get('isSample')][0]
   p = d/'problem.md'; t = p.read_text(encoding='utf-8')
   p.write_text(t.replace('<待回填输入>', s['input']).replace('<待回填输出>', s['expected']), encoding='utf-8')
   EOF
   ```
10. **门禁**：只有当 `author` 的退出码为 0、报告里没有 ERROR 时，才可以把题交给用户。**验证没通过、或者你根本没跑验证，就不许把题面发出去**——宁可说“这道题没通过自检，我重出一道”。交题时如实说一句：“已通过自检：四个非解均 0 分、M 个错解均丢分。”只展示题面、骨架、示例；**不要**在对话里贴出参考解、隐藏用例的输入输出或错解。告诉用户改作答文件，改完说“判我”。

**写完 `.hidden/` 之后就当自己没看过。** 参考解、隐藏用例的输入与期望输出、错解，从这一刻起只由脚本读取，不进对话。用户在作答阶段问思路，只能用题面里已有的信息回答；要举例子就现编一个题面示例之外的小数据，**绝不引用任何一条隐藏用例的数值**。

## 判题流程

1. 用户说“判我”（或类似的话）：运行 `python3 "$JUDGE" judge drills/<slug>`。
2. 把脚本的结果表原样转述：得分、每条用例通过与否；**隐藏用例默认只揭开第一条没过的**（输入、期望、实际），其余只说“这条抓的是：…”。用户明确要求全部揭开再加 `--reveal-all`。
3. 解释没过的那条用例抓到了什么误解，指向它对应的知识点。**给帮助分三档，一次只上一档**：① 提示误解方向（默认）；② 用户再问 → 给伪代码或一句关键判断条件；③ 用户明确说“就是要看代码”→ 才给，并且**另写一份讲解版代码，不要直接贴 `.hidden/` 里的参考解**，贴完提醒他这道题的隐藏用例已经失效，建议出同知识点的下一道。
4. 提醒用户：错题本 `drills/misconceptions.md` 新增了什么（脚本已自动追加），以及**判题卡在 `drills/<slug>/report.html`，用浏览器打开可以直接截图**。
5. 全部通过后，可以顺势问一句要不要出同一知识点的下一档难度。

## 老师模式

用户说“给学生出题 ＜知识点＞ ＜语言＞ ＜难度＞ [N 道]”时：

- 每道题走完上面出题流程的全部步骤，`meta.json` 的 `mode` 写 `teacher`。
- 全部通过 `author` 验证后，运行 `python3 "$JUDGE" export drills/<slug>` 导出题包 JSON，并把 `author-report.md` 给老师看（它不含隐藏用例的内容，只含闸门结果与每个错解的得分）。
- 老师要看参考解和隐藏用例时可以给——这是老师的题。

## 安全约束（必须遵守）

- 脚本在临时目录里用超时运行程序、限制输出体积、超时杀整棵进程树，但**没有沙箱**：不能隔离网络与文件系统。所以：
  - 只运行本次由你生成的参考解、错解、基线，以及用户自己写的作答文件；不运行来路不明的代码。
  - 生成参考解与错解时不写任何文件操作、网络访问、子进程调用、进程探查；运行前把生成的代码通读一遍确认这一点。要盯的关键词：Python 的 `subprocess` / `os.system` / `os.popen` / `os.fork` / `os.exec*` / `os.spawn*` / `os.posix_spawn` / `multiprocessing` / `concurrent.futures` / `ctypes` / `os.setsid` / `os.getppid` / `/proc/` / `lsof` / `socket` / `urllib` / `open(` / `pathlib` / `shutil`；JavaScript 的 `child_process` / `worker_threads` / `cluster` / `process.ppid` / `net` / `http` / `dns` / 除读 stdin 之外的 `fs`；Java 的 `ProcessBuilder` / `Runtime.getRuntime` / `ProcessHandle` / `java.io.File` / `java.nio.file` / `java.net`。
  - `judge` 会先对作答文件做同样的静态扫描，命中就不运行并退出 2。这时把命中的行给用户看，**用户确认无害后**才加 `--allow-io` 重跑；不要自己替用户加。扫描是尽力而为的绊线，不是沙箱边界——起进程的写法穷举不完，最终仍靠你通读代码。
- 每条用例超时默认 2 秒，编译超时 15 秒；超时判 `time_limit_exceeded`，输出超过 256 KB 判 `output_limit_exceeded`。
- 不要为了“让题通过”修改脚本本身。

## 边界与承诺

- 这份 Skill 给的是出题与判题的**纪律**，不是题库：题由你的 Agent 现出，质量取决于模型，纪律保证它薅不到分、抓得到错。
- 支持 Python 3（无第三方库）、JavaScript（Node，CommonJS，无 npm 包）、Java（`public class Main`，无 `package`）。
- 判题脚本零依赖，Python 3.8+。

## 文件

- `scripts/judge.py`——出题验证（`author`）、判题（`judge`）、任意程序试跑（`run`）、导出（`export`）、环境检查（`doctor`）
- `scripts/selftest.py`——脚本自测
- `references/problem-format.md`——题包目录、`tests.json`、`mutants.json`、脚本契约
- `references/authoring-rules.md`——出题纪律全文（用例职责、薅不到分的构造、错解、难度）
- `examples/`——两道经过验证的示例题包（Python、JavaScript），可直接 `judge` 试手

---

English summary: coding-drill turns a topic into a stdin→stdout programming exercise with a hidden reference solution, five purpose-built test cases (one 0-point sample + four hidden cases that each name the misconception they catch), and 2–3 wrong solutions. `scripts/judge.py author` fills expected outputs by actually running the reference, then proves that printing a constant, printing nothing, echoing stdin, and the untouched starter all score 0 and that every wrong solution loses points. `judge` runs the learner's file, reveals only the first failing hidden case, and appends the caught misconception to `drills/misconceptions.md`. No sandbox: the agent must review generated code before running it.
