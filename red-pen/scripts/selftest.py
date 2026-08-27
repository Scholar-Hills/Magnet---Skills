#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""redpen.py 自测：在临时目录里建工作区，逐条验证六道闸门与八个子命令，最后打印 OK。

用法：python3 scripts/selftest.py
不依赖 examples/ 目录（示例还没建时 t_check_examples 记为跳过）；所有工作区都建在
临时目录里，跑完删除。稿子、批语、docx 全部是现造的合成材料。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REDPEN = os.path.join(HERE, "redpen.py")
PY = sys.executable
SLUG = "weekly-note"


class Failed(Exception):
    """用例不通过。"""


class Skipped(Exception):
    """用例的前置条件还不具备，记为跳过。"""


def check(cond, msg):
    if not cond:
        raise Failed(msg)


# ---------------------------------------------------------------- 合成材料

DRAFT_V1 = """周更小记：把复盘写短一点

上周我们把周会的复盘模板改短了，从八栏减到三栏。改完第一周，写的人平均少花二十分钟，读的人反而记住了更多东西。

原来的模板要求每个人填满八栏，于是大家把力气花在填空上，真正值得说的那一两句反而被埋掉了。三栏之后只剩下三个问题：这周最意外的一件事、下周准备换的做法、需要别人帮忙的地方。写的人必须挑，读的人一眼看得完。

当然也有代价。有同事说三栏装不下跨部门的事，容易漏掉需要长期跟进的项目。我们的做法是把长期项目单独挂一张看板，复盘只写这周有变化的部分，其余的留在看板上。

再往后一步，我们想把复盘换成口头两分钟，文字只留一句结论。能不能成还不知道，下个月再来汇报。
"""

# 第二版：删掉了第四段，结尾也重写了 —— 上一版挂在这两处的批注会「消失」。
DRAFT_V2 = """周更小记：把复盘写短一点

上周我们把周会的复盘模板改短了，从八栏减到三栏。改完第一周，写的人平均少花二十分钟，读的人反而记住了更多东西。

原来的模板要求每个人填满八栏，于是大家把力气花在填空上，真正值得说的那一两句反而被埋掉了。三栏之后只剩下三个问题：这周最意外的一件事、下周准备换的做法、需要别人帮忙的地方。写的人必须挑，读的人一眼看得完。

下个月我们打算再试一版口头复盘，两分钟说完，文字只留一句结论，到时候把数据一起贴出来。
"""

# 引子极短、后文很长：所有引文都落在开头，用来验证覆盖闸。
DRAFT_FRONT = """开头这一段是引子，先把结论摆出来。

正文第一段开始展开。我们把三个月里所有的周会记录翻了一遍，按主题归了六类，再把每一类里重复出现的说法挑出来单独列了一张表，这张表后来成了改模板的主要依据，也是这篇稿子里最花时间的部分。

正文第二段继续。归类的过程中发现，重复最多的并不是项目进展，而是「这件事到底谁来拍板」，同一个问题在不同的周会上被换着说法提了很多次，却始终没有人写下一个结论，于是它每周都会再出现一次。

正文第三段收尾。我们把拍板这一类单独拎出来放进了模板的第三栏，要求提问的人自己写清楚需要谁点头，这一栏上线之后，同类问题的重复出现次数明显下降，虽然还没有降到零。
"""

BRIEF_V1 = {
    "audience": "关注团队协作的同行读者",
    "purpose": "把一次模板精简的经过讲清楚，让别人能照着试",
    "worries": ["结论下得太满", "缺少可核对的依据"],
    "lang": "zh",
}

LONG_QUOTE_A = "原来的模板要求每个人填满八栏，于是大家把力气花在填空上，真正值得说的那一两句反而被埋掉了。"
LONG_QUOTE_B = "我们的做法是把长期项目单独挂一张看板，复盘只写这周有变化的部分，其余的留在看板上。"


def marks_ok():
    """五条散落在全文各处的批注，全部能锚定。"""
    return [
        {"quote": "从八栏减到三栏", "level": "minor", "note": "可以补一句为什么正好是三栏。"},
        {"quote": "读的人反而记住了更多东西", "level": "major", "note": "结论下得很满，缺一个可核对的依据。"},
        {"quote": "真正值得说的那一两句反而被埋掉了", "level": "remark", "note": "这是全文最好的一句，值得提前。"},
        {"quote": "容易漏掉需要长期跟进的项目", "level": "minor", "note": "同事的原话引一句会更有分量。"},
        {"quote": "能不能成还不知道", "level": "remark", "note": "结尾略平，给个具体时间点更好。"},
    ]


DOCX_MAIN_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX_PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCX_DOC_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
DOCX_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
DOCX_MAIN_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def make_docx(path, text):
    """现造一个最小 docx：只有 word/document.xml 里的若干 w:p 是真材料。"""
    body = "".join(
        "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % block
        for block in [b.strip() for b in text.split("\n\n")] if block)
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="%s"><w:body>%s</w:body></w:document>' % (DOCX_MAIN_NS, body))
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Type="%s" Target="word/document.xml"/>'
            '</Relationships>' % (DOCX_PKG_NS, DOCX_DOC_TYPE))
    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="%s">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="%s"/>'
             '</Types>' % (DOCX_CT_NS, DOCX_MAIN_CT))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return path


# ---------------------------------------------------------------- 跑脚本

_TEMPS = []


def sweep():
    while _TEMPS:
        shutil.rmtree(_TEMPS.pop(), ignore_errors=True)


def run(root, *args):
    proc = subprocess.run([PY, REDPEN, "--root", root] + [str(a) for a in args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def ws_dir(root, slug=SLUG):
    return os.path.join(root, "drafts", slug)


def workspace(text=DRAFT_V1, name="draft.md", brief=BRIEF_V1, slug=SLUG):
    """建一个临时根目录，init 一份稿子并写好 brief，返回根目录。"""
    root = tempfile.mkdtemp(prefix="red-pen-selftest-")
    _TEMPS.append(root)
    src = os.path.join(root, "source", name)
    if name.endswith(".docx"):
        os.makedirs(os.path.dirname(src), exist_ok=True)
        make_docx(src, text)
    else:
        write(src, text)
    rc, out, err = run(root, "init", slug, "--from", src)
    check(rc == 0, "init 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    if brief is not None:
        set_brief(root, brief, slug)
    return root


def set_brief(root, brief, slug=SLUG):
    path = os.path.join(root, "source", "brief-%s.json" % slug)
    write(path, json.dumps(brief, ensure_ascii=False, indent=2))
    rc, out, err = run(root, "brief", "set", slug, "--from", path)
    check(rc == 0, "brief set 应退出 0，rc=%d\n%s%s" % (rc, out, err))


def context(root, slug=SLUG):
    rc, out, err = run(root, "context", slug)
    check(rc == 0, "context 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    try:
        return json.loads(out)
    except ValueError as e:
        raise Failed("context 的输出应当是 JSON：%s\n%s" % (e, out))


def submit(root, marks, digest=None, slug=SLUG):
    """把一份 marks 写进 inbox 再跑 review，返回 (rc, out, err)。"""
    pack = context(root, slug)
    payload = {"context_hash": digest or pack["context_hash"], "marks": marks}
    write(os.path.join(ws_dir(root, slug), "inbox", "marks.json"),
          json.dumps(payload, ensure_ascii=False, indent=2))
    return run(root, "review", slug)


# ---------------------------------------------------------------- 用例

def t_init_from_txt_md_html_docx():
    """四种输入都能 init，各自落成对应后缀的 draft，纯文本抽得出来。"""
    html_src = ("<h2>周更小记：把复盘写短一点</h2>"
                "<p>上周我们把周会的复盘模板改短了，从八栏减到三栏。</p>"
                "<p>真正值得说的那一两句反而被埋掉了。</p>")
    cases = (
        ("draft.txt", DRAFT_V1, "draft.txt", "从八栏减到三栏"),
        ("draft.md", DRAFT_V1, "draft.md", "真正值得说的那一两句反而被埋掉了"),
        ("draft.html", html_src, "draft.html", "上周我们把周会的复盘模板改短了"),
        ("draft.docx", DRAFT_V1, "draft.txt", "容易漏掉需要长期跟进的项目"),
    )
    for name, text, landed, needle in cases:
        root = workspace(text=text, name=name)
        path = os.path.join(ws_dir(root), landed)
        check(os.path.isfile(path), "%s 应当落成 %s，实际目录：%r"
              % (name, landed, sorted(os.listdir(ws_dir(root)))))
        others = [f for f in os.listdir(ws_dir(root)) if f.startswith("draft.")]
        check(others == [landed], "工作区里同时只应有一份稿子，实际 %r" % others)
        pack = context(root)
        check(needle in pack["draft_text"], "%s 抽出的纯文本应含「%s」，实际开头：%r"
              % (name, needle, pack["draft_text"][:60]))
        check("<" not in pack["draft_text"], "纯文本里不应残留标签：%r" % pack["draft_text"][:80])


def t_context_hash_includes_brief():
    """brief 也进 context_hash：改了标准，旧批注就该作废。"""
    root = workspace()
    before = context(root)["context_hash"]
    changed = dict(BRIEF_V1)
    changed["purpose"] = "换一个目的：让读者愿意转发给同事"
    set_brief(root, changed)
    after = context(root)["context_hash"]
    check(before != after, "改了 brief.purpose 之后 context_hash 应当变，两次都是 %s" % before)
    rc, out, err = submit(root, marks_ok(), digest=before)
    check(rc == 1, "拿旧 context_hash 提交应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("context_hash" in out, "应当指出是 context_hash 对不上：\n%s" % out)


def t_marks_count_bounds():
    """0 条不算批注，31 条超过上限，两头都拒。"""
    root = workspace()
    rc, out, err = submit(root, [])
    check(rc == 1, "0 条批注应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("1" in out and "30" in out, "应当写明 1–30 条的区间：\n%s" % out)
    many = [{"quote": "第 %02d 处需要再想想" % i, "level": "remark",
             "note": "第 %02d 条批语，先占个位置。" % i} for i in range(1, 32)]
    rc, out, err = submit(root, many)
    check(rc == 1, "31 条批注应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("31" in out, "应当报出实际条数 31：\n%s" % out)
    check(not os.path.exists(os.path.join(ws_dir(root), "marks.json")),
          "闸门没过时不应写出 marks.json")


def t_fix_rules():
    """fix 不能等于原句、不能是三倍长的重写、也不能是空串。"""
    root = workspace()
    same = marks_ok()[:2]
    same[0]["fix"] = same[0]["quote"]
    rc, out, err = submit(root, same)
    check(rc == 1, "fix 与 quote 相同应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("相同" in out, "应当说明 fix 与引文相同：\n%s" % out)

    long_fix = marks_ok()[:2]
    long_fix[0]["fix"] = "这里应当换一种说法，把三栏各自负责什么讲清楚，再补一句为什么不是四栏。"
    check(len(long_fix[0]["fix"]) > 3 * len(long_fix[0]["quote"]), "用例材料本身应当超过三倍")
    rc, out, err = submit(root, long_fix)
    check(rc == 1, "fix 超过 quote 三倍应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("三倍" in out, "应当说明超过三倍：\n%s" % out)

    empty = marks_ok()[:2]
    empty[0]["fix"] = ""
    rc, out, err = submit(root, empty)
    check(rc == 1, "fix 为空串应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("空" in out, "应当说明 fix 是空串：\n%s" % out)

    good = marks_ok()[:2]
    good[0]["fix"] = "从八栏减成三栏"
    rc, out, err = submit(root, good)
    check(rc == 0, "合规的 fix 应当通过，rc=%d\n%s%s" % (rc, out, err))


def t_anchor_ratio():
    """锚定率 0.6 低于 0.7：拒收，并且把锚不上的引文逐条列出来。"""
    root = workspace()
    marks = marks_ok()[:3] + [
        {"quote": "这句话稿子里根本没有出现过", "level": "minor", "note": "这条引文是编的，锚不上。"},
        {"quote": "另外一句同样不存在的引文", "level": "minor", "note": "这条引文也是编的，锚不上。"},
    ]
    rc, out, err = submit(root, marks)
    check(rc == 1, "锚定率 0.6 应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("0.6" in out or "60" in out, "应当报出实际锚定率：\n%s" % out)
    check("这句话稿子里根本没有出现过" in out and "另外一句同样不存在的引文" in out,
          "应当逐条列出未锚定的引文：\n%s" % out)
    check(not os.path.exists(os.path.join(ws_dir(root), "review.html")),
          "闸门没过时不应写出 review.html")


def t_duplicate():
    """同一句被批两次、或两条批语一字不差，都是贴评语的迹象。"""
    root = workspace()
    dup_quote = marks_ok()[:3]
    dup_quote[2]["quote"] = dup_quote[0]["quote"]
    rc, out, err = submit(root, dup_quote)
    check(rc == 1, "两条引文相同应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("引文" in out and "重复" in out, "应当说明是引文重复：\n%s" % out)

    dup_note = marks_ok()[:3]
    dup_note[2]["note"] = dup_note[0]["note"]
    rc, out, err = submit(root, dup_note)
    check(rc == 1, "两条批语相同应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("批语" in out and "重复" in out, "应当说明是批语重复：\n%s" % out)


def t_coverage_warn():
    """引文全挤在开头 20%：提醒没读完，但不拦。"""
    root = workspace(text=DRAFT_FRONT)
    front = [
        {"quote": "开头这一段是引子", "level": "remark", "note": "引子可以再短半句。"},
        {"quote": "先把结论摆出来", "level": "minor", "note": "结论摆出来之后要马上给依据。"},
    ]
    rc, out, err = submit(root, front)
    check(rc == 0, "覆盖闸只警告不拦，应退出 0，rc=%d\n%s%s" % (rc, out, err))
    check("[WARN]" in out, "应当给出 WARN：\n%s" % out)
    check("20%" in out, "WARN 应当说明是集中在前 20%%：\n%s" % out)

    spread = workspace()
    rc, out, err = submit(spread, marks_ok())
    check(rc == 0, "散落全文的批注应当通过，rc=%d\n%s%s" % (rc, out, err))
    check("[WARN]" not in out, "批注散落全文时不该报覆盖 WARN：\n%s" % out)


def t_no_rewrite():
    """fix 加起来超过稿子一半：那是重写，不是批注。"""
    root = workspace()
    text = context(root)["draft_text"]
    filler = ("把这一段整体换成下面这版说法：先讲改之前是什么样子，再讲改之后是什么样子，"
              "中间补一句我们当时是怎么决定的，最后留一句代价在那里，读者才知道要不要照着自己试一遍。")
    marks = [
        {"quote": LONG_QUOTE_A, "level": "major", "note": "这一段建议整体重排。", "fix": filler},
        {"quote": LONG_QUOTE_B, "level": "major", "note": "这一段也建议整体重排。", "fix": filler[:-1]},
    ]
    total = sum(len(m["fix"]) for m in marks)
    check(total > len(text) * 0.5, "用例材料本身应当超过稿子一半：%d vs %d" % (total, len(text)))
    for m in marks:
        check(len(m["fix"]) <= 3 * len(m["quote"]), "单条 fix 不该先被三倍闸拦下")
    rc, out, err = submit(root, marks)
    check(rc == 1, "fix 总量超过稿子一半应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("一半" in out or "50%" in out, "应当说明超过稿子一半：\n%s" % out)


def t_history_append_only():
    """history/ 只增不改：第二次 review 不许动第一次留下的那份。"""
    root = workspace()
    rc, out, err = submit(root, marks_ok())
    check(rc == 0, "第一次 review 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    hist = os.path.join(ws_dir(root), "history")
    first = sorted(f for f in os.listdir(hist) if f.endswith(".json"))
    check(len(first) == 1, "第一次 review 后 history 应有一个文件，实际 %r" % first)
    snapshot = read(os.path.join(hist, first[0]))

    rc, out, err = submit(root, marks_ok()[:3])
    check(rc == 0, "第二次 review 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    files = sorted(f for f in os.listdir(hist) if f.endswith(".json"))
    check(len(files) == 2, "第二次 review 后 history 应有两个文件，实际 %r" % files)
    check(files[0] == first[0], "第一个文件的名字不该变：%r → %r" % (first, files))
    check(read(os.path.join(hist, files[0])) == snapshot, "第一个文件的内容不该被改写")
    later = json.loads(read(os.path.join(hist, files[1])))
    check(len(later["marks"]) == 3, "第二份快照应当记的是第二次的三条批注")
    check(later["draft_sha256"] == json.loads(snapshot)["draft_sha256"], "同一版稿子的哈希应当一致")


def t_stats_diff():
    """换了新版稿再批，stats 要说清上一版有几条挂不住了。"""
    root = workspace()
    rc, out, err = submit(root, marks_ok())
    check(rc == 0, "第一版 review 应退出 0，rc=%d\n%s%s" % (rc, out, err))

    src = os.path.join(root, "source", "draft-v2.md")
    write(src, DRAFT_V2)
    rc, out, err = run(root, "init", SLUG, "--from", src)
    check(rc == 0, "同一个 slug 再 init 应当当成新版本，rc=%d\n%s%s" % (rc, out, err))
    old = os.path.join(ws_dir(root), "history", "v1", "marks.json")
    check(os.path.isfile(old), "上一版的 marks 应当归入 history/v1/，实际：%r"
          % sorted(os.listdir(os.path.join(ws_dir(root), "history"))))

    rc, out, err = submit(root, marks_ok()[:3])
    check(rc == 0, "第二版 review 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    rc, out, err = run(root, "stats", SLUG)
    check(rc == 0, "stats 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    check("上一版" in out and "消失" in out, "stats 应当报出上一版消失了几条：\n%s" % out)
    check("2 条" in out, "第四段与结尾都没了，应当正好消失 2 条：\n%s" % out)
    check("锚定率" in out, "stats 应当给出锚定率：\n%s" % out)


def t_review_html():
    """红笔页自带样式：有锚点、没有任何外链。"""
    root = workspace()
    rc, out, err = submit(root, marks_ok())
    check(rc == 0, "review 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    page = read(os.path.join(ws_dir(root), "review.html"))
    check("data-an" in page, "红笔页里应当有锚点属性")
    check(page.count("data-an") >= 5, "五条批注都锚上了，锚点不该少于五个")
    for bad in ("http", "<link", "src=", "@import", "url("):
        check(bad not in page, "红笔页不该有外链（出现了 %s）" % bad)
    check("周更小记" in page and "结论下得很满" in page, "红笔页应当同时含原文与批语")


def t_check_examples():
    """examples/ 里的每个示例工作区都要 0 ERROR；示例还没建时跳过。"""
    base = os.path.join(SKILL_DIR, "examples", "drafts")
    if not os.path.isdir(base):
        raise Skipped("examples/drafts/ 还没建，等示例到位后本用例自动生效")
    dirs = sorted(os.path.join(base, d) for d in os.listdir(base)
                  if os.path.isdir(os.path.join(base, d)))
    check(dirs, "examples/drafts/ 下应当至少有一个示例工作区")
    for d in dirs:
        rc, out, err = run(SKILL_DIR, "check", d)
        check(rc == 0, "示例 %s 应当 0 ERROR，rc=%d\n%s%s" % (os.path.basename(d), rc, out, err))
        check("[ERROR]" not in out, "示例 %s 不该有 ERROR：\n%s" % (os.path.basename(d), out))


def t_export_no_text():
    """导出件只有哈希与计数，一个字的正文都不带。"""
    root = workspace()
    rc, out, err = submit(root, marks_ok())
    check(rc == 0, "review 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    rc, out, err = run(root, "export", SLUG)
    check(rc == 0, "export 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    pack = json.loads(out)
    check(sorted(pack) == ["anchored_ratio", "context_hash", "level_counts",
                           "marks_count", "slug", "versions"],
          "导出件的键应当固定为六个，实际 %r" % sorted(pack))
    check(pack["marks_count"] == 5 and pack["versions"] == 1, "计数应当对上：%r" % pack)
    check(pack["level_counts"] == {"major": 1, "minor": 2, "remark": 2},
          "等级分布应当对上：%r" % pack["level_counts"])
    for leak in ("周更小记", "从八栏减到三栏", "结论下得很满", "同事的原话"):
        check(leak not in out, "导出件里泄露了正文或批语：%s\n%s" % (leak, out))


def t_banned_scan():
    """整个 Skill 目录过一遍禁用词静态闸：无输出、退出 0。"""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import banned_words
    hits = banned_words.scan_dir(SKILL_DIR)
    check(hits == [], "Skill 目录不应含禁用词，实际：\n%s" % "\n".join(hits))
    proc = subprocess.run([PY, os.path.join(HERE, "banned_words.py"), SKILL_DIR],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", "replace")
    check(proc.returncode == 0 and out.strip() == "",
          "banned_words.py 扫 Skill 目录应当无输出退出 0，rc=%d\n%s" % (proc.returncode, out))


SELFTESTS = (
    t_init_from_txt_md_html_docx,
    t_context_hash_includes_brief,
    t_marks_count_bounds,
    t_fix_rules,
    t_anchor_ratio,
    t_duplicate,
    t_coverage_warn,
    t_no_rewrite,
    t_history_append_only,
    t_stats_diff,
    t_review_html,
    t_check_examples,
    t_export_no_text,
    t_banned_scan,
)


def main():
    failed = []
    skipped = 0
    probe = tempfile.mkdtemp(prefix="red-pen-selftest-")
    try:
        rc, out, err = run(probe, "doctor")
        if rc != 0 or "[OK]" not in out:
            failed.append("doctor")
            print("FAIL doctor：应退出 0 并列出可用组件，rc=%d\n%s%s" % (rc, out, err))
        else:
            print("pass doctor（%s）" % out.strip().split("\n")[0])
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    for fn in SELFTESTS:
        try:
            fn()
        except Skipped as e:
            skipped += 1
            print("skip %s：%s" % (fn.__name__, e))
        except Failed as e:
            failed.append(fn.__name__)
            print("FAIL %s：%s" % (fn.__name__, e))
        except Exception as e:
            failed.append(fn.__name__)
            print("FAIL %s：%s：%s" % (fn.__name__, type(e).__name__, e))
        else:
            print("pass %s" % fn.__name__)
        finally:
            sweep()
    engine = subprocess.run([PY, os.path.join(HERE, "anchor.py"), "selftest"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if engine.returncode != 0:
        failed.append("anchor.py selftest")
        print("FAIL 引擎自测：\n%s" % engine.stdout.decode("utf-8", "replace"))
    else:
        print("pass 引擎自测（anchor.py selftest）")
    if failed:
        print("%d/%d 个用例未通过：%s" % (len(failed), len(SELFTESTS) + 2, "、".join(failed)))
        return 1
    print("OK（%d 个用例全部通过，其中 %d 个跳过）" % (len(SELFTESTS) + 2, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
