#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lessonkit.py 自测：临时目录里造一节最小课，走完四步三锁，再跑一组对抗回归。

用法：python3 scripts/selftest.py
不依赖 examples/；所有课都建在临时目录，跑完删除。examples/ 存在时额外复核一遍。

覆盖 G1–G14：课纲卡/作业/阶段/页稿四步的正反例、三把锁、上游改动作废、
八个作弊课、五组消毒绕过、build 幂等、repalette 逐字节不变、deck 不含讲稿、
壳字符串、发布卫生静态闸。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "lessonkit.py")
SKILL_DIR = os.path.dirname(HERE)
PY = sys.executable


class Failed(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Failed(msg)


def run(*args, **kw):
    cwd = kw.pop("cwd", None)
    proc = subprocess.run([PY, KIT] + list(args), cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    return proc.returncode, proc.stdout, proc.stderr


def both(res):
    return (res[1] or "") + (res[2] or "")


def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def dump(path, obj):
    write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------- 最小课素材
#
# 题材是「水的三态与相变」，初中常识，合成内容，不含任何真实课纲或真题。

LESSON = {
    "title": "水的三态与相变",
    "minutes": 10,
    "goals": [
        "能说出固态、液态、气态三种状态在形状与体积上的差别",
        "能用熔化、汽化、液化解释身边的常见现象",
    ],
    "keyPoints": ["相变过程里温度与热量的关系"],
    "audience": "初中二年级",
    "materials": [],
    "route": "homework-first",
    "language": {"slides": "zh", "notes": "zh"},
}

QUESTIONS = [
    {"id": "q1", "kind": "choice",
     "prompt": "水从液态变成气态的相变叫做什么？",
     "choices": ["熔化", "汽化", "凝固", "液化"], "correct": [1], "targets": ["g1"]},
    {"id": "q2", "kind": "short",
     "prompt": "冰在熔化时不断吸收热量，温度却停着不动，请说明这里的道理。",
     "focus": ["熔化", "热量", "温度"], "targets": ["g2", "k1"]},
    {"id": "q3", "kind": "short",
     "prompt": "写一个液化现象，并说明水蒸气为什么在冷的物体表面变成水珠。",
     "focus": ["液化", "水蒸气"], "targets": ["g2"]},
    {"id": "q4", "kind": "extended",
     "prompt": "结合气压与沸点的关系，解释高山上煮饭不容易熟的原因。",
     "focus": ["气压", "沸点"], "targets": ["g2", "k1"]},
]

PHASE_A = "固液气三态的差别"
PHASE_B = "相变里的温度与热量"

PHASES = [
    {"title": PHASE_A,
     "summary": "从日常画面引出固态、液态、气态在形状与体积上的差别，为后面的相变铺路。",
     "goals": ["g1"], "minutes": 4},
    {"title": PHASE_B,
     "summary": "沿熔化与液化两条线索，讲清相变过程里温度停住而热量继续进出的道理。",
     "goals": ["g2"], "minutes": 6},
]

P1_HTML = """<h1>固态、液态、气态</h1>
<p>同一种物质在温度改变时会呈现三种状态。固态有确定的形状与体积；液态只有确定的体积，形状随容器改变；气态既没有确定形状，也没有确定体积。</p>
<ul>
<li>液态受热变成气态，这个相变叫做汽化。</li>
<li>气态遇冷变回液态，这个相变叫做液化。</li>
</ul>
"""

P1_NOTES = """先让学生回想三个熟悉的画面：冬天窗玻璃上的薄冰、杯子里晃动的水、烧水壶口冒出的白汽。让他们用自己的话说说这三样东西哪里不一样，再把话头引到形状与体积这两个词上面。
板书时把三种状态排成一行，中间空出箭头的位置，后面讲到相变时直接在箭头上写名称，省得重画一次。
提问顺序建议：先问形状，再问体积，最后才问「为什么同一种物质会有这么多副样子」。第三问不必要求答对，只要有人提到冷热，就顺势接到下一页。
班上若有学生提前喊出汽化或者液化，不要打断，请他把箭头方向指出来，再由全班判断对错。这一页控制在两分钟以内，不要展开分子层面的解释。
"""

P2_HTML = """<h2>熔化与液化里的热量</h2>
<p>冰在熔化时不断吸收热量，温度却停在零摄氏度不动；吸进去的热量都用来拆开冰的结构。</p>
<p>反过来，水蒸气碰到冷的物体表面会放出热量，重新聚成小水珠，这就是液化。</p>
<table><tr><th>相变</th><th>吸热还是放热</th></tr><tr><td>熔化</td><td>吸热</td></tr><tr><td>液化</td><td>放热</td></tr></table>
"""

P2_NOTES = """这一页是整节课的重心，安排三分钟，其中留一分钟给学生自己动笔。
先摆事实：把温度计插进冰水混合物里，读数长时间不动，可是酒精灯一直在烧。请学生解释这个矛盾，允许他们说错。
等有人提到「热量跑到哪里去了」，再补上第二句：热量被拿去拆结构，没有拿去升温。这句话要慢慢说两遍，写在黑板正中间。
表格从下往上读一遍，让学生自己补出凝固与汽化两行，答案不必当场公布，留到讲评作业时对照。
末尾提醒一句：吸热放热讲的是能量往哪边走，跟冷热的感觉不是一回事，考试里最容易混。
巡视时留意两种典型的写法：一种把「温度不变」写成「没有吸热」，一种把「吸热」写成「变热」。看到就当场用铅笔圈出来，不必写评语，讲评时再统一处理。
"""

P3_HTML = """<h2>气压怎样改变沸点</h2>
<p>液体表面的气压越低，分子越容易跑出来，沸点也就跟着降低。高山上气压不足，水不到一百摄氏度就翻滚起来了。</p>
<blockquote>沸点不是水身上固定的数字，它随气压一起变。</blockquote>
"""

P3_NOTES = """这一页拿来收尾，两分钟讲完，别再引入新名词。
先复述一句上一页的结论，再抛出真实情境：为什么在海拔很高的地方，米饭常常夹生。让学生先猜，猜完再给出解释，顺序不要颠倒。
可以顺手提一句高压锅，方向正好相反，压强升高、翻滚需要的温度也跟着抬高。这句只说一遍，不要展开原理，留给下一节。
最后把四道作业题的题号念一遍，指出第四题就是这一页的延伸，回家之前先想清楚压强与温度之间的那条线。
下课前留半分钟收本子，别在铃响之后补充新内容；实在没讲完的部分记在自己的备课本上，下一节开头补，不要挤在这一页。
"""


def base_pages():
    return [
        {"id": "p1", "phase": PHASE_A, "covers": ["q1"], "title": "三种状态",
         "html": P1_HTML, "notes": P1_NOTES},
        {"id": "p2", "phase": PHASE_B, "covers": ["q2", "q3"], "title": "熔化与液化",
         "html": P2_HTML, "notes": P2_NOTES},
        {"id": "p3", "phase": PHASE_B, "covers": ["q4"], "title": "气压与沸点",
         "html": P3_HTML, "notes": P3_NOTES},
    ]


def clone(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False))


def make(root, slug, lesson=None, questions=None, phases=None, pages=None,
         skip_questions=False, skip_phases=False, skip_pages=False):
    """把一整套产物写进 root/lessons/<slug>/，返回课目录。"""
    d = os.path.join(root, "lessons", slug)
    os.makedirs(os.path.join(d, "pages"), exist_ok=True)
    os.makedirs(os.path.join(d, "assets"), exist_ok=True)
    os.makedirs(os.path.join(d, "materials"), exist_ok=True)
    dump(os.path.join(d, "lesson.json"), lesson if lesson is not None else clone(LESSON))
    if not skip_questions:
        dump(os.path.join(d, "questions.json"),
             questions if questions is not None else clone(QUESTIONS))
    if not skip_phases:
        dump(os.path.join(d, "phases.json"), phases if phases is not None else clone(PHASES))
    if not skip_pages:
        pages = pages if pages is not None else base_pages()
        index = [{"id": p["id"], "phase": p["phase"], "covers": p["covers"],
                  "title": p.get("title", "")} for p in pages]
        dump(os.path.join(d, "pages", "index.json"), index)
        for p in pages:
            write(os.path.join(d, "pages", p["id"] + ".html"), p["html"])
            write(os.path.join(d, "pages", p["id"] + ".notes.md"), p["notes"])
    return d


def steps_ok(root, slug, upto="pages"):
    """按顺序跑到某一步，每步都必须退出 0。"""
    order = ["lesson", "questions", "phases", "pages"]
    for name in order[:order.index(upto) + 1]:
        res = run("check", slug, name, cwd=root)
        check(res[0] == 0, "check %s 应退出 0，实际 %d\n%s" % (name, res[0], both(res)))
    return True


def expect_fail(root, slug, args, needle, rc=1):
    res = run(*args, cwd=root)
    check(res[0] == rc, "%s 应退出 %d，实际 %d\n%s" % (" ".join(args), rc, res[0], both(res)))
    check(needle in both(res), "%s 的输出里应有「%s」\n%s" % (" ".join(args), needle, both(res)))
    return both(res)


# ---------------------------------------------------------------- 正例全流程

def t_positive(root):
    slug = "water-states"
    d = make(root, slug)
    res = run("check", slug, "lesson", cwd=root)
    check(res[0] == 0, "check lesson 应退出 0\n%s" % both(res))
    for name in ("questions", "phases", "pages"):
        res = run("check", slug, name, cwd=root)
        check(res[0] == 0, "check %s 应退出 0\n%s" % (name, both(res)))
        check(os.path.isfile(os.path.join(d, ".stamps", name + ".json")),
              ".stamps/%s.json 应被写出" % name)
    check("ERROR" not in read(os.path.join(d, ".stamps", "pages.json")),
          "盖章文件里不该有 ERROR 字样")

    res = run("build", slug, cwd=root)
    check(res[0] == 0, "build 应退出 0\n%s" % both(res))
    deck = read(os.path.join(d, "deck.html"))
    notes = read(os.path.join(d, "notes.html"))

    # G9 壳字符串
    for lit in ("width:1280px;height:720px",
                ".fit{width:100%;transform-origin:top left;}",
                "@page{size:13.333in 7.5in;margin:0;}"):
        check(lit in deck, "deck.html 里应有壳字符串「%s」" % lit)
    check(re.search(r":root\{--accent:#[0-9a-f]{6};\}", deck),
          "deck.html 里应有 :root{--accent:#xxxxxx;} 一行")
    check(deck.count("<script") == 1, "deck.html 里 <script 应恰好一次，实际 %d" % deck.count("<script"))
    check("<svg" not in deck, "deck.html 里不许有 <svg")
    check(deck.count("data-page-id") == 3, "deck.html 的 data-page-id 应等于成品页数 3，实际 %d"
          % deck.count("data-page-id"))
    check(deck.count('class="slide"') == 3, 'deck.html 的 class="slide" 应等于成品页数 3，实际 %d'
          % deck.count('class="slide"'))
    check("src=\"http" not in deck and "src='http" not in deck, "deck.html 不许有外链资源")
    for doc, tag in ((deck, "deck.html"), (notes, "notes.html")):
        check("url(http" not in doc and "url(//" not in doc, "%s 不许有 url() 外链" % tag)
    check(notes.count("<script") == 0, "notes.html 里不该有脚本")
    check("教师讲稿 · 不投屏" in notes, "notes.html 页首应写「教师讲稿 · 不投屏」")
    check("@page{size:13.333in 7.5in;margin:0;}" in notes, "notes.html 应带打印 CSS")

    # G9 deck 不含讲稿
    for text in (P1_NOTES, P2_NOTES, P3_NOTES):
        head = re.sub(r"\s+", "", text)[:40]
        check(head not in re.sub(r"\s+", "", deck), "deck.html 里出现了讲稿前 40 字：%s" % head)
        check(head in re.sub(r"\s+", "", notes), "notes.html 里应有讲稿前 40 字：%s" % head)

    # build 幂等
    first = read_bytes(os.path.join(d, "deck.html"))
    firstn = read_bytes(os.path.join(d, "notes.html"))
    res = run("build", slug, cwd=root)
    check(res[0] == 0, "第二次 build 应退出 0\n%s" % both(res))
    check(read_bytes(os.path.join(d, "deck.html")) == first, "build 两次 deck.html 应逐字节一致")
    check(read_bytes(os.path.join(d, "notes.html")) == firstn, "build 两次 notes.html 应逐字节一致")

    # G12 报告
    res = run("report", slug, cwd=root)
    check(res[0] == 0, "report 应退出 0\n%s" % both(res))
    md = read(os.path.join(d, "report.md"))
    rep = read(os.path.join(d, "report.html"))
    for needle in ("覆盖矩阵", "讲稿", PHASE_A, "q4", "p3"):
        check(needle in md, "report.md 里应有「%s」" % needle)
    check("http://" not in rep and "https://" not in rep, "report.html 应零外链")
    check("四步" in rep or "步骤" in rep, "report.html 应有四步状态条")
    check("q1" in rep and "p1" in rep, "report.html 应有覆盖矩阵格子")

    res = run("check", slug, "--all", cwd=root)
    check(res[0] == 0, "check --all 应退出 0\n%s" % both(res))
    return d


# ---------------------------------------------------------------- G11 换色

def t_repalette(root):
    slug = "palette-course"
    d = make(root, slug)
    steps_ok(root, slug)
    check(run("build", slug, cwd=root)[0] == 0, "build 应退出 0")
    old_deck = read(os.path.join(d, "deck.html")).split("\n")
    old_notes = read(os.path.join(d, "notes.html")).split("\n")
    pages_before = dict((n, read_bytes(os.path.join(d, "pages", n)))
                        for n in sorted(os.listdir(os.path.join(d, "pages"))))

    res = run("repalette", slug, "--palette", "amber", cwd=root)
    check(res[0] == 0, "repalette 应退出 0\n%s" % both(res))
    pages_after = dict((n, read_bytes(os.path.join(d, "pages", n)))
                       for n in sorted(os.listdir(os.path.join(d, "pages"))))
    check(pages_before == pages_after, "repalette 之后 pages/ 必须逐字节不变")

    new_deck = read(os.path.join(d, "deck.html")).split("\n")
    check(len(old_deck) == len(new_deck), "换色前后 deck.html 行数应一致")
    diff = [i for i in range(len(new_deck)) if old_deck[i] != new_deck[i]]
    check(len(diff) == 1, "换色前后 deck.html 只该差一行，实际差 %d 行：%s"
          % (len(diff), [new_deck[i] for i in diff[:4]]))
    check(new_deck[diff[0]].startswith(":root{--accent:"),
          "差的那一行应是 :root{--accent:...}，实际是 %r" % new_deck[diff[0]])
    new_notes = read(os.path.join(d, "notes.html")).split("\n")
    diffn = [i for i in range(len(new_notes)) if old_notes[i] != new_notes[i]]
    check(len(diffn) == 1 and new_notes[diffn[0]].startswith(":root{--accent:"),
          "notes.html 换色也只该差 :root{--accent:...} 一行，实际差 %d 行" % len(diffn))

    out = both(run("repalette", slug, "--palette", "no-such-key", cwd=root))
    check("WARN" in out, "未知配色应给 WARN\n%s" % out)
    check(read(os.path.join(d, "deck.html")).split("\n")[diff[0]] == old_deck[diff[0]],
          "未知配色应回落到默认 cyan")

    # 换色后 check --all 仍应通过（deck 盖章跟着更新）
    res = run("check", slug, "--all", cwd=root)
    check(res[0] == 0, "repalette 之后 check --all 应退出 0\n%s" % both(res))
    return "repalette：八色白名单、未知回落 cyan+WARN、pages 逐字节不变、deck/notes 只差 accent 一行"


# ---------------------------------------------------------------- G1 课纲卡

def t_g1(root):
    lesson = clone(LESSON)
    lesson["title"] = ""
    make(root, "g1-no-title", lesson=lesson, skip_questions=True, skip_phases=True, skip_pages=True)
    expect_fail(root, "g1-no-title", ("check", "g1-no-title", "lesson"), "title")

    lesson = clone(LESSON)
    lesson["goals"] = []
    lesson["keyPoints"] = []
    make(root, "g1-empty", lesson=lesson, skip_questions=True, skip_phases=True, skip_pages=True)
    expect_fail(root, "g1-empty", ("check", "g1-empty", "lesson"), "没有出题依据")

    lesson = clone(LESSON)
    lesson["route"] = "teacher-first"
    make(root, "g1-route", lesson=lesson, skip_questions=True, skip_phases=True, skip_pages=True)
    expect_fail(root, "g1-route", ("check", "g1-route", "lesson"), "route")

    lesson = clone(LESSON)
    lesson["minutes"] = 400
    make(root, "g1-minutes", lesson=lesson, skip_questions=True, skip_phases=True, skip_pages=True)
    res = run("check", "g1-minutes", "lesson", cwd=root)
    check(res[0] == 0 and "WARN" in both(res), "课时 400 分钟应只给 WARN\n%s" % both(res))

    lesson = clone(LESSON)
    lesson["minutes"] = 0
    make(root, "g1-zero", lesson=lesson, skip_questions=True, skip_phases=True, skip_pages=True)
    expect_fail(root, "g1-zero", ("check", "g1-zero", "lesson"), "minutes")

    lesson = clone(LESSON)
    lesson["materials"] = [{"name": "课文", "path": "materials/missing.txt"}]
    make(root, "g1-material", lesson=lesson, skip_questions=True, skip_phases=True, skip_pages=True)
    expect_fail(root, "g1-material", ("check", "g1-material", "lesson"), "materials")

    # slug 不许穿越目录
    res = run("init", "../escape", cwd=root)
    check(res[0] == 2, "越界 slug 应退出 2，实际 %d\n%s" % (res[0], both(res)))
    return "G1：标题空 / 目标与知识点同时空 / route 非法 / minutes 非正 / 材料文件缺失 全被判死；400 分钟只 WARN；slug 拦目录穿越"


# ---------------------------------------------------------------- G2 作业

def t_g2(root):
    qs = clone(QUESTIONS)[:2]
    make(root, "g2-few", questions=qs, skip_phases=True, skip_pages=True)
    steps_ok(root, "g2-few", "lesson")
    expect_fail(root, "g2-few", ("check", "g2-few", "questions"), "3")

    qs = clone(QUESTIONS)
    qs[1]["id"] = "q1"
    make(root, "g2-dupid", questions=qs, skip_phases=True, skip_pages=True)
    steps_ok(root, "g2-dupid", "lesson")
    expect_fail(root, "g2-dupid", ("check", "g2-dupid", "questions"), "id")

    qs = clone(QUESTIONS)
    qs[0]["kind"] = "coding"
    make(root, "g2-kind", questions=qs, skip_phases=True, skip_pages=True)
    steps_ok(root, "g2-kind", "lesson")
    expect_fail(root, "g2-kind", ("check", "g2-kind", "questions"), "kind")

    qs = clone(QUESTIONS)
    qs[0]["correct"] = [0, 1, 2, 3]
    make(root, "g2-correct", questions=qs, skip_phases=True, skip_pages=True)
    steps_ok(root, "g2-correct", "lesson")
    expect_fail(root, "g2-correct", ("check", "g2-correct", "questions"), "correct")

    qs = clone(QUESTIONS)
    qs[0]["prompt"] = "水？"
    make(root, "g2-short", questions=qs, skip_phases=True, skip_pages=True)
    steps_ok(root, "g2-short", "lesson")
    expect_fail(root, "g2-short", ("check", "g2-short", "questions"), "prompt")

    qs = clone(QUESTIONS)
    qs[0]["targets"] = ["g9"]
    make(root, "g2-targets", questions=qs, skip_phases=True, skip_pages=True)
    steps_ok(root, "g2-targets", "lesson")
    expect_fail(root, "g2-targets", ("check", "g2-targets", "questions"), "g9")

    qs = clone(QUESTIONS)
    qs[3]["prompt"] = qs[2]["prompt"]
    qs[3]["kind"] = "short"
    make(root, "g2-dup", questions=qs, skip_phases=True, skip_pages=True)
    steps_ok(root, "g2-dup", "lesson")
    res = run("check", "g2-dup", "questions", cwd=root)
    check("WARN" in both(res) and "重复" in both(res), "两题几乎同文应给 WARN 重复题\n%s" % both(res))
    return "G2：题数不足 / id 重复 / kind 非法 / correct 越界 / prompt 过短 / targets 悬空 全被判死；近似重复题给 WARN"


# ---------------------------------------------------------------- G3 三把锁

def t_locks(root):
    # 锁一：没出作业不许规划阶段
    make(root, "lock-one", skip_questions=True, skip_pages=True)
    steps_ok(root, "lock-one", "lesson")
    expect_fail(root, "lock-one", ("check", "lock-one", "phases"), "先出作业，再规划阶段", rc=2)

    # 锁二：没规划阶段不许写页
    make(root, "lock-two", skip_phases=True)
    steps_ok(root, "lock-two", "questions")
    expect_fail(root, "lock-two", ("check", "lock-two", "pages"), "先规划阶段", rc=2)

    # 锁三：没有一页过验收不许 build
    d = make(root, "lock-three")
    steps_ok(root, "lock-three", "phases")
    expect_fail(root, "lock-three", ("build", "lock-three"), "不许出成品", rc=2)
    # 撞在锁上时 report 照样画得出四步与三把锁，不许直接退 2
    res = run("report", "lock-three", cwd=root)
    check(res[0] == 0, "撞锁时 report 也该出得来，实际 %d\n%s" % (res[0], both(res)))
    md = read(os.path.join(d, "report.md"))
    check("锁住" in md and "不许出成品" in md, "报告里应写出锁住的那把锁与 lockReason\n%s" % md[:600])

    # content-first 逃生口：出题后置，但 build 前必须补上
    lesson = clone(LESSON)
    lesson["route"] = "content-first"
    make(root, "route-cf", lesson=lesson, skip_questions=True)
    steps_ok(root, "route-cf", "lesson")
    res = run("check", "route-cf", "phases", cwd=root)
    check(res[0] == 0, "content-first 下 check phases 应放行\n%s" % both(res))
    res = run("check", "route-cf", "pages", cwd=root)
    check(res[0] == 0, "content-first 下 check pages 应放行\n%s" % both(res))
    check("未先出作业" in both(res), "content-first 应标注「未先出作业」\n%s" % both(res))
    expect_fail(root, "route-cf", ("build", "route-cf"), "只能后置", rc=2)
    d = os.path.join(root, "lessons", "route-cf")
    dump(os.path.join(d, "questions.json"), clone(QUESTIONS))
    # 作业刚落盘还没验收：content-first 的主链是 课纲卡→阶段→页稿，
    # 出题挂在旁边，所以这时 check phases 不该突然被作业挡住
    res = run("check", "route-cf", "phases", cwd=root)
    check(res[0] == 0, "content-first 下作业还没验收，check phases 不该被挡住\n%s" % both(res))
    check(run("check", "route-cf", "questions", cwd=root)[0] == 0, "补交作业后 check questions 应通过")
    res = run("check", "route-cf", "pages", cwd=root)
    check(res[0] == 0, "补交作业后 check pages 应通过\n%s" % both(res))
    res = run("build", "route-cf", cwd=root)
    check(res[0] == 0, "补交作业后 build 应通过\n%s" % both(res))
    res = run("report", "route-cf", cwd=root)
    check("未先出作业" in read(os.path.join(d, "report.md")), "content-first 的报告顶部应标「未先出作业」")
    res = run("check", "route-cf", "--all", cwd=root)
    check(res[0] == 0, "content-first 补齐之后 check --all 应退出 0\n%s" % both(res))
    check(os.path.isfile(os.path.join(d, ".stamps", "questions.json")),
          "content-first 的 check --all 也要把后置的作业一起盖章")
    # 出成品之后再改作业：覆盖结论作废，成品要重出
    qs = clone(QUESTIONS)
    qs[0]["prompt"] = "水从液态变成气态的那个相变，究竟叫做什么名字？"
    dump(os.path.join(d, "questions.json"), qs)
    expect_fail(root, "route-cf", ("check", "route-cf", "--all"), "重新出成品")
    return "三把锁：没作业不许规划 / 没阶段不许写页 / 没过验收不许出成品；content-first 只把出题后置，build 前仍强制补上"


# ---------------------------------------------------------------- G4 阶段

def t_g4(root):
    ph = clone(PHASES)[:1]
    ph[0]["goals"] = ["g1", "g2"]
    ph[0]["minutes"] = 10
    make(root, "g4-one", phases=ph, skip_pages=True)
    steps_ok(root, "g4-one", "questions")
    res = run("check", "g4-one", "phases", cwd=root)
    check(res[0] == 0 and "WARN" in both(res), "只有一个阶段应只给 WARN\n%s" % both(res))

    ph = clone(PHASES)
    ph[0]["title"] = ph[1]["title"]
    make(root, "g4-same", phases=ph, skip_pages=True)
    steps_ok(root, "g4-same", "questions")
    expect_fail(root, "g4-same", ("check", "g4-same", "phases"), "两两不同")

    ph = clone(PHASES)
    ph[0]["summary"] = "很短"
    make(root, "g4-summary", phases=ph, skip_pages=True)
    steps_ok(root, "g4-summary", "questions")
    expect_fail(root, "g4-summary", ("check", "g4-summary", "phases"), "summary")

    ph = clone(PHASES)
    ph[1]["goals"] = ["g1"]
    make(root, "g4-orphan", phases=ph, skip_pages=True)
    steps_ok(root, "g4-orphan", "questions")
    expect_fail(root, "g4-orphan", ("check", "g4-orphan", "phases"), "目标无阶段承接")

    ph = clone(PHASES)
    ph[0]["minutes"] = 40
    make(root, "g4-minutes", phases=ph, skip_pages=True)
    steps_ok(root, "g4-minutes", "questions")
    res = run("check", "g4-minutes", "phases", cwd=root)
    check(res[0] == 0 and "WARN" in both(res), "阶段时长之和偏差过大应只 WARN\n%s" % both(res))

    ph = clone(PHASES)
    ph[0]["summary"] = "这一段完全不提本阶段目标里的任何名词，只讲天气与路况，凑够二十个字。"
    make(root, "g4-nolink", phases=ph, skip_pages=True)
    steps_ok(root, "g4-nolink", "questions")
    res = run("check", "g4-nolink", "phases", cwd=root)
    check("WARN" in both(res), "阶段 summary 与目标零重合应给 WARN\n%s" % both(res))

    ph = clone(PHASES)
    for i in range(9):
        ph.append({"title": "补充阶段%s" % "甲乙丙丁戊己庚辛壬"[i],
                   "summary": "这是为了把阶段数量顶到上限而补的一段说明文字，长度足够二十个字。",
                   "goals": ["g1"], "minutes": 1})
    make(root, "g4-many", phases=ph, skip_pages=True)
    steps_ok(root, "g4-many", "questions")
    expect_fail(root, "g4-many", ("check", "g4-many", "phases"), "阶段")
    return "G4：单阶段 WARN / 标题重名 / summary 过短 / 目标无阶段承接 / 阶段过多 / 时长偏差 WARN / summary 与目标零重合 WARN"


# ---------------------------------------------------------------- G4 编号前缀

NUMBERED = ["第一阶段：三态的差别", "第 2 阶段 温度与热量", "Phase 1 — Water states",
            "1. 引入与观察", "1、引入与观察", "一、引入与观察", "Step 1 引入与观察",
            "（1）引入与观察", "Part 2 热量"]


def t_numbered(root):
    for i, title in enumerate(NUMBERED):
        ph = clone(PHASES)
        ph[0]["title"] = title
        slug = "num-%d" % i
        make(root, slug, phases=ph, skip_pages=True)
        steps_ok(root, slug, "questions")
        expect_fail(root, slug, ("check", slug, "phases"), "编号前缀")
    for i, title in enumerate(("三态的差别", "水的相变", "从冰到水蒸气")):
        ph = clone(PHASES)
        ph[0]["title"] = title
        slug = "num-ok-%d" % i
        make(root, slug, phases=ph, skip_pages=True)
        steps_ok(root, slug, "questions")
        res = run("check", slug, "phases", cwd=root)
        check(res[0] == 0, "正常阶段名 %r 不该被编号前缀正则误伤\n%s" % (title, both(res)))
    return "G4 编号前缀：%d 个编号写法全被拦，3 个正常阶段名不误伤" % len(NUMBERED)


# ---------------------------------------------------------------- G5 页稿准入

BYPASS = [
    ("bp-onerror", '<img src=x/onerror=alert(1)>', "on* 事件属性"),
    ("bp-script", '<script src=//x>', "<script>"),
    ("bp-jsurl", '<img src="jAvAsCrIpT:alert(1)">', "危险 URL 协议"),
    ("bp-tabjs", '<img src="java\tscript:alert(1)">', "危险 URL 协议"),
    ("bp-datahtml", '<img src="data:text/html;base64,PHA+eDwvcD4=">', "危险 URL 协议"),
]


def t_g5(root):
    for slug, evil, needle in BYPASS:
        pages = base_pages()
        pages[0]["html"] = P1_HTML + evil
        make(root, slug, pages=pages)
        steps_ok(root, slug, "phases")
        out = expect_fail(root, slug, ("check", slug, "pages"), needle)
        check("p1" in out, "%s 的报错应指到页 p1\n%s" % (slug, out))

    # 外链图
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<img src="http://example.invalid/a.png">'
    make(root, "g5-remote", pages=pages)
    steps_ok(root, "g5-remote", "phases")
    expect_fail(root, "g5-remote", ("check", "g5-remote", "pages"), "assets/")

    # assets/ 里的文件必须真的存在
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<img src="assets/nope.png">'
    make(root, "g5-noasset", pages=pages)
    steps_ok(root, "g5-noasset", "phases")
    expect_fail(root, "g5-noasset", ("check", "g5-noasset", "pages"), "assets/nope.png")

    # 白名单外的标签
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<iframe src="assets/a.html"></iframe>'
    make(root, "g5-tag", pages=pages)
    steps_ok(root, "g5-tag", "phases")
    expect_fail(root, "g5-tag", ("check", "g5-tag", "pages"), "iframe")

    # style 的 url() 外链：走的不是 src=，一样不许出去
    for i, evil in enumerate(("url(https://cdn.example.invalid/track.png)",
                              "url('http://example.invalid/a.png')",
                              "url(//example.invalid/a.png)")):
        pages = base_pages()
        pages[0]["html"] = P1_HTML + '<p style="background:%s">底纹</p>' % evil
        slug = "g5-cssurl-%d" % i
        make(root, slug, pages=pages)
        steps_ok(root, slug, "phases")
        out = expect_fail(root, slug, ("check", slug, "pages"), "url()")
        check("p1" in out, "%s 的报错应指到页 p1\n%s" % (slug, out))

    # style 的 url() 指到不存在的本地图
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<p style="background:url(assets/none.png)">底纹</p>'
    make(root, "g5-cssmiss", pages=pages)
    steps_ok(root, "g5-cssmiss", "phases")
    expect_fail(root, "g5-cssmiss", ("check", "g5-cssmiss", "pages"), "assets/none.png")

    # style 的 url() 指到 assets/ 里真实存在的文件：放行，且成品里没有外链
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<p style="background:url(assets/bg.png)">底纹</p>'
    d = make(root, "g5-cssok", pages=pages)
    write(os.path.join(d, "assets", "bg.png"), "假装这是一张图")
    steps_ok(root, "g5-cssok")
    check(run("build", "g5-cssok", cwd=root)[0] == 0, "本地底图应放行并出得了成品")
    deck = read(os.path.join(d, "deck.html"))
    check("url(assets/bg.png)" in deck, "本地底图应原样进成品")
    check("example.invalid" not in deck and "url(http" not in deck and "url(//" not in deck,
          "成品里不许有 url() 外链")

    # 外链判据不按函数名枚举（终审收窄：协议字样出现即判）：image-set / cross-fade /
    # -webkit-image-set / image() 乃至 CSS 注释里的网址，一律拒收
    for i, evil in enumerate(("image-set('https://cdn.example.invalid/a.png' 1x)",
                              "-webkit-image-set(url('https://cdn.example.invalid/a.png') 1x)",
                              "image('//example.invalid/x.png')",
                              "cross-fade('https://a.example.invalid/a.png',"
                              "'https://b.example.invalid/b.png')",
                              "red;/* 参考 https://example.invalid/doc */")):
        pages = base_pages()
        pages[0]["html"] = P1_HTML + '<p style="background:%s">底纹</p>' % evil
        slug = "g5-cssproto-%d" % i
        make(root, slug, pages=pages)
        steps_ok(root, slug, "phases")
        out = expect_fail(root, slug, ("check", slug, "pages"), "外链字样")
        check("p1" in out, "%s 的报错应指到页 p1\n%s" % (slug, out))

    # data:image 载荷里的 // 不算外链：判据先抠掉合法载荷再查，不误伤内嵌图
    pages = base_pages()
    pages[0]["html"] = (P1_HTML +
                        '<p style="background:url(data:image/png;base64,aa//bb+cc==)">底纹</p>')
    make(root, "g5-dataok", pages=pages)
    steps_ok(root, "g5-dataok", "phases")
    res = run("check", "g5-dataok", "pages", cwd=root)
    check(res[0] == 0, "data:image 载荷里的 // 不该被外链判据误伤\n%s" % both(res))

    # CSS 反斜杠转义与实体裹协议：浏览器会把 \\68\\74… 解码成 https，协议判扫不到，
    # 所以 style 值经实体解码后出现反斜杠一律拒收；&sol;&sol; 解码后就是协议相对 //
    for i, (evil, needle) in enumerate((
            ("image-set('\\68\\74\\74\\70\\73:\\2f\\2f evil\\2f x' 1x)", "反斜杠"),
            ("image-set('&#92;68&#92;74&#92;74&#92;70&#92;73:&#92;2f&#92;2f evil&#92;2f x' 1x)",
             "反斜杠"),
            ("image-set('&#x5c;68&#X5C;74&#x5c;74&#x5c;70&#x5c;73:&#x5c;2f&#x5c;2f evil' 1x)",
             "反斜杠"),
            ("url(&sol;&sol;evil.invalid/x.png)", "外链字样"))):
        pages = base_pages()
        pages[0]["html"] = P1_HTML + '<div style="background:%s">底纹</div>' % evil
        slug = "g5-cssesc-%d" % i
        make(root, slug, pages=pages)
        steps_ok(root, slug, "phases")
        out = expect_fail(root, slug, ("check", slug, "pages"), needle)
        check("p1" in out, "%s 的报错应指到页 p1\n%s" % (slug, out))

    # 成品侧同一条判据：verify_shell 自己也要抓 image-set 外链，不依赖准入闸兜底
    sys.path.insert(0, HERE)
    import lessonkit                                             # noqa: E402
    shell_rep = lessonkit.Rep()
    lessonkit.verify_shell(
        "<div style=\"background:image-set('https://evil.invalid/x.png' 1x)\"></div>",
        "", 0, shell_rep)
    check(any("外链字样" in e["reason"] for e in shell_rep.errors()),
          "verify_shell 应按协议字样抓成品里的 image-set 外链")

    # 成品侧的反斜杠同口径：deck 里 style 值出现 CSS 转义也要在 G9 被拒
    shell_rep = lessonkit.Rep()
    lessonkit.verify_shell(
        "<div style=\"background:image-set('\\68\\74\\74\\70\\73:\\2f\\2f evil\\2f x' 1x)\">"
        "</div>", "", 0, shell_rep)
    check(any("反斜杠" in e["reason"] for e in shell_rep.errors()),
          "verify_shell 应拒收成品 style 值里的反斜杠转义")

    # 壳保留的类名：页稿用了就会在成品里多出一页假页
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<div class="slide">冒充一页</div>'
    make(root, "g5-shellclass", pages=pages)
    steps_ok(root, "g5-shellclass", "phases")
    out = expect_fail(root, "g5-shellclass", ("check", "g5-shellclass", "pages"), "保留的类名")
    check("p1" in out and "slide" in out, "应点名是哪一页用了哪个类名\n%s" % out)

    # 普通类名不误伤
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<div class="tip note">课堂提示</div>'
    make(root, "g5-okclass", pages=pages)
    steps_ok(root, "g5-okclass", "phases")
    res = run("check", "g5-okclass", "pages", cwd=root)
    check(res[0] == 0, "普通类名不该被壳保留名误伤\n%s" % both(res))

    # 页稿里写 data-page-id：G5 直接拒收并点名页 id，不等到 build 报壳级错误
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<div data-page-id="p9">冒充</div>'
    make(root, "g5-pageattr", pages=pages)
    steps_ok(root, "g5-pageattr", "phases")
    out = expect_fail(root, "g5-pageattr", ("check", "g5-pageattr", "pages"), "data-page-id")
    check("p1" in out, "应点名是页 p1 写了 data-page-id\n%s" % out)
    check("G9" not in out, "这该在 G5 拦下，不该拖到 build 变成壳级错误\n%s" % out)

    # 普通 data-* 不误伤
    pages = base_pages()
    pages[0]["html"] = P1_HTML + '<div data-step="2">课堂提示</div>'
    make(root, "g5-okdata", pages=pages)
    steps_ok(root, "g5-okdata", "phases")
    res = run("check", "g5-okdata", "pages", cwd=root)
    check(res[0] == 0, "普通 data-* 不该被误伤\n%s" % both(res))

    # 占位模式
    for i, bad in enumerate(("<p>TODO：这里补一段。</p>", "<p>TBD</p>", "<p>placeholder text here</p>",
                             "<p>Lorem ipsum dolor sit amet.</p>", "<p>此处插图</p>",
                             "<p>待补图</p>", "<p>[图]</p>")):
        pages = base_pages()
        pages[0]["html"] = P1_HTML + bad
        slug = "g5-ph-%d" % i
        make(root, slug, pages=pages)
        steps_ok(root, slug, "phases")
        expect_fail(root, slug, ("check", slug, "pages"), "占位")

    # 空 figure
    pages = base_pages()
    pages[0]["html"] = P1_HTML + "<figure></figure>"
    make(root, "g5-figure", pages=pages)
    steps_ok(root, "g5-figure", "phases")
    expect_fail(root, "g5-figure", ("check", "g5-figure", "pages"), "figure")

    # 密度：>350 WARN，>1000 ERROR
    pages = base_pages()
    pages[0]["html"] = P1_HTML + "<p>" + ("字" * 400) + "</p>"
    pages[0]["notes"] = P1_NOTES + "另说一句。" * 90
    make(root, "g5-dense", pages=pages)
    steps_ok(root, "g5-dense", "phases")
    res = run("check", "g5-dense", "pages", cwd=root)
    check("WARN" in both(res), "正文 400 字应给密度 WARN\n%s" % both(res))
    pages = base_pages()
    pages[0]["html"] = P1_HTML + "<p>" + ("字" * 1100) + "</p>"
    pages[0]["notes"] = P1_NOTES + "另说一句。" * 250
    make(root, "g5-toodense", pages=pages)
    steps_ok(root, "g5-toodense", "phases")
    expect_fail(root, "g5-toodense", ("check", "g5-toodense", "pages"), "密度")

    # 阶段没有页
    pages = [p for p in base_pages() if p["phase"] == PHASE_A]
    pages.append(dict(base_pages()[1], phase=PHASE_A))
    make(root, "g5-emptyphase", pages=pages)
    steps_ok(root, "g5-emptyphase", "phases")
    expect_fail(root, "g5-emptyphase", ("check", "g5-emptyphase", "pages"), PHASE_B)

    # 页引用了不存在的阶段
    pages = base_pages()
    pages[0]["phase"] = "没有这个阶段"
    make(root, "g5-badphase", pages=pages)
    steps_ok(root, "g5-badphase", "phases")
    expect_fail(root, "g5-badphase", ("check", "g5-badphase", "pages"), "没有这个阶段")

    # covers 指向不存在的题
    pages = base_pages()
    pages[0]["covers"] = ["q9"]
    make(root, "g5-badcover", pages=pages)
    steps_ok(root, "g5-badcover", "phases")
    expect_fail(root, "g5-badcover", ("check", "g5-badcover", "pages"), "q9")

    # drill:<slug> 只校验形态
    pages = base_pages()
    pages[0]["covers"] = ["q1", "drill:binary-search"]
    make(root, "g5-drill", pages=pages)
    steps_ok(root, "g5-drill", "phases")
    res = run("check", "g5-drill", "pages", cwd=root)
    check(res[0] == 0, "covers 里的 drill:<slug> 应只校验形态\n%s" % both(res))
    pages[0]["covers"] = ["q1", "drill:Bad Slug!"]
    make(root, "g5-drillbad", pages=pages)
    steps_ok(root, "g5-drillbad", "phases")
    expect_fail(root, "g5-drillbad", ("check", "g5-drillbad", "pages"), "drill:")
    return ("G5：5 组消毒绕过 + 外链图 + 缺图文件 + 白名单外标签 + style 的 url() 三种外链写法 + "
            "image-set 家族与注释网址 5 种协议字样 + CSS 反斜杠转义／&#92; 实体／&sol; 拼协议相对 "
            "4 种裹协议写法（成品侧 verify_shell 同判据，反斜杠也拒） + "
            "壳保留类名 + 页稿写 data-page-id + 7 种占位 + 空 figure + 密度双档 + 阶段无页 + "
            "covers 悬空 全被判死；drill:<slug>、本地底图、data:image 载荷、普通类名与普通 data-* 不误伤")


# ---------------------------------------------------------------- G6 讲稿

def t_g6(root):
    pages = base_pages()
    pages[0]["notes"] = ""
    make(root, "g6-empty", pages=pages)
    steps_ok(root, "g6-empty", "phases")
    expect_fail(root, "g6-empty", ("check", "g6-empty", "pages"), "讲稿")

    pages = base_pages()
    pages[0]["notes"] = "<p>" + P1_NOTES + "</p>"
    make(root, "g6-html", pages=pages)
    steps_ok(root, "g6-html", "phases")
    expect_fail(root, "g6-html", ("check", "g6-html", "pages"), "HTML")

    pages = base_pages()
    pages[0]["notes"] = "TODO 回头补讲稿。" + "再想想。" * 90
    make(root, "g6-placeholder", pages=pages)
    steps_ok(root, "g6-placeholder", "phases")
    expect_fail(root, "g6-placeholder", ("check", "g6-placeholder", "pages"), "占位")

    lesson = clone(LESSON)
    lesson["minutes"] = 120
    pages = base_pages()
    make(root, "g6-total", lesson=lesson, pages=pages)
    steps_ok(root, "g6-total", "phases")
    expect_fail(root, "g6-total", ("check", "g6-total", "pages"), "全课讲稿字数")
    return "G6：讲稿空 / 讲稿带 HTML / 讲稿写占位 / 全课讲稿低于 minutes×60 全被判死"


# ---------------------------------------------------------------- G7 覆盖

def t_g7(root):
    pages = base_pages()
    pages[2]["covers"] = []
    make(root, "g7-uncovered", pages=pages)
    steps_ok(root, "g7-uncovered", "phases")
    out = expect_fail(root, "g7-uncovered", ("check", "g7-uncovered", "pages"), "没有任何一页覆盖")
    check("q4" in out, "应逐题指出是 q4 没被覆盖\n%s" % out)

    qs = clone(QUESTIONS)
    qs[0]["choices"] = ["熔化", "凝华", "凝固", "液化"]
    qs[0]["correct"] = [1]
    make(root, "g7-choice", questions=qs)
    steps_ok(root, "g7-choice", "phases")
    res = run("check", "g7-choice", "pages", cwd=root)
    check("WARN" in both(res), "正确项文本在覆盖页里找不到应给 WARN\n%s" % both(res))
    return "G7：漏题逐题点名；choice 正确项文本不在覆盖页给 WARN"


# ---------------------------------------------------------------- G8 八个作弊课

def t_cheats(root):
    notes = []

    # ① 一页 covers 全部题
    pages = base_pages()
    pages[0]["covers"] = ["q1", "q2", "q3", "q4"]
    pages[1]["covers"] = []
    pages[2]["covers"] = []
    make(root, "cheat-allcovers", pages=pages)
    steps_ok(root, "cheat-allcovers", "phases")
    expect_fail(root, "cheat-allcovers", ("check", "cheat-allcovers", "pages"), "单页最多覆盖 3 道题")
    notes.append("①一页 covers 全部题 → 单页最多覆盖 3 道题")

    # ② 题干与覆盖页 0 实词重合
    qs = clone(QUESTIONS)
    qs[3]["prompt"] = "比较帆船时代的星象定位与卫星导航在精度上的高下，并写出两条依据。"
    qs[3]["focus"] = ["星象定位", "卫星导航"]
    make(root, "cheat-noword", questions=qs)
    steps_ok(root, "cheat-noword", "phases")
    out = expect_fail(root, "cheat-noword", ("check", "cheat-noword", "pages"), "页里没讲到这道题")
    check("q4" in out, "应点名 q4\n%s" % out)
    notes.append("②题干与覆盖页 0 实词重合 → 页里没讲到这道题")

    # ③ 讲稿 = 正文复制
    body = re.sub(r"<[^>]+>", "", P2_HTML)
    pages = base_pages()
    pages[1]["notes"] = (body + "\n") * 4
    make(root, "cheat-copy", pages=pages)
    steps_ok(root, "cheat-copy", "phases")
    expect_fail(root, "cheat-copy", ("check", "cheat-copy", "pages"), "抄正文当讲稿")
    notes.append("③讲稿复制正文 → 抄正文当讲稿")

    # ③b 讲稿抄大半正文再添几句：重合率钉在 COPY_RATIO 与 1.00 之间，闸门必须照样判死。
    #    ③ 是逐字复制（重合率 1.00），把 COPY_RATIO 悄悄抬到 0.999 它也照样红，
    #    等于没钉住边界；这条用例专治那个变异。
    sys.path.insert(0, HERE)
    import lessonkit                                             # noqa: E402
    near_tail = ("下面这些句子是讲稿自己的话：先请两位同学各复述一遍，再留半分钟自由提问，"
                 "然后请大家把桌上的练习册翻到对应那页，圈出容易写错的两个词，"
                 "最后板书擦干净，准备进入气压与沸点那一页。")
    near_copy = body[: int(len(body) * 0.9)] + "\n" + near_tail
    ratio = lessonkit.overlap_ratio(lessonkit.bigrams(near_copy), lessonkit.bigrams(body))
    check(lessonkit.COPY_RATIO < ratio < 0.97,
          "边界用例失守：重合率 %.3f 应落在 COPY_RATIO=%.2f 与 0.97 之间，"
          "否则这条用例退化成逐字复制、钉不住边界" % (ratio, lessonkit.COPY_RATIO))
    check(lessonkit.text_len(near_copy) >= lessonkit.text_len(body),
          "边界用例的讲稿字数应不少于正文，免得先撞上字数闸")
    pages = base_pages()
    pages[1]["notes"] = near_copy
    make(root, "cheat-nearcopy", pages=pages)
    steps_ok(root, "cheat-nearcopy", "phases")
    expect_fail(root, "cheat-nearcopy", ("check", "cheat-nearcopy", "pages"), "抄正文当讲稿")
    notes.append("③b 讲稿抄 %.0f%% 正文再添新话（重合率 %.2f）→ 抄正文当讲稿" % (90, ratio))

    # ③c 重合率钉在 (0.80, 0.90) 的下侧边界：③b 落在 0.9 以上，只防得住阈值抬到
    #    0.999 的变异；把 COPY_RATIO 从 0.8 悄悄抬到 0.9，③b 照样红、变异就活了。
    #    这条用例的重合率落在两档之间，0.8→0.9 与 0.8→0.999 两个方向的变异都判死。
    mid_tail = ("以下是讲稿自己的安排：请第一排的同学把桌面清空只留笔，随后两人一组互相口述"
                "刚才的结论，口述完各自在练习册背面默写一遍关键词，写错的用铅笔圈出来。"
                "教师沿过道巡视一圈，挑两份写法不同的举给全班看，请大家评一评谁的表述更严谨，"
                "最后齐读黑板中间那句话收束。")
    mid_copy = body[: int(len(body) * 0.82)] + "\n" + mid_tail
    mid_ratio = lessonkit.overlap_ratio(lessonkit.bigrams(mid_copy), lessonkit.bigrams(body))
    check(0.80 < mid_ratio < 0.90,
          "下侧边界用例失守：重合率 %.3f 应落在 0.80 与 0.90 之间，"
          "否则钉不住 COPY_RATIO 被抬到 0.9 的变异" % mid_ratio)
    check(lessonkit.text_len(mid_copy) >= lessonkit.text_len(body),
          "下侧边界用例的讲稿字数应不少于正文，免得先撞上字数闸")
    pages = base_pages()
    pages[1]["notes"] = mid_copy
    make(root, "cheat-midcopy", pages=pages)
    steps_ok(root, "cheat-midcopy", "phases")
    expect_fail(root, "cheat-midcopy", ("check", "cheat-midcopy", "pages"), "抄正文当讲稿")
    notes.append("③c 讲稿抄 82%% 正文再添新话（重合率 %.2f，落在 0.80 与 0.90 之间）"
                 "→ 抄正文当讲稿" % mid_ratio)

    # ④ 讲稿只有一个字
    pages = base_pages()
    pages[1]["notes"] = "讲\n"
    make(root, "cheat-oneword", pages=pages)
    steps_ok(root, "cheat-oneword", "phases")
    expect_fail(root, "cheat-oneword", ("check", "cheat-oneword", "pages"), "讲稿字数少于本页正文")
    notes.append("④讲稿只有一个字 → 讲稿字数少于本页正文")

    # ⑤ 没出作业直接写阶段
    make(root, "cheat-noqs", skip_questions=True, skip_pages=True)
    steps_ok(root, "cheat-noqs", "lesson")
    expect_fail(root, "cheat-noqs", ("check", "cheat-noqs", "phases"), "先出作业，再规划阶段", rc=2)
    notes.append("⑤没出作业直接写阶段 → 先出作业，再规划阶段（exit 2）")

    # ⑥ 阶段带编号前缀
    ph = clone(PHASES)
    ph[0]["title"] = "第一阶段：三态的差别"
    make(root, "cheat-numbered", phases=ph, skip_pages=True)
    steps_ok(root, "cheat-numbered", "questions")
    expect_fail(root, "cheat-numbered", ("check", "cheat-numbered", "phases"), "编号前缀")
    notes.append("⑥阶段带编号前缀 → 阶段标题不许带编号前缀")

    # ⑦ 手改 deck.html
    slug = "cheat-handdeck"
    d = make(root, slug)
    steps_ok(root, slug)
    check(run("build", slug, cwd=root)[0] == 0, "build 应退出 0")
    write(os.path.join(d, "deck.html"), read(os.path.join(d, "deck.html")) + "<!-- 手改一笔 -->\n")
    expect_fail(root, slug, ("check", slug, "--all"), "成品不是由 build 生成或生成后被手改")
    notes.append("⑦手改 deck.html → 成品不是由 build 生成或生成后被手改")

    # 手写 deck.html 而根本没 build 过
    slug = "cheat-nobuild"
    d = make(root, slug)
    steps_ok(root, slug)
    write(os.path.join(d, "deck.html"), "<!DOCTYPE html><html><body>我自己写的</body></html>\n")
    expect_fail(root, slug, ("check", slug, "--all"), "成品不是由 build 生成或生成后被手改")

    # ⑧ 上游改动，下游作废
    slug = "cheat-stale"
    d = make(root, slug)
    steps_ok(root, slug)
    qs = clone(QUESTIONS)
    qs[0]["prompt"] = "水从液态变成气态的相变到底叫做什么名字呢？"
    dump(os.path.join(d, "questions.json"), qs)
    expect_fail(root, slug, ("check", slug, "pages"),
                "questions.json 已改动，请从 check questions 重新验收")
    notes.append("⑧上游改动 → questions.json 已改动，请从 check questions 重新验收")

    # 阶段改动同理
    slug = "cheat-stale2"
    d = make(root, slug)
    steps_ok(root, slug)
    ph = clone(PHASES)
    ph[1]["minutes"] = 5
    dump(os.path.join(d, "phases.json"), ph)
    expect_fail(root, slug, ("check", slug, "pages"),
                "phases.json 已改动，请从 check phases 重新验收")

    # 页稿改动，成品作废
    slug = "cheat-stale3"
    d = make(root, slug)
    steps_ok(root, slug)
    check(run("build", slug, cwd=root)[0] == 0, "build 应退出 0")
    write(os.path.join(d, "pages", "p1.html"), P1_HTML + "<p>临时加一句，改完没重新出成品。</p>")
    expect_fail(root, slug, ("check", slug, "--all"), "重新")
    return notes


# ---------------------------------------------------------------- G9 build

def t_build(root):
    # 单页失败只标页级：盖章后把一页改坏，那一页记 failReason 不进成品，
    # 其余两页照样拼得出来；同时上游改动本身也判死，所以整次 build 仍不落盘。
    slug = "build-onefail"
    d = make(root, slug)
    steps_ok(root, slug)
    check(run("build", slug, cwd=root)[0] == 0, "先出一版干净成品")
    stamp = read_bytes(os.path.join(d, "deck.html"))
    write(os.path.join(d, "pages", "p3.html"), P3_HTML + '<img src="jAvAsCrIpT:alert(1)">')
    res = run("build", slug, cwd=root)
    check(res[0] == 1, "带毒页的 build 应判死，实际 %d\n%s" % (res[0], both(res)))
    out = both(res)
    check("p3" in out and "没能进成品" in out, "失败页应记页级 failReason\n%s" % out)
    check("已改动" in out, "上游改动也该被点出来\n%s" % out)
    check(read_bytes(os.path.join(d, "deck.html")) == stamp, "判死的这次 build 不许覆盖旧成品")

    # 页稿有毒时 check pages 先一步判死
    pages = base_pages()
    pages[2]["html"] = P3_HTML + '<img src="jAvAsCrIpT:alert(1)">'
    make(root, "build-poison", pages=pages)
    steps_ok(root, "build-poison", "phases")
    check(run("check", "build-poison", "pages", cwd=root)[0] == 1, "带毒页的 check pages 应判死")

    pages = base_pages()
    make(root, "build-clean", pages=pages)
    steps_ok(root, "build-clean")
    check(run("build", "build-clean", cwd=root)[0] == 0, "干净课 build 应退出 0")

    # 全部页失败：不写 deck.html，退出 2
    slug = "build-allfail"
    d = make(root, slug)
    steps_ok(root, slug)
    for name in ("p1", "p2", "p3"):
        write(os.path.join(d, "pages", name + ".html"), '<script src=//x>')
    expect_fail(root, slug, ("build", slug), "全部", rc=2)
    check(not os.path.isfile(os.path.join(d, "deck.html")), "全部页失败时不许写出 deck.html")

    # accent 定值被换回 var(--accent)
    pages = base_pages()
    pages[0]["html"] = '<h1 style="color:#0891B2">固态、液态、气态</h1>' + P1_HTML[P1_HTML.index("\n"):]
    slug = "build-accent"
    d = make(root, slug, pages=pages)
    steps_ok(root, slug)
    check(run("build", slug, cwd=root)[0] == 0, "build 应退出 0")
    deck = read(os.path.join(d, "deck.html"))
    check("#0891B2" not in deck and "#0891b2" not in deck.replace(":root{--accent:#0891b2;}", ""),
          "八色定值应被换成 var(--accent)")
    check("var(--accent)" in deck, "换色后正文里应留下 var(--accent)")

    # 非中性色 WARN
    pages = base_pages()
    pages[0]["html"] = '<h1 style="color:#ff2d55">固态、液态、气态</h1>' + P1_HTML[P1_HTML.index("\n"):]
    slug = "build-hex"
    make(root, slug, pages=pages)
    steps_ok(root, slug)
    res = run("build", slug, cwd=root)
    check(res[0] == 0 and "WARN" in both(res), "写死非中性色应给 WARN\n%s" % both(res))

    # 消毒会把没闭合的标签配平，一页的版面吞不掉下一页
    pages = base_pages()
    pages[0]["html"] = "<div><p>" + P1_HTML
    slug = "build-unclosed"
    d = make(root, slug, pages=pages)
    steps_ok(root, slug)
    check(run("build", slug, cwd=root)[0] == 0, "没闭合的标签不该挡住 build")
    deck = read(os.path.join(d, "deck.html"))
    for tag in ("div", "p", "section", "ul", "li"):
        check(deck.count("<%s" % tag) == deck.count("</%s>" % tag),
              "成品里 <%s> 应配平：开 %d 个、闭 %d 个"
              % (tag, deck.count("<%s" % tag), deck.count("</%s>" % tag)))

    # 换色无可见变化 WARN
    pages = base_pages()
    pages[0]["html"] = ("<p>同一种物质在温度改变时会呈现三种状态：固态、液态、气态。"
                        "液态受热变成气态，这个相变叫做汽化；气态遇冷变回液态，叫做液化。</p>")
    pages[0]["notes"] = P1_NOTES
    slug = "build-flat"
    make(root, slug, pages=pages)
    steps_ok(root, slug)
    res = run("build", slug, cwd=root)
    check("换色" in both(res) and "WARN" in both(res), "纯文本页应给「换色无可见变化」WARN\n%s" % both(res))
    return ("G9：单页失败只标页级且不覆盖旧成品 / 全部失败退 2 且不写 deck / 消毒把没闭合的标签配平 / "
            "八色定值换回 var(--accent) / 非中性色与纯文本页各给 WARN")


# ---------------------------------------------------------------- doctor 与卫生

_EXTRA_PARTS = (
    ("__int", "ro__"), ("__conclu", "sion__"), ("review", "History"), ("quality", "Reviews"),
    ("ai", "Suggestions"), ("section", "Snapshot"), ("trigger", "Score"), ("question", "GenCount"),
    ("read", "ability"), ("vertical", "Relevance"), ("horizontal", "Relevance"),
    ("potential", "-source"), ("common", "-phrase"), ("citation", "-needed"),
    ("core", "Lens"), ("learning", "Objectives"), ("slideDeck", "Shell"),
    ("STYLE_", "SEEDS"), ("DENSITY_", "TEXT"), ("data-image", "-request"),
    ("data-cos", "-key"), ("gen", "-image"), ("img", "-hint"), ("Cos", "Image"),
    ("myq", "cloud"), ("homework", "-prompts"),
)
BATCH_BANNED = tuple("".join(parts) for parts in _EXTRA_PARTS)
SCAN_EXT = (".py", ".md", ".json", ".html", ".css", ".js", ".txt", ".yml", ".yaml")


def t_hygiene():
    """G14：禁用词静态闸 + 本批次追加表 + 本机路径。"""
    sys.path.insert(0, HERE)
    import banned_words                                          # noqa: E402
    hits = banned_words.scan_dir(SKILL_DIR)
    check(not hits, "禁用词静态闸有命中：\n%s" % "\n".join(hits))

    bad = []
    for here, dirs, files in os.walk(SKILL_DIR):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git")]
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() not in SCAN_EXT:
                continue
            full = os.path.join(here, name)
            rel = os.path.relpath(full, SKILL_DIR)
            try:
                with open(full, "r", encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            low = text.lower()
            for word in BATCH_BANNED:
                if word.lower() in low:
                    bad.append("%s：出现本批次禁用子串「%s」" % (rel, word))
    check(not bad, "本批次追加禁用表有命中：\n%s" % "\n".join(bad))
    return "G14：禁用词静态闸 0 命中，本批次追加表 %d 条 0 命中" % len(BATCH_BANNED)


def t_engine_sync():
    """母仓内共享文件同步闸必须绿；单 Skill 独立安装（没有 tools/）时跳过不报错。"""
    gate = os.path.join(os.path.dirname(SKILL_DIR), "tools", "check_engine_sync.py")
    if not os.path.isfile(gate):
        return "共享文件同步闸 SKIP：tools/check_engine_sync.py 不在（单 Skill 安装），由母仓负责跑"
    proc = subprocess.run([PY, gate], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    check(proc.returncode == 0, "共享文件同步闸未过：\n%s" % out)
    check("banned_words.py" in out, "同步闸输出里应点名 banned_words.py：\n%s" % out)
    return "共享文件同步闸通过（banned_words.py 六份同字节）"


def t_doctor(root):
    res = run("doctor", cwd=root)
    check(res[0] == 0, "doctor 应退出 0，实际 %d\n%s" % (res[0], both(res)))
    check("Python" in res[1], "doctor 应报出 Python 版本\n%s" % res[1])
    check("3.8" in res[1] or "[OK]" in res[1], "doctor 应说明版本下限\n%s" % res[1])

    res = run("init", "brand-new", cwd=root)
    check(res[0] == 0, "init 应退出 0\n%s" % both(res))
    d = os.path.join(root, "lessons", "brand-new")
    for sub in ("pages", "assets", "materials"):
        check(os.path.isdir(os.path.join(d, sub)), "init 应建出 %s/" % sub)
    check(os.path.isfile(os.path.join(d, "lesson.json")), "init 应写出 lesson.json 骨架")
    skel = json.loads(read(os.path.join(d, "lesson.json")))
    check(skel.get("route") == "homework-first", "init 默认路线应是 homework-first")
    res = run("init", "brand-new", cwd=root)
    check(res[0] == 2, "重复 init 应退出 2\n%s" % both(res))
    res = run("init", "cf-new", "--route", "content-first", cwd=root)
    check(res[0] == 0, "init --route content-first 应退出 0\n%s" % both(res))
    skel = json.loads(read(os.path.join(root, "lessons", "cf-new", "lesson.json")))
    check(skel.get("route") == "content-first", "init 应把路线写进 lesson.json")
    res = run("check", "nope-not-here", "lesson", cwd=root)
    check(res[0] == 2, "不存在的课应退出 2\n%s" % both(res))
    return "doctor / init：骨架、默认路线、重复 init 拒绝、不存在的课退 2"


# ---------------------------------------------------------------- examples 复核

def t_examples(root):
    """示例课复核。

    `check --all` 每步都会 write_stamp，直接跑真实目录会把 .stamps/ 写脏工作树，
    发布闸自测跑一次就多出几个改动文件。所以先整份拷进临时目录再跑，
    示例课本身一个字节都不动。
    """
    ex = os.path.join(SKILL_DIR, "examples", "lessons")
    if not os.path.isdir(ex):
        return "examples/lessons/ 尚未落地，示例课复核 SKIP"
    names = sorted(n for n in os.listdir(ex) if os.path.isdir(os.path.join(ex, n)))
    if not names:
        return "examples/lessons/ 是空的，示例课复核 SKIP"
    sandbox = os.path.join(root, "examples-copy")
    done = []
    for name in names:
        before = snapshot(os.path.join(ex, name))
        target = os.path.join(sandbox, name)
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(os.path.join(ex, name), target)
        res = run("check", target, "--all", cwd=root)
        check(res[0] == 0, "示例课 %s 的 check --all 应 0 ERROR\n%s" % (name, both(res)))
        check(snapshot(os.path.join(ex, name)) == before,
              "复核示例课 %s 不许改动 examples/ 下的任何文件" % name)
        done.append(name)
    return "示例课复核（拷到临时目录跑，原目录逐字节不动）：%s 全部 0 ERROR" % "、".join(done)


def snapshot(directory):
    """目录里每个文件的相对路径 → 内容，用来断言「一个字节都没动」。"""
    out = {}
    for here, dirs, files in os.walk(directory):
        dirs[:] = [d for d in sorted(dirs) if d != "__pycache__"]
        for name in sorted(files):
            full = os.path.join(here, name)
            out[os.path.relpath(full, directory)] = read_bytes(full)
    return out


# ---------------------------------------------------------------- 入口

def main():
    if not os.path.isfile(KIT):
        print("FAIL：找不到 %s" % KIT)
        return 1
    root = tempfile.mkdtemp(prefix="lesson-prep-selftest-")
    try:
        print(t_doctor(root))
        t_positive(root)
        print("正例：四步全绿 → build → report → check --all；壳字符串、deck 不含讲稿、build 两次逐字节一致")
        print(t_repalette(root))
        print(t_g1(root))
        print(t_g2(root))
        print(t_locks(root))
        print(t_g4(root))
        print(t_numbered(root))
        print(t_g5(root))
        print(t_g6(root))
        print(t_g7(root))
        for line in t_cheats(root):
            print("作弊课：" + line)
        print(t_build(root))
        print(t_hygiene())
        print(t_engine_sync())
        print(t_examples(root))
        print("OK")
        return 0
    except Failed as e:
        print("FAIL：%s" % e)
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
