#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""self-grader 自批脚本（零依赖，Python 3.8+ 标准库，单文件）。

一个人对着自己带来的评分标准批自己的作答。脚本不内置任何学科评分标准，只做三件事：
把材料拼成一份可复算的上下文包、把模型给的判定逐条核回原文、把结果钉成一页判题卡。

子命令：
  doctor                          查看本机环境与引擎是否就位
  init <slug>                     建练习骨架 practice/<slug>
  criteria set <slug> --from <f>  写入条目表（满分、语言、条目名与分值）
  baseline <slug>                 生成三份对抗作答：空、题面回贴、无关段落
  context <slug> <attempt>        输出上下文包 JSON（stdout 只有 JSON）
  grade <slug> <attempt>          读 inbox/grade.json，跑闸门，写判题卡
  progress <slug>                 打印 progress.md 并给一句走势
  check <slug>                    离线复核整个练习目录
  export <slug>                   导出脱敏证据（只有哈希、分数、判定、锚定率）

退出码：0 通过 / 1 未通过（有 ERROR）/ 2 用法或前置条件不满足。
目录与 JSON 契约见 references/workspace-format.md；纪律见 references/rules.md。
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchor                                                    # noqa: E402

# 稿号（attempt 名，含对抗基线名）会拼进 attempts/ 的目录名，按 red-pen 的 slug 口径校验。
ATTEMPT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def check_attempt(name):
    """稿号要拼进 attempts/ 的目录名，按 slug 口径校验，一步不许穿越目录。"""
    if not ATTEMPT_RE.match(name or ""):
        raise UsageError("稿号只能是小写字母、数字与连字符（不超过 64 位），当前是：%r" % name)
    return name

VERDICTS = ("hit", "partial", "miss")
PAYLOAD_KEYS = ("context_hash", "points", "summary", "criteria", "marks")
CRITERIA_KEYS = ("name", "verdict", "quote")
MARK_KEYS = ("quote", "level", "note")
CONFIG_KEYS = ("max", "lang", "criteria", "max_notes", "min_anchored")
LANGS = ("zh", "en")

DEFAULT_MAX_NOTES = 12
DEFAULT_MIN_ANCHORED = 0.7
SUMMARY_RANGE = (60, 200)
NOTE_MIN = 6
SHORT_QUOTE = 6

BASE_ATTEMPTS = ("base-empty", "base-echo", "base-noise")

# 无关段落：写死在脚本里，跟任何题目都不搭界（只讲天气与路况，没有一个学科词）。
# 模型要是能从这段话里批出分来，那它给的分就跟作答无关，真作答也不必批了。
NOISE_ANSWER = (
    "今天清晨起了一层薄雾，路面有些湿滑，公交车比平时晚了七八分钟到站。"
    "中午云散开，太阳晒得人睁不开眼，路口的车流慢慢排成一条长队。"
    "傍晚又刮起风，气温降下来，骑车的人纷纷把外套的拉链拉到顶。\n"
)

QUESTION_STUB = "把题目原样贴在这里（可以带 HTML）。脚本不改这个文件。\n"
RUBRIC_STUB = ("把你自己带来的评分标准原样贴在这里 —— 老师给的、官方的、自己写的都行。\n"
               "本 Skill 不内置任何学科评分标准，也不会替你猜。脚本不改这个文件。\n")
PROGRESS_HEAD = "# 进度（脚本只增不改，手改这里就对不上 result.json 了）\n\n"

# 「第 3 题」式逐题复述。字符类与 rubric-grader 的那一条对齐，并各自补上对方缺的写法：
# 半角与全角数字、〇 与中文数字、题 / 題 / 问 / 問，位数不设上限。
_RECAP = re.compile(r"第\s*[0-9０-９〇一二三四五六七八九十百]+\s*[题題问問]")
_SPACE = re.compile(r"\s+")


class UsageError(Exception):
    """用法或前置条件错误，退出码 2。"""


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
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read_json(path):
    try:
        return json.loads(read_text(path))
    except ValueError as e:
        raise UsageError("JSON 解析失败：%s（%s）" % (path, e))


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def canonical(obj):
    """哈希用的规范 JSON：不转义非 ASCII、键排序、不留空格。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def today():
    return datetime.date.today().isoformat()


def clip(text, width=40):
    text = _SPACE.sub(" ", str(text or "")).strip()
    return text if len(text) <= width else text[:width] + "…"


def short_hash(value):
    return clip(value, 12) if isinstance(value, str) else repr(value)


def count_units(text, lang):
    """中文按字（不计空白），英文按空白分词 —— 两种语言的「一段话」长度感差得远。

    英文按空白切而不是按字母块切：`state-of-the-art` 是一个词，不是四个。
    """
    body = text or ""
    if lang == "en":
        return len([w for w in _SPACE.split(body.strip()) if w])
    return len(_SPACE.sub("", body))


def trigrams(text):
    """空心闸用的三字窗口：先规范化，再去掉全部空白并折成小写，中英文各自可比。"""
    folded = _SPACE.sub("", anchor.normalize(text or "")).lower()
    return set(folded[i:i + 3] for i in range(len(folded) - 2))


def context_hash(job, answer_text):
    """题目 / 标准 / 条目表 / 作答 / 满分 / 语言，任一变了哈希就变。"""
    return sha256_text(canonical({
        "question_text": job["question_text"],
        "rubric_text": job["rubric_text"],
        "criteria": job["criteria"],
        "answer_text": answer_text,
        "max": job["max"],
        "lang": job["lang"],
    }))


def resolve_ws(slug):
    """<slug> 既可以是练习名（→ practice/<slug>），也可以直接给一个目录。"""
    seps = [os.sep] + ([os.altsep] if os.altsep else [])
    if any(s in slug for s in seps):
        return os.path.abspath(slug)
    nested = os.path.join("practice", slug)
    if os.path.isdir(nested) or not os.path.isdir(slug):
        return os.path.abspath(nested)
    return os.path.abspath(slug)


# ---------------------------------------------------------------- 条目表

def criteria_problems(cfg):
    """检查用户确认过的条目表；返回问题描述列表，空列表即合格。"""
    if not isinstance(cfg, dict):
        return ["条目表必须是一个 JSON 对象"]
    problems = []
    extra = sorted(set(cfg) - set(CONFIG_KEYS))
    if extra:
        problems.append("多了不认识的键：%s（只收 %s）" % ("、".join(extra), "、".join(CONFIG_KEYS)))

    limit = cfg.get("max")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        problems.append("max 必须是不小于 1 的整数，实际 %r" % (limit,))
    lang = cfg.get("lang", "zh")
    if lang not in LANGS:
        problems.append("lang 只能是 %s，实际 %r" % (" / ".join(LANGS), lang))
    cap = cfg.get("max_notes", DEFAULT_MAX_NOTES)
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        problems.append("max_notes 必须是不小于 1 的整数，实际 %r" % (cap,))
    floor = cfg.get("min_anchored", DEFAULT_MIN_ANCHORED)
    if not isinstance(floor, (int, float)) or isinstance(floor, bool) or not 0 <= floor <= 1:
        problems.append("min_anchored 必须是 0～1 的小数，实际 %r" % (floor,))

    items = cfg.get("criteria")
    if not isinstance(items, list) or not items:
        return problems + ["criteria 必须是非空数组：每条一个条目名，带不带分值都行"]
    seen, scored = set(), 0
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            problems.append("第 %d 条不是对象" % i)
            continue
        bad = sorted(set(item) - {"name", "points"})
        if bad:
            problems.append("第 %d 条多了不认识的键：%s" % (i, "、".join(bad)))
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append("第 %d 条的 name 必须是非空字符串，实际 %r" % (i, name))
        elif name in seen:
            problems.append("条目名重复：%s" % name)
        else:
            seen.add(name)
        pts = item.get("points")
        if pts is None:
            continue
        if not isinstance(pts, int) or isinstance(pts, bool) or pts < 0:
            problems.append("第 %d 条的 points 必须是非负整数或不填，实际 %r" % (i, pts))
        else:
            scored += 1
    if scored and scored != len(items):
        problems.append("条目分值要么全填要么全不填，现在 %d/%d 条填了" % (scored, len(items)))
    elif scored == len(items) and isinstance(limit, int):
        total = sum(item.get("points", 0) for item in items if isinstance(item, dict))
        if total != limit:
            problems.append("条目分值合计 %d 与满分 %d 对不上（这样永远拿不到满分）" % (total, limit))
    return problems


def normalize_config(cfg):
    """落盘形状固定：字段齐全、条目只留 name 与 points，哈希才稳。"""
    return {
        "max": cfg["max"],
        "lang": cfg.get("lang", "zh"),
        "max_notes": cfg.get("max_notes", DEFAULT_MAX_NOTES),
        "min_anchored": cfg.get("min_anchored", DEFAULT_MIN_ANCHORED),
        "criteria": [{"name": c["name"], "points": c.get("points")} for c in cfg["criteria"]],
    }


# ---------------------------------------------------------------- 练习目录

class Practice:
    """practice/<slug>/ 的读写门面：脚本只碰这个目录里的文件。"""

    def __init__(self, path, need_config=True):
        self.dir = os.path.abspath(path)
        if not os.path.isdir(self.dir):
            raise UsageError("练习目录不存在：%s（先跑 init <slug>）" % path)
        self.slug = os.path.basename(self.dir.rstrip(os.sep)) or "practice"
        self.question_raw = read_text(self.path("question.md"))
        self.rubric_raw = read_text(self.path("rubric.md"))
        self.question_text = anchor.plain_text(self.question_raw)
        self.rubric_text = anchor.plain_text(self.rubric_raw)
        self.config = None
        if need_config:
            self.config = self._load_config()

    # --- 路径

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def rel(self, path):
        return os.path.relpath(path, self.dir).replace(os.sep, "/")

    def attempt_dir(self, name):
        return self.path("attempts", name)

    def answer_path(self, name):
        return self.path("attempts", name, "answer.md")

    def inbox_path(self, name):
        return self.path("attempts", name, "inbox", "grade.json")

    def result_path(self, name):
        return self.path("attempts", name, "result.json")

    def page_path(self, name):
        return self.path("attempts", name, "result.html")

    @property
    def stamp_path(self):
        return self.path(".stamps", "baseline.json")

    @property
    def progress_path(self):
        return self.path("progress.md")

    # --- 配置

    def _load_config(self):
        path = self.path("criteria.json")
        if not os.path.isfile(path):
            raise UsageError("还没有条目表：%s。先把 rubric 整理成条目表让自己确认，"
                             "再跑 criteria set <slug> --from <文件>。" % self.rel(path))
        cfg = read_json(path)
        problems = criteria_problems(cfg)
        if problems:
            raise UsageError("条目表不合格：%s\n  %s" % (self.rel(path), "\n  ".join(problems)))
        return normalize_config(cfg)

    @property
    def max(self):
        return self.config["max"]

    @property
    def criteria(self):
        return self.config["criteria"]

    def job(self):
        """validate_grade 要的那一份材料快照。"""
        out = dict(self.config)
        out["question_text"] = self.question_text
        out["rubric_text"] = self.rubric_text
        return out

    # --- attempt

    def answer_raw(self, name):
        path = self.answer_path(name)
        if not os.path.isfile(path):
            raise UsageError("还没有作答：%s。自己写，脚本不代写。" % self.rel(path))
        return read_text(path)

    def attempts(self):
        """真作答的稿号（不含三份对抗基线，也不含点开头的目录）。"""
        base = self.path("attempts")
        if not os.path.isdir(base):
            return []
        return sorted(n for n in os.listdir(base)
                      if not n.startswith(".") and n not in BASE_ATTEMPTS
                      and os.path.isdir(os.path.join(base, n)))

    def passed(self):
        return [n for n in self.attempts() if os.path.isfile(self.result_path(n))]

    def record(self, name):
        return read_json(self.result_path(name))

    def previous_pass(self, name):
        """上一个通过的真作答（不含基线，也不含自己）。"""
        earlier = [n for n in self.passed() if n < name]
        return self.record(earlier[-1]) if earlier else None

    def own_pass(self, name):
        """这个 attempt 自己上一次批出来的结果 —— 重批时拿它比，别让同一稿换分数。"""
        return self.record(name) if os.path.isfile(self.result_path(name)) else None

    # --- 基线盖章

    def baseline_body(self, name):
        """三份对抗作答的正身：由脚本按当前题目算出来，不存在「用户版本」。"""
        return {"base-empty": "",
                "base-echo": self.question_text + "\n",
                "base-noise": NOISE_ANSWER}[name]

    def baseline_intact_problems(self):
        """三份对抗作答必须还是磁盘上脚本生成的那一份，且结果就是照它批出来的。"""
        out = []
        for name in BASE_ATTEMPTS:
            path, body = self.answer_path(name), self.baseline_body(name)
            if not os.path.isfile(path) or read_text(path) != body:
                out.append("attempts/%s/answer.md 已经不是 baseline 生成的那一份" % name)
                continue
            if not os.path.isfile(self.result_path(name)):
                continue                       # 还没批，缺哪份由 baseline_problem 去说
            if self.record(name).get("answer_hash") != sha256_text(body):
                out.append("基线 %s 的结果不是照现在这份作答批的" % name)
        return out

    def material_hashes(self):
        return {"question": sha256_text(self.question_text),
                "rubric": sha256_text(self.rubric_text),
                "criteria": sha256_text(canonical(self.criteria))}

    def stamp_baselines(self):
        """三份基线都 0 分全未命中才盖章；差一份就不盖，返回 None。"""
        for name in BASE_ATTEMPTS:
            if not os.path.isfile(self.result_path(name)):
                return None
            rec = self.record(name)
            if rec.get("points") or any(it.get("verdict") != "miss" for it in rec.get("criteria", [])):
                return None
            if rec.get("answer_hash") != sha256_text(self.baseline_body(name)):
                return None
        stamp = self.material_hashes()
        stamp["checkedAt"] = today()
        stamp["baselines"] = list(BASE_ATTEMPTS)
        write_json(self.stamp_path, stamp)
        return stamp

    def baseline_problem(self):
        """真作答的前置：没盖章或材料改过都不放行；返回提示文字，None 即放行。"""
        if not os.path.isfile(self.stamp_path):
            missing = [n for n in BASE_ATTEMPTS if not os.path.isfile(self.result_path(n))]
            if missing:
                return ("三份对抗基线还没批完（缺 %s）。先跑 baseline <slug> 生成它们，"
                        "再把 %s 各 grade 一遍 —— 脚本确认三份都是 0 分才放行真作答。"
                        % ("、".join(missing), "、".join(BASE_ATTEMPTS)))
            return ("三份对抗基线都批过了却没有盖章，说明有一份没过基线闸。"
                    "回头看那一份的 grade 输出，改完重批。")
        stamp = read_json(self.stamp_path)
        now = self.material_hashes()
        for key in ("question", "rubric", "criteria"):
            if stamp.get(key) != now[key]:
                return ("盖章之后「%s」改过了，基线作废。重跑 baseline <slug> 并把三份基线重批一遍。"
                        % {"question": "题目", "rubric": "评分标准", "criteria": "条目表"}[key])
        bad = self.baseline_intact_problems()
        if bad:
            return ("%s，盖章作废。重跑 baseline <slug> 拿回原样，再把三份基线重批一遍。"
                    % "；".join(bad))
        return None


# ---------------------------------------------------------------- 闸门

def validate_grade(job, answer_text, payload):
    """校验一份评分结果 JSON，返回 (errors, warnings, normalized)。

    与 rubric-grader 的同名函数是同一套契约（spec §3.2 / §3.4）。两个 Skill 必须能各自
    整目录拷走独立安装，所以这段是复制而不是共享模块。
    `answer_text` 是 answer.md 的原文；纯文本与位置映射由函数内一次 `extract` 同时得到。

    只有一处**故意**比 rubric-grader 严：条目表不标分值时，`_gate_points_sum` 仍守住
    「引文锚不到就整份退回」与「全部未命中就不许有分」两条底线（自批没有第二个人复核，
    这两条一让开就等于白给分）。别把它当成没对齐而删掉。
    """
    # 与 rubric-grader 同步：改这里要同步改 grader.py 的 validate_grade，以那一份为准。
    errors, warnings = [], []

    def err(name, message):
        errors.append({"name": name, "message": message})

    def warn(name, message):
        warnings.append({"name": name, "message": message})

    if not isinstance(payload, dict):
        err("payload_keys", "结果必须是一个 JSON 对象，实际是 %s" % type(payload).__name__)
        return errors, warnings, None

    table = job["criteria"]
    limit = job["max"]
    lang = job.get("lang", "zh")
    cap = job.get("max_notes", DEFAULT_MAX_NOTES)
    floor = job.get("min_anchored", DEFAULT_MIN_ANCHORED)
    extraction = anchor.extract(answer_text)          # 抽文本与建位置映射同一次遍历

    _gate_keys(payload, err)
    _gate_hash(job, extraction.text, payload, err)
    points = _gate_points(payload, limit, err)
    items = _gate_criteria(payload, table, err)
    submitted = [it["verdict"] for it in items]
    _gate_evidence(items, extraction, err, warn)
    _gate_points_sum(items, submitted, table, points, err)
    result = _gate_marks(payload, answer_text, cap, floor, err, warn)
    _gate_summary(payload, lang, err)
    _gate_hollow(result.marks, extraction.text, warn)

    normalized = {
        "context_hash": context_hash(job, extraction.text),
        "points": points,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), str) else "",
        "criteria": items,
        "marks": result.marks,
        "anchored_ratio": result.anchored_ratio,
    }
    return errors, warnings, normalized


def _gate_keys(payload, err):
    """顶层键白名单：别的字段名一律不收，免得换个名字就把契约绕过去。"""
    extra = sorted(set(payload) - set(PAYLOAD_KEYS))
    missing = sorted(set(PAYLOAD_KEYS) - set(payload))
    if extra:
        err("payload_keys", "顶层多了不认识的键：%s（只收 %s）"
            % ("、".join(extra), "、".join(PAYLOAD_KEYS)))
    if missing:
        err("payload_keys", "顶层缺少必填键：%s" % "、".join(missing))


def _gate_hash(job, answer_plain, payload, err):
    """哈希对不上：要么没跑 context，要么材料改了还在用旧结果。"""
    want = context_hash(job, answer_plain)
    got = payload.get("context_hash")
    if got != want:
        err("context_hash", "上下文哈希对不上：结果里是 %s，当前材料算出来是 %s。"
                            "先跑 context，照它写结果。" % (short_hash(got), short_hash(want)))


def _gate_points(payload, limit, err):
    points = payload.get("points")
    if not isinstance(points, int) or isinstance(points, bool):
        err("points_range", "points 必须是整数，实际 %r" % (points,))
        return None
    if not 0 <= points <= limit:
        err("points_range", "points 应在 0～%d 之间，实际 %d" % (limit, points))
    return points


def _gate_criteria(payload, table, err):
    """条目必须与条目表一一对应，不多不少；顺序不论，脚本自己按条目表排好。

    条目名是对应关系的唯一依据（与 rubric-grader 同口径）：模型换个顺序交上来不算错，
    少一条、多一条、同一条交两次才算。对应不上时返回空列表，后面的分值闸自动让开 ——
    条目都没对齐，再去算「这个分数对不对」只会刷出一堆连带错误。
    """
    raw = payload.get("criteria")
    if not isinstance(raw, list):
        err("criteria_table", "criteria 必须是数组，实际 %r" % (raw,))
        return []
    want = [c["name"] for c in table]
    seen, broken = {}, False
    for i, one in enumerate(raw, 1):
        if not isinstance(one, dict):
            err("criteria_table", "第 %d 条不是对象" % i)
            broken = True
            continue
        bad = sorted(set(one) - set(CRITERIA_KEYS))
        if bad:
            err("criteria_keys", "第 %d 条多了不认识的键：%s（只收 %s）"
                % (i, "、".join(bad), "、".join(CRITERIA_KEYS)))
        verdict = one.get("verdict")
        if verdict not in VERDICTS:
            err("verdict_value", "第 %d 条的 verdict 只能是 %s，实际 %r"
                % (i, " / ".join(VERDICTS), verdict))
            verdict = None
        name = str(one.get("name") or "")
        if name in seen:
            err("criteria_table", "条目「%s」提交了两次" % name)
            broken = True
        seen[name] = {"name": name, "verdict": verdict, "quote": str(one.get("quote") or "")}
    absent = [n for n in want if n not in seen]
    extra = [n for n in sorted(seen) if n not in want]
    if absent:
        err("criteria_table", "criteria 少了条目表里的：%s" % "、".join(absent))
        broken = True
    if extra:
        err("criteria_table", "criteria 多了条目表以外的：%s" % "、".join(extra))
        broken = True
    return [] if broken else [seen[n] for n in want]


def _gate_evidence(items, extraction, err, warn):
    """命中要有原文撑着：引文空是错，引文锚不到就降为未命中。"""
    for it in items:
        if it["verdict"] not in ("hit", "partial"):
            continue
        quote = it["quote"].strip()
        if not quote:
            err("evidence", "条目「%s」判了 %s 却没给引文" % (it["name"], it["verdict"]))
            it["verdict"] = "miss"
            it["evidence_unanchored"] = True
        elif anchor.locate(extraction, quote) is None:
            warn("evidence_unanchored", "条目「%s」的引文在作答里找不到，已降为未命中：%s"
                 % (it["name"], clip(quote)))
            it["verdict"] = "miss"
            it["evidence_unanchored"] = True


def _gate_points_sum(items, submitted, table, points, err):
    """分数得跟条目判定对得上：带分值的逐条算，不带分值的至少不能自相矛盾。"""
    by_name = dict((c["name"], c.get("points")) for c in table)
    if not table or len(items) != len(table) or any(it["name"] not in by_name for it in items):
        return
    if any(v is None for v in submitted):
        return
    final = [it["verdict"] for it in items]
    if any(c.get("points") is None for c in table):
        # 条目不带分值：算不出「降级该扣多少」，所以只能守住两条底线
        fell = [it["name"] for it in items if it.get("evidence_unanchored")]
        if fell:
            err("evidence_points", "条目表没标分值，脚本算不出证据落空该扣多少分，"
                                   "所以引文一锚不到就整份退回：%s。换一句真的在作答里的引文，"
                                   "或者如实判未命中。" % "、".join(str(x) for x in fell))
        if points and all(v == "miss" for v in final):
            err("points_sum", "条目全部未命中，却给了 %d 分 —— 分数没有任何条目撑着" % points)
        return

    def total(verdicts):
        got = 0
        for it, verdict in zip(items, verdicts):
            worth = by_name[it["name"]] or 0
            if verdict == "hit":
                got += worth
            elif verdict == "partial":
                got += worth // 2
        return got

    raw = total(submitted)
    if points is not None and points != raw:
        err("points_sum", "points 是 %d，但按条目判定算出来是 %d（命中给满、部分给一半向下取整）"
            % (points, raw))
    after = total(final)
    if after != raw:
        err("evidence_points", "证据锚不到让分数从 %d 变成了 %d，整份退回重批 —— "
                               "要么换一句真的在作答里的引文，要么如实判未命中" % (raw, after))


def _gate_marks(payload, answer_text, cap, floor, err, warn):
    """批注：条数有上限、引文非空、批语够长、不许两条一模一样、锚定率要够。"""
    raw = payload.get("marks")
    if not isinstance(raw, list):
        err("notes_cap", "marks 必须是数组，实际 %r" % (raw,))
        raw = []
    if len(raw) > cap:
        err("notes_cap", "批注最多 %d 条，实际 %d 条（自批不是把作答重写一遍）" % (cap, len(raw)))

    clean, seen = [], {}
    for i, one in enumerate(raw, 1):
        if not isinstance(one, dict):
            err("note_quality", "第 %d 条批注不是对象" % i)
            continue
        bad = sorted(set(one) - set(MARK_KEYS))
        if bad:
            err("mark_keys", "第 %d 条批注多了不认识的键：%s（只收 %s）"
                % (i, "、".join(bad), "、".join(MARK_KEYS)))
        quote = str(one.get("quote") or "")
        note = str(one.get("note") or "")
        if not quote.strip():
            err("note_quality", "第 %d 条批注没给引文" % i)
        if len(note.strip()) < NOTE_MIN:
            err("note_quality", "第 %d 条批注的批语不足 %d 字：%s" % (i, NOTE_MIN, clip(note)))
        # 重复判据用规范化后的批语：只差一个空格或一对弯引号，说的还是同一句话。
        key = anchor.normalize(note)
        if key and key in seen:
            err("note_dup", "第 %d 条与第 %d 条的批语一字不差：%s" % (i, seen[key], clip(note)))
        seen.setdefault(key, i)
        clean.append({"quote": quote, "level": one.get("level", anchor.DEFAULT_LEVEL), "note": note})

    result = anchor.annotate(answer_text, clean)
    missed = [m for m in result.marks if not m.get("anchored")]
    if clean and result.anchored_ratio < floor:
        err("anchored_ratio", "锚定率 %.0f%%，低于 %.0f%%。锚不到的引文：%s"
            % (result.anchored_ratio * 100, floor * 100,
               "；".join(clip(m["quote"]) for m in missed[:5])))
    fixed = [m for m in result.marks if m.get("level_fixed")]
    if fixed:
        warn("level_fixed", "%d 条批注的等级不在白名单，已按「%s」处理"
             % (len(fixed), anchor.DEFAULT_LEVEL))
    dropped = [m for m in result.marks if m.get("dropped_overlap")]
    if dropped:
        warn("overlap", "%d 条批注与别的条目在原文上重叠，判题卡里没给它们画线" % len(dropped))
    return result


def _gate_summary(payload, lang, err):
    """总评长度闸：只查长度，不查里面写了什么。"""
    summary = payload.get("summary")
    low, high = SUMMARY_RANGE
    unit = "词" if lang == "en" else "字"
    if not isinstance(summary, str):
        err("summary_length", "summary 必须是字符串，实际 %r" % (summary,))
        return
    size = count_units(summary, lang)
    if not low <= size <= high:
        err("summary_length", "总评应在 %d～%d %s，实际 %d %s" % (low, high, unit, size, unit))
    found = _RECAP.search(summary)
    if found:
        err("summary_recap", "总评里出现了逐题复述（「%s」）；这是一道题的自批，说结论就好"
            % found.group(0))


def _gate_hollow(marks, answer_plain, warn):
    """空心闸（只提示）：引文都极短、批语跟作答一个字都不搭 —— 多半是套话。"""
    if not marks:
        return
    if any(len(anchor.normalize(m.get("quote", ""))) > SHORT_QUOTE for m in marks):
        return
    grams = trigrams(answer_plain)
    if any(trigrams(m.get("note", "")) & grams for m in marks):
        return
    warn("hollow", "所有批注的引文都不超过 %d 字，批语也和作答没有一个三字片段重合，"
                   "像是套话；回头确认这些批注是不是真读了作答" % SHORT_QUOTE)


def gate_baseline_intact(ws, name, answer, errors):
    """对抗基线是脚本写的：手改过就不是对抗了，重跑 baseline 拿回原样。"""
    if answer != ws.baseline_body(name):
        errors.append({"name": "baseline_intact",
                       "message": "attempts/%s/answer.md 不是 baseline 生成的那一份（被改过，"
                                  "或者题目变了却没重跑）。重跑 baseline 拿回原样再批。" % name})


def gate_baseline_zero(normalized, errors):
    """基线闸：空作答、题面回贴、无关段落，三份都必须 0 分且条目全未命中。"""
    if normalized is None:
        return
    if normalized.get("points"):
        errors.append({"name": "baseline_zero",
                       "message": "对抗基线拿到了 %d 分。空作答 / 题面回贴 / 无关段落都该是 0 分；"
                                  "会给它们分的标准，用在真作答上也不作数。" % normalized["points"]})
    hit = [it["name"] for it in normalized["criteria"] if it.get("verdict") in ("hit", "partial")]
    if hit:
        errors.append({"name": "baseline_zero",
                       "message": "对抗基线上有条目判成了命中：%s" % "、".join(str(n) for n in hit)})


def gate_regrade(own, answer_hash, normalized, errors):
    """同稿闸的另一半：同一个 attempt 重批，作答没改就不该批出另一个分数。"""
    if own is None or normalized is None:
        return
    if own.get("answer_hash") != answer_hash:
        return
    if normalized.get("points") != own.get("points"):
        errors.append({"name": "same_draft",
                       "message": "attempt %s 上次批的是 %s 分，作答一字未改，这次却批成 %s 分。"
                                  "重批不该换分数 —— 要么改作答另起一稿，"
                                  "要么先说清上次哪条判错了再改。"
                                  % (own.get("attempt"), own.get("points"),
                                     normalized.get("points"))})


def gate_same_draft(previous, answer_hash, normalized, errors):
    """同稿闸：一字未改的稿子不该评出两个分数。返回是否同稿。"""
    if previous is None or normalized is None:
        return False
    if previous.get("answer_hash") != answer_hash:
        return False
    if normalized.get("points") != previous.get("points"):
        errors.append({"name": "same_draft",
                       "message": "这份作答与 attempt %s 一字不差，却评出了 %s 分（上次 %s 分）。"
                                  "同一稿评出不同分，说明标准在飘 —— 对齐后再批。"
                                  % (previous.get("attempt"), normalized.get("points"),
                                     previous.get("points"))})
    return True


def gate_monotonic(previous, normalized, warnings):
    """单调提示：分数掉了不拦，但要说一声。"""
    if previous is None or normalized is None:
        return
    now, before = normalized.get("points"), previous.get("points")
    if isinstance(now, int) and isinstance(before, int) and now < before:
        warnings.append({"name": "monotonic",
                         "message": "这次 %d 分，比 attempt %s 的 %d 分低。改稿之后掉分是可能的，"
                                    "但先核对一下是不是这次批得更严了。"
                                    % (now, previous.get("attempt"), before)})


def report_gates(errors, warnings):
    print("闸门：")
    for gate in errors:
        print("  [ERROR] %s：%s" % (gate["name"], gate["message"]))
    for gate in warnings:
        print("  [WARN] %s：%s" % (gate["name"], gate["message"]))
    if not errors and not warnings:
        print("  全部通过")


# ---------------------------------------------------------------- 子命令

def cmd_doctor(args):
    version = "%d.%d.%d" % sys.version_info[:3]
    print("self-grader 环境检查（selfgrade.py 由 Python %s 运行，%s）" % (version, sys.platform))
    worst = 0
    if sys.version_info[:2] >= (3, 8):
        print("  [OK]   Python           %s" % version)
    else:
        print("  [缺失] Python           %s —— 本脚本需要 3.8 及以上" % version)
        worst = 2
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("anchor.py", "banned_words.py"):
        path = os.path.join(here, name)
        if os.path.isfile(path):
            print("  [OK]   %-16s 就位（%d 字节）" % (name, os.path.getsize(path)))
        else:
            print("  [缺失] %-16s 不在 scripts/ 里，整个目录拷贝时漏掉了" % name)
            worst = 2
    try:
        probe = anchor.extract("<p>一段用来冒烟的短文</p>")
        hit = anchor.locate(probe, "用来冒烟")
        marked = anchor.annotate("<p>一段用来冒烟的短文</p>",
                                 [{"quote": "用来冒烟", "level": "minor", "note": "冒烟自测"}])
        ok = hit is not None and marked.anchored_ratio == 1.0
    except Exception as e:                                        # 引擎坏了要说清楚
        print("  [缺失] anchor.py         冒烟失败：%s：%s" % (type(e).__name__, e))
        return 2
    if ok:
        print("  [OK]   引擎冒烟         抽取 / 定位 / 批注都跑通了")
    else:
        print("  [缺失] 引擎冒烟         抽取 / 定位 / 批注没跑通，引擎那份拷贝可能损坏了")
        worst = 2
    print("提示：脚本只读写你指定的练习目录，不联网，也不执行你的作答。")
    print("提示：评分标准由你自带 —— 本 Skill 不内置任何学科标准，也不会替你猜。")
    return worst


def cmd_init(args):
    ws_dir = resolve_ws(args.slug)
    os.makedirs(ws_dir, exist_ok=True)
    made = []
    for rel, body in (("question.md", QUESTION_STUB), ("rubric.md", RUBRIC_STUB),
                      ("progress.md", PROGRESS_HEAD)):
        path = os.path.join(ws_dir, rel)
        if not os.path.isfile(path):
            write_text(path, body)
            made.append(rel)
    for rel in (os.path.join("attempts", "01", "inbox"), ".stamps"):
        os.makedirs(os.path.join(ws_dir, rel), exist_ok=True)
    answer = os.path.join(ws_dir, "attempts", "01", "answer.md")
    if not os.path.isfile(answer):
        write_text(answer, "")
        made.append("attempts/01/answer.md")
    print("练习目录：%s" % ws_dir)
    print("新建：%s" % ("、".join(made) if made else "（都已存在，没动任何文件）"))
    print("下一步：")
    print("  1. 把题目贴进 question.md，把你自己带来的评分标准贴进 rubric.md")
    print("  2. 把 rubric 整理成条目表，自己确认无误后 criteria set %s --from <文件>" % args.slug)
    print("  3. baseline %s —— 先批三份假作答，证明这套标准不会白给分" % args.slug)
    return 0


def cmd_criteria(args):
    if args.sub != "set":
        raise UsageError("criteria 只有一个子命令：set")
    ws_dir = resolve_ws(args.slug)
    if not os.path.isdir(ws_dir):
        raise UsageError("练习目录不存在：%s（先跑 init <slug>）" % ws_dir)
    cfg = read_json(args.src)
    problems = criteria_problems(cfg)
    if problems:
        raise UsageError("条目表不合格：%s\n  %s" % (args.src, "\n  ".join(problems)))
    clean = normalize_config(cfg)
    write_json(os.path.join(ws_dir, "criteria.json"), clean)
    print("条目表已写入：%s" % os.path.join(ws_dir, "criteria.json"))
    print("满分 %d · 语言 %s · 批注上限 %d 条 · 锚定率下限 %.0f%%"
          % (clean["max"], clean["lang"], clean["max_notes"], clean["min_anchored"] * 100))
    for item in clean["criteria"]:
        worth = "%d 分" % item["points"] if item["points"] is not None else "未标分值"
        print("  · %s（%s）" % (item["name"], worth))
    print("下一步：baseline %s" % args.slug)
    return 0


def cmd_baseline(args):
    ws = Practice(resolve_ws(args.slug))
    for name in BASE_ATTEMPTS:
        write_text(ws.answer_path(name), ws.baseline_body(name))
        os.makedirs(os.path.join(ws.attempt_dir(name), "inbox"), exist_ok=True)
    print("对抗基线已生成（三份都是脚本写的，不用你看）：")
    print("  · attempts/base-empty/answer.md    空文件")
    print("  · attempts/base-echo/answer.md     题面纯文本原样回贴")
    print("  · attempts/base-noise/answer.md    与本题无关的固定段落")
    if os.path.isfile(ws.stamp_path):
        print("提示：已有基线盖章；材料没改过的话不必重批。")
    print("下一步：把三份各批一遍 —— context <slug> base-empty → 写 inbox/grade.json → "
          "grade <slug> base-empty，另外两份同理。")
    print("三份都判 0 分、条目全未命中，脚本才会盖章放行真作答。")
    return 0


def cmd_context(args):
    ws = Practice(resolve_ws(args.slug))
    name = check_attempt(args.attempt)
    os.makedirs(os.path.join(ws.attempt_dir(name), "inbox"), exist_ok=True)
    path = ws.answer_path(name)
    if not os.path.isfile(path):
        write_text(path, "")
        raise UsageError("已建好 %s，现在它还是空的。先自己把作答写进去 —— 脚本不代写。"
                         % ws.rel(path))
    raw = read_text(path)
    if not raw.strip() and name not in BASE_ATTEMPTS:
        raise UsageError("%s 还是空的。先自己把作答写进去 —— 脚本不代写。" % ws.rel(path))
    answer_plain = anchor.plain_text(raw)
    job = ws.job()
    pack = {
        "slug": ws.slug,
        "attempt": name,
        "max": ws.max,
        "lang": job["lang"],
        "max_notes": job["max_notes"],
        "min_anchored": job["min_anchored"],
        "criteria": ws.criteria,
        "question_text": ws.question_text,
        "rubric_text": ws.rubric_text,
        "answer_text": answer_plain,
        "context_hash": context_hash(job, answer_plain),
        "inbox": ws.rel(ws.inbox_path(name)),
    }
    print(json.dumps(pack, ensure_ascii=False, indent=2))
    print("上下文包已输出；照它的 context_hash 与条目名写结果，放进 %s。"
          % ws.rel(ws.inbox_path(name)), file=sys.stderr)
    return 0


def cmd_grade(args):
    ws = Practice(resolve_ws(args.slug))
    name = check_attempt(args.attempt)
    is_base = name in BASE_ATTEMPTS
    print("批改：%s · attempt %s%s" % (ws.slug, name, "（对抗基线）" if is_base else ""))
    if not is_base:
        problem = ws.baseline_problem()
        if problem:
            raise UsageError(problem)
    answer = ws.answer_raw(name)
    inbox = ws.inbox_path(name)
    if not os.path.isfile(inbox):
        raise UsageError("还没有结果文件：%s。先跑 context %s %s，照它写一份放进去。"
                         % (ws.rel(inbox), args.slug, name))

    errors, warnings, normalized = validate_grade(ws.job(), answer, read_json(inbox))
    answer_hash = sha256_text(answer)
    same_draft = False
    if is_base:
        gate_baseline_intact(ws, name, answer, errors)
        gate_baseline_zero(normalized, errors)
    else:
        gate_regrade(ws.own_pass(name), answer_hash, normalized, errors)
        previous = ws.previous_pass(name)
        same_draft = gate_same_draft(previous, answer_hash, normalized, errors)
        gate_monotonic(previous, normalized, warnings)

    report_gates(errors, warnings)
    if errors:
        print("结论：未通过（%d ERROR，%d WARN）· %s 保留 —— 改结果，别改作答"
              % (len(errors), len(warnings), ws.rel(inbox)))
        return 1

    result = anchor.annotate(answer, normalized["marks"])
    record = {
        "slug": ws.slug,
        "attempt": name,
        "checkedAt": today(),
        "points": normalized["points"],
        "max": ws.max,
        "summary": normalized["summary"],
        "criteria": normalized["criteria"],
        "marks": result.marks,
        "anchored_ratio": result.anchored_ratio,
        "context_hash": normalized["context_hash"],
        "answer_hash": answer_hash,
        "sameDraft": same_draft,
    }
    write_json(ws.result_path(name), record)
    write_text(ws.page_path(name), anchor.render_page(
        "自批判题卡 · %s · attempt %s" % (ws.slug, name), answer, result,
        {"得分": "%d/%d" % (record["points"], ws.max), "日期": record["checkedAt"]}))

    misses = [it["name"] for it in record["criteria"] if it.get("verdict") == "miss"]
    if not is_base:
        append_progress(ws, record)
    tail = ""
    if is_base:
        tail = (" · 已盖章，可以批真作答了" if ws.stamp_baselines()
                else " · 还差别的基线，三份齐了才盖章")
    print("结论：通过（0 ERROR，%d WARN）· %d/%d · 未命中：%s · 判题卡 %s%s"
          % (len(warnings), record["points"], ws.max, "、".join(misses) if misses else "无",
             ws.rel(ws.page_path(name)), tail))
    return 0


def progress_line(record):
    """一份 result.json 对应 progress.md 里的哪一行 —— 写和复核都用这一个来源。"""
    misses = [it.get("name") for it in record.get("criteria", []) if it.get("verdict") == "miss"]
    return "- %s · attempt %s · %s/%s · 未命中：%s%s" % (
        record.get("checkedAt"), record.get("attempt"), record.get("points"), record.get("max"),
        "、".join(str(x) for x in misses) if misses else "无",
        " · sameDraft" if record.get("sameDraft") else "")


def append_progress(ws, record):
    """progress.md 只增：一行一次通过的批改，重复的一行不再追加。"""
    line = progress_line(record)
    text = read_text(ws.progress_path) if os.path.isfile(ws.progress_path) else PROGRESS_HEAD
    if line in text.split("\n"):
        return
    if text and not text.endswith("\n"):
        text += "\n"
    write_text(ws.progress_path, text + line + "\n")


def anchor_drift(name, record, normalized):
    """落盘的每条 anchored 必须等于重新锚定算出来的那一个。

    锚定率对得上不等于每条都对得上：把一条 true 改成 false、另一条 false 改成 true，
    比率一点没变。而判题卡和导出直接读这个字段，不对账就等于让人手写「这条我锚上了」。
    """
    problems = []
    stored = [m for m in record.get("marks", []) if isinstance(m, dict)]
    fresh = (normalized or {}).get("marks") or []
    if len(stored) != len(fresh):
        return ["attempt %s 落盘 %d 条批注，重新锚定得到 %d 条" % (name, len(stored), len(fresh))]
    bad = [i for i, (a, b) in enumerate(zip(stored, fresh), 1)
           if bool(a.get("anchored")) != bool(b.get("anchored"))]
    if bad:
        problems.append("attempt %s 第 %s 条批注落盘的 anchored 与重新锚定的结论对不上；"
                        "锚没锚上由引擎说了算，不许手改"
                        % (name, "、".join(str(i) for i in bad)))
    return problems


def drafts_of(ws):
    """按 answer 哈希把连续同稿折成一稿；走势只看稿子变了几次。"""
    out = []
    for name in ws.passed():
        rec = ws.record(name)
        if out and out[-1]["answer_hash"] == rec.get("answer_hash"):
            continue
        out.append(rec)
    return out


def cmd_progress(args):
    ws = Practice(resolve_ws(args.slug))
    text = read_text(ws.progress_path).rstrip("\n") if os.path.isfile(ws.progress_path) else ""
    print(text if text.strip() else "还没有通过的批改记录。")
    drafts = drafts_of(ws)
    if not drafts:
        print("走势：还没有通过的批改，先写一稿、跑一次 grade 再来看。")
        return 0
    if len(drafts) == 1:
        print("走势：只有 1 稿（%d/%d），再改一稿才看得出方向。"
              % (drafts[0]["points"], drafts[0]["max"]))
        return 0
    first, last = drafts[0], drafts[-1]
    if last["points"] > first["points"]:
        trend = "在涨"
    elif last["points"] < first["points"]:
        trend = "在降"
    else:
        trend = "持平"
    print("走势：共 %d 稿（同稿重批不计），从 %d/%d 到 %d/%d，%s。"
          % (len(drafts), first["points"], first["max"], last["points"], last["max"], trend))
    return 0


def cmd_check(args):
    ws = Practice(resolve_ws(args.slug))
    errors, warnings = [], []

    def err(name, message):
        errors.append({"name": name, "message": message})

    def warn(name, message):
        warnings.append({"name": name, "message": message})

    print("复核：%s（%d 个条目，满分 %d）" % (ws.slug, len(ws.criteria), ws.max))
    problem = ws.baseline_problem()
    if problem:
        err("baseline", problem)
    for name in BASE_ATTEMPTS:
        if not os.path.isfile(ws.result_path(name)):
            continue
        rec = ws.record(name)
        hit = [it["name"] for it in rec.get("criteria", []) if it.get("verdict") != "miss"]
        if rec.get("points") or hit:
            err("baseline_zero", "基线 %s 的结果不是 0 分全未命中（%s 分，命中 %s）"
                % (name, rec.get("points"), "、".join(str(n) for n in hit) or "无"))

    progress = read_text(ws.progress_path) if os.path.isfile(ws.progress_path) else ""
    previous = None
    for name in ws.passed():
        rec = ws.record(name)
        answer = ws.answer_raw(name)
        replay = {
            "context_hash": rec.get("context_hash"),
            "points": rec.get("points"),
            "summary": rec.get("summary"),
            "criteria": [{"name": it.get("name"), "verdict": it.get("verdict"),
                          "quote": it.get("quote", "")} for it in rec.get("criteria", [])],
            "marks": [{"quote": m.get("quote", ""), "level": m.get("level"),
                       "note": m.get("note", "")} for m in rec.get("marks", [])],
        }
        again, again_warn, normalized = validate_grade(ws.job(), answer, replay)
        for gate in again:
            err("replay", "attempt %s 重跑闸门没过 —— %s：%s" % (name, gate["name"], gate["message"]))
        for gate in again_warn:
            warn("replay", "attempt %s 重跑闸门提示 —— %s：%s" % (name, gate["name"], gate["message"]))
        if normalized and abs(normalized["anchored_ratio"] - (rec.get("anchored_ratio") or 0)) > 1e-6:
            err("anchored_ratio", "attempt %s 存的锚定率 %r 与重算的 %r 对不上"
                % (name, rec.get("anchored_ratio"), normalized["anchored_ratio"]))
        for gate in anchor_drift(name, rec, normalized):
            err("anchored_flag", gate)
        if rec.get("answer_hash") != sha256_text(answer):
            err("answer_hash", "attempt %s 的 answer.md 在批改之后改过了，这份结果已作废" % name)
        if previous is not None and previous.get("answer_hash") == rec.get("answer_hash") \
                and previous.get("points") != rec.get("points"):
            err("same_draft", "attempt %s 与 %s 是同一稿，分数却不一样（%s / %s）"
                % (previous.get("attempt"), name, previous.get("points"), rec.get("points")))
        want_line = progress_line(rec)
        if want_line not in progress.split("\n"):
            err("progress", "progress.md 里没有 attempt %s 那一行的原样记录。"
                            "按 result.json 重算，它应当是：%s" % (name, want_line))
        previous = rec

    report_gates(errors, warnings)
    print("结论：%s（%d ERROR，%d WARN）· 复核了 %d 份真作答"
          % ("通过" if not errors else "未通过", len(errors), len(warnings), len(ws.passed())))
    return 1 if errors else 0


def cmd_export(args):
    ws = Practice(resolve_ws(args.slug))
    rows = []
    for name in ws.passed():
        rec = ws.record(name)
        rows.append({
            "id": name,
            "points": rec.get("points"),
            "verdicts": [it.get("verdict") for it in rec.get("criteria", [])],
            "anchored_ratio": rec.get("anchored_ratio"),
            "sameDraft": bool(rec.get("sameDraft")),
            "context_hash": rec.get("context_hash"),
        })
    stamp = read_json(ws.stamp_path) if os.path.isfile(ws.stamp_path) else None
    print(json.dumps({"slug": ws.slug, "max": ws.max, "attempts": rows,
                      "baseline_stamp": stamp}, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- 入口

def build_parser():
    p = argparse.ArgumentParser(prog="selfgrade.py", description="self-grader 自批脚本")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("doctor", help="查看本机环境与引擎是否就位")
    i = sub.add_parser("init", help="建练习骨架")
    i.add_argument("slug", help="练习名（→ practice/<slug>），也可以直接给目录")
    c = sub.add_parser("criteria", help="条目表")
    csub = c.add_subparsers(dest="sub")
    cs = csub.add_parser("set", help="从 JSON 写入条目表")
    cs.add_argument("slug")
    cs.add_argument("--from", dest="src", required=True, help="条目表 JSON 文件")
    b = sub.add_parser("baseline", help="生成三份对抗作答")
    b.add_argument("slug")
    x = sub.add_parser("context", help="输出上下文包 JSON")
    x.add_argument("slug")
    x.add_argument("attempt", help="第几稿，如 01；对抗基线用 base-empty / base-echo / base-noise")
    g = sub.add_parser("grade", help="批一份作答")
    g.add_argument("slug")
    g.add_argument("attempt")
    r = sub.add_parser("progress", help="打印进度与走势")
    r.add_argument("slug")
    k = sub.add_parser("check", help="离线复核整个练习目录")
    k.add_argument("slug")
    e = sub.add_parser("export", help="导出脱敏证据")
    e.add_argument("slug")
    return p


HANDLERS = {"doctor": cmd_doctor, "init": cmd_init, "criteria": cmd_criteria,
            "baseline": cmd_baseline, "context": cmd_context, "grade": cmd_grade,
            "progress": cmd_progress, "check": cmd_check, "export": cmd_export}


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
        return HANDLERS[args.command](args)
    except UsageError as e:
        return _fail("错误：%s" % e)
    except KeyboardInterrupt:
        return _fail("已中断")
    except Exception as e:
        return _fail("错误：%s：%s" % (type(e).__name__, e))


def _fail(message):
    sys.stdout.flush()                       # 管道里 stdout 是块缓冲，不刷就跟 stderr 串位置了
    print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
