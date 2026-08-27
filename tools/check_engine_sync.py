#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享引擎同步闸：三个 Skill 各自带一份 `anchor.py` 与 `banned_words.py`，必须字节相同。

每个 Skill 目录都要能整个拷到 `~/.claude/skills/<name>/` 独立安装，所以共享文件只能
复制、不能 import。复制就会漂：改了一处忘了另两处，三个 Skill 的行为就悄悄分家了。
本脚本以第一个 Skill 的那份为基准，逐份比字节，不一致就打印 diff 摘要并退出 1。

用法：`python3 tools/check_engine_sync.py [仓库根目录]`；一致时退出 0。
拷贝还没建好时会逐条打印「缺少 …」并退出 1 —— 这也是待办清单。
"""

import argparse
import difflib
import hashlib
import os
import sys
from typing import List

SKILLS = ("rubric-grader", "red-pen", "self-grader")
SHARED = ("anchor.py", "banned_words.py")
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
    """返回问题描述列表，空列表即三份一致。"""
    problems = []
    for name in SHARED:
        base_rel = _rel(SKILLS[0], name)
        base_path = os.path.join(root, base_rel)
        if not os.path.isfile(base_path):
            problems.append("缺少 %s（这是基准那一份）" % base_rel)
            continue
        with open(base_path, "rb") as f:
            base_bytes = f.read()
        for skill in SKILLS[1:]:
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
        print("共享文件没同步：%d 个 Skill × %d 个文件应当字节相同。"
              % (len(SKILLS), len(SHARED)))
        return 1
    print("共享文件已同步：%s 在 %s 三处字节相同。"
          % ("、".join(SHARED), "、".join(SKILLS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
