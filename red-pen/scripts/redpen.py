#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""red-pen 红笔改稿脚本（零依赖，Python 3.8+ 标准库，单文件）。

模型只负责说「哪一句、什么问题、怎么改」，本脚本负责把它钉回原文、校验它没有胡说，
再渲染成一页可截图的红笔稿。稿子本身脚本一个字都不改。

子命令：
  doctor                              查看本机环境与工作区
  init <slug> --from <file> [--lang]  收一份稿子；正文与后缀没变就不升版本
  brief set <slug> --from <file>      写入「给谁看 / 要达到什么 / 最怕什么」
  context <slug>                      输出上下文包 JSON（纯文本、brief、context_hash）
  review <slug>                       读 inbox/marks.json → 闸门 → 锚定 → 红笔页
  stats <slug>                        锚定率、等级分布、上一版有几条挂不住了
  check <slug|dir>                    离线复核整个工作区
  export <slug>                       导出脱敏证据（只有哈希与计数，不含正文）

退出码：0 通过 / 1 闸门没过 / 2 用法或输入格式错误。
闸门与目录契约见 references/workspace-format.md，纪律见 references/rules.md。
"""

import argparse
import datetime
import hashlib
import json
import ntpath
import os
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchor

# ---- 闸门常量（改这里必须同步改 references/workspace-format.md 与 selftest.py）
MARKS_MIN = 1                 # 批注条数下限
MARKS_MAX = 30                # 批注条数上限
QUOTE_MAX = 200               # 单条引文字数上限（unit_len 口径）
QUOTE_MAX_CHARS = 400         # 单条引文原串字符硬顶（字数闸之外再兜一道）
NOTE_MIN = 6                  # 单条批语字数下限（unit_len 口径）
MIN_ANCHORED = 0.7            # 锚定率门槛
LOOK_ALIKE = 0.6              # 批语相似度提醒，沿用家族门槛，不拦
FIX_MAX_RATIO = 3             # 单条 fix 相对引文的长度上限倍数
FIX_MIN_UNITS = 20            # 单条 fix 预算的地板：短引文也要写得完一句话
FIX_MAX_UNITS = 40            # 单条 fix 预算的天花板：限制长建议，不能替代不代笔的纪律
FIX_TOTAL_RATIO = 0.5         # fix 合计相对全稿的长度上限比例
FIX_TOTAL_MIN_UNITS = 60      # fix 合计预算的地板：短稿上几条正常改法不该被顶掉
FRONT_RATIO = 0.2             # 覆盖闸：引文全落在这个比例之前就提醒
FRONT_MIN_BLOCKS = 3          # 覆盖闸的前提：稿子不足这么多块就无从谈起

# ---- 目录与文件名
DRAFTS_DIR = "drafts"
DRAFT_STEM = "draft"
BRIEF_NAME = "brief.json"
MARKS_NAME = "marks.json"
PAGE_NAME = "review.html"
INBOX_DIR = "inbox"
HISTORY_DIR = "history"
SNAPSHOT_FMT = "review-%04d.json"
SNAPSHOT_RE = re.compile(r"^review-(\d+)\.json$")
VERSION_RE = re.compile(r"^v(\d+)$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# ---- 契约键名
PAYLOAD_KEYS = ("context_hash", "marks")
MARK_KEYS = ("quote", "level", "note", "fix")
BRIEF_KEYS = ("audience", "purpose", "worries", "lang")
LANGS = ("zh", "en")

# ---- docx：只读 word/document.xml 里的文字段落
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WORD_MAIN = "word/document.xml"
# 同一段内容的两种画法：新版画在 mc:Choice 里，旧版在 mc:Fallback 里兜底。两边都读等于复制一份。
MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


# ---- 原稿准入与解码；JSON 载荷不消费这组编码兜底
# UTF-32 的 BOM 以 UTF-16 的 BOM 开头，必须先匹配长标记。
BOMS = ((b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
        (b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"))
UTF8_ENCS = ("utf-8-sig", "utf-8")
FALLBACK_ENC = "gb18030"
TEXT_EXTS = (".txt", ".md", ".markdown", ".html", ".htm")
DOCX_EXT = ".docx"
SNIFF_BYTES = 8192
REFUSE_EXTS = {
    ".pdf": "PDF 读不了。在阅读器里全选复制、粘成 .txt，或用 Word 打开另存为 .docx 再来。",
    ".doc": "旧版 Word .doc 读不了。请用 Word 另存为 .docx 或 .txt。",
    ".rtf": "RTF 读不了。请用文字处理软件另存为 .docx 或 .txt。",
    ".odt": "ODT 读不了。请用文字处理软件另存为 .docx 或 .txt。",
    ".pages": "Pages 文稿读不了。请在 Pages 中导出为 .docx 或 .txt。",
    ".epub": "EPUB 读不了。请在阅读器里复制所需正文，粘成 .txt。",
}
for _ext in (".xlsx", ".xls", ".csv", ".numbers"):
    REFUSE_EXTS[_ext] = "表格文件读不了。请把要批的单元格文字复制出来，粘成 .txt。"
for _ext in (".pptx", ".ppt", ".key"):
    REFUSE_EXTS[_ext] = "演示文件读不了。请把要批的文字复制出来，粘成 .txt。"
for _ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg", ".heic", ".ico"):
    REFUSE_EXTS[_ext] = "图片读不了。请先用文字识别工具提取文字，核对后存成 .txt。"
for _ext in (".zip", ".rar", ".7z", ".gz", ".gzip", ".tar", ".bz2", ".xz", ".tgz"):
    REFUSE_EXTS[_ext] = "压缩包读不了。请先解压，再交里面的 .txt、.md、.html 或 .docx 稿子。"
BINARY_MAGIC = (
    (b"%PDF-", REFUSE_EXTS[".pdf"]), (b"{\\rtf", REFUSE_EXTS[".rtf"]),
    (b"PK\x03\x04", REFUSE_EXTS[".zip"]), (b"\xd0\xcf\x11\xe0", REFUSE_EXTS[".doc"]),
    (b"\x89PNG", REFUSE_EXTS[".png"]), (b"\xff\xd8\xff", REFUSE_EXTS[".jpg"]),
    (b"GIF8", REFUSE_EXTS[".gif"]),
    (b"%!PS", "PostScript 读不了。请从原文档复制正文，存成 .txt。"),
    (b"\x1f\x8b", REFUSE_EXTS[".gz"]),
    (b"\x7fELF", "这是程序文件，读不了。请交 .txt、.md、.html 或 .docx 稿子。"),
)
WORD_TBL = WORD_NS + "tbl"
WORD_TR = WORD_NS + "tr"
WORD_TXBX = WORD_NS + "txbxContent"
WORD_PICT = tuple(WORD_NS + tag for tag in ("drawing", "pict", "object"))
WORD_TRACK = tuple(WORD_NS + tag for tag in ("ins", "del"))
CELL_SEP = "\t"
DOCX_LINES = {
    "word": "这是 Word 稿：我只读得到文字，抽成纯文本存进了工作区。",
    "table": "表格按行读出来了，同一行的单元格用制表符相连，整行可以整句引；行与行之间是块边界，跨行引不了。",
    "textbox": "文本框里的字读到了，按它在正文里的位置读一次，不重复。",
    "picture": "图片里的字读不到（脚本不做文字识别），图本身不进稿子；普通文字段落里的图注仍会读到。",
    "track": "读到的是正文里的文字节点（通常包括插入文字，不含删除文字节点）；修订痕迹与 Word 批注读不到，也不替你接受或拒绝修订。",
}


class UsageError(Exception):
    """用法或输入格式错误，退出码 2。"""


# ---------------------------------------------------------------- 小工具

def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        raise UsageError("找不到文件：%s" % _shown(path))
    except IsADirectoryError:
        raise UsageError("这是一个目录而不是文件：%s" % _shown(path))


def read_text(path):
    """工作区与 JSON 只读严格 UTF-8，兼容 UTF-8 BOM；不猜旧编码。"""
    try:
        return read_bytes(path).decode(UTF8_ENCS[0]).replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as e:
        raise UsageError("文件不是 UTF-8 编码：%s（%s）" % (_shown(path), e))


def _bom_of(raw):
    return next((encoding for bom, encoding in BOMS if raw.startswith(bom)), None)


def decode_bytes(raw, shown):
    """仅供原稿使用，返回（统一换行的正文，BOM 编码／utf-8／gb18030）。"""
    encoding = _bom_of(raw)
    try:
        if encoding:
            text = raw.decode(encoding)
        else:
            try:
                text = raw.decode(UTF8_ENCS[1])
                encoding = UTF8_ENCS[1]
            except UnicodeDecodeError:
                encoding = FALLBACK_ENC
                text = raw.decode(encoding)
    except UnicodeDecodeError:
        raise UsageError("编码读不出：%s。按文件头字节序标记或 UTF-8、GB18030 都未能读出正文；"
                         "若其实是 Word / PDF / 图片，先按它自己的格式导出。" % shown)
    return text.replace("\r\n", "\n").replace("\r", "\n"), encoding


def _refuse_by_content(raw):
    for magic, reason in BINARY_MAGIC:
        if raw.startswith(magic):
            raise UsageError(reason)
    # BOM 必须先于 NUL 判定：UTF-16／UTF-32 正文本来就会含零字节。
    if _bom_of(raw) not in ("utf-16", "utf-32") and b"\x00" in raw[:SNIFF_BYTES]:
        raise UsageError("这像是二进制文件，读不了。请按原格式导出为 .txt 或 .docx。")


def _refuse_by_ext(ext):
    if ext in REFUSE_EXTS:
        raise UsageError(REFUSE_EXTS[ext])


def _keep_ext(ext):
    if ext in (".html", ".htm"):
        return ".html"
    if ext in (".md", ".markdown"):
        return ".md"
    return ".txt"


def admit(path, raw):
    """内容先拒收，后缀再拒收；其余文本返回（目标后缀，提示行列表）。"""
    _refuse_by_content(raw)
    ext = os.path.splitext(path)[1].lower()
    _refuse_by_ext(ext)
    notes = []
    if path != STDIN_MARK and ext not in TEXT_EXTS:
        notes.append("这个后缀我不认得，按纯文本读的。读出来不是你的正文就换个格式再来。")
    return _keep_ext(ext), notes


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_json(path):
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as e:
        raise UsageError("JSON 解析失败：%s（%s）" % (_shown(path), e))


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def canonical(obj):
    """稳定序列化：键排序、不留空格、中文不转义 —— 哈希只认这一种写法。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


_ROOT = "."


def _set_root(root):
    global _ROOT
    _ROOT = os.path.abspath(root)


def _shown(path):
    """业务路径相对 --root；目录外、跨盘符只能回显文件名。"""
    try:
        rel = os.path.relpath(path, _ROOT)
        if not os.path.isabs(rel) and rel != os.pardir and not rel.startswith(os.pardir + os.sep):
            return rel
    except ValueError:
        pass
    return os.path.basename(os.path.normpath(path)) or "（根目录）"


def _abs(path):
    """仅供 doctor 当场核对目录，不用于业务输出。"""
    return os.path.abspath(path)


def _diagnostic(message):
    """只处理诊断元数据，正文、brief 与编码预览不经过这里。"""
    pattern = r"(?<![\w./\\])(?:[A-Za-z]:[\\/]|[\\/]+)[^\s\"'，。；（）：]+"
    return re.sub(pattern, lambda m: ntpath.basename(m.group(0).rstrip("/\\")) or "（根目录）", message)


def _metadata(value):
    """拒收的键名与枚举／哈希／slug 值，只在诊断时缩短路径。"""
    if isinstance(value, str):
        if value.startswith(("/", "\\")) or ntpath.isabs(value):
            return ntpath.basename(value.rstrip("/\\")) or "（根目录）"
        return _diagnostic(value)
    return value


def _pct(ratio):
    return "%d%%" % int(round(ratio * 100))


def _cut(text, width=40):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width] + "…"


# ---------------------------------------------------------------- 字数口径

# 全库只有这一把尺：闸门的分子分母、init 的字数行都走 unit_len，绝不再写第二个 CJK 检测器。
_CJK_RANGES = (
    (0x3040, 0x30FF),        # 假名
    (0x3400, 0x4DBF),        # 汉字扩展 A
    (0x4E00, 0x9FFF),        # 汉字基本区
    (0xAC00, 0xD7A3),        # 谚文音节
    (0xF900, 0xFAFF),        # 汉字兼容区
    (0x20000, 0x2FA1F),      # 汉字扩展 B 及以后
)


def _is_cjk(ch):
    code = ord(ch)
    for lo, hi in _CJK_RANGES:
        if lo <= code <= hi:
            return True
    return False


def _units(s):
    """汉字假名谚文逐字成词，连着的字母数字成词，标点与空白丢掉。

    CJK 那一支必须排在 isalnum() 之前，CJK 字符本身也断开字母数字连写。
    保留词的原样大小写，字数与批语相似度只用这一套切法。
    """
    units = []
    run = []
    for ch in s:
        if _is_cjk(ch):
            if run:
                units.append("".join(run))
                run = []
            units.append(ch)
        elif ch.isalnum():
            run.append(ch)
        elif run:
            units.append("".join(run))
            run = []
    if run:
        units.append("".join(run))
    return units


def unit_len(s):
    """统一字数口径：分词后数单位，折叠空白、归一引号都不改变长度。"""
    return len(_units(s))


def fix_budget(quote_units):
    """单条 fix 的字数预算：引文的三倍，夹在地板与天花板之间。

    地板保住英文短引文（「Hi Dana,」只有 2 个字，三倍写不完一句话），
    天花板限制长建议，不能识别所有整段重写，仍须遵守不代笔的纪律。
    """
    return min(max(FIX_MAX_RATIO * quote_units, FIX_MIN_UNITS), FIX_MAX_UNITS)


def total_fix_budget(draft_units):
    """全篇 fix 合计的字数预算：稿子的一半，短稿另有一道地板。

    地板只放松短稿那一侧 —— 长稿走的仍是比例，几百字的稿子不会因此多出额度。
    """
    return max(int(draft_units * FIX_TOTAL_RATIO), FIX_TOTAL_MIN_UNITS)


# ---------------------------------------------------------------- 工作区

def resolve(root, target):
    """参数带路径分隔符就当目录，否则当 <root>/drafts/<slug>。返回 (工作区, slug)。"""
    if os.sep in target or (os.altsep and os.altsep in target):
        here = os.path.abspath(target)
        if not os.path.isdir(here):
            raise UsageError("找不到工作区目录：%s" % _shown(here))
        return here, os.path.basename(here.rstrip(os.sep + (os.altsep or os.sep)))
    slug = check_slug(target)
    here = os.path.join(os.path.abspath(root), DRAFTS_DIR, slug)
    if not os.path.isdir(here):
        raise UsageError("还没有这个工作区：%s；先跑 init %s --from <稿子>" % (_shown(here), slug))
    return here, slug


def check_slug(slug):
    if not SLUG_RE.match(slug or ""):
        raise UsageError("slug 只能是小写字母、数字与连字符（不超过 64 位），当前是：%r" % _metadata(slug))
    return slug


def draft_path(ws):
    """工作区里那一份稿子；没有返回 None。"""
    found = sorted(f for f in os.listdir(ws)
                   if f.startswith(DRAFT_STEM + ".") and os.path.isfile(os.path.join(ws, f)))
    return os.path.join(ws, found[0]) if found else None


def require_draft(ws):
    path = draft_path(ws)
    if path is None:
        raise UsageError("工作区里没有稿子：%s；先跑 init … --from <稿子>" % _shown(ws))
    return path


def version_dirs(ws):
    """history/ 下已归档的版本号，从小到大。"""
    hist = os.path.join(ws, HISTORY_DIR)
    if not os.path.isdir(hist):
        return []
    out = []
    for name in os.listdir(hist):
        hit = VERSION_RE.match(name)
        if hit and os.path.isdir(os.path.join(hist, name)):
            out.append(int(hit.group(1)))
    return sorted(out)


def version_of(ws):
    """当前是第几版：已归档的版本数 + 1。"""
    seen = version_dirs(ws)
    return seen[-1] + 1 if seen else 1


def inbox_path(ws):
    return os.path.join(ws, INBOX_DIR, MARKS_NAME)


def record_path(ws):
    return os.path.join(ws, MARKS_NAME)


def read_record(ws):
    path = record_path(ws)
    if not os.path.isfile(path):
        raise UsageError("还没有通过闸门的批注：%s；先写 %s 再跑 review"
                         % (_shown(path), os.path.join(INBOX_DIR, MARKS_NAME)))
    return read_json(path)


# ---------------------------------------------------------------- brief

def brief_template(lang="zh"):
    return {"audience": "", "purpose": "", "worries": [], "lang": lang}


def normalize_brief(raw):
    if not isinstance(raw, dict):
        raise UsageError("brief 的顶层应当是一个 JSON 对象")
    unknown = sorted(k for k in raw if k not in BRIEF_KEYS)
    if unknown:
        raise UsageError("brief 只认这四个键：%s；多出来的：%s"
                         % ("、".join(BRIEF_KEYS), "、".join(_metadata(key) for key in unknown)))
    worries = raw.get("worries") or []
    if not isinstance(worries, list) or any(not isinstance(w, str) for w in worries):
        raise UsageError("brief 的 worries 应当是一串字符串")
    lang = str(raw.get("lang") or "zh").strip().lower()
    if lang not in LANGS:
        raise UsageError("brief 的 lang 只能是 zh 或 en，当前是：%r" % _metadata(raw.get("lang")))
    return {
        "audience": str(raw.get("audience") or "").strip(),
        "purpose": str(raw.get("purpose") or "").strip(),
        "worries": [w.strip() for w in worries if w.strip()],
        "lang": lang,
    }


def read_brief(ws):
    path = os.path.join(ws, BRIEF_NAME)
    if not os.path.isfile(path):
        return brief_template()
    return normalize_brief(read_json(path))


# ---------------------------------------------------------------- 取稿

def _docx_paragraphs(node):
    """按文档顺序产出顶层 w:p；文本框里的 w:p 归外层那一段，mc:Fallback 整棵跳过。

    文本框的 w:p 嵌在外层 w:p 之下，若把它当顶层段落再枚举一遍，同一句话就会
    被读第二次；而 Choice 与 Fallback 各带一份同样的文字，两边都读又乘二。
    所以遇到 w:p 就产出它、不再往里钻，遇到 mc:Fallback 直接绕过整棵子树。
    """
    for child in node:
        if child.tag == MC_FALLBACK:
            continue
        if child.tag == WORD_NS + "p":
            yield child
        else:
            for found in _docx_paragraphs(child):
                yield found


def _docx_line(node, parts):
    """一段里的文字：w:t 拼起来，w:br / w:cr 换行，w:tab 制表；Fallback 同样绕过。"""
    for child in node:
        if child.tag == MC_FALLBACK:
            continue
        if child.tag == WORD_NS + "t":
            parts.append(child.text or "")
        elif child.tag in (WORD_NS + "br", WORD_NS + "cr"):
            parts.append("\n")
        elif child.tag == WORD_NS + "tab":
            parts.append("\t")
        _docx_line(child, parts)
    return parts


def _docx_shape(root):
    """只报告正文 XML 实际出现的结构，不推断图片或批注内容。"""
    tags = {node.tag for node in root.iter()}
    shape = set()
    for name, present in (("table", WORD_TBL in tags), ("textbox", WORD_TXBX in tags),
                          ("picture", bool(tags.intersection(WORD_PICT))),
                          ("track", bool(tags.intersection(WORD_TRACK)))):
        if present:
            shape.add(name)
    return shape


def _docx_rows(tbl):
    """显式按行、单元格取字：一格多段用空格，格间用制表符。"""
    def members(node, tag):
        # 内容控件等容器透明；一旦找到目标就停，不把嵌套表格再算成同级行／格。
        for child in node:
            if child.tag == MC_FALLBACK:
                continue
            if child.tag == tag:
                yield child
            elif child.tag not in (WORD_TBL, WORD_TR, WORD_NS + "tc", WORD_NS + "p"):
                yield from members(child, tag)

    for row in members(tbl, WORD_TR):
        cells = []
        for cell in members(row, WORD_NS + "tc"):
            paragraphs = ["".join(_docx_line(p, [])).strip() for p in _docx_paragraphs(cell)]
            cells.append(" ".join(p for p in paragraphs if p))
        line = CELL_SEP.join(cells)
        if line.strip():
            yield line


def _docx_blocks(root):
    for child in root:
        if child.tag == MC_FALLBACK:
            continue
        if child.tag == WORD_TBL:
            yield from _docx_rows(child)
        elif child.tag == WORD_NS + "p":
            line = "".join(_docx_line(child, [])).strip()
            if line:
                yield line
        else:
            yield from _docx_blocks(child)


def docx_text(path):
    """返回（正文，结构集合）；表格按行成块，文本框沿用不重复抽取。"""
    try:
        with zipfile.ZipFile(path) as pack:
            raw = pack.read(WORD_MAIN)
    except FileNotFoundError:
        raise UsageError("找不到文件：%s" % _shown(path))
    except IsADirectoryError:
        raise UsageError("这是一个目录而不是文件：%s" % _shown(path))
    except KeyError:
        raise UsageError("这个 .docx 里没有 %s，不像是 Word 文档：%s" % (WORD_MAIN, _shown(path)))
    except zipfile.BadZipFile:
        raise UsageError("这个文件不是有效的 .docx（打不开压缩包）：%s" % _shown(path))
    try:
        root = ET.fromstring(raw.decode("utf-8", "replace"))
    except ET.ParseError as e:
        raise UsageError("这个 .docx 的正文 XML 解析失败：%s（%s）" % (_shown(path), e))
    blocks = list(_docx_blocks(root))
    if not blocks:
        raise UsageError("这个 .docx 里没读到文字段落（整篇都是图片的稿子读不了）：%s" % _shown(path))
    return "\n\n".join(blocks) + "\n", _docx_shape(root)


def load_source(path):
    """原稿唯一入口，返回（正文，目标后缀，提示行列表）。"""
    if os.path.splitext(path)[1].lower() == DOCX_EXT:
        # docx 本来就是 ZIP，不能跑内容嗅探；假 docx 由 BadZipFile 兜住。
        text, shape = docx_text(path)
        return text, ".txt", [DOCX_LINES["word"]] + [
            DOCX_LINES[key] for key in ("table", "textbox", "picture", "track") if key in shape]
    raw = sys.stdin.buffer.read() if path == STDIN_MARK else read_bytes(path)
    ext, notes = admit(path, raw)
    text, encoding = decode_bytes(raw, _source_label(path))
    if _bom_of(raw):
        notes.append("按 %s 编码读取，这是文件头的字节序标记说的。" % encoding.upper())
    elif encoding == FALLBACK_ENC:
        notes.append("编码是猜的：按 GB18030 读出。请核对正文开头两行；这两行是乱码就先停下，别接着批。")
        notes.extend(text.split("\n")[:2])
    return text, ext, notes


# ---------------------------------------------------------------- 闸门

def context_hash(draft_text, brief):
    """稿子纯文本 + brief 一起入哈希：改了稿子或改了标准，旧批注都得作废。"""
    return sha256_text(canonical({"draft_text": draft_text, "brief": brief}))


def _gate_top(payload):
    if not isinstance(payload, dict):
        return ["%s 的顶层应当是一个 JSON 对象。" % os.path.join(INBOX_DIR, MARKS_NAME)]
    unknown = sorted(k for k in payload if k not in PAYLOAD_KEYS)
    if unknown:
        return ["顶层只认 %s 这两个键，多出来的：%s。" % ("、".join(PAYLOAD_KEYS), "、".join(_metadata(key) for key in unknown))]
    return []


def _gate_hash(draft_text, brief, payload):
    want = context_hash(draft_text, brief)
    got = str(payload.get("context_hash") or "")
    if got == want:
        return []
    return ["context_hash 对不上：交上来的是 %s，当前稿子与 brief 算出来的是 %s；"
            "跑一次 context 拿到新的上下文包再重批。" % (_cut(_metadata(got) or "（空）", 16), _cut(want, 16))]


def _gate_count(items):
    n = len(items)
    if MARKS_MIN <= n <= MARKS_MAX:
        return []
    return ["批注应当是 %d–%d 条，实际 %d 条。" % (MARKS_MIN, MARKS_MAX, n)]


def _gate_fix(idx, quote, fix):
    if not fix.strip():
        return ["提交的第 %d 条的 fix 是空串：要么写清怎么改，要么把这个键去掉。" % idx]
    errors = []
    bare_quote, bare_fix = anchor.normalize(quote), anchor.normalize(fix)
    if bare_fix == bare_quote:
        errors.append("提交的第 %d 条的 fix 与引文规范化后完全相同，那不是改法。" % idx)
    q_units, f_units = unit_len(bare_quote), unit_len(bare_fix)
    budget = fix_budget(q_units)
    if bare_quote and f_units > budget:
        errors.append("提交的第 %d 条的 fix 有 %d 字，超过预算 %d 字（引文 %d 字 × %d，最少 %d 字、最多 %d 字）："
                      "给方向就够，整段重写不是批注。"
                      % (idx, f_units, budget, q_units, FIX_MAX_RATIO, FIX_MIN_UNITS, FIX_MAX_UNITS))
    return errors


def _gate_one(idx, item):
    """单条批注的形状闸；总是返回一条清洗过的记录，好让后面的编号对得上。"""
    tidy = {"quote": "", "level": anchor.DEFAULT_LEVEL, "note": ""}
    if not isinstance(item, dict):
        return ["提交的第 %d 条不是一个 JSON 对象。" % idx], tidy
    errors = []
    unknown = sorted(k for k in item if k not in MARK_KEYS)
    if unknown:
        errors.append("提交的第 %d 条多了不认识的键：%s；只认 %s。"
                      % (idx, "、".join(_metadata(key) for key in unknown), "、".join(MARK_KEYS)))
    quote = str(item.get("quote") or "").strip()
    note = str(item.get("note") or "").strip()
    if not quote:
        errors.append("提交的第 %d 条的引文是空的：批注必须指向原文里的某一句。" % idx)
    elif unit_len(quote) > QUOTE_MAX:
        errors.append("提交的第 %d 条的引文有 %d 字，超过 %d 字上限：引一句就够，不要整段抄。"
                      % (idx, unit_len(quote), QUOTE_MAX))
    elif len(quote) > QUOTE_MAX_CHARS:
        errors.append("提交的第 %d 条的引文有 %d 个字符，超过 %d 字符硬顶：引一句就够，不要整段抄。"
                      % (idx, len(quote), QUOTE_MAX_CHARS))
    if unit_len(note) < NOTE_MIN:
        errors.append("提交的第 %d 条的批语只有 %d 字，至少 %d 字才说得清问题。"
                      % (idx, unit_len(note), NOTE_MIN))
    tidy["quote"] = quote
    tidy["note"] = note
    if item.get("level") is not None:
        tidy["level"] = item["level"]
    if "fix" in item:
        fix = str(item.get("fix") or "")
        errors.extend(_gate_fix(idx, quote, fix))
        tidy["fix"] = fix.strip()
    return errors, tidy


def _gate_duplicate(marks):
    """同一句批两次、同一句评语贴两处 —— 都是没在逐条看稿。"""
    errors = []
    for label, key in (("引文", "quote"), ("批语", "note")):
        seen = {}
        for i, m in enumerate(marks, 1):
            token = anchor.normalize(m.get(key) or "")
            if not token:
                continue
            if token in seen:
                errors.append("提交的第 %d 条与提交的第 %d 条的%s重复：%s"
                              % (seen[token], i, label, _cut(m.get(key))))
            else:
                seen[token] = i
    return errors


def warn_look_alike(marks):
    """相似批语只提醒；规范化后完全相同仍由重复闸拒收。"""
    warnings = []
    tokens = [set(_units(m.get("note") or "")) for m in marks]
    for i, left in enumerate(tokens):
        for j in range(i + 1, len(tokens)):
            right = tokens[j]
            union = left | right
            if not union:
                continue
            ratio = len(left & right) / len(union)
            if ratio >= LOOK_ALIKE:
                warnings.append(
                    "提交的第 %d 条与第 %d 条的批语很像（相似度 %s，门槛 %s）："
                    "确认不是套模板；真的是同一个毛病，就合成一条并在批语里说清它在下面还犯了一次。"
                    % (i + 1, j + 1, _pct(ratio), _pct(LOOK_ALIKE)))
    return warnings


def _gate_no_rewrite(draft_text, marks):
    total = sum(unit_len(m["fix"]) for m in marks if m.get("fix"))
    draft_units = unit_len(draft_text)
    budget = total_fix_budget(draft_units)
    if total <= budget:
        return []
    return ["fix 合计 %d 字，超过预算 %d 字（全稿 %d 字的一半，短稿至少给到 %d 字）："
            "这是重写不是批注，请只在关键处给改法。"
            % (total, budget, draft_units, FIX_TOTAL_MIN_UNITS)]


def _warn_brief(brief):
    if (brief.get("audience") or "").strip() or (brief.get("purpose") or "").strip():
        return []
    return ["brief 里还没写给谁看、要达到什么：先问用户这几个问题再批，批语才有落脚点。"]


def validate_marks(draft_text, brief, payload):
    """纯函数：只看稿子纯文本与 brief，判这份批注合不合规。

    返回 (errors, warnings, normalized)。normalized 是清洗过的
    `{"context_hash", "marks": [{quote, level, note, fix?}]}`；errors 非空时不要拿它去锚定。
    锚定率与覆盖两道闸要先 annotate 才知道，见 gate_anchored / gate_coverage。
    """
    warnings = _warn_brief(brief)
    top = _gate_top(payload)
    if top:
        return top, warnings, {"context_hash": "", "marks": []}
    errors = _gate_hash(draft_text, brief, payload)
    raw = payload.get("marks")
    if not isinstance(raw, list):
        errors.append("marks 应当是一个数组。")
        raw = []
    errors.extend(_gate_count(raw))
    marks = []
    for i, item in enumerate(raw, 1):
        item_errors, tidy = _gate_one(i, item)
        errors.extend(item_errors)
        marks.append(tidy)
    errors.extend(_gate_duplicate(marks))
    warnings.extend(warn_look_alike(marks))
    errors.extend(_gate_no_rewrite(draft_text, marks))
    return errors, warnings, {"context_hash": str(payload.get("context_hash") or ""), "marks": marks}


WHY_OVERLAP = "与别的批注重叠，脚本留了起点靠前的那条（同起点取长）；引文本身没问题，把这两条合成一条，或改引另一句"
WHY_CROSS = "这一句在稿子里逐字都有，但它横跨了两块（段落 / 列表项 / 表格行 / 标题之间）；脚本不做跨块锚定，只引其中一块"
WHY_MISSING = "稿子里找不到这一句；回 draft_text 一字不差地重抄"
PARTIAL_WARN_RATIO = 1.0 / 3


def why_missed(ex, mark):
    """先认重叠让位，再区分跨块与真正找不到；让位的引文本身可能定位成功。"""
    if mark.get("dropped_overlap"):
        return WHY_OVERLAP
    if anchor.locate_reason(ex, mark.get("quote") or "") == anchor.CROSS_BLOCK:
        return WHY_CROSS
    return WHY_MISSING


def submit_order(tidy_marks, result_marks):
    """返回页面 id → 提交序号；只在形状与重复闸通过后调用。

    这张映射靠闸门四（两条引文规范化后不许相同）才成立。闸门四一旦被放宽，
    同一个规范化引文会对应两个提交序，编号映射会静默错位，报错就会指着错的
    那一行让人去改。改闸门四之前先改这里。
    """
    by_quote = {anchor.normalize(m["quote"]): i for i, m in enumerate(tidy_marks, 1)}
    return {m["id"]: by_quote[anchor.normalize(m["quote"])] for m in result_marks}


def order_line(order):
    if all(pid == submitted for pid, submitted in order.items()):
        return None
    return "红笔页编号 ← inbox 提交序：" + "、".join(
        "%d←%d" % (pid, order[pid]) for pid in sorted(order))


def missed_lines(ex, marks, order=None):
    """未定位清单；review 带提交序，stats 只用留档中的页面序。"""
    lines = []
    for m in marks:
        if m.get("anchored"):
            continue
        pid, why = m["id"], why_missed(ex, m)
        if order is None:
            lines.append("    红笔页第 %d 条（%s）" % (pid, why))
        else:
            lines.append("    提交的第 %d 条 → 红笔页第 %d 条（%s）" % (order[pid], pid, why))
        lines.append("      引文：%s" % _cut(m.get("quote"), 60))
        lines.append("      批语：%s" % _cut(m.get("note"), 60))
    return lines


def partial_line(marks):
    count = sum(1 for m in marks if m.get("partial"))
    if not count:
        return None
    return "其中 %d 条只对上头尾，仅供参考——这几条的引文值得回原文核一遍。" % count


def warn_partial(result):
    anchored = sum(1 for m in result.marks if m.get("anchored"))
    partial = sum(1 for m in result.marks if m.get("partial"))
    if not anchored or partial / anchored <= PARTIAL_WARN_RATIO:
        return []
    return ["头尾锚定的有 %d 条，占已锚定 %d 条的 %s，超过三分之一：这几条的引文回原文重抄一遍更稳。"
            % (partial, anchored, _pct(partial / anchored))]


def gate_anchored(ex, result, order):
    """锚定率不够就退回重批，并把钉不住的引文逐条摊开。"""
    if not result.marks or result.anchored_ratio >= MIN_ANCHORED:
        return []
    lines = ["锚定率 %s（%d/%d）低于门槛 %s，下面这些引文没能钉回原文，下面逐条说清是哪一种没钉住、该怎么办："
             % (_pct(result.anchored_ratio),
                sum(1 for m in result.marks if m.get("anchored")), len(result.marks),
                _pct(MIN_ANCHORED))]
    if len(result.marks) - 1 < MIN_ANCHORED * len(result.marks):
        lines.append("    条数少的时候一条钉不住就等于整份不过：回原文把那一条重抄一遍就行，不必删条凑比例。")
    missed = sum(1 for m in result.marks if not m.get("anchored"))
    overlaps = sum(1 for m in result.marks if m.get("dropped_overlap"))
    if overlaps == missed:
        lines.append("下面这 %d 条都是与别的批注重叠被让位的，引文没写错——把重叠的两条合成一条，或改引另一句。" % overlaps)
    elif overlaps:
        lines.append("其中 %d 条是与别的批注重叠被让位的，那几条的引文没写错。" % overlaps)
    lines.extend(missed_lines(ex, result.marks, order))
    return ["\n".join(lines)]


def gate_coverage(result, html, blocks):
    """引文全挤在开头：多半是没读完，提醒但不拦。稿子不足三块就无从谈起。

    块数只认 `len(anchor.blocks(ex))`，不许改数换行符：带三处软换行的单段公告，
    换行符计数会数成 4 块、提醒照旧会响——那正是这道闸要修的那类稿子，实测
    `blocks()` 数出来是 1 块。块数这个量在「文字自带尾换行的 HTML 稿」上偏少
    （见 anchor.blocks 的边界说明），偏少只会让提醒更沉默，不会误报。
    """
    if blocks < FRONT_MIN_BLOCKS:
        return []
    starts = [m["start"] for m in result.marks if m.get("anchored") and "start" in m]
    if not starts or not html:
        return []
    if max(starts) >= len(html) * FRONT_RATIO:
        return []
    return ["所有引文都落在稿子前 %s 的篇幅里，看着像后半段没读完；确认过再交。" % _pct(FRONT_RATIO)]


def warn_levels(result, order):
    bad = [m for m in result.marks if m.get("level_fixed")]
    if not bad:
        return []
    return ["提交的第 %s 条的等级不在 %s 之内，已改判为「%s」：等级由脚本兜底，不要自己造词。"
            % ("、".join(str(order[m["id"]]) for m in bad), "、".join(anchor.LEVELS),
               anchor.LEVEL_LABEL[anchor.DEFAULT_LEVEL])]


def run_gates(raw, brief, payload):
    """六道闸门跑一遍，返回 (errors, warnings, normalized, result, order)。

    review 与 check 共用这一条通道 —— 「全部闸门」只在这里定义一次，两边不会走岔。
    形状闸没过就不锚定：拿一份自己都不认的批注去 splice 原文没有意义。
    """
    ex = anchor.extract(raw)
    errors, warnings, tidy = validate_marks(ex.text, brief, payload)
    result = None
    order = {}
    if not errors:
        result = anchor.annotate(raw, tidy["marks"])
        order = submit_order(tidy["marks"], result.marks)
        errors.extend(gate_anchored(ex, result, order))
        warnings.extend(gate_coverage(result, ex.html, len(anchor.blocks(ex))))
        warnings.extend(warn_levels(result, order))
        warnings.extend(warn_partial(result))
    return errors, warnings, tidy, result, order


def level_counts(marks):
    counts = dict((lv, 0) for lv in anchor.LEVELS)
    for m in marks:
        lv = m.get("level", anchor.DEFAULT_LEVEL)
        if lv in counts:
            counts[lv] += 1
    return counts


def level_line(counts):
    return "等级：" + " · ".join("%s %d" % (anchor.LEVEL_LABEL[lv], counts.get(lv, 0))
                                for lv in anchor.LEVELS)


# ---------------------------------------------------------------- init

def archive_version(ws):
    """把当前这一版的稿子、批注与红笔页整个归入 history/vN/。只增，不覆盖。"""
    current = draft_path(ws)
    if current is None:
        return None
    n = version_of(ws)
    box = os.path.join(ws, HISTORY_DIR, "v%d" % n)
    if os.path.exists(box):
        raise UsageError("history/v%d 已经存在：历史只增不改，请先把它挪走再 init。" % n)
    os.makedirs(box)
    for name in (os.path.basename(current), MARKS_NAME, PAGE_NAME):
        src = os.path.join(ws, name)
        if os.path.isfile(src):
            shutil.move(src, os.path.join(box, name))
    return n


DRAFT_WARN_CHARS = 50000      # 收稿提示阈值，按抽取文本字符数，不是闸门
STDIN_MARK = "-"


def _size_phrase(text):
    """已抽成纯文本的正文规模，沿用第 5 节的唯一主尺。"""
    return "正文 %d 字（汉字按字、英文按词，标点不算）" % unit_len(text)


def _source_label(path):
    """来源只显示文件名；标准输入使用统一标记。"""
    return "（标准输入）" if path == STDIN_MARK else os.path.basename(path)


def _intake_notes(source, ext, text, extra):
    """返回收稿提示行；extra 接收收稿层的附加提示，不在这里打印。"""
    lines = ["收进来：%s → %s%s" % (_source_label(source), DRAFT_STEM, ext)]
    lines.extend(extra)
    if len(text) >= DRAFT_WARN_CHARS:
        lines.append("这份稿子很长：%s —— 一轮最多 %d 条批注，红笔页会很难读，建议先切成一节一节地批。"
                     % (_size_phrase(anchor.plain_text(text)), MARKS_MAX))
        lines.append("如果你也装了段级评审那个技能，可以先用它定位最弱的一段，再把那一段单独送进来。")
    return lines


def cmd_init(args):
    slug = check_slug(args.slug)
    root = os.path.abspath(args.root)
    ws = os.path.join(root, DRAFTS_DIR, slug)
    try:
        text, ext, extra = load_source(args.source)
    except UsageError as e:
        raise UsageError(str(e).replace(_shown(args.source), _source_label(args.source)))
    intake_notes = _intake_notes(args.source, ext, text, extra)
    if not text.strip():
        raise UsageError("这份稿子是空的：%s" % _source_label(args.source))
    current = draft_path(ws) if os.path.isdir(ws) else None
    if current and os.path.splitext(current)[1] == ext and read_text(current) == text:
        if args.lang:
            brief = read_brief(ws)
            lang_changed = brief["lang"] != args.lang
            if lang_changed or not os.path.isfile(os.path.join(ws, BRIEF_NAME)):
                brief["lang"] = args.lang
                write_json(os.path.join(ws, BRIEF_NAME), brief)
                print("批语语言已写入 brief：%s。" % args.lang)
                if lang_changed:
                    print("brief 进 context_hash，旧批注作废，请重跑 context。")
        print("稿子和第 %d 版逐字相同，没有收成新版本 —— marks.json 与 review.html 都留在原地。"
              % version_of(ws))
        print("下一步：context %s → 写 %s → review %s。"
              % (slug, os.path.join(INBOX_DIR, MARKS_NAME), slug))
        print("确实改过稿就核对一下 --from 指的是不是新文件。")
        for note in intake_notes:
            print(note)
        return 0
    archived = archive_version(ws) if os.path.isdir(ws) else None
    for sub in (INBOX_DIR, HISTORY_DIR):
        os.makedirs(os.path.join(ws, sub), exist_ok=True)
    write_text(os.path.join(ws, DRAFT_STEM + ext), text)

    brief_file = os.path.join(ws, BRIEF_NAME)
    had_brief = os.path.isfile(brief_file)
    if not had_brief:
        write_json(brief_file, brief_template(args.lang or "zh"))
    elif args.lang:
        brief = read_brief(ws)
        brief["lang"] = args.lang
        write_json(brief_file, brief)
    brief = read_brief(ws)

    version = version_of(ws)
    if archived:
        print("收到新一版稿子：%s（第 %d 版），上一版已归入 %s。"
              % (slug, version, os.path.join(HISTORY_DIR, "v%d" % archived)))
    else:
        print("建好工作区：%s（第 %d 版）→ %s" % (slug, version, os.path.join(DRAFTS_DIR, slug)))
    line = "稿子：%s%s · %s" % (DRAFT_STEM, ext, _size_phrase(anchor.plain_text(text)))
    if had_brief or args.lang:
        line += " · 批语语言 %s" % brief["lang"]
    print(line)
    for note in intake_notes:
        print(note)
    if not brief["audience"] and not brief["purpose"]:
        print("下一步：先问清给谁看、要达到什么、最怕什么，写成 JSON 后跑 brief set %s --from <文件>；"
              "然后 context %s → 写 %s → review %s。"
              % (slug, slug, os.path.join(INBOX_DIR, MARKS_NAME), slug))
    else:
        print("下一步：context %s → 写 %s → review %s。"
              % (slug, os.path.join(INBOX_DIR, MARKS_NAME), slug))
    return 0


# ---------------------------------------------------------------- brief set

def cmd_brief(args):
    ws, slug = resolve(args.root, args.slug)
    brief = normalize_brief(read_json(args.source))
    write_json(os.path.join(ws, BRIEF_NAME), brief)
    print("写入 brief：%s" % slug)
    print("  给谁看：%s" % (brief["audience"] or "（还没写）"))
    print("  要达到：%s" % (brief["purpose"] or "（还没写）"))
    print("  最怕的：%s" % ("；".join(brief["worries"]) or "（还没写）"))
    print("brief 也进 context_hash：改过之后要重跑 context，旧批注作废。")
    return 0


# ---------------------------------------------------------------- context

def build_context(ws, slug):
    raw = read_text(require_draft(ws))
    ex = anchor.extract(raw)
    brief = read_brief(ws)
    return {
        "slug": slug,
        "version": version_of(ws),
        "brief": brief,
        "draft_text": ex.text,
        "context_hash": context_hash(ex.text, brief),
    }


def cmd_context(args):
    ws, slug = resolve(args.root, args.slug)
    print(json.dumps(build_context(ws, slug), ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- review

def next_snapshot(ws):
    hist = os.path.join(ws, HISTORY_DIR)
    seen = [0]
    if os.path.isdir(hist):
        seen += [int(m.group(1)) for m in
                 (SNAPSHOT_RE.match(f) for f in os.listdir(hist)) if m]
    return os.path.join(hist, SNAPSHOT_FMT % (max(seen) + 1))


def build_record(slug, version, digest, raw, draft_file, result):
    return {
        "slug": slug,
        "version": version,
        "at": now_iso(),
        "draft_file": draft_file,
        "draft_sha256": sha256_text(raw),
        "context_hash": digest,
        "anchored_ratio": result.anchored_ratio,
        "level_counts": level_counts(result.marks),
        "marks": result.marks,
    }


def render(slug, version, raw, result, draft_file):
    title = "红笔改稿：%s（第 %d 版）" % (slug, version)
    meta = {"稿子": draft_file, "版本": "第 %d 版" % version, "批注": "%d 条" % len(result.marks)}
    return anchor.render_page(title, raw, result, meta)


def cmd_review(args):
    ws, slug = resolve(args.root, args.slug)
    draft = require_draft(ws)
    raw = read_text(draft)
    brief = read_brief(ws)
    box = inbox_path(ws)
    if not os.path.isfile(box):
        raise UsageError("还没有待审的批注：先跑 context %s 拿上下文包，把批注写进 %s，再 review。"
                         % (slug, _shown(box)))
    errors, warnings, tidy, result, order = run_gates(raw, brief, read_json(box))
    for line in errors:
        print("[ERROR] %s" % line)
    for line in warnings:
        print("[WARN] %s" % line)
    if errors:
        print("%d 处不合格；marks.json 与 review.html 都没有写出。"
              "请改 %s 里的批注 —— 稿子不要动。" % (len(errors), os.path.join(INBOX_DIR, MARKS_NAME)))
        return 1

    version = version_of(ws)
    record = build_record(slug, version, tidy["context_hash"], raw, os.path.basename(draft), result)
    write_json(record_path(ws), record)
    write_text(os.path.join(ws, PAGE_NAME), render(slug, version, raw, result, record["draft_file"]))
    snapshot = next_snapshot(ws)
    write_json(snapshot, record)

    anchored = sum(1 for m in result.marks if m.get("anchored"))
    print("批注 %d 条 · 锚定率 %s（%d/%d）" % (len(result.marks), _pct(result.anchored_ratio),
                                              anchored, len(result.marks)))
    print(level_line(record["level_counts"]))
    print("写出：%s · %s" % (_shown(record_path(ws)), _shown(os.path.join(ws, PAGE_NAME))))
    print("留档：%s" % _shown(snapshot))
    for line in (partial_line(result.marks), order_line(order)):
        if line is not None:
            print(line)
    missed = [m for m in result.marks if not m.get("anchored")]
    if missed:
        print("有 %d 条没能定位，红笔页里单列一节 —— 脚本不擅自摆放，请把下面这几行原样念给用户。" % len(missed))
        for line in missed_lines(anchor.extract(raw), result.marks, order):
            print(line)
    return 0


# ---------------------------------------------------------------- stats

def previous_record(ws):
    """上一版归档的批注；没有就返回 (None, None)。"""
    seen = version_dirs(ws)
    if not seen:
        return None, None
    n = seen[-1]
    path = os.path.join(ws, HISTORY_DIR, "v%d" % n, MARKS_NAME)
    return (n, read_json(path)) if os.path.isfile(path) else (n, None)


def stale_reasons(ws, record, raw, brief, draft, with_hash=True):
    """只查新鲜度；check 用 with_hash=False，让 _gate_hash 单独报上下文作废。"""
    reasons = []
    if record.get("draft_sha256") != sha256_text(raw):
        reasons.append("marks.json 记的稿子哈希与现在的 %s 对不上：稿子改过了，请重跑 context 与 review。"
                       % os.path.basename(draft))
    elif with_hash and context_hash(anchor.extract(raw).text, brief) != record.get("context_hash"):
        reasons.append("marks.json 记的 context_hash 与当前稿子加 brief 算出来的对不上：brief 改过了，请重跑 context 与 review。")
    if record.get("version") != version_of(ws):
        reasons.append("marks.json 记的是第 %s 版，工作区现在是第 %d 版。"
                       % (record.get("version"), version_of(ws)))
    return reasons


def read_snapshots(ws):
    """按留档文件名依次读取各轮记录；不写回，也不改历史。"""
    hist = os.path.join(ws, HISTORY_DIR)
    if not os.path.isdir(hist):
        return []
    return [read_json(os.path.join(hist, name)) for name in sorted(os.listdir(hist))
            if SNAPSHOT_RE.match(name)]


def say_history(ws, raw, snaps):
    if not snaps:
        print("history/ 里还没有留档，看不出走势。")
        return
    print("留档 %d 份，按引文逐字对齐，不是同一条批注的身份——仍使用规范化与头尾锚定兜底，改过字也可能找得到；消失不等于问题解决。" % len(snaps))
    ex = anchor.extract(raw)
    for round_no, snap in enumerate(snaps, 1):
        marks = snap.get("marks") or []
        counts = snap.get("level_counts") or level_counts(marks)
        levels = " / ".join("%s %d" % (anchor.LEVEL_LABEL[lv], counts.get(lv, 0))
                            for lv in anchor.LEVELS)
        pinned = [m for m in marks if m.get("anchored")]
        remaining = sum(1 for m in pinned if anchor.locate(ex, m.get("quote") or "") is not None)
        print("第 %d 轮 · 第 %s 版 · %s · 批注 %d 条 · 钉住 %d 条 · %s · 当前稿里还剩 %d 条"
              % (round_no, snap.get("version"), snap.get("at"), len(marks),
                 len(pinned), levels, remaining))


def cmd_stats(args):
    ws, slug = resolve(args.root, args.slug)
    record = read_record(ws)
    draft = require_draft(ws)
    raw = read_text(draft)
    brief = read_brief(ws)
    stale = stale_reasons(ws, record, raw, brief, draft, with_hash=True)
    if stale:
        print("[作废] 这个工作区的结果已经作废，下面的数字都不作数，所以一个都不打：")
        for reason in stale:
            print("    - %s" % reason)
        print("按这三步重来：1) context %s 拿新的上下文包；2) 照新的 draft_text 重写 inbox/marks.json；3) review %s。" % (slug, slug))
        print("磁盘上的 review.html 是上一轮渲染的，别再拿它截图。")
        return 1
    marks = record.get("marks") or []
    anchored = sum(1 for m in marks if m.get("anchored"))
    print("%s（第 %d 版，%s）" % (slug, record.get("version", 1), record.get("at", "")))
    print("批注 %d 条 · 锚定率 %s（%d/%d）"
          % (len(marks), _pct(record.get("anchored_ratio") or 0.0), anchored, len(marks)))
    print(level_line(record.get("level_counts") or level_counts(marks)))
    with_fix = sum(1 for m in marks if m.get("fix"))
    print("给了改法的 %d 条，只指方向的 %d 条。" % (with_fix, len(marks) - with_fix))

    partial = partial_line(marks)
    if partial is not None:
        print(partial)
    ex = anchor.extract(raw)
    missed = [m for m in marks if not m.get("anchored")]
    if missed:
        print("有 %d 条没能定位，下面这几行原样念给用户：" % len(missed))
        for line in missed_lines(ex, marks):
            print(line)
    if args.history:
        say_history(ws, raw, read_snapshots(ws))

    n, prev = previous_record(ws)
    if n is None:
        print("这是第 1 版，还没有可比的上一版。")
        return 0
    if prev is None:
        print("上一版（第 %d 版）没有留下通过闸门的批注，无从比较。" % n)
        return 0
    old = prev.get("marks") or []
    pinned = [m for m in old if m.get("anchored")]
    loose = [m for m in old if not m.get("anchored")]
    gone = [m for m in pinned if anchor.locate(ex, m.get("quote") or "") is None]
    print("与上一版（第 %d 版）对比：上一版钉住的 %d 条批注里有 %d 条在新稿里消失了。"
          % (n, len(pinned), len(gone)))
    for m in gone:
        print("    %s：%s" % (anchor.LEVEL_LABEL.get(m.get("level"), "提示"), _cut(m.get("quote"), 50)))
    if not gone:
        print("上一版钉住的批注在新稿里都还在 —— 要么还没改，要么改动没碰到这些句子。")
        print("也可能句子改过但仍被规范化或头尾锚定找到，不能据此认定没有改动。")
    if loose:
        print("另有 %d 条上一版就没能定位，不参与这次比较——它们从来没钉在稿子上，「消失」说不上。" % len(loose))
    return 0


# ---------------------------------------------------------------- check

def cmd_check(args):
    ws, slug = resolve(args.root, args.slug)
    errors, warns = [], []
    draft = draft_path(ws)
    if draft is None:
        print("[ERROR] 工作区里没有稿子：%s" % _shown(ws))
        return 1
    raw = read_text(draft)
    try:
        brief = read_brief(ws)
    except UsageError as e:
        print("[ERROR] brief 不合规：%s" % _diagnostic(str(e)))
        return 1

    record_file = record_path(ws)
    if not os.path.isfile(record_file):
        print("[ERROR] 还没跑过 review：缺 %s" % _shown(record_file))
        return 1
    record = read_json(record_file)
    marks = record.get("marks") or []

    errors.extend(stale_reasons(ws, record, raw, brief, draft, with_hash=False))

    payload = {"context_hash": record.get("context_hash"),
               "marks": [dict((k, m[k]) for k in MARK_KEYS if k in m) for m in marks]}
    again, more_warns, _tidy, result, _order = run_gates(raw, brief, payload)
    errors.extend(again)
    warns.extend(more_warns)
    if result is not None:
        if abs((record.get("anchored_ratio") or 0.0) - result.anchored_ratio) > 1e-9:
            errors.append("marks.json 记的锚定率 %r 与重算的 %r 对不上。"
                          % (record.get("anchored_ratio"), result.anchored_ratio))
        if record.get("level_counts") != level_counts(result.marks):
            errors.append("marks.json 记的等级分布与重算的对不上。")
        page_file = os.path.join(ws, PAGE_NAME)
        if not os.path.isfile(page_file):
            errors.append("缺红笔页：%s" % _shown(page_file))
        elif read_text(page_file) != render(slug, record.get("version") or 1, raw, result,
                                            record.get("draft_file") or os.path.basename(draft)):
            errors.append("review.html 与由 marks.json 重新渲染出来的不一致：红笔页不能手改，请重跑 review。")

    hist = os.path.join(ws, HISTORY_DIR)
    snaps = sorted(f for f in os.listdir(hist) if SNAPSHOT_RE.match(f)) if os.path.isdir(hist) else []
    if not snaps:
        warns.append("history/ 里还没有留档，看不出改过几轮。")

    for line in errors:
        print("[ERROR] %s" % line)
    for line in warns:
        print("[WARN] %s" % line)
    print("check：%s 第 %s 版 · 批注 %d 条 · 锚定率 %s · 留档 %d 份 · %d ERROR / %d WARN"
          % (slug, record.get("version"), len(marks),
             _pct(record.get("anchored_ratio") or 0.0), len(snaps), len(errors), len(warns)))
    return 1 if errors else 0


# ---------------------------------------------------------------- export

def cmd_export(args):
    ws, slug = resolve(args.root, args.slug)
    record = read_record(ws)
    marks = record.get("marks") or []
    pack = {
        "slug": slug,
        "versions": record.get("version") or version_of(ws),
        "marks_count": len(marks),
        "partial_count": sum(1 for m in marks if m.get("partial")),
        "anchored_ratio": record.get("anchored_ratio") or 0.0,
        "level_counts": record.get("level_counts") or level_counts(marks),
        "context_hash": record.get("context_hash") or "",
    }
    print(json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------- doctor

SCAN_DEPTH = 4
SCAN_MAX_DIRS = 4000
SCAN_MAX_HITS = 20
SCAN_HOME_DIRS = tuple(os.path.join(os.path.expanduser("~"), name)
                       for name in ("", "Documents", "Desktop", "Downloads"))
_TEMPISH = re.compile(r"(?:^|[\\/])(?:[0-9]{8}-[0-9]{6}|[0-9]{4}(?:-[0-9]{2}){5})(?:[\\/]|$)")


def _drift_hint(root):
    return bool(_TEMPISH.search(os.path.abspath(root)))


def scan_bases(root):
    """默认起点与家目录／文稿目录不能有祖先或后代关系。"""
    bases = []
    for base in (os.path.abspath(root), os.path.dirname(os.path.abspath(root))):
        real = os.path.realpath(base)
        safe = True
        for protected in SCAN_HOME_DIRS:
            protected = os.path.realpath(protected)
            try:
                if os.path.commonpath((real, protected)) in (real, protected):
                    safe = False
                    break
            except ValueError:
                continue
        if safe and base not in bases:
            bases.append(base)
    return bases


def find_workspaces(base):
    """有界只读扫描；只收 drafts/<合法 slug>/marks.json，不跟随符号链接。"""
    result = {"hits": [], "limited": False, "unreadable": False, "invalid": False}
    visited = 0

    def visit(cur, depth):
        nonlocal visited
        if visited >= SCAN_MAX_DIRS:
            result["limited"] = True
            return
        visited += 1
        try:
            with os.scandir(cur) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if os.path.basename(cur) == DRAFTS_DIR:
                        # drafts 到此为止，不能下钻 inbox、history 或其它项目。
                        if not SLUG_RE.fullmatch(entry.name):
                            continue
                        if visited >= SCAN_MAX_DIRS:
                            result["limited"] = True
                            break
                        visited += 1
                        path = os.path.join(entry.path, MARKS_NAME)
                        if os.path.islink(path) or not os.path.isfile(path):
                            continue
                        try:
                            with open(path, encoding="utf-8-sig") as stream:
                                record = json.load(stream)
                            if (not isinstance(record, dict) or record.get("slug") != entry.name
                                    or not isinstance(record.get("marks"), list)
                                    or not isinstance(record.get("at"), str)
                                    or "T" not in record["at"]):
                                raise ValueError("invalid record")
                            datetime.datetime.fromisoformat(record["at"])
                        except (ValueError, UnicodeError):
                            result["invalid"] = True
                            continue
                        except OSError:
                            result["unreadable"] = True
                            continue
                        result["hits"].append((entry.name, os.path.abspath(entry.path), record["at"]))
                    elif depth >= SCAN_DEPTH:
                        result["limited"] = True
                    else:
                        visit(entry.path, depth + 1)
                        if visited >= SCAN_MAX_DIRS:
                            result["limited"] = True
                            break
        except OSError:
            result["unreadable"] = True

    base = os.path.abspath(base)
    if os.path.islink(base):
        result["unreadable"] = True
    else:
        visit(base, 0)
    return result


def scan_report(hits):
    """仅报告结构命中的目录；错误与截断提示永不带无关目录名。"""
    groups = {}
    for slug, path, at in sorted(set(hits["hits"])):
        groups.setdefault(slug, []).append((path, at))
    for slug in sorted(groups)[:SCAN_MAX_HITS]:
        print("  %s 在 %d 处：" % (slug, len(groups[slug])))
        for path, at in groups[slug]:
            print("    %s · %s" % (path, at))
    if len(groups) > SCAN_MAX_HITS:
        print("还有 %d 个没列出来。" % (len(groups) - SCAN_MAX_HITS))
    if not groups:
        print("没有找到可报告的红笔工作区。")
    if hits["limited"]:
        print("达到扫描深度或目录数上限，结果可能不全，用 --scan <目录> 指个准的。")
    if hits["unreadable"]:
        print("有目录或记录无法读取，或起点是符号链接；结果可能不全，用 --scan <目录> 指个准的。")
    if hits["invalid"]:
        print("跳过了格式不完整或损坏的 marks.json。")
    if groups:
        print("扫描只报告，不搬任何文件。要把历史接起来，请先选固定工作区，自己按 history/v<N>/ "
              "布局整理各版稿子与产物，保留原文件并避免覆盖；搬完跑 check，哈希或版本对不上就重跑 context 与 review。")


def cmd_doctor(args):
    root = _abs(args.root)
    print("red-pen 环境检查（redpen.py 由 Python %d.%d.%d 运行，%s）"
          % (sys.version_info[0], sys.version_info[1], sys.version_info[2], sys.platform))
    worst = 0
    if sys.version_info < (3, 8):
        print("  [缺失] Python 3.8+ —— 当前版本太低，脚本跑不起来")
        worst = 2
    else:
        print("  [OK]   Python %d.%d" % (sys.version_info[0], sys.version_info[1]))
    here = os.path.dirname(os.path.abspath(__file__))
    for name, what in (("anchor.py", "锚定批注引擎"), ("banned_words.py", "禁用词静态闸")):
        if os.path.isfile(os.path.join(here, name)):
            print("  [OK]   %s（%s）" % (what, name))
        else:
            print("  [缺失] %s（%s）—— 整个 scripts/ 一起拷贝才完整" % (what, name))
            worst = 2
    base = os.path.join(root, DRAFTS_DIR)
    slugs = sorted(d for d in os.listdir(base)
                   if SLUG_RE.fullmatch(d) and os.path.isdir(os.path.join(base, d))) if args.scan is None and os.path.isdir(base) else []
    if args.scan is not None:
        print("  [提示] 工作区根目录 %s；扫描结果只列有效记录。" % _abs(root))
    elif slugs:
        print("  [OK]   工作区根目录 %s（已有 %d 份稿子：%s）"
              % (_abs(root), len(slugs), "、".join(slugs[:6]) + ("…" if len(slugs) > 6 else "")))
    else:
        print("  [提示] 工作区根目录 %s 下还没有 %s/，init 时会建" % (_abs(root), DRAFTS_DIR))
    print("提示：脚本只读写工作区，不联网，不执行稿子里的任何代码；稿子本身一个字都不改。")
    print("      docx 只读 %s 里的文字段落：表格按行读出、整行可以引，跨行引不了，文本框的文字按位置读一次；"
          "图片与修订痕迹不支持。" % WORD_MAIN)
    if _drift_hint(root):
        print("看着像宿主给每个任务新建的临时目录：历轮批注会落进不同目录，stats 就比不出『上一版哪几条消失了』，先选固定文件夹或每次带 --root。")
    if args.scan is not None:
        bases = [os.path.abspath(args.scan)] if args.scan else scan_bases(root)
        if not bases:
            print("默认起点里没有安全可扫的目录，用 --scan <目录> 指一个准的。")
        else:
            hits = {"hits": [], "limited": False, "unreadable": False, "invalid": False}
            for base in bases:
                found = find_workspaces(base)
                hits["hits"].extend(found["hits"])
                for key in ("limited", "unreadable", "invalid"):
                    hits[key] = hits[key] or found[key]
            scan_report(hits)
    print("这行绝对路径是给你自己核对用的，别抄进交给别人的报告或产物里。")
    return worst


# ---------------------------------------------------------------- 入口

SUBCOMMANDS = ("doctor", "init", "brief", "context", "review", "stats", "check", "export")
USAGE_ZH = """用法：python3 redpen.py [--root <工作区>] <子命令> [参数]

子命令：
  doctor                              查看本机环境与工作区
  init <稿件名> --from <文件>          收一份稿子；正文与后缀没变就不升版本
  brief set <稿件名> --from <文件>     写入给谁看、要达到什么、最怕什么
  context <稿件名>                     输出上下文包
  review <稿件名>                      跑闸门并锚定批注，写红笔页
  stats <稿件名>                       查看锚定率、等级分布与上一版对比
  check <稿件名或目录>                 离线复核整个工作区
  export <稿件名>                      导出只有哈希与计数的脱敏证据

--root 写在子命令前面或后面都认，建议只给一次；默认使用当前目录。
前后各给一次时，按当前目录转成绝对路径后相同才接受，不同则退出 2。
-h、--help 查看本说明；子命令后加 -h 查看该命令的参数。"""


def _argparse_zh(message):
    """翻译四类参数错误，保留选项名与可选值供用户纠正。"""
    choice = re.match(r"argument (.+?): invalid choice: (.*?) \(choose from (.*)\)$", message)
    if choice:
        argument, value, choices = choice.groups()
        if argument == "command":
            return "没有这个子命令，可用的是：%s。请从中选一个。" % "、".join(SUBCOMMANDS)
        return "参数 %s 的值不对：%s。可用的是：%s。请改用其中一个值。" % (argument, value, choices)
    if message.startswith("unrecognized arguments: "):
        return "这个参数放错位置了：%s。请检查拼写与位置，用 -h 查看参数。" % message.split(": ", 1)[1]
    if message.startswith("the following arguments are required: "):
        return "少了必填参数：%s。请补齐后重试。" % message.split(": ", 1)[1]
    expected = re.match(r"argument (.+?): expected one argument$", message)
    if expected:
        return "这个选项后面要跟一个值：%s。请补上值后重试。" % expected.group(1)
    return "参数用法有误：%s。请用 -h 查看参数。" % message


class Parser(argparse.ArgumentParser):
    def parse_known_args(self, args=None, namespace=None):
        self._input_args = list(sys.argv[1:] if args is None else args)
        return super().parse_known_args(args, namespace)

    def error(self, message):
        for value in sorted(getattr(self, "_input_args", []), key=len, reverse=True):
            candidate = value.split("=", 1)[-1] if value.startswith("--") else value
            if candidate:
                label = _metadata(candidate)
                message = message.replace(repr(candidate), repr(label)).replace(candidate, label)
        self.exit(2, "错误：%s\n" % _diagnostic(_argparse_zh(message)))


class _HelpZh(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(USAGE_ZH)
        parser.exit()


def build_parser():
    p = Parser(prog="redpen.py", description="red-pen 红笔改稿脚本", add_help=False)
    p.add_argument("-h", "--help", action=_HelpZh, nargs=0, help="查看中文用法")
    p.add_argument("--root", default=None, help="工作区根目录（默认当前目录，其下是 drafts/<slug>/）")
    sub = p.add_subparsers(dest="command")

    def add(name, helptext):
        one = sub.add_parser(name, help=helptext)
        one.add_argument("--root", dest="sub_root", default=argparse.SUPPRESS,
                         help="工作区根目录（也可写在子命令前面）")
        return one

    doctor = add("doctor", "查看本机环境与工作区")
    doctor.add_argument("--scan", nargs="?", const="", default=None,
                        help="只报告散落的红笔工作区；可显式指定扫描目录")

    i = add("init", "收一份稿子建工作区；正文与后缀没变就不升版本")
    i.add_argument("slug")
    i.add_argument("--from", dest="source", required=True, help="稿子文件（.md / .html / .txt / .docx）；给 - 表示从标准输入收稿")
    i.add_argument("--lang", choices=LANGS, help="批语语言（默认 zh）")

    b = add("brief", "写入给谁看 / 要达到什么 / 最怕什么")
    b.add_argument("action", choices=("set",))
    b.add_argument("slug")
    b.add_argument("--from", dest="source", required=True, help="brief 的 JSON 文件")

    for name, helptext in (("context", "输出上下文包 JSON"),
                           ("review", "跑闸门并锚定批注，写红笔页"),
                           ("check", "离线复核整个工作区"),
                           ("export", "导出脱敏证据")):
        one = add(name, helptext)
        one.add_argument("slug", help="工作区 slug，或直接给工作区目录")
    s = add("stats", "锚定率、等级分布、与上一版的对比")
    s.add_argument("slug", help="工作区 slug，或直接给工作区目录")
    s.add_argument("--history", action="store_true", help="逐份读 history/review-*.json，看多版走势")
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"doctor": cmd_doctor, "init": cmd_init, "brief": cmd_brief,
                "context": cmd_context, "review": cmd_review, "stats": cmd_stats,
                "check": cmd_check, "export": cmd_export}
    if not args.command:
        print(USAGE_ZH)
        return 2
    try:
        inner = getattr(args, "sub_root", None)
        top = args.root
        if inner is not None and top is not None and os.path.abspath(inner) != os.path.abspath(top):
            raise UsageError("--root 给了两次而且不一样，只能给一个工作区。")
        args.root = inner or top or "."
        _set_root(args.root)
        return handlers[args.command](args)
    except UsageError as e:
        print("错误：%s" % _diagnostic(str(e)), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 2
    except OSError as e:
        filenames = [getattr(e, key, None) for key in ("filename", "filename2")]
        shown = "、".join(_source_label(path) if path == getattr(args, "source", None)
                         else _shown(path) for path in filenames if path)
        print("错误：文件操作失败（%s，错误码 %s）%s。请检查文件类型与访问权限。"
              % (type(e).__name__, e.errno, "：" + shown if shown else ""), file=sys.stderr)
        return 2
    except Exception as e:
        print("错误：%s：%s" % (type(e).__name__, _diagnostic(str(e))), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
