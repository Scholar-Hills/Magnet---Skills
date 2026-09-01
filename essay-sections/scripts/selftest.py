#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""essayctl.py 自测：在临时目录里建分段写作工作区，走 init → import → assemble →
outline add → context → review add → reflect add → reading add → version → status →
report → export → check 全流程，逐条验证 19 条闸门的正反例与攻击回归，最后跑禁用词静态闸。

用法：python3 scripts/selftest.py
不依赖 examples/ 目录；examples/ 还没建时对应用例自动跳过（计通过）。
所有稿件、题目、评语都是合成的，跑完临时目录删除。
"""

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "essayctl.py")
PY = sys.executable

SLUG = "remote-work-cities-01"

# ---------------------------------------------------------------- 合成稿件

TITLE = "远程办公会把人从大城市推出去吗"

P_OPEN = ("过去三年里，远程办公从临时应急变成了不少公司的常规安排，随之而来的问题是：如果上班不必到办公室，"
          "人们还会不会继续挤在房价最高的那几座城市里。本文认为，远程办公改变的是人们挑住处的顺序，"
          "而不是把大城市清空。")

P_B1 = ("先看真的搬走的那部分人。通勤时间一旦从每天两小时降到零，住处离公司多远就不再是硬约束，"
        "于是有人把家搬到房租只有原来三分之一的中小城市，省下来的钱换成更大的房子和离家更近的公园。"
        "这类搬迁在公开的租房登记里能看到，但它集中在收入稳定、工作又完全可以线上完成的那一小群人身上。")

P_B2 = ("再看留下来的人。城市贵，贵在的不只是写字楼，还有随手可约的同行、临时能补上的托育、"
        "半夜仍然开门的医院。这些东西没法通过一根网线送到县城，所以哪怕一年只回办公室十几天，"
        "很多人仍然愿意为这些配套付房租。")

P_B3 = ("第三种情况最容易被忽略：搬走的人未必搬得很远。多数人挑的是同一都市圈里通勤一小时开外的卫星城，"
        "既躲开了核心区的房价，又保留了随时进城的能力。从统计口径上看他们离开了城市，"
        "从生活半径上看他们一步也没离开。")

P_B4 = ("远程办公还改变了公司这一头。企业发现工位可以按需租，于是把面积压缩，"
        "把省下来的预算换成几次全员见面。办公楼的空置率升高了，但人流并没有等比例消失，"
        "只是从每天摊薄成了每月几次的高峰。")

P_B5 = ("反方最强的证据是几座科技城市的租金确实掉过一截。但把时间拉长两年再看，"
        "掉下去的租金又爬了回来，掉得最狠的恰好是那些靠单一产业撑着的城市。"
        "这说明松动的是产业结构，不是城市本身。")

P_B6 = ("最后要承认一个边界：以上讨论只覆盖那些工作能搬到线上的岗位。"
        "餐饮、护理、施工、快递这些必须到场的工作占了城市就业的大半，"
        "他们的住处选择跟远程办公一点关系也没有，任何关于人口外流的结论都不能替他们下。")

P_CLOSE = ("综合来看，远程办公松开了住处与工位之间的那根绳子，却没有解开城市与机会之间的那根。"
           "它让一部分人得以重新挑一次住处，也让另一部分人第一次算清了自己为什么留下。"
           "把这两件事一起看，才不至于把一次挑法的变化误读成一场搬迁。")

P_TAIL = ("（写完之后补的一句话：数据部分还要再核一遍出处，先记在这里免得忘。）")

SRC_MD = "# %s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n\n%s\n" % (
    TITLE, P_OPEN, P_B1, P_B2, P_B3, P_B4, P_B5, P_B6, P_CLOSE, P_TAIL)

# 块号：1=标题 2=开头 3..8=正文六段 9=结论 10=尾注
GROUPS_OK = {"intro": [2], "body": [[3], [4], [5], [6], [7], [8]], "conclusion": [9]}
SEGMENTS = ["intro", "body-01", "body-02", "body-03", "body-04", "body-05", "body-06", "conclusion"]

BARE = "这一行是没有被任何标签包住的裸文本。"
SRC_HTML = ("<div class=\"paper\">\n<h1>%s</h1>\n<p>%s</p>\n%s\n<p>%s</p>\n<p>%s</p>\n</div>\n"
            % (TITLE, P_OPEN, BARE, P_B1, P_CLOSE))

# ---------------------------------------------------------------- docx 合成

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
BOX_LINE = "这句话待在一个文本框里，正文并没有它的位置。"
CELL_A = "表格左边一格"
CELL_B = "表格右边一格"
DOCX_HEAD = "远程办公与城市（Word 版）"
DOCX_H2 = "一、谁真的搬走了"
DOCX_H3 = "（一）留下来的理由"


def _wp(text, style=None, bold=False):
    pr = ""
    if style:
        pr = "<w:pPr><w:pStyle w:val=\"%s\"/></w:pPr>" % style
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return "<w:p>%s<w:r>%s<w:t>%s</w:t></w:r></w:p>" % (pr, rpr, text)


def docx_bytes():
    """合成一个只带 word/document.xml 的 .docx：标题、正文、文本框（Choice + Fallback 各一份）、表格。"""
    box = ("<w:txbxContent><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:txbxContent>" % BOX_LINE)
    para_with_box = ("<w:p><w:r><w:t>%s</w:t></w:r>"
                     "<w:r><mc:AlternateContent><mc:Choice Requires=\"wps\">%s</mc:Choice>"
                     "<mc:Fallback>%s</mc:Fallback></mc:AlternateContent></w:r></w:p>"
                     % (P_B2, box, box))
    table = ("<w:tbl><w:tr><w:tc>%s</w:tc><w:tc>%s</w:tc></w:tr></w:tbl>"
             % (_wp(CELL_A), _wp(CELL_B)))
    body = "".join([
        _wp(DOCX_HEAD, style="Heading1"),
        _wp(P_OPEN),
        _wp(DOCX_H2, style="Heading2"),
        _wp(P_B1),
        _wp(DOCX_H3, style="Heading3"),
        para_with_box,
        table,
        _wp("小结", bold=True),
        _wp(P_CLOSE),
    ])
    xml = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
           "<w:document xmlns:w=\"%s\" xmlns:mc=\"%s\"><w:body>%s</w:body></w:document>"
           % (W, MC, body))
    types = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
             "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
             "<Default Extension=\"xml\" ContentType=\"application/xml\"/></Types>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr("[Content_Types].xml", types)
        pack.writestr("word/document.xml", xml)
    return buf.getvalue()


# ---------------------------------------------------------------- 本批次追加禁用表
# 共享的 banned_words.py 不动（五份同字节）；这一批新拉黑的生产标识放在这里做静态闸。
# 每串拆成两半再拼：本文件自己也要过共享禁用词表那一关，写成整串就会被它逮住
# （banned_words.py 里的 "/" + "Users" + "/" 是同一个写法）。
_BATCH_PARTS = (
    ("__int", "ro__"), ("__conc", "lusion__"), ("review", "History"),
    ("quality", "Reviews"), ("aiSug", "gestions"), ("section", "Snapshot"),
    ("trigger", "Score"), ("question", "GenCount"), ("read", "ability"),
    ("vertical", "Relevance"), ("horizontal", "Relevance"), ("potential", "-source"),
    ("common", "-phrase"), ("citation", "-needed"), ("core", "Lens"),
    ("learning", "Objectives"), ("slideDeck", "Shell"), ("STYLE", "_SEEDS"),
    ("DENSITY", "_TEXT"), ("data-image", "-request"), ("data-cos", "-key"),
    ("gen", "-image"), ("img", "-hint"), ("Cos", "Image"),
    ("application", "Key"), ("essay-quality", "-review"),
)
BATCH_SUBSTRINGS = tuple(head + tail for head, tail in _BATCH_PARTS)
# 这两个是生产的通用枚举名，做子串会把散文全误报，按 banned_words.py 第 3 层的口径只查引号字面量。
BATCH_LITERALS = ("scale", "kind")
_QUOTED = re.compile(r'"([^"\n]{1,80})"' r"|'([^'\n]{1,80})'" r"|`([^`\n]{1,80})`")
SCAN_EXT = frozenset((".py", ".md", ".json", ".html", ".htm", ".css", ".js", ".txt", ".yml", ".yaml"))
SCAN_SKIP_DIRS = frozenset((".git", "__pycache__", "node_modules", ".venv"))


# ---------------------------------------------------------------- 小工具

class Failed(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Failed(msg)


def run(cwd, *argv):
    proc = subprocess.run([PY, TOOL] + [str(a) for a in argv], cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (proc.returncode, proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def ok(cwd, *argv):
    rc, out, err = run(cwd, *argv)
    check(rc == 0, "%s 应退出 0，rc=%d\n%s%s" % (" ".join(str(a) for a in argv), rc, out, err))
    return out


def write(path, text):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_json(path, obj):
    write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def write_bytes(path, blob):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(blob)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load(path):
    return json.loads(read(path))


def lines_of(path):
    return [ln for ln in read(path).split("\n") if ln.strip()]


def ws_of(root):
    return os.path.join(root, "essays", SLUG)


def norm(text):
    return re.sub(r"\s+", " ", text).strip()


def canon(obj):
    """跟 essayctl.canonical 同口径：账本行就是这么写出来的。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 建工作区

def new_ws(root, slug=SLUG):
    """建一个空工作区并写好题目背景，返回工作区绝对路径。"""
    ok(root, "init", slug, "--title", TITLE, "--genre", "议论文", "--level", "hs",
       "--setting", "untimed", "--target-words", "900",
       "--background", "校内写作课的期末长作业，允许查资料。",
       "--thesis", "远程办公改变的是挑住处的顺序，而不是把大城市清空。")
    ws = os.path.join(root, "essays", slug)
    check(os.path.isdir(ws), "init 应建出 essays/<slug>")
    return ws


def built(root, src=None, groups=None, slug=SLUG, name="draft.md"):
    """init → import → assemble，返回工作区路径。"""
    ws = new_ws(root, slug)
    src_path = os.path.join(root, name)
    write(src_path, SRC_MD if src is None else src)
    ok(root, "import", slug, src_path)
    write_json(os.path.join(ws, "inbox", "groups.json"), GROUPS_OK if groups is None else groups)
    ok(root, "assemble", slug, "--from", os.path.join(ws, "inbox", "groups.json"))
    return ws


def ctx(root, segment, slug=SLUG):
    """跑 context 拿到上下文包。"""
    return json.loads(ok(root, "context", slug, segment))


DEFAULT_NOTE = ("这一段把论点摆出来了，证据也贴着论点走，"
                "但收尾那句还停在复述上，没有把它推到下一段要谈的方向。")


def review_payload(root, segment, scores=None, note=None, quotes=None, extra=None):
    pack = ctx(root, segment)
    body = {"contextHash": pack["contextHash"],
            "scores": scores or {"language": 4, "answersSubquestion": 3, "advancesThesis": 4},
            "note": note or (DEFAULT_NOTE + "（%s）" % segment),
            "quotes": quotes if quotes is not None else [pack["text"][10:40]]}
    if extra:
        body.update(extra)
    return body


def add_review(root, ws, segment, **kw):
    path = os.path.join(ws, "inbox", "review.json")
    write_json(path, review_payload(root, segment, **kw))
    return run(root, "review", "add", SLUG, segment, "--from", path)


def add_review_ok(root, ws, segment, **kw):
    rc, out, err = add_review(root, ws, segment, **kw)
    check(rc == 0, "review add %s 应退出 0，rc=%d\n%s%s" % (segment, rc, out, err))
    return out


def ledger_rows(ws, segment):
    path = os.path.join(ws, "ledger", "%s.jsonl" % segment)
    return [json.loads(ln) for ln in lines_of(path)]


# ================================================================ 用例

def t_doctor_init(root):
    """doctor 能跑；init 建出骨架；稿号非法（含目录穿越）退出 2。"""
    out = ok(root, "doctor")
    check("essayctl" in out or "Python" in out, "doctor 应打印环境信息：\n%s" % out)
    ws = new_ws(root)
    for name in ("essay.json", "outline.jsonl", "reflections.jsonl"):
        check(os.path.isfile(os.path.join(ws, name)), "init 应建出 %s" % name)
    for name in ("sections", "ledger", "inbox", "readings", "versions"):
        check(os.path.isdir(os.path.join(ws, name)), "init 应建出 %s/" % name)
    meta = load(os.path.join(ws, "essay.json"))
    check(meta.get("title") == TITLE and meta.get("thesis"), "essay.json 应带题目与主论点：%r" % meta)

    for bad in ("../escape", "Upper", "with space", "a" * 65, ""):
        rc, out, err = run(root, "init", bad)
        check(rc == 2, "非法稿号 %r 应退出 2，实际 %d\n%s%s" % (bad, rc, out, err))
    rc, out, err = run(root, "context", SLUG, "../../etc")
    check(rc == 2, "非法分区名应退出 2，实际 %d\n%s%s" % (rc, out, err))
    return "init 建骨架；稿号与分区名一步不许穿越目录"


def t_import_md_offsets(root):
    """import 为每块记 [start,end) 字节偏移，原子按序无缝覆盖全文。"""
    ws = new_ws(root)
    src = os.path.join(root, "draft.md")
    write(src, SRC_MD)
    out = ok(root, "import", SLUG, src)
    view = json.loads(out)
    check(len(view["blocks"]) == 10, "应切出 10 块，实际 %d：\n%s" % (len(view["blocks"]), out))
    check(view["blocks"][0]["heading"] is True, "第 1 块（# 标题）应判为标题：%r" % view["blocks"][0])
    check(sum(1 for b in view["blocks"] if b["heading"]) == 1, "只有一块是标题：%r" % view["blocks"])

    meta = load(os.path.join(ws, "blocks.json"))
    raw = open(os.path.join(ws, "source.txt"), "rb").read()
    check(meta["bytes"] == len(raw), "blocks.json 记的字节数应与 source.txt 一致")
    at = 0
    rebuilt = b""
    for atom in meta["atoms"]:
        check(atom["start"] == at, "原子必须首尾相接，第 %d 个断了：%r" % (atom["i"], atom))
        rebuilt += raw[atom["start"]:atom["end"]]
        at = atom["end"]
    check(at == len(raw) and rebuilt == raw, "全部原子拼回应等于原文字节")
    numbered = [a for a in meta["atoms"] if a["role"] == "block"]
    check([a["no"] for a in numbered] == list(range(1, 11)), "块号应是 1..10：%r" % [a["no"] for a in numbered])
    return "10 块 + 1 个标题，原子首尾相接拼回等于原文"


def t_assemble_identity(root):
    """assemble 恒等式：段文本 + 未纳入片段按偏移拼回 == 原文字节；漏号并入相邻段。"""
    ws = built(root)
    raw = open(os.path.join(ws, "source.txt"), "rb").read()
    meta = load(os.path.join(ws, "essay.json"))
    check([s["name"] for s in meta["segments"]] == SEGMENTS,
          "应拆出 8 段：%r" % [s["name"] for s in meta["segments"]])

    pieces = []
    for seg in meta["segments"]:
        pieces.append((seg["start"], seg["end"]))
    for frag in meta["outside"]:
        pieces.append((frag["start"], frag["end"]))
    pieces.sort()
    at = 0
    rebuilt = b""
    for start, end in pieces:
        check(start == at, "段与未纳入片段之间不许有缝：%d != %d" % (start, at))
        rebuilt += raw[start:end]
        at = end
    check(at == len(raw) and rebuilt == raw, "恒等式不成立：拼回来的不等于原文")

    for seg in meta["segments"]:
        text = read(os.path.join(ws, "sections", "%s.md" % seg["name"]))
        check(text.encode("utf-8") == raw[seg["start"]:seg["end"]],
              "%s 的正文应等于按偏移切出来的原文片段" % seg["name"])

    report = read(os.path.join(ws, "split-report.md"))
    check("未纳入分段" in report, "split-report.md 应有「未纳入分段」一节：\n%s" % report)
    check(TITLE in report, "标题那一块没被分配，必须逐条列进未纳入清单：\n%s" % report)
    check(P_TAIL[:14] in read(os.path.join(ws, "sections", "conclusion.md")),
          "落在最末段之后的未分配块应并入末段")
    check("已并入" in report, "split-report.md 应交代未分配块并进了哪一段：\n%s" % report)

    out = ok(root, "status", SLUG)
    check("未纳入" in out, "status 应显示未纳入条数：\n%s" % out)
    return "8 段 + 未纳入片段拼回等于原文；漏号并入末段并写进报告"


def t_assemble_bad_ids(root):
    """重复号与越界号丢弃，恒等式照样成立。"""
    groups = {"intro": [2], "body": [[3, 3], [4], [5, 99], [6], [7], [8]], "conclusion": [9, 2]}
    ws = built(root, groups=groups)
    raw = open(os.path.join(ws, "source.txt"), "rb").read()
    meta = load(os.path.join(ws, "essay.json"))
    total = b""
    spans = [(s["start"], s["end"]) for s in meta["segments"]] + \
            [(f["start"], f["end"]) for f in meta["outside"]]
    for start, end in sorted(spans):
        total += raw[start:end]
    check(total == raw, "丢弃重复号与越界号之后，恒等式仍必须成立")
    report = read(os.path.join(ws, "split-report.md"))
    check("丢弃" in report, "split-report.md 应列出被丢弃的段号：\n%s" % report)
    check("99" in report, "越界号 99 应被记下来：\n%s" % report)
    intro = read(os.path.join(ws, "sections", "intro.md"))
    check(P_OPEN[:12] in intro, "第 2 块只能用一次，仍归开头段")
    return "重复号与越界号丢弃、写进报告，恒等式不破"


def t_assemble_html_wrapper(root):
    """HTML 包裹层与裸文本进「未纳入分段」，恒等式成立。"""
    ws = new_ws(root)
    src = os.path.join(root, "draft.html")
    write(src, SRC_HTML)
    out = ok(root, "import", SLUG, src)
    view = json.loads(out)
    previews = [b["preview"] for b in view["blocks"]]
    check(any(BARE[:8] in p for p in previews), "裸文本应自成一块：%r" % previews)
    groups = {"intro": [2], "body": [[4]], "conclusion": [5]}
    write_json(os.path.join(ws, "inbox", "groups.json"), groups)
    ok(root, "assemble", SLUG, "--from", os.path.join(ws, "inbox", "groups.json"))
    raw = open(os.path.join(ws, "source.txt"), "rb").read()
    meta = load(os.path.join(ws, "essay.json"))
    spans = [(s["start"], s["end"]) for s in meta["segments"]] + \
            [(f["start"], f["end"]) for f in meta["outside"]]
    check(b"".join(raw[a:b] for a, b in sorted(spans)) == raw, "HTML 恒等式不成立")
    report = read(os.path.join(ws, "split-report.md"))
    check("<div" in report and "</div>" in report, "包裹层必须逐条列进未纳入清单：\n%s" % report)
    return "包裹层与裸文本不静默丢，HTML 恒等式成立"


def t_assemble_fallback(root):
    """groups 缺 body 数组 / 不是对象 → 整段导入并标 fallback。"""
    ws = new_ws(root)
    src = os.path.join(root, "draft.md")
    write(src, SRC_MD)
    ok(root, "import", SLUG, src)
    path = os.path.join(ws, "inbox", "groups.json")
    write_json(path, {"intro": [2]})
    out = ok(root, "assemble", SLUG, "--from", path)
    check("fallback" in out or "整段导入" in out, "缺 body 应整段导入：\n%s" % out)
    meta = load(os.path.join(ws, "essay.json"))
    check(meta.get("fallback") is True, "essay.json 应标 fallback：%r" % meta)
    check(len(meta["segments"]) == 1, "整段导入只该有一段：%r" % meta["segments"])
    raw = open(os.path.join(ws, "source.txt"), "rb").read()
    seg = meta["segments"][0]
    check(raw[seg["start"]:seg["end"]] == raw, "整段导入的那一段应覆盖全文")

    other = "remote-work-cities-02"
    ws2 = new_ws(root, other)
    ok(root, "import", other, src)
    path2 = os.path.join(ws2, "inbox", "groups.json")
    write(path2, "[1, 2, 3]\n")
    ok(root, "assemble", other, "--from", path2)
    meta2 = load(os.path.join(ws2, "essay.json"))
    check(meta2.get("fallback") is True and len(meta2["segments"]) == 1,
          "groups 不是对象时也该整段导入：%r" % meta2["segments"])
    return "groups 缺 body 数组 / 不是对象时都整段导入并标 fallback"


def t_import_docx(root):
    """docx：只用 zipfile + xml；文本框读一次不读三份；表格与文本框进未纳入清单。"""
    ws = new_ws(root)
    src = os.path.join(root, "draft.docx")
    write_bytes(src, docx_bytes())
    out = ok(root, "import", SLUG, src)
    view = json.loads(out)
    source = read(os.path.join(ws, "source.txt"))
    check(source.count(BOX_LINE) == 1,
          "文本框的字只该出现一次（Choice 与 Fallback 不许各读一遍），实际 %d 次" % source.count(BOX_LINE))
    heads = [b for b in view["blocks"] if b["heading"]]
    check(len(heads) == 4, "Heading1/2/3 与整段加粗的短句都算标题，应有 4 个：%r" % heads)
    check(len(view["blocks"]) == 8, "正文应切出 8 块（表格与文本框不算块），实际 %d" % len(view["blocks"]))
    check([b["no"] for b in heads] == [1, 3, 5, 7], "标题应落在第 1/3/5/7 块：%r" % heads)

    groups = {"intro": [2], "body": [[3, 4], [5, 6]], "conclusion": [8]}
    write_json(os.path.join(ws, "inbox", "groups.json"), groups)
    ok(root, "assemble", SLUG, "--from", os.path.join(ws, "inbox", "groups.json"))
    report = read(os.path.join(ws, "split-report.md"))
    for text in (BOX_LINE, CELL_A, CELL_B):
        check(text in report, "「%s」未纳入分段，必须出现在清单里：\n%s" % (text, report))
    check("表格" in report and "文本框" in report, "未纳入清单应注明来源是表格还是文本框")
    raw = open(os.path.join(ws, "source.txt"), "rb").read()
    meta = load(os.path.join(ws, "essay.json"))
    spans = [(s["start"], s["end"]) for s in meta["segments"]] + \
            [(f["start"], f["end"]) for f in meta["outside"]]
    check(b"".join(raw[a:b] for a, b in sorted(spans)) == raw, "docx 恒等式不成立")
    return "docx 8 块 4 标题（三级标题 + 加粗短句），文本框只读一次，表格与文本框进未纳入清单"


def t_outline_rounds(root):
    """拆题闸：初始 6–10、增补 ≤4、小写去重、空题拒收、封顶 4 轮。"""
    ws = new_ws(root)
    path = os.path.join(ws, "inbox", "outline.json")
    before = read(os.path.join(ws, "outline.jsonl"))

    write_json(path, {"items": ["第一问", "第二问", "第三问", "第四问", "第五问"]})
    rc, out, err = run(root, "outline", "add", SLUG, "--from", path)
    check(rc == 1, "初始模式只有 5 条应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check(read(os.path.join(ws, "outline.jsonl")) == before, "被拒的一轮不许落盘")

    write_json(path, {"items": ["A" + str(i) for i in range(11)]})
    rc, out, err = run(root, "outline", "add", SLUG, "--from", path)
    check(rc == 1, "初始模式 11 条应退出 1，rc=%d" % rc)

    write_json(path, {"items": ["远程办公省下的通勤时间去了哪里", "谁真的搬走了", "谁留下了",
                                "卫星城算不算离开", "公司这一头怎么变", "反方证据站得住吗"]})
    ok(root, "outline", "add", SLUG, "--from", path)
    check(len(lines_of(os.path.join(ws, "outline.jsonl"))) == 1, "初始一轮 = 一行")
    meta = load(os.path.join(ws, "essay.json"))
    body = [s for s in meta["segments"] if s["name"].startswith("body-")]
    check(len(body) == 6, "6 条子问题应建出 6 个正文段：%r" % meta["segments"])
    check(os.path.isfile(os.path.join(ws, "sections", "body-06.md")), "应建出 body-06.md 空壳")
    check(body[0]["subquestion"] == "远程办公省下的通勤时间去了哪里", "子问题应按序绑到正文段")
    check(not os.path.exists(path), "载荷消费后应删除")

    write_json(path, {"items": ["谁真的搬走了", "  谁留下了  "]})
    rc, out, err = run(root, "outline", "add", SLUG, "--from", path)
    check(rc == 1, "整轮都是重复题应退出 1，rc=%d\n%s" % (rc, out))

    write_json(path, {"items": ["新的一问甲", ""]})
    rc, out, err = run(root, "outline", "add", SLUG, "--from", path)
    check(rc == 1, "空题应拒收，rc=%d" % rc)

    write_json(path, {"items": ["新一问甲", "新一问乙", "新一问丙", "新一问丁", "新一问戊"]})
    rc, out, err = run(root, "outline", "add", SLUG, "--from", path)
    check(rc == 1, "增补 5 条超过 4 条上限应退出 1，rc=%d" % rc)

    for i in range(3):
        write_json(path, {"items": ["增补第%d轮的一问" % (i + 1)]})
        ok(root, "outline", "add", SLUG, "--from", path)
    check(len(lines_of(os.path.join(ws, "outline.jsonl"))) == 4, "应恰好 4 轮")

    frozen = read(os.path.join(ws, "outline.jsonl"))
    write_json(path, {"items": ["第五轮不许有"]})
    rc, out, err = run(root, "outline", "add", SLUG, "--from", path)
    check(rc == 1, "第 5 轮必须被拒，rc=%d\n%s%s" % (rc, out, err))
    check(read(os.path.join(ws, "outline.jsonl")) == frozen, "被拒的第 5 轮不许改动账本字节")
    return "初始 6–10、增补 ≤4、去重与空题拒收、第 5 轮被拒且字节不变"


def t_outline_bind(root):
    """bind 模式：先贴稿拆好段，再补子问题——条数必须正好等于已有正文段数。"""
    groups = {"intro": [2], "body": [[3, 4, 5], [6, 7, 8]], "conclusion": [9]}
    ws = built(root, groups=groups)
    meta = load(os.path.join(ws, "essay.json"))
    body = [s for s in meta["segments"] if s["name"].startswith("body-")]
    check(len(body) == 2, "这一轮先拆成 2 个正文段：%r" % [s["name"] for s in meta["segments"]])
    check(body[0]["subquestion"] == "", "还没绑之前正文段没有子问题：%r" % body[0])
    before_hash = ctx(root, "body-01")["contextHash"]

    # 反例：2 个正文段却给 3 条，拒收且工作区一个字节不许动
    frozen_essay = read(os.path.join(ws, "essay.json"))
    frozen_outline = read(os.path.join(ws, "outline.jsonl"))
    path = os.path.join(ws, "inbox", "outline.json")
    write_json(path, {"items": ["谁真的搬走了", "谁留下了", "多出来的一条"]})
    rc, out, err = run(root, "outline", "add", SLUG, "--from", path)
    check(rc == 1, "2 个正文段给 3 条子问题应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check(read(os.path.join(ws, "essay.json")) == frozen_essay, "被拒的一轮不许改 essay.json")
    check(read(os.path.join(ws, "outline.jsonl")) == frozen_outline, "被拒的一轮不许写账本")
    check(ctx(root, "body-01")["contextHash"] == before_hash, "被拒的一轮不许影响 contextHash")

    # 正例：正好 2 条，按序绑上去
    write_json(path, {"items": ["谁真的搬走了", "谁留下了"]})
    out = ok(root, "outline", "add", SLUG, "--from", path)
    check("bind" in out, "这一轮应走 bind 模式：\n%s" % out)
    check(len(lines_of(os.path.join(ws, "outline.jsonl"))) == 1, "bind 也占一轮")
    row = json.loads(lines_of(os.path.join(ws, "outline.jsonl"))[0])
    check(row["mode"] == "bind", "账本行应记下 mode=bind：%r" % row)

    meta = load(os.path.join(ws, "essay.json"))
    names = [s["name"] for s in meta["segments"]]
    check(names == ["intro", "body-01", "body-02", "conclusion"],
          "绑定不该凭空多出正文段：%r" % names)
    body = dict((s["name"], s["subquestion"]) for s in meta["segments"])
    check(body["body-01"] == "谁真的搬走了" and body["body-02"] == "谁留下了",
          "子问题应按序绑到正文段：%r" % body)
    pack = ctx(root, "body-01")
    check(pack["subquestion"] == "谁真的搬走了", "context 应带上刚绑的子问题：%r" % pack["subquestion"])
    check(pack["contextHash"] != before_hash, "子问题进了 contextHash，绑完哈希必须变")
    for name in ("intro", "conclusion"):
        text = read(os.path.join(ws, "sections", "%s.md" % name))
        check(text.strip(), "绑定不许把已有的 %s 正文清空" % name)
    out = ok(root, "check", SLUG)
    check("0 个 ERROR" in out, "绑完 check 应 0 ERROR：\n%s" % out)
    return "bind：2 段给 3 条拒且字节不变；正好 2 条按序绑上，contextHash 随之变，check 0 ERROR"


def t_thin_segment(root):
    """评审准入闸：纯文本不足 10 字，context 拒绝输出、review add 拒收。"""
    ws = built(root)
    write(os.path.join(ws, "sections", "body-02.md"), "<p>太短</p>\n")
    rc, out, err = run(root, "context", SLUG, "body-02")
    check(rc == 1, "不足 10 字的分区 context 应退出 1，rc=%d\n%s%s" % (rc, out, err))
    path = os.path.join(ws, "inbox", "review.json")
    write_json(path, {"contextHash": "0" * 64, "scores": {"language": 3, "answersSubquestion": 3,
                                                          "advancesThesis": 3},
                      "note": "随便写点", "quotes": ["太短"]})
    rc, out, err = run(root, "review", "add", SLUG, "body-02", "--from", path)
    check(rc == 1, "不足 10 字的分区 review add 应退出 1，rc=%d\n%s%s" % (rc, out, err))
    return "分区纯文本 <10 字：context 与 review add 都退出 1"


def t_context_shape(root):
    """context 输出的结构与 contextHash 成分。"""
    ws = built(root)
    pack = ctx(root, "body-01")
    check(set(pack) == {"segment", "text", "subquestion", "thesis", "background",
                        "reflections", "previousReview", "contextHash"},
          "context 顶层键对不上：%r" % sorted(pack))
    check(pack["segment"] == "body-01", "segment 应回显")
    check(pack["previousReview"] is None, "还没评过时 previousReview 应为 null")
    check(isinstance(pack["reflections"], list) and pack["reflections"] == [], "还没写反思时应是空数组")
    check(set(pack["background"]) == {"genre", "level", "setting", "targetWords", "text"},
          "background 应带上文体、级别、场景、目标字数与背景说明：%r" % pack["background"])
    check(len(pack["contextHash"]) == 64, "contextHash 应是 sha256 十六进制")
    return "context 八个顶层键齐全，还没评过时 previousReview 为 null"


def t_stale_hash(root):
    """上下文新鲜度闸：改一字、改背景、改目标字数、缺 hash 四种都拒收。"""
    ws = built(root)
    path = os.path.join(ws, "inbox", "review.json")

    body = review_payload(root, "body-01")
    seg = os.path.join(ws, "sections", "body-01.md")
    write(seg, read(seg).replace("先看真的搬走", "先看确实搬走"))
    write_json(path, body)
    rc, out, err = run(root, "review", "add", SLUG, "body-01", "--from", path)
    check(rc == 1, "改过一个字之后旧 contextHash 必须被拒，rc=%d\n%s%s" % (rc, out, err))

    body = review_payload(root, "body-02")
    ok(root, "meta", SLUG, "--setting", "timed")
    write_json(path, body)
    rc, out, err = run(root, "review", "add", SLUG, "body-02", "--from", path)
    check(rc == 1, "把 untimed 改成 timed 之后旧 contextHash 必须被拒，rc=%d" % rc)

    body = review_payload(root, "body-03")
    ok(root, "meta", SLUG, "--target-words", "1200")
    write_json(path, body)
    rc, out, err = run(root, "review", "add", SLUG, "body-03", "--from", path)
    check(rc == 1, "改了目标字数之后旧 contextHash 必须被拒，rc=%d" % rc)

    body = review_payload(root, "body-04")
    del body["contextHash"]
    write_json(path, body)
    rc, out, err = run(root, "review", "add", SLUG, "body-04", "--from", path)
    check(rc == 1, "没跑 context（缺 contextHash）必须被拒，rc=%d" % rc)
    check(not os.path.isfile(os.path.join(ws, "ledger", "body-04.jsonl")), "被拒的评审不许落盘")
    return "改一字 / 改场景 / 改目标字数 / 缺 hash 四种都退出 1"


def t_scores_gate(root):
    """分值闸：布尔、浮点、字符串、负号、越界全无效；手填综合分与未知键拒收。"""
    ws = built(root)
    bad = [
        {"language": True, "answersSubquestion": 3, "advancesThesis": 3},
        {"language": 3.5, "answersSubquestion": 3, "advancesThesis": 3},
        {"language": "4", "answersSubquestion": 3, "advancesThesis": 3},
        {"language": -1, "answersSubquestion": 3, "advancesThesis": 3},
        {"language": 0, "answersSubquestion": 3, "advancesThesis": 3},
        {"language": 6, "answersSubquestion": 3, "advancesThesis": 3},
        {"language": 3, "answersSubquestion": 3},
        {"language": 3, "answersSubquestion": 3, "advancesThesis": 3, "extraDim": 3},
    ]
    for scores in bad:
        rc, out, err = add_review(root, ws, "body-01", scores=scores)
        check(rc == 1, "分值 %r 应被拒，rc=%d\n%s%s" % (scores, rc, out, err))

    rc, out, err = add_review(root, ws, "body-01", extra={"composite": 5})
    check(rc == 1, "手填综合分必须被拒，rc=%d\n%s%s" % (rc, out, err))
    rc, out, err = add_review(root, ws, "body-01", extra={"atScore": 2})
    check(rc == 1, "载荷里塞 atScore 必须被拒，rc=%d" % rc)
    rc, out, err = add_review(root, ws, "body-01", extra={"whateverElse": 1})
    check(rc == 1, "载荷出现不认识的键必须被拒，rc=%d" % rc)

    add_review_ok(root, ws, "body-01", scores={"language": 4, "answersSubquestion": 3,
                                               "advancesThesis": 4})
    row = ledger_rows(ws, "body-01")[-1]
    check(row["composite"] == 4, "综合分应由脚本取均值四舍五入（4+3+4)/3≈3.67→4，实际 %r" % row["composite"])
    return "八种非法分值 + 手填综合分 / atScore / 未知键全拒；综合分由脚本算"


def t_quotes_gate(root):
    """证据引用闸：0 条、非原文、重复、单条超 40%、合计超 40% 全拒。"""
    ws = built(root)
    text = ctx(root, "body-01")["text"]
    rc, out, err = add_review(root, ws, "body-01", quotes=[])
    check(rc == 1, "一条引用都没有应被拒，rc=%d\n%s%s" % (rc, out, err))
    rc, out, err = add_review(root, ws, "body-01", quotes=["这句话原文里压根没有出现过"])
    check(rc == 1, "非原文引用应被拒，rc=%d" % rc)
    check("原文" in (out + err), "拒收时要把违规原文说清楚：\n%s%s" % (out, err))
    rc, out, err = add_review(root, ws, "body-01", quotes=[text[5:35], text[5:35]])
    check(rc == 1, "两条一模一样的引用应被拒，rc=%d" % rc)
    big = text[:int(len(text) * 0.5)]
    rc, out, err = add_review(root, ws, "body-01", quotes=[big])
    check(rc == 1, "单条超过该段 40%% 应被拒，rc=%d" % rc)
    third = int(len(text) * 0.22)
    rc, out, err = add_review(root, ws, "body-01",
                              quotes=[text[:third], text[third:third * 2], text[third * 2:third * 3]])
    check(rc == 1, "合计超过该段 40%% 应被拒，rc=%d" % rc)

    # 空白归一之后仍是逐字子串就该收下
    quote = re.sub(r"(.{8})", r"\1 ", text[10:40], count=1)
    add_review_ok(root, ws, "body-01", quotes=[quote])
    return "0 条 / 非原文 / 重复 / 单条超 40%% / 合计超 40%% 全拒；空白归一后的逐字引用收下".replace("%%", "%")


def t_handoff_gate(root):
    """improved / rewrite 出现即拒收，并提示交给 red-pen。"""
    ws = built(root)
    for key in ("improved", "rewrite"):
        rc, out, err = add_review(root, ws, "body-01", extra={key: "帮你把这句改写成……"})
        check(rc == 1, "%s 字段出现即应拒收，rc=%d\n%s%s" % (key, rc, out, err))
        check("red-pen" in (out + err), "拒收时应提示把这段丢给 red-pen：\n%s%s" % (out, err))
    return "improved / rewrite 出现即拒收并指向 red-pen"


def t_hollow_gate(root):
    """空心评审闸：两段贴同一份评语 ERROR；零引用套话与雷同评审 WARN。"""
    ws = built(root)
    same = ("这段整体不错，条理清楚，建议继续保持，下一步可以再打磨一下措辞，"
            "让整体读起来更顺一些，也更容易让人记住。")
    add_review_ok(root, ws, "intro", note=same)
    # 8 段贴同一份评审的攻击：第 2 段就必须被挡住，后面 6 段根本轮不到
    for seg in SEGMENTS[1:]:
        rc, out, err = add_review(root, ws, seg, note=same)
        check(rc == 1, "第 2 段贴同一份评语必须 ERROR 退出 1（%s），rc=%d\n%s%s" % (seg, rc, out, err))
        check("ERROR" in (out + err), "同评语拒收应打 ERROR：\n%s%s" % (out, err))
        break

    text = ctx(root, "body-02")["text"]
    rc, out, err = add_review(root, ws, "body-02", note="写得挺好，加油。", quotes=[text[3:9]])
    check(rc == 0, "零引用套话只该 WARN 不该拒收，rc=%d\n%s%s" % (rc, out, err))
    check("WARN" in out, "零引用套话应打 WARN：\n%s" % out)
    row = ledger_rows(ws, "body-02")[-1]
    check(row.get("flags"), "WARN 应记进账本行的 flags：%r" % row)

    near = "这一段把论点摆出来了，证据也贴着论点走，但收尾那句还停在复述上，没有推到下一段。"
    four = {"language": 4, "answersSubquestion": 4, "advancesThesis": 4}
    add_review_ok(root, ws, "body-03", note=near, scores=four)
    out = add_review_ok(root, ws, "body-04", note=near + "整体如此。", scores=four)
    check("WARN" in out and "雷同" in out, "三维分相同且评语高度重合应 WARN 雷同：\n%s" % out)
    return "同评语 ERROR；零引用套话与雷同评审各 WARN 并记进 flags"


def t_same_draft_trend(root):
    """同稿重评闸：零修改连评 3 次，sameDraft=true，走势长度为 1。"""
    ws = built(root)
    notes = ["第 %d 次看这一段，仍然觉得论据摆得清楚，但收束那句还差一口气，没有推到下一段。" % i
             for i in (1, 2, 3)]
    for note in notes:
        add_review_ok(root, ws, "body-05", note=note)
    rows = ledger_rows(ws, "body-05")
    check(len(rows) == 3, "应有 3 行评审")
    check(rows[0]["sameDraft"] is False, "第一次不算同稿重评")
    check(rows[1]["sameDraft"] is True and rows[2]["sameDraft"] is True, "后两次应标 sameDraft")
    out = ok(root, "status", SLUG)
    check("走势 1 点" in out, "零修改连评 3 次，走势长度必须是 1：\n%s" % out)

    seg = os.path.join(ws, "sections", "body-05.md")
    write(seg, read(seg) + "\n\n这是改稿之后新加的一整句话，用来把上一段的结论推到下一段去。\n")
    add_review_ok(root, ws, "body-05")
    out = ok(root, "status", SLUG)
    check("走势 2 点" in out, "改过稿再评，走势才加一点：\n%s" % out)
    ok(root, "report", SLUG)
    page = read(os.path.join(ws, "report.html"))
    check("同稿重评" in page, "report 应标出同稿重评：\n%s" % page[:2000])
    return "同稿重评标 sameDraft、走势不加点；改稿后才加点"


def t_chain_tamper(root):
    """账本链闸：改中间行一个字节、删末行、手动追加一行，check 都必须 ERROR。"""
    ws = built(root)
    for i in (1, 2, 3):
        seg = os.path.join(ws, "sections", "body-06.md")
        if i > 1:
            write(seg, read(seg) + "\n\n第 %d 次改稿补的一句话，让这一段跟下一段接得上。\n" % i)
        add_review_ok(root, ws, "body-06", note="第 %d 次评审，论据与论点之间的那一步还要再说白一点。" % i)
    ok(root, "check", SLUG)
    path = os.path.join(ws, "ledger", "body-06.jsonl")
    good = read(path)

    rows = good.split("\n")
    hacked = list(rows)
    hacked[1] = hacked[1].replace('"language":4', '"language":5', 1)
    if hacked[1] == rows[1]:
        hacked[1] = hacked[1].replace("论据", "论点", 1)
    write(path, "\n".join(hacked))
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "ERROR" in out, "改中间一行必须 ERROR，rc=%d\n%s%s" % (rc, out, err))

    write(path, "\n".join([ln for ln in good.split("\n") if ln.strip()][:-1]) + "\n")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "ERROR" in out, "删掉末行必须 ERROR，rc=%d\n%s%s" % (rc, out, err))

    # 追加的这一行不是稻草人：seq 接得上、prevHash 是上一行真实的 sha256、
    # 字节也按脚本的规范 JSON 排好——只剩 chains.json 的链尾能识破它。
    kept = [ln for ln in good.split("\n") if ln.strip()]
    forged = canon({"seq": len(kept) + 1, "when": "2026-09-01T00:00:00Z", "stage": "review",
                    "segment": "body-06", "versionNumber": 0, "segmentText": "伪造",
                    "segmentHash": sha256_hex("伪造"), "subquestion": "", "thesis": "",
                    "background": {}, "reflectionPack": [], "contextHash": "0" * 64,
                    "scores": {"language": 5, "answersSubquestion": 5, "advancesThesis": 5},
                    "composite": 5, "note": "伪造的一行", "quotes": ["伪造"],
                    "sameDraft": False, "flags": [], "prevHash": sha256_hex(kept[-1])})
    write(path, "\n".join(kept + [forged]) + "\n")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "ERROR" in out,
          "手动追加一行（seq 与 prevHash 都算对）必须 ERROR，rc=%d\n%s%s" % (rc, out, err))

    write(path, good)
    ok(root, "check", SLUG)
    return "改中间行 / 删末行 / 手动追加（含算对 prevHash 的）三种篡改都 ERROR，还原后复绿"


def t_chain_index_known_limit(root):
    """已知限界（不是 bug，是 spec §风险 8 认过的账）：链尾索引 chains.json 跟账本一起改就过。

    prevHash 链只能发现「有人动过行」，末行没有下一行给它作证，所以得靠 chains.json
    记链尾。谁知道这个文件存在，两处一起改就能把删末行 / 追加行做成 0 ERROR
    （seq 跳号仍然抓得住）。这条用例把这个边界钉死：将来有人以为它被挡住了，
    这里会告诉他没有。README 安全段与 workspace-format.md 必须按同一口径写。
    """
    ws = built(root)
    for i in (1, 2, 3):
        seg = os.path.join(ws, "sections", "body-06.md")
        if i > 1:
            write(seg, read(seg) + "\n\n第 %d 次改稿补的一句话。\n" % i)
        add_review_ok(root, ws, "body-06", note="第 %d 次评审，这一步还要再说白一点。" % i)
    path = os.path.join(ws, "ledger", "body-06.jsonl")
    chains_path = os.path.join(ws, "chains.json")
    rel = "ledger/body-06.jsonl"
    good = read(path)
    kept = [ln for ln in good.split("\n") if ln.strip()]

    def sync(lines):
        write(path, "\n".join(lines) + "\n")
        tips = load(chains_path)
        tips[rel] = {"seq": len(lines), "hash": sha256_hex(lines[-1])}
        write_json(chains_path, tips)

    # 1) 删末行 + 同步改索引 → 0 ERROR（已知限界）
    sync(kept[:-1])
    rc, out, err = run(root, "check", SLUG)
    check(rc == 0, "已知限界：删末行并同步改 chains.json 目前是 0 ERROR，"
                   "如果这里开始报错说明护栏变强了，请连报告一起更新。rc=%d\n%s%s" % (rc, out, err))

    # 2) 改中间行 + 重算后续 prevHash + 同步改索引 → 0 ERROR（已知限界）
    rows = [json.loads(ln) for ln in kept]
    rows[1]["note"] = "重造过的一行评语，链上下都算对了。"
    rebuilt = []
    prev = json.loads(kept[0])["prevHash"]
    for i, row in enumerate(rows):
        row["prevHash"] = prev if i == 0 else sha256_hex(rebuilt[-1])
        rebuilt.append(canon(row))
        prev = row["prevHash"]
    sync(rebuilt)
    rc, out, err = run(root, "check", SLUG)
    check(rc == 0, "已知限界：整链重造并同步改 chains.json 目前是 0 ERROR，rc=%d\n%s%s"
          % (rc, out, err))

    # 3) 但 seq 跳号仍然抓得住——重造得连 seq 一起编才行
    broken = list(rebuilt)
    row = json.loads(broken[-1])
    row["seq"] = 99
    broken[-1] = canon(row)
    sync(broken)
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "seq" in out, "seq 跳号即使同步改了索引也必须 ERROR，rc=%d\n%s%s"
          % (rc, out, err))
    return "已知限界：同步改 chains.json 能把删末行与整链重造做成 0 ERROR；seq 跳号仍抓得住"


def t_chain_rebuild_index(root):
    """写盘被打断（追加了行、索引没跟上）不该把用户当篡改者：check --rebuild-index 能修。"""
    ws = built(root)
    add_review_ok(root, ws, "body-01")
    add_review_ok(root, ws, "body-02")
    ok(root, "check", SLUG)
    chains_path = os.path.join(ws, "chains.json")
    good_chains = read(chains_path)

    # A. chains.json 整个丢了 → 报错并指路 --rebuild-index → 重建后 0 ERROR
    os.remove(chains_path)
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1, "chains.json 丢了应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("--rebuild-index" in out, "应告诉用户可以用 --rebuild-index 修：\n%s" % out)
    out = ok(root, "check", SLUG, "--rebuild-index")
    check("重建" in out and "0 个 ERROR" in out, "重建之后应 0 ERROR：\n%s" % out)
    ok(root, "check", SLUG)
    check(os.path.isfile(chains_path), "重建应写回 chains.json")

    # B. 追加了合法一行、索引停在上一条（模拟 append_row 两步之间被打断）
    write(chains_path, good_chains)
    path = os.path.join(ws, "ledger", "body-01.jsonl")
    kept = [ln for ln in read(path).split("\n") if ln.strip()]
    row = json.loads(kept[-1])
    row["seq"] = len(kept) + 1
    row["prevHash"] = sha256_hex(kept[-1])
    row["note"] = "写盘被打断之前落下来的那一条评语，内容是真的。"
    write(path, "\n".join(kept + [canon(row)]) + "\n")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "--rebuild-index" in out,
          "索引落后一条应退出 1 并指路重建，rc=%d\n%s%s" % (rc, out, err))
    out = ok(root, "check", SLUG, "--rebuild-index")
    check("0 个 ERROR" in out, "重建之后应 0 ERROR：\n%s" % out)

    # C. 链自身断了的时候，--rebuild-index 必须拒绝重建，不许把篡改盖过去。
    #    索引这一侧摆成「落后但锚得住」，好让走到的确实是「链断」这条拒绝分支。
    kept = [ln for ln in read(path).split("\n") if ln.strip()]
    hacked = kept[0].replace('"language":4', '"language":5', 1)
    check(hacked != kept[0], "用例本身要能改到第一行的分值：%s" % kept[0][:120])
    kept[0] = hacked
    write(path, "\n".join(kept) + "\n")
    tips = load(chains_path)
    tips["ledger/body-01.jsonl"] = {"seq": 1, "hash": sha256_hex(kept[0])}
    write_json(chains_path, tips)
    frozen = read(chains_path)
    rc, out, err = run(root, "check", SLUG, "--rebuild-index")
    check(rc == 1 and "拒绝" in out,
          "链自身断了时 --rebuild-index 必须拒绝重建，rc=%d\n%s%s" % (rc, out, err))
    check(read(chains_path) == frozen, "被拒绝的重建不许改动 chains.json 字节")
    return "索引丢失 / 落后一条都能 --rebuild-index 修好；链自身断了时拒绝重建且不动索引"


def t_rebuild_never_launders_deletion(root):
    """删行不许被 --rebuild-index 洗白，check 也不许主动指路。

    脚本是先追加行、再写索引，所以打断只做得出「索引落后」。索引比账本长、或者账本
    空了索引还记着行，这两种打断做不出来 —— 只可能是行没了。这种时候重建就是替人
    把一条评审抹掉，所以必须拒绝，而且提示里一个字都不许提 --rebuild-index。
    """
    ws = built(root)
    for i in (1, 2, 3):
        seg = os.path.join(ws, "sections", "body-06.md")
        if i > 1:
            write(seg, read(seg) + "\n\n第 %d 次改稿补的一句话。\n" % i)
        add_review_ok(root, ws, "body-06", note="第 %d 次评审，这一步还要再说白一点。" % i)
    ok(root, "check", SLUG)
    path = os.path.join(ws, "ledger", "body-06.jsonl")
    chains_path = os.path.join(ws, "chains.json")
    good = read(path)
    kept = [ln for ln in good.split("\n") if ln.strip()]
    check(len(kept) == 3, "先攒够 3 行账本，实际 %d 行" % len(kept))

    def refuses(label, content):
        write(path, content)
        frozen = read(chains_path)
        rc, out, err = run(root, "check", SLUG)
        check(rc == 1, "%s 必须 ERROR，rc=%d\n%s%s" % (label, rc, out, err))
        check("--rebuild-index" not in out,
              "%s 时 check 不许主动指路 --rebuild-index：\n%s" % (label, out))
        rc, out, err = run(root, "check", SLUG, "--rebuild-index")
        check(rc == 1, "%s 时 --rebuild-index 必须照样 ERROR，rc=%d\n%s%s"
              % (label, rc, out, err))
        check("已按各条链的实际内容重建" not in out,
              "%s 时不许真的重建索引：\n%s" % (label, out))
        check(read(chains_path) == frozen, "%s 时 chains.json 一个字节都不许动" % label)
        # 再跑一次，确认没有被「洗成永久 0 ERROR」
        rc, out, err = run(root, "check", SLUG)
        check(rc == 1, "%s 之后 check 必须一直红，rc=%d\n%s" % (label, rc, out))

    refuses("删掉末行", "\n".join(kept[:-1]) + "\n")
    refuses("删掉最后两行", kept[0] + "\n")
    refuses("整条账本清空", "")
    refuses("整条账本只剩空白", "\n\n")

    os.remove(path)
    frozen = read(chains_path)
    rc, out, err = run(root, "check", SLUG, "--rebuild-index")
    check(rc == 1, "账本文件被删掉时 --rebuild-index 必须照样 ERROR，rc=%d\n%s%s" % (rc, out, err))
    check(read(chains_path) == frozen, "账本文件被删掉时 chains.json 也不许动")

    write(path, good)
    ok(root, "check", SLUG)
    return "删末行 / 删两行 / 清空 / 删文件：--rebuild-index 一律拒绝、不动索引、不指路，还原后复绿"


def t_reflect_trigger(root):
    """反思触发闸：综合 3 拒收，≤2 与 =5 接受；atScore 手填拒；超 4000 字拒。"""
    ws = built(root)
    path = os.path.join(ws, "inbox", "reflect.json")

    add_review_ok(root, ws, "body-01", scores={"language": 3, "answersSubquestion": 3,
                                               "advancesThesis": 3})
    write_json(path, {"text": "这一段当时评了 3 分，我想写点什么。"})
    rc, out, err = run(root, "reflect", "add", SLUG, "--segment", "body-01", "--from", path)
    check(rc == 1, "综合 3 分不触发反思，应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("总反思" in (out + err), "拒收时应提示可以写总反思：\n%s%s" % (out, err))

    add_review_ok(root, ws, "body-02", scores={"language": 2, "answersSubquestion": 1,
                                               "advancesThesis": 2})
    write_json(path, {"text": "我把两个论点塞进了一段，读的人分不清我到底要证哪一个。"})
    ok(root, "reflect", "add", SLUG, "--segment", "body-02", "--from", path)
    rows = [json.loads(ln) for ln in lines_of(os.path.join(ws, "reflections.jsonl"))]
    check(rows[-1]["atScore"] == 2, "atScore 应由脚本从账本取，实际 %r" % rows[-1])
    check(rows[-1]["scope"] == "segment" and rows[-1]["segment"] == "body-02", "反思应钉在这一段上")

    add_review_ok(root, ws, "body-03", scores={"language": 5, "answersSubquestion": 5,
                                               "advancesThesis": 5})
    write_json(path, {"text": "这一段写顺了，原因是我先把子问题抄在纸上再动笔。"})
    ok(root, "reflect", "add", SLUG, "--segment", "body-03", "--from", path)

    write_json(path, {"text": "手填触发分试试看。", "atScore": 1})
    rc, out, err = run(root, "reflect", "add", SLUG, "--segment", "body-02", "--from", path)
    check(rc == 1, "载荷里手填 atScore 必须被拒，rc=%d" % rc)

    write_json(path, {"text": "总反思随时可以写，不看分数。"})
    ok(root, "reflect", "add", SLUG, "--from", path)
    rows = [json.loads(ln) for ln in lines_of(os.path.join(ws, "reflections.jsonl"))]
    check(rows[-1]["scope"] == "essay" and rows[-1].get("atScore") is None, "总反思不带触发分")

    write_json(path, {"text": "长" * 4001})
    rc, out, err = run(root, "reflect", "add", SLUG, "--from", path)
    check(rc == 1, "超过 4000 字的反思应被拒，rc=%d" % rc)

    write_json(path, {"text": "<p>剥标签之后仍要留住 x&lt;0 这种符号</p>"})
    ok(root, "reflect", "add", SLUG, "--from", path)
    rows = [json.loads(ln) for ln in lines_of(os.path.join(ws, "reflections.jsonl"))]
    check("x<0" in rows[-1]["text"], "剥 HTML 标签不许把 x<0 一起吞掉：%r" % rows[-1]["text"])
    return "综合 3 拒、≤2 与 =5 收、atScore 手填拒、超 4000 拒、剥标签不吞 x<0"


def t_reflect_pack(root):
    """反思装配闸：≤3 条，同段 > 总反思 > 其他段，组内新→旧。"""
    ws = built(root)
    path = os.path.join(ws, "inbox", "reflect.json")
    low = {"language": 2, "answersSubquestion": 1, "advancesThesis": 2}
    add_review_ok(root, ws, "body-01", scores=low,
                  note="这一段的问题在于论据没有回到子问题上，读者要自己补那一步。")
    add_review_ok(root, ws, "body-02", scores=low,
                  note="留下来的理由列了三条，可是没有一条说清它为什么比搬走更划算。")

    order = []
    for tag in ("其他段甲", "其他段乙"):
        write_json(path, {"text": "%s：当时的问题是论据摆得多但没有回到子问题。" % tag})
        ok(root, "reflect", "add", SLUG, "--segment", "body-02", "--from", path)
        order.append(tag)
    for tag in ("总反思甲", "总反思乙"):
        write_json(path, {"text": "%s：整篇的毛病是每段都想多说一句。" % tag})
        ok(root, "reflect", "add", SLUG, "--from", path)
        order.append(tag)
    for tag in ("同段甲", "同段乙"):
        write_json(path, {"text": "%s：这一段我把两个论点塞在了一起。" % tag})
        ok(root, "reflect", "add", SLUG, "--segment", "body-01", "--from", path)
        order.append(tag)

    pack = ctx(root, "body-01")["reflections"]
    check(len(pack) == 3, "反思包最多 3 条，实际 %d 条：%r" % (len(pack), pack))
    tags = [p["text"][:3] for p in pack]
    check(tags == ["同段乙", "同段甲", "总反思"],
          "顺序应是同段新→旧、再总反思，实际 %r" % tags)
    check(set(pack[0]) == {"scope", "when", "atScore", "text"}, "反思条目四个字段：%r" % sorted(pack[0]))
    return "6 条混合反思里取 3 条：同段新→旧、然后总反思"


def t_segment_changed(root):
    """原文已修改闸：改稿后 status / context / report 都要显眼地标出来。"""
    ws = built(root)
    add_review_ok(root, ws, "body-01")
    pack = ctx(root, "body-01")
    check(pack["previousReview"] is not None, "评过之后 previousReview 不该是 null")
    check(pack["previousReview"]["segmentChanged"] is False, "没改稿时 segmentChanged 应为 false")
    check(set(pack["previousReview"]) == {"scores", "segmentChanged"},
          "previousReview 只带这两个键：%r" % sorted(pack["previousReview"]))

    seg = os.path.join(ws, "sections", "body-01.md")
    write(seg, read(seg) + "\n\n改稿补的一整句：这一步要把租房登记的口径先交代清楚。\n")
    pack = ctx(root, "body-01")
    check(pack["previousReview"]["segmentChanged"] is True, "改稿之后 segmentChanged 必须是 true")
    out = ok(root, "status", SLUG)
    check("原文已修改" in out, "status 必须显眼地标「原文已修改」：\n%s" % out)
    ok(root, "report", SLUG)
    page = read(os.path.join(ws, "report.html"))
    check("原文已修改" in page, "report 也要标「原文已修改」")
    check("prefers-color-scheme" in page, "report 应带深色模式配色")
    check("http" not in page.lower().replace("http-equiv", ""), "report 不许外链")
    return "改稿后 status / context / report 三处都标「原文已修改」"


def t_status_mtime(root):
    """Agent 不代写闸里可机检的那半条：status 打印每段 mtime 与哈希供核对。"""
    ws = built(root)
    out = ok(root, "status", SLUG)
    for seg in SEGMENTS:
        check(seg in out, "status 应逐段列出：缺 %s\n%s" % (seg, out))
    check(re.search(r"\d{4}-\d{2}-\d{2}", out), "status 应打印每段的 mtime：\n%s" % out)
    check(re.search(r"[0-9a-f]{8}", out), "status 应打印每段的哈希前缀：\n%s" % out)
    return "status 逐段打印 mtime 与哈希，便于核对有没有人替你写"


def t_reading_gate(root):
    """荐读结构闸：缺字段拒、verified 缺省 false 并标未核实、同段同名拒。"""
    ws = built(root)
    path = os.path.join(ws, "inbox", "reading.json")
    for bad in ({"authors": "某某", "year": 2024},
                {"title": "远程办公与城市空间", "year": 2024},
                {"title": "远程办公与城市空间", "authors": "某某", "year": ""},
                {"title": "  ", "authors": "某某", "year": 2024}):
        write_json(path, bad)
        rc, out, err = run(root, "reading", "add", SLUG, "body-01", "--from", path)
        check(rc == 1, "缺字段的荐读 %r 应被拒，rc=%d" % (bad, rc))

    write_json(path, {"title": "远程办公与城市空间", "authors": "某某、某某某", "year": 2024,
                      "summary": "讨论通勤成本下降之后住处选择的变化。"})
    ok(root, "reading", "add", SLUG, "body-01", "--from", path)
    files = sorted(os.listdir(os.path.join(ws, "readings")))
    check(len(files) == 1, "应写出一份荐读：%r" % files)
    card = load(os.path.join(ws, "readings", files[0]))
    check(card["verified"] is False, "verified 缺省必须是 false：%r" % card)
    out = ok(root, "status", SLUG)
    check("引用未核实" in out, "status 应标「引用未核实」：\n%s" % out)
    ok(root, "report", SLUG)
    check("引用未核实" in read(os.path.join(ws, "report.html")), "report 也要标「引用未核实」")

    write_json(path, {"title": "远程办公与城市空间  ", "authors": "另一位", "year": 2020})
    rc, out, err = run(root, "reading", "add", SLUG, "body-01", "--from", path)
    check(rc == 1, "同段同名（小写归一）的荐读应被拒，rc=%d\n%s%s" % (rc, out, err))
    write_json(path, {"title": "远程办公与城市空间", "authors": "另一位", "year": 2020})
    ok(root, "reading", "add", SLUG, "body-02", "--from", path)
    return "缺字段拒、verified 缺省 false 并标未核实、同段同名拒"


def t_version_gate(root):
    """版本闸：编号递增、manifest 记哈希、check 复核、篡改必 ERROR。"""
    ws = built(root)
    out = ok(root, "version", SLUG)
    check("v1" in out, "第一次版本应是 v1：\n%s" % out)
    add_review_ok(root, ws, "body-01")
    row = ledger_rows(ws, "body-01")[-1]
    check(row["versionNumber"] == 1, "账本行应自带版本号：%r" % row)

    seg = os.path.join(ws, "sections", "body-01.md")
    write(seg, read(seg) + "\n\n第二版补的一句：把租房登记的口径先交代清楚。\n")
    ok(root, "version", SLUG)
    check(os.path.isdir(os.path.join(ws, "versions", "v2")), "版本编号应递增到 v2")
    manifest = load(os.path.join(ws, "versions", "v2", "manifest.json"))
    check(manifest["version"] == 2 and len(manifest["files"]) == len(SEGMENTS),
          "manifest 应逐文件记哈希：%r" % manifest)
    ok(root, "check", SLUG)

    write(os.path.join(ws, "versions", "v1", "body-01.md"), "有人回头改了旧版本快照。\n")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "ERROR" in out, "改动版本快照必须 ERROR，rc=%d\n%s%s" % (rc, out, err))
    return "版本递增、manifest 哈希、篡改旧快照必 ERROR"


def t_version_numbering(root):
    """编号按最大号 +1，不按目录个数：中间那一版被删掉也不许撞号、不许覆盖。"""
    ws = built(root)
    for want in ("v1", "v2", "v3"):
        out = ok(root, "version", SLUG)
        check(want in out, "应拍出 %s：\n%s" % (want, out))
    keep = load(os.path.join(ws, "versions", "v3", "manifest.json"))
    shutil.rmtree(os.path.join(ws, "versions", "v2"))

    out = ok(root, "version", SLUG)
    check("v4" in out, "删掉 v2 之后再拍应该是 v4（最大号 +1），不是 v3：\n%s" % out)
    check(sorted(os.listdir(os.path.join(ws, "versions"))) == ["v1", "v3", "v4"],
          "目录应是 v1 / v3 / v4：%r" % sorted(os.listdir(os.path.join(ws, "versions"))))
    check(load(os.path.join(ws, "versions", "v3", "manifest.json")) == keep,
          "v3 的 manifest 不许被后来那一版覆盖")
    add_review_ok(root, ws, "body-01")
    row = ledger_rows(ws, "body-01")[-1]
    check(row["versionNumber"] == 4, "账本行记的版本号应是最新版本 4，不是版本个数 3：%r" % row)
    out = ok(root, "check", SLUG)
    check("0 个 ERROR" in out, "缺了中间一版不算错：\n%s" % out)
    return "编号按最大号 +1：删掉 v2 后再拍是 v4，v3 不被覆盖，账本记的是最新版本号"


def t_check_workspace(root):
    """工作区一致性闸：干净的退出 0；inbox 有残留、账本对不上原文都 ERROR。"""
    ws = built(root)
    add_review_ok(root, ws, "intro")
    ok(root, "version", SLUG)
    out = ok(root, "check", SLUG)
    check("0 个 ERROR" in out, "干净工作区不该有 ERROR：\n%s" % out)

    write_json(os.path.join(ws, "inbox", "leftover.json"), {"x": 1})
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "inbox" in out, "inbox 有残留必须 ERROR，rc=%d\n%s%s" % (rc, out, err))
    os.remove(os.path.join(ws, "inbox", "leftover.json"))

    os.remove(os.path.join(ws, "sections", "body-03.md"))
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "ERROR" in out, "essay.json 与 sections/ 对不上必须 ERROR，rc=%d\n%s" % (rc, out))

    rc, out, err = run(root, "check", os.path.join(root, "essays", "no-such-essay"))
    check(rc == 2, "目录不存在应退出 2，rc=%d" % rc)
    return "干净 0、inbox 残留 / 分段缺失 ERROR、目录不存在退出 2"


def t_check_recompute(root):
    """check 只凭账本行自带的载荷离线复算；改稿之后旧行仍然复算通过。"""
    ws = built(root)
    add_review_ok(root, ws, "body-01")
    seg = os.path.join(ws, "sections", "body-01.md")
    write(seg, read(seg) + "\n\n改稿之后加的一句，旧账本行的复算不该受影响。\n")
    out = ok(root, "check", SLUG)
    check("0 个 ERROR" in out, "改稿后旧账本行仍应复算通过：\n%s" % out)

    path = os.path.join(ws, "ledger", "body-01.jsonl")
    row = json.loads(read(path).strip())
    row["contextHash"] = "f" * 64
    write(path, json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "ERROR" in out, "contextHash 对不上材料必须 ERROR，rc=%d\n%s" % (rc, out))
    return "账本行自带材料可离线复算；改稿不影响旧行，改哈希立刻 ERROR"


def t_export_evidence(root):
    """证据脱敏闸：export --evidence 只带哈希与分数，正文 0 命中。"""
    ws = built(root)
    add_review_ok(root, ws, "body-01")
    add_review_ok(root, ws, "body-02")
    ok(root, "version", SLUG)
    out = ok(root, "export", SLUG, "--evidence")
    data = json.loads(out)
    check(set(data) == {"slug", "rows", "versions"}, "证据包三个顶层键：%r" % sorted(data))
    check(len(data["rows"]) == 2, "应带出两行证据：%r" % data["rows"])
    for row in data["rows"]:
        check(set(row) == {"seq", "when", "stage", "segment", "segmentHash", "contextHash",
                           "scores", "sameDraft", "segmentChanged"},
              "证据行的键对不上：%r" % sorted(row))
    for text in (P_OPEN[:14], P_B1[:14], TITLE, "这一段把论点摆出来了"):
        check(text not in out, "证据包里不许出现正文或评语片段：%r" % text)

    plain = ok(root, "export", SLUG)
    check(P_B1[:14] in plain, "不带 --evidence 的导出应能拼回整篇")
    check("侧注" in plain or "评审" in plain, "导出应把各段最新评审拼在整篇后面：\n%s" % plain[-800:])
    return "证据包三个顶层键、九个行字段，正文 0 命中"


def t_report_cards(root):
    """report.html：分段卡带三个维度格子、逐字引用、走势点。"""
    ws = built(root)
    add_review_ok(root, ws, "intro")
    add_review_ok(root, ws, "body-01")
    ok(root, "report", SLUG)
    page = read(os.path.join(ws, "report.html"))
    for dim in ("language", "answersSubquestion", "advancesThesis"):
        check(dim in page, "report 应有维度 %s：\n%s" % (dim, page[:1500]))
    check(page.startswith("<!DOCTYPE html>"), "report 应是完整 HTML")
    check("<script" not in page.lower(), "report 不许带脚本")
    check(DEFAULT_NOTE[:12] in page, "report 应带上评语")
    check("走势" in page, "report 应画走势点")
    return "分段卡带三维格子、逐字引用与走势点，无脚本无外链"


def t_check_examples(root):
    """examples/ 下的示例工作区必须 check 0 ERROR（还没建就跳过）。"""
    base = os.path.join(SKILL_DIR, "examples", "essays")
    if not os.path.isdir(base):
        return "SKIP：examples/essays/ 还没建"
    names = sorted(n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n)))
    if not names:
        return "SKIP：examples/essays/ 是空的"
    for name in names:
        rc, out, err = run(SKILL_DIR, "check", os.path.join(base, name))
        check(rc == 0, "示例 %s 的 check 应 0 ERROR，rc=%d\n%s%s" % (name, rc, out, err))
    return "%d 个示例工作区 check 全绿" % len(names)


def t_banned_scan(root):
    """命名隔离闸：共享禁用词表 0 命中，本批次追加表 0 命中。"""
    scanner = os.path.join(HERE, "banned_words.py")
    proc = subprocess.run([PY, scanner, SKILL_DIR], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", "replace")
    check(proc.returncode == 0 and out.strip() == "", "禁用词扫描应无输出：\n%s" % out)

    hits = []
    for here, dirs, files in os.walk(SKILL_DIR):
        dirs[:] = sorted(d for d in dirs if d not in SCAN_SKIP_DIRS)
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() not in SCAN_EXT:
                continue
            if name == "banned_words.py":
                continue
            full = os.path.join(here, name)
            rel = os.path.relpath(full, SKILL_DIR)
            if rel == os.path.join("scripts", "selftest.py"):
                continue                      # 本文件自己写着这张表
            try:
                text = open(full, "r", encoding="utf-8-sig").read()
            except (OSError, UnicodeDecodeError):
                continue
            for word in BATCH_SUBSTRINGS:
                if word in text:
                    hits.append("%s：出现本批次禁用串「%s」" % (rel, word))
            for m in _QUOTED.finditer(text):
                literal = m.group(1) or m.group(2) or m.group(3) or ""
                if literal in BATCH_LITERALS:
                    hits.append("%s：生产枚举名「%s」不许当字面量" % (rel, literal))
    check(not hits, "本批次追加禁用表命中：\n%s" % "\n".join(hits))
    return "共享禁用词表与本批次追加表（%d 串 + %d 字面量）都 0 命中" % (
        len(BATCH_SUBSTRINGS), len(BATCH_LITERALS))


SELFTESTS = (
    t_doctor_init,
    t_import_md_offsets,
    t_assemble_identity,
    t_assemble_bad_ids,
    t_assemble_html_wrapper,
    t_assemble_fallback,
    t_import_docx,
    t_outline_rounds,
    t_outline_bind,
    t_thin_segment,
    t_context_shape,
    t_stale_hash,
    t_scores_gate,
    t_quotes_gate,
    t_handoff_gate,
    t_hollow_gate,
    t_same_draft_trend,
    t_chain_tamper,
    t_chain_index_known_limit,
    t_chain_rebuild_index,
    t_rebuild_never_launders_deletion,
    t_reflect_trigger,
    t_reflect_pack,
    t_segment_changed,
    t_status_mtime,
    t_reading_gate,
    t_version_gate,
    t_version_numbering,
    t_check_workspace,
    t_check_recompute,
    t_export_evidence,
    t_report_cards,
    t_check_examples,
    t_banned_scan,
)


def main():
    failed = []
    for fn in SELFTESTS:
        root = tempfile.mkdtemp(prefix="essay-sections-selftest-")
        try:
            note = fn(root)
        except Failed as e:
            failed.append(fn.__name__)
            print("FAIL %s：%s" % (fn.__name__, e))
        except Exception as e:
            failed.append(fn.__name__)
            print("FAIL %s：%s：%s" % (fn.__name__, type(e).__name__, e))
        else:
            print("pass %-24s %s" % (fn.__name__, note))
        finally:
            shutil.rmtree(root, ignore_errors=True)
    if failed:
        print("%d/%d 个用例未通过：%s" % (len(failed), len(SELFTESTS), "、".join(failed)))
        return 1
    print("OK（%d 个用例全部通过）" % len(SELFTESTS))
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
