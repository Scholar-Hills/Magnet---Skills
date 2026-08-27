#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""锚定批注引擎（零依赖，Python 3.8+ 标准库，单文件）。

模型只负责说「哪一句、什么问题、什么等级」，本文件负责把那句话钉回原文、
校验它确实来自原文，并把结果渲染成一页可截图的 HTML。

公开接口：
  extract(html)                    一次遍历同时产出纯文本与位置映射
  plain_text(html)                 extract(html).text 的快捷方式
  normalize(s)                     引文与原文共用的规范化（供各 Skill 的 CLI 复用）
  locate(ex, quote)                在原文里定位一句引文，返回 (start, end, partial)
  annotate(html, marks)            按引文锚定并 splice 出带 mark 的 HTML
  render_page(title, original_html, result, meta)   自包含单页报告
  LEVELS / DEFAULT_LEVEL           等级白名单；模型给的等级只能落在这里面

子命令：
  selftest                         跑内置回归用例

退出码：0 通过 / 1 未通过 / 2 用法错误。
"""

import argparse
import re
import sys
from html import escape as _escape
from html import unescape as _unescape
from html.parser import HTMLParser
from typing import List, NamedTuple, Optional, Tuple


class UsageError(Exception):
    """用法错误，退出码 2。"""


LEVELS = ("major", "minor", "remark")
DEFAULT_LEVEL = "remark"


# ---------------------------------------------------------------- 抽取

class Extraction(NamedTuple):
    """一次遍历的产物：给模型看的纯文本，以及每个字符在原 HTML 里的区间。"""
    text: str
    spans: List[Tuple[int, int]]
    html: str


class AnnotateResult(NamedTuple):
    """marks 是真相，html 只是缓存 —— 丢了可以由 marks 重新锚定出来。"""
    html: str
    marks: List[dict]
    anchored_ratio: float


# 边界处要在纯文本里插一个换行分隔符的标签
_BLOCK_TAGS = frozenset((
    "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "br", "blockquote", "pre", "td", "th",
))
_SKIP_TAGS = frozenset(("script", "style"))
_BLANK_LINE = re.compile(r"\n[ \t]*\n")

# 判「这份输入是 HTML 吗」。只看开始标签会把作答里的不等号当标签（`x<y 而且 y>z`
# 里的 `<y 而且 y>` 就长得像 `<y ...>`），后面整段被当标签吞掉。所以要求出现
# 三者之一：已知标签的闭合标签、已知的空标签、或明确自闭合的标签 —— 真的 HTML
# 一定会有其中之一，而散文里的不等号不会。
_HTML_MARKER = re.compile(
    r"</\s*(?:p|div|li|ul|ol|table|thead|tbody|tr|td|th|h[1-6]|blockquote|pre|code"
    r"|b|strong|i|em|u|s|span|a|mark|section|article|figure|figcaption|dl|dt|dd"
    r"|sub|sup|small|font|center|main|header|footer|nav|aside|body|html)\s*>"
    r"|<\s*(?:br|hr|img|input|meta|link|col|source|wbr)\b[^<>]*>"
    r"|<\s*[a-zA-Z][a-zA-Z0-9]*\b[^<>]*/\s*>",
    re.IGNORECASE)


def _wrap_plain(src: str) -> str:
    """无标签输入按空行分段包成 p；Markdown 不解析，整段当纯文本处理。"""
    blocks = [b.strip() for b in _BLANK_LINE.split(src)]
    return "".join("<p>%s</p>" % _escape(b, quote=False) for b in blocks if b)


class _Walker(HTMLParser):
    """同一次遍历里同时攒出纯文本和位置映射（两套抽取器口径不一是最根本的坑）。"""

    def __init__(self, src: str):
        HTMLParser.__init__(self, convert_charrefs=False)
        self.src = src
        self.chars = []                      # type: List[str]
        self.spans = []                      # type: List[Tuple[int, int]]
        self._line_head = [0]
        for i, ch in enumerate(src):
            if ch == "\n":
                self._line_head.append(i + 1)
        self._skip_depth = 0
        self._break_pending = False

    # -- 位置：由解析器当前偏移换算，不用 raw.find(data) 猜
    def _offset(self) -> int:
        line, col = self.getpos()
        if line - 1 < len(self._line_head):
            return self._line_head[line - 1] + col
        return len(self.src)

    def _push(self, ch: str, a: int, b: int) -> None:
        if self._break_pending:
            self._break_pending = False
            if self.chars and self.chars[-1] != "\n":
                self.chars.append("\n")
                self.spans.append((a, a))    # 分隔符是零宽区间
        self.chars.append(ch)
        self.spans.append((a, b))

    def _mark_boundary(self, tag: str) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self._break_pending = True

    def handle_starttag(self, tag, attrs):
        if tag.lower() in _SKIP_TAGS:
            self._skip_depth += 1
            return
        self._mark_boundary(tag)

    def handle_startendtag(self, tag, attrs):
        if tag.lower() in _SKIP_TAGS:
            return
        self._mark_boundary(tag)

    def handle_endtag(self, tag):
        if tag.lower() in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        self._mark_boundary(tag)

    def handle_data(self, data):
        if self._skip_depth or not data:
            return
        if not data.strip() and (self._break_pending or not self.chars):
            return                            # 标签之间的排版空白，丢掉
        base = self._offset()
        for i, ch in enumerate(data):
            self._push(ch, base + i, base + i + 1)

    def _handle_ref(self, prefix_len: int, name: str) -> None:
        if self._skip_depth:
            return
        start = self._offset()
        end = start + prefix_len + len(name)
        if self.src[end:end + 1] == ";":
            end += 1
        raw = self.src[start:end]
        decoded = _unescape(raw)
        if len(decoded) != 1:
            # 解不开的实体，或一个实体解出多个字符（&NotEqualTilde; 之类）：
            # 逐字符照原样映射。字符与区间必须严丝合缝地一对一，宁可把实体原文
            # 摆给模型看，也不要留一个对不上账的映射。
            for i, ch in enumerate(raw):
                self._push(ch, start + i, start + i + 1)
            return
        self._push(decoded, start, end)

    def handle_entityref(self, name):
        self._handle_ref(1, name)

    def handle_charref(self, name):
        self._handle_ref(2, name)


def extract(html: str) -> Extraction:
    """把 HTML / Markdown / 纯文本抽成纯文本 + 位置映射。"""
    src = (html or "").replace("\r\n", "\n").replace("\r", "\n")
    if not _HTML_MARKER.search(src):
        src = _wrap_plain(src)
    walker = _Walker(src)
    walker.feed(src)
    walker.close()
    return Extraction("".join(walker.chars), walker.spans, src)


def plain_text(html: str) -> str:
    """extract(html).text 的快捷方式：只要给模型看的那份文本。"""
    return extract(html).text


# ---------------------------------------------------------------- 规范化与定位

_CHAR_MAP = {"\xa0": " ", "　": " ",
             "‘": "'", "’": "'", "‚": "'", "‛": "'",
             "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"',
             "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-"}
_EDGE_PUNCT = frozenset(
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    "，。！？：；「」『』（）、“”‘’…——"
)


def _fold(s: str) -> Tuple[str, List[int]]:
    """规范化，并给出「规范化下标 → 原字符串下标」的反查表。"""
    out = []                                  # type: List[str]
    back = []                                 # type: List[int]
    i, n = 0, len(s)
    while i < n:
        ch = _CHAR_MAP.get(s[i], s[i])
        if ch.isspace():
            j = i
            while j < n and _CHAR_MAP.get(s[j], s[j]).isspace():
                j += 1
            if out:                           # 去首部空白
                out.append(" ")
                back.append(i)
            i = j
            continue
        out.append(ch)
        back.append(i)
        i += 1
    while out and out[-1] == " ":             # 去尾部空白
        out.pop()
        back.pop()
    return "".join(out), back


def normalize(s: str) -> str:
    """引文与原文共用的规范化：空白折叠、弯引号 / 破折号 / 不换行空格归一。"""
    return _fold(s or "")[0]


def _lower_keep_len(s: str) -> str:
    """小写化但保持长度不变（个别字符小写后会变长，会打乱下标）。"""
    out = []
    for ch in s:
        low = ch.lower()
        out.append(low if len(low) == 1 else ch)
    return "".join(out)


def _find(hay: str, needle: str) -> Optional[Tuple[int, int]]:
    """精确子串 → 大小写不敏感。"""
    if not needle:
        return None
    at = hay.find(needle)
    if at < 0:
        at = _lower_keep_len(hay).find(_lower_keep_len(needle))
    if at < 0:
        return None
    return at, at + len(needle)


def _strip_edge_punct(s: str) -> str:
    out = s
    while out and out[0] in _EDGE_PUNCT:
        out = out[1:]
    while out and out[-1] in _EDGE_PUNCT:
        out = out[:-1]
    return out.strip()


def _anchor_ends(hay: str, needle: str) -> Tuple[Optional[Tuple[int, int]], bool]:
    """头锚定 / 尾锚定：引文被改写过一半时的兜底。"""
    size = min(24, len(needle) // 2)
    if size < 8:                              # 太短的引文不做模糊锚定
        return None, False
    head = _find(hay, needle[:size])
    tail = _find(hay, needle[-size:])
    head_span = (head[0], min(len(hay), head[0] + len(needle))) if head else None
    tail_span = (max(0, tail[1] - len(needle)), tail[1]) if tail else None
    if head_span and tail_span:
        return (head_span, False) if head_span == tail_span else (None, False)
    if head_span:
        return head_span, True
    if tail_span:
        return tail_span, True
    return None, False


_TAG_IN_SPAN = re.compile(r"<[a-zA-Z/!][^<>]*>")

# 正文是不可信输入：它自带的 <mark> 与 class / data-an 长得和引擎钉上去的一模一样，
# 混进左栏就是一条伪造的批注（还会被页面的联动高亮认领）。定位之前先剥掉：标签脱壳
# 留字，属性整个删掉，其余部分一个字节都不动。
_ENGINE_ATTRS = frozenset(("class", "data-an"))
# 顺序扫一个标签里的属性。从属性区开头一路往后吃，引号里的 `class=foo` 会被当成
# 上一个属性的值吞掉，不会被当成属性名；属性名整串比对，`data-answer` 与 `classic`
# 这种以禁词开头的合法属性名也不会被啃掉半截。
_ATTR_SCAN = re.compile(r"""\s+([^\s"'>/=]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'=<>`]*))?""")


class _Stripper(HTMLParser):
    """找出正文里伪造的 mark 标签、以及 class / data-an 属性各自占的字节区间。

    用解析器定位标签而不是用正则：属性值里塞一个 `<` 或 `>`（`<mark title="<" …>`）
    就能把 `<[^<>]*>` 这类正则骗过去，伪造的批注照样落地。解析器认得引号。
    """

    def __init__(self, src: str):
        HTMLParser.__init__(self, convert_charrefs=False)
        self.src = src
        self.cuts = []                       # type: List[Tuple[int, int]]
        self._line_head = [0]
        for i, ch in enumerate(src):
            if ch == "\n":
                self._line_head.append(i + 1)

    def _offset(self) -> int:
        line, col = self.getpos()
        if line - 1 < len(self._line_head):
            return self._line_head[line - 1] + col
        return len(self.src)

    def handle_starttag(self, tag, attrs):
        start = self._offset()
        raw = self.get_starttag_text() or ""
        if not raw or not raw.startswith("<"):
            return
        if tag.lower() == "mark":
            self.cuts.append((start, start + len(raw)))   # 整个标签拿掉，里面的字留着
            return
        present = set(k.lower() for k, _ in attrs)
        for m in _ATTR_SCAN.finditer(raw, 1 + len(tag)):
            name = m.group(1).lower()
            if name in _ENGINE_ATTRS and name in present:
                self.cuts.append((start + m.start(), start + m.end()))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag.lower() != "mark":
            return
        start = self._offset()
        closed = self.src.find(">", start)
        self.cuts.append((start, closed + 1 if closed >= 0 else len(self.src)))


def _strip_forged(html: str) -> str:
    """剥掉正文里已有的 mark 标签与 class / data-an 属性，其余字节一个不动。"""
    src = html or ""
    if not _HTML_MARKER.search(src):
        return src                            # 纯文本里的尖括号不是标签，别乱动
    stripper = _Stripper(src)
    stripper.feed(src)
    stripper.close()
    if not stripper.cuts:
        return src
    out, cursor = [], 0
    for a, b in sorted(stripper.cuts):
        if a < cursor:                        # 兜底：区间重叠时以先到的为准
            continue
        out.append(src[cursor:a])
        cursor = b
    out.append(src[cursor:])
    return "".join(out)


def _mark_segments(html: str, start: int, end: int) -> List[Tuple[int, int]]:
    """把区间按标签切成若干段纯文本。

    一条批注可能跨过 `<b>` 这样的行内标签。整段包一个 mark 会 splice 出畸形嵌套
    （mark 在标签里开、在外面关），所以改成每个文本节点各包一个 mark，同一条批注
    的这几个 mark 共用一个 `data-an`。标签本身不进 mark。
    """
    segments = []
    cursor = start
    for m in _TAG_IN_SPAN.finditer(html, start, end):
        if m.start() > cursor:
            segments.append((cursor, m.start()))
        cursor = max(cursor, m.end())
    if end > cursor:
        segments.append((cursor, end))
    trimmed = []
    for a, b in segments:
        while a < b and html[a] in " \t\n":     # 不给零散的空白描下划线
            a += 1
        while b > a and html[b - 1] in " \t\n":
            b -= 1
        if b > a:
            trimmed.append((a, b))
    return trimmed


def _to_html_span(ex: Extraction, back: List[int], lo: int, hi: int,
                  partial: bool) -> Optional[Tuple[int, int, bool]]:
    if hi <= lo:
        return None
    first, last = back[lo], back[hi - 1]
    for k in range(first, last + 1):
        a, b = ex.spans[k]
        if a == b and ex.text[k] == "\n":     # 跨块引用不锚定，免得吞掉标签
            return None
    start, end = ex.spans[first][0], ex.spans[last][1]
    if end <= start:
        return None
    return start, end, partial


def locate(ex: Extraction, quote: str) -> Optional[Tuple[int, int, bool]]:
    """在原文里定位一句引文，返回 (start, end, partial)；找不到返回 None。"""
    if not quote or not ex.text:
        return None
    hay, back = _fold(ex.text)
    needle = normalize(quote)
    if not needle or not hay:
        return None
    partial = False
    span = _find(hay, needle)
    if span is None:
        bare = _strip_edge_punct(needle)
        if bare and bare != needle:
            span = _find(hay, bare)
            if span is not None:
                needle = bare
    if span is None:
        span, partial = _anchor_ends(hay, needle)
    if span is None:
        return None
    return _to_html_span(ex, back, span[0], span[1], partial)


# ---------------------------------------------------------------- 批注

_MARK_KEYS = ("id", "quote", "level", "note", "fix", "anchored", "partial",
              "start", "end", "level_fixed", "dropped_overlap")


def _prepare(raw: dict, levels) -> dict:
    level = raw.get("level", DEFAULT_LEVEL)
    fixed = not (isinstance(level, str) and level in levels)
    item = {
        "quote": str(raw.get("quote") or ""),
        "level": DEFAULT_LEVEL if fixed else level,
        "note": str(raw.get("note") or ""),
        "anchored": False,
        "partial": False,
        "level_fixed": fixed,
        "dropped_overlap": False,
    }
    if raw.get("fix"):
        item["fix"] = str(raw["fix"])
    return item


def _reduce_overlap(items: List[dict]) -> List[dict]:
    """同 start 取最长 → 贪心保留两两不相交。HTML 表达不了交叉区间。"""
    placed = [m for m in items if "start" in m]
    placed.sort(key=lambda m: (m["start"], -m["end"]))
    kept, edge = [], -1
    for m in placed:
        if m["start"] < edge:
            m["dropped_overlap"] = True
            m["partial"] = False
            m.pop("start", None)
            m.pop("end", None)
            continue
        edge = m["end"]
        m["anchored"] = True
        kept.append(m)
    return kept


def annotate(html: str, marks: List[dict], *, levels=LEVELS) -> AnnotateResult:
    """按引文把批注钉回原文；钉不上的条目照样入列，只是没有锚点。

    跨行内标签的引文按文本节点切段，一条批注可能对应多个共用 `data-an` 的 mark。
    正文里已有的 mark 与 class / data-an 会先被剥掉，所以带伪造批注的输入，
    输出 HTML 不会与输入逐字相同 —— 这正是要的。
    """
    ex = extract(_strip_forged(html))
    items = []
    for raw in (marks or []):
        item = _prepare(raw if isinstance(raw, dict) else {}, levels)
        hit = locate(ex, item["quote"]) if item["quote"] else None
        if hit is not None:
            item["start"], item["end"], item["partial"] = hit
        items.append(item)

    kept = _reduce_overlap(items)
    ordered = kept + [m for m in items if not m["anchored"]]
    for i, m in enumerate(ordered, 1):
        m["id"] = i

    pieces = []
    for m in kept:
        opening = '<mark class="an an-%s" data-an="%d">' % (m["level"], m["id"])
        pieces.extend((a, b, opening) for a, b in _mark_segments(ex.html, m["start"], m["end"]))
    out = ex.html
    for a, b, opening in sorted(pieces, reverse=True):   # 从后往前才不打乱前面的偏移
        out = out[:b] + "</mark>" + out[b:]
        out = out[:a] + opening + out[a:]

    tidy = [dict((k, m[k]) for k in _MARK_KEYS if k in m) for m in ordered]
    ratio = round(len(kept) / len(ordered), 4) if ordered else 0.0
    return AnnotateResult(out, tidy, ratio)


# ---------------------------------------------------------------- 渲染

# 左栏的正文来自学生作答与老师题干（题干允许含 HTML），是不可信输入；判题卡又是
# 老师在本地双击打开的文件。所以进页面前过一遍白名单：只留排版需要的标签，属性只
# 留 class 与 data-an，script / style / iframe 这类连内容一起丢，其余标签脱掉外壳
# 但保留里面的文字。
_SAFE_TAGS = frozenset((
    "p", "div", "ul", "ol", "li", "table", "thead", "tbody", "tr", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6", "br", "blockquote", "pre", "code",
    "b", "strong", "i", "em", "u", "s", "mark",
))
_SAFE_ATTRS = frozenset(("class", "data-an"))
_VOID_TAGS = frozenset((
    "br", "img", "hr", "input", "meta", "link", "source", "col",
    "area", "base", "wbr", "embed", "param", "track", "frame",
))
_DROP_SUBTREE = frozenset((
    "script", "style", "iframe", "object", "embed", "applet", "noscript",
    "template", "svg", "math", "form", "select", "textarea", "button",
    "canvas", "audio", "video", "frame", "frameset",
))


class _Cleaner(HTMLParser):
    """白名单过滤器：重新拼一份只含安全标签的 HTML，顺手把标签配平。"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.out = []                        # type: List[str]
        self.open_tags = []                  # type: List[str]
        self._drop_tag = None
        self._drop_depth = 0

    def handle_starttag(self, tag, attrs):
        name = tag.lower()
        if self._drop_depth:
            if name == self._drop_tag:
                self._drop_depth += 1
            return
        if name in _DROP_SUBTREE:
            if name in _VOID_TAGS:
                return                       # 空元素等不到闭合标签，进了 drop 模式就再也出不来
            self._drop_tag, self._drop_depth = name, 1
            return
        if name not in _SAFE_TAGS:
            return                           # 脱掉外壳，里面的文字照留
        kept = "".join(' %s="%s"' % (k.lower(), _escape(v or "", quote=True))
                       for k, v in attrs if k.lower() in _SAFE_ATTRS)
        self.out.append("<%s%s>" % (name, kept))
        if name not in _VOID_TAGS:
            self.open_tags.append(name)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        name = tag.lower()
        if self._drop_depth:
            if name == self._drop_tag:
                self._drop_depth -= 1
                if not self._drop_depth:
                    self._drop_tag = None
            return
        if name in _VOID_TAGS or name not in self.open_tags:
            return                           # 野生的闭合标签，丢掉
        while self.open_tags:
            top = self.open_tags.pop()
            self.out.append("</%s>" % top)
            if top == name:
                break

    def handle_data(self, data):
        if not self._drop_depth and data:
            self.out.append(_escape(data, quote=False))

    def result(self) -> str:
        while self.open_tags:                # 没闭合的补上，免得撑破整页布局
            self.out.append("</%s>" % self.open_tags.pop())
        return "".join(self.out)


def sanitize(html: str) -> str:
    """把一段 HTML 过成只含白名单标签与 class / data-an 属性的安全版本。"""
    cleaner = _Cleaner()
    cleaner.feed(html or "")
    cleaner.close()
    return cleaner.result()


LEVEL_LABEL = {"major": "要紧", "minor": "次要", "remark": "提示"}

_PAGE_CSS = """
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#ffffff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de;
--accent:#0969da;--major:#cf222e;--majorbg:#ffebe9;--minor:#9a6700;--minorbg:#fff8c5;--remark:#0969da;--remarkbg:#ddf4ff}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--fg:#e6edf3;--muted:#8b949e;--line:#30363d;
--accent:#58a6ff;--major:#f85149;--majorbg:#2d1416;--minor:#d29922;--minorbg:#272115;--remark:#58a6ff;--remarkbg:#0c2d6b}}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px 28px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:20px 0 8px;color:var(--muted)}
.meta{color:var(--muted);font-size:13px;margin-bottom:16px}
.cols{display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap}
.doc{flex:3 1 380px;min-width:0;border:1px solid var(--line);border-radius:10px;padding:8px 16px;overflow-x:auto}
.doc p,.doc li,.doc blockquote{margin:10px 0}
.side{flex:2 1 300px;min-width:0}
mark.an{background:transparent;color:inherit;padding:1px 0;border-bottom:2px solid var(--remark)}
mark.an-major{border-color:var(--major)}mark.an-minor{border-color:var(--minor)}
mark.an.lit{background:var(--remarkbg)}mark.an-major.lit{background:var(--majorbg)}mark.an-minor.lit{background:var(--minorbg)}
ol.list{list-style:none;margin:0;padding:0}
li.item{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0 0 10px}
li.item.lit{border-color:var(--accent)}
.tag{display:inline-block;font-size:12px;font-weight:600;border-radius:999px;padding:1px 9px;margin-right:6px}
.tag-major{background:var(--majorbg);color:var(--major)}.tag-minor{background:var(--minorbg);color:var(--minor)}
.tag-remark{background:var(--remarkbg);color:var(--remark)}
.no{color:var(--muted);font-size:12px}
.said{margin:6px 0;padding-left:10px;border-left:3px solid var(--line);color:var(--muted);font-size:13px}
.item p{margin:6px 0}.tip{font-size:13px;color:var(--accent)}
.empty{color:var(--muted);font-size:13px}
.foot{margin:20px 0 0;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
"""

_PAGE_JS = """
(function(){
  var all=document.querySelectorAll('[data-an]');
  function light(id,on){
    var group=document.querySelectorAll('[data-an="'+id+'"]');
    for(var i=0;i<group.length;i++){group[i].classList.toggle('lit',on);}
  }
  for(var i=0;i<all.length;i++){
    (function(el){
      var id=el.getAttribute('data-an');
      el.addEventListener('mouseenter',function(){light(id,true);});
      el.addEventListener('mouseleave',function(){light(id,false);});
    })(all[i]);
  }
})();
"""


def _mark_card(m: dict) -> str:
    level = m.get("level", DEFAULT_LEVEL)
    parts = ['<li class="item" data-an="%d">' % m.get("id", 0),
             '<span class="tag tag-%s">%s</span><span class="no">第 %d 条%s</span>'
             % (level, _escape(LEVEL_LABEL.get(level, level)), m.get("id", 0),
                "　（头尾锚定，仅供参考）" if m.get("partial") else "")]
    if m.get("quote"):
        parts.append('<div class="said">%s</div>' % _escape(m["quote"]))
    if m.get("note"):
        parts.append("<p>%s</p>" % _escape(m["note"]))
    if m.get("fix"):
        parts.append('<p class="tip">建议改为：%s</p>' % _escape(m["fix"]))
    parts.append("</li>")
    return "".join(parts)


def render_page(title: str, original_html: str, result: AnnotateResult, meta: dict) -> str:
    """自包含单页报告：左栏原文带 mark，右栏按编号列条目，无任何外链。

    左栏的正文先过 `sanitize`：正文是不可信输入，页面却要在老师本地直接打开。
    """
    anchored = [m for m in result.marks if m.get("anchored")]
    missed = [m for m in result.marks if not m.get("anchored")]
    bits = ["　·　".join("%s：%s" % (_escape(str(k)), _escape(str(v))) for k, v in (meta or {}).items())]
    bits.append("锚定率 %d%%（%d/%d）" % (round(result.anchored_ratio * 100), len(anchored), len(result.marks)))
    side = ["<h2>批注（%d 条）</h2>" % len(anchored)]
    side.append('<ol class="list">%s</ol>' % "".join(_mark_card(m) for m in anchored)
                if anchored else '<p class="empty">没有锚定成功的批注。</p>')
    if missed:
        side.append("<h2>未能定位（%d 条）</h2>" % len(missed))
        side.append('<ol class="list">%s</ol>' % "".join(_mark_card(m) for m in missed))
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>%s</title><style>%s</style></head>\n<body><div class=\"wrap\">"
            "<h1>%s</h1><div class=\"meta\">%s</div>"
            "<div class=\"cols\"><div class=\"doc\">%s</div><div class=\"side\">%s</div></div>"
            "<p class=\"foot\">批注由脚本锚定，未定位条目脚本不擅自摆放。</p>"
            "</div><script>%s</script></body></html>\n"
            % (_escape(title), _PAGE_CSS, _escape(title), "　·　".join(b for b in bits if b),
               sanitize(result.html or _strip_forged(original_html or "")), "".join(side), _PAGE_JS))


# ---------------------------------------------------------------- 自测

class Failed(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Failed(msg)


SRC_TWO_BLOCKS = "<p>Supply &amp; demand</p><p>shift</p>"


def t_extract_invariant():
    """抽取给模型的文本与建位置映射必须是同一次遍历的产物。"""
    ex = extract(SRC_TWO_BLOCKS)
    check(ex.text == "Supply & demand\nshift", "纯文本应为 'Supply & demand\\nshift'，实际 %r" % ex.text)
    check(len(ex.spans) == len(ex.text), "spans 与 text 应等长，实际 %d / %d" % (len(ex.spans), len(ex.text)))
    zero = [i for i, (a, b) in enumerate(ex.spans) if a == b]
    check(zero == [15], "只有块级分隔符是零宽区间，实际零宽下标 %r" % zero)
    check(ex.text[15] == "\n", "零宽区间处应是换行分隔符，实际 %r" % ex.text[15])
    joined = "".join(ex.html[a:b] for a, b in ex.spans if a != b)
    visible = "".join(c for c, (a, b) in zip(ex.text, ex.spans) if a != b)
    check(_unescape(joined) == visible,
          "拼回的 HTML 片段解码后应等于去零宽的纯文本：%r vs %r" % (_unescape(joined), visible))
    check(all(ex.spans[i][0] <= ex.spans[i + 1][0] for i in range(len(ex.spans) - 1)), "spans 起点应单调不减")

    # 同一组不变量换各种脏输入再验一遍，不只是漂亮的那一份。
    # 解不出单个字符的实体（&NotEqualTilde; 之类）按原文逐字符映射，所以两边都 unescape 再比。
    for src in (SRC_TWO_BLOCKS, "<p>A&foo B</p>", "<p>甲&nbsp;乙</p>", "<p>x&NotEqualTilde;y</p>",
                "<p>甲</p>\n  <p>乙</p>", "<p>甲<b>乙", "<table><tr><td>甲</td><td>乙</td></tr></table>",
                "<p>甲</p><script>var x = '<p>假</p>';</script><p>乙</p>", "纯文本一段。\n\n第二段。"):
        one = extract(src)
        check(len(one.spans) == len(one.text), "%r：spans 与 text 应等长" % src)
        got = "".join(one.html[a:b] for a, b in one.spans if a != b)
        want = "".join(c for c, (a, b) in zip(one.text, one.spans) if a != b)
        check(_unescape(got) == _unescape(want),
              "%r：拼回的 HTML 片段应等于去零宽的纯文本：%r vs %r" % (src, _unescape(got), _unescape(want)))
        check(all(one.spans[i][0] <= one.spans[i + 1][0] for i in range(len(one.spans) - 1)),
              "%r：spans 起点应单调不减" % src)
        # 跨块判定全靠这条：零宽区间只可能是块级分隔符
        bad = [i for i, (a, b) in enumerate(one.spans) if a == b and one.text[i] != "\n"]
        check(not bad, "%r：零宽区间只应出现在块级分隔符上，实际还有下标 %r" % (src, bad))


def t_entity_anchor():
    """回归缺陷 A（实体让文本节点整块丢失）与缺陷 B（跨块引用吞标签）。"""
    ex = extract(SRC_TWO_BLOCKS)
    check(locate(ex, "demand shift") is None, "跨块引文必须拒绝锚定，实际 %r" % (locate(ex, "demand shift"),))
    hit = locate(ex, "Supply & demand")
    check(hit is not None, "含实体的引文必须能锚定，实际 None")
    start, end, partial = hit
    check(ex.html[start:end] == "Supply &amp; demand", "区间应覆盖实体原文，实际 %r" % ex.html[start:end])
    check(partial is False, "精确命中不应标 partial")


def t_attr_collision():
    """回归缺陷 D：前一个标签的属性值与文本相同，mark 不得被塞进属性里。"""
    src = '<p title="alpha">alpha</p>'
    res = annotate(src, [{"quote": "alpha", "level": "minor", "note": "属性碰撞回归"}])
    check('title="alpha"' in res.html, "原属性应原样保留，实际 %r" % res.html)
    check(res.html.count("<mark") == 1, "应恰好包裹一次，实际 %d 次：%r" % (res.html.count("<mark"), res.html))
    want = '<p title="alpha"><mark class="an an-minor" data-an="1">alpha</mark></p>'
    check(res.html == want, "应只包住文本节点，实际 %r" % res.html)


def t_level_injection():
    """回归缺陷 C：等级是模型可控字段，插进属性前必须白名单。"""
    bad = 'x" onclick="alert(1)'
    res = annotate("<p>alpha beta</p>", [{"quote": "beta", "level": bad, "note": "注入回归"}])
    check("onclick" not in res.html, "白名单外的等级不得进入 HTML，实际 %r" % res.html)
    check(res.marks[0]["level"] == DEFAULT_LEVEL, "非法等级应回落为默认等级，实际 %r" % res.marks[0]["level"])
    check(res.marks[0]["level_fixed"] is True, "回落时应记 level_fixed")


def t_overlap():
    """重叠区间先归约再 splice，同 start 取最长。"""
    src = "<p>the quick brown fox jumps</p>"
    res = annotate(src, [{"quote": "quick brown", "level": "major", "note": "甲"},
                         {"quote": "brown fox", "level": "minor", "note": "乙"}])
    by_quote = {m["quote"]: m for m in res.marks}
    check(by_quote["quick brown"]["anchored"] is True, "先到的区间应保留")
    check(by_quote["brown fox"]["anchored"] is False, "重叠的后一条应改为未锚定")
    check(by_quote["brown fox"]["dropped_overlap"] is True, "重叠剔除应记 dropped_overlap")
    check(res.html.count("<mark") == 1, "只应留下一个 mark，实际 %r" % res.html)

    res2 = annotate(src, [{"quote": "quick", "level": "minor", "note": "甲"},
                          {"quote": "quick brown", "level": "minor", "note": "乙"}])
    by_quote2 = {m["quote"]: m for m in res2.marks}
    check(by_quote2["quick brown"]["anchored"] is True, "同 start 应取最长")
    check(by_quote2["quick"]["anchored"] is False, "同 start 的短区间应被剔除")


def t_disjoint_order():
    """不相交的多条乱序输入：编号按文档顺序，原文逐字不变。"""
    src = "<p>alpha</p><p>beta</p><p>gamma</p>"
    res = annotate(src, [{"quote": "gamma", "level": "remark", "note": "丙"},
                         {"quote": "alpha", "level": "major", "note": "甲"},
                         {"quote": "beta", "level": "minor", "note": "乙"}])
    ids = re.findall(r'data-an="(\d+)"', res.html)
    check(ids == ["1", "2", "3"], "文档顺序上的编号应为 1,2,3，实际 %r" % ids)
    order = [m["quote"] for m in res.marks]
    check(order == ["alpha", "beta", "gamma"], "条目应按文档顺序重排，实际 %r" % order)
    stripped = re.sub(r"</?mark[^>]*>", "", res.html)
    check(stripped == src, "去掉 mark 后应与原文逐字相同，实际 %r" % stripped)


def t_unanchored_kept():
    """定位失败不等于批注失败：条目保留，只是没有锚点。"""
    res = annotate("<p>alpha</p>", [{"quote": "not here at all", "level": "major", "note": "甲"}])
    check(len(res.marks) == 1, "未命中的条目也要保留")
    check(res.marks[0]["anchored"] is False, "未命中应记 anchored False")
    check(res.marks[0]["note"] == "甲", "批语不得被加前缀，实际 %r" % res.marks[0]["note"])
    check("<mark" not in res.html, "未命中不得产出 mark")
    check(res.anchored_ratio == 0.0, "锚定率应为 0.0，实际 %r" % res.anchored_ratio)


def t_quotes_dashes():
    """弯引号与破折号归一：模型抄原文时标点几乎必然漂移。"""
    ex = extract("<p>他说“机会成本”——是最重要的概念。</p>")
    hit = locate(ex, '他说"机会成本"--是')
    check(hit is not None, "直引号与双连字符的引文应能命中")
    start, end, partial = hit
    check(ex.html[start:end] == "他说“机会成本”——是", "区间应覆盖原文的弯引号写法，实际 %r" % ex.html[start:end])


def t_case_and_punct():
    """大小写不敏感 + 剥去引文首尾标点后重试。"""
    ex = extract("<p>The Firm decides.</p>")
    hit = locate(ex, "the firm decides")
    check(hit is not None, "大小写不同的引文应能命中")
    check(ex.html[hit[0]:hit[1]] == "The Firm decides", "应命中原文大小写，实际 %r" % ex.html[hit[0]:hit[1]])
    hit2 = locate(ex, "“The Firm decides.”")
    check(hit2 is not None, "剥去首尾标点后应能命中")
    check(ex.html[hit2[0]:hit2[1]] == "The Firm decides", "剥标点后的区间不应含句号，实际 %r" % ex.html[hit2[0]:hit2[1]])


def t_partial_anchor():
    """头尾锚定：引文前半逐字、后半被改写时仍给出锚点并标 partial。"""
    ex = extract("<p>The opportunity cost of choosing option A is the value of the next best alternative.</p>")
    hit = locate(ex, "The opportunity cost of choosing something entirely different.")
    check(hit is not None, "头锚定应能命中")
    start, end, partial = hit
    check(partial is True, "只命中一头时应标 partial")
    check(ex.html[start:end].startswith("The opportunity cost of "), "区间应从引文头部开始，实际 %r" % ex.html[start:end])
    check(locate(ex, "The opportunXYZ") is None, "总长 15 时不启用头尾锚定，应返回 None")
    longer = locate(ex, "The opportunity cost of XYZ")
    check(longer is not None and longer[2] is True, "总长够时同样的分歧应能头锚定并标 partial")


def t_markdown_plain_input():
    """无标签输入按空行分段包成 p，Markdown 不解析。"""
    src = "第一段文字。\n\n第二段文字。\n\n第三段文字。"
    ex = extract(src)
    check(ex.text == "第一段文字。\n第二段文字。\n第三段文字。", "空行分段应折成单个换行，实际 %r" % ex.text)
    check(ex.text.count("\n") == 2, "三段应有两个换行，实际 %d" % ex.text.count("\n"))
    res = annotate(src, [{"quote": "第二段文字", "level": "remark", "note": "乙"}])
    check(res.html.startswith("<p>"), "纯文本输入应被包成 p，实际 %r" % res.html[:20])
    check("<mark" in res.html, "纯文本输入也应能锚定")


def t_render_selfcontained():
    """报告页自包含：不外链、深浅色可读、每条批注都在页面上。"""
    src = "<p>alpha</p><p>beta</p>"
    res = annotate(src, [{"quote": "alpha", "level": "major", "note": "甲", "fix": "改成这样"},
                         {"quote": "nope nope nope nope", "level": "minor", "note": "乙"}])
    page = render_page("合成样例批注", src, res, {"来源": "合成样例", "条目": 2})
    check("http://" not in page and "https://" not in page, "页面不得外链")
    check("<script src" not in page, "页面不得引用外部脚本")
    check("prefers-color-scheme" in page, "页面应带深色模式配色")
    for m in res.marks:
        check('data-an="%d"' % m["id"] in page, "第 %d 条应出现在页面上" % m["id"])
    check("合成样例批注" in page, "标题应出现在页面上")

    # 正文是不可信输入（作答与题干都允许含 HTML），页面却要在老师本地直接打开
    hostile = ('<p>alpha beta</p><script>alert(1)</script>'
               '<img src="http://evil.example/x.png">'
               '<p onclick="alert(2)">gamma</p>'
               '<iframe src="https://evil.example"></iframe>'
               '<a href="javascript:alert(3)">链接文字</a>'
               '<div style="background:url(http://evil.example/y)">delta</div>')
    bad_res = annotate(hostile, [{"quote": "alpha beta", "level": "major", "note": "甲"}])
    bad_page = render_page("敌意样例", hostile, bad_res, {})
    for danger in ("alert(", "http://", "https://", "onclick", "<img", "<iframe",
                   "javascript:", "style=", "<a ", "evil.example"):
        check(danger not in bad_page, "敌意正文里的 %s 不该出现在页面上" % danger)
    check(bad_page.count("<script") == 1, "页面只应有自己那一段内联脚本，实际 %d 段" % bad_page.count("<script"))
    for text in ("alpha beta", "gamma", "delta", "链接文字"):
        check(text in bad_page, "正文文字 %s 应当留下来" % text)
    check('data-an="1"' in bad_page, "敌意正文里的批注仍应锚定并出现在页面上")


def t_inline_tag_span():
    """跨行内标签的引文按文本节点切段，多个 mark 共用同一个 data-an。"""
    src = "<p>The <b>quick brown</b> fox jumps over</p>"
    ex = extract(src)
    for quote in ("quick brown fox", "The quick", "brown fox"):
        check(locate(ex, quote) is not None, "跨行内标签的引文应能锚定，%r 却是 None" % quote)
    res = annotate(src, [{"quote": "quick brown fox", "level": "major", "note": "甲"}])
    check(res.marks[0]["anchored"] is True, "跨行内标签的条目应记为已锚定")
    want = ('<p>The <b><mark class="an an-major" data-an="1">quick brown</mark></b> '
            '<mark class="an an-major" data-an="1">fox</mark> jumps over</p>')
    check(res.html == want, "应按文本节点切成两段且标签配平，实际 %r" % res.html)
    check(res.html.count('data-an="1"') == 2, "两段应共用一个编号，实际 %r" % res.html)
    check(re.sub(r"</?mark[^>]*>", "", res.html) == src, "去掉 mark 后应与原文逐字相同")
    inside = annotate(src, [{"quote": "quick brown", "level": "minor", "note": "乙"}])
    check(inside.html.count("<mark") == 1, "整段落在行内标签内的引文只应有一段，实际 %r" % inside.html)


def t_plain_text_with_angles():
    """作答里的不等号不是标签：判 HTML 的判据不许把纯文本吞掉。"""
    src = "如果 x<y 而且 y>z，那么 x<z。\n\n第二段结论。"
    ex = extract(src)
    check(ex.text == "如果 x<y 而且 y>z，那么 x<z。\n第二段结论。", "纯文本不得被吞，实际 %r" % ex.text)
    hit = locate(ex, "那么 x<z")
    check(hit is not None, "含不等号的引文应能锚定")
    check(ex.html[hit[0]:hit[1]] == "那么 x&lt;z", "纯文本进 HTML 时应转义，实际 %r" % ex.html[hit[0]:hit[1]])
    res = annotate(src, [{"quote": "x<y 而且 y>z", "level": "minor", "note": "乙"}])
    check("&lt;y" in res.html, "角括号应已转义，实际 %r" % res.html)
    check(res.marks[0]["anchored"] is True, "含不等号的引文应锚定成功")
    # 单字母变量名恰好撞上标签名也不许误判
    plain = "若 a<b and b>c 则 a<c"
    check(extract(plain).text == plain, "撞上标签名的不等号也不得被吞，实际 %r" % extract(plain).text)


def t_sanitize_void_drop():
    """空元素不能把后面的正文一起吞掉（embed / frame 既是空元素又在丢弃名单里）。"""
    for bad in ('<embed src="x">', '<embed src="x"/>', '<frame src="x">',
                "<embed>", "<object data=x></object>", '<iframe src="x"></iframe>'):
        out = sanitize("<p>一</p>%s<p>二</p>" % bad)
        check("二" in out, "%s 之后的正文必须保留，实际 %r" % (bad, out))
        check("一" in out, "%s 之前的正文必须保留，实际 %r" % (bad, out))
        check("<embed" not in out and "<frame" not in out and "<iframe" not in out and "<object" not in out,
              "%s 本身不该留在页面上，实际 %r" % (bad, out))
    # 真正带闭合标签的丢弃项，里面的内容仍然要丢干净
    dropped = sanitize("<p>一</p><script>alert(1)</script><p>二</p>")
    check("alert" not in dropped, "script 的内容应被丢掉，实际 %r" % dropped)
    check("一" in dropped and "二" in dropped, "script 前后的正文应保留，实际 %r" % dropped)
    nested = sanitize("<p>一</p><object data=x><object data=y></object></object><p>二</p>")
    check("二" in nested, "嵌套的丢弃项闭合后应恢复，实际 %r" % nested)


def t_forged_mark():
    """正文自带的 mark 与 class / data-an 是伪造的批注，进引擎前先剥掉。"""
    src = ('<p>正文 <mark class="an an-major" data-an="1">伪造的批注</mark> 结束</p>'
           '<p class="an an-minor" data-an="2" title="留着">整段伪造</p>')
    res = annotate(src, [{"quote": "结束", "level": "remark", "note": "真批注"}])
    check("伪造的批注" in res.html and "整段伪造" in res.html, "伪造标记里的文字应作为普通文本留下，实际 %r" % res.html)
    check("an-major" not in res.html and "an-minor" not in res.html, "伪造的 class 应被剥掉，实际 %r" % res.html)
    check('title="留着"' in res.html, "class 以外的属性不该被误删，实际 %r" % res.html)
    ids = re.findall(r'data-an="(\d+)"', res.html)
    anchored = [m for m in res.marks if m["anchored"]]
    check(len(anchored) == 1, "真批注应锚定成功，实际 %r" % res.marks)
    check(ids == ["1"], "页面上只应有引擎自己钉的那些段，实际 %r" % ids)
    page = render_page("伪造样例", src, res, {})
    check('data-an="2"' not in page, "伪造的编号不该出现在页面上")
    # 页面自带的样式表里有 mark.an-major 选择器，所以要按属性形态查
    check('class="an an-major"' not in page, "伪造的 mark 不该出现在页面上")
    check(page.count('<mark class="an an-remark" data-an="1">') == 1, "页面上只应有引擎钉的那一个 mark")
    check("伪造的批注" in page, "伪造标记里的文字应作为普通文本出现在页面上")


def t_strip_forged_exact():
    """剥伪造批注：绕不过去（属性值里塞尖括号），也不许啃到合法属性。"""
    # 合法属性逐字不变 —— 名字以禁词开头、或值里写着 class= 的都不许动
    for clean in ('<p data-answer="42" id="q1">题目</p>',
                  '<p classic="x">古典</p>',
                  '<p title="use class=foo here">说明</p>',
                  '<p title="alpha">alpha</p>',
                  '<p title="a<b">尖括号在属性值里</p>',
                  "<p>甲</p><p>乙</p>"):
        got = annotate(clean, []).html
        check(got == clean, "干净输入应逐字不变：%r → %r" % (clean, got))

    # 属性值里塞尖括号绕不过去
    for forged in ('<p>正文 <mark title="<" class="an an-major" data-an="97">伪造满分</mark> 结束</p>',
                   '<p>正文 <b title=">" class="an an-major" data-an="99">伪造满分</b> 结束</p>'):
        res = annotate(forged, [{"quote": "结束", "level": "remark", "note": "真批注"}])
        ids = re.findall(r'data-an="(\d+)"', res.html)
        check(ids == ["1"], "%r：只应剩引擎自己的编号，实际 %r（%r）" % (forged, ids, res.html))
        check("an-major" not in res.html, "%r：伪造的等级 class 应被剥掉，实际 %r" % (forged, res.html))
        check("伪造满分" in res.html, "%r：伪造标记里的文字应作为普通文本留下" % forged)
        page = render_page("伪造样例", forged, res, {})
        check('data-an="97"' not in page and 'data-an="99"' not in page, "伪造的编号不该出现在页面上")
        check(page.count('<mark class="an an-remark" data-an="1">') == 1, "页面上只应有引擎钉的那一个 mark")
        check("伪造满分" in page, "伪造标记里的文字应作为普通文本出现在页面上")

    # 截断的伪造标签：解析器不认它，剥不掉也不许它变成真属性落到左栏上
    for broken in ('<p>甲</p><mark class="an an-major" data-an="5"',
                   '<p>甲</p><mark class="an an-major" data-an="5" 未闭合'):
        page = render_page("截断", broken, annotate(broken, []), {})
        doc = page.split('<div class="doc">')[1].split('</div><div class="side">')[0]
        check('data-an="5"' not in doc, "截断的伪造标签不该在左栏变成真属性，实际 %r" % doc)
        check("甲" in doc, "截断输入的正文应保留，实际 %r" % doc)

    # 引号形态换着写也一样剥
    for forged, want in (('<p data-an=5 class=x id=z>甲</p>', '<p id=z>甲</p>'),
                         ("<p class='an' data-an='7'>乙</p>", "<p>乙</p>")):
        got = annotate(forged, []).html
        check(got == want, "%r 应剥成 %r，实际 %r" % (forged, want, got))


def t_banned_words_selfscan():
    """引擎自身不含禁用词；同时正向验证扫描器确实会报。"""
    import os
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import banned_words

    hits = banned_words.scan_dir(here)
    check(hits == [], "引擎目录不应含禁用词，实际：\n%s" % "\n".join(hits))

    # 三个脏字符串都拆开拼，免得本文件自己被扫出来
    probe = "zzz_internal" + "_canary_zzz"
    home = "/Us" + "ers/somebody/x"
    enum = "warn" + "ing"
    tmp = tempfile.mkdtemp(prefix="anchor-selftest-")
    try:
        with open(os.path.join(tmp, "a.md"), "w", encoding="utf-8") as f:
            f.write("路径 %s 不该出现。\n" % home)
        with open(os.path.join(tmp, "b.json"), "w", encoding="utf-8") as f:
            f.write('{"level": "%s"}\n' % enum)
        with open(os.path.join(tmp, "c.md"), "w", encoding="utf-8") as f:
            f.write("金丝雀 %s 应被摘要表命中。\n" % probe)
        with open(os.path.join(tmp, "d.md"), "w", encoding="utf-8") as f:
            f.write("这是一段干净的中文说明，没有任何禁用词。\n")
        found = banned_words.scan_dir(tmp)
        files = " ".join(found)
        check(len(found) == 3, "三个脏文件应各报一条，实际 %d 条：\n%s" % (len(found), "\n".join(found)))
        check("a.md" in files, "本机绝对路径应被子串表命中：\n%s" % "\n".join(found))
        check("b.json" in files, "JSON 里的通用枚举词应被令牌表命中：\n%s" % "\n".join(found))
        check("c.md" in files, "摘要表应命中金丝雀：\n%s" % "\n".join(found))
        check("d.md" not in files, "干净文件不应被报：\n%s" % "\n".join(found))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


SELFTESTS = (
    t_extract_invariant,
    t_entity_anchor,
    t_attr_collision,
    t_level_injection,
    t_overlap,
    t_disjoint_order,
    t_unanchored_kept,
    t_quotes_dashes,
    t_case_and_punct,
    t_partial_anchor,
    t_markdown_plain_input,
    t_render_selfcontained,
    t_inline_tag_span,
    t_plain_text_with_angles,
    t_sanitize_void_drop,
    t_forged_mark,
    t_strip_forged_exact,
    t_banned_words_selfscan,
)


def run_selftest():
    failed = []
    for fn in SELFTESTS:
        try:
            fn()
        except Failed as e:
            failed.append(fn.__name__)
            print("FAIL %s：%s" % (fn.__name__, e))
        except Exception as e:  # 未实现 / 崩溃同样算失败
            failed.append(fn.__name__)
            print("FAIL %s：%s：%s" % (fn.__name__, type(e).__name__, e))
        else:
            print("pass %s" % fn.__name__)
    if failed:
        print("%d/%d 个用例未通过：%s" % (len(failed), len(SELFTESTS), "、".join(failed)))
        return 1
    print("OK（%d 个用例全部通过）" % len(SELFTESTS))
    return 0


# ---------------------------------------------------------------- 入口

def build_parser():
    p = argparse.ArgumentParser(prog="anchor.py", description="锚定批注引擎")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("selftest", help="跑内置回归用例")
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    if not args.command:
        build_parser().print_help()
        return 2
    try:
        if args.command == "selftest":
            return run_selftest()
        raise UsageError("未知子命令：%s" % args.command)
    except UsageError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
