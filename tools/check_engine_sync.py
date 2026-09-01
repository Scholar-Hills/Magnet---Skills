#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享引擎同步闸：多个 Skill 各自带一份共享文件的拷贝，同名的那些必须字节相同。

每个 Skill 目录都要能整个拷到 `~/.claude/skills/<name>/` 独立安装，所以共享文件只能
复制、不能 import。复制就会漂：改了一处忘了别处，几个 Skill 的行为就悄悄分家了。
本脚本对每个共享文件以它自己那份清单里第一个 Skill 的拷贝为基准，逐份比字节，
不一致就打印 diff 摘要并退出 1。

两份共享文件的覆盖面不同，所以清单分开写：

- `banned_words.py`（黑名单闸门）五个 Skill 都要带 —— 批改三件套加 essay-sections、
  lesson-prep。凡是会把模型产物当交付物的流程都得过同一道闸，口径不许分家。
- `anchor.py`（锚定批注引擎）只有批改三件套用。essay-sections 与 lesson-prep 不做
  逐句锚定批注，本来就不带这份，也不该被要求带 —— 别顺手把它们加进这条清单。

用法：`python3 tools/check_engine_sync.py [仓库根目录]`；一致时退出 0。
拷贝还没建好时会逐条打印「缺少 …」并退出 1 —— 这也是待办清单。
"""

import argparse
import difflib
import hashlib
import os
import sys
from typing import List

ANNOTATION_SKILLS = ("rubric-grader", "red-pen", "self-grader")
BANNED_SKILLS = ANNOTATION_SKILLS + ("essay-sections", "lesson-prep")
# 共享文件 → 必须带这份拷贝的 Skill 清单；每条清单里第一个是比对基准。
SHARED = (
    ("anchor.py", ANNOTATION_SKILLS),
    ("banned_words.py", BANNED_SKILLS),
)
SCRIPTS_DIR = "scripts"
DIFF_LINES = 20


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rel(skill: str, name: str) -> str:
    return "%s/%s/%s" % (skill, SCRIPTS_DIR, name)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _diff_summary(base_rel: str, base_text: str, other_rel: str, other_text: str) -> List[str]:
    lines = list(difflib.unified_diff(
        base_text.splitlines(), other_text.splitlines(),
        fromfile=base_rel, tofile=other_rel, lineterm="", n=1))
    if len(lines) > DIFF_LINES:
        rest = len(lines) - DIFF_LINES
        lines = lines[:DIFF_LINES] + ["（还有 %d 行差异未列出）" % rest]
    return ["    " + line for line in lines]


def check(root: str) -> List[str]:
    """返回问题描述列表，空列表即每份共享文件在它自己的清单里处处一致。"""
    problems = []
    for name, skills in SHARED:
        base_rel = _rel(skills[0], name)
        base_path = os.path.join(root, base_rel)
        if not os.path.isfile(base_path):
            problems.append("缺少 %s（这是基准那一份）" % base_rel)
            continue
        with open(base_path, "rb") as f:
            base_bytes = f.read()
        for skill in skills[1:]:
            rel = _rel(skill, name)
            path = os.path.join(root, rel)
            if not os.path.isfile(path):
                problems.append("缺少 %s" % rel)
                continue
            with open(path, "rb") as f:
                other_bytes = f.read()
            if other_bytes == base_bytes:
                continue
            problems.append("%s 与 %s 不一致（%s ≠ %s）"
                            % (rel, base_rel, _digest(other_bytes), _digest(base_bytes)))
            problems.extend(_diff_summary(
                base_rel, base_bytes.decode("utf-8", "replace"),
                rel, other_bytes.decode("utf-8", "replace")))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(prog="check_engine_sync.py", description="共享引擎同步闸")
    parser.add_argument("root", nargs="?", default=_repo_root(), help="仓库根目录（默认按本文件位置推断）")
    args = parser.parse_args(argv)
    problems = check(args.root)
    for line in problems:
        print(line)
    if problems:
        print("共享文件没同步；应当字节相同的是：%s。"
              % "；".join("%s × %d 份" % (name, len(skills)) for name, skills in SHARED))
        return 1
    for name, skills in SHARED:
        print("共享文件已同步：%s 在 %s 共 %d 处字节相同。"
              % (name, "、".join(skills), len(skills)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
