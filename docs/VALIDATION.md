# 本次文档调整的验证记录

验证日期：２０２６年９月３０日。范围：仓库首页、六个 Skill 的介绍与安装说明、维护模板和宣传素材。本次未修改脚本或格式契约。

## 本机检查

| Skill | 自测退出码 | 示例验证 |
| --- | --- | --- |
| coding-drill | 0 | 两个题包的 author 均为零 ERROR、零 WARN |
| red-pen | 0 | check 为零 ERROR、零 WARN |
| essay-sections | 0 | check 为零 ERROR、两项 WARN |
| lesson-prep | 0 | check --all 为零 ERROR、零 WARN |
| rubric-grader | 0 | check 为零 ERROR、一项 WARN |
| self-grader | 0 | check 为零 ERROR、零 WARN |

自测入口均为 `python3 <skill>/scripts/selftest.py`。示例复核使用临时副本，保留仓库原始示例和报告。

本机未安装 Java 编译与运行环境。coding-drill 已验证缺少 Java 运行时的降级行为，但本次没有验证 Java 程序实际编译与执行；Python 和 JavaScript 的示例 author 验证均已执行。

## WARN 说明

- essay-sections 的 body-01 原文已修改，旧评审分数过期。查看当前文本的分数前，应重新评审该段；旧记录继续保留。
- essay-sections 的荐读为未核实的示例条目，不能作为核实过的出处引用。此提醒保留在示例中。
- rubric-grader 的 inbox 保留七个评分结果提交文件。脚本允许通过后删除；当前示例保留它们以供查看提交格式，复核仍为零 ERROR。

## 安装与文档检查

skills CLI 的本地与 GitHub `--list` 均退出零，识别出六个 Skill。完整复制安装在临时目录中验证，各 Skill 包含 scripts、references 与 examples，安装脚本与源文件字节一致。

共享脚本同步检查通过；文档本地链接、占位地址、本机绝对路径和空白检查通过。仓库首页提供在线安装命令，独立 Skill README 提供本地安装与手动复制步骤。

## 尚未完成的发布验收

本轮未执行至少两个非 Codex 模型的跨模型实测，也未据此宣布任何 Skill 已通过正式发布验收。正式发布前须按[贡献指南](../CONTRIBUTING.md#发布验收)补齐适用记录。

本机校验结果只说明本次执行的检查通过，不代表评分准确、教学有效或所有模型都能遵守门禁。

## English summary

All six local self-test suites and all seven example checks passed. Three example warnings are documented. Skill discovery and complete copy installation were checked. Java execution was unavailable, and cross-model release trials were not performed in this documentation update.
