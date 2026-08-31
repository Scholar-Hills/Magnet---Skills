#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""禁用词静态闸：扫一个 Skill 目录，报出不该对外发布的字眼。

三层，各管一类：

1. `BANNED_SUBSTRING` —— 明文子串表。本机家目录路径这类「写出来就是错」且公开无害的
   模式放这里（母仓 CLAUDE.md 要求提交前用 grep 确认 Skill 目录里没有本机绝对路径，
   这一层把那条检查收进脚本）。
2. `_INTERNAL` —— 内部标识符的**摘要**表（品牌、类名、函数名、文件名、CSS class、
   环境变量、表名、HTTP 路径、日志前缀…）。这些词本身就是不能对外发布的东西，
   所以这里只存 SHA-256 截断摘要，不存明文：扫描时对文件内容按长度开窗算摘要比对，
   命中了才把原文打出来（原文本来就在被扫的文件里）。有摘要的人无法反推出词表，
   要验证某个词是否在表内则必须先知道那个词。
3. `BANNED_TOKEN` —— 通用英文枚举词。这些是普通英文单词，明文放着无妨，但直接做子串
   匹配会把散文全误报，所以只在两种位置查：JSON 文件的键与字符串值、Python / Markdown
   里被引号（`"` `'` `` ` ``）包住且整串恰好等于该词的字面量。**区分大小写**：
   生产的枚举值一律小写，而母仓 CLI 报告里的 `ERROR` / `WARN` 是既有约定，不能误伤。

用法：`python3 tools/banned_words.py <目录>`；干净时不输出、退出 0，有命中时逐条打印、
退出 1。三个 Skill 各带一份同字节的拷贝，`tools/check_engine_sync.py` 断言它们一致。
扫描会跳过本文件自身（词表本来就写着这些词）。
"""

import argparse
import hashlib
import os
import re
import sys
from typing import List

# ---- 第 1 层：明文子串（公开无害）
# 三段拼出来，免得本文件自己被 grep 本机路径的那条检查逮到
BANNED_SUBSTRING = [
    "/" + "Users" + "/",
    "/" + "home" + "/",
    "C:" + "\\Users" + "\\",
]

# ---- 第 3 层：通用英文枚举词（只在 JSON 键 / 引号字面量位置匹配）
BANNED_TOKEN = [
    "error", "warning", "info", "highlight", "good", "overall",
    "knowledge", "efficiency", "expression",
    "relevant", "ambiguous", "irrelevant",
    "grading", "reviewed", "degraded",
    "objective", "subjective", "generic", "embedded",
    "stimulus", "annotations", "transcription",
    "single_choice", "multiple_choice", "true_false", "fill_blank",
    "short_answer", "long_answer",
    "skipped_disabled", "skipped_has_image", "skipped_empty", "skipped_subject",
    "target", "severity", "comment",
]

# ---- 第 2 层：内部标识符摘要表（明文不入库；自测金丝雀也在表内）
_INTERNAL_LENGTHS = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 30, 31)

_INTERNAL_PREFIX = frozenset((
    "00a9e425", "00d74baf", "037aeaea", "03846851", "0510eddd", "05bb48ed", "08c85bd3", "0a64ce10",
    "135e6098", "141582aa", "17057013", "183ee087", "19503ea6", "225ed656", "27c47b28", "2b6bdfb2",
    "2c9dcded", "2ce2847c", "2d6c9a90", "309d2086", "32e83e92", "337405b2", "34367776", "3ac1ecbd",
    "3c44c3e1", "3d9fc4bd", "3e399c46", "3ebb1c99", "4748e43c", "4a44dc15", "4a60bf7d", "4ec9599f",
    "5312fb60", "56af4bde", "58296753", "6199aecf", "632cd2fe", "68bca10e", "69590970", "6bda26c4",
    "70ba3370", "712dd58e", "715fe4f3", "73094374", "7571aec5", "75a288c0", "76592b9d", "765dbb8c",
    "7978f506", "8693873c", "885036a0", "89c4ec9f", "8df0b3fd", "8e446e1b", "8f434346", "8ff5d4f4",
    "9294ab38", "9390298f", "9508394f", "9513229d", "959a45d4", "970f519c", "9911f4d2", "997164d1",
    "9aaf6807", "9d0e8aa2", "9f6fee1a", "a082f17c", "a1d98908", "a821c62e", "a898df22", "a8cdcf61",
    "aa58b21b", "acafaa51", "ad9a67fe", "b24cb4b1", "b484cba2", "b4bdc848", "bc3fafdb", "c278ec5a",
    "c330ec50", "c8b60efc", "cdf69b25", "cfccfcde", "cffba188", "d1923758", "d9065d6d", "dbdbc97d",
    "e0b9a879", "ea325d76", "ed5ad332", "f3370384", "f44b6f48", "f4a4ce5f", "f52d6323", "f9e00106",
    "f9e01239", "fa51fd49",
))

_INTERNAL = frozenset((
    "10:1507bc664af8", "10:181d2af5370c", "10:1da8e185129d", "10:1e28da705555", "10:1ff0345f0bdf",
    "10:36a7f3d50236", "10:41a1a12d3f86", "10:478d625a1873", "10:4b5ee9a68089", "10:4d9e1a4e27de",
    "10:52c53471b23d", "10:5ae25452eafb", "10:63042bb3978c", "10:6dc9864f02b8", "10:7f871cbf905f",
    "10:83333c879c15", "10:bddc1c61d8a3", "10:c994327f10c1", "10:cd0ccbd4501e", "10:d6aeec89f770",
    "10:e49617115152", "10:e73d62b7fdde", "10:fe378c42586f", "11:04e2af9cfcbb", "11:33f3a0002110",
    "11:3414b5a8a6cb", "11:3f9a402b00f8", "11:8c8d9b7ca302", "11:9fe07d7f885f", "11:a209cc32115a",
    "11:b0ba02e800d2", "11:bff5d0c5457e", "11:d26cbb16966f", "11:d5aa9afb29f6", "11:d82a69c95249",
    "11:f0f04776a125", "12:21e01bbc1c4c", "12:3735fe52718e", "12:495f8d997abb", "12:4b9ef987d982",
    "12:579d4b1c3d8b", "12:60a6128047f5", "12:67dae0806e8b", "12:7514b6288057", "12:76c47a75c102",
    "12:832017222f47", "12:846664f2e27a", "12:8661a012f007", "12:8fedfcfbe545", "12:9b56cc0b5318",
    "12:a5ff5a7ab9ff", "12:a96243231987", "12:b04abae0c523", "12:b133d062b554", "12:b4a8c492c3f1",
    "12:c6dc6539e340", "12:ca177a778e9c", "12:daabb5b3e3b0", "12:e85ab2bc8346", "12:eef00d0a8994",
    "12:f933db6dbc8d", "12:fc988c4c16fa", "13:02145935ecb7", "13:0703aeed7ad3", "13:077c4636eb3c",
    "13:0eb2c8e4eae5", "13:1107f7ef6a17", "13:12c7ccbeedbb", "13:2e391d6244dc", "13:5a4787b1052b",
    "13:690a5e78e627", "13:6975013cc90b", "13:6b2674ee66a0", "13:8e70d3540c42", "13:968973b8cdb2",
    "13:acf3f70f8d09", "13:b4427a4ca47b", "13:c1a73b73a859", "13:c1ccab6b761f", "13:c226a654166a",
    "13:c3fdd5332a23", "13:c773fdc0ea3e", "13:ca864c2b0e4d", "13:cece87281c67", "13:e3fc78aef770",
    "13:ebb042f3f785", "13:f2d126019981", "13:fad53c492e22", "14:0dbdc5a2650f", "14:15365bcade6f",
    "14:3a0ffe52e037", "14:438469a3af9d", "14:48470c2a6b2c", "14:511c48ed2c87", "14:53859102f860",
    "14:5b24df88ea8d", "14:5d5686f99583", "14:692a70d2f70a", "14:6e6a6e87e782", "14:7de6adaddb31",
    "14:89db1821a3c4", "14:8adf1585b069", "14:90ea417e3ef4", "14:cec85ec2ef58", "14:cfb7ebf65f91",
    "14:dc0d968cc858", "14:dcf69e7c87ef", "14:dd8a0e94bc65", "14:de1482a0d6a6", "14:df8de4293dd4",
    "14:f0cd9e2a6881", "14:f193a64c3ce8", "15:051b2990849a", "15:0d6af4fede34", "15:160ee79739ad",
    "15:2e63c2e0ddc0", "15:405a7ecff610", "15:4225d94a7d71", "15:521aa105f458", "15:69045dbe6d8b",
    "15:7431e2768a70", "15:994cf3e7ecc4", "15:9ce8053cc5ef", "15:aff951141bd4", "15:ba5c7754d7de",
    "15:e0209c17f942", "15:f191788ce6cb", "16:0ae158405bbb", "16:19fcdfbb6b0a", "16:2b38f64c55b6",
    "16:41224edae7ad", "16:5083fc3aa289", "16:5859a7c15e67", "16:66548d933cbf", "16:6a4b30778015",
    "16:6c9c055807c0", "16:6ccba1a0df36", "16:6f6e9753a89f", "16:72dfa40019a5", "16:75e399142f73",
    "16:7f91de9ab3ac", "16:90ee981ff834", "16:9373de201bce", "16:95313d210307", "16:9cfb5b5b18c8",
    "16:9d5baf053658", "16:a1b7d86de2be", "16:a2c696a86d91", "16:a8719caf0c60", "16:bf079b0123cb",
    "16:c2fad0aa86f5", "16:cd3d514d49d7", "16:d2b6d911eac8", "16:d5492e9f0c9c", "16:f260c5fb982c",
    "17:001fb02f594f", "17:0b890304ad4d", "17:4078208973bc", "17:4bbc401c4522", "17:5a0da35321e8",
    "17:76d68d9a7408", "17:8220c9fee5ec", "17:87a307e5575f", "17:8ac06d524d20", "17:8b9ff877028c",
    "17:9818927bec43", "17:acde9db6b35d", "17:b15511319755", "17:bb630e74bd89", "17:c5125ec72f5b",
    "17:dc22f173d301", "17:f4615a3fcdb9", "17:f9677c6f461c", "17:fd16f7fc5e82", "17:ff84674de6dc",
    "18:02d003e26327", "18:131f6e61db2b", "18:3054e7d10c2a", "18:312b7b736953", "18:3d1975dd1eba",
    "18:4e144690dde9", "18:5a014a36d4ae", "18:63ea97e6da2e", "18:64d796cbca83", "18:69344373b24e",
    "18:7d6b939516a5", "18:8167b73998b5", "18:8b03c10cf53f", "18:984f11f67219", "18:9f6226815834",
    "18:9f878e283f31", "18:b2f3a8ad72fe", "18:b674c5b9877e", "18:cdf1db89bc1a", "18:e0894412298e",
    "18:e361779668eb", "19:0d964f3af3ff", "19:14ee09f759d1", "19:3674eb056060", "19:4cec3f2e5098",
    "19:750e36c22a3b", "19:7a29b61dd6fd", "19:7c82c57ed597", "19:7cb15f6e7c4c", "19:8455fbb80228",
    "19:8fb54643631d", "19:a608e39c29a0", "19:c3c4dc5cffe8", "19:c8a5787de138", "19:ee17eea53c19",
    "19:f0f144fb804c", "20:6f9f727c59ba", "20:7f71646f15a1", "20:afc80c86a46c", "20:b34eafce023b",
    "21:0e91ff0275ec", "21:19f98a2aa98c", "21:43e8dae57db2", "21:6036f01a9ad4", "21:67a0081f2eda",
    "21:67fe1915a2f6", "21:6bb994d5b6bc", "21:87cab588c766", "21:9fb58645e513", "21:ae4976e0fde3",
    "21:b154293e0da9", "21:d6f5cd88f7aa", "21:ecd729382837", "22:07f3762c7a70", "22:2061b8e607af",
    "22:21c9706750e6", "22:2262c0bd1e01", "22:404450a440de", "22:4f54d20daee1", "22:58b0424d37da",
    "22:7cfca9fd549d", "22:8fb1af0e4fa2", "22:947c12e0064c", "22:a75ee8e4fa6b", "22:a9920e04c7be",
    "22:b0aa9ae239d0", "23:02d8c3e0252e", "23:033912f0b556", "23:06d457828a9e", "23:2cd8fba4b2e9",
    "23:5586199cf965", "23:62747f1e2982", "23:7ea72831bbd4", "23:a19a414923c5", "23:a282f5741d85",
    "23:bfcfa4318ff2", "23:e375bae5ff9c", "23:e952463fee14", "24:313b47dcedaf", "24:3efccd60db28",
    "25:1fcac3b43483", "25:8165f1b5e8a3", "26:4e167cf03060", "26:f98dc686eaab", "27:6d631fe82533",
    "27:b02f23686c8e", "27:bf9eb2387320", "27:bffd51260300", "28:acf22929c61c", "28:d2b12ddd40b9",
    "28:f2d8c6e9dda4", "2:135e609829c2", "2:8df0b3fd66a6", "2:a8cdcf612b9c", "2:f3370384ddff",
    "30:ec57ea60ad17", "31:48feae812538", "31:4f9ea6639004", "31:d101587b831c", "31:dfcc0274a27a",
    "3:4741aac82c01", "4:2152ebe01cec", "4:225196b5f371", "4:65329f889fae", "4:701a15ae96fb",
    "5:023aab1fb1c3", "5:1128f7bc6344", "5:4b69c5b922df", "5:b2a1783da0a9", "5:f251f45f8a9b",
    "6:8055e5cdb06f", "6:8586510cac11", "6:ed05dd4d068f", "7:06ab8b60c0cc", "7:68679eedeef0",
    "7:878c8de29820", "7:a2abcc658ba6", "7:c3509ec5630e", "7:e6313f4e3d9b", "7:f3a5990c5ba5",
    "8:2faeae97a0c9", "8:439d2d83d7c8", "8:776d17601eca", "8:86347cac3a3f", "8:8c6ad88ccb67",
    "8:b12e14e5a422", "8:d074b0358556", "8:daeba72ecb85", "8:f570c731a139", "9:055c5e3e02a6",
    "9:70666b651054", "9:795b104abe3e", "9:89907cfb4d9e", "9:8b80d8ee4b10", "9:92ee02d8c2a4",
    "9:9debad18e613", "9:a6e224fad446", "9:aeb9a6d7d904", "9:c95570091a61", "9:d8380156a309",
    "9:ec1bc03602e1",
))

SCAN_EXT = frozenset((
    ".py", ".md", ".json", ".html", ".htm", ".css", ".js", ".txt",
    ".yml", ".yaml", ".toml", ".cfg", ".ini", ".sh", ".csv",
))
SKIP_DIRS = frozenset((".git", "__pycache__", "node_modules", ".venv", ".idea"))
SKIP_FILES = frozenset(("banned_words.py",))
MAX_BYTES = 4 * 1024 * 1024

_QUOTED = re.compile(r'"([^"\n]{1,80})"' r"|'([^'\n]{1,80})'" r"|`([^`\n]{1,80})`")


def _fold_case(s: str) -> str:
    """小写化但保持长度不变（个别字符小写后会变长，会打乱下标）。"""
    out = []
    for ch in s:
        low = ch.lower()
        out.append(low if len(low) == 1 else ch)
    return "".join(out)


def _digest(s: str, size: int) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:size]


def _line_of(text: str, at: int) -> int:
    return text.count("\n", 0, at) + 1


def _internal_hits(text: str):
    """按长度开窗比对摘要；2 字前缀做预筛，免得每个位置都算全部长度。"""
    folded = _fold_case(text)
    size = len(folded)
    for i in range(size - 1):
        if _digest(folded[i:i + 2], 8) not in _INTERNAL_PREFIX:
            continue
        for width in _INTERNAL_LENGTHS:
            if i + width > size:
                break
            if "%d:%s" % (width, _digest(folded[i:i + width], 12)) in _INTERNAL:
                yield i, text[i:i + width]


def scan_text(rel: str, text: str) -> List[str]:
    """扫一段文本，返回违规描述（空列表即通过）。"""
    seen = set()
    hits = []

    def add(at, msg):
        key = (at, msg)
        if key not in seen:
            seen.add(key)
            hits.append((at, "%s:%d：%s" % (rel, _line_of(text, at), msg)))

    lowered = _fold_case(text)
    for word in BANNED_SUBSTRING:
        needle = _fold_case(word)
        at = lowered.find(needle)
        while at >= 0:
            add(at, "出现本机路径或明文禁用串「%s」" % text[at:at + len(word)])
            at = lowered.find(needle, at + 1)

    for at, word in _internal_hits(text):
        add(at, "出现内部标识符「%s」，对外发布的文件里不许有" % word)

    tokens = frozenset(BANNED_TOKEN)
    for m in _QUOTED.finditer(text):
        literal = m.group(1) or m.group(2) or m.group(3) or ""
        if literal in tokens:
            add(m.start(), "通用枚举词「%s」不得作为 JSON 键或字面量出现，请换成自定的名字" % literal)

    return [msg for _, msg in sorted(hits)]


def scan_dir(path) -> List[str]:
    """扫一个目录（递归），返回违规描述列表；空列表即通过。"""
    root = os.path.abspath(path)
    if os.path.isfile(root):
        return scan_text(os.path.basename(root), _read(root)) if _wanted(root) else []
    if not os.path.isdir(root):
        return ["找不到目录：%s" % path]
    found = []
    for here, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            full = os.path.join(here, name)
            if not _wanted(full):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            found.extend(scan_text(rel, _read(full)))
    return found


def _wanted(full: str) -> bool:
    name = os.path.basename(full)
    if name in SKIP_FILES:
        return False
    if os.path.splitext(name)[1].lower() not in SCAN_EXT:
        return False
    try:
        return os.path.getsize(full) <= MAX_BYTES
    except OSError:
        return False


def _read(full: str) -> str:
    try:
        with open(full, "r", encoding="utf-8-sig") as f:
            return f.read()
    except (UnicodeDecodeError, OSError):
        return ""


def main(argv=None):
    parser = argparse.ArgumentParser(prog="banned_words.py", description="禁用词静态闸")
    parser.add_argument("path", nargs="?", default=".", help="要扫描的目录（默认当前目录）")
    args = parser.parse_args(argv)
    hits = scan_dir(args.path)
    for line in hits:
        print(line)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
