#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfgrade.py 自测：在临时目录里建练习工作区，走 init → criteria set → baseline → context →
grade → progress → check → export 全流程，逐条验证闸门的正反例，最后跑禁用词静态闸。

用法：python3 scripts/selftest.py
不依赖 examples/ 目录；examples/ 还没建时第 8 条用例自动跳过（计通过）。
所有作答、题目、评分标准都是合成的，跑完临时目录删除。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "selfgrade.py")
PY = sys.executable

SLUG = "library-due-date-01"

QUESTION_MD = """# 练习题

请用自己的话说明：为什么社区图书馆要给借出的书设置归还期限？请至少给出两条理由，并各举一个生活里的例子。
"""

RUBRIC_MD = """这份评分标准是练习者自带的（本例为合成示例），满分 5 分。

- 说清「期限让同一本书能在读者之间轮流」这一层，2 分。
- 说清「期限让管理方有一个可预期的回收时间点」这一层，2 分。
- 至少举出一个具体的生活例子，1 分。
"""

CRITERIA_IN = {
    "max": 5,
    "lang": "zh",
    "criteria": [
        {"name": "轮流可借", "points": 2},
        {"name": "可预期回收", "points": 2},
        {"name": "举例具体", "points": 1},
    ],
}

ANSWER_01 = (
    "设置归还期限，是为了让同一本书能在不同读者之间轮流，而不是被一个人长期占着。\n\n"
    "比如上个月我想借的那本画册一直显示在借，系统提示三天后到期，我预约之后果然很快就拿到了。\n\n"
    "这样一来，想读的人都能排上队。\n"
)

ANSWER_02 = (
    "设置归还期限，是为了让同一本书能在不同读者之间轮流，而不是被一个人长期占着。\n\n"
    "同时，期限给管理方一个可预期的回收时间点，书架上少了什么、什么时候补得回来，都能提前算出来。\n\n"
    "比如上个月我想借的那本画册一直显示在借，系统提示三天后到期，我预约之后果然很快就拿到了。\n"
)

Q_ROTATE = "让同一本书能在不同读者之间轮流"
Q_OCCUPY = "而不是被一个人长期占着"
Q_RECYCLE = "期限给管理方一个可预期的回收时间点"
Q_CASE = "系统提示三天后到期"
Q_BOOKED = "我预约之后果然很快就拿到了"
Q_QUEUE = "想读的人都能排上队"
Q_ABSENT = "这一句压根不在作答里出现过"

SUMMARY_3 = (
    "两条理由里只写清了轮流借阅这一层，管理方需要一个可预期回收时间点的那一层还没有正面说明；"
    "例子写得具体，看得出确实发生过。下一步先改哪一条：把回收时间点这条理由补上，"
    "并给它也配一个自己经历过的小例子，篇幅不用长。"
)

SUMMARY_5 = (
    "两条理由这次都摆到了台面上，轮流借阅与可预期回收各自成段，例子仍然具体可信，"
    "读起来比上一稿有条理。下一步先改哪一条：把第二条理由的例子也补成亲身经历，"
    "现在那一段还停在道理上，读者不容易记住。"
)

SUMMARY_BASE = (
    "这份作答没有正面回应题目要求的任何一层理由，也没有给出可以支撑判断的具体例子，"
    "三个条目都判为未命中。下一步先改哪一条：先把归还期限对读者的意义写成一句完整的话，"
    "再补一个自己遇到过的例子。"
)


# ---------------------------------------------------------------- 小工具

class Failed(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Failed(msg)


def run(cwd, *argv):
    proc = subprocess.run([PY, TOOL] + [str(a) for a in argv], cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    return proc.returncode, out, err


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_json(path, obj):
    write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def new_ws(root, criteria=True):
    """建一个练习工作区并放好题目与评分标准，返回工作区绝对路径。"""
    rc, out, err = run(root, "init", SLUG)
    check(rc == 0, "init 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    ws = os.path.join(root, "practice", SLUG)
    check(os.path.isdir(ws), "init 应建出 practice/<slug>，实际没有：%s" % out)
    write(os.path.join(ws, "question.md"), QUESTION_MD)
    write(os.path.join(ws, "rubric.md"), RUBRIC_MD)
    if criteria:
        src = os.path.join(root, "criteria-in.json")
        write_json(src, CRITERIA_IN)
        rc, out, err = run(root, "criteria", "set", SLUG, "--from", src)
        check(rc == 0, "criteria set 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    return ws


def context_of(root, attempt):
    rc, out, err = run(root, "context", SLUG, attempt)
    check(rc == 0, "context %s 应退出 0，rc=%d\n%s%s" % (attempt, rc, out, err))
    return json.loads(out)


def submit(ws, attempt, payload):
    write_json(os.path.join(ws, "attempts", attempt, "inbox", "grade.json"), payload)


def payload(root, attempt, points, verdicts, marks=None, summary=None):
    """按当前 context 组装一份合法结果；verdicts 是 (判定, 引文) 三元组列表。"""
    ctx = context_of(root, attempt)
    names = [c["name"] for c in ctx["criteria"]]
    return {
        "context_hash": ctx["context_hash"],
        "points": points,
        "summary": summary if summary is not None else SUMMARY_3,
        "criteria": [{"name": n, "verdict": v, "quote": q}
                     for n, (v, q) in zip(names, verdicts)],
        "marks": marks if marks is not None else [],
    }


def pass_baselines(root, ws):
    """把三份对抗基线各批一遍（全 0 分、全未命中），返回最后一次的输出。"""
    rc, out, err = run(root, "baseline", SLUG)
    check(rc == 0, "baseline 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    last = ""
    for name in ("base-empty", "base-echo", "base-noise"):
        body = payload(root, name, 0,
                       [("miss", ""), ("miss", ""), ("miss", "")],
                       marks=[], summary=SUMMARY_BASE)
        submit(ws, name, body)
        rc, out, err = run(root, "grade", SLUG, name)
        check(rc == 0, "基线 %s 应通过，rc=%d\n%s%s" % (name, rc, out, err))
        last = out
    return last


def graded_01(root, ws, answer=ANSWER_01):
    """走到「attempt 01 已通过」的状态，返回工作区。"""
    write(os.path.join(ws, "attempts", "01", "answer.md"), answer)
    pass_baselines(root, ws)
    body = payload(root, "01", 3,
                   [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)],
                   marks=[{"quote": Q_OCCUPY, "level": "minor",
                           "note": "这一层可以再往前推一句，说明轮流带来的好处。"},
                          {"quote": Q_QUEUE, "level": "remark",
                           "note": "结尾偏重复，换成第二条理由会更有分量。"}],
                   summary=SUMMARY_3)
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 0, "attempt 01 应通过，rc=%d\n%s%s" % (rc, out, err))
    return out


def gate_names(out, level):
    return [line.split("]", 1)[1].split("：", 1)[0].strip()
            for line in out.split("\n") if line.strip().startswith("[%s]" % level)]


# ---------------------------------------------------------------- 用例

def t_doctor(root):
    """doctor 要能报出本机 Python 与引擎是否就位。"""
    rc, out, err = run(root, "doctor")
    check(rc == 0, "doctor 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    check("[OK]" in out and "Python" in out, "doctor 应列出 Python：\n%s" % out)
    check("anchor.py" in out, "doctor 应报告引擎文件是否就位：\n%s" % out)
    return "doctor 列出 Python 与引擎状态"


def t_baseline_files(root):
    """baseline 生成三份对抗作答：空、题面回贴、固定无关段落。"""
    sys.path.insert(0, HERE)
    import selfgrade

    ws = new_ws(root)
    rc, out, err = run(root, "baseline", SLUG)
    check(rc == 0, "baseline 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    paths = dict((n, os.path.join(ws, "attempts", n, "answer.md"))
                 for n in ("base-empty", "base-echo", "base-noise"))
    for name, path in paths.items():
        check(os.path.isfile(path), "缺少 %s/answer.md" % name)
        check(os.path.isdir(os.path.join(os.path.dirname(path), "inbox")),
              "缺少 %s/inbox/" % name)
    check(read(paths["base-empty"]) == "", "base-empty 必须是空文件，实际 %r"
          % read(paths["base-empty"]))

    import anchor
    echo = read(paths["base-echo"])
    check(echo.strip() == anchor.plain_text(QUESTION_MD).strip(),
          "base-echo 应等于题面纯文本，实际 %r" % echo)

    noise = read(paths["base-noise"])
    check(noise == selfgrade.NOISE_ANSWER, "base-noise 应是脚本里的固定段落，实际 %r" % noise)
    check(60 <= len(noise.strip()) <= 140, "无关段落长度应在 60～140 字，实际 %d" % len(noise.strip()))
    qt = anchor.plain_text(QUESTION_MD)
    shared = [qt[i:i + 4] for i in range(len(qt) - 3) if qt[i:i + 4] in noise]
    check(not shared, "无关段落不该与题面共用四字窗口，实际重合：%r" % shared[:3])
    return "三份基线：空 / 题面回贴 / 固定无关段落，各带 inbox"


def t_grade_blocked_before_baseline(root):
    """基线还没批完就想批真作答 —— 退出 2，不给分。"""
    ws = new_ws(root)
    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_01)
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)])
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 2, "基线没批完时 grade 应退出 2，rc=%d\n%s%s" % (rc, out, err))
    check("基线" in (out + err), "应提示先跑基线：\n%s%s" % (out, err))
    check(not os.path.isfile(os.path.join(ws, "attempts", "01", "result.json")),
          "被拦下时不该写 result.json")

    # 只批两份基线仍然不放行
    run(root, "baseline", SLUG)
    for name in ("base-empty", "base-echo"):
        submit(ws, name, payload(root, name, 0, [("miss", "")] * 3, marks=[], summary=SUMMARY_BASE))
        rc, out, err = run(root, "grade", SLUG, name)
        check(rc == 0, "基线 %s 应通过，rc=%d\n%s%s" % (name, rc, out, err))
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 2, "三份基线只批了两份时仍应退出 2，rc=%d\n%s%s" % (rc, out, err))
    check(not os.path.isfile(os.path.join(ws, ".stamps", "baseline.json")),
          "基线没批齐不该盖章")

    # 批齐三份、盖了章，改一下评分标准 —— 盖章作废，照样退出 2
    submit(ws, "base-noise", payload(root, "base-noise", 0, [("miss", "")] * 3,
                                     marks=[], summary=SUMMARY_BASE))
    rc, out, err = run(root, "grade", SLUG, "base-noise")
    check(rc == 0, "第三份基线应通过，rc=%d\n%s%s" % (rc, out, err))
    check(os.path.isfile(os.path.join(ws, ".stamps", "baseline.json")), "三份齐了该盖章")
    submit(ws, "01", payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)]))
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 0, "盖章后真作答应能批，rc=%d\n%s%s" % (rc, out, err))
    write(os.path.join(ws, "rubric.md"), RUBRIC_MD + "\n- 追加一条：例子要是自己经历过的，1 分。\n")
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 2, "评分标准改过后盖章应作废，rc=%d\n%s%s" % (rc, out, err))
    check("作废" in (out + err), "应说清盖章为什么作废：\n%s%s" % (out, err))
    return "基线不齐 → 退出 2；批齐盖章 → 放行；改评分标准 → 盖章作废再退出 2"


def t_baseline_must_be_zero(root):
    """基线给了分就是白给分：拒收；三份全 0 分全未命中才盖章。"""
    ws = new_ws(root)
    rc, out, err = run(root, "baseline", SLUG)
    check(rc == 0, "baseline 应退出 0，rc=%d\n%s%s" % (rc, out, err))

    # 题面回贴的那份被判了 2 分：条目分值算得通，但基线闸不放行
    ctx = context_of(root, "base-echo")
    quote = "为什么社区图书馆要给借出的书设置归还期限"
    check(quote in ctx["answer_text"], "题面回贴的作答里应含题干原句：%r" % ctx["answer_text"])
    body = payload(root, "base-echo", 2,
                   [("hit", quote), ("miss", ""), ("miss", "")],
                   marks=[], summary=SUMMARY_BASE)
    submit(ws, "base-echo", body)
    rc, out, err = run(root, "grade", SLUG, "base-echo")
    check(rc == 1, "基线给了分应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("baseline_zero" in gate_names(out, "ERROR"),
          "应报 baseline_zero 闸门：\n%s" % out)

    stamp_path = os.path.join(ws, ".stamps", "baseline.json")
    check(not os.path.isfile(stamp_path), "基线没过不该盖章")

    # 把无关段落那份换成真作答，就不是对抗了 —— 拒收
    write(os.path.join(ws, "attempts", "base-noise", "answer.md"), ANSWER_01)
    submit(ws, "base-noise", payload(root, "base-noise", 0, [("miss", "")] * 3,
                                     marks=[], summary=SUMMARY_BASE))
    rc, out, err = run(root, "grade", SLUG, "base-noise")
    check(rc == 1, "手改过的基线应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("baseline_intact" in gate_names(out, "ERROR"),
          "应报 baseline_intact 闸门：\n%s" % out)

    last = pass_baselines(root, ws)
    check(os.path.isfile(stamp_path), "三份基线全过后应盖章：\n%s" % last)
    stamp = load(stamp_path)
    for key in ("question", "rubric", "criteria"):
        check(isinstance(stamp.get(key), str) and len(stamp[key]) == 64,
              "盖章应含 %s 的 sha256，实际 %r" % (key, stamp.get(key)))
    return "基线给分 / 手改基线 → 退出 1；三份 0 分全未命中 → 盖章（含题目、标准、条目哈希）"


def t_same_draft_same_points(root):
    """同一稿评出不同分 —— 拒收；同分才通过，并在 progress 上标 sameDraft。"""
    ws = new_ws(root)
    graded_01(root, ws)
    write(os.path.join(ws, "attempts", "02", "answer.md"), ANSWER_01)

    lower = payload(root, "02", 2,
                    [("hit", Q_ROTATE), ("miss", ""), ("partial", Q_CASE)],
                    marks=[], summary=SUMMARY_3)
    submit(ws, "02", lower)
    rc, out, err = run(root, "grade", SLUG, "02")
    check(rc == 1, "同稿不同分应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("same_draft" in gate_names(out, "ERROR"), "应报 same_draft 闸门：\n%s" % out)
    check(not os.path.isfile(os.path.join(ws, "attempts", "02", "result.json")),
          "拒收时不该写 result.json")

    same = payload(root, "02", 3,
                   [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)],
                   marks=[], summary=SUMMARY_3)
    submit(ws, "02", same)
    rc, out, err = run(root, "grade", SLUG, "02")
    check(rc == 0, "同稿同分应通过，rc=%d\n%s%s" % (rc, out, err))
    lines = [ln for ln in read(os.path.join(ws, "progress.md")).split("\n")
             if ln.startswith("- ")]
    check(len(lines) == 2, "progress 应有两行，实际 %r" % lines)
    check("sameDraft" in lines[1], "同稿那一行应标 sameDraft，实际 %r" % lines[1])
    check("sameDraft" not in lines[0], "第一行不该标 sameDraft，实际 %r" % lines[0])
    check(load(os.path.join(ws, "attempts", "02", "result.json"))["sameDraft"] is True,
          "result.json 应记 sameDraft")
    return "同稿不同分 → 退出 1；同稿同分 → 通过并标 sameDraft"


def t_progress_append(root):
    """progress.md 只增不改；progress 打印走势；check 复核整份工作区 0 ERROR。"""
    ws = new_ws(root)
    graded_01(root, ws)
    first = read(os.path.join(ws, "progress.md"))
    first_line = [ln for ln in first.split("\n") if ln.startswith("- ")][0]
    check("3/5" in first_line, "第一行应记 3/5，实际 %r" % first_line)
    check("可预期回收" in first_line, "第一行应列出未命中条目，实际 %r" % first_line)

    write(os.path.join(ws, "attempts", "02", "answer.md"), ANSWER_02)
    body = payload(root, "02", 5,
                   [("hit", Q_ROTATE), ("hit", Q_RECYCLE), ("hit", Q_CASE)],
                   marks=[{"quote": Q_BOOKED, "level": "remark",
                           "note": "例子可信，可以再点一句它为什么能说明问题。"}],
                   summary=SUMMARY_5)
    submit(ws, "02", body)
    rc, out, err = run(root, "grade", SLUG, "02")
    check(rc == 0, "attempt 02 应通过，rc=%d\n%s%s" % (rc, out, err))

    lines = [ln for ln in read(os.path.join(ws, "progress.md")).split("\n")
             if ln.startswith("- ")]
    check(len(lines) == 2, "progress 应有两行，实际 %r" % lines)
    check(lines[0] == first_line, "第一行必须原样保留：%r ≠ %r" % (lines[0], first_line))
    check("5/5" in lines[1] and "未命中：无" in lines[1], "第二行应是 5/5 且无未命中，实际 %r" % lines[1])

    # 同一份结果重批一次：progress 不该多出一行重复记录
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 0, "重批 01 应仍然通过，rc=%d\n%s%s" % (rc, out, err))
    again = [ln for ln in read(os.path.join(ws, "progress.md")).split("\n") if ln.startswith("- ")]
    check(again == lines, "重批同一份结果不该改动 progress：%r ≠ %r" % (again, lines))

    rc, out, err = run(root, "progress", SLUG)
    check(rc == 0, "progress 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    check(first_line in out, "progress 应把 progress.md 原样打出来：\n%s" % out)
    check("走势：" in out, "progress 应给一句走势：\n%s" % out)
    check("2 稿" in out, "走势应按作答哈希变化计稿数：\n%s" % out)

    rc, out, err = run(root, "check", SLUG)
    check(rc == 0, "check 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    check("0 ERROR" in out, "check 应报 0 ERROR：\n%s" % out)
    return "两次通过 → progress 两行且首行不变；progress 给走势；check 0 ERROR"


def t_lower_points_warn(root):
    """分数比上一稿低只提示核对，不拒收。"""
    ws = new_ws(root)
    graded_01(root, ws)
    write(os.path.join(ws, "attempts", "02", "answer.md"), ANSWER_02)
    body = payload(root, "02", 2,
                   [("hit", Q_ROTATE), ("miss", ""), ("partial", Q_CASE)],
                   marks=[], summary=SUMMARY_5)
    submit(ws, "02", body)
    rc, out, err = run(root, "grade", SLUG, "02")
    check(rc == 0, "分数变低应只是 WARN，rc=%d\n%s%s" % (rc, out, err))
    check("monotonic" in gate_names(out, "WARN"), "应报 monotonic 提示：\n%s" % out)
    check(os.path.isfile(os.path.join(ws, "attempts", "02", "result.json")),
          "WARN 不该挡住写 result.json")
    return "02 比 01 低分 → WARN 退出 0，照常出判题卡"


def t_gate_hash(root):
    """context_hash 对不上就是没跑 context 或改过材料 —— 拒收。"""
    ws = new_ws(root)
    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_01)
    pass_baselines(root, ws)
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)])
    body["context_hash"] = "0" * 64
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "哈希对不上应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("context_hash" in gate_names(out, "ERROR"), "应报 context_hash 闸门：\n%s" % out)

    # 改了作答再用旧哈希，同样拦下
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)])
    submit(ws, "01", body)
    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_02)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "改过作答后旧哈希应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("context_hash" in gate_names(out, "ERROR"), "应报 context_hash 闸门：\n%s" % out)
    return "伪造哈希 / 改作答后用旧哈希 → 都退出 1"


def t_gate_unknown_key(root):
    """顶层键白名单：多一个键就拒收，别拿别的字段名混进来。"""
    ws = new_ws(root)
    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_01)
    pass_baselines(root, ws)
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)])
    body["extraKey"] = {"a": 1}
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "多余顶层键应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("payload_keys" in gate_names(out, "ERROR"), "应报 payload_keys 闸门：\n%s" % out)
    check("extraKey" in out, "应把多余的键名列出来：\n%s" % out)

    # 条目里多一个键同样拒收
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)])
    body.pop("extraKey", None)
    body["criteria"][0]["extraKey"] = 2
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "条目多余键应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("criteria_keys" in gate_names(out, "ERROR"), "应报 criteria_keys 闸门：\n%s" % out)
    return "顶层 / 条目多余键 → 退出 1 并列出键名"


def t_gate_consistency(root):
    """分数必须与条目判定算得出来，且不超过满分。"""
    ws = new_ws(root)
    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_01)
    pass_baselines(root, ws)

    body = payload(root, "01", 5, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)])
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "分数与条目对不上应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("points_sum" in gate_names(out, "ERROR"), "应报 points_sum 闸门：\n%s" % out)

    body = payload(root, "01", 9, [("hit", Q_ROTATE), ("hit", Q_RECYCLE), ("hit", Q_CASE)])
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "超过满分应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("points_range" in gate_names(out, "ERROR"), "应报 points_range 闸门：\n%s" % out)

    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)])
    body["criteria"] = body["criteria"][:2]
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "条目数对不上应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("criteria_table" in gate_names(out, "ERROR"), "应报 criteria_table 闸门：\n%s" % out)

    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("blank", ""), ("hit", Q_CASE)])
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "判定值不在白名单应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("verdict_value" in gate_names(out, "ERROR"), "应报 verdict_value 闸门：\n%s" % out)
    return "分数与条目不一致 / 超满分 / 条目缺项 / 判定越界 → 都退出 1"


def t_gate_evidence(root):
    """命中要有原文支撑：引文锚不到就降为未命中，分数因此变化则整份退回。"""
    ws = new_ws(root)
    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_01)
    pass_baselines(root, ws)

    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_ABSENT)])
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "引文锚不到应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("evidence_unanchored" in gate_names(out, "WARN"),
          "锚不到的条目应被降为未命中：\n%s" % out)
    check("evidence_points" in gate_names(out, "ERROR"),
          "降级改了分数就该整份退回：\n%s" % out)

    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", "")])
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "命中却不给引文应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("evidence" in gate_names(out, "ERROR"), "应报 evidence 闸门：\n%s" % out)
    return "引文锚不到 / 命中无引文 → 降为未命中并退回整份"


def t_gate_cap(root):
    """批注条数上限：超过 max_notes 就拒收。"""
    src = os.path.join(root, "criteria-in.json")
    tight = dict(CRITERIA_IN)
    tight["max_notes"] = 2
    ws = new_ws(root, criteria=False)
    write_json(src, tight)
    rc, out, err = run(root, "criteria", "set", SLUG, "--from", src)
    check(rc == 0, "criteria set 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    check(load(os.path.join(ws, "criteria.json"))["max_notes"] == 2, "max_notes 应写进 criteria.json")

    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_01)
    pass_baselines(root, ws)
    marks = [{"quote": q, "level": "minor", "note": "第 %d 条批语，说明这里可以怎么改。" % i}
             for i, q in enumerate((Q_OCCUPY, Q_CASE, Q_QUEUE), 1)]
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)], marks=marks)
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "批注超上限应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("notes_cap" in gate_names(out, "ERROR"), "应报 notes_cap 闸门：\n%s" % out)

    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)], marks=marks[:2])
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 0, "两条批注应通过，rc=%d\n%s%s" % (rc, out, err))

    # 两条批语一模一样也拒收
    dup = [dict(marks[0]), dict(marks[1])]
    dup[1]["note"] = dup[0]["note"]
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)], marks=dup)
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "重复批语应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("note_dup" in gate_names(out, "ERROR"), "应报 note_dup 闸门：\n%s" % out)

    # 空心闸：引文都极短、批语和作答一个三字片段都不重合 —— 只提示，不拦
    hollow = [{"quote": "长期占着", "level": "minor", "note": "论据不足需补强"},
              {"quote": "画册", "level": "remark", "note": "此段落宜精简合并"}]
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)], marks=hollow)
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 0, "空心闸只提示不拦，rc=%d\n%s%s" % (rc, out, err))
    check("hollow" in gate_names(out, "WARN"), "应报 hollow 提示：\n%s" % out)
    return "批注超上限 / 批语重复 → 退出 1；套话式批注 → WARN 不拦"


def t_gate_ratio(root):
    """锚定率不够说明多半在凭印象写引文 —— 退回重批。"""
    ws = new_ws(root)
    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_01)
    pass_baselines(root, ws)
    marks = [{"quote": Q_OCCUPY, "level": "minor", "note": "这一层可以再往前推一句。"},
             {"quote": "凭印象写下的第一句引文", "level": "minor", "note": "这条引文并不在作答里。"},
             {"quote": "凭印象写下的第二句引文", "level": "remark", "note": "这条引文同样锚不到原文。"}]
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)], marks=marks)
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "锚定率不够应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("anchored_ratio" in gate_names(out, "ERROR"), "应报 anchored_ratio 闸门：\n%s" % out)
    check("凭印象写下的第一句引文" in out, "应列出锚不到的引文：\n%s" % out)

    # 没有批注时不套锚定率（空作答的基线就是这种情况）
    body = payload(root, "01", 3, [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)], marks=[])
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 0, "没有批注时不该被锚定率挡住，rc=%d\n%s%s" % (rc, out, err))
    return "锚定率 1/3 → 退出 1 并列出未锚定引文；无批注时不套此闸"


def t_gate_summary(root):
    """总评长度闸：太短太长都退回；只查长度，不查语义。"""
    ws = new_ws(root)
    write(os.path.join(ws, "attempts", "01", "answer.md"), ANSWER_01)
    pass_baselines(root, ws)
    verdicts = [("hit", Q_ROTATE), ("miss", ""), ("hit", Q_CASE)]

    body = payload(root, "01", 3, verdicts, summary="写得还行，下次注意。")
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "总评过短应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("summary_length" in gate_names(out, "ERROR"), "应报 summary_length 闸门：\n%s" % out)

    body = payload(root, "01", 3, verdicts, summary="这段话来回说同一件事。" * 30)
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "总评过长应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("summary_length" in gate_names(out, "ERROR"), "应报 summary_length 闸门：\n%s" % out)

    body = payload(root, "01", 3, verdicts,
                   summary=SUMMARY_3.replace("下一步先改哪一条", "第 1 题的下一步"))
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 1, "总评逐题复述应退出 1，rc=%d\n%s%s" % (rc, out, err))
    check("summary_recap" in gate_names(out, "ERROR"), "应报 summary_recap 闸门：\n%s" % out)

    # 长度够就放行，脚本不管里面写没写「下一步先改哪一条」
    body = payload(root, "01", 3, verdicts,
                   summary=SUMMARY_3.replace("下一步先改哪一条：", ""))
    submit(ws, "01", body)
    rc, out, err = run(root, "grade", SLUG, "01")
    check(rc == 0, "长度合格就该放行，rc=%d\n%s%s" % (rc, out, err))
    return "总评过短 / 过长 / 逐题复述 → 退出 1；长度合格即放行（不查语义）"


def t_check_examples(root):
    """examples/ 下每个练习包都要能离线复核 0 ERROR；目录还没建时跳过。"""
    base = os.path.join(SKILL_DIR, "examples", "practice")
    if not os.path.isdir(base):
        return "examples/practice/ 还没建，跳过（计通过）"
    dirs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
    check(dirs, "examples/practice/ 是空的")
    for name in dirs:
        rc, out, err = run(SKILL_DIR, "check", os.path.join("examples", "practice", name))
        check(rc == 0, "check %s 应退出 0，rc=%d\n%s%s" % (name, rc, out, err))
        check("0 ERROR" in out, "check %s 应报 0 ERROR：\n%s" % (name, out))
    return "examples/practice/ 下 %d 个练习包全部 0 ERROR" % len(dirs)


def t_export_no_text(root):
    """导出只带哈希、分数、条目判定、锚定率 —— 不带任何正文。"""
    ws = new_ws(root)
    graded_01(root, ws)
    rc, out, err = run(root, "export", SLUG)
    check(rc == 0, "export 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    data = json.loads(out)
    check(set(data) == {"slug", "max", "attempts", "baseline_stamp"},
          "导出顶层键应恰好是四个，实际 %r" % sorted(data))
    check(data["slug"] == SLUG and data["max"] == 5, "slug / max 应如实带出：%r" % data)
    check(len(data["attempts"]) == 1, "只批过一份，实际 %d 份" % len(data["attempts"]))
    row = data["attempts"][0]
    check(set(row) == {"id", "points", "verdicts", "anchored_ratio", "sameDraft", "context_hash"},
          "每份的键应恰好是六个，实际 %r" % sorted(row))
    check(row["id"] == "01" and row["points"] == 3, "分数应如实带出：%r" % row)
    check(row["verdicts"] == ["hit", "miss", "hit"], "条目判定应按条目表顺序：%r" % row["verdicts"])
    check(row["sameDraft"] is False, "第一份不该是同稿：%r" % row)
    check(isinstance(data["baseline_stamp"], dict), "应带上基线盖章：%r" % data["baseline_stamp"])

    blob = json.dumps(data, ensure_ascii=False)
    for text in (Q_ROTATE, Q_OCCUPY, SUMMARY_3[:12], ANSWER_01[:12], "轮流可借", "图书馆"):
        check(text not in blob, "导出里不该出现正文片段 %r：\n%s" % (text, blob))
    return "导出四个顶层键、每份六个字段，正文与条目名一概不带"


def t_banned_scan(root):
    """整个 Skill 目录过一遍禁用词静态闸。"""
    scanner = os.path.join(HERE, "banned_words.py")
    proc = subprocess.run([PY, scanner, SKILL_DIR],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    check(proc.returncode == 0, "禁用词扫描应退出 0，rc=%d\n%s%s" % (proc.returncode, out, err))
    check(out.strip() == "", "禁用词扫描应无输出，实际：\n%s" % out)

    engine = os.path.join(HERE, "anchor.py")
    proc = subprocess.run([PY, engine, "selftest"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    eout = proc.stdout.decode("utf-8", "replace")
    check(proc.returncode == 0, "引擎自测应退出 0，rc=%d\n%s" % (proc.returncode, eout))
    return "Skill 目录禁用词 0 命中；引擎自测同时全绿"


SELFTESTS = (
    t_doctor,
    t_baseline_files,
    t_grade_blocked_before_baseline,
    t_baseline_must_be_zero,
    t_same_draft_same_points,
    t_progress_append,
    t_lower_points_warn,
    t_gate_hash,
    t_gate_unknown_key,
    t_gate_consistency,
    t_gate_evidence,
    t_gate_cap,
    t_gate_ratio,
    t_gate_summary,
    t_check_examples,
    t_export_no_text,
    t_banned_scan,
)


def main():
    failed = []
    for fn in SELFTESTS:
        root = tempfile.mkdtemp(prefix="self-grader-selftest-")
        try:
            note = fn(root)
        except Failed as e:
            failed.append(fn.__name__)
            print("FAIL %s：%s" % (fn.__name__, e))
        except Exception as e:                      # 未实现 / 崩溃同样算失败
            failed.append(fn.__name__)
            print("FAIL %s：%s：%s" % (fn.__name__, type(e).__name__, e))
        else:
            print("pass %-32s %s" % (fn.__name__, note))
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
