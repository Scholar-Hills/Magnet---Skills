# -*- coding: utf-8 -*-
"""应用层与 red-pen 引擎之间的只读桥。

这里**不生成也不修改**任何引擎产物：`marks.json`、`review.html`、
`history/` 全部由 `redpen.py` 写出。本模块只做两件事：

1. 把引擎定位到的批注区间，换算成「纯文本坐标」，让应用层能按自己的
   版式渲染原文与批注（引擎的坐标落在消毒后的 HTML 上，应用渲染的是
   `draft_text`，两者不是一套坐标系）。
2. 读引擎写出的记录（`marks.json`）与上下文包，供接口层直接使用。

换算复用引擎自己的定位函数 `anchor._search()`：它和 `anchor.locate()`
走同一条分支（精确 → 剥首尾标点 → 头尾锚定），所以「引擎说钉住了」
与「应用算出的区间」永远是同一个答案。引擎升级后若私有函数改名，
`_plain_span()` 会退到精确子串匹配并在结果里标 `degraded`，不会静默错位。
"""

import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(APP_DIR, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import anchor  # noqa: E402  引擎模块（随 engine/ 同步进来）
import redpen  # noqa: E402

LEVEL_TEXT = {"major": "需要处理", "minor": "可以改进", "remark": "供你参考"}
LEVEL_ORDER = {"major": 0, "minor": 1, "remark": 2}

# 引擎未定位原因的中文说法，与 redpen.why_missed() 的三个返回值一一对应。
REASON_TEXT = {
    redpen.WHY_OVERLAP: "与另一条批注覆盖了同一段原文，脚本保留了靠前的那条",
    redpen.WHY_CROSS: "这句横跨了两个段落，引擎不做跨段落定位",
    redpen.WHY_MISSING: "在稿件正文里找不到这一句，引文可能抄得不准",
}


class EngineMissing(Exception):
    """engine/ 里没有引擎脚本。"""


def engine_ready():
    return all(os.path.isfile(os.path.join(ENGINE_DIR, name))
               for name in ("redpen.py", "anchor.py"))


def _extraction(raw):
    """引擎的提取对象。

    必须拿**稿子原文**（draft.* 的内容）来提取，不能拿 draft_text 再提取一次：
    块边界是提取阶段的零宽区间，draft_text 里只剩一个换行符，再提取就分不出段了。
    """
    return anchor.extract(raw)


def _plain_span(ex, quote):
    """引文在纯文本里的 (start, end, partial)；钉不住返回 None。"""
    if not quote:
        return None
    # 先问引擎「这条到底钉住没有」——跨段落的引文在这里就会被否掉。
    if anchor.locate(ex, quote) is None:
        return None
    try:
        hit = anchor._search(ex, quote)
    except Exception:
        hit = None
    if hit is not None:
        back, lo, hi, partial = hit
        if hi > lo:
            start, end = back[lo], back[hi - 1] + 1
            if 0 <= start < end <= len(ex.text):
                return start, end, bool(partial)
    # 兜底：引擎私有函数改名时，退到精确子串匹配（坐标仍然可信，只是少了规范化）。
    pos = ex.text.find(quote)
    if pos >= 0:
        return pos, pos + len(quote), False
    return None


def blocks_of(ex):
    """按引擎的块边界切段，返回 [{start, end, text}]。"""
    out = []
    for start, end in anchor.blocks(ex):
        chunk = ex.text[start:end]
        text = chunk.strip("\n")
        if not text.strip():
            continue
        lead = len(chunk) - len(chunk.lstrip("\n"))
        out.append({"start": start + lead, "end": start + lead + len(text), "text": text})
    if not out and ex.text.strip():
        out.append({"start": 0, "end": len(ex.text), "text": ex.text.strip("\n")})
    return out


def _block_index(blocks, offset):
    for i, blk in enumerate(blocks):
        if blk["start"] <= offset < blk["end"]:
            return i
    if blocks and offset >= blocks[-1]["end"]:
        return len(blocks) - 1
    return 0


def view_model(raw_draft, record, draft_text=None):
    """把引擎记录翻成前端要的结构：分段、定位区间、未定位原因。

    `raw_draft` 是 draft.* 的原文；`draft_text` 可选，传进来就核对一次——
    两者不一致说明引擎抽文本的口径变了，宁可报错也不要拿错坐标去画下划线。
    """
    ex = _extraction(raw_draft)
    if draft_text is not None and draft_text != ex.text:
        raise ValueError("draft_text 与重新提取的正文不一致，拒绝渲染")
    blocks = blocks_of(ex)
    marks = []
    for m in record.get("marks") or []:
        item = {
            "id": m.get("id"),
            "level": m.get("level"),
            "level_text": LEVEL_TEXT.get(m.get("level"), "供你参考"),
            "note": m.get("note") or "",
            "fix": m.get("fix") or "",
            "quote": m.get("quote") or "",
            "anchored": bool(m.get("anchored")),
            "partial": bool(m.get("partial")),
            "dropped_overlap": bool(m.get("dropped_overlap")),
        }
        span = _plain_span(ex, item["quote"]) if item["anchored"] else None
        if span is not None:
            start, end, partial = span
            idx = _block_index(blocks, start)
            item["block"] = idx
            item["start"] = start - blocks[idx]["start"]
            item["end"] = min(end, blocks[idx]["end"]) - blocks[idx]["start"]
            item["partial"] = item["partial"] or partial
        else:
            item["block"] = None
            item["start"] = None
            item["end"] = None
            if item["anchored"]:
                # 引擎说钉住了，应用这边换算不出来：标成降级，不假装摆好了。
                item["anchored"] = False
                item["reason"] = "定位结果无法换算到阅读版式，请以下载的红笔稿为准"
            else:
                item["reason"] = REASON_TEXT.get(redpen.why_missed(ex, m), "没能定位")
        marks.append(item)

    located = [m for m in marks if m["anchored"]]
    located.sort(key=lambda m: (m["block"], m["start"]))
    unlocated = [m for m in marks if not m["anchored"]]

    # 「先看这几条」：先按等级、再按在稿件里的先后，取前三。
    priority = sorted(located, key=lambda m: (LEVEL_ORDER.get(m["level"], 2), m["block"], m["start"]))[:3]

    return {
        "blocks": blocks,
        "marks": located,
        "unlocated": unlocated,
        "priority": [m["id"] for m in priority],
        "anchored_count": len(located),
        "total": len(marks),
    }


def read_context(root, slug="draft-01"):
    """引擎的上下文包：draft_text / brief / version / context_hash。"""
    ws = os.path.join(root, "drafts", slug)
    return redpen.build_context(ws, slug)


def read_record(root, slug="draft-01"):
    ws = os.path.join(root, "drafts", slug)
    path = redpen.record_path(ws)
    if not os.path.isfile(path):
        return None
    return redpen.read_json(path)


def version_of(root, slug="draft-01"):
    return redpen.version_of(os.path.join(root, "drafts", slug))


def draft_raw(root, slug="draft-01"):
    ws = os.path.join(root, "drafts", slug)
    path = redpen.draft_path(ws)
    if path is None:
        return None
    return redpen.read_text(path)


def brief_of(root, slug="draft-01"):
    ws = os.path.join(root, "drafts", slug)
    return redpen.read_brief(ws)
