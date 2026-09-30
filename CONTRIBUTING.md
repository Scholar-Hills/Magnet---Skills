# 参与维护 Magnet Skills

欢迎提交工作流改进、可复现的问题和文档修正。维护与对外署名统一为「学霸山丘技术团队」。

## 改动前

先读目标 Skill 的 `SKILL.md` 与 `references/`。每个 Skill 使用一个顶层目录，整个目录必须能独立安装，不再套一层 `skills/`。README 面向使用者，SKILL.md 面向 Agent，references 定义格式与规则，scripts 执行检查，examples 提供可复现示例。

新 Skill 请先开 Issue，说明使用者、任务、交付物、验证方式与边界。现有 Skill 的问题请给出最小复现和预期行为。

## 内容边界

公开贡献只包含可复用的工作流、校验机制与合成示例。不要提交内部调教内容、学科评分标准、题库、隐藏用例库、考纲清单、内部系统标识或平台导入格式。学生、老师与订单等生产数据即使脱敏也不接收。

示例必须使用公开可分发的合成材料。问题截图、终端输出与报告先检查个人路径和私人内容。

## 文档与契约

中文使用全角标点，英文摘要集中放在文末。不贬低模型或平台，不使用个人真名；成绩与宣传数字须提供出处，设计目标不能写成实测成绩。

修改格式契约时，同一个提交必须同步对应脚本与自测断言；脚本行为改变时，同步 references 与对应断言。只修改介绍或安装说明时，核对文案与现有行为一致，并验证命令和链接。

## 本机验证

在仓库根目录运行所有 Skill 自测：

```bash
for skill in coding-drill red-pen essay-sections lesson-prep rubric-grader self-grader; do
  python3 "$skill/scripts/selftest.py" || exit 1
done
python3 tools/check_engine_sync.py
```

复核示例时建议使用临时副本，避免验收生成文件覆盖已提交报告。当前示例的验证入口如下；增加示例时也必须逐个验证。

```bash
python3 coding-drill/scripts/judge.py author coding-drill/examples/drills/binary-search-01
python3 coding-drill/scripts/judge.py author coding-drill/examples/drills/word-count-threshold-01
python3 red-pen/scripts/redpen.py check red-pen/examples/drafts/newsletter-01
python3 rubric-grader/scripts/grader.py check rubric-grader/examples/grading/short-answer-01
python3 self-grader/scripts/selfgrade.py check self-grader/examples/practice/opportunity-cost-01
```

分段写作与备课的示例需从各自 examples 目录运行，脚本路径仍指向该 Skill：

```bash
(cd essay-sections/examples && python3 ../scripts/essayctl.py check remote-work-cities-01)
(cd lesson-prep/examples && python3 ../scripts/lessonkit.py check city-wetland --all)
```

逐条记录 WARN 及其理由。命令退出失败时保留原因，不能只写「测过」。

## 发布验收

提交发布 PR 或上传小红书 Red Skill 前，目标 Skill 必须同时满足：

１．`python3 <skill>/scripts/selftest.py` 全绿，包含攻击回归。

２．全部示例验证为零 ERROR。编程示例运行 `author`；其他工作流运行对应的离线 `check`。WARN 在 PR 中逐条说明。

３．至少两个非 Codex 模型完成跨模型实测，并保留模型名称、版本、日期、任务规模、执行结果与失败轮证据。出题类每个模型各出三个知识点、每个知识点五题；批改或批注类每个模型各批三篇稿子、每篇至少五条批注，其中至少一篇进入第二版。其他工作流记录完整流程覆盖，并按仓库发布规则核对适用要求。

实测重点检查是否跳过验证、手写应由脚本生成的期望输出、在作答阶段泄露参考解，以及是否违反该 Skill 的其他门禁。任何一项发生，先修规则再重测。没有证据、没有跑完或没有通过，就不能宣称「可以发布」。自动化自测不能替代跨模型实测。

公开 PR 只写合成任务与必要结论，不附私人数据、内部路径或内部证据文件。

## 提交前

确认没有本机绝对路径、运行缓存、错题本或导出文件进入提交；示例报告保留规定的生成产物。检查 `git diff --check` 和本次 diff，避免混入其他改动。PR 中写明改变了什么、怎样验证、哪些验收仍待完成。

## English summary

Contributions must preserve independently installable skill directories, keep format references and scripts in sync, and use synthetic examples only. Release acceptance requires passing self-tests, validating every example, and documented trials with at least two non-Codex models. Report warnings and incomplete checks explicitly.
