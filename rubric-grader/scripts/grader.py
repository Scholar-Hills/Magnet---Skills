#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rubric-grader 判卷脚本（零依赖，Python 3.8+ 标准库，单文件）。

老师给题目、评分标准与条目表，Agent 只负责说「这一条命中没有、哪一句是证据、
哪一句要提醒」，本脚本负责把它钉回作答原文、核它没有胡说，再渲染成判题卡。

子命令：
  doctor                                  查看本机环境与引擎
  init <job-dir> --max <int> [--lang zh|en] [--max-notes 12] [--min-anchored 0.7]
                                          建题批次骨架
  rubric set <job-dir> --from <file>      写入条目表（老师确认后再交）
  context <job-dir> <answer>              输出上下文包 JSON（含 context_hash）
  oracle check <job-dir>                  满分范例与残缺版都判对了才准开批
  grade <job-dir> <student-id>            读 inbox 的评分结果，跑闸门，写 results
  summary <job-dir>                       全班汇总（只统计已通过的结果）
  check <job-dir>                         离线复核整个题批次
  export <job-dir> [--out <file>]         导出脱敏证据（只有哈希、分数、判定、锚定率）

退出码：0 通过 / 1 闸门未过 / 2 用法或前置条件错误。

工作区与 JSON 契约见 references/workspace-format.md；纪律见 references/rules.md。
脚本只读写题批次目录，不联网；作答里的 HTML 会先经引擎消毒再进判题卡。
"""

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchor  # noqa: E402


class UsageError(Exception):
    """用法或前置条件错误，退出码 2。"""


VERDICTS = ("hit", "partial", "miss")
PAYLOAD_KEYS = ("context_hash", "points", "summary", "criteria", "marks")
CRITERION_KEYS = ("name", "verdict", "quote")
MARK_KEYS = ("quote", "level", "note")

JOB_FILE = "job.json"
QUESTION_FILE = "question.md"
RUBRIC_FILE = "rubric.md"
STAMP_FILE = os.path.join(".stamps", "oracle.json")
ORACLE_FULL = os.path.join("oracle", "full.md")
ORACLE_BROKEN = os.path.join("oracle", "broken.md")
ORACLE_BROKEN_LIST = os.path.join("oracle", "broken.json")
SUB_DIRS = ("oracle", "answers", "inbox", "results")

LANGS = ("zh", "en")
DEFAULT_MAX_NOTES = 12
DEFAULT_MIN_ANCHORED = 0.7
SUMMARY_MIN_WORDS = 60
SUMMARY_MAX_WORDS = 200
NOTE_MIN_CHARS = 6
SIMILARITY_CAP = 0.8
HOLLOW_QUOTE_CHARS = 6
GRAM = 3

# 对抗作答：老师放进 answers/ 的假作答，文件名以此开头。批出 0 分以外的任何结果，
# 都说明这一轮的批改在白给分，整个题批次的分数都不可信。
BASE_PREFIX = "base-"

ANSWER_EXTS = (".md", ".txt", ".html", ".htm", ".docx")

# 「第 3 题」式逐题复述：总评是给这一份作答的整体评价，不是把评分标准再抄一遍。
PER_ITEM_RECAP = re.compile(r"第\s*[0-9０-９一二三四五六七八九十百]{1,3}\s*[题題问問]")


# ---------------------------------------------------------------- 小工具

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
        return read_text(path)
    except UsageError:
        return ""


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_json(path):
    text = read_text(path)
    try:
        return json.loads(text)
    except ValueError as e:
        raise UsageError("JSON 解析失败：%s（%s）" % (path, e))


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n")


def canonical(obj):
    """算哈希用的规范写法：键排序、不转义非 ASCII、无多余空白。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def count_words(text, lang):
    """中文按字符（去掉空白）、英文按空白分词；判据是 job.json 的 lang。"""
    body = text or ""
    if lang == "en":
        return len([w for w in re.split(r"\s+", body.strip()) if w])
    return len(re.sub(r"\s+", "", body))


def grams(text, size=GRAM):
    body = re.sub(r"\s+", "", anchor.normalize(text or "")).lower()
    return set(body[i:i + size] for i in range(len(body) - size + 1))


def jaccard(left, right):
    if not left and not right:
        return 0.0
    union = left | right
    return round(len(left & right) / len(union), 4) if union else 0.0


def docx_text(path):
    """docx 只抽段落文字（zipfile + 正则），图片与图表里的内容抽不出来，也不猜。"""
    try:
        with zipfile.ZipFile(path) as pack:
            raw = pack.read("word/document.xml").decode("utf-8", "replace")
    except (KeyError, OSError, zipfile.BadZipFile) as e:
        raise UsageError("读不出 docx 的正文：%s（%s）" % (path, e))
    lines = []
    for block in re.findall(r"<w:p[^>]*>(.*?)</w:p>", raw, re.S):
        joined = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", block, re.S))
        line = html.unescape(joined).strip()
        if line:
            lines.append(line)
    if not lines:
        raise UsageError("docx 里没有抽到任何文字：%s（图片作答不支持，请老师转成文字）" % path)
    return "\n\n".join(lines)


def read_answer(path):
    """作答原文：Markdown / HTML / 纯文本直接读，docx 抽段落文字。"""
    if path.lower().endswith(".docx"):
        return docx_text(path)
    return read_text(path)


# ---------------------------------------------------------------- 题批次

class Job:
    """一个题批次目录：job.json + 题干 + 评分标准 + 条目表，读进来就不再碰磁盘。"""

    def __init__(self, job_dir):
        self.dir = os.path.abspath(job_dir)
        if not os.path.isdir(self.dir):
            raise UsageError("题批次目录不存在：%s" % job_dir)
        if not os.path.isfile(self.path(JOB_FILE)):
            raise UsageError("这不像一个题批次目录（缺 %s）：%s" % (JOB_FILE, job_dir))
        meta = read_json(self.path(JOB_FILE))
        if not isinstance(meta, dict):
            raise UsageError("%s 必须是一个 JSON 对象" % JOB_FILE)
        self.meta = meta
        self.slug = str(meta.get("slug") or os.path.basename(self.dir))
        self.max = meta.get("max")
        if not is_int(self.max) or self.max < 1:
            raise UsageError("%s 的 max 必须是不小于 1 的整数，当前是：%r" % (JOB_FILE, self.max))
        self.lang = meta.get("lang", "zh")
        if self.lang not in LANGS:
            raise UsageError("%s 的 lang 只能是 zh 或 en，当前是：%r" % (JOB_FILE, self.lang))
        self.max_notes = meta.get("max_notes", DEFAULT_MAX_NOTES)
        if not is_int(self.max_notes) or self.max_notes < 1:
            raise UsageError("%s 的 max_notes 必须是不小于 1 的整数，当前是：%r" % (JOB_FILE, self.max_notes))
        self.min_anchored = meta.get("min_anchored", DEFAULT_MIN_ANCHORED)
        if not isinstance(self.min_anchored, (int, float)) or isinstance(self.min_anchored, bool) \
                or not 0 <= self.min_anchored <= 1:
            raise UsageError("%s 的 min_anchored 必须是 0～1 之间的小数，当前是：%r"
                             % (JOB_FILE, self.min_anchored))
        self.criteria = meta.get("criteria") or []
        if not isinstance(self.criteria, list):
            raise UsageError("%s 的 criteria 必须是一个列表" % JOB_FILE)
        self.question_text = anchor.plain_text(read_text_or_empty(self.path(QUESTION_FILE)))
        self.rubric_text = anchor.plain_text(read_text_or_empty(self.path(RUBRIC_FILE)))

    # ---- 路径

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def answer_path(self, student):
        for ext in ANSWER_EXTS:
            candidate = self.path("answers", student + ext)
            if os.path.isfile(candidate):
                return candidate
        raise UsageError("找不到 %s 的作答文件：answers/%s%s（支持 %s）"
                         % (student, student, ANSWER_EXTS[0], "、".join(ANSWER_EXTS)))

    def answer_of(self, student):
        return read_answer(self.answer_path(student))

    def students(self):
        folder = self.path("answers")
        if not os.path.isdir(folder):
            return []
        found = set()
        for name in os.listdir(folder):
            stem, ext = os.path.splitext(name)
            if ext.lower() in ANSWER_EXTS and stem:
                found.add(stem)
        return sorted(found)

    def result_ids(self):
        folder = self.path("results")
        if not os.path.isdir(folder):
            return []
        return sorted(os.path.splitext(n)[0] for n in os.listdir(folder) if n.endswith(".json"))

    # ---- 条目表

    @property
    def names(self):
        return [str(c.get("name") or "") for c in self.criteria if isinstance(c, dict)]

    @property
    def weighted(self):
        """条目表带不带分值。不带分值时 points 只受 0 <= points <= max 约束。"""
        return bool(self.criteria) and all(
            isinstance(c, dict) and is_int(c.get("points")) for c in self.criteria)

    def expected_points(self, verdicts):
        """hit 拿满、partial 拿一半向下取整、miss 拿 0；不带分值时返回 None。"""
        if not self.weighted:
            return None
        total = 0
        for item, verdict in zip(self.criteria, verdicts):
            points = int(item["points"])
            if verdict == "hit":
                total += points
            elif verdict == "partial":
                total += points // 2
        return total

    # ---- 上下文

    def context_body(self, answer_text):
        return {"question_text": self.question_text,
                "rubric_text": self.rubric_text,
                "criteria": self.criteria,
                "answer_text": anchor.plain_text(answer_text),
                "max": self.max,
                "lang": self.lang}

    def context_hash(self, answer_text):
        return sha256_text(canonical(self.context_body(answer_text)))

    def context_pack(self, answer_text):
        pack = dict(self.context_body(answer_text))
        pack.update({"job": self.slug,
                     "max_notes": self.max_notes,
                     "min_anchored": self.min_anchored,
                     "context_hash": self.context_hash(answer_text)})
        return pack


def load_criteria(job_dir):
    """读一个题批次的条目表（供别的脚本复用）。"""
    return Job(job_dir).criteria


def compute_context_hash(job_dir, answer_text):
    """sha256(规范 JSON{question_text, rubric_text, criteria, answer_text, max, lang})。"""
    return Job(job_dir).context_hash(answer_text)


# ---------------------------------------------------------------- 闸门

def gate_keys(payload):
    """闸门 2 上半：顶层键白名单，多一个少一个都拒收。"""
    errors = []
    extra = [k for k in sorted(payload) if k not in PAYLOAD_KEYS]
    if extra:
        errors.append("评分结果里有契约外的顶层键：%s；只接受 %s"
                      % ("、".join(extra), "、".join(PAYLOAD_KEYS)))
    missing = [k for k in PAYLOAD_KEYS if k not in payload]
    if missing:
        errors.append("评分结果缺少顶层键：%s" % "、".join(missing))
    return errors


def gate_context(job, answer_text, payload):
    """闸门 1：上下文哈希必须等于当前重算值。"""
    given = payload.get("context_hash")
    if not isinstance(given, str) or not given:
        return ["缺 context_hash：请先跑 context 拿到上下文包，再照着它写评分结果"]
    want = job.context_hash(answer_text)
    if given != want:
        return ["context_hash 与当前重算值不一致（作答、题干、评分标准或条目表改过，"
                "或这份结果不是照着 context 写的）：给的 %s…，当前 %s…" % (given[:12], want[:12])]
    return []


def _ordered_criteria(job, payload):
    """把提交的条目按条目表顺序排好；对不上时返回 (None, 原因列表)。"""
    items = payload.get("criteria")
    if not isinstance(items, list):
        return None, ["criteria 必须是一个列表"]
    errors = []
    seen = {}
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append("criteria 第 %d 项不是对象" % i)
            continue
        stray = [k for k in sorted(item) if k not in CRITERION_KEYS]
        if stray:
            errors.append("条目「%s」有契约外的键：%s；只接受 %s"
                          % (item.get("name"), "、".join(stray), "、".join(CRITERION_KEYS)))
        name = str(item.get("name") or "")
        if name in seen:
            errors.append("条目「%s」提交了两次" % name)
        seen[name] = item
    if errors:
        return None, errors
    absent = [n for n in job.names if n not in seen]
    extra = [n for n in sorted(seen) if n not in job.names]
    if absent:
        errors.append("criteria 少了条目表里的：%s" % "、".join(absent))
    if extra:
        errors.append("criteria 多了条目表以外的：%s" % "、".join(extra))
    if errors:
        return None, errors
    return [seen[n] for n in job.names], []


def gate_points(job, payload, ordered):
    """闸门 2 下半：points 是整数、在 0～满分之间、与条目分值一致。"""
    errors = []
    points = payload.get("points")
    if not is_int(points):
        return ["points 必须是整数，当前是：%r" % (points,)]
    if points < 0 or points > job.max:
        errors.append("points 必须在 0～%d 之间，当前是 %d" % (job.max, points))
    if ordered is None:
        return errors
    verdicts = [str(c.get("verdict") or "") for c in ordered]
    if any(v not in VERDICTS for v in verdicts):
        return errors
    want = job.expected_points(verdicts)
    if want is not None and want != points:
        errors.append("points 与条目判定对不上：按条目分值应为 %d，提交的是 %d"
                      "（hit 拿满分、partial 拿一半向下取整、miss 拿 0）" % (want, points))
    return errors


def gate_criteria(job, answer_text, payload, ordered):
    """闸门 3：条目一一对应；hit / partial 的引文必须能锚回作答原文。

    锚不到的照规矩降为 miss 并记 evidence_unanchored；若因此分数变了就整份退回，
    让 Agent 重批 —— 不许脚本替它把分数改小。
    """
    errors, cautions, normalized = [], [], []
    if ordered is None:
        return errors, cautions, normalized
    ex = anchor.extract(answer_text)
    degraded = []
    for item in ordered:
        name = str(item.get("name") or "")
        verdict = str(item.get("verdict") or "")
        quote = str(item.get("quote") or "")
        entry = {"name": name, "verdict": verdict, "quote": quote, "evidence_unanchored": False}
        if verdict not in VERDICTS:
            errors.append("条目「%s」的 verdict 只能是 %s，当前是：%r"
                          % (name, " / ".join(VERDICTS), item.get("verdict")))
            normalized.append(entry)
            continue
        if verdict in ("hit", "partial"):
            if not quote.strip():
                errors.append("条目「%s」判 %s 却没给引文；判定要有原文撑着" % (name, verdict))
            elif anchor.locate(ex, quote) is None:
                entry["verdict"] = "miss"
                entry["evidence_unanchored"] = True
                degraded.append(name)
        normalized.append(entry)
    if degraded:
        want = job.expected_points([c["verdict"] for c in normalized])
        given = payload.get("points")
        detail = "、".join("「%s」" % n for n in degraded)
        if want is not None and is_int(given) and want != given:
            errors.append("条目%s判了 hit / partial，引文却锚不回作答原文，按规矩降为 miss；"
                          "降完分数从 %d 变成 %d，整份退回重批" % (detail, given, want))
        else:
            cautions.append("条目%s的引文锚不回作答原文，已降为 miss（分数没变，已记 evidence_unanchored）"
                            % detail)
    return errors, cautions, normalized


def gate_marks(job, answer_text, payload):
    """闸门 4：条数、引文、批语长度、锚定率、批语重复。返回 (错误, 提醒, 锚定结果)。"""
    errors, cautions = [], []
    items = payload.get("marks")
    if not isinstance(items, list):
        return ["marks 必须是一个列表"], cautions, anchor.annotate(answer_text, [])
    if len(items) > job.max_notes:
        errors.append("marks 有 %d 条，超过上限 %d 条（在 %s 的 max_notes 里改）"
                      % (len(items), job.max_notes, JOB_FILE))
    clean = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append("marks 第 %d 条不是对象" % i)
            continue
        stray = [k for k in sorted(item) if k not in MARK_KEYS]
        if stray:
            errors.append("marks 第 %d 条有契约外的键：%s；只接受 %s"
                          % (i, "、".join(stray), "、".join(MARK_KEYS)))
        quote = str(item.get("quote") or "")
        note = str(item.get("note") or "")
        if not quote.strip():
            errors.append("marks 第 %d 条没给引文" % i)
        if len(note.strip()) < NOTE_MIN_CHARS:
            errors.append("marks 第 %d 条的批语只有 %d 字，至少要 %d 字"
                          % (i, len(note.strip()), NOTE_MIN_CHARS))
        clean.append({"quote": quote, "level": item.get("level", anchor.DEFAULT_LEVEL), "note": note})

    seen = {}
    for i, item in enumerate(clean, 1):
        key = anchor.normalize(item["note"])
        if key and key in seen:
            errors.append("marks 第 %d 条与第 %d 条的批语完全相同；同一句话不必说两遍"
                          % (seen[key], i))
        seen.setdefault(key, i)

    result = anchor.annotate(answer_text, clean)
    if clean and result.anchored_ratio < job.min_anchored:
        lost = ["「%s」" % m["quote"][:24] for m in result.marks if not m.get("anchored")]
        errors.append("锚定率只有 %.2f，低于 %s 要求的 %.2f；锚不上的引文：%s"
                      % (result.anchored_ratio, JOB_FILE, job.min_anchored, "、".join(lost)))
    fixed = [m["id"] for m in result.marks if m.get("level_fixed")]
    if fixed:
        cautions.append("第 %s 条的 level 不在白名单里，已按默认等级处理"
                        % "、".join(str(i) for i in fixed))
    dropped = [m["id"] for m in result.marks if m.get("dropped_overlap")]
    if dropped:
        cautions.append("第 %s 条与别的批注在原文上重叠，已让位（HTML 表达不了交叉区间）"
                        % "、".join(str(i) for i in dropped))
    return errors, cautions, result


def gate_summary(job, payload):
    """闸门 5：总评字数在 60～200（中文按字、英文按词），且不许逐题复述。"""
    body = payload.get("summary")
    if not isinstance(body, str):
        return ["summary 必须是一段字符串"]
    errors = []
    unit = "词" if job.lang == "en" else "字"
    size = count_words(body, job.lang)
    if size < SUMMARY_MIN_WORDS or size > SUMMARY_MAX_WORDS:
        errors.append("summary 应在 %d–%d %s之间，当前 %d %s"
                      % (SUMMARY_MIN_WORDS, SUMMARY_MAX_WORDS, unit, size, unit))
    hit = PER_ITEM_RECAP.search(body)
    if hit:
        errors.append("summary 里出现逐题复述「%s」；总评是对这一份作答的整体评价，"
                      "不是把评分标准再抄一遍" % hit.group(0))
    return errors


def gate_hollow(job, answer_text, result):
    """闸门 7（只提醒）：引文全是短词、批语又和作答毫无字面交集 —— 像是没读作答。"""
    marks = result.marks
    if not marks:
        return []
    if any(len(anchor.normalize(m.get("quote") or "")) > HOLLOW_QUOTE_CHARS for m in marks):
        return []
    body = grams(anchor.plain_text(answer_text))
    if any(body & grams(m.get("note") or "") for m in marks):
        return []
    return ["空心批注：所有引文都不超过 %d 字，批语也和作答没有一处 %d 字重合，请确认确实读了作答"
            % (HOLLOW_QUOTE_CHARS, GRAM)]


def gate_baseline(record):
    """对抗作答（answers/base-*）只能是 0 分、条目全 miss，否则这一轮批改在白给分。"""
    errors = []
    if record.get("points"):
        errors.append("这是对抗作答（%s 开头），基线必须批出 0 分，当前是 %d 分"
                      % (BASE_PREFIX, record["points"]))
    wrong = [c["name"] for c in record.get("criteria") or [] if c.get("verdict") != "miss"]
    if wrong:
        errors.append("这是对抗作答（%s 开头），条目必须全部 miss，当前命中：%s"
                      % (BASE_PREFIX, "、".join("「%s」" % n for n in wrong)))
    return errors


def gate_similarity(record, prior):
    """闸门 6：一份评语贴全班。总评相同，或批语集合 Jaccard ≥ 0.8，拒收后一份。"""
    errors = []
    mine_notes = set(m.get("note") for m in record.get("marks") or [] if m.get("note"))
    for other in prior:
        if other.get("student") == record.get("student"):
            continue
        who = other.get("student")
        if record.get("summary") and record.get("summary") == other.get("summary"):
            errors.append("总评与已通过的 %s 一字不差；一份评语贴全班等于没批" % who)
        others = set(m.get("note") for m in other.get("marks") or [] if m.get("note"))
        overlap = jaccard(mine_notes, others)
        if overlap >= SIMILARITY_CAP:
            errors.append("批语集合与已通过的 %s 重合度 %.2f（上限 %.2f）；请按这一份作答重批"
                          % (who, overlap, SIMILARITY_CAP))
    return errors


def validate_grade(job, answer_text, payload):
    """跑闸门 1–5 与 7（不含需要读别人结果的雷同闸），返回 (错误, 提醒, 规范化结果)。

    纯函数：只看传进来的 job（已读好题干、评分标准、条目表）、作答原文与这一份评分
    结果，不碰磁盘。self-grader 的闸门 1–5、7 与这里逐条相同，可以整个复用。
    """
    if not isinstance(payload, dict):
        return ["评分结果必须是一个 JSON 对象"], [], {}
    errors = list(gate_keys(payload))
    errors += gate_context(job, answer_text, payload)
    ordered, shape = _ordered_criteria(job, payload)
    errors += shape
    errors += gate_points(job, payload, ordered)
    crit_errors, crit_cautions, criteria = gate_criteria(job, answer_text, payload, ordered)
    errors += crit_errors
    mark_errors, mark_cautions, result = gate_marks(job, answer_text, payload)
    errors += mark_errors
    errors += gate_summary(job, payload)
    cautions = crit_cautions + mark_cautions + gate_hollow(job, answer_text, result)
    normalized = {
        "context_hash": payload.get("context_hash"),
        "points": payload.get("points"),
        "summary": payload.get("summary"),
        "criteria": criteria,
        "marks": result.marks,
        "anchored_ratio": result.anchored_ratio,
    }
    return errors, cautions, normalized


# ---------------------------------------------------------------- 盖章与新鲜度

def current_hashes(job):
    return {"rubric": sha256_text(read_text_or_empty(job.path(RUBRIC_FILE))),
            "question": sha256_text(read_text_or_empty(job.path(QUESTION_FILE))),
            "oracle_full": sha256_text(read_text_or_empty(job.path(ORACLE_FULL))),
            "oracle_broken": sha256_text(read_text_or_empty(job.path(ORACLE_BROKEN)))}


HASH_LABEL = {"rubric": RUBRIC_FILE, "question": QUESTION_FILE,
              "oracle_full": ORACLE_FULL, "oracle_broken": ORACLE_BROKEN}


def stamp_state(job):
    """返回 (盖章内容或 None, 变过的材料名列表)。"""
    path = job.path(STAMP_FILE)
    if not os.path.isfile(path):
        return None, []
    stamp = read_json(path)
    stored = (stamp or {}).get("hashes") or {}
    now = current_hashes(job)
    changed = [HASH_LABEL[k] for k in sorted(now) if stored.get(k) != now[k]]
    return stamp, changed


def require_stamp(job):
    """grade 的前置：盖章在、且四份材料一个字没变过。"""
    stamp, changed = stamp_state(job)
    if stamp is None:
        raise UsageError("还没有 oracle 盖章，不许开批。请先让 Agent 交 "
                         "inbox/grade-oracle-full.json 与 inbox/grade-oracle-broken.json，"
                         "再跑 grader.py oracle check %s" % job.dir)
    if changed:
        raise UsageError("oracle 盖章已作废（%s 改过），之前批的都算旧的。"
                         "请重跑 grader.py oracle check %s" % ("、".join(changed), job.dir))
    return stamp


def passed_records(job):
    out = []
    for student in job.result_ids():
        record = read_json(job.path("results", "%s.json" % student))
        if isinstance(record, dict):
            record.setdefault("student", student)
            out.append(record)
    return out


def stale_records(job):
    """结果的 context_hash 与当前重算值对不上 —— 材料改过，这份结果已经作废。"""
    stale = []
    for record in passed_records(job):
        student = record.get("student")
        try:
            answer_text = job.answer_of(student)
        except UsageError:
            stale.append((student, "作答文件不见了"))
            continue
        if record.get("context_hash") != job.context_hash(answer_text):
            stale.append((student, "上下文哈希与当前重算值不一致"))
    return stale


# ---------------------------------------------------------------- 报告

def payload_of(record):
    """把落盘结果还原成契约形状的评分结果，供离线复核重跑闸门。"""
    return {"context_hash": record.get("context_hash"),
            "points": record.get("points"),
            "summary": record.get("summary"),
            "criteria": [{"name": c.get("name"), "verdict": c.get("verdict"),
                          "quote": c.get("quote", "")} for c in record.get("criteria") or []],
            "marks": [{"quote": m.get("quote", ""), "level": m.get("level", anchor.DEFAULT_LEVEL),
                       "note": m.get("note", "")} for m in record.get("marks") or []]}


def render_card(job, record, answer_text):
    """判题卡：marks 是真相，html 只是缓存，所以每次都重新锚定再渲染。"""
    result = anchor.annotate(answer_text, [{"quote": m.get("quote", ""),
                                            "level": m.get("level", anchor.DEFAULT_LEVEL),
                                            "note": m.get("note", "")}
                                           for m in record.get("marks") or []])
    tally = verdict_tally(record)
    meta = {"学号": record.get("student", ""),
            "得分": "%s / %d" % (record.get("points"), job.max),
            "条目": "命中 %d · 部分 %d · 未命中 %d" % (tally["hit"], tally["partial"], tally["miss"]),
            "批改于": record.get("graded_at", "")}
    title = "判题卡 · %s · %s" % (job.slug, record.get("student", ""))
    return anchor.render_page(title, answer_text, result, meta)


def verdict_tally(record):
    tally = dict((v, 0) for v in VERDICTS)
    for item in record.get("criteria") or []:
        verdict = item.get("verdict")
        if verdict in tally:
            tally[verdict] += 1
    return tally


_HTML_CSS = """
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#ffffff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--fg:#e6edf3;--muted:#8b949e;--line:#30363d}}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.card{max-width:900px;margin:0 auto;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px 28px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px}.meta{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:13px}td.num{white-space:nowrap;color:var(--muted)}
.foot{margin:20px 0 0;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
.empty{color:var(--muted)}
"""

SUMMARY_FOOT = "「未定位」的批注脚本没有摆放到原文上，请人工看一眼判题卡右栏。"
EMPTY_ROW = "还没有通过的结果"


def summary_view(job, records):
    """汇总要摆的三张表：(标题, 表头, 行)。Markdown 与 HTML 共用同一份数据。"""
    per_item = []
    for name in job.names:
        row = dict((v, 0) for v in VERDICTS)
        for record in records:
            for item in record.get("criteria") or []:
                if item.get("name") == name and item.get("verdict") in row:
                    row[item["verdict"]] += 1
        per_item.append([name, row["hit"], row["partial"], row["miss"]])
    levels = dict((lv, 0) for lv in anchor.LEVELS)
    for record in records:
        for mark in record.get("marks") or []:
            if mark.get("level") in levels:
                levels[mark["level"]] += 1
    per_student = [[r.get("student"), "%s / %d" % (r.get("points"), job.max),
                    "%d%%" % round((r.get("anchored_ratio") or 0.0) * 100),
                    len(r.get("marks") or []),
                    len([m for m in r.get("marks") or [] if not m.get("anchored")])]
                   for r in records]
    points = [r.get("points") or 0 for r in records]
    headline = ("已通过 %d 份 · 满分 %d · 平均 %.1f 分 · 生成于 %s"
                % (len(records), job.max,
                   (sum(points) / len(points)) if points else 0.0, now_iso()))
    return headline, [
        ("按条目看谁没命中", ("条目", "命中", "部分", "未命中"), per_item),
        ("按等级看批注", ("等级", "条数"),
         [["%s（%s）" % (anchor.LEVEL_LABEL.get(lv, lv), lv), levels[lv]] for lv in anchor.LEVELS]),
        ("每一份", ("学号", "得分", "锚定率", "批注", "未定位"), per_student),
    ]


def render_summary_md(job, records):
    headline, tables = summary_view(job, records)
    out = ["# 汇总 · %s" % job.slug, "", headline]
    for title, head, rows in tables:
        out += ["", "## %s" % title, "",
                "| %s |" % " | ".join(head),
                "| %s |" % " | ".join(["---"] + ["---:"] * (len(head) - 1))]
        out += (["| %s |" % " | ".join(str(c) for c in row) for row in rows]
                or ["| %s |" % " | ".join([EMPTY_ROW] + [""] * (len(head) - 1))])
    return "\n".join(out + ["", SUMMARY_FOOT, ""])


def render_summary_html(job, records):
    esc = html.escape
    headline, tables = summary_view(job, records)
    blocks = []
    for title, head, rows in tables:
        body = "".join("<tr>%s</tr>" % "".join(
            "<td%s>%s</td>" % ("" if i == 0 else ' class="num"', esc(str(cell)))
            for i, cell in enumerate(row)) for row in rows)
        if not rows:
            body = '<tr><td colspan="%d" class="empty">%s</td></tr>' % (len(head), EMPTY_ROW)
        blocks.append("<h2>%s</h2><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
                      % (esc(title), "".join("<th>%s</th>" % esc(h) for h in head), body))
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>汇总 · %s</title><style>%s</style></head><body><div class=\"card\">"
            "<h1>汇总 · %s</h1><div class=\"meta\">%s</div>%s"
            "<p class=\"foot\">%s</p></div></body></html>\n"
            % (esc(job.slug), _HTML_CSS, esc(job.slug), esc(headline),
               "".join(blocks), esc(SUMMARY_FOOT)))


# ---------------------------------------------------------------- 命令

def cmd_doctor(args):
    print("rubric-grader 环境检查（grader.py 由 Python %d.%d.%d 运行，%s）"
          % (sys.version_info[0], sys.version_info[1], sys.version_info[2], sys.platform))
    if sys.version_info < (3, 8):
        print("  [缺失] Python 3.8+ —— 本脚本需要 3.8 以上")
        return 2
    print("  [OK]   Python %d.%d 满足 3.8+ 要求" % (sys.version_info[0], sys.version_info[1]))
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("anchor.py", "banned_words.py"):
        mark = "[OK]  " if os.path.isfile(os.path.join(here, name)) else "[缺失]"
        print("  %s %s" % (mark, os.path.join(here, name)))
    print("  [OK]   锚定引擎可用（等级白名单 %s，默认 %s）"
          % (" / ".join(anchor.LEVELS), anchor.DEFAULT_LEVEL))
    print("提示：脚本只读写题批次目录，不联网；作答里的 HTML 会先消毒再进判题卡；"
          "图片作答不支持。默认批注上限 %d 条、锚定率下限 %.1f。"
          % (DEFAULT_MAX_NOTES, DEFAULT_MIN_ANCHORED))
    return 0


def cmd_init(args):
    job_dir = os.path.abspath(args.job_dir)
    if os.path.isfile(job_dir):
        raise UsageError("这是一个文件而不是目录：%s" % job_dir)
    if os.path.isdir(job_dir) and os.listdir(job_dir):
        raise UsageError("目录已存在且不为空，换个名字或先清空：%s" % job_dir)
    if args.max < 1:
        raise UsageError("--max 必须是不小于 1 的整数，当前是 %d" % args.max)
    if args.max_notes < 1:
        raise UsageError("--max-notes 必须是不小于 1 的整数，当前是 %d" % args.max_notes)
    if not 0 <= args.min_anchored <= 1:
        raise UsageError("--min-anchored 必须在 0～1 之间，当前是 %r" % args.min_anchored)
    slug = os.path.basename(job_dir.rstrip(os.sep)) or "job"
    for name in SUB_DIRS:
        os.makedirs(os.path.join(job_dir, name), exist_ok=True)
    write_json(os.path.join(job_dir, JOB_FILE),
               {"slug": slug, "max": args.max, "lang": args.lang,
                "max_notes": args.max_notes, "min_anchored": args.min_anchored,
                "criteria": [], "created": now_iso()})
    write_text(os.path.join(job_dir, QUESTION_FILE),
               "在这里粘贴题干原文（可以含 HTML；脚本不改动它）。\n")
    write_text(os.path.join(job_dir, RUBRIC_FILE),
               "在这里逐字粘贴老师给的评分标准（脚本不改动它，也不自己解析）。\n")
    print("建好题批次：%s（满分 %d · 语言 %s · 批注上限 %d · 锚定率下限 %.2f）"
          % (job_dir, args.max, args.lang, args.max_notes, args.min_anchored))
    print("下一步：")
    print("  1. 把题干写进 %s，把评分标准逐字粘进 %s" % (QUESTION_FILE, RUBRIC_FILE))
    print("  2. 帮老师把评分标准整理成条目表，老师确认后："
          "grader.py rubric set %s --from inbox/criteria.json" % args.job_dir)
    print("  3. 把满分范例放 %s、残缺版放 %s，缺哪几条写进 %s"
          % (ORACLE_FULL, ORACLE_BROKEN, ORACLE_BROKEN_LIST))
    print("  4. 学生作答放 answers/<学号>.md（对抗基线用 %s 开头的文件名）" % BASE_PREFIX)
    return 0


def cmd_rubric_set(args):
    job = Job(args.job_dir)
    raw = read_json(args.source)
    items = raw.get("criteria") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise UsageError("条目表要么是一个数组，要么是 {\"criteria\": [...]}，且不能为空：%s" % args.source)
    problems, table, seen = [], [], set()
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            problems.append("第 %d 项不是对象" % i)
            continue
        stray = [k for k in sorted(item) if k not in ("name", "points")]
        if stray:
            problems.append("第 %d 项有多余的键：%s；只接受 name 与 points" % (i, "、".join(stray)))
        name = str(item.get("name") or "").strip()
        if not name:
            problems.append("第 %d 项没有条目名" % i)
            continue
        if name in seen:
            problems.append("条目名「%s」重复了" % name)
        seen.add(name)
        entry = {"name": name}
        if "points" in item:
            if not is_int(item["points"]) or item["points"] < 0:
                problems.append("条目「%s」的 points 必须是不小于 0 的整数，当前是：%r" % (name, item["points"]))
            else:
                entry["points"] = item["points"]
        table.append(entry)

    scored = [c for c in table if "points" in c]
    if scored and len(scored) != len(table):
        problems.append("条目表要么每条都带分值，要么每条都不带；当前 %d/%d 条带分值"
                        % (len(scored), len(table)))
    elif scored:
        total = sum(c["points"] for c in scored)
        if total != job.max:
            problems.append("条目分值加起来是 %d，与满分 %d 对不上" % (total, job.max))
    if problems:
        print("条目表未通过（%d 条问题，job.json 里的旧条目表原样保留）：" % len(problems))
        for line in problems:
            print("  [ERROR] %s" % line)
        return 1

    job.meta["criteria"] = table
    write_json(job.path(JOB_FILE), job.meta)
    kind = "带分值" if scored else "不带分值"
    print("条目表已写入 %s：%d 条（%s）" % (JOB_FILE, len(table), kind))
    for item in table:
        print("  · %s%s" % (item["name"], "（%d 分）" % item["points"] if "points" in item else ""))
    if job.result_ids():
        print("  [WARN] results/ 里已经有 %d 份结果，改了条目表它们全部作废，"
              "请重跑 oracle check 再逐份重批" % len(job.result_ids()))
    return 0


def _resolve_answer(job, value):
    """作答参数可以是路径，也可以是学号（去 answers/ 里找）。"""
    if os.path.isfile(value):
        return os.path.abspath(value)
    candidate = os.path.join(job.dir, value)
    if os.path.isfile(candidate):
        return candidate
    return job.answer_path(value)


def cmd_context(args):
    job = Job(args.job_dir)
    if not job.criteria:
        raise UsageError("条目表还是空的，请先跑 grader.py rubric set")
    path = _resolve_answer(job, args.answer)
    print(json.dumps(job.context_pack(read_answer(path)), ensure_ascii=False, indent=2))
    return 0


def _oracle_payload(job, kind):
    path = job.path("inbox", "grade-oracle-%s.json" % kind)
    if not os.path.isfile(path):
        raise UsageError("缺 %s。请让 Agent 先对 oracle/%s.md 跑 context，再把评分结果写到这里"
                         % (os.path.relpath(path, job.dir), kind))
    return read_json(path)


def cmd_oracle_check(args):
    job = Job(args.job_dir)
    if not job.criteria:
        raise UsageError("条目表还是空的，请先跑 grader.py rubric set")
    for name in (ORACLE_FULL, ORACLE_BROKEN, ORACLE_BROKEN_LIST):
        if not os.path.isfile(job.path(name)):
            raise UsageError("缺 %s。满分范例、残缺版与「残缺版缺哪几条」都要老师给" % name)
    listed = read_json(job.path(ORACLE_BROKEN_LIST))
    missing = (listed or {}).get("missing") if isinstance(listed, dict) else None
    if not isinstance(missing, list) or not missing:
        raise UsageError("%s 应形如 {\"missing\": [\"条目名\", ...]}，且至少列一条" % ORACLE_BROKEN_LIST)
    unknown = [n for n in missing if n not in job.names]
    if unknown:
        raise UsageError("%s 里的 %s 不在条目表里" % (ORACLE_BROKEN_LIST, "、".join(unknown)))

    problems = []
    full_text = read_answer(job.path(ORACLE_FULL))
    broken_text = read_answer(job.path(ORACLE_BROKEN))
    full_errors, full_cautions, full = validate_grade(job, full_text, _oracle_payload(job, "full"))
    problems += ["满分范例：%s" % e for e in full_errors]
    if full.get("points") != job.max and is_int(full.get("points")):
        problems.append("满分范例的 points 必须等于满分 %d，实际 %d" % (job.max, full["points"]))
    for item in full.get("criteria") or []:
        if item.get("verdict") != "hit":
            problems.append("满分范例的条目「%s」判成 %s；满分范例必须条条命中，"
                            "否则不是评分标准写歪了就是这一轮批得太紧"
                            % (item.get("name"), item.get("verdict")))

    broken_errors, broken_cautions, broken = validate_grade(job, broken_text, _oracle_payload(job, "broken"))
    problems += ["残缺版：%s" % e for e in broken_errors]
    if is_int(broken.get("points")) and broken["points"] >= job.max:
        problems.append("残缺版的 points 必须小于满分 %d，实际 %d" % (job.max, broken["points"]))
    got = dict((c.get("name"), c.get("verdict")) for c in broken.get("criteria") or [])
    for name in missing:
        if got.get(name) not in ("miss", "partial"):
            problems.append("残缺版删掉了「%s」，这一条应判 miss 或 partial，实际 %s；"
                            "批出命中说明这一轮在无中生有" % (name, got.get(name)))

    if problems:
        print("oracle 未通过（%d 条问题）：" % len(problems))
        for line in problems:
            print("  [ERROR] %s" % line)
        print("改 inbox 里的两份评分结果（或请老师改范例），改完重跑；不盖章就不许开批。")
        return 1
    for line in full_cautions + broken_cautions:
        print("  [WARN] %s" % line)
    write_json(job.path(STAMP_FILE),
               {"job": job.slug, "stamped_at": now_iso(), "hashes": current_hashes(job)})
    print("oracle 通过：满分范例 %d / %d 分条条命中；残缺版 %d / %d 分，缺的%s都判了 miss 或 partial"
          % (full["points"], job.max, broken["points"], job.max,
             "、".join("「%s」" % n for n in missing)))
    print("已盖章：%s（记下 %s 四份材料的哈希，任一改动都作废）"
          % (STAMP_FILE, "、".join(HASH_LABEL[k] for k in sorted(HASH_LABEL))))
    return 0


def cmd_grade(args):
    job = Job(args.job_dir)
    if not job.criteria:
        raise UsageError("条目表还是空的，请先跑 grader.py rubric set")
    require_stamp(job)
    student = args.student
    answer_text = job.answer_of(student)
    inbox = job.path("inbox", "grade-%s.json" % student)
    if not os.path.isfile(inbox):
        raise UsageError("缺 %s。请先跑 context 拿上下文包，再把评分结果写到这里"
                         % os.path.relpath(inbox, job.dir))
    payload = read_json(inbox)

    errors, cautions, normalized = validate_grade(job, answer_text, payload)
    record = {"job": job.slug, "student": student, "max": job.max,
              "graded_at": now_iso(), "cautions": cautions}
    record.update(normalized)
    if student.startswith(BASE_PREFIX):
        errors += gate_baseline(record)
    else:
        prior = [r for r in passed_records(job) if not str(r.get("student", "")).startswith(BASE_PREFIX)]
        errors += gate_similarity(record, prior)

    if errors:
        print("grade 未通过：%s（%d 条问题）" % (student, len(errors)))
        for line in errors:
            print("  [ERROR] %s" % line)
        for line in cautions:
            print("  [WARN] %s" % line)
        print("inbox/grade-%s.json 原样保留：改评分结果，不要改作答，也不要手写 results/。" % student)
        return 1

    write_json(job.path("results", "%s.json" % student), record)
    write_text(job.path("results", "%s.html" % student), render_card(job, record, answer_text))
    tally = verdict_tally(record)
    lost = len([m for m in record["marks"] if not m.get("anchored")])
    print("grade 通过：%s · %d / %d 分 · 条目 命中 %d、部分 %d、未命中 %d · 批注 %d 条（锚定 %d%%）"
          % (student, record["points"], job.max, tally["hit"], tally["partial"], tally["miss"],
             len(record["marks"]), round(record["anchored_ratio"] * 100)))
    for line in cautions:
        print("  [WARN] %s" % line)
    print("  写出 results/%s.json 与 results/%s.html" % (student, student))
    if lost:
        print("  其中 %d 条未能定位到原文，判题卡右栏单列，脚本不擅自摆放，请人工看一眼" % lost)
    return 0


def _freshness_problems(job):
    """汇总与导出共用的新鲜度前置：盖章在不在、有没有过期的结果。"""
    problems = []
    stamp, changed = stamp_state(job)
    if stamp is None:
        problems.append("还没有 oracle 盖章，先跑 grader.py oracle check")
    elif changed:
        problems.append("oracle 盖章已作废（%s 改过）" % "、".join(changed))
    for student, why in stale_records(job):
        problems.append("结果 %s 已过期（stale）：%s" % (student, why))
    return problems


def cmd_summary(args):
    job = Job(args.job_dir)
    problems = _freshness_problems(job)
    if problems:
        print("summary 拒绝生成（%d 条问题）：" % len(problems))
        for line in problems:
            print("  [ERROR] %s" % line)
        print("材料改过之后旧结果都不算数：重跑 oracle check，再逐份重跑 grade。")
        return 1
    records = [r for r in passed_records(job) if not str(r.get("student", "")).startswith(BASE_PREFIX)]
    write_text(job.path("summary.md"), render_summary_md(job, records))
    write_text(job.path("summary.html"), render_summary_html(job, records))
    headline, tables = summary_view(job, records)
    print("汇总：%s · %s（对抗基线不计入）" % (job.slug, headline))
    for name, hit, partial, miss in tables[0][2]:
        print("  · %s：命中 %d · 部分 %d · 未命中 %d" % (name, hit, partial, miss))
    print("  批注：%s" % "、".join("%s %s 条" % (row[0], row[1]) for row in tables[1][2]))
    print("  写出 summary.md 与 summary.html")
    return 0


def cmd_check(args):
    job = Job(args.job_dir)
    lines = []

    def add(level, message):
        lines.append((level, message))

    if not job.criteria:
        add("ERROR", "条目表是空的，先跑 grader.py rubric set")
    elif job.weighted:
        total = sum(int(c["points"]) for c in job.criteria)
        if total != job.max:
            add("ERROR", "条目分值加起来是 %d，与满分 %d 对不上" % (total, job.max))
        else:
            add("OK", "条目表 %d 条，分值合计 %d，与满分一致" % (len(job.criteria), job.max))
    else:
        add("OK", "条目表 %d 条（不带分值，points 只受 0～%d 约束）" % (len(job.criteria), job.max))
    for name in (QUESTION_FILE, RUBRIC_FILE):
        if not read_text_or_empty(job.path(name)).strip():
            add("ERROR", "%s 是空的" % name)

    stamp, changed = stamp_state(job)
    if stamp is None:
        add("ERROR", "没有 oracle 盖章（%s），这个题批次还不该开批" % STAMP_FILE)
    elif changed:
        add("ERROR", "oracle 盖章已作废（stale）：%s 在盖章之后改过" % "、".join(changed))
    else:
        add("OK", "oracle 盖章有效（%s 四份材料一个字没变）" % "、".join(sorted(HASH_LABEL.values())))

    records = passed_records(job)
    fresh = []
    stale = dict(stale_records(job))
    for record in records:
        student = record.get("student")
        if student in stale:
            add("ERROR", "结果 %s 已过期（stale）：%s，请重跑 grade" % (student, stale[student]))
            continue
        answer_text = job.answer_of(student)
        errors, cautions, _ = validate_grade(job, answer_text, payload_of(record))
        for line in errors:
            add("ERROR", "结果 %s：%s" % (student, line))
        for line in cautions:
            add("WARN", "结果 %s：%s" % (student, line))
        if not os.path.isfile(job.path("results", "%s.html" % student)):
            add("ERROR", "结果 %s 缺判题卡 results/%s.html" % (student, student))
        if str(student).startswith(BASE_PREFIX):
            for line in gate_baseline(record):
                add("ERROR", "结果 %s：%s" % (student, line))
        else:
            fresh.append(record)
    for i, record in enumerate(fresh):
        for line in gate_similarity(record, fresh[:i]):
            add("ERROR", "结果 %s：%s" % (record.get("student"), line))
    if records and not [l for l, _ in lines if l == "ERROR"]:
        add("OK", "%d 份结果重跑闸门全部通过" % len(records))

    graded = set(job.result_ids())
    bases = [s for s in job.students() if s.startswith(BASE_PREFIX)]
    if not bases:
        add("WARN", "answers/ 里没有 %s 开头的对抗作答；建议放三份（空白、回贴题面、无关段落）"
                    "验证这一轮不会白给分" % BASE_PREFIX)
    pending = [s for s in job.students() if s not in graded]
    if pending:
        add("WARN", "还没批：%s" % "、".join(pending))
    leftover = [n for n in sorted(os.listdir(job.path("inbox")))
                if n.startswith("grade-") and n.endswith(".json")] \
        if os.path.isdir(job.path("inbox")) else []
    if leftover:
        add("WARN", "inbox/ 里还留着 %d 个评分结果文件（通过之后可以删）" % len(leftover))

    errors = [m for l, m in lines if l == "ERROR"]
    warns = [m for l, m in lines if l == "WARN"]
    print("复核：%s（%d ERROR · %d WARN）" % (job.dir, len(errors), len(warns)))
    for level, message in lines:
        print("  [%s] %s" % (level, message))
    return 1 if errors else 0


def cmd_export(args):
    job = Job(args.job_dir)
    problems = _freshness_problems(job)
    if problems:
        print("export 拒绝导出（%d 条问题）：" % len(problems))
        for line in problems:
            print("  [ERROR] %s" % line)
        return 1
    stamp, _ = stamp_state(job)
    students = []
    for record in passed_records(job):
        students.append({"id": record.get("student"),
                         "points": record.get("points"),
                         "verdicts": [c.get("verdict") for c in record.get("criteria") or []],
                         "anchored_ratio": record.get("anchored_ratio"),
                         "marks_count": len(record.get("marks") or []),
                         "context_hash": record.get("context_hash")})
    pack = {"job": job.slug, "max": job.max, "criteria_names": job.names,
            "students": students, "oracle_stamp": stamp or {}}
    out_path = os.path.abspath(args.out) if args.out else job.path("export.json")
    write_json(out_path, pack)
    print("导出：%s · %d 份结果 → %s" % (job.slug, len(students), out_path))
    print("只带哈希、分数、条目判定与锚定率；作答原文、引文与评语一个字都没有带出去。")
    return 0


# ---------------------------------------------------------------- 入口

def build_parser():
    p = argparse.ArgumentParser(prog="grader.py", description="rubric-grader 判卷脚本")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("doctor", help="查看本机环境与引擎")

    i = sub.add_parser("init", help="建题批次骨架")
    i.add_argument("job_dir", help="题批次目录（目录名就是批次名）")
    i.add_argument("--max", type=int, required=True, help="这道题的满分")
    i.add_argument("--lang", choices=LANGS, default="zh", help="作答语言（决定总评按字还是按词计数）")
    i.add_argument("--max-notes", dest="max_notes", type=int, default=DEFAULT_MAX_NOTES,
                   help="每份作答的批注条数上限（默认 %d）" % DEFAULT_MAX_NOTES)
    i.add_argument("--min-anchored", dest="min_anchored", type=float, default=DEFAULT_MIN_ANCHORED,
                   help="批注锚定率下限（默认 %.1f）" % DEFAULT_MIN_ANCHORED)

    r = sub.add_parser("rubric", help="条目表")
    rsub = r.add_subparsers(dest="action")
    rs = rsub.add_parser("set", help="写入条目表（老师确认后再交）")
    rs.add_argument("job_dir")
    rs.add_argument("--from", dest="source", required=True, help="条目表 JSON 文件")

    c = sub.add_parser("context", help="输出上下文包 JSON")
    c.add_argument("job_dir")
    c.add_argument("answer", help="作答文件路径，或 answers/ 里的学号")

    o = sub.add_parser("oracle", help="满分范例与残缺版")
    osub = o.add_subparsers(dest="action")
    oc = osub.add_parser("check", help="两份范例都判对了才盖章")
    oc.add_argument("job_dir")

    g = sub.add_parser("grade", help="批一份作答")
    g.add_argument("job_dir")
    g.add_argument("student", help="学号（对应 answers/<学号>.md 与 inbox/grade-<学号>.json）")

    s = sub.add_parser("summary", help="全班汇总")
    s.add_argument("job_dir")

    k = sub.add_parser("check", help="离线复核整个题批次")
    k.add_argument("job_dir")

    x = sub.add_parser("export", help="导出脱敏证据")
    x.add_argument("job_dir")
    x.add_argument("--out", help="输出文件（默认 <job-dir>/export.json）")
    return p


NESTED = {"rubric": ("set", cmd_rubric_set), "oracle": ("check", cmd_oracle_check)}
HANDLERS = {"doctor": cmd_doctor, "init": cmd_init, "context": cmd_context,
            "grade": cmd_grade, "summary": cmd_summary, "check": cmd_check, "export": cmd_export}


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
            wanted, handler = NESTED[args.command]
            if getattr(args, "action", None) != wanted:
                raise UsageError("请写全子命令：grader.py %s %s <job-dir>" % (args.command, wanted))
            return handler(args)
        return HANDLERS[args.command](args)
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
