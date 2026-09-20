#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""redpen.py 自测：在临时目录里建工作区，逐条验证六道闸门与八个子命令，最后打印 OK。

用法：python3 scripts/selftest.py
不依赖 examples/ 目录（示例还没建时 t_check_examples 记为跳过）；所有工作区都建在
临时目录里，跑完删除。稿子、批语、docx 全部是现造的合成材料。
"""

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
REDPEN = os.path.join(HERE, "redpen.py")
PY = sys.executable
SLUG = "weekly-note"
MARKS_NAME = "marks.json"

if HERE not in sys.path:
    sys.path.insert(0, HERE)
import redpen        # noqa: E402


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

# 四行、行与行之间不留空行的家长群公告：正文 31 字、纯文本 34 字符、只有一块，
# 而换行符数出来是 4 块 —— 短稿上两条地板与覆盖闸的块数前提都靠它验。
DRAFT_NOTICE = """各位家长好
本周五家长会改到晚上七点
请提前十分钟进会议室
辛苦大家
"""

# 六段英文邮件：第一块逐字是「Hi Dana,」（2 个字），第三块最长（646 字符），
# 全稿只用 ASCII。收件人与署名都是虚构的短名。
DRAFT_EN = """Hi Dana,

Thanks for sending the draft on Tuesday. I read it twice, once quickly and once with a pen, and I wrote down the three places that cost a reader the most. The draft itself is yours to change; I have not rewritten anything.

The middle section is where I lost the thread. It opens with the date change, moves to the budget, then comes back to the date two paragraphs later, and by that point I had forgotten which of the two dates was the one that moved. A reader skimming this on a phone will not scroll back to check. Put every date in one place, say plainly which one changed and which one did not, and only then explain why the change was needed. The reasons are the part you clearly care about most, and they land better once the reader is sure about the facts. Right now those facts are spread across four screens, with the same number written three different ways.

The closing line does not ask for anything. It says the team can reach out with questions, which is true of every message ever sent. Name the one thing you want back, and give a date for it.

One more thing on tone. The second half reads as an apology for a decision that, from everything here, was the right one. Say what changed and why, then stop.

Thanks,
Mo
"""

# 第四块里那句可以整句引的短句。
EN_ASK = "Name the one thing you want back, and give a date for it."

BRIEF_EN = {
    "audience": "the colleague who wrote the draft and will revise it themselves",
    "purpose": "point at the places that cost a reader the most and leave the rewriting to them",
    "worries": ["reads like a rewrite", "too vague to act on"],
    "lang": "en",
}

# 41 字的整句引文配 64 字的整段改法：改前 3×41=123 字符，放行；换尺之后落在天花板之外。
CAP_QUOTE = "三栏之后只剩下三个问题：这周最意外的一件事、下周准备换的做法、需要别人帮忙的地方。"
CAP_FIX = ("建议把这三个问题拆成三行分开写，每行前面加一个序号，再各补一句话说明这一栏要交代"
           "什么，读的人扫一眼就知道该看哪一行，不用来回翻。")


def notice_marks_ok():
    """公告上三条各带一个 12 字改法的批注：合计 36 字。"""
    return [
        {"quote": "各位家长好", "level": "remark",
         "note": "开头这一句没带任何信息，手机上第一眼看到的就是它。",
         "fix": "改成「家长会时间有变了」"},
        {"quote": "本周五家长会改到晚上七点", "level": "major",
         "note": "改到几点写了，原来是几点没写，家长会自己去翻旧消息。",
         "fix": "把新的时间单独放在第一行"},
        {"quote": "请提前十分钟进会议室", "level": "minor",
         "note": "提前十分钟到了之后去哪里等，这一句没有交代。",
         "fix": "再补一句进不去时找谁开门"},
    ]


def notice_marks_over():
    """公告上六条，引文互不重叠、改法各 10–13 字：合计 72 字，超过 60 字的地板。

    每条改法都落在自己的预算之内（改前是引文的三倍，改后是 20 字地板），
    所以响的只会是合计那一道闸。
    """
    return [
        {"quote": "各位家长好", "level": "remark",
         "note": "开头这一句没带任何信息。", "fix": "改成一句能一眼看见时间的话"},
        {"quote": "本周五家长会", "level": "minor",
         "note": "本周五和下周五在群里最容易看混。", "fix": "写清楚是本周五而不是下周五"},
        {"quote": "改到晚上七点", "level": "major",
         "note": "只写了改到几点，没写原来是几点。", "fix": "把原来的开会时间也写在旁边"},
        {"quote": "请提前十分钟", "level": "minor",
         "note": "提前十分钟到的人去哪里等着。", "fix": "说明早到的人可以在哪里等着"},
        {"quote": "进会议室", "level": "minor",
         "note": "哪一间会议室，通知里没有写。", "fix": "写明会议室在几楼几号"},
        {"quote": "辛苦大家", "level": "remark",
         "note": "结尾这一句可以换成一个动作。", "fix": "换成一句需不需要回复"},
    ]


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


DOCX_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
DOCX_DRAW_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def pack_docx(path, body):
    """把一段 w:body 的内容封成 docx；三个部件都摆齐，是一个真能打开的包。"""
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="%s" xmlns:mc="%s" xmlns:wp="%s">'
                '<w:body>%s</w:body></w:document>'
                % (DOCX_MAIN_NS, DOCX_MC_NS, DOCX_DRAW_NS, body))
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


def make_docx(path, text):
    """最小 docx：按空行切段，每段一个 w:p。"""
    return pack_docx(path, "".join(
        "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % block
        for block in [b.strip() for b in text.split("\n\n")] if block))


def make_rich_docx(path):
    """带表格与文本框的 docx：文本框那句同时写进 mc:Choice 与 mc:Fallback。

    这是 Word 真实的画法 —— 新版渲染器读 Choice，旧版读 Fallback，两份内容一样。
    朴素地 `root.iter(w:p)` 会把同一句读四次（外层段落吞一次 Choice 一次 Fallback，
    嵌套的两个 w:p 又各被当成顶层段落枚举一次）。
    """
    textbox = ("<w:txbxContent><w:p><w:r><w:t>文本框里的话</w:t></w:r></w:p></w:txbxContent>")
    body = (
        "<w:p><w:r><w:t>普通段落一</w:t></w:r></w:p>"
        "<w:tbl><w:tr>"
        "<w:tc><w:p><w:r><w:t>表格单元一</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>表格单元二</w:t></w:r></w:p></w:tc>"
        "</w:tr></w:tbl>"
        "<w:p><w:r><mc:AlternateContent>"
        "<mc:Choice Requires=\"wps\"><w:drawing><wp:anchor>%s</wp:anchor></w:drawing></mc:Choice>"
        "<mc:Fallback><w:pict>%s</w:pict></mc:Fallback>"
        "</mc:AlternateContent></w:r></w:p>"
        "<w:p><w:r><w:t>普通段落二</w:t></w:r></w:p>" % (textbox, textbox))
    return pack_docx(path, body)


RICH_DOCX_WANT = "普通段落一\n\n表格单元一\n\n表格单元二\n\n文本框里的话\n\n普通段落二\n"


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


def t_docx_table_and_textbox():
    """带表格与文本框的 docx：每句只读一次，顺序照旧。

    Word 会把文本框的内容同时写进 mc:Choice 与 mc:Fallback，还把它的 w:p 嵌在外层
    w:p 之下。朴素地枚举 w:p 会让同一句话出现四次（其中两次还糊在一起）——
    这个 Skill 的立身之本是稿子一个字都不改，输入侧静默失真同样不能接受。
    """
    root = tempfile.mkdtemp(prefix="red-pen-selftest-")
    _TEMPS.append(root)
    src = make_rich_docx(os.path.join(root, "rich.docx"))
    rc, out, err = run(root, "init", SLUG, "--from", src)
    check(rc == 0, "init 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    landed = read(os.path.join(ws_dir(root), "draft.txt"))
    check(landed == RICH_DOCX_WANT, "docx 抽出来的正文应当逐字等于期望：\n实际 %r\n期望 %r"
          % (landed, RICH_DOCX_WANT))
    for once in ("普通段落一", "表格单元一", "表格单元二", "文本框里的话", "普通段落二"):
        check(landed.count(once) == 1, "「%s」应当只出现一次，实际 %d 次：%r"
              % (once, landed.count(once), landed))
    order = [landed.index(x) for x in ("普通段落一", "表格单元一", "表格单元二",
                                       "文本框里的话", "普通段落二")]
    check(order == sorted(order), "段落顺序应当与文档一致，实际下标 %r" % order)
    pack = context(root)
    check(pack["draft_text"] == RICH_DOCX_WANT.strip().replace("\n\n", "\n"),
          "纯文本也应当每句一次：%r" % pack["draft_text"])


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
    """fix 不能等于原句、不能是超预算的重写、也不能是空串。

    验的是新 §5 主尺下的单条改法预算（`fix_budget`：引文的三倍，夹在 20 字地板与
    40 字天花板之间），不是原串字符数。
    """
    root = workspace()
    same = marks_ok()[:2]
    same[0]["fix"] = same[0]["quote"]
    rc, out, err = submit(root, same)
    check(rc == 1, "fix 与 quote 相同应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("相同" in out, "应当说明 fix 与引文相同：\n%s" % out)

    long_fix = marks_ok()[:2]
    long_fix[0]["fix"] = "这里应当换一种说法，把三栏各自负责什么讲清楚，再补一句为什么不是四栏。"
    check(redpen.unit_len(long_fix[0]["fix"])
          > redpen.fix_budget(redpen.unit_len(long_fix[0]["quote"])),
          "用例材料本身应当超预算")
    rc, out, err = submit(root, long_fix)
    check(rc == 1, "fix 超过 quote 三倍应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("预算" in out, "应当说明超过预算：\n%s" % out)

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
    check("重抄" not in out, "条数够多时不该再补那句指路提示（反例见 t_few_marks_hint）：\n%s" % out)
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
    """引文全挤在开头 20%：提醒没读完，但不拦。

    验的是新 §5 里覆盖闸那两条例外——比的是消毒后 HTML 里的起始偏移与 HTML 总长度
    （`FRONT_RATIO`），不是纯文本偏移；且以块数 ≥ 3 为前提（DRAFT_FRONT 有 4 块，
    不足三块的那一侧见 t_coverage_needs_three_blocks）。
    """
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
    """fix 加起来超过稿子一半：那是重写，不是批注。

    验的是新 §5 主尺下的合计预算（`total_fix_budget`：全稿字数的一半，短稿另有 60 字
    地板）。这颗牙的职责是证明新加的地板没有把长稿那一侧放松 —— 266 字的稿子走的是
    133 的比例预算，不是 60 的地板；四条改法各 36–38 字，都落在自己的单条预算之内，
    所以响的只会是合计那一道闸（短稿那一侧见 t_short_draft_budget）。
    """
    root = workspace()
    text = context(root)["draft_text"]
    marks = [
        {"quote": LONG_QUOTE_A, "level": "major",
         "note": "这一段建议整体重排，改前改后各说一遍。",
         "fix": "这一段建议先说改之前是什么样子，再说改之后是什么样子，中间补一句当时怎么定的"},
        {"quote": LONG_QUOTE_B, "level": "major",
         "note": "看板这一句只说了做法，没说边界在哪。",
         "fix": "看板那一句建议写清楚哪些事留在看板上、哪些事仍要进复盘，再举一个上周真实的例子"},
        {"quote": "上周我们把周会的复盘模板改短了，从八栏减到三栏。", "level": "minor",
         "note": "开头这一句把结论和数字挤在一起了。",
         "fix": "开头这一句可以把八栏与三栏各自的毛病列成两行对照，让读的人一眼看出少掉哪几栏"},
        {"quote": "有同事说三栏装不下跨部门的事，容易漏掉需要长期跟进的项目。", "level": "minor",
         "note": "跨部门这一条被压在段尾，容易被跳过。",
         "fix": "跨部门这一条建议单独起一段，先写以前漏掉过什么事，再写现在靠哪一张看板接住它们"},
    ]
    total_units = sum(redpen.unit_len(m["fix"]) for m in marks)
    budget = redpen.total_fix_budget(redpen.unit_len(text))
    check(total_units > budget,
          "用例材料本身应当超过合计预算：%d vs %d" % (total_units, budget))
    check(budget > redpen.FIX_TOTAL_MIN_UNITS,
          "这份稿子必须走比例预算而不是地板：%d vs %d" % (budget, redpen.FIX_TOTAL_MIN_UNITS))
    for m in marks:
        check(redpen.unit_len(m["fix"]) <= redpen.fix_budget(redpen.unit_len(m["quote"])),
              "单条 fix 不该先被逐条预算闸拦下")
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


def t_check_tamper():
    """check 是发布闸靠的那道门：干净工作区 0 ERROR，动过手脚的一律逮住。"""
    root = workspace()
    rc, out, err = submit(root, marks_ok())
    check(rc == 0, "review 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    rc, out, err = run(root, "check", SLUG)
    check(rc == 0 and "[ERROR]" not in out, "干净工作区应当 0 ERROR 退出 0，rc=%d\n%s" % (rc, out))

    page = os.path.join(ws_dir(root), "review.html")
    keep_page = read(page)
    write(page, keep_page + "<!-- 手改一笔 -->")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "[ERROR]" in out, "手改红笔页应当被逮住，rc=%d\n%s" % (rc, out))
    check("红笔页" in out, "应当说明是红笔页被改过：\n%s" % out)
    write(page, keep_page)

    record = os.path.join(ws_dir(root), MARKS_NAME)
    keep_record = read(record)
    tampered = json.loads(keep_record)
    tampered["marks"][0]["note"] = "偷偷把这条批语换掉，红笔页就对不上了。"
    write(record, json.dumps(tampered, ensure_ascii=False, indent=2) + "\n")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "[ERROR]" in out, "手改 marks.json 应当被逮住，rc=%d\n%s" % (rc, out))

    # 只有「重新过一遍闸门」这条路能逮住的篡改：hash 不进红笔页，页面比对看不见它
    forged = json.loads(keep_record)
    forged["context_hash"] = "0" * 64
    write(record, json.dumps(forged, ensure_ascii=False, indent=2) + "\n")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "context_hash" in out, "假的 context_hash 应当被逮住，rc=%d\n%s" % (rc, out))
    write(record, keep_record)

    draft = os.path.join(ws_dir(root), "draft.md")
    keep_draft = read(draft)
    write(draft, keep_draft + "\n偷偷加的一段，批注都还挂在旧稿上。\n")
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "[ERROR]" in out, "改过稿子应当被逮住，rc=%d\n%s" % (rc, out))
    check("哈希" in out, "应当说明是稿子的哈希对不上：\n%s" % out)
    write(draft, keep_draft)

    os.remove(page)
    rc, out, err = run(root, "check", SLUG)
    check(rc == 1 and "缺红笔页" in out, "删掉红笔页应当被逮住，rc=%d\n%s" % (rc, out))

    rc, out, err = run(root, "review", SLUG)
    check(rc == 0, "重跑 review 应当把工作区恢复成合规状态，rc=%d\n%s%s" % (rc, out, err))
    rc, out, err = run(root, "check", SLUG)
    check(rc == 0 and "[ERROR]" not in out, "重跑 review 之后应当重新 0 ERROR：\n%s" % out)


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


def t_unit_len_is_normalization_blind():
    """字数口径：汉字逐字计、连着的字母数字算一个单位、标点空白不计，且对规范化不敏感。

    这颗牙不起子进程，验的是那把尺本身。同一句话的三种写法（弯引号、全角空格、
    多打空格）必须数出同一个值，也必须与规范化之后的值相同 —— 闸门的宽严不许随
    排版微调漂移。末尾两端一致性把预算函数的地板与天花板一起钉住。
    """
    check(redpen.unit_len("Hi Dana,") == 2,
          "英文两个词应当是 2 个字，实际 %r" % redpen.unit_len("Hi Dana,"))
    check(redpen.unit_len("问不清楚的先不报") == 8,
          "八个汉字应当是 8 个字，实际 %r" % redpen.unit_len("问不清楚的先不报"))
    punct = "，。！？ 　“”"
    check(redpen.unit_len(punct) == 0,
          "纯标点空白串应当是 0 个字，实际 %r" % redpen.unit_len(punct))

    plain = 'He said "we ship on Friday" and left.'
    curly = 'He said “we ship on Friday” and left.'
    wide = 'He said　"we ship on Friday"　and left.'
    spaced = 'He  said   "we ship on Friday"   and left.'
    sizes = [redpen.unit_len(s) for s in (plain, curly, wide, spaced)]
    check(len(set(sizes)) == 1, "同一句话的三种写法应当数出同一个值，实际 %r" % sizes)
    for s in (plain, curly, wide, spaced):
        check(redpen.unit_len(redpen.anchor.normalize(s)) == sizes[0],
              "规范化前后应当同一个值：%r → %d，期望 %d"
              % (s, redpen.unit_len(redpen.anchor.normalize(s)), sizes[0]))

    check(redpen.fix_budget(0) == redpen.FIX_MIN_UNITS == 20,
          "引文为 0 字时单条预算应当落在地板 20，实际 %r" % redpen.fix_budget(0))
    check(redpen.fix_budget(10 ** 6) == redpen.FIX_MAX_UNITS == 40,
          "引文再长也不许超过天花板 40，实际 %r" % redpen.fix_budget(10 ** 6))
    check(redpen.total_fix_budget(0) == redpen.FIX_TOTAL_MIN_UNITS == 60,
          "空稿的合计预算应当落在地板 60，实际 %r" % redpen.total_fix_budget(0))


def t_fix_budget_floor():
    """英文短引文也要有写得完一句话的改法预算：单条预算的地板是 20 字。

    改前实测：`[ERROR] 第 1 条的 fix 有 28 字，超过引文 8 字的三倍`，rc=1 ——
    「Hi Dana,」规范化后是 8 个字符，三倍只有 24，一句 28 个字符（7 个词）的
    建议就被逼着削成半句。换尺之后引文是 2 个字，3×2 落到地板 20，这条改法过得了。
    """
    root = workspace(text=DRAFT_EN, name="draft.txt", brief=BRIEF_EN)
    marks = [
        {"quote": "Hi Dana,", "level": "minor",
         "note": "The greeting takes a whole line and then stalls before any ask.",
         "fix": "Add a one-line ask under it."},
        {"quote": EN_ASK, "level": "major",
         "note": "This is the only sentence that tells the reader what to do next."},
    ]
    rc, out, err = submit(root, marks)
    check(rc == 0, "英文短引文配一句可照抄的改法应当过闸，rc=%d\n%s%s" % (rc, out, err))


def t_fix_budget_cap():
    """引一整段就能还一整段的路要堵上：单条预算的天花板是 40 字。

    材料是 41 字的整句引文配 64 字的整段改法：改前三倍闸的上限是 123 字符，当场
    放行 rc=0 —— 这颗牙今天失败在 `check(rc == 1, …)` 那一行，那正是它要盯的洞。
    """
    root = workspace()
    marks = [
        {"quote": CAP_QUOTE, "level": "major",
         "note": "三个问题挤在一句里，读的人得自己数着顿号拆。", "fix": CAP_FIX},
        {"quote": "读的人反而记住了更多东西", "level": "minor",
         "note": "结论下得很满，缺一个可核对的依据。"},
    ]
    cap_units, quote_units = redpen.unit_len(CAP_FIX), redpen.unit_len(CAP_QUOTE)
    check(cap_units > redpen.FIX_MAX_UNITS,
          "用例材料必须超过天花板 %d 字，否则验不到天花板，实际 %d 字"
          % (redpen.FIX_MAX_UNITS, cap_units))
    check(cap_units <= redpen.FIX_MAX_RATIO * quote_units,
          "用例材料不该先被三倍那一档拦下（%d 字 vs %d × %d 字），否则拦住它的就不是天花板"
          % (cap_units, redpen.FIX_MAX_RATIO, quote_units))
    rc, out, err = submit(root, marks)
    check(rc == 1, "整段改法应当被天花板拦下，rc=%d\n%s%s" % (rc, out, err))
    check("最多" in out, "应当报出预算构成、说明最多能写多少字：\n%s" % out)


def t_quote_char_ceiling():
    """引文双条件：新口径的 200 字之外，再加一道原串字符硬顶。

    引文从常量现算（`QUOTE_MAX_CHARS + 120`），将来常量动了这颗牙跟着动。前置断言
    先把「拦住它的是哪道闸」钉死：这条引文的字数落在 200 以内，所以响的必须是字符
    硬顶而不是字数闸。改前的脚本对同一条引文报的是「引文有 519 字，超过 200 字上限」
    （520 个字符里末尾那个空格被 strip 掉了），里面没有「字符」二字 —— 手工对照见 PR，
    那句话就是这颗牙要接管的那句事实。
    """
    quote = max(DRAFT_EN.split("\n\n"), key=len)[:redpen.QUOTE_MAX_CHARS + 120]
    check(redpen.unit_len(quote) < redpen.QUOTE_MAX,
          "引文的字数必须落在 %d 以内，否则先响的是字数闸、这颗牙就验不到字符硬顶"
          % redpen.QUOTE_MAX)
    root = workspace(text=DRAFT_EN, name="draft.txt", brief=BRIEF_EN)
    marks = [
        {"quote": quote, "level": "minor",
         "note": "Quoting most of a paragraph is not a line-level comment."},
        {"quote": EN_ASK, "level": "major",
         "note": "This is the only sentence that tells the reader what to do next."},
    ]
    rc, out, err = submit(root, marks)
    check(rc == 1, "超过字符硬顶的引文应当被拒收，rc=%d\n%s%s" % (rc, out, err))
    check("字符" in out, "应当说明拦住它的是字符硬顶：\n%s" % out)


def t_note_min_counts_words():
    """批语下限 6 从字符换成字：中文一个字不变，英文侧从 6 个字符收紧成 6 个词。

    第一条沿用 t_fix_budget_floor 那条（改前被三倍闸拦下，换尺之后落在 20 字地板
    之内），第二条的批语是「Too vague.」——10 个字符过得了今天的 NOTE_MIN，只有 2
    个词。今天这份提交是被第 1 条的三倍闸拦下的，输出里没有「批语」二字，这颗牙红
    在关键词那一行。
    """
    root = workspace(text=DRAFT_EN, name="draft.txt", brief=BRIEF_EN)
    marks = [
        {"quote": "Hi Dana,", "level": "minor",
         "note": "The greeting takes a whole line and then stalls before any ask.",
         "fix": "Add a one-line ask under it."},
        {"quote": EN_ASK, "level": "major", "note": "Too vague."},
    ]
    check(redpen.unit_len(marks[1]["note"]) < redpen.NOTE_MIN <= len(marks[1]["note"]),
          "第二条的批语必须字数不足而字符数够（%d 字 / %d 字符，NOTE_MIN=%d），否则验的就不是换尺"
          % (redpen.unit_len(marks[1]["note"]), len(marks[1]["note"]), redpen.NOTE_MIN))
    rc, out, err = submit(root, marks)
    check(rc == 1, "两个词的批语应当被拒收，rc=%d\n%s%s" % (rc, out, err))
    check("批语" in out, "应当说明是批语太短：\n%s" % out)


def t_short_draft_budget():
    """短稿的合计预算要有地板 60 字，否则三条正常改法就顶掉一整篇群公告。

    正例：31 字的公告上三条批注、改法合计 36 字。改前实测
    `[ERROR] fix 合计 36 字，超过全稿 34 字的一半`、rc=1 —— 这颗牙今天红在这里。
    反例：同一份公告上六条、改法合计 72 字，超过 60 字的地板，仍要被拦下；六条改法
    各自都落在自己的预算之内，所以响的只会是合计那一道闸。
    """
    root = workspace(text=DRAFT_NOTICE, name="draft.txt")
    rc, out, err = submit(root, notice_marks_ok())
    check(rc == 0, "短稿上三条正常改法应当过闸，rc=%d\n%s%s" % (rc, out, err))
    check("[WARN]" not in out, "短稿上不该再有提醒：\n%s" % out)

    over = workspace(text=DRAFT_NOTICE, name="draft.txt")
    rc, out, err = submit(over, notice_marks_over())
    check(rc == 1, "合计超过地板 60 字仍应拒收，rc=%d\n%s%s" % (rc, out, err))
    check("合计" in out, "应当说明是改法合计超了：\n%s" % out)


def t_coverage_needs_three_blocks():
    """稿子不足三块就不提醒「只批了开头」：单块短公告上那句提醒本来就无从谈起。

    改前实测：`[WARN] 所有引文都落在稿子前 20% 的篇幅里……` —— 公告只有一块，
    引文落在哪里都是「前 20%」，这颗牙今天红在 `"[WARN]" not in out` 那一行。
    这次修改没有把提醒整体关掉，证据是现成的 t_coverage_warn：DRAFT_FRONT 有 4 块，
    批注挤在开头时仍必须出 WARN 且含「20%」，那条用例一个字都没动。
    """
    root = workspace(text=DRAFT_NOTICE, name="draft.txt")
    marks = [{"quote": "各位家长好", "level": "remark",
              "note": "开头这一句没带任何信息，手机上第一眼看到的就是它。"}]
    rc, out, err = submit(root, marks)
    check(rc == 0, "单条批注的公告应当过闸，rc=%d\n%s%s" % (rc, out, err))
    check("[WARN]" not in out, "只有一块的稿子不该报覆盖 WARN：\n%s" % out)


def t_few_marks_hint():
    """条数少又锚不上时补一句指路：回原文重抄，不是删条凑比例。

    三条里锚上两条（2/3 = 0.67 低于 0.7），改前报的是「请照原文一字不差地重引」，
    里面没有「重抄」二字 —— 这颗牙今天红在关键词那一行。这句提示按条数触发，条数够
    多时不打，反例是现成的 t_anchor_ratio（5 条里锚不上 2 条，那份输出里不许出现「重抄」）。
    """
    root = workspace()
    marks = marks_ok()[:2] + [
        {"quote": "这句话稿子里根本没有出现过", "level": "minor", "note": "这条引文是编的，锚不上。"},
    ]
    rc, out, err = submit(root, marks)
    check(rc == 1, "锚定率 0.67 应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("重抄" in out, "条数少时应当补一句回原文重抄：\n%s" % out)


def t_init_units_line():
    """init 那一行的字数换成新口径，并且把口径当场写清楚；语言那一项有依据时才打。

    字数从 fixture 现算 —— `cmd_init` 算的就是 `unit_len(anchor.plain_text(text))`，
    两边同源，换了正文也不用回来改断言。「（汉字按字、英文按词，标点不算）」是本期
    定型的措辞，逐字钉死，也是与期 2 之间的契约。
    """
    want = "正文 %d 字" % redpen.unit_len(redpen.anchor.plain_text(DRAFT_EN))
    root = tempfile.mkdtemp(prefix="red-pen-selftest-")
    _TEMPS.append(root)
    src = os.path.join(root, "source", "mail.txt")
    write(src, DRAFT_EN)
    rc, out, err = run(root, "init", "mail-en", "--from", src)
    check(rc == 0, "init 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    check(want in out, "字数行应当写成「%s」：\n%s" % (want, out))
    check("（汉字按字、英文按词，标点不算）" in out, "字数行应当逐字带上口径说明：\n%s" % out)
    check("批语语言" not in out, "第一次收稿又没给 --lang 时不该猜批语语言：\n%s" % out)

    rc, out, err = run(root, "init", "mail-en-2", "--from", src, "--lang", "en")
    check(rc == 0, "init --lang en 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    check("· 批语语言 en" in out, "给了 --lang 就该把批语语言打出来：\n%s" % out)

    zh_src = os.path.join(root, "source", "weekly.md")
    write(zh_src, DRAFT_V1)
    rc, out, err = run(root, "init", "weekly-zh", "--from", zh_src)
    check(rc == 0, "init 中文稿应退出 0，rc=%d\n%s%s" % (rc, out, err))
    got = re.search(r"正文 (\d+) 字", out)
    check(got, "init 应当打出正文字数：\n%s" % out)
    plain = len(redpen.anchor.plain_text(DRAFT_V1))
    check(int(got.group(1)) != plain,
          "中文稿的字数不该等于纯文本的 %d 个字符（那是没换口径）：\n%s" % (plain, out))


def t_gates_ignore_lang():
    """闸门的宽严绝不许挂在 brief.lang 上 —— 那是 Agent 自己写得动的字段。

    挂上去就等于开了一条「把 lang 改成 en 就能拿到更宽预算」的道。同一份稿子、
    同一套会被逐条闸拦下的批注，brief.lang 一个 zh 一个 en，两次 review 的退出码与
    全部 [ERROR] 行必须逐字相同（context_hash 不同不影响闸门结论）。这是一条不变量，
    今天就该成立；它防的是将来。
    """
    def submitted(lang):
        brief = dict(BRIEF_V1)
        brief["lang"] = lang
        root = workspace(brief=brief)
        marks = marks_ok()[:2]
        marks[0]["fix"] = "这里应当换一种说法，把三栏各自负责什么讲清楚，再补一句为什么不是四栏。"
        rc, out, err = submit(root, marks)
        return rc, [line for line in out.split("\n") if line.startswith("[ERROR]")]

    rc_zh, errs_zh = submitted("zh")
    rc_en, errs_en = submitted("en")
    check(errs_zh, "用例材料本身应当至少触发一条 [ERROR]，否则这条不变量验不到东西")
    check(rc_zh == rc_en, "两种批语语言的退出码应当相同：zh=%d en=%d" % (rc_zh, rc_en))
    check(errs_zh == errs_en,
          "两种批语语言的 [ERROR] 行应当逐字相同：\nzh：\n%s\nen：\n%s"
          % ("\n".join(errs_zh), "\n".join(errs_en)))


DOC_CONSTANTS = ("MARKS_MAX", "QUOTE_MAX", "QUOTE_MAX_CHARS", "NOTE_MIN", "FIX_MAX_RATIO",
                 "FIX_MIN_UNITS", "FIX_MAX_UNITS", "FIX_TOTAL_MIN_UNITS",
                 "FRONT_MIN_BLOCKS", "MIN_ANCHORED")


def t_doc_numbers_match():
    """契约同步牙：闸门那一节里的数字要与脚本常量对得上。

    局限写在这里 —— 个位数（3）会被这一节里别处的数字碰巧匹配上，所以它防的是
    「改了常量忘了改文档」，不是「文档写得对」。文档不在时记为跳过。
    """
    doc = os.path.join(SKILL_DIR, "references", "workspace-format.md")
    if not os.path.isfile(doc):
        raise Skipped("references/workspace-format.md 还没到位")
    text = read(doc)
    lo, hi = text.find("## 4."), text.find("## 6.")
    check(lo >= 0 and hi > lo, "workspace-format.md 里应当有 ## 4. 与 ## 6. 两节")
    section = text[lo:hi]
    for name in DOC_CONSTANTS:
        value = getattr(redpen, name)
        check(str(value) in section,
              "常量 %s = %s 没有出现在闸门那一节里：改了常量要同一个 commit 改文档" % (name, value))


SELFTESTS = (
    t_init_from_txt_md_html_docx,
    t_docx_table_and_textbox,
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
    t_check_tamper,
    t_export_no_text,
    t_banned_scan,
    # 期 1：口径 → 形状闸 → 覆盖闸 → 锚定闸 → init → 护栏
    t_unit_len_is_normalization_blind,
    t_fix_budget_floor,
    t_fix_budget_cap,
    t_quote_char_ceiling,
    t_note_min_counts_words,
    t_short_draft_budget,
    t_coverage_needs_three_blocks,
    t_few_marks_hint,
    t_init_units_line,
    t_gates_ignore_lang,
    t_doc_numbers_match,
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
