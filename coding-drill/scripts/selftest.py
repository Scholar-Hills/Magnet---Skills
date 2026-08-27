#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""judge.py 自测：临时构造题包，走 author → judge → export 全流程，再跑一组攻击 / 健壮性回归，断言全部通过后打印 OK。

用法：python3 scripts/selftest.py
不依赖 examples/ 目录；所有题包都建在临时目录里，跑完删除。
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(HERE, "judge.py")
PY = sys.executable

PROBLEM_MD = """# 有序数组里第一个不小于目标的位置

## 任务

给定一个**非递减**排列的整数数组和一个目标值 `t`，输出第一个满足 `a[i] >= t` 的下标 `i`（从 0 开始）。
如果所有元素都小于 `t`，输出 `n`。

## 输入格式

- 第一行一个整数 n（1 ≤ n ≤ 100）
- 第二行 n 个整数，空格分隔，非递减
- 第三行一个整数 t

## 输出格式

一个整数。

## 示例

输入：

```
5
1 3 5 7 9
5
```

输出：

```
2
```
"""

TESTS = {
    "cases": [
        {"id": "c1", "isSample": True, "score": 0, "job": "sample", "input": "5\n1 3 5 7 9\n5", "expected": None, "catches": ""},
        {"id": "c2", "isSample": False, "score": 2, "job": "typical", "input": "6\n2 4 6 8 10 12\n11", "expected": None, "catches": "只在样例位置附近查找"},
        {"id": "c3", "isSample": False, "score": 3, "job": "boundary", "input": "4\n1 2 3 4\n4", "expected": None, "catches": "用 > 代替 >=，恰好相等的元素被跳过"},
        {"id": "c4", "isSample": False, "score": 2, "job": "empty", "input": "7\n1 2 3 4 5 6 7\n10", "expected": None, "catches": "找不到时没有返回 n"},
        {"id": "c5", "isSample": False, "score": 3, "job": "saturated", "input": "1\n5\n1", "expected": None, "catches": "单元素数组时循环边界写错"},
    ]
}

# ---------------- Python 题包
PY_STARTER = """import sys

def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    a = [int(x) for x in data[1:1 + n]]
    t = int(data[1 + n])
    # 在这里写你的代码
    answer = -1
    print(answer)

main()
"""

PY_REFERENCE = """import sys

def lower_bound(a, t):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] >= t:
            hi = mid
        else:
            lo = mid + 1
    return lo

def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    a = [int(x) for x in data[1:1 + n]]
    t = int(data[1 + n])
    print(lower_bound(a, t))

main()
"""

PY_M1 = """import sys

def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    a = [int(x) for x in data[1:1 + n]]
    t = int(data[1 + n])
    for i in range(n):
        if a[i] > t:
            print(i)
            return
    print(n)

main()
"""

PY_M2 = """import sys

def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    a = [int(x) for x in data[1:1 + n]]
    t = int(data[1 + n])
    for i in range(n):
        if a[i] >= t:
            print(i)
            return
    print(-1)

main()
"""

PY_CONSTANT = "print(2)\n"
PY_TIMEOUT = "import sys\nsys.stdin.read()\nwhile True:\n    pass\n"
PY_SYNTAX = "def main(:\n    pass\n"
PY_WRONG = PY_STARTER.replace("answer = -1", "answer = n + 100")

# ---------------- JavaScript 题包
JS_STARTER = """const data = require('fs').readFileSync(0, 'utf8').split(/\\s+/).filter(Boolean);
const n = parseInt(data[0], 10);
const a = data.slice(1, 1 + n).map(Number);
const t = parseInt(data[1 + n], 10);
// 在这里写你的代码
let answer = -1;
console.log(answer);
"""

JS_REFERENCE = """const data = require('fs').readFileSync(0, 'utf8').split(/\\s+/).filter(Boolean);
const n = parseInt(data[0], 10);
const a = data.slice(1, 1 + n).map(Number);
const t = parseInt(data[1 + n], 10);
let lo = 0, hi = n;
while (lo < hi) {
  const mid = Math.floor((lo + hi) / 2);
  if (a[mid] >= t) hi = mid; else lo = mid + 1;
}
console.log(lo);
"""

JS_M1 = """const data = require('fs').readFileSync(0, 'utf8').split(/\\s+/).filter(Boolean);
const n = parseInt(data[0], 10);
const a = data.slice(1, 1 + n).map(Number);
const t = parseInt(data[1 + n], 10);
let ans = n;
for (let i = 0; i < n; i++) { if (a[i] > t) { ans = i; break; } }
console.log(ans);
"""

JS_M2 = """const data = require('fs').readFileSync(0, 'utf8').split(/\\s+/).filter(Boolean);
const n = parseInt(data[0], 10);
const a = data.slice(1, 1 + n).map(Number);
const t = parseInt(data[1 + n], 10);
let ans = -1;
for (let i = 0; i < n; i++) { if (a[i] >= t) { ans = i; break; } }
console.log(ans);
"""

JS_CONSTANT = "console.log(2);\n"
JS_TIMEOUT = "require('fs').readFileSync(0, 'utf8');\nwhile (true) {}\n"
JS_SYNTAX = "function main( {\n"
JS_WRONG = JS_STARTER.replace("let answer = -1;", "let answer = n + 100;")

# ---------------- Java 题包
JAVA_STARTER = """import java.util.*;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int[] a = new int[n];
        for (int i = 0; i < n; i++) a[i] = sc.nextInt();
        int t = sc.nextInt();
        // 在这里写你的代码
        int answer = -1;
        System.out.println(answer);
    }
}
"""

JAVA_REFERENCE = """import java.util.*;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int[] a = new int[n];
        for (int i = 0; i < n; i++) a[i] = sc.nextInt();
        int t = sc.nextInt();
        int lo = 0, hi = n;
        while (lo < hi) {
            int mid = (lo + hi) / 2;
            if (a[mid] >= t) hi = mid; else lo = mid + 1;
        }
        System.out.println(lo);
    }
}
"""

JAVA_M1 = JAVA_REFERENCE.replace("a[mid] >= t", "a[mid] > t")
JAVA_M2 = JAVA_STARTER.replace("int answer = -1;", "int answer = -1;\n        for (int i = 0; i < n; i++) { if (a[i] >= t) { answer = i; break; } }")
JAVA_WRONG = JAVA_STARTER.replace("int answer = -1;", "int answer = n + 100;")

# ---------------- 攻击程序
PY_OUTPUT_BOMB = "import sys\nbuf = 'y' * (1 << 20)\nwhile True:\n    sys.stdout.write(buf)\n"

PY_ESCAPE = """import os, sys, time
sys.stdin.read()
sys.stdout.write('spawned')
sys.stdout.flush()
pid = os.fork()
if pid == 0:
    os.setsid()
    os.execv(sys.executable, [sys.executable, '-c', 'import time\\ntime.sleep(60)  # %s'])
while True:
    pass
"""

JS_ESCAPE = """require('fs').readFileSync(0, 'utf8');
process.stdout.write('spawned');
const cp = require('child_process');
const c = cp.spawn(process.execPath, ['-e', 'setTimeout(() => {}, 60000) // %s'], {detached: true, stdio: 'ignore'});
c.unref();
while (true) {}
"""

PY_PEEK = """import os, sys, subprocess, glob, json
data = sys.stdin.read()
ppid = os.getppid()
cwd = None
try:
    cwd = os.readlink('/proc/%d/cwd' % ppid)
except Exception:
    try:
        out = subprocess.run(['lsof', '-a', '-p', str(ppid), '-d', 'cwd', '-Fn'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8).stdout.decode()
        for line in out.splitlines():
            if line.startswith('n'):
                cwd = line[1:]
    except Exception:
        pass
if cwd is None:
    cwd = os.getcwd()
for path in glob.glob(os.path.join(cwd, 'drills', '*', '.hidden', 'tests.json')):
    with open(path) as f:
        for c in json.load(f)['cases']:
            if c['input'] == data:
                print(c['expected'])
                sys.exit(0)
print('FOUND ' + cwd)
"""

# ---------------- 求最大值题包（答案总是输入里的最后一个 token）
MAX_PROBLEM_MD = """# 最大值

## 任务

给定 n 个整数，输出其中的最大值。

## 输入格式

- 第一行一个整数 n（1 ≤ n ≤ 100）
- 第二行 n 个整数

## 输出格式

一个整数。

## 示例

输入：

```
3
1 5 2
```

输出：

```
5
```
"""

MAX_TESTS = {
    "cases": [
        {"id": "c1", "isSample": True, "score": 0, "job": "sample", "input": "3\n1 5 2", "expected": None, "catches": ""},
        {"id": "c2", "isSample": False, "score": 2, "job": "typical", "input": "4\n1 2 3 9", "expected": None, "catches": "最大值在末尾时没有遍历到最后一个元素"},
        {"id": "c3", "isSample": False, "score": 3, "job": "order", "input": "5\n1 2 3 4 8", "expected": None, "catches": "只比较了前几个元素就提前停止"},
        {"id": "c4", "isSample": False, "score": 2, "job": "boundary", "input": "3\n6 1 2", "expected": None, "catches": "最大值在开头时被后面的元素覆盖"},
        {"id": "c5", "isSample": False, "score": 3, "job": "saturated", "input": "1\n11", "expected": None, "catches": "单元素数组时循环没有执行"},
    ]
}
MAX_STARTER = "import sys\ndata = sys.stdin.read().split()\nn = int(data[0])\na = [int(x) for x in data[1:1 + n]]\n# 在这里写你的代码\nanswer = -1\nprint(answer)\n"
MAX_REFERENCE = "import sys\ndata = sys.stdin.read().split()\nn = int(data[0])\na = [int(x) for x in data[1:1 + n]]\nprint(max(a))\n"
MAX_M1 = MAX_REFERENCE.replace("print(max(a))", "print(a[0])")
MAX_M2 = MAX_REFERENCE.replace("print(max(a))", "print(max(a[:-1]) if n > 1 else a[0])")


# ---------------- 工具
class Failed(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Failed(msg)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run(*args, cwd=None, env=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    r = subprocess.run([PY, JUDGE] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=full_env, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def gate(ar, name):
    for g in ar["gates"]:
        if g["name"] == name:
            return g
    return None


def pgrep_f(marker):
    """按命令行关键词找进程，返回 pid 列表。"""
    try:
        r = subprocess.run(["pgrep", "-f", marker], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        return []
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def descendants(pid):
    out, stack = [], [pid]
    while stack:
        p = stack.pop()
        try:
            r = subprocess.run(["pgrep", "-P", str(p)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            continue
        for k in [int(x) for x in r.stdout.split() if x.strip().isdigit()]:
            out.append(k)
            stack.append(k)
    return out


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        # 已退出但尚未被回收的僵尸也算死
        r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        st = r.stdout.decode("utf-8", "replace").strip()
        return bool(st) and not st.startswith("Z")
    except Exception:
        return True


def wait_gone(pids, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not any(alive(p) for p in pids):
            return True
        time.sleep(0.1)
    return not any(alive(p) for p in pids)


def temp_dirs():
    base = tempfile.gettempdir()
    try:
        return {n for n in os.listdir(base) if n.startswith("coding-drill-") and not n.startswith("coding-drill-selftest-")}
    except OSError:
        return set()


def build_drill(root, slug, lang, starter, reference, mutants, time_limit_ms=1000, problem_md=PROBLEM_MD, tests=TESTS,
                title="有序数组里第一个不小于目标的位置", difficulty=2):
    d = os.path.join(root, "drills", slug)
    ext = {"python": ".py", "javascript": ".js", "java": ".java"}[lang]
    write(os.path.join(d, "problem.md"), problem_md)
    write(os.path.join(d, "meta.json"), json.dumps({
        "slug": slug, "title": title, "topic": "二分查找", "language": lang,
        "difficulty": difficulty, "difficultyReason": "一个循环加一个需要推理的边界（目标恰好等于某元素）",
        "timeLimitMs": time_limit_ms, "compareMode": "trim", "createdAt": "2026-08-27", "mode": "learner",
    }, ensure_ascii=False, indent=2))
    if lang == "java":
        write(os.path.join(d, "starter", "Main.java"), starter)
        write(os.path.join(d, "Main.java"), starter)
        write(os.path.join(d, ".hidden", "reference", "Main.java"), reference)
        for i, src in enumerate(mutants, 1):
            write(os.path.join(d, ".hidden", "mutants", "m%d" % i, "Main.java"), src)
        files = ["m%d" % i for i in range(1, len(mutants) + 1)]
    else:
        write(os.path.join(d, "starter" + ext), starter)
        write(os.path.join(d, "solution" + ext), starter)
        write(os.path.join(d, ".hidden", "reference" + ext), reference)
        for i, src in enumerate(mutants, 1):
            write(os.path.join(d, ".hidden", "mutants", "m%d%s" % (i, ext)), src)
        files = ["m%d%s" % (i, ext) for i in range(1, len(mutants) + 1)]
    write(os.path.join(d, ".hidden", "tests.json"), json.dumps(tests, ensure_ascii=False, indent=2))
    write(os.path.join(d, ".hidden", "mutants.json"), json.dumps({"mutants": [
        {"file": files[0], "misconception": "用 > 代替 >=，恰好等于目标的元素被跳过"},
        {"file": files[1], "misconception": "找不到时返回 -1 而不是 n"},
    ]}, ensure_ascii=False, indent=2))
    return d


def full_flow(root, slug, lang, starter, reference, mutants, m1, constant, timeout_src, syntax_src, wrong_src):
    """author → judge（正确 / 错解 / 常量 / 超时 / 语法错误 / 全错）→ export，含错题本规则与导出闸门。"""
    d = build_drill(root, slug, lang, starter, reference, mutants)
    ext = {"python": ".py", "javascript": ".js"}[lang]
    sol = os.path.join(d, "solution" + ext)
    tests_path = os.path.join(d, ".hidden", "tests.json")
    ref_path = os.path.join(d, ".hidden", "reference" + ext)
    problem_path = os.path.join(d, "problem.md")
    meta_path = os.path.join(d, "meta.json")
    mis_path = os.path.join(root, "drills", "misconceptions.md")
    wrong = os.path.join(root, "wrong-" + slug + ext)
    write(wrong, wrong_src)

    # export 在 author 之前必须拒绝
    rc, out, err = run("export", d)
    check(rc == 2, "%s：未 author 就 export 应退出 2，实际 %d\n%s%s" % (lang, rc, out, err))

    # author：回填 + 全部闸门
    rc, out, err = run("author", d)
    check(rc == 0, "%s：author 应通过，rc=%d\n%s%s" % (lang, rc, out, err))
    tests = load(tests_path)
    exp = [c["expected"] for c in tests["cases"]]
    check(exp == ["2", "5", "3", "7", "0"], "%s：回填期望输出不对：%r" % (lang, exp))
    ar = load(os.path.join(d, ".hidden", "author-report.json"))
    check(ar["ok"] and ar["errorCount"] == 0, "%s：author-report 应无 ERROR" % lang)
    for name in ("constant", "empty", "echo", "starter"):
        check(ar["baselines"][name]["score"] == 0, "%s：基线 %s 应 0 分" % (lang, name))
    for name in ("first_token", "last_token", "first_line", "last_line"):
        check(name in ar["baselines"] and "unproven" not in ar["baselines"][name], "%s：应跑过 token/行基线 %s 且已证明" % (lang, name))
    # c4 的 n=7 恰等于期望 7：first_token / first_line 各拿 2 分 → WARN（不到一半），last_* 0 分
    check(ar["baselines"]["first_token"]["score"] == 2.0 and ar["baselines"]["first_token"]["passed"] == ["c4"],
          "%s：first_token 基线应恰过 c4 拿 2.0：%r" % (lang, ar["baselines"]["first_token"]))
    check(gate(ar, "baseline_first_token")["level"] == "WARN" and "c4" in gate(ar, "baseline_first_token")["message"],
          "%s：first_token 拿 2 分应是 WARN 并附用例 id" % lang)
    check(ar["baselines"]["last_token"]["score"] == 0 and gate(ar, "baseline_last_token")["level"] == "OK", "%s：last_token 应 0 分 OK" % lang)
    # c5 期望 0：print(0) 能过 → constant_guessable WARN
    cg = gate(ar, "constant_guessable")
    check(cg and cg["level"] == "WARN" and "打印 0 " in cg["message"] and "c5" in cg["message"] and "empty" in cg["message"],
          "%s：print(0) 过 c5 应触发 constant_guessable WARN：%r" % (lang, cg))
    check(ar["baselines"]["const:0"]["score"] == 3.0 and ar["baselines"]["const:-1"]["score"] == 0 and ar["baselines"]["const:1"]["score"] == 0,
          "%s：常量基线得分不对：%r" % (lang, {k: v for k, v in ar["baselines"].items() if k.startswith("const:")}))
    check(gate(ar, "difficulty")["level"] == "OK", "%s：difficulty=2 应 OK" % lang)
    check(all(c["verdict"] == "ok" for c in ar["reference"]["cases"]), "%s：参考解结果标签应统一为 ok：%r" % (lang, ar["reference"]["cases"]))
    check(set(ar["files"]) == {"tests.json", "reference", "starter", "mutant:m1" + ext, "mutant:m2" + ext} and all(ar["files"].values()),
          "%s：author-report 应记录 tests/参考解/骨架/错解的 sha256：%r" % (lang, ar.get("files")))
    check([m["status"] for m in ar["mutants"]] == ["ok", "ok"], "%s：两个错解都应是部分分：%r" % (lang, ar["mutants"]))
    md = read(os.path.join(d, "author-report.md"))
    for c in TESTS["cases"]:
        check(c["input"] not in md, "%s：author-report.md 泄露了用例输入" % lang)
    check("通过" in md and "| c1 | sample | ok |" in md and "accepted" not in md, "%s：author-report.md 应写明通过且参考解标签为 ok" % lang)
    check("| first_token | 2.0 | c4 |" in md and "| const:0 | 3.0 | c5 |" in md, "%s：author-report.md 基线表应列出新基线\n%s" % (lang, md))

    # author 不覆盖已有 expected；--refill 才覆盖
    tests["cases"][1]["expected"] = "999"
    write(tests_path, json.dumps(tests, ensure_ascii=False, indent=2))
    rc, out, err = run("author", d)
    check(rc == 1 and "solution_fail" in out, "%s：手写 expected 不一致应报 solution_fail 且退出 1，rc=%d\n%s" % (lang, rc, out))
    check(load(tests_path)["cases"][1]["expected"] == "999", "%s：author 不该覆盖已有 expected" % lang)
    rc, out, err = run("export", d)
    check(rc == 2, "%s：author 有 ERROR 时 export 应拒绝，rc=%d" % (lang, rc))
    rc, out, err = run("author", d, "--refill")
    check(rc == 0, "%s：--refill 后应通过，rc=%d\n%s%s" % (lang, rc, out, err))
    check(load(tests_path)["cases"][1]["expected"] == "5", "%s：--refill 应覆盖为实跑值" % lang)
    check("--refill" in read(os.path.join(d, "author-report.md")), "%s：报告应标明 --refill" % lang)

    # 静态闸门：样例分值非 0 → ERROR sample_count
    bad = load(tests_path)
    bad["cases"][0]["score"] = 2
    write(tests_path, json.dumps(bad, ensure_ascii=False, indent=2))
    rc, out, err = run("author", d)
    check(rc == 1 and "sample_count" in out, "%s：样例分值非 0 应报 sample_count，rc=%d\n%s" % (lang, rc, out))
    bad["cases"][0]["score"] = 0
    bad["cases"][4]["job"] = "boundary"
    write(tests_path, json.dumps(bad, ensure_ascii=False, indent=2))
    rc, out, err = run("author", d)
    check(rc == 1 and "hidden_jobs" in out, "%s：隐藏用例职责重复应报 hidden_jobs，rc=%d\n%s" % (lang, rc, out))
    bad["cases"][4]["job"] = "saturated"
    bad["cases"][4]["catches"] = ""
    write(tests_path, json.dumps(bad, ensure_ascii=False, indent=2))
    rc, out, err = run("author", d)
    check(rc == 1 and "catches_missing" in out, "%s：隐藏用例 catches 为空应报 catches_missing，rc=%d\n%s" % (lang, rc, out))
    bad["cases"][4]["catches"] = "边界测试"
    bad["cases"][4]["id"] = "c4"
    write(tests_path, json.dumps(bad, ensure_ascii=False, indent=2))
    rc, out, err = run("author", d)
    check(rc == 1 and "dup_id" in out and "catches_generic" in out, "%s：id 重复应报 dup_id、笼统 catches 应报 catches_generic，rc=%d\n%s" % (lang, rc, out))
    bad["cases"][4]["id"] = "c5"
    bad["cases"][4]["catches"] = TESTS["cases"][4]["catches"]
    bad["cases"].pop()
    write(tests_path, json.dumps(bad, ensure_ascii=False, indent=2))
    rc, out, err = run("author", d)
    check(rc == 1 and "hidden_count" in out, "%s：隐藏用例 3 条应报 hidden_count，rc=%d\n%s" % (lang, rc, out))
    bad = load(tests_path)
    bad["cases"].append(dict(TESTS["cases"][4]))
    write(tests_path, json.dumps(bad, ensure_ascii=False, indent=2))

    # 静态闸门：difficulty 不是 1/2/3 的整数 → ERROR difficulty
    meta = load(meta_path)
    for value in ("中等", "2", 4, 2.5, True):
        meta["difficulty"] = value
        write(meta_path, json.dumps(meta, ensure_ascii=False, indent=2))
        rc, out, err = run("author", d)
        check(rc == 1 and "[ERROR] difficulty" in out, "%s：difficulty=%r 应报 ERROR difficulty，rc=%d\n%s" % (lang, value, rc, out))
    meta["difficulty"] = 2
    write(meta_path, json.dumps(meta, ensure_ascii=False, indent=2))

    # tests.json 校验：catches 为数字 / job 非字符串 / score 为 NaN / timeLimitMs 越界 → 退出 2（author 与 judge 都拒）
    for label, mutate in (
        ("catches 为数字", lambda t, m: t["cases"][1].__setitem__("catches", 5)),
        ("job 为数字", lambda t, m: t["cases"][1].__setitem__("job", 7)),
        ("score 为 NaN", lambda t, m: t["cases"][1].__setitem__("score", float("nan"))),
        ("score 为字符串", lambda t, m: t["cases"][1].__setitem__("score", "2")),
        ("timeLimitMs 为 1e12", lambda t, m: m.__setitem__("timeLimitMs", 1e12)),
        ("timeLimitMs 为 50", lambda t, m: m.__setitem__("timeLimitMs", 50)),
        ("timeLimitMs 为字符串", lambda t, m: m.__setitem__("timeLimitMs", "2000")),
    ):
        t = load(tests_path)
        m = load(meta_path)
        mutate(t, m)
        write(tests_path, json.dumps(t, ensure_ascii=False, indent=2, allow_nan=True))
        write(meta_path, json.dumps(m, ensure_ascii=False, indent=2, allow_nan=True))
        for cmd in ("author", "judge"):
            rc, out, err = run(cmd, d)
            check(rc == 2 and err.startswith("错误：") and "Traceback" not in err, "%s：%s 时 %s 应退出 2 并给中文提示，rc=%d\n%s%s" % (lang, label, cmd, rc, out, err))
        write(tests_path, json.dumps(bad, ensure_ascii=False, indent=2))
        write(meta_path, json.dumps(meta, ensure_ascii=False, indent=2))

    # tests.json 带 UTF-8 BOM 也能读；恢复后 author 应通过并提示错解只有 2 个
    write_bytes(tests_path, b"\xef\xbb\xbf" + json.dumps(bad, ensure_ascii=False, indent=2).encode("utf-8"))
    rc, out, err = run("author", d)
    check(rc == 0 and "mutants_count" in out, "%s：恢复（带 BOM）后 author 应通过并提示错解只有 2 个\n%s%s" % (lang, out, err))
    bad = load(tests_path)  # 之后复原都用这份已回填的
    md = read(os.path.join(d, "author-report.md"))
    check("| c2 | typical | ok |" in md and "accepted" not in md, "%s：已有 expected 的用例标签也应是 ok\n%s" % (lang, md))

    # judge：起步骨架原样 → 0 分，退出 1；骨架原样不记错题本
    rc, out, err = run("judge", d)
    check(rc == 1, "%s：骨架原样判题应退出 1，rc=%d\n%s%s" % (lang, rc, out, err))
    rep = load(os.path.join(d, "report.json"))
    check(rep["score"] == 0 and rep["verdict"] == "wrong_answer", "%s：骨架应 0 分 wrong_answer：%r" % (lang, (rep["score"], rep["verdict"])))
    check(not os.path.isabs(rep["file"]) and ".." not in rep["file"], "%s：report.json 的 file 应是工作区相对路径（报告会被截图/入库，不能带本机绝对路径）：%r" % (lang, rep["file"]))
    revealed_hidden = [c["id"] for c in rep["cases"] if c["revealed"] and not c["isSample"]]
    check(revealed_hidden == ["c2"], "%s：默认只揭开第一条未通过隐藏用例，实际 %r" % (lang, revealed_hidden))
    for c in rep["cases"]:
        if not c["revealed"]:
            check("input" not in c and "expected" not in c, "%s：未揭开的用例不该带输入输出" % lang)
    check("这条用例抓的是" in out, "%s：终端应显示 catches" % lang)
    html_text = read(os.path.join(d, "report.html"))
    check("prefers-color-scheme" in html_text and "http" not in html_text.lower().replace("http-equiv", ""),
          "%s：report.html 应自包含且支持深浅色" % lang)
    check("有序数组里第一个不小于目标的位置" in html_text and "0.0" in html_text, "%s：report.html 应含标题与得分" % lang)
    check(TESTS["cases"][2]["input"] not in html_text, "%s：report.html 不该泄露未揭开的隐藏用例输入" % lang)
    check(TESTS["cases"][1]["input"] in html_text, "%s：report.html 应显示被揭开的那条用例" % lang)
    mis_count = lambda: read(mis_path).count(" · %s · " % slug) if os.path.isfile(mis_path) else 0
    check(mis_count() == 0 and "无新增" in out and rep["newMisconceptions"] == [],
          "%s：起步骨架原样提交不该记错题本\n%s" % (lang, out))

    # 全错的作答（读了输入、不是骨架）→ 4 条 wrong_answer 记入错题本
    rc, out, err = run("judge", d, "--file", wrong)
    mis = read(mis_path)
    check(mis.count(" · %s · " % slug) == 4 and "错题本新增 4 条" in out, "%s：全错作答应新增 4 条，实际：\n%s\n%s" % (lang, mis, out))

    # 再判一次：错题本不重复
    rc, out, err = run("judge", d, "--file", wrong)
    check(read(mis_path).count(" · %s · " % slug) == 4, "%s：同题同条不该重复追加" % lang)
    check("无新增" in out, "%s：第二次判题应提示错题本无新增" % lang)

    # --reveal-all
    rc, out, err = run("judge", d, "--reveal-all")
    rep = load(os.path.join(d, "report.json"))
    check(all(c["revealed"] for c in rep["cases"]), "%s：--reveal-all 应全部揭开" % lang)

    # 正确解 → 10 分，退出 0
    write(sol, reference)
    rc, out, err = run("judge", d)
    check(rc == 0, "%s：正确解应退出 0，rc=%d\n%s%s" % (lang, rc, out, err))
    rep = load(os.path.join(d, "report.json"))
    check(rep["score"] == 10.0 and rep["verdict"] == "accepted", "%s：正确解应 10 分 accepted：%r" % (lang, (rep["score"], rep["verdict"])))
    check(rep["newMisconceptions"] == [], "%s：正确解不该新增错题本" % lang)

    # 错解 m1（> 代替 >=）→ 部分分：过 c2(2) c4(2) c5(3) = 7.0，挂 c1 c3
    write(sol, m1)
    rc, out, err = run("judge", d)
    rep = load(os.path.join(d, "report.json"))
    check(rc == 1 and rep["verdict"] == "partial" and rep["score"] == 7.0, "%s：错解应 7.0 partial：%r" % (lang, (rc, rep["score"], rep["verdict"])))
    check([c["id"] for c in rep["cases"] if not c["passed"]] == ["c1", "c3"], "%s：错解应挂 c1 c3" % lang)
    check([c["id"] for c in rep["cases"] if c["revealed"] and not c["isSample"]] == ["c3"], "%s：应只揭开 c3" % lang)

    # 常量解 → 0 分
    write(sol, constant)
    rc, out, err = run("judge", d)
    rep = load(os.path.join(d, "report.json"))
    check(rep["score"] == 0.0, "%s：常量解应 0 分：%r" % (lang, rep["score"]))

    # 超时程序 → time_limit_exceeded；TLE 不记错题本
    mis_before = read(mis_path)
    write(sol, timeout_src)
    rc, out, err = run("judge", d)
    rep = load(os.path.join(d, "report.json"))
    check(rep["verdict"] == "time_limit_exceeded" and rep["score"] == 0.0, "%s：死循环应判 time_limit_exceeded：%r" % (lang, rep["verdict"]))
    check(all(c["verdict"] == "time_limit_exceeded" for c in rep["cases"]), "%s：每条用例都应超时" % lang)
    check(all(c["timeMs"] < 4000 for c in rep["cases"]), "%s：超时应被及时杀掉：%r" % (lang, [c["timeMs"] for c in rep["cases"]]))
    check(rep["newMisconceptions"] == [] and read(mis_path) == mis_before, "%s：TLE 的用例不该记错题本" % lang)

    # 语法错误 → runtime_error 或 compile_error；不记错题本
    write(sol, syntax_src)
    rc, out, err = run("judge", d)
    rep = load(os.path.join(d, "report.json"))
    check(rep["verdict"] in ("runtime_error", "compile_error") and rep["score"] == 0.0, "%s：语法错误应判 runtime_error/compile_error：%r" % (lang, rep["verdict"]))
    check(rep["newMisconceptions"] == [] and read(mis_path) == mis_before, "%s：语法错误不该记错题本" % lang)

    # --file 指定文件
    alt = os.path.join(root, "alt" + ext)
    write(alt, reference)
    rc, out, err = run("judge", d, "--file", alt)
    check(rc == 0 and load(os.path.join(d, "report.json"))["score"] == 10.0, "%s：--file 应生效" % lang)

    # stdout 不是 UTF-8（PYTHONIOENCODING=ascii）也不崩
    rc, out, err = run("judge", d, "--file", alt, env={"PYTHONIOENCODING": "ascii"})
    check(rc == 0 and "Traceback" not in err and "UnicodeEncodeError" not in err, "%s：PYTHONIOENCODING=ascii 下不该崩，rc=%d\n%s" % (lang, rc, err))

    # GBK 编码的作答文件 → 退出 2 并提示不是 UTF-8
    gbk = os.path.join(root, "gbk-" + slug + ext)
    write_bytes(gbk, ("print('中文')  # 注释\n" if lang == "python" else "console.log('中文'); // 注释\n").encode("gbk"))
    rc, out, err = run("judge", d, "--file", gbk)
    check(rc == 2 and "UTF-8" in err and "Traceback" not in err, "%s：GBK 作答文件应退出 2 并提示编码，rc=%d\n%s" % (lang, rc, err))

    # 错题本路径是目录 → 退出 2 而不是 traceback
    shutil.move(mis_path, mis_path + ".bak")
    os.makedirs(mis_path)
    rc, out, err = run("judge", d, "--file", wrong)
    check(rc == 2 and err.startswith("错误：") and "Traceback" not in err, "%s：misconceptions.md 是目录时应退出 2，rc=%d\n%s" % (lang, rc, err))
    os.rmdir(mis_path)
    shutil.move(mis_path + ".bak", mis_path)

    # catches 含换行 → 折成单行写入且去重；id 含 | 与换行 → report.md 表格不被撑坏
    t = load(tests_path)
    t["cases"][1]["catches"] = "行一\n行二"
    t["cases"][2]["id"] = "c|3\nx"
    write(tests_path, json.dumps(t, ensure_ascii=False, indent=2))
    for _ in range(3):
        rc, out, err = run("judge", d, "--file", wrong)
    mis = read(mis_path)
    check(mis.count(" · %s · 行一 行二" % slug) == 1 and "行一\n" not in mis, "%s：多行 catches 应折成单行并去重：\n%s" % (lang, mis))
    check("无新增" in out, "%s：多行 catches 第三次判题不该再新增\n%s" % (lang, out))
    md = read(os.path.join(d, "report.md"))
    rows = [l for l in md.split("\n") if l.startswith("| c")]
    check(len(rows) == 5 and all(l.count("|") - l.count("\\|") == 6 for l in rows), "%s：report.md 用例表每行应恰 5 格：%r" % (lang, rows))
    check("| c\\|3 x |" in md, "%s：id 里的竖线与换行应转义\n%s" % (lang, md))
    write(tests_path, json.dumps(bad, ensure_ascii=False, indent=2))

    # run：显示全部输入输出
    rc, out, err = run("run", d, os.path.join(d, ".hidden", "mutants", "m2" + ext))
    check(rc == 1 and "1 2 3 4 5 6 7" in out and "2 4 6 8 10 12" in out and "-1" in out and "8.0" in out,
          "%s：run 应显示全部输入输出\n%s" % (lang, out))

    # 重新 author（tests.json 复原后刷新校验值），然后 export
    rc, out, err = run("author", d)
    check(rc == 0, "%s：复原后 author 应通过，rc=%d\n%s%s" % (lang, rc, out, err))
    rc, out, err = run("export", d)
    check(rc == 0, "%s：export 应成功，rc=%d\n%s%s" % (lang, rc, out, err))
    pack = load(os.path.join(d, "export.json"))
    check(pack["coding"]["defaultLanguage"] == lang and pack["coding"]["totalScore"] == 10, "%s：export 语言/总分不对" % lang)
    check(len(pack["coding"]["testCases"]) == 5 and pack["coding"]["testCases"][0]["isSample"] is True, "%s：export 用例不对" % lang)
    check([c["expectedOutput"] for c in pack["coding"]["testCases"]] == ["2", "5", "3", "7", "0"], "%s：export 期望输出不对" % lang)
    check("<h1>" in pack["stem"] and "<pre><code>" in pack["stem"] and "<ul>" in pack["stem"] and "<strong>" in pack["stem"],
          "%s：stem 应转成 HTML（标题/代码块/列表/加粗）" % lang)
    check(pack["coding"]["solutionCode"][lang] == reference and pack["coding"]["starterCode"][lang] == starter, "%s：export 代码不对" % lang)
    check(pack["authoring"]["caseIntent"][1].startswith("typical: ") and len(pack["authoring"]["mutants"]) == 2, "%s：authoring 字段不对" % lang)
    check(pack["authoring"]["difficultyReason"] and pack["difficulty"] == 2, "%s：难度字段不对" % lang)

    # export --out
    out_path = os.path.join(root, slug + ".json")
    rc, out, err = run("export", d, "--out", out_path)
    check(rc == 0 and os.path.isfile(out_path), "%s：export --out 应写到指定文件" % lang)

    # export 拒绝：difficulty 非法（meta 不在哈希里，直接查）
    meta["difficulty"] = "中等"
    write(meta_path, json.dumps(meta, ensure_ascii=False, indent=2))
    rc, out, err = run("export", d)
    check(rc == 2 and "difficulty" in err, "%s：difficulty 非法应拒绝导出，rc=%d\n%s" % (lang, rc, err))
    meta["difficulty"] = 2
    write(meta_path, json.dumps(meta, ensure_ascii=False, indent=2))

    # export 拒绝：problem.md 含 <待回填>；样例输入/输出没逐字出现在题面
    write(problem_path, PROBLEM_MD.replace("```\n2\n```", "```\n<待回填>\n```"))
    rc, out, err = run("export", d)
    check(rc == 2 and "待回填" in err, "%s：problem.md 含 <待回填> 应拒绝导出，rc=%d\n%s" % (lang, rc, err))
    write(problem_path, PROBLEM_MD.replace("1 3 5 7 9", "1 3 5 7 8"))
    rc, out, err = run("export", d)
    check(rc == 2 and "stem_sample_mismatch" in err and "输入" in err, "%s：题面示例输入与样例不一致应拒绝导出，rc=%d\n%s" % (lang, rc, err))
    write(problem_path, PROBLEM_MD.replace("```\n2\n```", "```\n3\n```"))
    rc, out, err = run("export", d)
    check(rc == 2 and "stem_sample_mismatch" in err and "期望输出" in err, "%s：题面示例输出与样例不一致应拒绝导出，rc=%d\n%s" % (lang, rc, err))
    write(problem_path, PROBLEM_MD)
    rc, out, err = run("export", d)
    check(rc == 0, "%s：题面复原后 export 应成功，rc=%d\n%s" % (lang, rc, err))

    # export 拒绝：验证后改参考解 / 起步骨架 / 错解；改回原样又能导出
    for label, path, original in (("参考解", ref_path, reference), ("起步骨架", os.path.join(d, "starter" + ext), starter),
                                  ("错解", os.path.join(d, ".hidden", "mutants", "m1" + ext), mutants[0])):
        write(path, ("print(999)\n" if lang == "python" else "console.log(999);\n"))
        rc, out, err = run("export", d)
        check(rc == 2 and "author" in err and "改动" in err, "%s：验证后改%s应拒绝导出并提示重跑 author，rc=%d\n%s" % (lang, label, rc, err))
        check(not os.path.isfile(os.path.join(d, "export.json")) or load(os.path.join(d, "export.json"))["coding"]["solutionCode"][lang] == reference,
              "%s：拒绝导出时不该写出被改过的参考解" % lang)
        write(path, original)
        rc, out, err = run("export", d)
        check(rc == 0, "%s：%s改回原样后应能导出，rc=%d\n%s" % (lang, label, rc, err))

    # 验证后改动 tests.json → 拒绝导出
    t2 = load(tests_path)
    t2["cases"][4]["score"] = 4
    write(tests_path, json.dumps(t2, ensure_ascii=False, indent=2))
    rc, out, err = run("export", d)
    check(rc == 2, "%s：tests.json 在验证后被改动应拒绝导出，rc=%d" % (lang, rc))


def max_flow(root):
    """求最大值题：答案总是输入的最后一个 token → last_token 基线拿 8 分 → ERROR。"""
    d = build_drill(root, "max-01", "python", MAX_STARTER, MAX_REFERENCE, [MAX_M1, MAX_M2],
                    problem_md=MAX_PROBLEM_MD, tests=MAX_TESTS, title="最大值")
    rc, out, err = run("author", d)
    check(rc == 1 and "[ERROR] baseline_last_token" in out, "求最大值：last_token 基线应报 ERROR，rc=%d\n%s%s" % (rc, out, err))
    ar = load(os.path.join(d, ".hidden", "author-report.json"))
    lt = ar["baselines"]["last_token"]
    check(lt["score"] == 8.0 and lt["passed"] == ["c2", "c3", "c5"], "求最大值：last_token 应过 c2 c3 c5 拿 8.0：%r" % lt)
    g = gate(ar, "baseline_last_token")
    check(g["level"] == "ERROR" and "c2 c3 c5" in g["message"], "求最大值：ERROR 信息应附通过的用例 id：%r" % g)
    # first_token（n）从不等于答案 → OK；last_line 只过单元素那条 c5（3 分，不到一半）→ WARN
    check(gate(ar, "baseline_first_token")["level"] == "OK" and gate(ar, "baseline_last_line")["level"] == "WARN"
          and ar["baselines"]["last_line"]["passed"] == ["c5"],
          "求最大值：first_token 应 OK、last_line 应 WARN（只过 c5）：%r" % [gate(ar, n) for n in ("baseline_first_token", "baseline_last_line")])
    rc, out, err = run("export", d)
    check(rc == 2, "求最大值：author 未通过时 export 应拒绝，rc=%d" % rc)


def attack_flow(root, node_ok):
    """攻击回归：输出炸弹、逃逸子进程、读父进程 cwd 偷题、Ctrl-C / SIGTERM 清理。"""
    d = build_drill(root, "attack-py", "python", PY_STARTER, PY_REFERENCE, [PY_M1, PY_M2], time_limit_ms=1000)
    rc, out, err = run("author", d)
    check(rc == 0, "攻击：author 应通过，rc=%d\n%s%s" % (rc, out, err))
    notes = []

    # 1. 输出炸弹：每条用例无限打印 1MB 块 → output_limit_exceeded，峰值内存 < 100MB，几秒内返回
    bomb = os.path.join(root, "bomb.py")
    write(bomb, PY_OUTPUT_BOMB)
    wrapper = ("import resource, subprocess, sys, time\n"
               "t = time.time()\n"
               "r = subprocess.run(sys.argv[1:], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
               "ru = resource.getrusage(resource.RUSAGE_CHILDREN)\n"
               "print(r.returncode, ru.ru_maxrss, time.time() - t)\n")
    r = subprocess.run([PY, "-c", wrapper, PY, JUDGE, "judge", d, "--file", bomb], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    parts = r.stdout.decode("utf-8", "replace").split()
    check(len(parts) == 3, "攻击：内存包装器没拿到结果：%s %s" % (r.stdout, r.stderr))
    rc, maxrss, elapsed = int(parts[0]), int(parts[1]), float(parts[2])
    peak_mb = maxrss / (1024.0 * 1024.0) if sys.platform == "darwin" else maxrss / 1024.0
    rep = load(os.path.join(d, "report.json"))
    check(rep["verdict"] == "output_limit_exceeded" and all(c["verdict"] == "output_limit_exceeded" for c in rep["cases"]) and rep["score"] == 0.0,
          "攻击：输出炸弹应判 output_limit_exceeded：%r" % [c["verdict"] for c in rep["cases"]])
    check(rc == 1, "攻击：输出炸弹判题应退出 1，rc=%d" % rc)
    check(peak_mb < 100, "攻击：输出炸弹时 judge.py 峰值内存应 < 100MB，实际 %.0fMB" % peak_mb)
    check(elapsed < 10, "攻击：输出炸弹 5 条用例应几秒内返回，实际 %.1f 秒" % elapsed)
    check(all(c["timeMs"] < 1500 for c in rep["cases"]), "攻击：超出输出上限应立即终止：%r" % [c["timeMs"] for c in rep["cases"]])
    check(rep["newMisconceptions"] == [], "攻击：输出炸弹不该记错题本")
    notes.append("输出炸弹峰值 %.0fMB · %.1f 秒" % (peak_mb, elapsed))

    # 2. setsid / detached 逃逸子进程：超时后一并被杀，不残留；每条用例不再多等 5 秒；静态扫描先拦、--allow-io 放行
    escapes = [("python", PY_ESCAPE, ".py", d)]
    if node_ok:
        dj = build_drill(root, "attack-js", "javascript", JS_STARTER, JS_REFERENCE, [JS_M1, JS_M2], time_limit_ms=1000)
        rc, out, err = run("author", dj)
        check(rc == 0, "攻击：JS author 应通过，rc=%d\n%s%s" % (rc, out, err))
        escapes.append(("javascript", JS_ESCAPE, ".js", dj))
    for lang, src_tpl, ext, dd in escapes:
        marker = "coding-drill-selftest-escape-" + uuid.uuid4().hex
        esc = os.path.join(root, "escape-" + lang + ext)
        write(esc, src_tpl % marker)
        rc, out, err = run("judge", dd, "--file", esc)
        check(rc == 2 and "--allow-io" in err and ("os.fork" in err or "child_process" in err), "攻击：%s 逃逸程序应被静态扫描拦下，rc=%d\n%s" % (lang, rc, err))
        t0 = time.time()
        rc, out, err = run("judge", dd, "--file", esc, "--allow-io")
        elapsed = time.time() - t0
        leftovers = pgrep_f(marker)
        gone = wait_gone(leftovers, 2)
        for pid in leftovers:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        rep = load(os.path.join(dd, "report.json"))
        check(rep["cases"][0].get("actual") == "spawned", "攻击：%s 逃逸程序应先打印 spawned（证明子进程已派生）：%r" % (lang, rep["cases"][0]))
        check(rep["verdict"] == "time_limit_exceeded", "攻击：%s 逃逸程序应判 TLE：%r" % (lang, rep["verdict"]))
        check(gone, "攻击：%s 逃逸的子进程在超时后应被杀掉，仍活着：%r" % (lang, leftovers))
        check(all(c["timeMs"] < 3000 for c in rep["cases"]), "攻击：%s 逃逸子进程不该拖慢用例（每条应 < 3 秒）：%r" % (lang, [c["timeMs"] for c in rep["cases"]]))
        check(elapsed < 15, "攻击：%s 逃逸程序整题应在 15 秒内判完，实际 %.1f 秒" % (lang, elapsed))
        notes.append("%s 逃逸子进程已清理（整题 %.1f 秒）" % (lang, elapsed))

    # 3. 通过父进程 cwd 找 .hidden/tests.json：静态扫描拒跑；--allow-io 后因 chdir 隔离只能看到临时目录 → 0 分
    peek = os.path.join(root, "peek.py")
    write(peek, PY_PEEK)
    rc, out, err = run("judge", d, "--file", peek, cwd=root)
    check(rc == 2 and "--allow-io" in err and "getppid" in err and "lsof" in err and "subprocess" in err and "第 " in err,
          "攻击：偷题程序应被静态扫描拦下并列出命中行，rc=%d\n%s" % (rc, err))
    check(not os.path.isfile(os.path.join(d, "report.json")) or load(os.path.join(d, "report.json"))["file"] != peek, "攻击：被拦下的作答不该写报告")
    rc, out, err = run("judge", d, "--file", peek, "--allow-io", cwd=root)
    rep = load(os.path.join(d, "report.json"))
    actual = rep["cases"][0].get("actual", "")
    check(rep["score"] == 0.0 and rep["verdict"] == "wrong_answer", "攻击：偷题程序应 0 分 wrong_answer：%r\n%s%s" % ((rep["score"], rep["verdict"]), out, err))
    check(actual.startswith("FOUND ") and root not in actual, "攻击：偷题程序看到的父进程 cwd 不该是工作区：%r" % actual)
    check("--allow-io" in out, "攻击：--allow-io 时应提示已跳过扫描\n%s" % out)
    notes.append("偷题程序看到的 cwd：%s" % actual[6:])

    # 4. Ctrl-C / SIGTERM：正在跑的作答程序被杀，临时目录清理
    tle = os.path.join(root, "tle.py")
    write(tle, PY_TIMEOUT)
    long_drill = build_drill(root, "attack-long", "python", PY_STARTER, PY_REFERENCE, [PY_M1, PY_M2], time_limit_ms=20000)
    rc, out, err = run("author", long_drill)
    check(rc == 0, "攻击：长时限题包 author 应通过，rc=%d\n%s%s" % (rc, out, err))
    for sig, name in ((signal.SIGINT, "Ctrl-C"), (signal.SIGTERM, "SIGTERM")):
        before = temp_dirs()
        proc = subprocess.Popen([PY, JUDGE, "judge", long_drill, "--file", tle], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        kids = []
        deadline = time.time() + 10
        while time.time() < deadline and not kids:
            time.sleep(0.1)
            kids = [k for k in descendants(proc.pid) if k != proc.pid]
        check(kids, "攻击：%s 测试没等到作答程序启动" % name)
        time.sleep(0.3)
        kids = [k for k in descendants(proc.pid) if k != proc.pid] or kids
        proc.send_signal(sig)
        try:
            out, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise Failed("攻击：%s 后 judge.py 15 秒内没退出" % name)
        gone = wait_gone(kids, 3)
        for k in kids:
            try:
                os.kill(k, signal.SIGKILL)
            except Exception:
                pass
        check(proc.returncode == 2 and "已中断" in err.decode("utf-8", "replace"), "攻击：%s 应退出 2 并提示已中断，rc=%r\n%s" % (name, proc.returncode, err.decode("utf-8", "replace")))
        check(gone, "攻击：%s 后作答程序应被杀掉，仍活着：%r" % (name, kids))
        leaked = temp_dirs() - before
        check(not leaked, "攻击：%s 后临时目录应清理，残留：%r" % (name, sorted(leaked)))
        notes.append("%s 已清理子进程与临时目录" % name)
    return notes


def java_flow(root, java_ok):
    d = build_drill(root, "lower-bound-java", "java", JAVA_STARTER, JAVA_REFERENCE, [JAVA_M1, JAVA_M2])
    if not java_ok:
        rc, out, err = run("author", d)
        check(rc == 2, "Java：无运行时时 author 应退出 2，rc=%d\n%s%s" % (rc, out, err))
        check("Java" in err and "运行时" in err, "Java：应说明缺运行时：%s" % err)
        rc, out, err = run("judge", d)
        check(rc == 2, "Java：无运行时时 judge 应退出 2，rc=%d" % rc)
        return "Java：本机无 javac/java，已验证优雅降级（author/judge 退出 2 并说明缺运行时）"
    rc, out, err = run("author", d)
    check(rc == 0, "Java：author 应通过，rc=%d\n%s%s" % (rc, out, err))
    ar = load(os.path.join(d, ".hidden", "author-report.json"))
    check([m["status"] for m in ar["mutants"]] == ["ok", "ok"], "Java：错解应是部分分：%r" % ar["mutants"])
    rc, out, err = run("judge", d)
    rep = load(os.path.join(d, "report.json"))
    check(rc == 1 and rep["score"] == 0.0 and rep["newMisconceptions"] == [], "Java：骨架应 0 分且不记错题本")
    write(os.path.join(d, "Main.java"), JAVA_WRONG)
    rc, out, err = run("judge", d)
    rep = load(os.path.join(d, "report.json"))
    check(rc == 1 and rep["score"] == 0.0 and len(rep["newMisconceptions"]) == 4, "Java：全错作答应记 4 条错题本")
    write(os.path.join(d, "Main.java"), "import java.nio.file.Files;\npublic class Main { public static void main(String[] a) { } }")
    rc, out, err = run("judge", d)
    check(rc == 2 and "java.nio.file" in err, "Java：静态扫描应拦下 java.nio.file，rc=%d\n%s" % (rc, err))
    write(os.path.join(d, "Main.java"), JAVA_REFERENCE)
    rc, out, err = run("judge", d)
    rep = load(os.path.join(d, "report.json"))
    check(rc == 0 and rep["score"] == 10.0, "Java：正确解应 10 分")
    write(os.path.join(d, "Main.java"), "public class Main { public static void main(String[] a) { int x = ; } }")
    rc, out, err = run("judge", d)
    rep = load(os.path.join(d, "report.json"))
    check(rep["verdict"] == "compile_error" and rep["score"] == 0.0 and rep["newMisconceptions"] == [], "Java：编译错误应判 compile_error 且不记错题本")
    for name in ("echo", "first_token", "last_token", "first_line", "last_line"):
        check("unproven" not in ar["baselines"][name], "Java：基线 %s 应能在本机 JDK 上编译运行" % name)
    rc, out, err = run("export", d)
    check(rc == 0, "Java：export 应成功")
    return "Java：本机有 JDK，已跑通 author/judge/export"


def main():
    root = tempfile.mkdtemp(prefix="coding-drill-selftest-")
    try:
        rc, out, err = run("doctor")
        check(rc == 0, "doctor 应退出 0，rc=%d\n%s%s" % (rc, out, err))
        check("[OK]" in out and "Python" in out, "doctor 应列出 Python\n%s" % out)
        rows = [line.split() for line in out.split("\n") if line.strip().startswith("[")]
        java_ok = any(r[0] == "[OK]" and r[1] == "Java" for r in rows)
        node_ok = any(r[0] == "[OK]" and r[1] == "JavaScript" for r in rows)
        if not java_ok:
            check("[警告]" in out and "Java" in out, "doctor 无 Java 时应给出警告\n%s" % out)
        print("doctor：Python 可用；JavaScript %s；Java %s" % ("可用" if node_ok else "缺失", "可用" if java_ok else "缺失（仅警告）"))

        full_flow(root, "lower-bound-py", "python", PY_STARTER, PY_REFERENCE, [PY_M1, PY_M2], PY_M1, PY_CONSTANT, PY_TIMEOUT, PY_SYNTAX, PY_WRONG)
        print("Python：author（含 token/行基线、常量基线、difficulty 闸门、文件校验值）→ judge（正确 10 分 / 错解 7.0 / 常量 0 / 超时 TLE / 语法错误 RE / 错题本规则 / GBK / 坏 tests.json）→ export（待回填 / 示例不一致 / 改参考解 拒绝）全部通过")

        check(node_ok, "本机没有 node，JavaScript 自测无法进行")
        full_flow(root, "lower-bound-js", "javascript", JS_STARTER, JS_REFERENCE, [JS_M1, JS_M2], JS_M1, JS_CONSTANT, JS_TIMEOUT, JS_SYNTAX, JS_WRONG)
        print("JavaScript：author → judge → export 全部通过")

        max_flow(root)
        print("求最大值题：last_token 基线拿 8.0 → ERROR baseline_last_token，export 拒绝")

        for note in attack_flow(root, node_ok):
            print("攻击回归：" + note)

        print(java_flow(root, java_ok))
        print("OK")
        return 0
    except Failed as e:
        print("FAIL：%s" % e)
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
