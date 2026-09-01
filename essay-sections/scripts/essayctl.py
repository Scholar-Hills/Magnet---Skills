#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""essay-sections 分段写作脚本（零依赖，Python 3.8+ 标准库，单文件）。

把一篇写好的稿子拆成「开头 + 若干子问题段 + 结论」，一段一张卡。脚本只干四件事：
按偏移把原文切开（一个字不改，块外的文字逐条列出来，不静默丢）、把每次评审连同当刻
原文钉进只增不改的账本、在你改了原文之后标出哪些分数已经过期、把结果摆成一页卡片。
写作是你的事，措辞是模型的事，脚本只管纪律。

子命令：
  doctor                                    看本机环境与工作区在哪
  init <slug> [--title …]                   建工作区 essays/<slug>
  meta <slug> [--title …]                   改题目 / 文体 / 级别 / 场景 / 目标字数 / 背景 / 主论点
  import <slug> <file>                      md / txt / html / docx → 切块编号 + 记字节偏移
  assemble <slug> --from inbox/groups.json  按偏移切回分段，做保真校验，写拆分报告
  outline add <slug> --from inbox/…         拆题（初始 6–10 条 / 增补 ≤4 条 / 合计封顶 4 轮）
  context <slug> <segment>                  输出上下文包 JSON（stdout 只有 JSON）
  review add <slug> <segment> --from …      跑分值 / 证据 / 新鲜度 / 空心闸后入账
  reflect add <slug> [--segment …] --from … 写一条反思（区域反思要评分触发）
  reading add <slug> <segment> --from …     记一份荐读（默认标「引用未核实」）
  version <slug>                            给 sections/ 拍一个版本快照
  status <slug>                             每段一个块：哈希、mtime、最新分、走势、过期标记
  report <slug>                             生成 report.html 分段卡
  export <slug> [--evidence]                导出整篇（带侧注）或脱敏证据包
  check <slug|dir> [--rebuild-index]        离线复核整个工作区（发布闸第 2 项）

退出码：0 通过 / 1 闸门不过 / 2 用法或前置条件不满足。
目录与 JSON 契约见 references/workspace-format.md；纪律见 references/workflow-rules.md。
"""

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

# ---- 闸门常量（改这里必须同步改 references/workspace-format.md 与 selftest.py）
DIMS = ("language", "answersSubquestion", "advancesThesis")
REVIEW_KEYS = ("contextHash", "scores", "note", "quotes")
REFLECT_KEYS = ("text",)
READING_KEYS = ("title", "authors", "year", "summary", "url", "verified")
READING_MUST = ("title", "authors", "year")
HANDOFF_KEYS = ("improved", "rewrite")       # 改句子是 red-pen 的活，出现即拒收
MIN_PLAIN = 10                               # 分区纯文本不足这么多字就不给评
QUOTE_RATIO = 0.40                           # 单条与合计引用长度上限（占该段比例）
SHORT_QUOTE = 10                             # 「只引了一小截」的门槛
REFLECT_MAX = 4000                           # 反思纯文本上限
NO_DIFF_AT = 20000                           # 快照超过这么长就不再比对，免得永久误报
OUTLINE_ROUNDS = 4                           # 拆题合计轮数上限
OUTLINE_INITIAL = (6, 10)                    # 初始模式条数区间
OUTLINE_EXTRA = 4                            # 增补模式条数上限
TREND_DOTS = 20                              # report 里最多画多少个走势点（账本一行不丢）
LOOK_ALIKE = 0.6                             # 评语词集 Jaccard 到这个值就算雷同
HEAD_MAX = 80                                # 判标题的长度上限
PREVIEW = 46                                 # 给模型看的每块预览长度

SETTINGS = ("timed", "untimed")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SEGMENT_RE = re.compile(r"^(intro|conclusion|body-\d{2})$")
GENESIS = hashlib.sha256(b"").hexdigest()

ESSAYS_DIR = "essays"
SECTIONS = "sections"
LEDGER = "ledger"
INBOX = "inbox"
READINGS = "readings"
VERSIONS = "versions"
ESSAY_NAME = "essay.json"
SOURCE_NAME = "source.txt"
BLOCKS_NAME = "blocks.json"
OUTLINE_NAME = "outline.jsonl"
REFLECT_NAME = "reflections.jsonl"
CHAINS_NAME = "chains.json"
SPLIT_NAME = "split-report.md"
PAGE_NAME = "report.html"
VERSION_RE = re.compile(r"^v(\d+)$")

MARK_CHANGED = "原文已修改"
MARK_UNSURE = "引用未核实"
MARK_SAME = "同稿重评"

# 开头段与结论段没有子问题，用一句结构说明顶上，好让三类段落同权。
ROLE_INTRO = "开头段：交代题目、给出主论点。"
ROLE_CONCLUSION = "结论段：收束全文，回到主论点。"

_SPACE = re.compile(r"\s+")
_TAG = re.compile(r"<!--.*?-->|</?([A-Za-z][A-Za-z0-9:-]*)(?:\s[^<>]*?)?/?>", re.S)
_PARA_SEP = re.compile(r"\n[ \t]*\n\s*")
_WORD = re.compile(r"[A-Za-z0-9']+")
_CJK = re.compile(r"[㐀-鿿぀-ヿ가-힯]")
INLINE_TAGS = frozenset((
    "a", "b", "i", "em", "strong", "span", "code", "u", "sup", "sub", "small",
    "mark", "abbr", "q", "cite", "s", "del", "ins", "font", "img", "wbr",
))
HEAD_TAGS = frozenset(("h1", "h2", "h3", "h4", "h5", "h6"))

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
WORD_MAIN = "word/document.xml"
TXBX = WORD_NS + "txbxContent"

# 只在拆分报告的「未纳入分段」里用：这里出现的 block 就是没被分到任何一段的块
ROLE_LABEL = {"block": "没分到段的块", "space": "空白", "outside": "块外文字",
              "table": "表格", "textbox": "文本框"}


class UsageError(Exception):
    """用法或前置条件错误，退出码 2。"""


class GateError(Exception):
    """闸门不过，退出码 1。"""


# ---------------------------------------------------------------- 小工具

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read().replace("\r\n", "\n").replace("\r", "\n")
    except FileNotFoundError:
        raise UsageError("找不到文件：%s" % path)
    except IsADirectoryError:
        raise UsageError("这是一个目录而不是文件：%s" % path)
    except UnicodeDecodeError as e:
        raise UsageError("文件不是 UTF-8 编码：%s（%s）" % (path, e))


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_json(path):
    try:
        return json.loads(read_text(path))
    except ValueError as e:
        raise UsageError("JSON 解析失败：%s（%s）" % (path, e))


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def canonical(obj):
    """哈希与账本行用的规范 JSON：不转义非 ASCII、键排序、不留空格。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso():
    stamp = datetime.datetime.now(datetime.timezone.utc)
    return stamp.replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def plain_text(raw):
    """剥标签、还原实体、压空白。`x<0` 这类符号不算标签，不许吞掉。"""
    stripped = _TAG.sub(" ", raw or "")
    return _SPACE.sub(" ", html.unescape(stripped)).strip()


def squeeze(text):
    """引用比对用：去掉全部空白（含全角空格），跨行换行的引用也能对上。"""
    return _SPACE.sub("", text or "")


def clip(text, width=PREVIEW):
    one = _SPACE.sub(" ", str(text or "")).strip()
    return one if len(one) <= width else one[:width] + "…"


def token_set(text):
    """评语词集：英文按词，中日韩按相邻两字，两种语言都能比。"""
    folded = squeeze(text).lower()
    words = set(_WORD.findall((text or "").lower()))
    grams = set(folded[i:i + 2] for i in range(len(folded) - 1) if _CJK.search(folded[i:i + 2]))
    return words | grams


def trigrams(text):
    folded = squeeze(text).lower()
    return set(folded[i:i + 3] for i in range(len(folded) - 2))


def jaccard(left, right):
    if not left or not right:
        return 0.0
    return len(left & right) / float(len(left | right))


def round_half_up(value):
    return int(value + 0.5)


def check_slug(name):
    if not SLUG_RE.match(name or ""):
        raise UsageError("稿名只能是小写字母、数字与连字符（不超过 64 位），当前是：%r" % name)
    return name


def check_segment(name):
    if not SEGMENT_RE.match(name or ""):
        raise UsageError("分区名只能是 intro / body-01…body-NN / conclusion，当前是：%r" % name)
    return name


def is_int(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def mtime_of(path):
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return "-"
    return datetime.datetime.fromtimestamp(stamp).replace(microsecond=0).isoformat(" ")


# ---------------------------------------------------------------- 工作区

class Workspace(object):
    """一篇 essay 的工作区；只有脚本能写账本，Agent 只能往 inbox/ 放载荷。"""

    def __init__(self, path, must_exist=True):
        self.dir = path
        self.slug = os.path.basename(path.rstrip(os.sep))
        if must_exist and not os.path.isdir(path):
            raise UsageError("工作区不存在：%s（先跑 init <slug>）" % self.rel(path))
        self.essay_path = os.path.join(path, ESSAY_NAME)
        self.source_path = os.path.join(path, SOURCE_NAME)
        self.blocks_path = os.path.join(path, BLOCKS_NAME)
        self.outline_path = os.path.join(path, OUTLINE_NAME)
        self.reflect_path = os.path.join(path, REFLECT_NAME)
        self.chains_path = os.path.join(path, CHAINS_NAME)

    # -- 路径
    def at(self, *parts):
        return os.path.join(self.dir, *parts)

    def rel(self, path):
        try:
            return os.path.relpath(path, os.getcwd())
        except ValueError:
            return path

    def section_path(self, name):
        return self.at(SECTIONS, "%s.md" % name)

    def ledger_rel(self, name):
        return "%s/%s.jsonl" % (LEDGER, name)

    # -- essay.json
    def essay(self):
        if not os.path.isfile(self.essay_path):
            raise UsageError("缺 %s，这个目录不像工作区：%s" % (ESSAY_NAME, self.rel(self.dir)))
        data = read_json(self.essay_path)
        if not isinstance(data, dict):
            raise UsageError("%s 必须是一个 JSON 对象" % ESSAY_NAME)
        return data

    def save_essay(self, data):
        write_json(self.essay_path, data)

    def segment_names(self):
        return [s["name"] for s in self.essay().get("segments") or []]

    def segment_entry(self, name):
        for item in self.essay().get("segments") or []:
            if item.get("name") == name:
                return item
        raise UsageError("这一篇里没有分区 %s（先跑 assemble 或 outline add）" % name)

    def section_raw(self, name):
        path = self.section_path(name)
        if not os.path.isfile(path):
            raise UsageError("缺分区文件：%s" % self.rel(path))
        return read_text(path)

    # -- 账本
    def rows(self, rel):
        path = self.at(*rel.split("/"))
        if not os.path.isfile(path):
            return []
        out = []
        for line in read_text(path).split("\n"):
            if line.strip():
                out.append(json.loads(line))
        return out

    def raw_lines(self, rel):
        path = self.at(*rel.split("/"))
        if not os.path.isfile(path):
            return []
        return [ln for ln in read_text(path).split("\n") if ln.strip()]

    def chains(self):
        if not os.path.isfile(self.chains_path):
            return {}
        data = read_json(self.chains_path)
        return data if isinstance(data, dict) else {}

    def append_row(self, rel, row):
        """只以追加模式写一行；seq 与 prevHash 由脚本算，谁也不许手填。"""
        path = self.at(*rel.split("/"))
        lines = self.raw_lines(rel)
        body = dict(row)
        body["seq"] = len(lines) + 1
        body["when"] = now_iso()
        body["prevHash"] = sha256_text(lines[-1]) if lines else GENESIS
        line = canonical(body)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
        tips = self.chains()
        tips[rel] = {"seq": body["seq"], "hash": sha256_text(line)}
        write_json(self.chains_path, tips)
        return body

    def reviews(self, name):
        return [r for r in self.rows(self.ledger_rel(name)) if r.get("stage") == "review"]

    def latest_review(self, name):
        rows = self.reviews(name)
        return rows[-1] if rows else None

    def reflections(self):
        return [r for r in self.rows(REFLECT_NAME) if r.get("stage") == "reflect"]

    def version_numbers(self):
        base = self.at(VERSIONS)
        if not os.path.isdir(base):
            return []
        found = []
        for name in os.listdir(base):
            m = VERSION_RE.match(name)
            if m and os.path.isdir(os.path.join(base, name)):
                found.append(int(m.group(1)))
        return sorted(found)

    def version_dirs(self):
        return ["v%d" % n for n in self.version_numbers()]

    def version_count(self):
        return len(self.version_numbers())

    def latest_version(self):
        """编号只增不回收：中间那一版被删掉了，下一版也接着最大号往后排，绝不撞号。"""
        numbers = self.version_numbers()
        return numbers[-1] if numbers else 0

    def chain_rels(self):
        """这个工作区里的三类账本（拆题 / 反思 / 每段评审），按固定顺序。"""
        rels = [OUTLINE_NAME, REFLECT_NAME]
        base = self.at(LEDGER)
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                if name.endswith(".jsonl"):
                    rels.append("%s/%s" % (LEDGER, name))
        return rels

    def rebuild_chains(self):
        """按各条链的实际内容重写链尾索引；只在每条链自身复算自洽时才该调用。"""
        tips = {}
        for rel in self.chain_rels():
            lines = self.raw_lines(rel)
            if lines:
                tips[rel] = {"seq": len(lines), "hash": sha256_text(lines[-1])}
        write_json(self.chains_path, tips)
        return tips

    def consume(self, path):
        """脚本消费掉 inbox/ 里的载荷；载荷在别处就不动它。"""
        full = os.path.realpath(path)
        box = os.path.realpath(self.at(INBOX)) + os.sep
        if full.startswith(box) and os.path.isfile(full):
            os.remove(full)


def resolve_ws(name, must_exist=True):
    """<slug> 既可以是稿名（→ essays/<slug>），也可以直接给一个目录。"""
    seps = [os.sep] + ([os.altsep] if os.altsep else [])
    if any(s and s in name for s in seps):
        return Workspace(os.path.abspath(name), must_exist)
    check_slug(name)
    nested = os.path.join(ESSAYS_DIR, name)
    if os.path.isdir(nested) or not os.path.isdir(name):
        return Workspace(os.path.abspath(nested), must_exist)
    return Workspace(os.path.abspath(name), must_exist)


# ---------------------------------------------------------------- 切块

def _atoms_from_blocks(text, spans, marks=None):
    """把「块的区间」补成覆盖全文、首尾相接的原子表。

    spans: [(start, end, heading)]，按 start 升序、互不重叠。
    marks: {(start, end): role}，import 阶段已知的非块区域（docx 的表格与文本框）。
    """
    marks = marks or {}
    atoms = []
    at = 0
    number = 0

    def gap(start, end):
        while start < end:
            hit = None
            for (ms, me), role in sorted(marks.items()):
                if ms < end and me > start:
                    hit = (max(ms, start), min(me, end), role)
                    break
            if hit is None:
                _plain_gap(start, end)
                return
            if hit[0] > start:
                _plain_gap(start, hit[0])
            atoms.append({"i": len(atoms), "start": hit[0], "end": hit[1], "role": hit[2]})
            start = hit[1]

    def _plain_gap(start, end):
        chunk = text[start:end]
        if not chunk:
            return
        role = "space" if not chunk.strip() else "outside"
        atoms.append({"i": len(atoms), "start": start, "end": end, "role": role})

    for start, end, heading in spans:
        if start > at:
            gap(at, start)
        number += 1
        atoms.append({"i": len(atoms), "start": start, "end": end, "role": "block",
                      "no": number, "heading": bool(heading),
                      "preview": clip(plain_text(text[start:end]))})
        at = end
    if at < len(text):
        gap(at, len(text))
    return atoms


def _trim(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


_CLOSERS = "）)】》」』”’\"'"
_ENDINGS = ("。", "！", "？", "；", "：", ".", "!", "?", ";", ":", "，", ",")


def _looks_like_head(chunk):
    line = chunk.strip().rstrip(_CLOSERS)
    if chunk.strip().startswith("#"):
        return True
    if "\n" in line or len(line) > 40 or not line:
        return False
    return not line.endswith(_ENDINGS)


def split_plain(text):
    """md / txt：空行分段，段前后的空白归空白原子。"""
    spans = []
    at = 0
    bounds = []
    for m in _PARA_SEP.finditer(text):
        bounds.append((at, m.start()))
        at = m.end()
    bounds.append((at, len(text)))
    for start, end in bounds:
        start, end = _trim(text, start, end)
        if end > start:
            spans.append((start, end, _looks_like_head(text[start:end])))
    return _atoms_from_blocks(text, spans)


def split_html(text):
    """html：行内标签接着算同一块，块级标签断块；包裹层与裸文本各成原子。"""
    spans = []
    runs = []
    open_tag = ""
    pending = ""
    pos = 0

    def close():
        if runs:
            start, end = _trim(text, runs[0][0], runs[-1][1])
            if end > start:
                spans.append((start, end, open_tag in HEAD_TAGS or
                              _looks_like_head(plain_text(text[start:end]))))
        del runs[:]

    for m in _TAG.finditer(text):
        if m.start() > pos and text[pos:m.start()].strip():
            if not runs:
                open_tag = pending
            runs.append((pos, m.start()))
        name = (m.group(1) or "").lower()
        if name:
            if name not in INLINE_TAGS:
                close()
            pending = name
        pos = m.end()
    if pos < len(text) and text[pos:].strip():
        if not runs:
            open_tag = pending
        runs.append((pos, len(text)))
    close()
    return _atoms_from_blocks(text, spans)


# ---- docx

def _docx_units(node):
    """按文档顺序产出 ("p", 节点) 与 ("tbl", 节点)；mc:Fallback 整棵跳过，不钻进已产出的节点。

    同一段内容新版画在 mc:Choice 里、旧版在 mc:Fallback 里兜底，两边都读等于复制一份。
    """
    for child in node:
        if child.tag == MC_FALLBACK:
            continue
        if child.tag == WORD_NS + "p":
            yield ("p", child)
        elif child.tag == WORD_NS + "tbl":
            yield ("tbl", child)
        else:
            for item in _docx_units(child):
                yield item


def _docx_runs(node, parts, boxes):
    """一段里的文字：w:t 拼起来，w:br / w:cr 换行，w:tab 制表。

    文本框（w:txbxContent）的字单独收，不混进正文；mc:Fallback 同样绕过。
    """
    for child in node:
        if child.tag == MC_FALLBACK:
            continue
        if child.tag == TXBX:
            box = []
            _docx_box(child, box, boxes)
            line = "\n".join(x for x in box if x.strip())
            if line.strip():
                boxes.append(line)
            continue
        if child.tag == WORD_NS + "t":
            parts.append(child.text or "")
        elif child.tag in (WORD_NS + "br", WORD_NS + "cr"):
            parts.append("\n")
        elif child.tag == WORD_NS + "tab":
            parts.append("\t")
        _docx_runs(child, parts, boxes)
    return parts


def _docx_box(node, out, boxes=None):
    """收一棵子树（表格 / 文本框）里的段落文字；里面再套的文本框也一条不落。"""
    for kind, para in _docx_units(node):
        if kind == "p":
            out.append("".join(_docx_runs(para, [], boxes if boxes is not None else [])).strip())
        else:
            _docx_box(para, out, boxes)
    return out


def _docx_heading(para, text):
    ppr = para.find(WORD_NS + "pPr")
    if ppr is not None:
        style = ppr.find(WORD_NS + "pStyle")
        if style is not None:
            val = (style.get(WORD_NS + "val") or "").lower()
            if val.startswith("heading") or val in ("title", "subtitle"):
                return True
    runs = [r for r in para.findall(WORD_NS + "r") if r.find(WORD_NS + "t") is not None]
    if not runs or len(text) > HEAD_MAX:
        return False
    for run in runs:
        rpr = run.find(WORD_NS + "rPr")
        bold = rpr.find(WORD_NS + "b") if rpr is not None else None
        if bold is None or (bold.get(WORD_NS + "val") in ("0", "false")):
            return False
    return True


def read_docx(path):
    """docx 只用 zipfile + xml.etree 读 word/document.xml。

    正文段落进块；表格与文本框的文字放到正文之后的附录区，不参与分段——它们
    只能出现在「未纳入分段」清单里，用户一眼看得到丢了什么。图片与修订痕迹不支持。
    """
    try:
        with zipfile.ZipFile(path) as pack:
            raw = pack.read(WORD_MAIN)
    except FileNotFoundError:
        raise UsageError("找不到文件：%s" % path)
    except KeyError:
        raise UsageError("这个 .docx 里没有 %s，不像是 Word 文档：%s" % (WORD_MAIN, path))
    except zipfile.BadZipFile:
        raise UsageError("这个文件不是有效的 .docx（打不开压缩包）：%s" % path)
    try:
        root = ET.fromstring(raw.decode("utf-8", "replace"))
    except ET.ParseError as e:
        raise UsageError("这个 .docx 的正文 XML 解析失败：%s（%s）" % (path, e))

    body = []                 # (文本, 是否标题)
    extras = []               # (文本, table / textbox)
    for kind, node in _docx_units(root):
        if kind == "tbl":
            nested = []
            cells = _docx_box(node, [], nested)
            line = "\n".join(x for x in cells if x.strip())
            if line.strip():
                extras.append((line, "table"))
            for box in nested:
                extras.append((box, "textbox"))
            continue
        boxes = []
        line = "".join(_docx_runs(node, [], boxes)).strip()
        if line:
            body.append((line, _docx_heading(node, line)))
        for box in boxes:
            extras.append((box, "textbox"))

    chunks = []
    spans = []
    marks = {}
    at = 0
    for line, heading in body:
        spans.append((at, at + len(line), heading))
        chunks.append(line)
        at += len(line)
        chunks.append("\n\n")
        at += 2
    for line, role in extras:
        marks[(at, at + len(line))] = role
        chunks.append(line)
        at += len(line)
        chunks.append("\n\n")
        at += 2
    text = "".join(chunks)
    return text, _atoms_from_blocks(text, spans, marks)


# ---------------------------------------------------------------- 偏移换算

def byte_atoms(text, atoms):
    """字符下标换成 UTF-8 字节偏移；原子边界都落在字符边界上，切片安全。"""
    prefix = [0] * (len(text) + 1)
    for i, ch in enumerate(text):
        prefix[i + 1] = prefix[i] + len(ch.encode("utf-8"))
    out = []
    for atom in atoms:
        item = dict(atom)
        item["start"] = prefix[atom["start"]]
        item["end"] = prefix[atom["end"]]
        out.append(item)
    return out


# ---------------------------------------------------------------- init / meta

META_FIELDS = ("title", "genre", "level", "setting", "target_words", "background", "thesis")


def apply_meta(data, args):
    for field in META_FIELDS:
        value = getattr(args, field, None)
        if value is None:
            continue
        if field == "target_words":
            if not is_int(value, 0, 10 ** 6):
                raise UsageError("目标字数要是 0 以上的整数，当前是：%r" % value)
            data["targetWords"] = value
        elif field == "setting":
            if value not in SETTINGS:
                raise UsageError("场景只能是 %s，当前是：%r" % (" / ".join(SETTINGS), value))
            data["setting"] = value
        else:
            data[field] = value
    return data


def cmd_init(args):
    check_slug(args.slug)
    ws = resolve_ws(args.slug, must_exist=False)
    if os.path.isdir(ws.dir) and os.path.isfile(ws.essay_path):
        raise UsageError("这个工作区已经有了：%s（改题目背景请用 meta）" % ws.rel(ws.dir))
    for sub in (SECTIONS, LEDGER, INBOX, READINGS, VERSIONS):
        os.makedirs(ws.at(sub), exist_ok=True)
    data = apply_meta({
        "slug": ws.slug, "title": "", "genre": "", "level": "", "setting": "untimed",
        "targetWords": 0, "background": "", "thesis": "", "createdAt": now_iso(),
        "segments": [], "outside": [], "fallback": False, "sourceFile": "",
    }, args)
    ws.save_essay(data)
    for name in (OUTLINE_NAME, REFLECT_NAME):
        if not os.path.isfile(ws.at(name)):
            write_text(ws.at(name), "")
    write_json(ws.chains_path, {})
    print("已建好工作区 %s" % ws.rel(ws.dir))
    print("下一步：贴稿走 import，只有题目就走 outline add。sections/ 由你自己写，Agent 不许动。")
    return 0


def cmd_meta(args):
    ws = resolve_ws(args.slug)
    data = apply_meta(ws.essay(), args)
    ws.save_essay(data)
    print("已更新题目背景：%s" % ws.rel(ws.essay_path))
    print("提示：背景一改，此前跑过的 context 就过期了，评审要重新跑一次 context。")
    return 0


def cmd_doctor(args):
    print("essayctl.py：%s" % os.path.abspath(__file__))
    print("Python：%s" % sys.version.split()[0])
    print("当前目录：%s" % os.getcwd())
    base = os.path.abspath(ESSAYS_DIR)
    if os.path.isdir(base):
        names = sorted(n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n)))
        print("已有工作区（%s/）：%s" % (ESSAYS_DIR, "、".join(names) if names else "还没有"))
    else:
        print("还没有 %s/ 目录，先跑 init <slug>。" % ESSAYS_DIR)
    print("纪律：账本只经脚本写；Agent 只能写 inbox/；sections/ 由用户自己写。")
    return 0


# ---------------------------------------------------------------- import

def cmd_import(args):
    ws = resolve_ws(args.slug)
    data = ws.essay()
    if data.get("segments"):
        raise UsageError("这一篇已经拆过段了。要重来请另起一个 slug，免得盖掉已有账本。")
    path = args.src
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".docx":
        text, atoms = read_docx(path)
    else:
        text = read_text(path)
        atoms = split_html(text) if suffix in (".html", ".htm") else split_plain(text)
    blocks = [a for a in atoms if a["role"] == "block"]
    if not blocks:
        raise UsageError("这份稿子里没读到任何正文段落：%s" % path)

    blocks_text = [{"text": text[a["start"]:a["end"]]} for a in atoms]
    write_text(ws.source_path, text)
    atoms = byte_atoms(text, atoms)
    kinds = {".docx": "docx", ".html": "html", ".htm": "html", ".md": "md", ".txt": "txt"}
    meta = {"file": os.path.basename(path), "format": kinds.get(suffix, "txt"),
            "chars": len(text), "bytes": len(text.encode("utf-8")),
            "atoms": atoms, "blockCount": len(blocks)}
    write_json(ws.blocks_path, meta)
    data["sourceFile"] = SOURCE_NAME
    if not data.get("title"):
        for atom, chunk in zip(atoms, blocks_text):
            if atom["role"] == "block" and atom.get("heading"):
                data["title"] = plain_text(chunk["text"]).lstrip("# ")
                break
    ws.save_essay(data)

    outside = [a for a in atoms if a["role"] in ("outside", "table", "textbox")]
    view = {"slug": ws.slug, "format": meta["format"], "blockCount": len(blocks),
            "outsideBlocks": len(outside),
            "blocks": [{"no": a["no"], "heading": a["heading"], "chars": len(b["text"]),
                        "preview": a["preview"]}
                       for a, b in zip(atoms, blocks_text) if a["role"] == "block"]}
    print(json.dumps(view, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- assemble

def parse_groups(payload, count):
    """读模型回的分组；不合格就返回 None，由 assemble 整段导入。

    每个段号只用一次，越界与重复号丢弃并记下来。
    """
    if not isinstance(payload, dict):
        return None, ["载荷不是一个 JSON 对象"]
    body = payload.get("body")
    if not isinstance(body, list) or not body or not all(isinstance(g, list) for g in body):
        return None, ["缺 body 数组（或 body 里不是一组组段号）"]
    dropped = []
    used = set()

    def take(ids, where):
        picked = []
        for value in ids if isinstance(ids, list) else []:
            if not is_int(value, 1, count):
                dropped.append("%s 的段号 %r 越界或不是整数" % (where, value))
                continue
            if value in used:
                dropped.append("%s 的段号 %d 已经被别处用掉了" % (where, value))
                continue
            used.add(value)
            picked.append(value)
        return sorted(picked)

    groups = []
    if payload.get("intro") is not None:
        groups.append(("intro", take(payload.get("intro"), "intro")))
    for i, ids in enumerate(body):
        groups.append(("body-%02d" % (i + 1), take(ids, "body[%d]" % i)))
    if payload.get("conclusion") is not None:
        groups.append(("conclusion", take(payload.get("conclusion"), "conclusion")))
    groups = [(name, ids) for name, ids in groups if ids]
    if not groups:
        return None, dropped + ["一个有效段号都没有"]
    return groups, dropped


def cmd_assemble(args):
    ws = resolve_ws(args.slug)
    data = ws.essay()
    if data.get("segments"):
        raise UsageError("这一篇已经拆过段了，再拆会盖掉 sections/。要重来请另起一个 slug。")
    if not os.path.isfile(ws.blocks_path):
        raise UsageError("还没 import 过：%s" % ws.rel(ws.blocks_path))
    meta = read_json(ws.blocks_path)
    atoms = meta["atoms"]
    blocks = dict((a["no"], a) for a in atoms if a["role"] == "block")
    payload = read_json(args.src)
    groups, dropped = parse_groups(payload, len(blocks))

    with open(ws.source_path, "rb") as f:
        raw = f.read()
    fallback = groups is None
    if fallback:
        # 整段导入：全文原样归成一段，一个字节也不切
        spans = [["body-01", sorted(blocks), 0, len(raw)]]
    else:
        spans = [[name, ids, min(blocks[i]["start"] for i in ids),
                  max(blocks[i]["end"] for i in ids)] for name, ids in groups]
        spans.sort(key=lambda s: s[2])
    for i in range(1, len(spans)):
        if spans[i][2] < spans[i - 1][3]:
            raise GateError(["ERROR 分组算出来的段落跨度互相重叠：%s 与 %s。"
                             % (spans[i - 1][0], spans[i][0]),
                             "      拆分没有落盘，请让模型重回一次分组。"])

    merged = []
    assigned = set()
    for _, ids, _, _ in spans:
        assigned.update(ids)
    for no in sorted(blocks):
        if no in assigned:
            continue
        atom = blocks[no]
        for span in spans:
            if span[2] <= atom["start"] and atom["end"] <= span[3]:
                merged.append((no, span[0]))
                break
        else:
            if spans and atom["start"] >= spans[-1][3]:
                spans[-1][3] = max(spans[-1][3], atom["end"])
                merged.append((no, spans[-1][0]))

    covered = [(s[2], s[3]) for s in spans]
    outside = []
    for atom in atoms:
        if any(start <= atom["start"] and atom["end"] <= end for start, end in covered):
            continue
        outside.append({"start": atom["start"], "end": atom["end"], "role": atom["role"]})

    # 恒等式：按偏移把全部段文本与全部「未纳入」片段拼回，必须逐字节等于原文
    pieces = sorted([(s[2], s[3]) for s in spans] + [(o["start"], o["end"]) for o in outside])
    at = 0
    rebuilt = b""
    for start, end in pieces:
        if start != at:
            raise GateError(["ERROR 段落与未纳入片段之间出现了空隙：%d → %d。拆分未落盘。" % (at, start)])
        rebuilt += raw[start:end]
        at = end
    if at != len(raw) or rebuilt != raw:
        raise GateError(["ERROR 保真校验没过：按偏移拼回来的字节与原文不一致，拆分未落盘。"])

    names = []
    body_no = 0
    for span in spans:
        name = span[0]
        if name.startswith("body-"):
            body_no += 1
            name = "body-%02d" % body_no
        span[0] = name
        names.append(name)

    subs = outline_items(ws)
    segments = []
    body_no = 0
    for name, ids, start, end in spans:
        text = raw[start:end].decode("utf-8")
        write_text(ws.section_path(name), text)
        if name == "intro":
            sub = ROLE_INTRO
        elif name == "conclusion":
            sub = ROLE_CONCLUSION
        else:
            sub = subs[body_no] if body_no < len(subs) else ""
            body_no += 1
        segments.append({"name": name, "subquestion": sub, "start": start, "end": end,
                         "blocks": ids})
    data["segments"] = segments
    data["outside"] = outside
    data["fallback"] = fallback
    ws.save_essay(data)
    write_text(ws.at(SPLIT_NAME), render_split(ws, raw, meta, segments, outside, merged,
                                               dropped, fallback))
    ws.consume(args.src)

    if fallback:
        print("分组载荷不合格，已整段导入（fallback）：%s" % "；".join(dropped))
    wordy = [o for o in outside if o["role"] != "space"]
    print("已拆出 %d 段：%s" % (len(segments), "、".join(names)))
    print("未纳入分段 %d 条：有字的 %d 条、纯空白分隔 %d 条，逐条写在 %s 里，一个字都没丢。"
          % (len(outside), len(wordy), len(outside) - len(wordy), SPLIT_NAME))
    if merged:
        print("未分配的块已并入相邻段：%s" % "、".join("第%d块→%s" % m for m in merged))
    print("下一步：逐段跑 context，再让模型写评审。sections/ 从现在起只有你能改。")
    return 0


def render_split(ws, raw, meta, segments, outside, merged, dropped, fallback):
    out = ["# 拆分报告 · %s" % ws.slug, "",
           "来源：%s（%s）　块数：%d　段数：%d　未纳入片段：%d 条"
           % (meta["file"], meta["format"], meta["blockCount"], len(segments), len(outside)), ""]
    if fallback:
        out += ["> 分组载荷不合格，已整段导入（fallback）：全文归成一段。", ""]
    out += ["## 分段结果", "", "| 分区 | 块号 | 字节区间 | 字数 |", "| --- | --- | --- | --- |"]
    for seg in segments:
        text = raw[seg["start"]:seg["end"]].decode("utf-8")
        out.append("| %s | %s | [%d, %d) | %d |"
                   % (seg["name"], "、".join(str(i) for i in seg["blocks"]) or "-",
                      seg["start"], seg["end"], len(plain_text(text))))
    out += ["", "## 已并入的未分配块", ""]
    out += (["- 第 %d 块 → %s" % (no, name) for no, name in merged] or ["（没有）"])
    out += ["", "## 丢弃的段号", ""]
    out += (["- %s" % line for line in dropped] or ["（没有）"])
    wordy = [o for o in outside if o["role"] != "space"]
    blank = [o for o in outside if o["role"] == "space"]
    out += ["", "## 未纳入分段", "",
            "下面这些字没有进任何一段。脚本不替你决定它们该去哪，但一条也不会静默丢掉。", ""]
    if not wordy:
        out.append("（没有有字的片段）")
    for frag in wordy:
        text = raw[frag["start"]:frag["end"]].decode("utf-8")
        out += ["- [%d, %d) %s（%d 字）：" % (frag["start"], frag["end"],
                                              ROLE_LABEL.get(frag["role"], frag["role"]),
                                              len(text)),
                "", "  ```", "  " + text.replace("\n", "\n  "), "  ```", ""]
    out += ["", "### 纯空白分隔（%d 条）" % len(blank), "",
            "段与段之间的空行，一个字也不含；列在这里只为让上面的偏移能一路对齐拼回原文。", "",
            "、".join("[%d, %d)" % (f["start"], f["end"]) for f in blank) or "（没有）"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- outline

def outline_items(ws):
    items = []
    for row in ws.rows(OUTLINE_NAME):
        items.extend(row.get("items") or [])
    return items


def rebuild_segments(ws, data, items):
    """从题目入手时，子问题定下来就把分区骨架建出来（内容留给用户自己写）。"""
    old = dict((s["name"], s) for s in data.get("segments") or [])
    segments = [{"name": "intro", "subquestion": ROLE_INTRO}]
    for i, text in enumerate(items):
        segments.append({"name": "body-%02d" % (i + 1), "subquestion": text})
    segments.append({"name": "conclusion", "subquestion": ROLE_CONCLUSION})
    for seg in segments:
        keep = old.get(seg["name"]) or {}
        for field in ("start", "end", "blocks"):
            if field in keep:
                seg[field] = keep[field]
        path = ws.section_path(seg["name"])
        if not os.path.isfile(path):
            write_text(path, "")
    data["segments"] = segments
    return data


def cmd_outline_add(args):
    ws = resolve_ws(args.slug)
    data = ws.essay()
    rounds = len(ws.raw_lines(OUTLINE_NAME))
    if rounds >= OUTLINE_ROUNDS:
        raise GateError(["ERROR 拆题已经跑满 %d 轮了，不再叫模型。" % OUTLINE_ROUNDS,
                         "      再想不出角度就该动笔写，或者自己往 essay.json 的段落里补。"])
    payload = read_json(args.src)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise UsageError("拆题载荷要长这样：{\"items\": [\"子问题一\", \"子问题二\", …]}")
    items = payload["items"]
    for value in items:
        if not isinstance(value, str) or not value.strip():
            raise GateError(["ERROR 有一条子问题是空的（%r），整轮拒收。" % (value,)])

    have = outline_items(ws)
    seen = set(x.strip().lower() for x in have)
    fresh = []
    skipped = []
    for value in items:
        key = value.strip().lower()
        if key in seen:
            skipped.append(value.strip())
            continue
        seen.add(key)
        fresh.append(value.strip())
    if not fresh:
        raise GateError(["ERROR 这一轮的子问题跟已有的完全重复，没有新东西：",
                         "      %s" % "、".join(skipped)])

    written = [s for s in data.get("segments") or []
               if s["name"].startswith("body-") and plain_text(
                   read_text(ws.section_path(s["name"])) if os.path.isfile(
                       ws.section_path(s["name"])) else "")]
    if rounds == 0 and not written:
        mode = "initial"
        low, high = OUTLINE_INITIAL
        if not low <= len(fresh) <= high:
            raise GateError(["ERROR 初始拆题要 %d–%d 条，这一轮只有 %d 条，拒收。"
                             % (low, high, len(fresh))])
    elif rounds == 0:
        mode = "bind"
        if len(fresh) != len(written):
            raise GateError(["ERROR 这一篇已经拆好 %d 个正文段，绑定子问题就要正好 %d 条，"
                             "这一轮给了 %d 条。" % (len(written), len(written), len(fresh))])
    else:
        mode = "extra"
        if len(fresh) > OUTLINE_EXTRA:
            raise GateError(["ERROR 增补一轮最多 %d 条，这一轮给了 %d 条，拒收。"
                             % (OUTLINE_EXTRA, len(fresh))])

    ws.append_row(OUTLINE_NAME, {"stage": "outline", "mode": mode, "items": fresh,
                                 "dropped": skipped})
    ws.save_essay(rebuild_segments(ws, data, outline_items(ws)))
    ws.consume(args.src)
    print("第 %d 轮拆题（%s）收下 %d 条：" % (rounds + 1, mode, len(fresh)))
    for i, text in enumerate(fresh):
        print("  %d. %s" % (i + 1, text))
    if skipped:
        print("WARN 跟已有重复、已去掉：%s" % "、".join(skipped))
    print("还剩 %d 轮。分区骨架已建好，正文由你自己写。"
          % (OUTLINE_ROUNDS - rounds - 1))
    return 0


# ---------------------------------------------------------------- context

def reflection_pack(ws, segment):
    """≤3 条：同段 > 总反思 > 其他段，组内新→旧。"""
    rows = ws.reflections()
    mine, essay, others = [], [], []
    for row in rows:
        item = {"scope": row.get("scope"), "when": row.get("when"),
                "atScore": row.get("atScore"), "text": row.get("text")}
        if row.get("scope") == "essay":
            essay.append(item)
        elif row.get("segment") == segment:
            mine.append(item)
        else:
            others.append(item)
    ordered = list(reversed(mine)) + list(reversed(essay)) + list(reversed(others))
    return ordered[:3]


def background_of(data):
    return {"genre": data.get("genre", ""), "level": data.get("level", ""),
            "setting": data.get("setting", ""), "targetWords": data.get("targetWords", 0),
            "text": data.get("background", "")}


def build_context(ws, segment):
    data = ws.essay()
    entry = ws.segment_entry(segment)
    text = plain_text(ws.section_raw(segment))
    if len(text) < MIN_PLAIN:
        raise GateError(["ERROR %s 的纯文本只有 %d 字，不到 %d 字，不给评。"
                         % (segment, len(text), MIN_PLAIN),
                         "      先把这一段写出来——脚本不代写，模型也不许代写。"])
    pack = reflection_pack(ws, segment)
    material = {"segmentText": text, "subquestion": entry.get("subquestion", ""),
                "thesis": data.get("thesis", ""), "background": background_of(data),
                "reflectionPack": pack}
    last = ws.latest_review(segment)
    previous = None
    if last:
        previous = {"scores": last.get("scores"),
                    "segmentChanged": last.get("segmentHash") != sha256_text(text)}
    out = {"segment": segment, "text": text, "subquestion": material["subquestion"],
           "thesis": material["thesis"], "background": material["background"],
           "reflections": pack, "previousReview": previous,
           "contextHash": sha256_text(canonical(material))}
    return out, material


def cmd_context(args):
    ws = resolve_ws(args.slug)
    check_segment(args.segment)
    out, _ = build_context(ws, args.segment)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- review add

def check_scores(payload):
    scores = payload.get("scores")
    if not isinstance(scores, dict):
        return ["ERROR scores 必须是一个对象，三个维度各一个 1–5 的整数。"]
    bad = []
    extra = sorted(set(scores) - set(DIMS))
    if extra:
        bad.append("ERROR scores 里多了不认识的维度：%s（只收 %s）"
                   % ("、".join(extra), " / ".join(DIMS)))
    for dim in DIMS:
        if dim not in scores:
            bad.append("ERROR scores 缺维度 %s。" % dim)
        elif not is_int(scores[dim], 1, 5):
            bad.append("ERROR %s 必须是 1–5 的整数，实际是 %r（布尔、小数、字符串、"
                       "负号、越界都不算）。" % (dim, scores[dim]))
    return bad


def check_quotes(payload, text):
    quotes = payload.get("quotes")
    if not isinstance(quotes, list) or not quotes:
        return ["ERROR quotes 至少要有 1 条逐字引用，用来证明确实读了这一段的原文。"]
    body = squeeze(text)
    bad = []
    seen = set()
    total = 0
    for quote in quotes:
        if not isinstance(quote, str) or not quote.strip():
            bad.append("ERROR 有一条引用是空的。")
            continue
        tight = squeeze(quote)
        if tight not in body:
            bad.append("ERROR 这条引用不是这一段的原文（空白归一之后仍然对不上）：「%s」"
                       % clip(quote, 60))
            continue
        if tight in seen:
            bad.append("ERROR 这条引用跟前面某一条重了：「%s」" % clip(quote, 60))
            continue
        seen.add(tight)
        total += len(tight)
        if body and len(tight) > len(body) * QUOTE_RATIO:
            bad.append("ERROR 这条引用占了该段 %.0f%%，超过 %.0f%% 上限：「%s」"
                       % (100.0 * len(tight) / len(body), 100 * QUOTE_RATIO, clip(quote, 60)))
    if body and total > len(body) * QUOTE_RATIO:
        bad.append("ERROR 引用合计占了该段 %.0f%%，超过 %.0f%% 上限——评审不是复读原文。"
                   % (100.0 * total / len(body), 100 * QUOTE_RATIO))
    return bad


def hollow_flags(ws, segment, payload, text):
    """空心闸：同评语 ERROR，零引用与雷同 WARN。只跟别的分区比，同段多稿不算。"""
    note = payload.get("note") or ""
    quotes = payload.get("quotes") or []
    bad, flags = [], []
    for other in ws.segment_names():
        if other == segment:
            continue
        for row in ws.reviews(other):
            if (row.get("note") or "").strip() == note.strip():
                bad.append("ERROR %s 已经用过一模一样的评语了。八段贴同一份评审等于没读，"
                           "整份拒收。" % other)
                return bad, flags
    if not trigrams(note) & trigrams(text) and len(quotes) == 1 and \
            len(squeeze(quotes[0])) <= SHORT_QUOTE:
        flags.append("thin-quote")
    words = token_set(note)
    for other in ws.segment_names():
        if other == segment:
            continue
        for row in ws.reviews(other):
            if row.get("scores") == payload.get("scores") and \
                    jaccard(words, token_set(row.get("note") or "")) >= LOOK_ALIKE:
                flags.append("look-alike:%s" % other)
                break
        if any(f.startswith("look-alike") for f in flags):
            break
    return bad, flags


FLAG_TEXT = {"thin-quote": "WARN 未引用原文：评语跟这一段没有一处三字重合，引用也只有一小截。",
             "look-alike": "WARN 评审雷同：三维分与另一段完全相同，评语也高度重合（%s）。"}


def cmd_review_add(args):
    ws = resolve_ws(args.slug)
    check_segment(args.segment)
    payload = read_json(args.src)
    if not isinstance(payload, dict):
        raise UsageError("评审载荷必须是一个 JSON 对象")
    for key in HANDOFF_KEYS:
        if key in payload:
            raise GateError(["ERROR 载荷里出现了 %s 字段。这个 Skill 只判分与举证，不改句子。" % key,
                             "      要改句子，把这一段丢给 red-pen。"])
    extra = sorted(set(payload) - set(REVIEW_KEYS))
    if extra:
        raise GateError(["ERROR 载荷里多了不认识的键：%s（只收 %s）"
                         % ("、".join(extra), "、".join(REVIEW_KEYS)),
                         "      综合分与触发分都由脚本从三维分算，手填一律不认。"])

    out, material = build_context(ws, args.segment)
    if not isinstance(payload.get("contextHash"), str) or not payload["contextHash"]:
        raise GateError(["ERROR 载荷里没有 contextHash：没跑 context 就不许写评审。",
                         "      先跑 context %s %s，照它给的包写。" % (ws.slug, args.segment)])
    if payload["contextHash"] != out["contextHash"]:
        raise GateError(["ERROR contextHash 对不上：这份评审依据的上下文已经过期了。",
                         "      载荷里的 %s" % clip(payload["contextHash"], 16),
                         "      现在应是 %s" % clip(out["contextHash"], 16),
                         "      原文、背景、场景、目标字数或反思包里有一样变了，重跑一次 context。"])

    problems = check_scores(payload)
    note = payload.get("note")
    if not isinstance(note, str) or not note.strip():
        problems.append("ERROR note 要写一段评语，不能空着。")
    problems += check_quotes(payload, out["text"])
    if problems:
        raise GateError(problems)
    bad, flags = hollow_flags(ws, args.segment, payload, out["text"])
    if bad:
        raise GateError(bad)

    rows = ws.reviews(args.segment)
    segment_hash = sha256_text(out["text"])
    same_draft = bool(rows) and rows[-1].get("segmentHash") == segment_hash
    scores = payload["scores"]
    row = dict(material)
    row.update({"stage": "review", "segment": args.segment,
                "versionNumber": ws.latest_version(),
                "segmentHash": segment_hash, "contextHash": out["contextHash"],
                "scores": dict((d, scores[d]) for d in DIMS),
                "composite": round_half_up(sum(scores[d] for d in DIMS) / 3.0),
                "note": note.strip(), "quotes": [q for q in payload["quotes"]],
                "sameDraft": same_draft, "flags": flags})
    written = ws.append_row(ws.ledger_rel(args.segment), row)
    ws.consume(args.src)

    print("已入账 %s 第 %d 条评审：%s，综合 %d 分。"
          % (args.segment, written["seq"],
             " / ".join("%s %d" % (d, scores[d]) for d in DIMS), row["composite"]))
    if same_draft:
        print("%s：原文一个字没动，这一条不进走势。" % MARK_SAME)
    for flag in flags:
        head = flag.split(":")[0]
        print(FLAG_TEXT[head] % flag.split(":", 1)[1] if ":" in flag else FLAG_TEXT[head])
    if row["composite"] <= 2 or row["composite"] == 5:
        print("这一段评到了 %d 分，可以写一条反思钉在这一稿上：reflect add %s --segment %s"
              % (row["composite"], ws.slug, args.segment))
    return 0


# ---------------------------------------------------------------- reflect add

def cmd_reflect_add(args):
    ws = resolve_ws(args.slug)
    payload = read_json(args.src)
    if not isinstance(payload, dict):
        raise UsageError("反思载荷必须是一个 JSON 对象")
    extra = sorted(set(payload) - set(REFLECT_KEYS))
    if extra:
        raise GateError(["ERROR 载荷里多了不认识的键：%s（只收 %s）"
                         % ("、".join(extra), "、".join(REFLECT_KEYS)),
                         "      触发分由脚本从账本取，手填不认。"])
    text = plain_text(payload.get("text") or "")
    if not text:
        raise GateError(["ERROR 反思是空的。"])
    if len(text) > REFLECT_MAX:
        raise GateError(["ERROR 反思剥掉标签之后有 %d 字，超过 %d 字上限。"
                         % (len(text), REFLECT_MAX)])

    row = {"stage": "reflect", "text": text, "versionNumber": ws.latest_version()}
    if args.segment:
        check_segment(args.segment)
        ws.segment_entry(args.segment)
        last = ws.latest_review(args.segment)
        if last is None:
            raise GateError(["ERROR %s 还没有评审记录，区域反思无从钉起。" % args.segment,
                             "      现在可以写总反思：去掉 --segment 再跑一次。"])
        score = last.get("composite")
        if not (score <= 2 or score == 5):
            raise GateError(["ERROR %s 最新一条评审综合 %d 分，不在触发区间（≤2 或 =5）。"
                             % (args.segment, score),
                             "      想写就写总反思：去掉 --segment 再跑一次。"])
        snapshot = plain_text(ws.section_raw(args.segment))
        row.update({"scope": "segment", "segment": args.segment, "atScore": score,
                    "atSeq": last.get("seq"), "segmentHash": sha256_text(snapshot),
                    "noDiff": len(snapshot) >= NO_DIFF_AT})
        if len(snapshot) < NO_DIFF_AT:
            row["snapshot"] = snapshot
    else:
        row.update({"scope": "essay", "segment": None, "atScore": None, "atSeq": None,
                    "noDiff": True})

    written = ws.append_row(REFLECT_NAME, row)
    ws.consume(args.src)
    where = args.segment if args.segment else "整篇"
    print("已记下第 %d 条反思（%s）%s。"
          % (written["seq"], where,
             "，当时这一段是 %d 分" % row["atScore"] if row.get("atScore") else ""))
    return 0


# ---------------------------------------------------------------- reading add

def cmd_reading_add(args):
    ws = resolve_ws(args.slug)
    check_segment(args.segment)
    ws.segment_entry(args.segment)
    payload = read_json(args.src)
    if not isinstance(payload, dict):
        raise UsageError("荐读载荷必须是一个 JSON 对象")
    extra = sorted(set(payload) - set(READING_KEYS))
    if extra:
        raise GateError(["ERROR 载荷里多了不认识的键：%s（只收 %s）"
                         % ("、".join(extra), "、".join(READING_KEYS))])
    bad = []
    for field in READING_MUST:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()) or value == "":
            bad.append("ERROR 荐读缺 %s，或者填的是空的。" % field)
    if bad:
        raise GateError(bad)
    title = str(payload["title"]).strip()
    base = os.path.join(ws.at(READINGS))
    os.makedirs(base, exist_ok=True)
    same = []
    for name in sorted(os.listdir(base)):
        if not name.endswith(".json"):
            continue
        card = read_json(os.path.join(base, name))
        if card.get("segment") == args.segment:
            same.append(card)
            if (card.get("title") or "").strip().lower() == title.lower():
                raise GateError(["ERROR %s 已经推过同名材料了：「%s」"
                                 % (args.segment, card.get("title")),
                                 "      别再推同一个，换一个角度或换一段。"])
    card = {"segment": args.segment, "title": title,
            "authors": payload["authors"], "year": payload["year"],
            "summary": payload.get("summary", ""), "url": payload.get("url", ""),
            "verified": bool(payload.get("verified", False)), "addedAt": now_iso()}
    path = os.path.join(base, "%s-%02d.json" % (args.segment, len(same) + 1))
    write_json(path, card)
    ws.consume(args.src)
    print("已记下 %s 的一份荐读：%s（%s，%s）" % (args.segment, title, card["authors"], card["year"]))
    if not card["verified"]:
        print("%s：脚本不联网，也不替你核实出处。请自行检索确认之后再引用。" % MARK_UNSURE)
    return 0


# ---------------------------------------------------------------- version

def cmd_version(args):
    ws = resolve_ws(args.slug)
    names = ws.segment_names()
    if not names:
        raise UsageError("还没有任何分区，没什么可以拍快照的。")
    number = ws.latest_version() + 1
    target = ws.at(VERSIONS, "v%d" % number)
    os.makedirs(target, exist_ok=True)
    files = {}
    for name in names:
        src = ws.section_path(name)
        if not os.path.isfile(src):
            raise UsageError("缺分区文件：%s" % ws.rel(src))
        shutil.copyfile(src, os.path.join(target, "%s.md" % name))
        files["%s.md" % name] = sha256_text(read_text(src))
    write_json(os.path.join(target, "manifest.json"),
               {"version": number, "createdAt": now_iso(), "files": files})
    print("已拍下版本 v%d，共 %d 个文件。" % (number, len(files)))
    return 0


# ---------------------------------------------------------------- status / report

def trend_of(rows):
    """走势只按 segmentHash 变化计数；同稿重评画空心点，不加长度。"""
    dots = []
    for row in rows:
        if dots and dots[-1]["hash"] == row.get("segmentHash"):
            dots[-1]["repeat"] += 1
            dots[-1]["composite"] = row.get("composite")
            continue
        dots.append({"hash": row.get("segmentHash"), "composite": row.get("composite"),
                     "repeat": 0})
    return dots


def segment_view(ws):
    """每段一份视图数据：status 的分段块与 report 的分段卡共用。"""
    view = []
    for seg in ws.essay().get("segments") or []:
        name = seg["name"]
        path = ws.section_path(name)
        raw = read_text(path) if os.path.isfile(path) else ""
        text = plain_text(raw)
        digest = sha256_text(text)
        rows = ws.reviews(name)
        last = rows[-1] if rows else None
        view.append({
            "name": name, "subquestion": seg.get("subquestion", ""), "chars": len(text),
            "hash": digest, "mtime": mtime_of(path), "reviews": rows, "last": last,
            "changed": bool(last) and last.get("segmentHash") != digest,
            "trend": trend_of(rows),
            "reflections": [r for r in ws.reflections()
                            if r.get("scope") == "segment" and r.get("segment") == name],
        })
    return view


def readings_of(ws):
    base = ws.at(READINGS)
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        if name.endswith(".json"):
            out.append(read_json(os.path.join(base, name)))
    return out


def cmd_status(args):
    ws = resolve_ws(args.slug)
    data = ws.essay()
    view = segment_view(ws)
    print("# %s · %s" % (ws.slug, data.get("title") or "（还没填题目）"))
    print("文体 %s　级别 %s　场景 %s　目标字数 %s　版本 %d 个"
          % (data.get("genre") or "-", data.get("level") or "-", data.get("setting") or "-",
             data.get("targetWords") or "-", ws.version_count()))
    print("主论点：%s" % (data.get("thesis") or "（还没填）"))
    outside = data.get("outside") or []
    wordy = [o for o in outside if o.get("role") != "space"]
    print("拆题 %d 轮（还剩 %d 轮）　反思 %d 条　荐读 %d 份　未纳入分段 %d 条（有字的 %d 条）"
          % (len(ws.raw_lines(OUTLINE_NAME)),
             max(0, OUTLINE_ROUNDS - len(ws.raw_lines(OUTLINE_NAME))),
             len(ws.reflections()), len(readings_of(ws)), len(outside), len(wordy)))
    print("")
    for item in view:
        head = "%-10s %5d 字  %s  改于 %s" % (item["name"], item["chars"],
                                              item["hash"][:8], item["mtime"])
        print(head)
        if item["subquestion"]:
            print("    子问题：%s" % clip(item["subquestion"], 60))
        if item["last"]:
            last = item["last"]
            print("    最新评审：%s，综合 %d 分%s"
                  % (" / ".join("%s %d" % (d, last["scores"][d]) for d in DIMS),
                     last["composite"], "（%s）" % MARK_SAME if last.get("sameDraft") else ""))
            print("    走势 %d 点（评审 %d 条，其中同稿重评 %d 条）"
                  % (len(item["trend"]), len(item["reviews"]),
                     sum(1 for r in item["reviews"] if r.get("sameDraft"))))
            if item["changed"]:
                print("    ** %s：这一段在最近一次评审之后动过，上面的分数已经过期。" % MARK_CHANGED)
        else:
            print("    还没评过。先跑 context %s %s。" % (ws.slug, item["name"]))
        for note in item["reflections"][-1:]:
            print("    反思（当时 %s 分）：%s" % (note.get("atScore"), clip(note.get("text"), 50)))
    cards = readings_of(ws)
    if cards:
        print("")
        for card in cards:
            print("荐读 %s：%s（%s，%s）%s"
                  % (card["segment"], card["title"], card["authors"], card["year"],
                     "" if card.get("verified") else "　【%s】" % MARK_UNSURE))
    box = [n for n in os.listdir(ws.at(INBOX))] if os.path.isdir(ws.at(INBOX)) else []
    if box:
        print("")
        print("inbox/ 里还剩 %d 份没消费的载荷：%s" % (len(box), "、".join(sorted(box))))
    print("")
    print("哈希与 mtime 逐段列在上面：sections/ 只该由你自己动，Agent 写了你一眼能看出来。")
    return 0


_HTML_CSS = """
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#ffffff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--fg:#e6edf3;--muted:#8b949e;--line:#30363d}}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:0}
.meta{color:var(--muted);font-size:13px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.box{display:inline-block;min-width:52px;text-align:center;border:1px solid var(--line);
border-radius:8px;padding:4px 8px;margin-left:6px}
.box b{display:block;font-size:17px}.box span{color:var(--muted);font-size:10px}
.sub{color:var(--muted);font-size:13px;margin:6px 0}
.quote{border-left:3px solid var(--line);padding:2px 10px;margin:8px 0;color:var(--muted);font-size:13px}
.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:1px 8px;
font-size:11px;color:var(--muted);margin-left:6px}
.stale{opacity:.55}
.dots{font-size:13px;color:var(--muted);margin-top:8px;letter-spacing:2px}
.foot{margin:24px 0 0;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
"""


def cmd_report(args):
    ws = resolve_ws(args.slug)
    data = ws.essay()
    view = segment_view(ws)
    esc = html.escape
    cards = []
    for item in view:
        last = item["last"]
        badges = []
        if item["changed"]:
            badges.append(MARK_CHANGED)
        if last and last.get("sameDraft"):
            badges.append(MARK_SAME)
        for flag in (last or {}).get("flags") or []:
            badges.append("评审雷同" if flag.startswith("look-alike") else "未引用原文")
        boxes = ""
        if last:
            boxes = "".join('<span class="box"><b>%d</b><span>%s</span></span>'
                            % (last["scores"][d], esc(d)) for d in DIMS)
            boxes += ('<span class="box"><b>%d</b><span>综合</span></span>' % last["composite"])
        dots = "".join("○" if dot["repeat"] else "●"
                       for dot in item["trend"][-TREND_DOTS:])
        quotes = "".join('<div class="quote">%s</div>' % esc(q)
                         for q in (last or {}).get("quotes") or [])
        notes = "".join('<div class="sub">反思（当时 %s 分）：%s</div>'
                        % (esc(str(r.get("atScore"))), esc(r.get("text") or ""))
                        for r in item["reflections"][-2:])
        body = ('<div class="sub">%s</div>' % esc(last["note"])) if last else \
               '<div class="sub">还没评过这一段。</div>'
        cards.append(
            '<div class="card%s"><div class="top"><div><h2>%s%s</h2>'
            '<div class="sub">%d 字 · %s · 改于 %s</div></div><div>%s</div></div>'
            '%s%s<div class="dots">走势 %s（%d 点，同稿重评画空心）</div>%s</div>'
            % (" stale" if item["changed"] else "", esc(item["name"]),
               "".join('<span class="badge">%s</span>' % esc(b) for b in badges),
               item["chars"], esc(clip(item["subquestion"], 50) or "—"), esc(item["mtime"]),
               boxes, body, quotes, dots or "—", len(item["trend"]), notes))

    lines = []
    for card in readings_of(ws):
        lines.append('<div class="sub">%s · %s（%s，%s）%s</div>'
                     % (esc(card["segment"]), esc(card["title"]), esc(str(card["authors"])),
                        esc(str(card["year"])),
                        "" if card.get("verified") else
                        '<span class="badge">%s</span>' % MARK_UNSURE))
    page = ('<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>分段卡 · %s</title><style>%s</style></head><body><div class="wrap">'
            '<h1>%s</h1><div class="meta">%s · %d 段 · 未纳入分段 %d 条（有字的 %d 条）'
            ' · 生成于 %s</div>'
            '%s%s<p class="foot">三个格子只说这一段答没答自己的问题，不核对文献重合，也不是改稿。'
            '引用都是从你自己的原文里逐字取的。要改句子，把那一段丢给 red-pen。</p>'
            '</div></body></html>\n'
            % (esc(ws.slug), _HTML_CSS, esc(data.get("title") or ws.slug),
               esc(ws.slug), len(view), len(data.get("outside") or []),
               len([o for o in data.get("outside") or [] if o.get("role") != "space"]),
               esc(now_iso()),
               "".join(cards),
               ('<div class="card"><h2>荐读</h2>%s</div>' % "".join(lines)) if lines else ""))
    write_text(ws.at(PAGE_NAME), page)
    print("已生成 %s（%d 张分段卡）。" % (ws.rel(ws.at(PAGE_NAME)), len(view)))
    return 0


# ---------------------------------------------------------------- export

def cmd_export(args):
    ws = resolve_ws(args.slug)
    view = segment_view(ws)
    if args.evidence:
        rows = []
        for item in view:
            for row in item["reviews"]:
                rows.append({"seq": row.get("seq"), "when": row.get("when"),
                             "stage": row.get("stage"), "segment": row.get("segment"),
                             "segmentHash": row.get("segmentHash"),
                             "contextHash": row.get("contextHash"),
                             "scores": row.get("scores"), "sameDraft": row.get("sameDraft"),
                             "segmentChanged": row.get("segmentHash") != item["hash"]})
        versions = []
        for name in ws.version_dirs():
            manifest = read_json(ws.at(VERSIONS, name, "manifest.json"))
            versions.append({"version": manifest.get("version"), "files": manifest.get("files")})
        print(json.dumps({"slug": ws.slug, "rows": rows, "versions": versions},
                         ensure_ascii=False, indent=2))
        return 0

    data = ws.essay()
    out = ["# %s" % (data.get("title") or ws.slug), ""]
    for item in view:
        out += [ws.section_raw(item["name"]).strip(), ""]
    out += ["---", "", "## 侧注：各段最新评审", ""]
    for item in view:
        last = item["last"]
        if not last:
            out.append("- %s：还没评过。" % item["name"])
            continue
        out.append("- %s：%s，综合 %d 分%s"
                   % (item["name"],
                      " / ".join("%s %d" % (d, last["scores"][d]) for d in DIMS),
                      last["composite"], "　【%s】" % MARK_CHANGED if item["changed"] else ""))
        out.append("  - 评语：%s" % last["note"])
        for quote in last.get("quotes") or []:
            out.append("  - 引自原文：%s" % quote)
    print("\n".join(out))
    return 0


# ---------------------------------------------------------------- check

def check_chain(ws, rel, bad, stale_bad, gone_bad):
    """复核一条链，三类问题分开报。

    - `bad`：链自身的毛病（行被改、断链、seq 跳号），只能人去查。
    - `stale_bad`：索引**落后**——索引停在某一行、账本比它长，或者索引整条缺失。
      `append_row` 是先追加行、再写索引，所以写盘被打断只可能落到这一格；链自身自洽时
      `check --rebuild-index` 能修。
    - `gone_bad`：索引**超前**（记着第 N 行、账本里根本没有那一行），或者账本空了索引
      还记着行。这两种打断做不出来，只可能是行没了。**不许重建**，也不给重建的提示——
      重建等于把丢掉的评审洗白。
    """
    lines = ws.raw_lines(rel)
    tips = ws.chains().get(rel)
    prev = GENESIS
    for i, line in enumerate(lines):
        try:
            row = json.loads(line)
        except ValueError as e:
            bad.append("ERROR %s 第 %d 行不是合法 JSON：%s" % (rel, i + 1, e))
            return []
        if row.get("seq") != i + 1:
            bad.append("ERROR %s 第 %d 行的 seq 是 %r，跟行号对不上（有人删行或插行）。"
                       % (rel, i + 1, row.get("seq")))
        if row.get("prevHash") != prev:
            bad.append("ERROR %s 第 %d 行断链：prevHash 不等于上一行的 sha256。" % (rel, i + 1))
        if canonical(row) != line:
            bad.append("ERROR %s 第 %d 行被改写过（字节跟脚本写出来的规范格式对不上）。"
                       % (rel, i + 1))
        prev = sha256_text(line)
    if lines:
        if not tips:
            stale_bad.append("ERROR %s 在 %s 里没有链尾索引。" % (rel, CHAINS_NAME))
        else:
            seq = tips.get("seq")
            # 索引指着的那一行必须真的在账本里、且逐字节对得上；否则就是行没了或末行被改
            anchored = (is_int(seq, 1, len(lines))
                        and tips.get("hash") == sha256_text(lines[seq - 1]))
            if not anchored:
                gone_bad.append("ERROR %s 的链尾索引记着第 %r 行，账本里没有对得上的那一行"
                                "（现在共 %d 行）：有行被删掉了，或者末行被改过。"
                                % (rel, seq, len(lines)))
            elif seq < len(lines):
                stale_bad.append("ERROR %s 的链尾索引停在第 %d 行，账本已经有 %d 行。"
                                 % (rel, seq, len(lines)))
    elif tips:
        gone_bad.append("ERROR %s 一行都没有了，但 %s 里还记着 %r 行：整条账本被删空了。"
                        % (rel, CHAINS_NAME, tips.get("seq")))
    return [json.loads(ln) for ln in lines]


def cmd_check(args):
    ws = resolve_ws(args.slug)
    data = ws.essay()
    bad, warn = [], []

    names = [s.get("name") for s in data.get("segments") or []]
    for name in names:
        if not SEGMENT_RE.match(name or ""):
            bad.append("ERROR essay.json 里有非法分区名：%r" % name)
        elif not os.path.isfile(ws.section_path(name)):
            bad.append("ERROR essay.json 记着 %s，但 sections/ 里没有这个文件。" % name)
    base = ws.at(SECTIONS)
    if os.path.isdir(base):
        for entry in sorted(os.listdir(base)):
            if entry.endswith(".md") and entry[:-3] not in names:
                bad.append("ERROR sections/%s 不在 essay.json 的分区表里。" % entry)

    if os.path.isfile(ws.source_path) and data.get("segments"):
        with open(ws.source_path, "rb") as f:
            raw = f.read()
        pieces = sorted([(s["start"], s["end"]) for s in data["segments"] if "start" in s] +
                        [(o["start"], o["end"]) for o in data.get("outside") or []])
        at = 0
        rebuilt = b""
        for start, end in pieces:
            if start != at:
                bad.append("ERROR 分段偏移之间有空隙：%d → %d，原文有一段没人认领。" % (at, start))
                break
            rebuilt += raw[start:end]
            at = end
        else:
            if at != len(raw) or rebuilt != raw:
                bad.append("ERROR 保真校验没过：按偏移拼回来的字节与 source.txt 不一致。")

    chain_bad, stale_bad, gone_bad = [], [], []
    check_chain(ws, OUTLINE_NAME, chain_bad, stale_bad, gone_bad)
    reflections = check_chain(ws, REFLECT_NAME, chain_bad, stale_bad, gone_bad)
    current = {}
    for name in names:
        path = ws.section_path(name)
        current[name] = sha256_text(plain_text(read_text(path))) if os.path.isfile(path) else ""

    seen_notes = {}
    for name in names:
        rel = ws.ledger_rel(name)
        for row in check_chain(ws, rel, chain_bad, stale_bad, gone_bad):
            if row.get("stage") != "review":
                continue
            seq = row.get("seq")
            material = dict((k, row.get(k)) for k in
                            ("segmentText", "subquestion", "thesis", "background",
                             "reflectionPack"))
            if sha256_text(canonical(material)) != row.get("contextHash"):
                bad.append("ERROR %s 第 %s 条的 contextHash 跟它自带的材料对不上。" % (name, seq))
            if sha256_text(row.get("segmentText") or "") != row.get("segmentHash"):
                bad.append("ERROR %s 第 %s 条的 segmentHash 跟它自带的段落全文对不上。" % (name, seq))
            scores = row.get("scores") or {}
            if sorted(scores) != sorted(DIMS) or not all(is_int(scores.get(d), 1, 5) for d in DIMS):
                bad.append("ERROR %s 第 %s 条的三维分不合法：%r" % (name, seq, scores))
            elif row.get("composite") != round_half_up(sum(scores[d] for d in DIMS) / 3.0):
                bad.append("ERROR %s 第 %s 条的综合分不是三维均值四舍五入。" % (name, seq))
            for problem in check_quotes(row, row.get("segmentText") or ""):
                bad.append("%s（%s 第 %s 条）" % (problem, name, seq))
            note = (row.get("note") or "").strip()
            if note in seen_notes and seen_notes[note] != name:
                bad.append("ERROR %s 第 %s 条的评语跟 %s 的一模一样。" % (name, seq, seen_notes[note]))
            seen_notes.setdefault(note, name)
            for flag in row.get("flags") or []:
                warn.append("WARN %s 第 %s 条标着 %s。" % (name, seq, flag))
        rows = ws.reviews(name)
        if rows and rows[-1].get("segmentHash") != current.get(name):
            warn.append("WARN %s：%s，最新一条评审的分数已经过期。" % (name, MARK_CHANGED))

    for row in reflections:
        if row.get("scope") != "segment":
            continue
        name = row.get("segment")
        target = None
        for item in ws.reviews(name or ""):
            if item.get("seq") == row.get("atSeq"):
                target = item
        if target is None:
            bad.append("ERROR 第 %s 条反思钉在 %s 第 %s 条评审上，但那一条不在账本里。"
                       % (row.get("seq"), name, row.get("atSeq")))
        elif target.get("composite") != row.get("atScore"):
            bad.append("ERROR 第 %s 条反思记的触发分 %r 跟对应评审的综合分 %r 对不上。"
                       % (row.get("seq"), row.get("atScore"), target.get("composite")))

    for card in readings_of(ws):
        for field in READING_MUST + ("verified",):
            if card.get(field) is None or card.get(field) == "":
                bad.append("ERROR 荐读「%s」缺 %s。" % (card.get("title"), field))
        if not card.get("verified"):
            warn.append("WARN 荐读「%s」仍标着「%s」，别当成核实过的出处引。"
                        % (card.get("title"), MARK_UNSURE))

    for name in ws.version_dirs():
        path = ws.at(VERSIONS, name, "manifest.json")
        if not os.path.isfile(path):
            bad.append("ERROR %s 没有 manifest.json。" % name)
            continue
        manifest = read_json(path)
        for entry, digest in (manifest.get("files") or {}).items():
            full = ws.at(VERSIONS, name, entry)
            if not os.path.isfile(full):
                bad.append("ERROR %s/%s 不见了，manifest 里还记着。" % (name, entry))
            elif sha256_text(read_text(full)) != digest:
                bad.append("ERROR %s/%s 的哈希跟 manifest 对不上（快照被改过）。" % (name, entry))

    box = ws.at(INBOX)
    if os.path.isdir(box):
        left = sorted(os.listdir(box))
        if left:
            bad.append("ERROR inbox/ 里还剩 %d 份载荷没被脚本消费：%s"
                       % (len(left), "、".join(left)))

    # 链尾索引对不上账本。只有「索引落后」这一格能重建：append_row 先落行、后写索引，
    # 打断只做得出这一种。索引超前、账本被删空都是行没了，重建等于把丢掉的评审洗白。
    hints = []
    if stale_bad or gone_bad:
        want = getattr(args, "rebuild_index", False)
        if want and stale_bad and not gone_bad and not chain_bad:
            tips = ws.rebuild_chains()
            hints.append("已按各条链的实际内容重建 %s（%d 条链）。" % (CHAINS_NAME, len(tips)))
            hints.append("注意：重建信的是账本文件本身，它只修「索引落后」，"
                         "不能替你证明没人往账本里加过行。")
            stale_bad = []
        else:
            bad.extend(gone_bad)
            bad.extend(stale_bad)
            if gone_bad:
                # 这里一个字都不许提重建：工具主动指路会把「删掉一条评审」变成一步消音
                hints.append("索引比账本长（或者账本空了索引还记着行）——脚本是先落行、"
                             "再写索引，打断只会让索引落后，做不出这种状态。")
                hints.append("只可能是账本的行没了。请自己把行找回来（版本快照、备份、"
                             "版本管理里都可能有），不要靠改索引把它抹平。")
            elif chain_bad and want:
                hints.append("--rebuild-index 拒绝动手：链自身就是断的，重建只会把篡改盖过去。"
                             "先照上面的行号把账本查清楚。")
            elif not chain_bad:
                hints.append("每条链自身逐行复算都是自洽的，对不上的只有索引 %s，"
                             "而且索引是落后的那一侧。" % CHAINS_NAME)
                hints.append("如果确认没有人动过账本（比如上一次写盘被打断），可以跑："
                             "check %s --rebuild-index" % ws.slug)
    bad.extend(chain_bad)

    for line in warn:
        print(line)
    for line in bad:
        print(line)
    for line in hints:
        print("      %s" % line)
    print("check %s：%d 个 ERROR，%d 个 WARN。" % (ws.slug, len(bad), len(warn)))
    return 1 if bad else 0


# ---------------------------------------------------------------- 入口

def build_parser():
    p = argparse.ArgumentParser(prog="essayctl.py", description="essay-sections 分段写作脚本")
    sub = p.add_subparsers(dest="command")

    def meta_flags(parser):
        parser.add_argument("--title", help="题目")
        parser.add_argument("--genre", help="文体")
        parser.add_argument("--level", help="级别")
        parser.add_argument("--setting", choices=SETTINGS, help="限时还是不限时")
        parser.add_argument("--target-words", dest="target_words", type=int, help="目标字数")
        parser.add_argument("--background", help="背景说明")
        parser.add_argument("--thesis", help="主论点")

    sub.add_parser("doctor", help="看本机环境与工作区在哪")
    i = sub.add_parser("init", help="建工作区")
    i.add_argument("slug", help="稿名（→ essays/<slug>），也可以直接给目录")
    meta_flags(i)
    m = sub.add_parser("meta", help="改题目背景")
    m.add_argument("slug")
    meta_flags(m)

    im = sub.add_parser("import", help="贴稿：切块编号 + 记字节偏移")
    im.add_argument("slug")
    im.add_argument("src", help="md / txt / html / docx 文件")
    a = sub.add_parser("assemble", help="按偏移切回分段")
    a.add_argument("slug")
    a.add_argument("--from", dest="src", required=True, help="分组载荷 JSON")

    o = sub.add_parser("outline", help="拆题")
    osub = o.add_subparsers(dest="sub")
    oa = osub.add_parser("add", help="加一轮子问题")
    oa.add_argument("slug")
    oa.add_argument("--from", dest="src", required=True, help="拆题载荷 JSON")

    c = sub.add_parser("context", help="输出上下文包 JSON")
    c.add_argument("slug")
    c.add_argument("segment", help="intro / body-01… / conclusion")

    r = sub.add_parser("review", help="评审")
    rsub = r.add_subparsers(dest="sub")
    ra = rsub.add_parser("add", help="入账一条评审")
    ra.add_argument("slug")
    ra.add_argument("segment")
    ra.add_argument("--from", dest="src", required=True, help="评审载荷 JSON")

    f = sub.add_parser("reflect", help="反思")
    fsub = f.add_subparsers(dest="sub")
    fa = fsub.add_parser("add", help="写一条反思")
    fa.add_argument("slug")
    fa.add_argument("--segment", help="区域反思钉在哪一段；不给就是总反思")
    fa.add_argument("--from", dest="src", required=True, help="反思载荷 JSON")

    d = sub.add_parser("reading", help="荐读")
    dsub = d.add_subparsers(dest="sub")
    da = dsub.add_parser("add", help="记一份荐读")
    da.add_argument("slug")
    da.add_argument("segment")
    da.add_argument("--from", dest="src", required=True, help="荐读载荷 JSON")

    for name, helptext in (("version", "拍一个版本快照"), ("status", "看每段的状态"),
                           ("report", "生成 report.html")):
        one = sub.add_parser(name, help=helptext)
        one.add_argument("slug")
    e = sub.add_parser("export", help="导出整篇或脱敏证据包")
    e.add_argument("slug")
    e.add_argument("--evidence", action="store_true", help="只导哈希与分数，不带正文")
    k = sub.add_parser("check", help="离线复核整个工作区")
    k.add_argument("slug", help="稿名或工作区目录")
    k.add_argument("--rebuild-index", dest="rebuild_index", action="store_true",
                   help="链自身自洽、且链尾索引只是落后或缺失时，按账本实际内容重建 %s；"
                        "索引超前或账本被删空一律拒绝（那是行没了，不是写盘被打断）"
                        % CHAINS_NAME)
    return p


HANDLERS = {"doctor": cmd_doctor, "init": cmd_init, "meta": cmd_meta, "import": cmd_import,
            "assemble": cmd_assemble, "context": cmd_context, "version": cmd_version,
            "status": cmd_status, "report": cmd_report, "export": cmd_export,
            "check": cmd_check}
NESTED = {"outline": ("add", cmd_outline_add), "review": ("add", cmd_review_add),
          "reflect": ("add", cmd_reflect_add), "reading": ("add", cmd_reading_add)}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    try:
        if args.command in NESTED:
            want, handler = NESTED[args.command]
            if getattr(args, "sub", None) != want:
                raise UsageError("%s 只有一个子命令：%s" % (args.command, want))
            return handler(args)
        return HANDLERS[args.command](args)
    except GateError as e:
        for line in e.args[0]:
            print(line)
        sys.stdout.flush()
        return 1
    except UsageError as e:
        return _fail("错误：%s" % e)
    except KeyboardInterrupt:
        return _fail("已中断")
    except Exception as e:
        return _fail("错误：%s：%s" % (type(e).__name__, e))


def _fail(message):
    sys.stdout.flush()
    print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
