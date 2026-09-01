#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lesson-prep 备课脚本（零依赖，Python 3.8+ 标准库，单文件）。

四步走：课纲卡 → 作业 → 阶段 → 页稿 → 成品。三把锁由盖章文件保证，不靠自觉：

  没出作业，不许规划阶段；没规划阶段，不许写页稿；没有一页过验收，不许出成品。

子命令：
  doctor                                    本机环境与发布卫生自检
  init <slug> [--route homework-first|content-first]
                                            建课骨架 lessons/<slug>/
  check <slug> <lesson|questions|phases|pages>
  check <slug> --all                        四步复核 + 成品哈希对账
  build <slug> [--palette <key>]            从 pages/ 派生 deck.html 与 notes.html
  repalette <slug> --palette <key>          只换主题色重拼，页稿逐字节不动
  report <slug>                             渲染 report.md 与 report.html

退出码：0 通过 / 1 闸门不过（有 ERROR）/ 2 用法、环境或锁。

成品只能由 build 产出：页稿是唯一的 source of truth，deck.html 由脚本逐页
消毒 → 主题色归一 → 校验后拼出来，讲稿另出 notes.html，绝不进投屏文件。

覆盖判据是文本重合启发式，不是执行真值：它挡得住「贴个标签蒙混过去」，
挡不住「讲到了但讲错了」，后者仍要老师这一步自己看。
"""

import argparse
import datetime
import hashlib
import html as htmllib
import json
import os
import re
import sys
from html.parser import HTMLParser

MIN_PY = (3, 8)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
DRILL_RE = re.compile(r"^drill:[a-z0-9][a-z0-9-]{0,63}$")
ROUTES = ("homework-first", "content-first")
KINDS = ("choice", "short", "extended")
STEPS = ("lesson", "questions", "phases", "pages")

# 阈值（跨模型实测后可回调；改这里必须同 commit 改 references 与 selftest）
QUESTION_RANGE = (3, 20)
KIND_CAP = 10
PROMPT_MIN = 10
CHOICE_RANGE = (2, 6)
FOCUS_CAP = 5
DUP_PROMPT_RATIO = 0.6
PHASE_SOFT = (2, 6)
PHASE_HARD = 10
SUMMARY_MIN = 20
MINUTES_SOFT = (10, 180)
MINUTES_DRIFT = 0.10
PAGE_SOFT = (3, 20)
PAGE_HARD = 30
COVERS_CAP = 3
OVERLAP_MIN = 2
DENSITY_WARN = 350
DENSITY_HARD = 1000
TALK_PER_MINUTE = 60
COPY_RATIO = 0.8
SAT_WARN = 0.25
IMG_CAP = 2 * 1024 * 1024

# 八个主题色：只发英文 key 与 hex，壳里所有主题色都走 var(--accent)
PALETTES = (
    ("cyan", "#0891b2"),
    ("indigo", "#4f46e5"),
    ("emerald", "#059669"),
    ("amber", "#d97706"),
    ("rose", "#e11d48"),
    ("violet", "#7c3aed"),
    ("slate", "#475569"),
    ("teal", "#0d9488"),
)
PALETTE_MAP = dict(PALETTES)
DEFAULT_PALETTE = "cyan"
ACCENT_HEXES = frozenset(v.lower() for _, v in PALETTES)

SAFE_TAGS = frozenset((
    "h1", "h2", "h3", "p", "ul", "ol", "li",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup", "col",
    "blockquote", "div", "span", "strong", "em", "code", "pre",
    "figure", "figcaption", "img", "br", "hr",
))
SAFE_ATTRS = frozenset((
    "class", "id", "style", "alt", "src", "width", "height",
    "colspan", "rowspan", "scope", "lang", "dir", "title", "span",
))
BLOCK_TAGS = frozenset((
    "p", "div", "li", "tr", "h1", "h2", "h3", "br", "blockquote", "pre",
    "td", "th", "figure", "figcaption", "ul", "ol", "table",
))
ACCENT_CARRIERS = frozenset(("h1", "h2", "h3", "th", "blockquote"))

# 壳自己的结构名：页稿里再用一次，翻页脚本就会把假页当真页数进去（rail 显示 1/4、
# 真页内容被藏掉），所以准入阶段直接拒收，让老师在页稿里改名，而不是等 build 报壳级错误。
SHELL_CLASSES = frozenset((
    "slide", "pad", "fit", "stage", "rail", "thumb", "talk", "row", "wrap",
    "say", "no", "hd", "sub",
))
SHELL_DATA_ATTRS = frozenset(("data-page-id", "data-talk-id"))

# 白名单外但一定要点名骂的（出现即 ERROR，连 CDATA 都不放过）
RAW_BAD_TAG = re.compile(
    r"<\s*/?\s*(script|style|iframe|object|embed|svg|math|link|meta|base|form|input|"
    r"button|select|textarea|template|frame|frameset|applet|marquee|audio|video|source)\b",
    re.IGNORECASE)
RAW_ON_ATTR = re.compile(r"""[\s/"']on[a-zA-Z]+\s*=""")
DANGER_SCHEME = re.compile(r"^(javascript|vbscript|data):")
DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,", re.IGNORECASE)
# 合法 data:image 的 base64 载荷：外链判据先把它抠掉，免得载荷里的「//」被误判成外链
DATA_IMAGE_PAYLOAD = re.compile(r"data:image/(?:png|jpeg|jpg|gif|webp);base64,[a-z0-9+/=]*")
HEX6 = re.compile(r"#[0-9a-fA-F]{6}\b")

PLACEHOLDER_ASCII = (
    (re.compile(r"\bTODO\b", re.IGNORECASE), "TODO"),
    (re.compile(r"\bTBD\b", re.IGNORECASE), "TBD"),
    (re.compile(r"\bplaceholder\b", re.IGNORECASE), "placeholder"),
    (re.compile(r"lorem\s+ipsum", re.IGNORECASE), "lorem ipsum"),
)
PLACEHOLDER_CN = ("此处插图", "待补图", "[图]", "［图］", "此处配图", "待补充")

# 阶段标题的编号前缀：纯阶段名才留得住，「第一阶段」这类顺序词一律拦下
NUM_PREFIX = re.compile(
    r"^\s*("
    r"第\s*[0-9０-９一二三四五六七八九十百]+\s*[部章节讲课阶段步时篇课]"
    r"|[0-9０-９]+\s*[.、．，,)）:：]"
    r"|[一二三四五六七八九十]+\s*[、.．，,)）:：]"
    r"|[（(]\s*[0-9０-９一二三四五六七八九十]+\s*[)）]"
    r"|(?i:phase|step|part|lesson|unit|section|chapter|module|stage)\s*[0-9０-９]+"
    r")")

# 讲稿里不许出现 HTML：只认已知标签名，免得把「a<b 且 b>c」这类不等号当标签
NOTES_HTML = re.compile(
    r"</?\s*(p|div|span|br|h[1-6]|ul|ol|li|table|tr|td|th|img|strong|em|b|i|a|pre|"
    r"code|blockquote|figure|figcaption|script|style|section|iframe)\s*(/?>|\s+[a-zA-Z-]+\s*=)",
    re.IGNORECASE)

# 实词口径：中文去高频虚词后取 2-gram，英文小写去 stopwords，数字与标点一律丢掉。
# 这份表写进 references/workflow-rules.md，改一个字就要同 commit 改文档与 selftest。
CN_STOP = frozenset(
    "的了和与或是在有不也就都而及之其这那个为以对于从被把让使会要可应该"
    "我你他她它们吗呢吧啊呀但却则因所由向并且又再还只若请各每些什么很更最等如")
EN_STOP = frozenset((
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at", "for",
    "with", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "it", "its", "this", "that", "these",
    "those", "you", "your", "we", "our", "they", "their", "he", "she", "his", "her",
    "not", "no", "so", "than", "then", "there", "here", "what", "which", "who", "how",
    "why", "when", "where", "can", "could", "will", "would", "should", "may", "might",
    "must", "shall", "also", "about", "into", "over", "under", "between", "during",
    "such", "some", "any", "all", "each", "more", "most", "other", "only", "own",
    "same", "too", "very", "up", "down", "out", "off", "again", "further", "because",
    "while", "after", "before", "above", "below", "both", "few", "nor", "just", "now",
))
CJK = r"一-鿿㐀-䶿"
CJK_RUN = re.compile("[%s]+" % CJK)
UNIT_RE = re.compile("[%s]|[A-Za-z]+" % CJK)


class UsageError(Exception):
    """用法、环境或锁，退出码 2。"""


class LockError(UsageError):
    """三把锁之一挡在这里。"""


# ---------------------------------------------------------------- 小工具

def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def esc(text):
    return htmllib.escape(text if isinstance(text, str) else str(text))


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except FileNotFoundError:
        raise UsageError("找不到文件：%s" % path)
    except IsADirectoryError:
        raise UsageError("这是一个目录而不是文件：%s" % path)
    except UnicodeDecodeError as e:
        raise UsageError("文件不是 UTF-8 编码：%s（%s）" % (path, e))


def read_text_or_empty(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_json(path):
    raw = read_text(path)
    try:
        return json.loads(raw)
    except ValueError as e:
        raise UsageError("JSON 解析失败：%s（%s）" % (path, e))


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def as_list(value):
    return value if isinstance(value, list) else []


def as_text(value):
    return value.strip() if isinstance(value, str) else ""


def check_slug(slug):
    if not SLUG_RE.match(slug or ""):
        raise UsageError("slug 只能是小写字母、数字与连字符（不超过 64 位），当前是：%r" % slug)
    return slug


# ---------------------------------------------------------------- 文本口径

class _TextGrab(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in BLOCK_TAGS:
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in BLOCK_TAGS:
            self.buf.append("\n")

    def handle_data(self, data):
        self.buf.append(data)


def strip_tags(source):
    grab = _TextGrab()
    try:
        grab.feed(source or "")
        grab.close()
    except Exception:
        return re.sub(r"<[^>]*>", " ", source or "")
    return "".join(grab.buf)


def units(text):
    """字数与 2-gram 的共同底座：中文按字、英文按词，数字与标点丢掉。"""
    return [m.group(0).lower() for m in UNIT_RE.finditer(text or "")]


def text_len(text):
    return len(units(text))


def bigrams(text):
    seq = units(text)
    return set(zip(seq, seq[1:]))


def overlap_ratio(one, two):
    """以短的一边作分母：正文被整段抄进讲稿时是 1.00，这正是要抓的形态。"""
    if not one or not two:
        return 0.0
    return len(one & two) / float(min(len(one), len(two)))


def content_words(text):
    """实词集合：中文去虚词后按段取 2-gram，英文小写去 stopwords。"""
    words = set()
    for run in CJK_RUN.findall(text or ""):
        for seg in "".join(" " if ch in CN_STOP else ch for ch in run).split():
            for i in range(len(seg) - 1):
                words.add(seg[i:i + 2])
    for token in re.findall(r"[A-Za-z]{2,}", text or ""):
        low = token.lower()
        if low not in EN_STOP:
            words.add(low)
    return words


def placeholder_hit(text):
    """返回命中的占位模式，没有则 None。"""
    for pattern, label in PLACEHOLDER_ASCII:
        if pattern.search(text or ""):
            return label
    for label in PLACEHOLDER_CN:
        if label in (text or ""):
            return label
    return None


# ---------------------------------------------------------------- 结果收集

class Rep:
    """一次运行的全部 ERROR / WARN；报告与退出码都从这里来。"""

    def __init__(self):
        self.items = []

    def add(self, level, gate, where, reason):
        self.items.append({"level": level, "gate": gate, "where": where, "reason": reason})

    def bad(self, gate, where, reason):
        self.add("ERROR", gate, where, reason)

    def warn(self, gate, where, reason):
        self.add("WARN", gate, where, reason)

    def errors(self):
        return [i for i in self.items if i["level"] == "ERROR"]

    def warns(self):
        return [i for i in self.items if i["level"] == "WARN"]

    def ok(self):
        return not self.errors()

    def extend(self, other):
        self.items.extend(other.items)


def line_of(item):
    head = "[%s] %s" % (item["level"], item["gate"])
    if item["where"]:
        head += " " + item["where"]
    return "%s：%s" % (head, item["reason"])


# ---------------------------------------------------------------- 页稿准入

def squash_url(value):
    return re.sub(r"[\s\x00-\x20\x7f]+", "", value or "").lower()


def url_verdict(value):
    """None 表示安全，否则给一句中文说明。"""
    flat = squash_url(value)
    hit = DANGER_SCHEME.match(flat)
    if not hit:
        return None
    if hit.group(1) == "data" and DATA_IMAGE.match(flat):
        return None
    return "危险 URL 协议「%s:」" % hit.group(1)


def external_url_verdict(value, css=False):
    """None 表示没有外链字样，否则给一句中文说明。

    判据故意不按写法枚举：`url()`、`image-set()`、`cross-fade()`、`-webkit-image-set()`、
    `image()` 换个函数名就能绕开枚举，所以只认协议字样本身——属性值先做 HTML 实体解码
    （防 `&#92;` 藏反斜杠、`&sol;` 藏斜杠这类写法多裹一层），再压掉空白、统一小写、
    抠掉合法 data:image 的 base64 载荷之后，出现 `http:`、`https:` 或 `//`（协议相对，
    `http://` 与 `https://` 也都含它）即判外链。CSS 注释里的网址一样算：属性里没有
    写网址的正当理由，网址请写进正文文字。准入（G5）与成品复查（G9）用的是同一条。

    css=True 表示这是 CSS 上下文（style 属性值）：浏览器会把 `\\68\\74\\74\\70\\73`
    这类 CSS 转义解码成协议字样，协议判扫不到，所以解码后出现反斜杠一律拒收——
    教学页稿的合法 CSS 值用不到反斜杠转义，宁枉勿纵，不做完整 CSS 解析器。
    """
    decoded = htmllib.unescape(value or "")
    if css and "\\" in decoded:
        return "反斜杠转义（样式值经实体解码后不接受反斜杠转义）"
    flat = DATA_IMAGE_PAYLOAD.sub("data:image", squash_url(decoded))
    if "//" in flat or re.search(r"https?:", flat):
        return "外链字样（http://、https:// 或协议相对 //）"
    return None


def img_src_verdict(src, job, label="img 的 src"):
    """图片来源判据：只放 assets/ 下真实存在的本地文件与 data:image base64。

    style 里的 url() 走同一套判据——外链一旦从 CSS 溜进成品，投屏时就是一次对外请求。
    """
    value = (src or "").strip()
    if not value:
        return "%s 是空的" % label
    if squash_url(value).startswith("data:"):
        if not DATA_IMAGE.match(squash_url(value)):
            return "内嵌图片只许 data:image/(png|jpeg|gif|webp);base64"
        payload = value.split(",", 1)[1] if "," in value else ""
        if len(payload) * 3 // 4 > IMG_CAP:
            return "内嵌图片超过 %d MB" % (IMG_CAP // (1024 * 1024))
        return None
    if not value.startswith("assets/") or ".." in value or value.startswith("//"):
        return "%s 只许 assets/ 下的相对路径或 data:image base64，当前是：%s" % (label, value)
    if not os.path.isfile(job.path(value)):
        return "找不到图片文件：%s" % value
    return None


def hex_saturation(value):
    raw = value.lstrip("#").lower()
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    try:
        rgb = [int(raw[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except ValueError:
        return 0.0
    high, low = max(rgb), min(rgb)
    if high == low:
        return 0.0
    light = (high + low) / 2.0
    return (high - low) / (2.0 - high - low) if light > 0.5 else (high - low) / (high + low)


class _Scan(HTMLParser):
    """页稿准入的第二道：标签白名单、on* 事件、危险 URL、图片来源、空 figure。"""

    def __init__(self, job, where, rep):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.job, self.where, self.rep = job, where, rep
        self.figures = []
        self.carriers = 0
        self.hexes = []

    def _bad(self, reason):
        self.rep.bad("G5", self.where, reason)

    def handle_starttag(self, tag, attrs):
        name = tag.lower()
        if name not in SAFE_TAGS:
            self._bad("不许出现 <%s> 标签（不在白名单里）" % name)
            return
        if name in ACCENT_CARRIERS:
            self.carriers += 1
        if self.figures:
            self.figures[-1] += 1
        if name == "figure":
            self.figures.append(0)
        seen = set()
        for key, value in attrs:
            key = (key or "").lower()
            seen.add(key)
            if key.startswith("on"):
                self._bad("不许出现 on* 事件属性：%s" % key)
                continue
            if key in SHELL_DATA_ATTRS:
                self._bad("不许出现属性 %s：这是成品壳自己要写的标记，页稿里带上它会把壳的结构算乱"
                          % key)
                continue
            if key not in SAFE_ATTRS and not key.startswith("data-") and not key.startswith("aria-"):
                self._bad("不许出现属性 %s（不在白名单里）" % key)
                continue
            verdict = url_verdict(value)
            if verdict:
                self._bad("属性 %s 里出现%s" % (key, verdict))
            # 外链判据按协议字样判，不按 url()/image-set() 这类写法枚举（见 external_url_verdict）；
            # style 属性是 CSS 上下文，实体解码后出现反斜杠转义即拒收
            verdict = external_url_verdict(value, css=(key == "style"))
            if verdict:
                self._bad("属性 %s 里出现%s" % (key, verdict))
            if key == "class":
                for token in (value or "").split():
                    if token.lower() in SHELL_CLASSES:
                        self._bad("class 里不许用壳保留的类名 %s：成品壳的样式与翻页脚本按它认页，"
                                  "页稿用了就会多出一页假页，换个名字" % token)
            if key == "style":
                for inner in re.findall(r"url\(([^)]*)\)", value or "", re.IGNORECASE):
                    one = inner.strip().strip("\"'")
                    deeper = url_verdict(one)
                    if deeper:
                        self._bad("style 的 url() 里出现%s" % deeper)
                        continue
                    deeper = img_src_verdict(one, self.job, label="style 的 url()")
                    if deeper:
                        self._bad(deeper)
                if re.search(r"expression\s*\(", value or "", re.IGNORECASE):
                    self._bad("style 里不许出现 expression()")
                self.hexes.extend(HEX6.findall(value or ""))
            if name == "img" and key == "src":
                verdict = img_src_verdict(value, self.job)
                if verdict:
                    self._bad(verdict)
        if name == "img" and "src" not in seen:
            self._bad("img 缺 src")

    def handle_endtag(self, tag):
        if tag.lower() == "figure" and self.figures:
            if self.figures.pop() == 0:
                self._bad("空 figure：里面既没有图也没有说明文字")

    def handle_data(self, data):
        if self.figures and (data or "").strip():
            self.figures[-1] += 1


def scan_page_html(job, where, source, rep):
    """两道独立闸：先按原文做词法预扫，再按解析树查。返回 (载体标签数, style 里的 hex)。"""
    raw = source or ""
    for hit in set(m.group(1).lower() for m in RAW_BAD_TAG.finditer(raw)):
        rep.bad("G5", where, "不许出现 <%s> 标签（不在白名单里）" % hit)
    for name in ("script", "style"):
        opens = len(re.findall(r"<\s*%s\b" % name, raw, re.IGNORECASE))
        closes = len(re.findall(r"<\s*/\s*%s\s*>" % name, raw, re.IGNORECASE))
        if opens != closes:
            rep.bad("G5", where, "未闭合的 <%s>：成对块没配平" % name)
    for tag in re.finditer(r"<[^<>]*>", raw):
        if RAW_ON_ATTR.search(tag.group(0)):
            rep.bad("G5", where, "不许出现 on* 事件属性（`/` 分隔也算）：%s" % tag.group(0)[:60])
            break
    scan = _Scan(job, where, rep)
    try:
        scan.feed(raw)
        scan.close()
    except Exception as e:
        rep.bad("G5", where, "HTML 解析失败：%s" % e)
    hit = placeholder_hit(strip_tags(raw))
    if hit:
        rep.bad("G5", where, "正文里出现占位模式「%s」" % hit)
    return scan.carriers, scan.hexes


class _ExternalScan(HTMLParser):
    """成品侧外链复查：只看属性值，判据与页稿准入的 external_url_verdict 是同一条。"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.hits = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            low = (key or "").lower()
            verdict = external_url_verdict(value, css=(low == "style"))
            if verdict:
                self.hits.append((tag.lower(), low, verdict))


EMPTY_TAGS = frozenset(("img", "br", "hr", "col"))


def attr_ok(name):
    key = (name or "").lower()
    if key.startswith("on"):
        return False
    return key in SAFE_ATTRS or key.startswith("data-") or key.startswith("aria-")


class _Clean(HTMLParser):
    """消毒：重拼一份只含白名单标签与排版属性的 HTML，顺手把标签配平。

    准入闸已经把不干净的页拦在外面了，所以这一遍在正常流程里等于恒等变换；
    它真正防的是「一个没闭合的 div 把后面几页整个吞进去」这类版面事故。
    """

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.out = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        name = tag.lower()
        if name not in SAFE_TAGS:
            return
        kept = "".join(' %s="%s"' % (k.lower(), htmllib.escape(v or "", quote=True))
                       for k, v in attrs if attr_ok(k))
        self.out.append("<%s%s>" % (name, kept))
        if name not in EMPTY_TAGS:
            self.stack.append(name)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in EMPTY_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        name = tag.lower()
        if name in EMPTY_TAGS or name not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            self.out.append("</%s>" % top)
            if top == name:
                break

    def handle_data(self, data):
        self.out.append(htmllib.escape(data or "", quote=False))

    def result(self):
        while self.stack:
            self.out.append("</%s>" % self.stack.pop())
        return "".join(self.out)


def sanitize(source):
    clean = _Clean()
    clean.feed(source or "")
    clean.close()
    return clean.result()


def enforce_accent_var(source):
    """八个主题色定值（大小写不敏感）一律换回 var(--accent)，否则 repalette 空转。"""
    def swap(match):
        return "var(--accent)" if match.group(0).lower() in ACCENT_HEXES else match.group(0)
    return HEX6.sub(swap, source or "")


# ---------------------------------------------------------------- 壳

SLIDE_CSS = """*{box-sizing:border-box}
.slide{width:1280px;height:720px;background:#ffffff;position:relative;overflow:hidden;color:#16181d;\
font:20px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.pad{position:absolute;left:72px;top:56px;width:1136px;height:608px;overflow:hidden}
.fit{width:100%;transform-origin:top left;}
.slide h1{font-size:44px;line-height:1.25;margin:0 0 20px;color:var(--accent)}
.slide h2{font-size:30px;line-height:1.3;margin:20px 0 10px;color:var(--accent)}
.slide h2:first-child,.slide h1:first-child{margin-top:0}
.slide h3{font-size:24px;margin:16px 0 8px}
.slide p{margin:0 0 12px}
.slide ul,.slide ol{margin:0 0 12px;padding-left:1.4em}
.slide li{margin:0 0 6px}
.slide table{border-collapse:collapse;width:100%;margin:0 0 12px}
.slide th,.slide td{border:1px solid #d5d8de;padding:8px 12px;text-align:left}
.slide th{color:var(--accent);font-weight:600}
.slide blockquote{margin:0 0 12px;padding:6px 0 6px 18px;border-left:4px solid var(--accent);color:#4a5058}
.slide code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#f1f2f5;padding:1px 5px;border-radius:4px}
.slide pre{background:#f1f2f5;padding:12px 14px;border-radius:8px;white-space:pre-wrap;word-break:break-word}
.slide img{max-width:100%;height:auto}
.slide figure{margin:0 0 12px}
.slide figcaption{font-size:16px;color:#6b7280;margin-top:6px}
.slide hr{border:0;border-top:1px solid #d5d8de;margin:16px 0}
"""

PAGE_RULE = "@page{size:13.333in 7.5in;margin:0;}"

DECK_CSS_REST = SLIDE_CSS + """html,body{margin:0;padding:0;background:#101216;height:100%}
.stage{position:fixed;left:0;top:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;overflow:hidden}
.slide{flex:0 0 auto;transform-origin:center center;box-shadow:0 8px 40px rgba(0,0,0,.45)}
.rail{position:fixed;right:18px;bottom:14px;font:13px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:#7c828c;letter-spacing:.06em}
""" + PAGE_RULE + """
@media print{html,body{background:#ffffff}
.stage{position:static;display:block;overflow:visible}
.slide{display:block!important;transform:none!important;box-shadow:none;page-break-after:always;break-after:page;margin:0}
.rail{display:none}}
"""

NOTES_CSS_REST = SLIDE_CSS + """html,body{margin:0;padding:0;background:#f4f5f7;color:#16181d;\
font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:24px 20px 40px}
.hd{font-size:13px;letter-spacing:.1em;color:var(--accent);font-weight:700;margin:0 0 6px}
.sub{font-size:13px;color:#6b7280;margin:0 0 20px}
.row{display:flex;gap:22px;align-items:flex-start;background:#ffffff;border:1px solid #dfe2e8;\
border-radius:10px;padding:16px;margin:0 0 18px;page-break-inside:avoid;break-inside:avoid}
.thumb{width:480px;height:270px;flex:0 0 480px;overflow:hidden;border:1px solid #dfe2e8;border-radius:6px;background:#ffffff}
.thumb .slide{transform:scale(0.375);transform-origin:top left;box-shadow:none}
.talk{flex:1 1 auto;min-width:0}
.no{font-size:12px;color:#6b7280;margin:0 0 8px;letter-spacing:.04em}
.say{white-space:pre-wrap;word-break:break-word;margin:0}
""" + PAGE_RULE + """
@media print{html,body{background:#ffffff}.wrap{max-width:none;padding:0}
.row{border:0;border-bottom:1px solid #dfe2e8;border-radius:0;margin:0}}
"""

NAV_JS = """(function(){
var slides=[].slice.call(document.querySelectorAll('.slide'));
if(!slides.length){return;}
var at=0;
var stage=document.querySelector('.stage');
var rail=document.querySelector('.rail');
function inner(one){
var pad=one.querySelector('.pad');
var fit=one.querySelector('.fit');
if(!pad||!fit){return;}
fit.style.transform='none';
fit.style.width='100%';
var need=fit.scrollHeight;
var room=pad.clientHeight;
var k=(need>room&&need>0)?room/need:1;
if(k<0.5){k=0.5;}
if(k<1){fit.style.width=(100/k)+'%';fit.style.transform='scale('+k+')';}
}
function outer(){
if(!stage){return;}
var k=Math.min(stage.clientWidth/1280,stage.clientHeight/720);
if(k>1){k=1;}
for(var i=0;i<slides.length;i++){slides[i].style.transform='scale('+k+')';}
}
function show(n){
at=n<0?0:(n>=slides.length?slides.length-1:n);
for(var i=0;i<slides.length;i++){slides[i].style.display=(i===at)?'block':'none';}
inner(slides[at]);
outer();
if(rail){rail.textContent=(at+1)+' / '+slides.length;}
}
document.addEventListener('keydown',function(e){
var k=e.key;
if(k==='ArrowRight'||k==='ArrowDown'||k==='PageDown'||k===' '){show(at+1);e.preventDefault();}
else if(k==='ArrowLeft'||k==='ArrowUp'||k==='PageUp'){show(at-1);e.preventDefault();}
else if(k==='Home'){show(0);e.preventDefault();}
else if(k==='End'){show(slides.length-1);e.preventDefault();}
});
window.addEventListener('resize',function(){inner(slides[at]);outer();});
window.addEventListener('beforeprint',function(){
for(var i=0;i<slides.length;i++){slides[i].style.display='block';slides[i].style.transform='none';inner(slides[i]);}
});
window.addEventListener('afterprint',function(){show(at);});
show(0);
})();"""


def accent_line(accent):
    return ":root{--accent:%s;}" % accent


def render_slide(page_id, body, page_attr=True):
    tag = ' data-page-id="%s"' % esc(page_id) if page_attr else ""
    return ('<section class="slide"%s><div class="pad"><div class="fit">%s</div></div></section>'
            % (tag, body))


def render_deck(title, ready, accent):
    slides = "\n".join(render_slide(p["id"], p["body"]) for p in ready)
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>%s</title>\n<style>\n%s\n%s</style>\n</head>\n<body>\n"
            "<div class=\"stage\">\n%s\n</div>\n<div class=\"rail\"></div>\n"
            "<script>\n%s\n</script>\n</body>\n</html>\n"
            % (esc(title), accent_line(accent), DECK_CSS_REST, slides, NAV_JS))


def render_notes(title, ready, accent):
    rows = []
    total = len(ready)
    for i, page in enumerate(ready):
        label = page.get("title") or page["id"]
        rows.append('<div class="row" data-talk-id="%s"><div class="thumb">%s</div>'
                    '<div class="talk"><div class="no">%d / %d · %s · %s</div>'
                    '<p class="say">%s</p></div></div>'
                    % (esc(page["id"]), render_slide(page["id"], page["body"], page_attr=False),
                       i + 1, total, esc(page["id"]), esc(label), esc(page["notes"])))
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>%s · 教师讲稿</title>\n<style>\n%s\n%s</style>\n</head>\n<body>\n"
            "<div class=\"wrap\">\n<div class=\"hd\">教师讲稿 · 不投屏</div>\n"
            "<div class=\"sub\">%s · 共 %d 页 · 浏览器打印即可得 16:9 讲稿</div>\n%s\n</div>\n"
            "</body>\n</html>\n"
            % (esc(title), accent_line(accent), NOTES_CSS_REST, esc(title), total, "\n".join(rows)))


def verify_shell(deck, notes, ready_count, rep):
    """壳字符串自检：脚本自己先兜一遍，免得改壳时把契约改没了。"""
    for literal in ("width:1280px;height:720px", ".fit{width:100%;transform-origin:top left;}",
                    PAGE_RULE):
        if literal not in deck:
            rep.bad("G9", "deck.html", "壳字符串缺失：%s" % literal)
    if not re.search(r":root\{--accent:#[0-9a-f]{6};\}", deck):
        rep.bad("G9", "deck.html", "壳里没有 :root{--accent:#xxxxxx;} 这一行")
    if deck.count("<script") != 1:
        rep.bad("G9", "deck.html", "壳里的 <script 应恰好一次，实际 %d 次" % deck.count("<script"))
    if "<svg" in deck:
        rep.bad("G9", "deck.html", "壳里不许出现 <svg")
    if deck.count("data-page-id") != ready_count:
        rep.bad("G9", "deck.html", "data-page-id 数 %d 与成品页数 %d 对不上"
                % (deck.count("data-page-id"), ready_count))
    # 翻页脚本按 .slide 认页：多一个假页，rail 的页码与翻页顺序就全错
    if deck.count('class="slide"') != ready_count:
        rep.bad("G9", "deck.html", 'class="slide" 出现 %d 次，与成品页数 %d 对不上：'
                                   "有页稿把壳的结构名带进来了"
                % (deck.count('class="slide"'), ready_count))
    if PAGE_RULE not in notes:
        rep.bad("G9", "notes.html", "讲稿页缺打印 CSS")
    if "<script" in notes:
        rep.bad("G9", "notes.html", "讲稿页里不许有脚本")
    # 外链复查与页稿准入是同一条判据：属性值实体解码后出现协议字样（http://、https://、
    # 协议相对 //）即报，不按 src= 或 url( 的写法枚举——image-set()/cross-fade()
    # 换个函数名也一样抓；style 属性值里出现反斜杠转义同样拒收；合法的 data:image
    # 内嵌图不受影响。deck 与 notes 都查。
    for name, doc in (("deck.html", deck), ("notes.html", notes)):
        scan = _ExternalScan()
        try:
            scan.feed(doc)
            scan.close()
        except Exception as e:
            rep.bad("G9", name, "成品 HTML 解析失败：%s" % e)
        for tag, key, verdict in scan.hits:
            rep.bad("G9", name, "成品里不许有外链资源：<%s> 的 %s 属性里出现%s"
                    % (tag, key, verdict))


# ---------------------------------------------------------------- 工作区

class Job:
    """lessons/<slug>/ 的读写门面：脚本只碰这一个目录。"""

    def __init__(self, directory):
        self.dir = os.path.abspath(directory)
        if not os.path.isdir(self.dir):
            raise UsageError("课目录不存在：%s（先跑 lessonkit.py init <slug>）" % directory)
        self.slug = os.path.basename(self.dir.rstrip(os.sep)) or "lesson"

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def has(self, name):
        return os.path.isfile(self.path(name))

    def hash_of(self, name):
        return sha256_text(read_text_or_empty(self.path(name)))

    def page_ids(self):
        if not self.has("pages/index.json"):
            return []
        try:
            index = json.loads(read_text_or_empty(self.path("pages", "index.json")))
        except ValueError:
            return []
        out = []
        for row in as_list(index):
            pid = as_text(row.get("id")) if isinstance(row, dict) else ""
            if SLUG_RE.match(pid):
                out.append(pid)
        return out


def resolve(root, slug, strict=False):
    if not slug:
        raise UsageError("要给出课的 slug")
    if not strict and any(sep in slug for sep in ("/", "\\", os.sep)):
        return os.path.abspath(slug)
    check_slug(slug)
    return os.path.abspath(os.path.join(root or ".", "lessons", slug))


# ---------------------------------------------------------------- 盖章

def step_files(job, step):
    if step == "lesson":
        return ["lesson.json"]
    if step == "questions":
        return ["questions.json"]
    if step == "phases":
        return ["phases.json"]
    if step == "pages":
        names = ["pages/index.json"]
        for pid in job.page_ids():
            names.append("pages/%s.html" % pid)
            names.append("pages/%s.notes.md" % pid)
        return names
    return ["deck.html", "notes.html"]


def owner_of(name):
    if name.startswith("pages/"):
        return "pages"
    if name in ("deck.html", "notes.html"):
        return "deck"
    return os.path.splitext(name)[0]


def stamp_path(step):
    return os.path.join(".stamps", "%s.json" % step)


def read_stamp(job, step):
    if not job.has(stamp_path(step)):
        return None
    try:
        stamp = json.loads(read_text_or_empty(job.path(stamp_path(step))))
    except ValueError:
        return None
    return stamp if isinstance(stamp, dict) else None


def write_stamp(job, step, order, extra=None):
    names = []
    for name in order:
        for one in step_files(job, name):
            if one not in names:
                names.append(one)
    stamp = {"step": step, "at": now_iso(),
             "hashes": dict((n, job.hash_of(n)) for n in names)}
    if extra:
        stamp.update(extra)
    write_json(job.path(stamp_path(step)), stamp)
    return stamp


def drifted(job, stamp):
    """盖章之后被改过的文件名列表。"""
    stored = (stamp or {}).get("hashes") or {}
    return [n for n in sorted(stored) if stored.get(n) != job.hash_of(n)]


# ---------------------------------------------------------------- G1 课纲卡

def gate_lesson(job, rep):
    if not job.has("lesson.json"):
        rep.bad("G1", "lesson.json", "课纲卡不存在，先把 title / minutes / goals 或 keyPoints 填上")
        return None
    data = read_json(job.path("lesson.json"))
    if not isinstance(data, dict):
        rep.bad("G1", "lesson.json", "课纲卡必须是一个对象")
        return None

    if not as_text(data.get("title")):
        rep.bad("G1", "lesson.json", "title 不能为空")
    minutes = data.get("minutes")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0:
        rep.bad("G1", "lesson.json", "minutes 必须是正整数（课时分钟数），当前是：%r" % (minutes,))
    elif not (MINUTES_SOFT[0] <= minutes <= MINUTES_SOFT[1]):
        rep.warn("G1", "lesson.json", "minutes %d 不在 %d–%d 之间，确认一下是不是写错了"
                 % (minutes, MINUTES_SOFT[0], MINUTES_SOFT[1]))

    goals = [as_text(x) for x in as_list(data.get("goals")) if as_text(x)]
    keys = [as_text(x) for x in as_list(data.get("keyPoints")) if as_text(x)]
    if not goals and not keys:
        rep.bad("G1", "lesson.json", "goals 与 keyPoints 不能同时为空——没有出题依据，后面几步都不用跑了")

    route = as_text(data.get("route")) or ROUTES[0]
    if route not in ROUTES:
        rep.bad("G1", "lesson.json", "route 只能是 %s，当前是：%r" % (" 或 ".join(ROUTES), data.get("route")))
        route = ROUTES[0]

    language = data.get("language")
    if language is not None:
        if not isinstance(language, dict):
            rep.bad("G1", "lesson.json", "language 要么不写，要么是 {slides, notes} 对象")
        else:
            for key in language:
                if key not in ("slides", "notes"):
                    rep.warn("G1", "lesson.json", "language 里多了一个键 %r，脚本只认 slides 与 notes" % key)

    materials = data.get("materials")
    if materials is not None:
        if not isinstance(materials, list):
            rep.bad("G1", "lesson.json", "materials 要么不写，要么是数组")
        else:
            for i, item in enumerate(materials, 1):
                tag = "materials 第 %d 条" % i
                if not isinstance(item, dict) or not as_text(item.get("name")):
                    rep.bad("G1", "lesson.json", "%s 必须是带 name 的对象" % tag)
                    continue
                rel = as_text(item.get("path"))
                if rel:
                    if ".." in rel or rel.startswith("/"):
                        rep.bad("G1", "lesson.json", "%s 的 path 不许跳出课目录：%s" % (tag, rel))
                    elif not os.path.isfile(job.path(rel)) and \
                            not os.path.isfile(job.path("materials", rel)):
                        rep.bad("G1", "lesson.json", "%s 的 path 指向的文件不存在：%s" % (tag, rel))
                elif not as_text(item.get("excerpt")):
                    rep.bad("G1", "lesson.json", "%s 要么给 path，要么给 excerpt" % tag)

    return {"title": as_text(data.get("title")), "minutes": minutes if isinstance(minutes, int) else 0,
            "goals": goals, "keyPoints": keys, "route": route,
            "audience": as_text(data.get("audience")), "language": language or {}}


# ---------------------------------------------------------------- G2 作业

def ref_ok(ref, lesson):
    hit = re.match(r"^([gk])([0-9]+)$", ref or "")
    if not hit:
        return False
    pool = lesson["goals"] if hit.group(1) == "g" else lesson["keyPoints"]
    number = int(hit.group(2))
    return 1 <= number <= len(pool)


def gate_questions(job, rep, lesson):
    if not job.has("questions.json"):
        rep.bad("G2", "questions.json", "作业不存在：先出 %d–%d 道题，再规划阶段" % QUESTION_RANGE)
        return None
    data = read_json(job.path("questions.json"))
    if not isinstance(data, list):
        rep.bad("G2", "questions.json", "作业必须是数组")
        return None
    if not (QUESTION_RANGE[0] <= len(data) <= QUESTION_RANGE[1]):
        rep.bad("G2", "questions.json", "题目数量 %d 不在 %d–%d 之间" % ((len(data),) + QUESTION_RANGE))

    out, seen, kinds = [], set(), {}
    for i, item in enumerate(data, 1):
        tag = "第 %d 题" % i
        if not isinstance(item, dict):
            rep.bad("G2", "questions.json", "%s 不是对象" % tag)
            continue
        qid = as_text(item.get("id"))
        if not SLUG_RE.match(qid):
            rep.bad("G2", "questions.json", "%s 的 id 只能是小写字母、数字与连字符，当前是：%r" % (tag, item.get("id")))
            continue
        if qid in seen:
            rep.bad("G2", "questions.json", "id 重复：%s" % qid)
            continue
        seen.add(qid)
        tag = qid

        kind = as_text(item.get("kind"))
        if kind not in KINDS:
            rep.bad("G2", tag, "kind 只能是 %s，当前是：%r" % (" / ".join(KINDS), item.get("kind")))
        else:
            kinds[kind] = kinds.get(kind, 0) + 1

        prompt = as_text(item.get("prompt"))
        if text_len(prompt) < PROMPT_MIN:
            rep.bad("G2", tag, "prompt 至少 %d 字，当前 %d 字" % (PROMPT_MIN, text_len(prompt)))

        choices = [as_text(c) for c in as_list(item.get("choices"))]
        correct = as_list(item.get("correct"))
        if kind == "choice":
            if not (CHOICE_RANGE[0] <= len(choices) <= CHOICE_RANGE[1]):
                rep.bad("G2", tag, "choice 题的 choices 要 %d–%d 项，当前 %d 项"
                        % (CHOICE_RANGE[0], CHOICE_RANGE[1], len(choices)))
            if not correct:
                rep.bad("G2", tag, "choice 题的 correct 必须是非空下标数组")
            elif not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x < len(choices)
                         for x in correct):
                rep.bad("G2", tag, "choice 题的 correct 下标越界或不是整数：%r" % (correct,))
            elif len(set(correct)) >= len(choices):
                rep.bad("G2", tag, "choice 题的 correct 必须少于选项数，不然没得选")
        elif choices or correct:
            rep.warn("G2", tag, "%s 题不需要 choices / correct，批改线的字段还没对齐，先别带" % kind)

        focus = [as_text(x) for x in as_list(item.get("focus")) if as_text(x)]
        if len(focus) > FOCUS_CAP:
            rep.bad("G2", tag, "focus 最多 %d 条考点短语，当前 %d 条" % (FOCUS_CAP, len(focus)))

        targets = [as_text(x) for x in as_list(item.get("targets")) if as_text(x)]
        if not targets:
            rep.bad("G2", tag, "targets 不能为空：每道题都要挂在某条 goal 或 keyPoint 上")
        for ref in targets:
            if not ref_ok(ref, lesson):
                rep.bad("G2", tag, "targets 里的 %s 在课纲卡里不存在（要写成 g<序号> 或 k<序号>）" % ref)

        out.append({"id": qid, "kind": kind, "prompt": prompt, "choices": choices,
                    "correct": [x for x in correct if isinstance(x, int)], "focus": focus,
                    "targets": targets})

    for kind, count in sorted(kinds.items()):
        if count > KIND_CAP:
            rep.bad("G2", "questions.json", "%s 题 %d 道，超过每种 %d 道的上限" % (kind, count, KIND_CAP))

    for i in range(len(out)):
        for k in range(i + 1, len(out)):
            ratio = overlap_ratio(bigrams(out[i]["prompt"]), bigrams(out[k]["prompt"]))
            if ratio > DUP_PROMPT_RATIO:
                rep.warn("G2", "%s / %s" % (out[i]["id"], out[k]["id"]),
                         "两题 prompt 的 2-gram 重合率 %.2f 高于 %.2f，疑似重复题"
                         % (ratio, DUP_PROMPT_RATIO))

    hit_goals = set()
    for item in out:
        hit_goals.update(item["targets"])
    for i in range(1, len(lesson["goals"]) + 1):
        if ("g%d" % i) not in hit_goals:
            rep.warn("G2", "g%d" % i, "这条学习目标一道题都没考到：%s" % lesson["goals"][i - 1])
    return out


# ---------------------------------------------------------------- G4 阶段

def gate_phases(job, rep, lesson):
    if not job.has("phases.json"):
        rep.bad("G4", "phases.json", "阶段不存在：先规划 %d–%d 个阶段" % PHASE_SOFT)
        return None
    data = read_json(job.path("phases.json"))
    if not isinstance(data, list):
        rep.bad("G4", "phases.json", "阶段必须是数组")
        return None
    if len(data) > PHASE_HARD:
        rep.bad("G4", "phases.json", "阶段数 %d 超过上限 %d" % (len(data), PHASE_HARD))
    elif not (PHASE_SOFT[0] <= len(data) <= PHASE_SOFT[1]):
        rep.warn("G4", "phases.json", "阶段数 %d 不在 %d–%d 之间" % ((len(data),) + PHASE_SOFT))

    out, titles, minutes_sum, has_minutes = [], [], 0, False
    for i, item in enumerate(data, 1):
        tag = "第 %d 个阶段" % i
        if not isinstance(item, dict):
            rep.bad("G4", "phases.json", "%s 不是对象" % tag)
            continue
        title = as_text(item.get("title"))
        if not title:
            rep.bad("G4", "phases.json", "%s 的 title 不能为空" % tag)
            continue
        tag = title
        if title in titles:
            rep.bad("G4", "phases.json", "阶段标题必须两两不同，重复的是：%s" % title)
        titles.append(title)
        if NUM_PREFIX.match(title):
            rep.bad("G4", tag, "阶段标题不许带编号前缀（第一阶段 / Phase 1 / 1. / 一、/ Step 1 都算），"
                               "写纯阶段名就行")

        summary = as_text(item.get("summary"))
        if text_len(summary) < SUMMARY_MIN:
            rep.bad("G4", tag, "summary 至少 %d 字，当前 %d 字" % (SUMMARY_MIN, text_len(summary)))

        goals = [as_text(x) for x in as_list(item.get("goals")) if as_text(x)]
        if not goals:
            rep.bad("G4", tag, "goals 不能为空：每个阶段都要说清它在承接哪条学习目标")
        for ref in goals:
            if not ref_ok(ref, lesson):
                rep.bad("G4", tag, "goals 里的 %s 在课纲卡里不存在" % ref)

        goal_text = " ".join(lesson["goals"][int(r[1:]) - 1] for r in goals
                             if ref_ok(r, lesson) and r.startswith("g"))
        goal_text += " " + " ".join(lesson["keyPoints"][int(r[1:]) - 1] for r in goals
                                    if ref_ok(r, lesson) and r.startswith("k"))
        if goal_text.strip() and not (content_words(summary) & content_words(goal_text)):
            rep.warn("G4", tag, "summary 与它承接的目标零实词重合，看不出这一段在做什么")

        span = item.get("minutes")
        if span is not None:
            if not isinstance(span, int) or isinstance(span, bool) or span <= 0:
                rep.bad("G4", tag, "minutes 要么不写，要么是正整数，当前是：%r" % (span,))
            else:
                has_minutes = True
                minutes_sum += span
        out.append({"title": title, "summary": summary, "goals": goals, "minutes": span})

    if has_minutes and lesson["minutes"] > 0:
        drift = abs(minutes_sum - lesson["minutes"]) / float(lesson["minutes"])
        if drift > MINUTES_DRIFT:
            rep.warn("G4", "phases.json", "各阶段 minutes 之和 %d 与课时 %d 相差 %.0f%%，超过 %.0f%%"
                     % (minutes_sum, lesson["minutes"], drift * 100, MINUTES_DRIFT * 100))

    carried = set()
    for item in out:
        carried.update(item["goals"])
    for i in range(1, len(lesson["goals"]) + 1):
        if ("g%d" % i) not in carried:
            rep.bad("G4", "g%d" % i, "目标无阶段承接：%s" % lesson["goals"][i - 1])
    return out


# ---------------------------------------------------------------- G5–G7 页稿

def gate_pages(job, rep, lesson, questions, phases):
    if not job.has("pages/index.json"):
        rep.bad("G5", "pages/index.json", "页稿目录还没有 index.json")
        return None
    index = read_json(job.path("pages", "index.json"))
    if not isinstance(index, list):
        rep.bad("G5", "pages/index.json", "pages/index.json 必须是顺序数组")
        return None
    if len(index) > PAGE_HARD:
        rep.bad("G5", "pages/index.json", "页数 %d 超过上限 %d" % (len(index), PAGE_HARD))
    elif not (PAGE_SOFT[0] <= len(index) <= PAGE_SOFT[1]):
        rep.warn("G5", "pages/index.json", "页数 %d 不在 %d–%d 之间" % ((len(index),) + PAGE_SOFT))

    titles = [p["title"] for p in (phases or [])]
    qids = [q["id"] for q in (questions or [])]
    pages, seen = [], set()

    for i, row in enumerate(index, 1):
        tag = "第 %d 页" % i
        if not isinstance(row, dict):
            rep.bad("G5", "pages/index.json", "%s 不是对象" % tag)
            continue
        pid = as_text(row.get("id"))
        if not SLUG_RE.match(pid):
            rep.bad("G5", "pages/index.json", "%s 的 id 只能是小写字母、数字与连字符，当前是：%r"
                    % (tag, row.get("id")))
            continue
        if pid in seen:
            rep.bad("G5", "pages/index.json", "页 id 重复：%s" % pid)
            continue
        seen.add(pid)

        phase = as_text(row.get("phase"))
        if phases is not None and phase not in titles:
            rep.bad("G5", pid, "phase 指向了一个不存在的阶段：%s" % (phase or "（空）"))

        covers = [as_text(x) for x in as_list(row.get("covers")) if as_text(x)]
        if len(covers) > COVERS_CAP:
            rep.bad("G5", pid, "单页最多覆盖 %d 道题，这一页写了 %d 道：%s"
                    % (COVERS_CAP, len(covers), "、".join(covers)))
        for ref in covers:
            if ref.startswith("drill:"):
                if not DRILL_RE.match(ref):
                    rep.bad("G5", pid, "编程题引用要写成 drill:<slug>，当前是：%s" % ref)
            elif questions is not None and ref not in qids:
                rep.bad("G5", pid, "covers 里的 %s 在作业里不存在" % ref)

        html_rel = "pages/%s.html" % pid
        notes_rel = "pages/%s.notes.md" % pid
        if not job.has(html_rel):
            rep.bad("G5", pid, "缺正文文件 %s" % html_rel)
            continue
        if not job.has(notes_rel):
            rep.bad("G6", pid, "缺讲稿文件 %s" % notes_rel)
            continue

        source = read_text_or_empty(job.path(html_rel))
        talk = read_text_or_empty(job.path(notes_rel))
        carriers, hexes = scan_page_html(job, pid, source, rep)
        body_text = strip_tags(source)
        body_len = text_len(body_text)
        if body_len > DENSITY_HARD:
            rep.bad("G5", pid, "正文密度过高：去标签 %d 字，超过 %d 字的硬上限（内容区 1136×608、"
                               "20px×1.6 行高约 19 行 × 56 字）" % (body_len, DENSITY_HARD))
        elif body_len > DENSITY_WARN:
            rep.warn("G5", pid, "正文密度偏高：去标签 %d 字，超过 %d 字就要靠缩放才装得下"
                     % (body_len, DENSITY_WARN))

        talk_len = text_len(talk)
        if not talk.strip():
            rep.bad("G6", pid, "讲稿是空的：投屏正文与教师讲稿必须双非空")
        else:
            if NOTES_HTML.search(talk):
                rep.bad("G6", pid, "讲稿里不许出现 HTML 标签，讲稿是给人念的纯文本")
            hit = placeholder_hit(talk)
            if hit:
                rep.bad("G6", pid, "讲稿里出现占位模式「%s」" % hit)
            if talk_len < body_len:
                rep.bad("G6", pid, "讲稿字数少于本页正文：讲稿 %d 字，正文 %d 字" % (talk_len, body_len))
            ratio = overlap_ratio(bigrams(talk), bigrams(body_text))
            if ratio > COPY_RATIO:
                rep.bad("G6", pid, "抄正文当讲稿：与本页正文的 2-gram 重合率 %.2f 高于 %.2f"
                        % (ratio, COPY_RATIO))

        pages.append({"id": pid, "phase": phase, "covers": covers,
                      "title": as_text(row.get("title")), "html": source, "notes": talk,
                      "bodyText": body_text, "bodyLen": body_len, "talkLen": talk_len,
                      "carriers": carriers, "hexes": hexes,
                      "words": content_words(body_text + "\n" + talk)})

    if phases is not None:
        used = set(p["phase"] for p in pages)
        for title in titles:
            if title not in used:
                rep.bad("G5", title, "这个阶段一页都没有：每个阶段至少要有一页")

    total_talk = sum(p["talkLen"] for p in pages)
    need = lesson["minutes"] * TALK_PER_MINUTE
    if pages and total_talk < need:
        rep.bad("G6", "notes", "全课讲稿字数 %d 不足 minutes×%d = %d（口径：语速 150 字/分的四成，"
                               "余下留给活动与问答）" % (total_talk, TALK_PER_MINUTE, need))

    coverage = cover_matrix(pages, questions, rep)
    return {"pages": pages, "coverage": coverage, "totalTalk": total_talk, "talkNeed": need}


def cover_matrix(pages, questions, rep):
    """G7：拿题干实词去每页正文＋讲稿里对照，不看模型自报的标签。"""
    grid, declared = {}, {}
    if questions is None:
        return {"grid": grid, "declared": declared, "cols": [p["id"] for p in pages],
                "rows": [], "checked": False}
    for item in questions:
        qid = item["id"]
        want = content_words(item["prompt"])
        grid[qid] = dict((p["id"], len(want & p["words"])) for p in pages)
        mine = [p for p in pages if qid in p["covers"]]
        declared[qid] = [p["id"] for p in mine]
        if not mine:
            rep.bad("G7", qid, "没有任何一页覆盖这道题：把它写进某一页的 covers，或者删掉这道题")
            continue
        best = max(grid[qid][p["id"]] for p in mine)
        if best < OVERLAP_MIN:
            rep.bad("G7", qid, "页里没讲到这道题：题干实词与覆盖页（%s）的正文＋讲稿最多只重合 %d 个，"
                               "下限 %d（口径：中文去高频虚词后 2-gram，英文小写去 stopwords，去数字与标点）"
                    % ("、".join(declared[qid]), best, OVERLAP_MIN))
        if item["kind"] == "choice" and item["correct"]:
            right = " ".join(item["choices"][x] for x in item["correct"] if x < len(item["choices"]))
            want_right = content_words(right)
            if want_right and not any(want_right & p["words"] for p in mine):
                rep.warn("G7", qid, "正确项「%s」的实词在覆盖页里一个都找不到，学生照这几页答不出来" % right)
    return {"grid": grid, "declared": declared, "cols": [p["id"] for p in pages],
            "rows": [q["id"] for q in questions], "checked": True}


# ---------------------------------------------------------------- 流水线

def route_order(lesson, want=None):
    """这次按什么顺序跑。

    homework-first 是一条直链：课纲卡 → 作业 → 阶段 → 页稿。
    content-first 把出题从主链上摘下来单挂在课纲卡后面（链变成 课纲卡 → 阶段 → 页稿），
    出题在 build 之前作为收尾步强制补上。这样一来，无论 questions.json 是先有还是后有，
    每一步的上游都是固定的，盖章记什么文件也就不会随手气变。
    """
    if lesson["route"] == ROUTES[0]:
        return list(STEPS)
    if want == "questions":
        return ["lesson", "questions"]
    return ["lesson", "phases", "pages"]


def stamp_order(lesson, step):
    """给某一步盖章时，要一起记下哈希的那串文件属于哪几步。"""
    chain = route_order(lesson, want=step)
    return chain[:chain.index(step) + 1] if step in chain else ["lesson", step]


LOCK_TAIL = {
    "questions": "先交课纲卡，再出作业：请先跑 lessonkit.py check <slug> lesson",
    "phases-hw": "先出作业，再规划阶段：请先跑 lessonkit.py check <slug> questions",
    "phases-cf": "先交课纲卡，再规划阶段：请先跑 lessonkit.py check <slug> lesson",
    "pages": "先规划阶段，再写页稿：请先跑 lessonkit.py check <slug> phases",
    "build": "没有一页过验收，不许出成品：请先跑 lessonkit.py check <slug> pages",
    "build-cf": "出题只能后置，不能跳过：build 之前必须先跑 lessonkit.py check <slug> questions",
}


def lock_key(step, route):
    if step == "phases":
        return "phases-hw" if route == ROUTES[0] else "phases-cf"
    return step


def guard(job, rep, step, order, route):
    """三把锁：上游盖章不在就退 2（锁住），盖章在但上游改过就判死（作废）。"""
    where = order.index(step)
    if where == 0:
        return
    previous = order[where - 1]
    stamp = read_stamp(job, previous)
    if stamp is None:
        raise LockError(LOCK_TAIL[lock_key(step, route)])
    for name in drifted(job, stamp):
        rep.bad("G10", name, "%s 已改动，请从 check %s 重新验收" % (name, owner_of(name)))


def evaluate(job, upto):
    """按路线跑到 upto，返回 (data, rep, order)。

    顺序刻意是「先验锁、再对哈希、最后才跑闸门」：没出作业就想规划阶段，
    该看到的是那句锁的话，而不是一串「作业不存在」。
    """
    rep = Rep()
    data = {"lesson": None, "questions": None, "phases": None, "pages": None}
    lesson = gate_lesson(job, rep)
    data["lesson"] = lesson
    if lesson is None:
        return data, rep, ["lesson"]
    order = stamp_order(lesson, upto)
    guard(job, rep, upto, order, lesson["route"])
    if not rep.ok():
        return data, rep, order
    # content-first 的作业不在主链上，但覆盖闸要用它：能读出一份合规的就静默读进来，
    # 读不出来就当没有——真正的把关放在 check questions 与 build 之前那道收尾步。
    if lesson["route"] == ROUTES[1] and "questions" not in order and job.has("questions.json"):
        quiet = Rep()
        parsed = gate_questions(job, quiet, lesson)
        data["questions"] = parsed if quiet.ok() else None
    for step in order[1:]:
        if step == "questions":
            data["questions"] = gate_questions(job, rep, lesson)
        elif step == "phases":
            data["phases"] = gate_phases(job, rep, lesson)
        else:
            data["pages"] = gate_pages(job, rep, lesson, data["questions"], data["phases"])
        if not rep.ok():
            break
    return data, rep, order


# ---------------------------------------------------------------- 成品对账

def deck_state(job):
    """返回 (状态, 说明)。状态 ∈ none / ok / bad。"""
    stamp = read_stamp(job, "deck")
    exists = job.has("deck.html") or job.has("notes.html")
    if stamp is None:
        if exists:
            return "bad", "成品不是由 build 生成或生成后被手改：没有 .stamps/deck.json 这张盖章"
        return "none", "还没有出成品"
    if not job.has("deck.html") or not job.has("notes.html"):
        return "bad", "成品不是由 build 生成或生成后被手改：盖章在，成品文件却不见了"
    changed = drifted(job, stamp)
    made = [n for n in changed if n in ("deck.html", "notes.html")]
    if made:
        return "bad", "成品不是由 build 生成或生成后被手改：%s 的哈希与盖章对不上" % "、".join(made)
    if changed:
        return "bad", "%s 已改动，请从 build 重新出成品" % "、".join(changed)
    return "ok", "成品与页稿一致，盖章时间 %s" % stamp.get("at", "?")


# ---------------------------------------------------------------- 报告数据

STEP_LABEL = {"lesson": "1 课纲卡", "questions": "2 出作业", "phases": "3 规划阶段", "pages": "4 写页稿"}
LOCK_LABEL = (
    ("questions", "没出作业，不许规划阶段"),
    ("phases", "没规划阶段，不许写页稿"),
    ("pages", "没有一页过验收，不许出成品"),
)


def collect(job):
    """报告与 --all 共用的一次完整体检（不写盖章）。

    撞上锁不算错，正好是报告要画出来的东西：所以这里把 LockError 收下来，
    照样渲染四步状态条与三把锁，而不是让 report 直接退 2。
    """
    locked = ""
    try:
        data, rep, order = evaluate(job, "pages")
    except LockError as e:
        locked = str(e)
        data, rep, order = evaluate(job, "lesson")
    lesson = data["lesson"] or {"title": job.slug, "minutes": 0, "goals": [], "keyPoints": [],
                                "route": ROUTES[0], "audience": "", "language": {}}
    by_step = {}
    for name in STEPS:
        if name not in order:
            by_step[name] = ("todo", locked or "还没跑到") if locked else ("skip", "这条路线不走这一步")
        elif data.get(name) is None and name != "lesson":
            by_step[name] = ("todo", "还没跑到")
        else:
            hits = [i for i in rep.errors() if i["gate"] in STEP_GATES.get(name, ())]
            by_step[name] = ("bad", "%d 个 ERROR" % len(hits)) if hits else ("ok", "通过")
    if data["lesson"] is None:
        by_step["lesson"] = ("bad", "课纲卡不过")

    locks = []
    cf = lesson["route"] == ROUTES[1]
    for step, label in LOCK_LABEL:
        if step == "questions" and cf:
            label = "没出作业，不许出成品（content-first 把出题后置到 build 之前）"
        stamp = read_stamp(job, step)
        if stamp is None:
            tail = LOCK_TAIL["build-cf"] if (step == "questions" and cf) else LOCK_TAIL[
                lock_key({"questions": "phases", "phases": "pages", "pages": "build"}[step],
                         lesson["route"])]
            locks.append({"name": label, "state": "closed", "lockReason": tail})
        else:
            drift = drifted(job, stamp)
            if drift:
                locks.append({"name": label, "state": "closed",
                              "lockReason": "%s 已改动，请从 check %s 重新验收"
                                            % (drift[0], owner_of(drift[0]))})
            else:
                locks.append({"name": label, "state": "open", "lockReason": ""})

    state, reason = deck_state(job)
    stamp = read_stamp(job, "deck") or {}
    return {"slug": job.slug, "at": now_iso(), "lesson": lesson, "steps": by_step,
            "locks": locks, "items": rep.items, "data": data,
            "deck": {"state": state, "reason": reason,
                     "palette": stamp.get("palette", DEFAULT_PALETTE),
                     "failedPages": stamp.get("failedPages", [])}}


STEP_GATES = {"lesson": ("G1",), "questions": ("G2",), "phases": ("G4",),
              "pages": ("G5", "G6", "G7", "G10")}


# ---------------------------------------------------------------- 报告渲染

MARK = {"ok": "✓", "bad": "✗", "todo": "…", "skip": "—", "none": "—"}
G0_NOTE = ("G0 分类声明：机器真值 = 结构校验、哈希盖章、页稿准入、壳字符串、逐字节 diff、静态闸；"
           "文本启发式 = 讲稿字数下限、题↔页实词重合、密度阈值、非中性色；"
           "仍靠老师确认 = 题目对不对、阶段合不合理、讲稿能不能照讲。")


def bar(value, need, width=20):
    if need <= 0:
        return "—"
    filled = max(0, min(width, int(round(value * width / float(need)))))
    return "█" * filled + "·" * (width - filled)


def report_md(snap):
    lesson = snap["lesson"]
    out = ["# %s · 备课报告" % (lesson["title"] or snap["slug"]), ""]
    out.append("课号 %s ｜ 课时 %d 分钟 ｜ 路线 %s ｜ 配色 %s ｜ 生成于 %s"
               % (snap["slug"], lesson["minutes"], lesson["route"],
                  snap["deck"]["palette"], snap["at"]))
    out.append("")
    if lesson["route"] == ROUTES[1]:
        out += ["> 未先出作业：本课走的是 content-first 路线，出题被后置到 build 之前，"
                "不是免除。", ""]

    out += ["## 四步状态条", "", "| 步骤 | 状态 | 说明 |", "| --- | --- | --- |"]
    for name in STEPS:
        state, note = snap["steps"][name]
        out.append("| %s | %s | %s |" % (STEP_LABEL[name], MARK[state], note))
    state = snap["deck"]["state"]
    out.append("| 5 成品对账 | %s | %s |" % (MARK.get(state, "—"), snap["deck"]["reason"]))
    out.append("")

    out += ["## 三把锁", ""]
    for lock in snap["locks"]:
        if lock["state"] == "open":
            out.append("- %s：已解锁" % lock["name"])
        else:
            out.append("- %s：**锁住** —— %s" % (lock["name"], lock["lockReason"]))
    out.append("")

    pack = snap["data"].get("pages")
    cov = (pack or {}).get("coverage") or {}
    out += ["## 题↔页覆盖矩阵", ""]
    if cov.get("checked") and cov.get("rows"):
        heads = cov["cols"]
        out.append("| 题 | " + " | ".join(heads) + " |")
        out.append("| --- |" + " --- |" * len(heads))
        for qid in cov["rows"]:
            cells = []
            for pid in heads:
                count = cov["grid"].get(qid, {}).get(pid, 0)
                cells.append(("**%d**" % count) if pid in cov["declared"].get(qid, []) else str(count))
            out.append("| %s | %s |" % (qid, " | ".join(cells)))
        out += ["", "格里是题干实词与该页正文＋讲稿的重合数，**加粗**表示这一页的 covers 里声明了这道题；"
                    "下限 %d。实词口径：中文去高频虚词后取 2-gram，英文小写去 stopwords，"
                    "数字与标点丢掉。" % OVERLAP_MIN]
    else:
        out.append("（作业还没过验收，覆盖矩阵先空着）")
    out.append("")

    out += ["## 目标↔阶段", "", "| 学习目标 | 承接阶段 |", "| --- | --- |"]
    phases = snap["data"].get("phases") or []
    for i, goal in enumerate(lesson["goals"], 1):
        carried = [p["title"] for p in phases if ("g%d" % i) in p["goals"]]
        out.append("| g%d %s | %s |" % (i, goal, "、".join(carried) if carried else "**无阶段承接**"))
    for i, key in enumerate(lesson["keyPoints"], 1):
        carried = [p["title"] for p in phases if ("k%d" % i) in p["goals"]]
        out.append("| k%d %s | %s |" % (i, key, "、".join(carried) if carried else "—"))
    out.append("")

    out += ["## 讲稿字数与正文密度", "", "| 页 | 阶段 | 正文字数 | 讲稿字数 | 讲稿条 |", "| --- | --- | --- | --- | --- |"]
    for page in (pack or {}).get("pages", []):
        out.append("| %s | %s | %d | %d | %s |"
                   % (page["id"], page["phase"], page["bodyLen"], page["talkLen"],
                      bar(page["talkLen"], max(page["bodyLen"], 1) * 2)))
    if pack:
        out += ["", "全课讲稿 %d 字，下限 minutes×%d = %d 字；讲稿条走到一半就是该页的下限"
                "（＝这一页的正文字数），走满是两倍。"
                % (pack["totalTalk"], TALK_PER_MINUTE, pack["talkNeed"])]
    out.append("")

    out += ["## 失败页", ""]
    failed = snap["deck"]["failedPages"]
    out += (["- %s：%s" % (f["page"], f["failReason"]) for f in failed] if failed else ["无"])
    out.append("")

    out += ["## 逐条结果", ""]
    if snap["items"]:
        out += ["- " + line_of(i) for i in snap["items"]]
    else:
        out.append("0 ERROR / 0 WARN。")
    out += ["", "---", "", G0_NOTE, ""]
    return "\n".join(out)


REPORT_CSS = """
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#ffffff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de;
--ok:#1a7f37;--okbg:#dafbe1;--bad:#cf222e;--badbg:#ffebe9;--warn:#9a6700;--warnbg:#fff8c5;--tint:#0969da}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--fg:#e6edf3;--muted:#8b949e;--line:#30363d;
--ok:#3fb950;--okbg:#12261e;--bad:#f85149;--badbg:#2d1416;--warn:#d29922;--warnbg:#272115;--tint:#58a6ff}}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.card{max-width:980px;margin:0 auto;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px 28px}
h1{font-size:21px;margin:0 0 4px}h2{font-size:16px;margin:26px 0 10px}.meta{color:var(--muted);font-size:13px}
.flow{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.pill{border:1px solid var(--line);border-radius:999px;padding:5px 14px;font-size:13px;font-weight:600}
.pill.ok{background:var(--okbg);color:var(--ok)}.pill.bad{background:var(--badbg);color:var(--bad)}
.pill.todo,.pill.skip,.pill.none{color:var(--muted)}
.lock{border:1px solid var(--line);border-left:4px solid var(--bad);border-radius:8px;padding:10px 14px;margin:0 0 8px}
.lock.open{border-left-color:var(--ok)}.lock b{font-size:14px}.lock .why{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:0 0 6px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12.5px}
td.n{text-align:center;font-variant-numeric:tabular-nums;color:var(--muted)}
td.n.hit{color:var(--fg);font-weight:700;background:var(--okbg)}
td.n.miss{color:var(--bad);font-weight:700;background:var(--badbg)}
.bar{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:-1px;color:var(--tint)}
ul{padding-left:20px;margin:6px 0}li{margin:2px 0}
.tag{display:inline-block;min-width:52px;padding:1px 7px;border-radius:5px;font-size:12px;font-weight:700;margin-right:6px}
.tag.bad{background:var(--badbg);color:var(--bad)}.tag.warn{background:var(--warnbg);color:var(--warn)}
.note{color:var(--muted);font-size:12.5px;margin:8px 0 0}
.none{color:var(--muted)}
"""


def report_html(snap):
    lesson = snap["lesson"]
    pack = snap["data"].get("pages")
    cov = (pack or {}).get("coverage") or {}
    parts = ['<div class="card">', "<h1>%s · 备课报告</h1>" % esc(lesson["title"] or snap["slug"]),
             '<div class="meta">课号 %s ｜ 课时 %d 分钟 ｜ 路线 %s ｜ 配色 %s ｜ 生成于 %s</div>'
             % (esc(snap["slug"]), lesson["minutes"], esc(lesson["route"]),
                esc(snap["deck"]["palette"]), esc(snap["at"]))]
    if lesson["route"] == ROUTES[1]:
        parts.append('<p class="note">未先出作业：本课走的是 content-first 路线，'
                     '出题被后置到 build 之前，不是免除。</p>')

    parts.append("<h2>四步状态条</h2><div class=\"flow\">")
    for name in STEPS:
        state, note = snap["steps"][name]
        parts.append('<span class="pill %s">%s %s</span>' % (state, MARK[state], esc(STEP_LABEL[name])))
    parts.append('<span class="pill %s">%s 5 成品对账</span></div>' %
                 (snap["deck"]["state"], MARK.get(snap["deck"]["state"], "—")))
    parts.append('<p class="note">%s</p>' % esc(snap["deck"]["reason"]))

    parts.append("<h2>三把锁</h2>")
    for lock in snap["locks"]:
        opened = lock["state"] == "open"
        parts.append('<div class="lock %s"><b>%s</b><div class="why">%s</div></div>'
                     % ("open" if opened else "", esc(lock["name"]),
                        "已解锁" if opened else esc(lock["lockReason"])))

    parts.append("<h2>题↔页覆盖矩阵</h2>")
    if cov.get("checked") and cov.get("rows"):
        head = "".join("<th>%s</th>" % esc(p) for p in cov["cols"])
        rows = []
        for qid in cov["rows"]:
            cells = []
            for pid in cov["cols"]:
                count = cov["grid"].get(qid, {}).get(pid, 0)
                if pid in cov["declared"].get(qid, []):
                    kind = "hit" if count >= OVERLAP_MIN else "miss"
                else:
                    kind = ""
                cells.append('<td class="n %s">%d</td>' % (kind, count))
            rows.append("<tr><td>%s</td>%s</tr>" % (esc(qid), "".join(cells)))
        parts.append("<table><thead><tr><th>题</th>%s</tr></thead><tbody>%s</tbody></table>"
                     % (head, "".join(rows)))
        parts.append('<p class="note">格里是题干实词与该页正文＋讲稿的重合数；有底色的格子是 covers 里'
                     '声明过的，绿=达到下限 %d，红=没讲到。实词口径：中文去高频虚词后取 2-gram，'
                     '英文小写去 stopwords，数字与标点丢掉。</p>' % OVERLAP_MIN)
    else:
        parts.append('<p class="none">作业还没过验收，覆盖矩阵先空着。</p>')

    parts.append("<h2>目标↔阶段</h2><table><thead><tr><th>学习目标</th><th>承接阶段</th></tr></thead><tbody>")
    phases = snap["data"].get("phases") or []
    for i, goal in enumerate(lesson["goals"], 1):
        carried = [p["title"] for p in phases if ("g%d" % i) in p["goals"]]
        parts.append("<tr><td>g%d %s</td><td>%s</td></tr>"
                     % (i, esc(goal), esc("、".join(carried)) if carried else "<b>无阶段承接</b>"))
    for i, key in enumerate(lesson["keyPoints"], 1):
        carried = [p["title"] for p in phases if ("k%d" % i) in p["goals"]]
        parts.append("<tr><td>k%d %s</td><td>%s</td></tr>"
                     % (i, esc(key), esc("、".join(carried)) if carried else "—"))
    parts.append("</tbody></table>")

    parts.append("<h2>讲稿字数与正文密度</h2><table><thead><tr><th>页</th><th>阶段</th>"
                 "<th>正文字数</th><th>讲稿字数</th><th>讲稿条</th></tr></thead><tbody>")
    for page in (pack or {}).get("pages", []):
        parts.append('<tr><td>%s</td><td>%s</td><td class="n">%d</td><td class="n">%d</td>'
                     '<td class="bar">%s</td></tr>'
                     % (esc(page["id"]), esc(page["phase"]), page["bodyLen"], page["talkLen"],
                        esc(bar(page["talkLen"], max(page["bodyLen"], 1) * 2))))
    parts.append("</tbody></table>")
    if pack:
        parts.append('<p class="note">全课讲稿 %d 字，下限 minutes×%d = %d 字；讲稿条走到一半'
                     '就是该页的下限（＝这一页的正文字数），走满是两倍。</p>'
                     % (pack["totalTalk"], TALK_PER_MINUTE, pack["talkNeed"]))

    parts.append("<h2>失败页</h2>")
    failed = snap["deck"]["failedPages"]
    if failed:
        parts.append("<ul>" + "".join("<li>%s：%s</li>" % (esc(f["page"]), esc(f["failReason"]))
                                      for f in failed) + "</ul>")
    else:
        parts.append('<p class="none">无</p>')

    parts.append("<h2>逐条结果</h2>")
    if snap["items"]:
        rows = []
        for item in snap["items"]:
            where = (" " + esc(item["where"])) if item["where"] else ""
            rows.append('<li><span class="tag %s">%s</span>%s%s：%s</li>'
                        % ("bad" if item["level"] == "ERROR" else "warn", item["level"],
                           esc(item["gate"]), where, esc(item["reason"])))
        parts.append("<ul>" + "".join(rows) + "</ul>")
    else:
        parts.append('<p class="none">0 ERROR / 0 WARN。</p>')

    parts.append('<p class="note">%s</p></div>' % esc(G0_NOTE))
    return ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>%s · 备课报告</title><style>%s</style></head><body>%s</body></html>\n"
            % (esc(lesson["title"] or snap["slug"]), REPORT_CSS, "".join(parts)))


# ---------------------------------------------------------------- 子命令

def emit(rep, head):
    for item in rep.items:
        print(line_of(item))
    bad, soft = len(rep.errors()), len(rep.warns())
    print("%s：%d ERROR / %d WARN" % (head, bad, soft))
    return 1 if bad else 0


def cmd_doctor(args):
    ok = sys.version_info >= MIN_PY
    print("[%s] Python %d.%d.%d（下限 %d.%d，只用标准库，无第三方依赖）"
          % ("OK" if ok else "缺失", sys.version_info[0], sys.version_info[1],
             sys.version_info[2], MIN_PY[0], MIN_PY[1]))
    print("[OK] 壳：1280×720、两级等比缩放（最小 0.5）、方向键翻页、打印 13.333in × 7.5in")
    print("[OK] 主题色：%s（未知 key 回落 %s）" % ("、".join(k for k, _ in PALETTES), DEFAULT_PALETTE))
    workspace = os.path.abspath(os.path.join(args.root or ".", "lessons"))
    print("[%s] 工作区 lessons/ %s" % ("OK" if os.path.isdir(workspace) else "提示",
                                       "已存在" if os.path.isdir(workspace) else "还没建，init 时会自动建"))
    hits = hygiene(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for line in hits:
        print("[ERROR] 发布卫生：%s" % line)
    print("[%s] 发布卫生：%d 处要改" % ("OK" if not hits else "ERROR", len(hits)))
    return 0 if (ok and not hits) else 1


HYGIENE_EXT = (".py", ".md", ".json", ".html", ".css", ".js", ".txt", ".yml", ".yaml")
LOCAL_PATH = ("/" + "Users" + "/", "/" + "home" + "/", "C:" + "\\Users" + "\\")


def hygiene(skill_dir):
    """G14 的脚本侧：对外发布的文件里不许留本机绝对路径与外链资源。"""
    hits = []
    for here, dirs, files in os.walk(skill_dir):
        dirs[:] = [d for d in sorted(dirs) if d not in ("__pycache__", ".git", "node_modules")]
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() not in HYGIENE_EXT:
                continue
            rel = os.path.relpath(os.path.join(here, name), skill_dir).replace(os.sep, "/")
            text = read_text_or_empty(os.path.join(here, name))
            for needle in LOCAL_PATH:
                if needle in text:
                    hits.append("%s 里出现本机绝对路径「%s」" % (rel, needle))
    return hits


SKELETON_NOTE = "把这份骨架填成真的课纲卡，再跑 check <slug> lesson；goals 与 keyPoints 不能同时为空。"


def cmd_init(args):
    directory = resolve(args.root, args.slug, strict=True)
    if os.path.exists(directory) and os.listdir(directory):
        raise UsageError("目录已经有东西了，不覆盖：%s" % directory)
    for sub in ("pages", "assets", "materials", ".stamps"):
        os.makedirs(os.path.join(directory, sub), exist_ok=True)
    write_json(os.path.join(directory, "lesson.json"), {
        "title": "", "minutes": 45, "goals": [], "keyPoints": [],
        "audience": "", "materials": [], "route": args.route,
        "language": {"slides": "", "notes": ""},
    })
    print("已建课目录：%s" % directory)
    print("路线：%s%s" % (args.route, "（出题后置，build 之前必须补上）" if args.route == ROUTES[1] else ""))
    print(SKELETON_NOTE)
    return 0


def cmd_check(args):
    job = Job(resolve(args.root, args.slug))
    if args.all:
        return check_all(job)
    step = args.step
    if step not in STEPS:
        raise UsageError("check 的第二个参数只能是 %s，或者用 --all" % " / ".join(STEPS))
    data, rep, order = evaluate(job, step)
    if rep.ok():
        write_stamp(job, step, order)
        print("已盖章 %s" % stamp_path(step))
    if step == "pages" and data["lesson"] and data["lesson"]["route"] == ROUTES[1]:
        print("未先出作业：content-first 路线的覆盖闸推迟到 build 之前，出题不能跳过。")
    return emit(rep, "check %s" % step)


def check_all(job):
    rep = Rep()
    lesson = gate_lesson(job, rep)
    if lesson is None:
        return emit(rep, "check --all")
    order = route_order(lesson)
    if lesson["route"] == ROUTES[1] and job.has("questions.json"):
        order = ["lesson", "questions"] + order[1:]   # 后置的出题也要一起复核
    if rep.ok():
        write_stamp(job, "lesson", ["lesson"])
    data = {"lesson": lesson, "questions": None, "phases": None, "pages": None}
    for step in order[1:]:
        if not rep.ok():
            break
        here = Rep()
        if step == "questions":
            data["questions"] = gate_questions(job, here, lesson)
        elif step == "phases":
            data["phases"] = gate_phases(job, here, lesson)
        else:
            data["pages"] = gate_pages(job, here, lesson, data["questions"], data["phases"])
        rep.extend(here)
        if here.ok():
            write_stamp(job, step, stamp_order(lesson, step))
    state, reason = deck_state(job)
    if state == "bad":
        rep.bad("G10", "deck.html", reason)
    else:
        print("成品对账：%s" % reason)
    if lesson["route"] == ROUTES[1]:
        print("未先出作业：本课走的是 content-first 路线，出题后置到 build 之前。")
    return emit(rep, "check --all")


def cmd_build(args):
    job = Job(resolve(args.root, args.slug))
    rep = Rep()
    lesson = gate_lesson(job, rep)
    if lesson is None or not rep.ok():
        return emit(rep, "build")
    order = stamp_order(lesson, "pages")
    if "questions" not in order:
        order = order + ["questions"]      # content-first：出题后置，但成品盖章一样要记
    if read_stamp(job, "pages") is None:
        raise LockError(LOCK_TAIL["build"])
    if lesson["route"] == ROUTES[1] and read_stamp(job, "questions") is None:
        raise LockError(LOCK_TAIL["build-cf"])

    index = read_json(job.path("pages", "index.json"))
    ready, failed = [], []
    for row in as_list(index):
        if not isinstance(row, dict):
            continue
        pid = as_text(row.get("id"))
        rel = "pages/%s.html" % pid
        if not SLUG_RE.match(pid) or not job.has(rel):
            failed.append({"page": pid or "?", "failReason": "缺正文文件 %s" % rel})
            continue
        # 逐页 sanitize → enforceAccentVar → validate；原文与成品体各查一遍，
        # 免得消毒把问题盖住，也免得消毒本身引进新问题。
        page = Rep()
        source = read_text_or_empty(job.path(rel))
        carriers, hexes = scan_page_html(job, pid, source, page)
        body = enforce_accent_var(sanitize(source))
        after = Rep()
        scan_page_html(job, pid, body, after)
        page.extend(after)
        if not page.ok():
            failed.append({"page": pid, "failReason": page.errors()[0]["reason"]})
            continue
        for value in hexes:
            if value.lower() not in ACCENT_HEXES and hex_saturation(value) > SAT_WARN:
                rep.warn("G9", pid, "style 里写死了非中性色 %s（饱和度 %.2f > %.2f），"
                                    "主题色一律走 var(--accent)"
                         % (value, hex_saturation(value), SAT_WARN))
        if carriers == 0 and "var(--accent)" not in body:
            rep.warn("G9", pid, "本页换色无可见变化：既没有 h1/h2/h3/th/blockquote，也没有用 var(--accent)")
        ready.append({"id": pid, "title": as_text(row.get("title")), "body": body,
                      "notes": read_text_or_empty(job.path("pages/%s.notes.md" % pid))})

    if not ready:
        for item in failed:
            print("[ERROR] G9 %s：%s" % (item["page"], item["failReason"]))
        raise UsageError("全部页稿都没能通过准入，不写成品：先把上面这些页改好，再跑 check <slug> pages")
    for item in failed:
        rep.warn("G9", item["page"], "这一页没能进成品：%s" % item["failReason"])

    for name in drifted(job, read_stamp(job, "pages")):
        rep.bad("G10", name, "%s 已改动，请从 check %s 重新验收" % (name, owner_of(name)))
    if lesson["route"] == ROUTES[1]:
        for name in drifted(job, read_stamp(job, "questions")):
            rep.bad("G10", name, "%s 已改动，请从 check %s 重新验收" % (name, owner_of(name)))
        cover_matrix([dict(p, covers=covers_of(index, p["id"]),
                           words=content_words(strip_tags(p["body"]) + "\n" + p["notes"]))
                      for p in ready],
                     gate_questions(job, Rep(), lesson), rep)
    if not rep.ok():
        return emit(rep, "build")

    key = args.palette or (read_stamp(job, "deck") or {}).get("palette") or DEFAULT_PALETTE
    if key not in PALETTE_MAP:
        rep.warn("G11", "palette", "没有 %r 这个配色，回落到 %s；可用的是：%s"
                 % (key, DEFAULT_PALETTE, "、".join(k for k, _ in PALETTES)))
        key = DEFAULT_PALETTE
    accent = PALETTE_MAP[key]

    title = lesson["title"] or job.slug
    deck = render_deck(title, ready, accent)
    notes = render_notes(title, ready, accent)
    verify_shell(deck, notes, len(ready), rep)
    flat = re.sub(r"\s+", "", strip_tags(deck))
    for page in ready:
        head = re.sub(r"\s+", "", page["notes"])[:40]
        if len(head) >= 12 and head in flat:
            rep.bad("G9", page["id"], "讲稿前 40 字出现在了 deck.html 里：讲稿绝不能进投屏文件")
    if not rep.ok():
        return emit(rep, "build")

    write_text(job.path("deck.html"), deck)
    write_text(job.path("notes.html"), notes)
    write_stamp(job, "deck", order + ["deck"], {"palette": key, "failedPages": failed,
                                                "readyPages": [p["id"] for p in ready]})
    print("已出成品：deck.html（%d 页，配色 %s）与 notes.html（教师讲稿 · 不投屏）"
          % (len(ready), key))
    return emit(rep, "build")


def covers_of(index, pid):
    for row in as_list(index):
        if isinstance(row, dict) and as_text(row.get("id")) == pid:
            return [as_text(x) for x in as_list(row.get("covers")) if as_text(x)]
    return []


def cmd_repalette(args):
    job = Job(resolve(args.root, args.slug))
    if read_stamp(job, "deck") is None:
        raise UsageError("还没出过成品，没什么可换色的：先跑 lessonkit.py build %s" % args.slug)
    before = dict((n, job.hash_of("pages/%s" % n)) for n in sorted(os.listdir(job.path("pages"))))
    code = cmd_build(args)
    after = dict((n, job.hash_of("pages/%s" % n)) for n in sorted(os.listdir(job.path("pages"))))
    if before != after:
        raise UsageError("换色本该只重拼成品，页稿却变了——这是脚本的 bug，请连同页稿一起报上来")
    if code == 0:
        print("换色只重拼成品，pages/ 逐字节没动。")
    return code


def cmd_report(args):
    job = Job(resolve(args.root, args.slug))
    snap = collect(job)
    write_json(job.path(".stamps", "checks.json"), {
        "at": snap["at"], "slug": snap["slug"], "route": snap["lesson"]["route"],
        "steps": dict((k, v[0]) for k, v in snap["steps"].items()),
        "locks": snap["locks"], "deck": snap["deck"], "items": snap["items"],
    })
    write_text(job.path("report.md"), report_md(snap))
    write_text(job.path("report.html"), report_html(snap))
    bad = len([i for i in snap["items"] if i["level"] == "ERROR"])
    soft = len(snap["items"]) - bad
    print("已写出 report.md 与 report.html：%d ERROR / %d WARN" % (bad, soft))
    return 0


# ---------------------------------------------------------------- 入口

def build_parser():
    parser = argparse.ArgumentParser(prog="lessonkit.py", description="lesson-prep 备课脚本")
    parser.add_argument("--root", default=".", help="工作区（lessons/ 的父目录，默认当前目录）")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="本机环境与发布卫生自检")

    one = sub.add_parser("init", help="建课骨架")
    one.add_argument("slug")
    one.add_argument("--route", choices=ROUTES, default=ROUTES[0], help="默认 homework-first")

    two = sub.add_parser("check", help="逐步验收")
    two.add_argument("slug")
    two.add_argument("step", nargs="?", choices=list(STEPS), help="要验收的那一步")
    two.add_argument("--all", action="store_true", help="四步复核 + 成品哈希对账")

    three = sub.add_parser("build", help="从 pages/ 派生 deck.html 与 notes.html")
    three.add_argument("slug")
    three.add_argument("--palette", help="主题色 key：%s" % "、".join(k for k, _ in PALETTES))

    four = sub.add_parser("repalette", help="只换主题色重拼")
    four.add_argument("slug")
    four.add_argument("--palette", required=True, help="主题色 key")

    five = sub.add_parser("report", help="渲染 report.md 与 report.html")
    five.add_argument("slug")
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"doctor": cmd_doctor, "init": cmd_init, "check": cmd_check,
                "build": cmd_build, "repalette": cmd_repalette, "report": cmd_report}
    if not args.command:
        parser.print_help()
        return 2
    if args.command == "check" and not args.all and not args.step:
        print("错误：check 要指定哪一步（%s），或者加 --all" % " / ".join(STEPS), file=sys.stderr)
        return 2
    try:
        return handlers[args.command](args)
    except LockError as e:
        print("锁住了：%s" % e, file=sys.stderr)
        return 2
    except UsageError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 2
    except Exception as e:
        print("错误：%s：%s" % (type(e).__name__, e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
