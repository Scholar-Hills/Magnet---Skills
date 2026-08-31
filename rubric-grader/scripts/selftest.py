#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""grader.py 自测：临时目录里造工作区，把八条闸门的正反例各走一遍，最后打印 OK。

用法：python3 scripts/selftest.py
所有题批次都建在临时目录里，跑完删除；只有「examples 复核」这一条会读仓库里的
examples/，目录不存在时打印 SKIP 并计通过。作答、题干、评分标准全部是合成文本。

退出码：0 全绿 / 1 有用例未通过。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
GRADER = os.path.join(HERE, "grader.py")
PY = sys.executable

if HERE not in sys.path:
    sys.path.insert(0, HERE)
import anchor          # noqa: E402
import banned_words    # noqa: E402


# ---------------------------------------------------------------- 合成素材

QUESTION = "请解释什么是机会成本，并举一个日常生活中的例子。"

RUBRIC = ("一、说清机会成本的定义：被放弃的选项里价值最高的那一个。（2 分）\n\n"
          "二、举一个具体例子，并指出被放弃的是什么。（2 分）\n\n"
          "三、有一句总结，把定义与例子连起来。（1 分）\n\n"
          "满分 5 分。")

CRITERIA = [{"name": "定义准确", "points": 2},
            {"name": "例子具体", "points": 2},
            {"name": "结论呼应", "points": 1}]

PARA_DEF = "机会成本是指做出一个选择时，所放弃的其他选项里价值最高的那一个。"
PARA_CASE = ("比如周六下午我有两个安排，一个是去图书馆复习三小时，另一个是去打球，"
             "我选择了复习，那么打球带来的快乐就是这次选择的机会成本。")
PARA_END = "所以真正的代价不是花掉的钱，而是被放弃的那个最好的选项。"

ANSWER_A = "\n\n".join((PARA_DEF, PARA_CASE, PARA_END))
ORACLE_FULL = ANSWER_A
ORACLE_BROKEN = "\n\n".join((PARA_DEF, PARA_END))          # 删掉了例子那一条

QUOTE_DEF = "所放弃的其他选项里价值最高的那一个"
QUOTE_CASE = "去图书馆复习三小时"
QUOTE_END = "被放弃的那个最好的选项"
HIT_QUOTE = {"定义准确": QUOTE_DEF, "例子具体": QUOTE_CASE, "结论呼应": QUOTE_END}

# 只在作答里出现的独特句子，用来验证 export 不带正文
MARKER = "紫色犀牛在图书馆门口排队"

MARKS_A = [
    {"quote": "机会成本是指做出一个选择时", "level": "remark", "note": "定义的开头写得清楚，可以再点明为什么取价值最高的那个。"},
    {"quote": "比如周六下午我有两个安排", "level": "remark", "note": "例子的时间与场景都具体，读起来不含糊。"},
    {"quote": "那么打球带来的快乐就是这次选择的机会成本", "level": "minor", "note": "这里把被放弃的收益说出来了，判断到位。"},
    {"quote": "所以真正的代价不是花掉的钱", "level": "minor", "note": "结论呼应了定义，句子还可以再短一点。"},
]

SUMMARY_A = ("这份作答把机会成本的定义讲清楚了，也给出了一个能落到具体时间与场景的例子，"
             "被放弃的选项写得明白。结论一句把定义与例子连了起来，读下来有条理。"
             "如果能再补一句说明为什么被放弃的是价值最高的那一个，整体会更完整。")
SUMMARY_B = ("这份作答的定义部分抓住了要点，例子也算具体，但被放弃的那个选项交代得偏简单，"
             "读者需要自己补一步才明白。结论句和前面的定义连得上，方向没有跑偏。"
             "下一步先把例子里放弃了什么写实，再回头收紧结论。")
SUMMARY_ZERO = ("这份作答没有给出机会成本的定义，也没有举出任何可以判定的例子，"
                "更谈不上把两者连起来的结论，所以三条评分条目都没有可以支撑的原文。"
                "建议先照着评分标准把定义一句写出来，再补一个自己身上真实发生过的选择。")
SUMMARY_SHORT = "这份作答写得还行，条目基本命中，继续保持就好。"
SUMMARY_PER_ITEM = ("第 2 题的定义部分抓住了要点，例子也算具体，但被放弃的那个选项交代得偏简单，"
                    "读者需要自己补一步才明白。结论句和前面的定义连得上，方向没有跑偏。"
                    "下一步先把例子里放弃了什么写实，再回头收紧结论。")

BASE_ANSWERS = {
    "base-empty": "",
    "base-restate": "请解释什么是机会成本，并举一个日常生活中的例子。",
    "base-off-topic": ("昨天下午下了很大的雨，我把晾在阳台的衣服收了进来，"
                       "然后煮了一锅面，加了两个鸡蛋和一把青菜。\n\n"
                       "晚上看了一集纪录片，讲的是深海里的发光生物，拍得很好看。"),
}


def long_answer(extra_lines=10):
    """作答 A 后面接若干条互不相同、各自独立成段的句子，方便造大量不重叠的引文。"""
    tail = "\n\n".join("这是第%d条可以被引用的独立句子，内容各不相同。" % i
                       for i in range(1, extra_lines + 1))
    return ANSWER_A + "\n\n" + tail


def long_marks(anchored, unanchored):
    """前 anchored 条能锚定，后 unanchored 条一定锚不上（长度不足 16，不触发头尾锚定）。"""
    out = [{"quote": "这是第%d条可以被引用的独立句子" % i, "level": "minor",
            "note": "第%d条批语，指出这句可以再具体一点。" % i}
           for i in range(1, anchored + 1)]
    out += [{"quote": "查无此句%d" % (anchored + i), "level": "minor",
             "note": "第%d条落空批语，引文并不在作答里。" % (anchored + i)}
            for i in range(1, unanchored + 1)]
    return out


def crit(verdicts, quotes=None):
    """按条目表拼 criteria；hit / partial 默认配一条真的能锚定的引文。"""
    out = []
    for item, verdict in zip(CRITERIA, verdicts):
        name = item["name"]
        quote = (quotes or {}).get(name)
        if quote is None:
            quote = "" if verdict == "miss" else HIT_QUOTE[name]
        out.append({"name": name, "verdict": verdict, "quote": quote})
    return out


# ---------------------------------------------------------------- 工具

class Failed(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Failed(msg)


def run(*args):
    argv = [PY, GRADER] + [str(a) for a in args]
    r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       stdin=subprocess.DEVNULL)
    return (r.returncode,
            r.stdout.decode("utf-8", "replace"),
            r.stderr.decode("utf-8", "replace"))


def say(*args):
    """跑一条命令，返回 (退出码, stdout+stderr)。闸门原因走 stdout，用法错误走 stderr。"""
    rc, out, err = run(*args)
    return rc, out + err


def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_json(path, obj):
    write(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ctx(job, answer):
    rc, out, err = run("context", job, answer)
    check(rc == 0, "context 应退出 0，rc=%d\n%s%s" % (rc, out, err))
    try:
        return json.loads(out)
    except ValueError as e:
        raise Failed("context 的输出不是 JSON（%s）：%s" % (e, out[:400]))


def submit(job, student, body):
    write_json(os.path.join(job, "inbox", "grade-%s.json" % student), body)


def body_for(job, answer, *, points=4, summary=SUMMARY_A, verdicts=("hit", "hit", "miss"),
             quotes=None, marks=None):
    """按当前上下文拼一份合规形状的评分结果。"""
    return {"context_hash": ctx(job, answer)["context_hash"],
            "points": points,
            "summary": summary,
            "criteria": crit(verdicts, quotes),
            "marks": list(MARKS_A if marks is None else marks)}


def make_job(root, name, *, top=5, lang="zh", criteria=CRITERIA, oracle=True, answers=None):
    """建一个题批次：题干、评分标准、条目表、（可选）oracle 盖章、若干份作答。"""
    job = os.path.join(root, name)
    rc, out = say("init", job, "--max", top, "--lang", lang)
    check(rc == 0, "init 应退出 0，rc=%d\n%s" % (rc, out))
    write(os.path.join(job, "question.md"), QUESTION)
    write(os.path.join(job, "rubric.md"), RUBRIC)
    write_json(os.path.join(job, "inbox", "criteria.json"), criteria)
    rc, out = say("rubric", "set", job, "--from", os.path.join(job, "inbox", "criteria.json"))
    check(rc == 0, "rubric set 应退出 0，rc=%d\n%s" % (rc, out))
    for student, text in (answers or {"a01": ANSWER_A}).items():
        write(os.path.join(job, "answers", "%s.md" % student), text)
    if oracle:
        stamp_oracle(job)
    return job


def stamp_oracle(job, *, full_over=None, broken_over=None, missing=("例子具体",)):
    """写满分范例与残缺版，交两份评分结果，跑 oracle check；返回 (退出码, 输出)。"""
    write(os.path.join(job, "oracle", "full.md"), ORACLE_FULL)
    write(os.path.join(job, "oracle", "broken.md"), ORACLE_BROKEN)
    write_json(os.path.join(job, "oracle", "broken.json"), {"missing": list(missing)})
    full_path = os.path.join(job, "oracle", "full.md")
    broken_path = os.path.join(job, "oracle", "broken.md")
    full = body_for(job, full_path, points=5, verdicts=("hit", "hit", "hit"),
                    summary=SUMMARY_A, marks=MARKS_A[:2])
    broken = body_for(job, broken_path, points=3, verdicts=("hit", "miss", "hit"),
                      summary=SUMMARY_B, marks=[MARKS_A[0], MARKS_A[3]])
    full.update(full_over or {})
    broken.update(broken_over or {})
    submit(job, "oracle-full", full)
    submit(job, "oracle-broken", broken)
    return say("oracle", "check", job)


def pass_one(job, student, **over):
    """交一份合规结果并断言 grade 通过。"""
    submit(job, student, body_for(job, student, **over))
    rc, out = say("grade", job, student)
    check(rc == 0, "grade %s 应退出 0，rc=%d\n%s" % (student, rc, out))
    return out


# ---------------------------------------------------------------- 用例

def t_init_layout(root):
    """init 建出完整骨架，job.json 记下四个可调参数。"""
    job = os.path.join(root, "layout-01")
    rc, out = say("init", job, "--max", 5, "--lang", "zh")
    check(rc == 0, "init 应退出 0，rc=%d\n%s" % (rc, out))
    for name in ("job.json", "question.md", "rubric.md"):
        check(os.path.isfile(os.path.join(job, name)), "init 后应有文件 %s" % name)
    for name in ("oracle", "answers", "inbox", "results"):
        check(os.path.isdir(os.path.join(job, name)), "init 后应有目录 %s/" % name)
    meta = load(os.path.join(job, "job.json"))
    for key in ("max", "lang", "max_notes", "min_anchored"):
        check(key in meta, "job.json 应含 %s，实际键 %r" % (key, sorted(meta)))
    check(meta["max"] == 5 and meta["lang"] == "zh", "job.json 应记下 max 与 lang，实际 %r" % meta)
    check(meta["max_notes"] == 12 and meta["min_anchored"] == 0.7,
          "默认应是 12 条批注上限与 0.7 锚定率，实际 %r" % meta)

    other = os.path.join(root, "layout-02")
    rc, out = say("init", other, "--max", 10, "--lang", "en", "--max-notes", 8, "--min-anchored", 0.9)
    check(rc == 0, "带可选参数的 init 应退出 0，rc=%d\n%s" % (rc, out))
    meta = load(os.path.join(other, "job.json"))
    check(meta["lang"] == "en" and meta["max_notes"] == 8 and meta["min_anchored"] == 0.9,
          "可选参数应写进 job.json，实际 %r" % meta)
    rc, out = say("init", other, "--max", 5)
    check(rc == 2, "对已存在的题批次再 init 应退出 2，rc=%d\n%s" % (rc, out))


def t_rubric_set(root):
    """条目表写进 job.json；分值和与满分对不上就拒收。"""
    job = os.path.join(root, "rubric-01")
    say("init", job, "--max", 5)
    write(os.path.join(job, "question.md"), QUESTION)
    write(os.path.join(job, "rubric.md"), RUBRIC)
    table = os.path.join(job, "inbox", "criteria.json")

    write_json(table, [{"name": "定义", "points": 2}, {"name": "例子", "points": 2}, {"name": "结论", "points": 1}])
    rc, out = say("rubric", "set", job, "--from", table)
    check(rc == 0, "分值和等于满分时应退出 0，rc=%d\n%s" % (rc, out))
    meta = load(os.path.join(job, "job.json"))
    check([c["name"] for c in meta["criteria"]] == ["定义", "例子", "结论"],
          "条目名应逐条写进 job.json，实际 %r" % meta.get("criteria"))
    check([c["points"] for c in meta["criteria"]] == [2, 2, 1],
          "条目分值应逐条写进 job.json，实际 %r" % meta.get("criteria"))

    write_json(table, [{"name": "定义", "points": 2}, {"name": "例子", "points": 2}])
    rc, out = say("rubric", "set", job, "--from", table)
    check(rc == 1, "分值和不等于满分时应退出 1，rc=%d\n%s" % (rc, out))
    check("4" in out and "5" in out, "应说清算出来的和与满分，实际输出：\n%s" % out)
    check([c["name"] for c in load(os.path.join(job, "job.json"))["criteria"]] == ["定义", "例子", "结论"],
          "拒收时不应把旧条目表覆盖掉")

    write_json(table, [{"name": "定义"}, {"name": "例子"}])
    rc, out = say("rubric", "set", job, "--from", table)
    check(rc == 0, "不带分值的条目表应被接受，rc=%d\n%s" % (rc, out))

    write_json(table, [{"name": "定义", "points": 3}, {"name": "定义", "points": 2}])
    rc, out = say("rubric", "set", job, "--from", table)
    check(rc == 1, "条目重名应退出 1，rc=%d\n%s" % (rc, out))


def t_context_hash_changes(root):
    """作答改一个字、评分标准改一句，上下文哈希都必须跟着变。"""
    job = make_job(root, "context-01", oracle=False)
    answer = os.path.join(job, "answers", "a01.md")
    first = ctx(job, answer)
    for key in ("question_text", "rubric_text", "criteria", "answer_text", "max", "lang", "context_hash"):
        check(key in first, "上下文包应含 %s，实际键 %r" % (key, sorted(first)))
    check(first["answer_text"] == anchor.plain_text(ANSWER_A),
          "上下文包里的作答应是引擎抽出来的纯文本")
    check(ctx(job, answer)["context_hash"] == first["context_hash"], "同样的输入应算出同样的哈希")

    write(answer, ANSWER_A.replace("最好的选项", "最贵的选项"))
    changed = ctx(job, answer)["context_hash"]
    check(changed != first["context_hash"], "作答改一个词后哈希应变化")

    write(answer, ANSWER_A)
    check(ctx(job, answer)["context_hash"] == first["context_hash"], "作答改回去后哈希应复原")

    write(os.path.join(job, "rubric.md"), RUBRIC + "\n\n四、书写整洁。")
    check(ctx(job, answer)["context_hash"] != first["context_hash"], "评分标准改动后哈希应变化")


def t_oracle_required(root):
    """没有 oracle 盖章就不许批：grade 退出 2。"""
    job = make_job(root, "gate-oracle-01", oracle=False)
    submit(job, "a01", body_for(job, "a01"))
    rc, out = say("grade", job, "a01")
    check(rc == 2, "没盖章时 grade 应退出 2，rc=%d\n%s" % (rc, out))
    check("oracle" in out, "应提示先跑 oracle check，实际输出：\n%s" % out)
    check(not os.path.exists(os.path.join(job, "results", "a01.json")), "没盖章时不许写 results")


def t_oracle_full_must_be_full(root):
    """满分范例没拿满分就不算范例。"""
    job = make_job(root, "gate-oracle-02", oracle=False)
    rc, out = stamp_oracle(job, full_over={
        "points": 4,
        "criteria": crit(("hit", "hit", "miss")),
    })
    check(rc == 1, "满分范例只拿 4 分时 oracle check 应退出 1，rc=%d\n%s" % (rc, out))
    check("满分范例" in out, "原因里应出现「满分范例」，实际输出：\n%s" % out)
    check("结论呼应" in out, "应指名哪一条没命中，实际输出：\n%s" % out)
    check(not os.path.exists(os.path.join(job, ".stamps", "oracle.json")), "不通过就不该盖章")


def t_oracle_broken_must_miss(root):
    """残缺版里被删掉的条目不许判成命中。"""
    job = make_job(root, "gate-oracle-03", oracle=False)
    rc, out = stamp_oracle(job, broken_over={
        "points": 5,
        "criteria": crit(("hit", "hit", "hit"), {"例子具体": QUOTE_DEF}),
    })
    check(rc == 1, "残缺版把缺失条目判成 hit 时应退出 1，rc=%d\n%s" % (rc, out))
    check("残缺版" in out and "例子具体" in out, "应指名残缺版的哪一条，实际输出：\n%s" % out)
    check(not os.path.exists(os.path.join(job, ".stamps", "oracle.json")), "不通过就不该盖章")


def t_oracle_pass_stamps(root):
    """合格的 oracle 盖章：五份材料的哈希都记下来。"""
    job = make_job(root, "gate-oracle-04", oracle=False)
    rc, out = stamp_oracle(job)
    check(rc == 0, "合格的 oracle 应退出 0，rc=%d\n%s" % (rc, out))
    stamp = load(os.path.join(job, ".stamps", "oracle.json"))
    hashes = stamp.get("hashes", {})
    check(len(hashes) == 5, "盖章应含五个哈希（含 oracle/broken.json），实际 %r" % sorted(hashes))
    for key, value in hashes.items():
        check(isinstance(value, str) and len(value) == 64, "%s 的哈希应是 64 位十六进制，实际 %r" % (key, value))


def t_grade_hash_mismatch(root):
    """拿旧的上下文哈希来交结果 —— 说明作答或标准变过，拒收。"""
    job = make_job(root, "gate-hash-01")
    body = body_for(job, "a01")
    body["context_hash"] = "0" * 64
    submit(job, "a01", body)
    rc, out = say("grade", job, "a01")
    check(rc == 1, "哈希对不上应退出 1，rc=%d\n%s" % (rc, out))
    check("context_hash" in out or "上下文" in out, "应说清是上下文对不上，实际输出：\n%s" % out)
    check(os.path.isfile(os.path.join(job, "inbox", "grade-a01.json")), "拒收时 inbox 文件应保留供修改")


def t_grade_unknown_key(root):
    """契约外的顶层键一律拒收（拆开拼是为了本文件自己不被禁用词闸扫到）。"""
    job = make_job(root, "gate-keys-01")
    stray = "sc" + "ore"
    body = body_for(job, "a01")
    body[stray] = 4
    submit(job, "a01", body)
    rc, out = say("grade", job, "a01")
    check(rc == 1, "多一个顶层键应退出 1，rc=%d\n%s" % (rc, out))
    check(stray in out, "应指名是哪个键，实际输出：\n%s" % out)

    body = body_for(job, "a01")
    del body["summary"]
    submit(job, "a01", body)
    rc, out = say("grade", job, "a01")
    check(rc == 1, "少一个顶层键应退出 1，rc=%d\n%s" % (rc, out))
    check("summary" in out, "应指名缺的是哪个键，实际输出：\n%s" % out)


def t_grade_points_consistency(root):
    """条目带分值时，分数由条目判定算出来，不许自己填一个。"""
    job = make_job(root, "gate-points-01")
    submit(job, "a01", body_for(job, "a01", points=5, verdicts=("hit", "hit", "miss")))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "分数与条目判定对不上应退出 1，rc=%d\n%s" % (rc, out))
    check("4" in out, "应算出正确的分数 4 并写在原因里，实际输出：\n%s" % out)

    submit(job, "a01", body_for(job, "a01", points=9, verdicts=("hit", "hit", "hit")))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "超过满分应退出 1，rc=%d\n%s" % (rc, out))


def t_grade_evidence_unanchored(root):
    """判命中却引不出原文：该条降为 miss，分数因此变了就整份退回。"""
    job = make_job(root, "gate-evidence-01")
    submit(job, "a01", body_for(job, "a01", points=4, verdicts=("hit", "hit", "miss"),
                                quotes={"定义准确": "作答里根本没有这句话甲乙丙"}))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "引文锚不到且分数变化应退出 1，rc=%d\n%s" % (rc, out))
    check("定义准确" in out, "应指名是哪一条的引文锚不到，实际输出：\n%s" % out)
    check("2" in out, "应给出降级后应得的分数 2，实际输出：\n%s" % out)
    check(not os.path.exists(os.path.join(job, "results", "a01.json")), "拒收时不该写 results")


def t_grade_evidence_warn_half(root):
    """锚不到但分数没变：降为 miss、记 evidence_unanchored、给 WARN，但放行。

    结论呼应值 1 分，partial 取整是 0、miss 也是 0，所以降级不影响总分 ——
    §3.4 第 3 条说这种情况只记不拦，拦的是「因此分数变了」那半边。
    """
    job = make_job(root, "gate-evidence-02")
    submit(job, "a01", body_for(job, "a01", points=4, verdicts=("hit", "hit", "partial"),
                                quotes={"结论呼应": "作答里根本没有这句话甲乙丙"}))
    rc, out = say("grade", job, "a01")
    check(rc == 0, "锚不到但分数没变应放行，rc=%d\n%s" % (rc, out))
    check("WARN" in out and "结论呼应" in out, "应给出降级的提醒并指名条目，实际输出：\n%s" % out)

    record = load(os.path.join(job, "results", "a01.json"))
    end = [c for c in record["criteria"] if c["name"] == "结论呼应"][0]
    check(end["verdict"] == "miss", "锚不到的条目应降为 miss，实际 %r" % end["verdict"])
    check(end["evidence_unanchored"] is True, "应记 evidence_unanchored，实际 %r" % end)
    check(record["points"] == 4, "分数不该被脚本改动，实际 %r" % record["points"])
    check(any("锚不回" in c for c in record.get("cautions") or []),
          "提醒应记进落盘结果，实际 %r" % record.get("cautions"))


def t_grade_partial_halves(root):
    """partial 拿一半向下取整：2 分的条目给 1 分，1 分的条目给 0 分。"""
    job = make_job(root, "gate-partial-01")
    # 定义准确 hit 2 + 例子具体 partial 2//2=1 + 结论呼应 partial 1//2=0 = 3
    submit(job, "a01", body_for(job, "a01", points=3, verdicts=("hit", "partial", "partial")))
    rc, out = say("grade", job, "a01")
    check(rc == 0, "partial 按向下取整算出 3 分应通过，rc=%d\n%s" % (rc, out))
    record = load(os.path.join(job, "results", "a01.json"))
    check([c["verdict"] for c in record["criteria"]] == ["hit", "partial", "partial"],
          "partial 判定应原样落盘，实际 %r" % record["criteria"])

    submit(job, "a01", body_for(job, "a01", points=4, verdicts=("hit", "partial", "partial")))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "把 partial 当满分算（填 4）应退出 1，rc=%d\n%s" % (rc, out))
    check("3" in out, "应算出正确的 3 分并写在原因里，实际输出：\n%s" % out)


def t_grade_unscored_criteria(root):
    """条目表不带分值时：points 只受 0 <= points <= max 约束，但两条底线要守住。"""
    job = make_job(root, "gate-unscored-01",
                   criteria=[{"name": "定义准确"}, {"name": "例子具体"}, {"name": "结论呼应"}])
    submit(job, "a01", body_for(job, "a01", points=5, verdicts=("hit", "hit", "miss")))
    rc, out = say("grade", job, "a01")
    check(rc == 0, "不带分值时 hit/hit/miss 填 5 分也应放行，rc=%d\n%s" % (rc, out))
    check(load(os.path.join(job, "results", "a01.json"))["points"] == 5, "应原样记 5 分")

    submit(job, "a01", body_for(job, "a01", points=6, verdicts=("hit", "hit", "miss")))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "超过满分仍应退出 1，rc=%d\n%s" % (rc, out))
    check("5" in out, "应写清满分是 5，实际输出：\n%s" % out)

    # 底线一：hit 的引文锚不到就整份退回——算不出降级该扣多少，不能只 WARN 放行
    submit(job, "a01", body_for(job, "a01", points=5, verdicts=("hit", "hit", "miss"),
                                quotes={"定义准确": "作答里根本没有这句话甲乙丙"}))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "不带分值时引文锚不到应整份退回，rc=%d\n%s" % (rc, out))
    check("定义准确" in out, "应指名是哪一条的引文锚不到，实际输出：\n%s" % out)
    check("没标分值" in out, "应说清是不带分值才整份退回，实际输出：\n%s" % out)

    # 底线二：条目全 miss 却给了分——这个分数没有任何条目撑着
    submit(job, "a01", body_for(job, "a01", points=3, verdicts=("miss", "miss", "miss"),
                                summary=SUMMARY_ZERO))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "全 miss 却给 3 分应退出 1，rc=%d\n%s" % (rc, out))
    check("撑" in out, "应说清分数没有条目撑着，实际输出：\n%s" % out)

    submit(job, "a01", body_for(job, "a01", points=0, verdicts=("miss", "miss", "miss"),
                                summary=SUMMARY_ZERO))
    rc, out = say("grade", job, "a01")
    check(rc == 0, "全 miss 且 0 分应照常放行，rc=%d\n%s" % (rc, out))


def t_docx_extraction(root):
    """docx 抽取：制表符不吞邻字、表格文字按段落读出、文本框（Choice/Fallback）只读一次。"""
    import zipfile as zf
    import grader
    doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
        ' xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
        '<w:body>'
        '<w:p><w:r><w:t>甲</w:t></w:r><w:r><w:tab/><w:t>乙</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格里的句子</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '<w:p><w:r><w:t>正文段落有文本框。</w:t></w:r>'
        '<w:r><mc:AlternateContent>'
        '<mc:Choice Requires="wps"><w:drawing><wps:txbx><w:txbxContent>'
        '<w:p><w:r><w:t>文本框里的句子</w:t></w:r></w:p>'
        '</w:txbxContent></wps:txbx></w:drawing></mc:Choice>'
        '<mc:Fallback><w:pict><w:txbxContent>'
        '<w:p><w:r><w:t>文本框里的句子</w:t></w:r></w:p>'
        '</w:txbxContent></w:pict></mc:Fallback>'
        '</mc:AlternateContent></w:r></w:p>'
        '</w:body></w:document>'
    )
    path = os.path.join(root, "docx-01.docx")
    with zf.ZipFile(path, "w") as pack:
        pack.writestr("word/document.xml", doc)
    text = grader.docx_text(path)
    check("<" not in text and ">" not in text, "抽出的正文不应有 XML 标签碎片，实际 %r" % text)
    check("甲\t乙" in text, "制表符应保留且不吞邻字，实际 %r" % text)
    check(text.count("表格里的句子") == 1, "表格文字应恰好读一次，实际 %r" % text)
    check(text.count("文本框里的句子") == 1,
          "文本框文字应恰好读一次（Fallback 整棵跳过、内层 w:p 不再当顶层段落），实际 %r" % text)
    check(text.count("正文段落有文本框。") == 1, "外层段落文字应恰好一次，实际 %r" % text)


def t_grade_student_slug(root):
    """学号拼进 answers/ 与 results/ 的文件名：slug 口径之外（大写、点号、路径穿越）退出 2。"""
    job = make_job(root, "gate-slug-01")
    for bad in ("../a01", "A01", "a01.md", "学号一"):
        rc, out = say("grade", job, bad)
        check(rc == 2, "学号 %r 应退出 2，rc=%d\n%s" % (bad, rc, out))
        check("学号" in out, "应说明学号的口径，实际输出：\n%s" % out)


def t_grade_marks_cap(root):
    """批注条数超过上限就退回，别把一份作答写成长篇批语。"""
    job = make_job(root, "gate-cap-01", answers={"a01": long_answer(13)})
    submit(job, "a01", body_for(job, "a01", marks=long_marks(13, 0)))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "13 条批注（上限 12）应退出 1，rc=%d\n%s" % (rc, out))
    check("13" in out and "12" in out, "应写清实际条数与上限，实际输出：\n%s" % out)

    submit(job, "a01", body_for(job, "a01", marks=long_marks(12, 0)))
    rc, out = say("grade", job, "a01")
    check(rc == 0, "12 条批注应通过，rc=%d\n%s" % (rc, out))


def t_grade_anchor_ratio(root):
    """锚定率不够说明批注多半没对着原文说，退回重批。"""
    job = make_job(root, "gate-ratio-01", answers={"a01": long_answer(10)})
    submit(job, "a01", body_for(job, "a01", marks=long_marks(5, 5)))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "10 条只锚上 5 条应退出 1，rc=%d\n%s" % (rc, out))
    check("0.5" in out or "50" in out, "应报出实际锚定率，实际输出：\n%s" % out)
    check("查无此句6" in out, "应列出锚不上的引文，实际输出：\n%s" % out)

    submit(job, "a01", body_for(job, "a01", marks=long_marks(7, 3)))
    rc, out = say("grade", job, "a01")
    check(rc == 0, "10 条锚上 7 条（阈值 0.7）应通过，rc=%d\n%s" % (rc, out))
    record = load(os.path.join(job, "results", "a01.json"))
    check(abs(record["anchored_ratio"] - 0.7) < 1e-9, "落盘应记下锚定率，实际 %r" % record["anchored_ratio"])


def t_grade_summary_len(root):
    """总评太短是敷衍，逐题复述是把评分标准抄一遍。"""
    job = make_job(root, "gate-summary-01")
    submit(job, "a01", body_for(job, "a01", summary=SUMMARY_SHORT))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "总评过短应退出 1，rc=%d\n%s" % (rc, out))
    check("60" in out, "应写清字数下限，实际输出：\n%s" % out)

    submit(job, "a01", body_for(job, "a01", summary=SUMMARY_A * 3))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "总评过长应退出 1，rc=%d\n%s" % (rc, out))
    check("200" in out, "应写清字数上限，实际输出：\n%s" % out)

    submit(job, "a01", body_for(job, "a01", summary=SUMMARY_PER_ITEM))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "总评里逐题复述应退出 1，rc=%d\n%s" % (rc, out))
    check("第 2 题" in out, "应把逐题复述的那一处摘出来，实际输出：\n%s" % out)

    # 逐题复述的字符类与 self-grader 对齐：全角数字位数不限、〇 也认，普通句子不误报
    import grader as g
    check(g.PER_ITEM_RECAP.search("第１２３４题的定义写得含糊") is not None, "全角多位数字应命中")
    check(g.PER_ITEM_RECAP.search("第〇问没有作答") is not None, "〇 应命中")
    check(g.PER_ITEM_RECAP.search("这道题整体答得有条理") is None, "普通句子不应误报")

    # 计数口径按 job.json 的 lang 走：同一段 70 个英文词，en 合规、zh 因字数超上限不合规
    import grader
    english = make_job(root, "gate-summary-02", lang="en", oracle=False)
    words = " ".join("word%02d" % i for i in range(1, 71))
    check(grader.count_words(words, "en") == 70, "英文应按空白分词，实际 %d" % grader.count_words(words, "en"))
    check(grader.count_words(words, "zh") > 200, "中文应按字符数，同一段英文会超上限")
    check(grader.gate_summary(grader.Job(english), {"summary": words}) == [],
          "英文题批次里 70 个词的总评应合规，实际：%r"
          % grader.gate_summary(grader.Job(english), {"summary": words}))
    check(grader.gate_summary(grader.Job(job), {"summary": words}) != [],
          "中文题批次里同一段英文按字数应判超上限")


def t_grade_duplicate_notes(root):
    """两条批语一模一样：等于同一句话说两遍。"""
    job = make_job(root, "gate-dup-01")
    marks = [dict(m) for m in MARKS_A]
    marks[1]["note"] = marks[0]["note"]
    submit(job, "a01", body_for(job, "a01", marks=marks))
    rc, out = say("grade", job, "a01")
    check(rc == 1, "两条批语相同应退出 1，rc=%d\n%s" % (rc, out))
    check("重复" in out or "相同" in out, "应说清是批语重复，实际输出：\n%s" % out)


def t_grade_hollow_warn(root):
    """空心闸只提醒不拦：引文全是短词、批语又和作答毫无字面交集。"""
    job = make_job(root, "gate-hollow-01")
    hollow = [{"quote": "机会成本", "level": "minor", "note": "vague remark alpha"},
              {"quote": "打球", "level": "minor", "note": "vague remark beta"}]
    submit(job, "a01", body_for(job, "a01", marks=hollow))
    rc, out = say("grade", job, "a01")
    check(rc == 0, "空心批注只提醒不拦，应退出 0，rc=%d\n%s" % (rc, out))
    check("WARN" in out and "空心" in out, "应给出空心批注的提醒，实际输出：\n%s" % out)
    record = load(os.path.join(job, "results", "a01.json"))
    check(any("空心" in c for c in record.get("cautions") or []),
          "提醒应记进落盘结果，实际 %r" % record.get("cautions"))

    submit(job, "a01", body_for(job, "a01"))
    rc, out = say("grade", job, "a01")
    check(rc == 0 and "空心" not in out, "引文够长的正常一份不该被提醒，rc=%d\n%s" % (rc, out))


def t_grade_success_writes(root):
    """合格的一份：落盘 JSON 记着每条批注锚没锚上，判题卡是自包含单页。"""
    job = make_job(root, "grade-ok-01")
    out = pass_one(job, "a01")
    check("a01" in out, "通过时应报出学号，实际输出：\n%s" % out)

    record = load(os.path.join(job, "results", "a01.json"))
    check(record["points"] == 4 and record["max"] == 5, "落盘应记下分数与满分，实际 %r" % record)
    check(len(record["marks"]) == len(MARKS_A), "落盘的批注条数应与提交一致，实际 %d" % len(record["marks"]))
    for m in record["marks"]:
        check("anchored" in m, "每条批注都应记 anchored，实际 %r" % sorted(m))
    check(all(m["anchored"] for m in record["marks"]), "这四条引文都取自原文，应全部锚上")
    check([c["verdict"] for c in record["criteria"]] == ["hit", "hit", "miss"],
          "落盘应记下条目判定，实际 %r" % record["criteria"])

    page = read(os.path.join(job, "results", "a01.html"))
    check("data-an" in page, "判题卡应带引擎钉的批注编号")
    check("http://" not in page and "https://" not in page, "判题卡不得外链")
    check(MARKER not in page, "本例的作答里没有这句独特文本")


def t_similarity_gate(root):
    """一份评语贴全班：第二份撞上就退回。"""
    job = make_job(root, "gate-similar-01",
                   answers={"a01": ANSWER_A, "a02": ANSWER_A + "\n\n补充一句：这个道理在选课时也一样用得上。"})
    pass_one(job, "a01")

    submit(job, "a02", body_for(job, "a02", summary=SUMMARY_A))
    rc, out = say("grade", job, "a02")
    check(rc == 1, "总评与前一份相同应退出 1，rc=%d\n%s" % (rc, out))
    check("a01" in out, "应指名和谁撞了，实际输出：\n%s" % out)

    submit(job, "a02", body_for(job, "a02", summary=SUMMARY_B, marks=MARKS_A))
    rc, out = say("grade", job, "a02")
    check(rc == 1, "批语集合几乎重合应退出 1，rc=%d\n%s" % (rc, out))
    check("a01" in out, "应指名和谁撞了，实际输出：\n%s" % out)

    fresh = [{"quote": m["quote"], "level": m["level"], "note": "另一份作答的第%d条批语，说法各不相同。" % i}
             for i, m in enumerate(MARKS_A, 1)]
    submit(job, "a02", body_for(job, "a02", summary=SUMMARY_B, marks=fresh))
    rc, out = say("grade", job, "a02")
    check(rc == 0, "换成各自的评语后应通过，rc=%d\n%s" % (rc, out))


def t_baselines_zero(root):
    """三份对抗作答只能是 0 分全 miss —— 模型得先证明自己不会白给分。"""
    job = make_job(root, "gate-base-01", answers=dict(BASE_ANSWERS, a01=ANSWER_A))
    for student in sorted(BASE_ANSWERS):
        submit(job, student, body_for(job, student, points=2, verdicts=("hit", "miss", "miss"),
                                      quotes={"定义准确": "机会成本"}, summary=SUMMARY_ZERO, marks=[]))
        rc, out = say("grade", job, student)
        check(rc == 1, "%s 给出 2 分应退出 1，rc=%d\n%s" % (student, rc, out))
        check("对抗" in out or "基线" in out, "%s 应说清这是对抗作答，实际输出：\n%s" % (student, out))
        check(not os.path.exists(os.path.join(job, "results", "%s.json" % student)),
              "%s 拒收时不该写 results" % student)

    for i, student in enumerate(sorted(BASE_ANSWERS)):
        submit(job, student, body_for(job, student, points=0, verdicts=("miss", "miss", "miss"),
                                      summary=SUMMARY_ZERO + "（第%d份）" % (i + 1), marks=[]))
        rc, out = say("grade", job, student)
        check(rc == 0, "%s 判 0 分全 miss 应通过，rc=%d\n%s" % (student, rc, out))
        record = load(os.path.join(job, "results", "%s.json" % student))
        check(record["points"] == 0, "%s 应记 0 分" % student)
        check(all(c["verdict"] == "miss" for c in record["criteria"]), "%s 应条目全 miss" % student)


def t_stale_after_rubric_edit(root):
    """评分标准改了，之前批的都算旧的：汇总拒绝出，复核报 stale。"""
    job = make_job(root, "stale-01")
    pass_one(job, "a01")
    rc, out = say("summary", job)
    check(rc == 0, "改动之前 summary 应退出 0，rc=%d\n%s" % (rc, out))
    check(os.path.isfile(os.path.join(job, "summary.md")), "summary 应写出 summary.md")
    check(os.path.isfile(os.path.join(job, "summary.html")), "summary 应写出 summary.html")
    rc, out = say("check", job)
    check(rc == 0, "改动之前 check 应 0 ERROR，rc=%d\n%s" % (rc, out))

    write(os.path.join(job, "rubric.md"), RUBRIC + "\n\n四、书写整洁，字迹清楚。")
    rc, out = say("summary", job)
    check(rc == 1, "评分标准改动后 summary 应退出 1，rc=%d\n%s" % (rc, out))
    check("a01" in out, "应列出哪几份结果已经过期，实际输出：\n%s" % out)

    rc, out = say("check", job)
    check(rc == 1, "评分标准改动后 check 应退出 1，rc=%d\n%s" % (rc, out))
    check("ERROR" in out, "check 应逐条报出问题，实际输出：\n%s" % out)
    check("stale" in out or "过期" in out or "作废" in out, "check 应报 stale，实际输出：\n%s" % out)

    rc, out = say("grade", job, "a01")
    check(rc == 2, "盖章作废后 grade 应退出 2，rc=%d\n%s" % (rc, out))


def t_check_anchor_tamper(root):
    """手改落盘的锚定结论骗不过复核：汇总与导出读的就是这两个字段。"""
    job = make_job(root, "tamper-01")
    pass_one(job, "a01")
    path = os.path.join(job, "results", "a01.json")
    clean = read(path)
    rc, out = say("check", job)
    check(rc == 0, "没动过的题批次应 0 ERROR，rc=%d\n%s" % (rc, out))

    record = json.loads(clean)
    record["anchored_ratio"] = 0.11
    write_json(path, record)
    rc, out = say("check", job)
    check(rc == 1, "改了 anchored_ratio 应退出 1，rc=%d\n%s" % (rc, out))
    check("anchored_ratio" in out, "应指名是 anchored_ratio 对不上，实际输出：\n%s" % out)
    check("0.11" in out and "1.0" in out, "应同时报出落盘值与重算值，实际输出：\n%s" % out)

    record = json.loads(clean)
    for mark in record["marks"]:
        mark["anchored"] = False
    write_json(path, record)
    rc, out = say("check", job)
    check(rc == 1, "把每条 anchored 改成 false 应退出 1，rc=%d\n%s" % (rc, out))
    check("anchored" in out, "应指名是 anchored 对不上，实际输出：\n%s" % out)

    write(path, clean)
    rc, out = say("check", job)
    check(rc == 0, "改回去之后应重新 0 ERROR，rc=%d\n%s" % (rc, out))


def t_stale_after_missing_list_edit(root):
    """改了残缺版「缺哪几条」等于换了一份 oracle：盖章必须跟着作废。"""
    job = make_job(root, "stale-02")
    pass_one(job, "a01")
    rc, out = say("check", job)
    check(rc == 0, "改动之前 check 应 0 ERROR，rc=%d\n%s" % (rc, out))

    write_json(os.path.join(job, "oracle", "broken.json"), {"missing": ["结论呼应"]})
    rc, out = say("check", job)
    check(rc == 1, "改了 broken.json 之后 check 应退出 1，rc=%d\n%s" % (rc, out))
    check("broken.json" in out, "应指名是 oracle/broken.json 改过，实际输出：\n%s" % out)
    check("作废" in out or "stale" in out, "应报盖章作废，实际输出：\n%s" % out)

    rc, out = say("grade", job, "a01")
    check(rc == 2, "盖章作废后 grade 应退出 2，rc=%d\n%s" % (rc, out))
    rc, out = say("summary", job)
    check(rc == 1, "盖章作废后 summary 应退出 1，rc=%d\n%s" % (rc, out))


def t_check_examples(root):
    """仓库里的示例题批次必须 0 ERROR（示例还没做出来时跳过）。"""
    base = os.path.join(SKILL_DIR, "examples")
    if not os.path.isdir(base):
        print("     SKIP：examples/ 还不存在（由示例任务交付），本条跳过")
        return
    jobs = []
    for here, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in (".stamps",))
        if "job.json" in files:
            jobs.append(here)
    check(jobs, "examples/ 里应至少有一个题批次（含 job.json）")
    for job in sorted(jobs):
        rc, out = say("check", job)
        check(rc == 0, "示例 %s 复核应 0 ERROR，rc=%d\n%s" % (os.path.basename(job), rc, out))


def t_export_no_text(root):
    """导出的是证据不是正文：作答、引文、评语一个字都不许带出来。"""
    answer = ANSWER_A + "\n\n" + MARKER + "，这件事让我想起选择总要放弃点什么。"
    job = make_job(root, "export-01", answers={"a01": answer})
    marks = [dict(m) for m in MARKS_A]
    marks[0] = {"quote": MARKER, "level": "remark", "note": "这句%s的比喻挺有意思，但和评分标准关系不大。" % MARKER}
    pass_one(job, "a01", summary=SUMMARY_A + MARKER + "。", marks=marks)

    out_path = os.path.join(root, "export-01.json")
    rc, out = say("export", job, "--out", out_path)
    check(rc == 0, "export 应退出 0，rc=%d\n%s" % (rc, out))
    raw = read(out_path)
    check(MARKER not in raw, "导出里不该出现作答原文的独特句子：%s" % MARKER)
    for piece in (PARA_DEF, PARA_CASE, PARA_END, QUOTE_DEF, SUMMARY_A[:20], MARKS_A[0]["note"]):
        check(piece not in raw, "导出里不该出现正文片段：%s" % piece[:20])

    pack = json.loads(raw)
    for key in ("job", "max", "criteria_names", "students", "oracle_stamp"):
        check(key in pack, "导出应含 %s，实际键 %r" % (key, sorted(pack)))
    check(pack["criteria_names"] == [c["name"] for c in CRITERIA],
          "导出应含条目名，实际 %r" % pack["criteria_names"])
    one = pack["students"][0]
    for key in ("id", "points", "verdicts", "anchored_ratio", "marks_count", "context_hash"):
        check(key in one, "每位学生应含 %s，实际键 %r" % (key, sorted(one)))
    check(one["id"] == "a01" and one["points"] == 4, "导出的分数应与结果一致，实际 %r" % one)
    check(one["marks_count"] == len(marks), "导出应只给批注条数，实际 %r" % one["marks_count"])
    check(len(pack["students"]) == 1, "只应导出通过的那一份，实际 %d 份" % len(pack["students"]))


def t_banned_scan(root):
    """整个 Skill 目录不许出现禁用词。"""
    hits = banned_words.scan_dir(SKILL_DIR)
    check(hits == [], "rubric-grader/ 不应含禁用词，实际：\n%s" % "\n".join(hits))


SELFTESTS = (
    t_init_layout,
    t_rubric_set,
    t_context_hash_changes,
    t_oracle_required,
    t_oracle_full_must_be_full,
    t_oracle_broken_must_miss,
    t_oracle_pass_stamps,
    t_grade_hash_mismatch,
    t_grade_unknown_key,
    t_grade_points_consistency,
    t_grade_evidence_unanchored,
    t_grade_evidence_warn_half,
    t_grade_partial_halves,
    t_grade_unscored_criteria,
    t_docx_extraction,
    t_grade_student_slug,
    t_grade_marks_cap,
    t_grade_anchor_ratio,
    t_grade_summary_len,
    t_grade_duplicate_notes,
    t_grade_hollow_warn,
    t_grade_success_writes,
    t_similarity_gate,
    t_baselines_zero,
    t_stale_after_rubric_edit,
    t_stale_after_missing_list_edit,
    t_check_anchor_tamper,
    t_check_examples,
    t_export_no_text,
    t_banned_scan,
)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    root = tempfile.mkdtemp(prefix="rubric-grader-selftest-")
    failed = []
    try:
        rc, out = say("doctor")
        if rc != 0:
            print("FAIL doctor：应退出 0，rc=%d\n%s" % (rc, out))
            failed.append("doctor")
        else:
            print("pass doctor")
        for fn in SELFTESTS:
            try:
                fn(root)
            except Failed as e:
                failed.append(fn.__name__)
                print("FAIL %s：%s" % (fn.__name__, e))
            except Exception as e:
                failed.append(fn.__name__)
                print("FAIL %s：%s：%s" % (fn.__name__, type(e).__name__, e))
            else:
                print("pass %s" % fn.__name__)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    total = len(SELFTESTS) + 1
    if failed:
        print("%d/%d 个用例未通过：%s" % (len(failed), total, "、".join(failed)))
        return 1
    print("OK（%d 个用例全部通过）" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
