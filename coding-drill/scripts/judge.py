#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coding-drill 判题脚本（零依赖，Python 3.8+ 标准库，单文件）。

子命令：
  doctor                         查看本机可用运行时
  author <drill-dir> [--refill]  出题验证：回填期望输出、静态闸门、基线、错解
  judge  <drill-dir> [--file <path>] [--reveal-all]
                                 判学生作答，写 report.json / report.md / report.html
  run    <drill-dir> <program>   对任意程序跑全部用例（显示全部输入输出）
  export <drill-dir> [--out <file>]
                                 把通过 author 验证的题包导出为平台中立 JSON

退出码：0 通过 / 1 未通过（有 ERROR）/ 2 用法或环境错误。
格式契约见 references/problem-format.md；出题纪律见 references/authoring-rules.md。
"""

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

LANGS = ("python", "javascript", "java")
LANG_ALIASES = {"py": "python", "python3": "python", "js": "javascript", "node": "javascript"}
LANG_LABEL = {"python": "Python", "javascript": "JavaScript", "java": "Java"}
JOBS = ("sample", "typical", "boundary", "empty", "saturated", "order")

OUTPUT_CAP = 256 * 1024          # stdout / stderr 各截断到 256 KB
COMPILE_TIMEOUT_S = 15           # 编译超时
DEFAULT_TL_MS = 2000             # 默认每条用例时限
FULL_SCORE = 10                  # 一道题满分
IS_WINDOWS = os.name == "nt"

MAIN_FILE = {"python": "main.py", "javascript": "main.js", "java": "Main.java"}
EXT = {"python": ".py", "javascript": ".js", "java": ".java"}


# ---------------------------------------------------------------- 小工具

class UsageError(Exception):
    """用法或环境错误，退出码 2。"""


def norm_output(text):
    """trim 比对：\\r\\n 归一为 \\n，整段去首尾空白。"""
    if text is None:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise UsageError("文件不是 UTF-8 编码：%s（%s）" % (path, e))
    except FileNotFoundError:
        raise UsageError("找不到文件：%s" % path)
    except IsADirectoryError:
        raise UsageError("这是一个目录而不是文件：%s" % path)


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        raise UsageError("找不到文件：%s" % path)
    except IsADirectoryError:
        raise UsageError("这是一个目录而不是文件：%s" % path)
    except UnicodeDecodeError as e:
        raise UsageError("文件不是 UTF-8 编码：%s（%s）" % (path, e))
    except json.JSONDecodeError as e:
        raise UsageError("JSON 解析失败：%s（%s）" % (path, e))


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def today():
    return datetime.date.today().isoformat()


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def normalize_lang(value):
    v = str(value or "").strip().lower()
    v = LANG_ALIASES.get(v, v)
    if v not in LANGS:
        raise UsageError("meta.json 的 language 必须是 python / javascript / java，当前是：%r" % value)
    return v


def indent_block(text, prefix="      "):
    text = text if text != "" else "（空）"
    return "\n".join(prefix + line for line in text.split("\n"))


def fmt_score(x):
    return ("%.1f" % x)


# ---------------------------------------------------------------- 运行时探测

_RUNTIME_CACHE = {}


def _probe(argv, timeout=20):
    """跑一次 `xxx --version`，返回 (成功?, 第一行文字)。macOS 的 javac 占位命令能被 which 找到但退出码非 0。"""
    try:
        r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    text = (r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")).strip()
    first = text.split("\n")[0].strip() if text else ""
    return r.returncode == 0, first


def detect_runtime(lang):
    """返回 {"ok": bool, "version": str, "reason": str, ...命令路径}。"""
    if lang in _RUNTIME_CACHE:
        return _RUNTIME_CACHE[lang]
    info = {"ok": False, "version": "", "reason": ""}
    if lang == "python":
        candidates = [shutil.which("python3"), shutil.which("python")]
        for p in candidates:
            if not p:
                continue
            ok, ver = _probe([p, "--version"])
            if ok and ver.startswith("Python 3"):
                info = {"ok": True, "version": ver, "reason": "", "python": p, "cmd": os.path.basename(p)}
                break
        if not info["ok"] and sys.executable:
            info = {"ok": True, "version": "Python %d.%d.%d" % sys.version_info[:3], "reason": "",
                    "python": sys.executable, "cmd": os.path.basename(sys.executable)}
        if not info["ok"]:
            info["reason"] = "未找到 python3 / python"
    elif lang == "javascript":
        p = shutil.which("node")
        if p:
            ok, ver = _probe([p, "--version"])
            if ok:
                info = {"ok": True, "version": "node " + ver, "reason": "", "node": p}
            else:
                info["reason"] = "node 无法运行：" + ver
        else:
            info["reason"] = "未找到 node"
    elif lang == "java":
        javac = shutil.which("javac")
        java = shutil.which("java")
        if not javac or not java:
            info["reason"] = "未找到 " + " 与 ".join(n for n, p in (("javac", javac), ("java", java)) if not p)
        else:
            ok_c, ver_c = _probe([javac, "-version"])
            ok_j, ver_j = _probe([java, "-version"])
            if ok_c and ok_j:
                info = {"ok": True, "version": ver_c + "；" + ver_j, "reason": "", "javac": javac, "java": java}
            else:
                bad = ver_c if not ok_c else ver_j
                info["reason"] = "javac/java 无法运行：" + (bad or "退出码非 0")
    _RUNTIME_CACHE[lang] = info
    return info


def require_runtime(lang):
    rt = detect_runtime(lang)
    if not rt["ok"]:
        raise UsageError("本机缺 %s 运行时（%s），无法处理 %s 题包。运行 judge.py doctor 查看环境。"
                         % (LANG_LABEL[lang], rt["reason"], LANG_LABEL[lang]))
    return rt


def child_env(lang):
    """子进程环境只留 PATH（Java 再留 JAVA_HOME）。Windows 下 Python 启动需要 SystemRoot，属于最小放行。"""
    env = {"PATH": os.environ.get("PATH", "")}
    if lang == "java" and os.environ.get("JAVA_HOME"):
        env["JAVA_HOME"] = os.environ["JAVA_HOME"]
    if IS_WINDOWS:
        for key in ("SystemRoot", "SYSTEMROOT"):
            if key in os.environ:
                env["SystemRoot"] = os.environ[key]
                break
    return env


# ---------------------------------------------------------------- 子进程

READ_CHUNK = 64 * 1024


def _descendants(pid):
    """递归收集 pid 的所有后代（POSIX）：先试 pgrep -P，再退化为 ps --ppid / ps -axo。"""
    found = []
    stack = [pid]
    seen = set()
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        kids = _children_of(p)
        for k in kids:
            if k not in seen:
                found.append(k)
                stack.append(k)
    return found


_CHILD_LOOKUP = {"mode": None}


def _children_of(pid):
    out = []
    mode = _CHILD_LOOKUP["mode"]
    if mode in (None, "pgrep"):
        try:
            r = subprocess.run(["pgrep", "-P", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
            if r.returncode in (0, 1):
                _CHILD_LOOKUP["mode"] = "pgrep"
                return [int(x) for x in r.stdout.split() if x.strip().isdigit()]
        except Exception:
            pass
    try:
        r = subprocess.run(["ps", "-o", "pid=", "--ppid", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        if r.returncode in (0, 1):
            _CHILD_LOOKUP["mode"] = "ps"
            return [int(x) for x in r.stdout.split() if x.strip().isdigit()]
    except Exception:
        pass
    try:
        r = subprocess.run(["ps", "-axo", "pid=,ppid="], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        for line in r.stdout.decode("utf-8", "replace").split("\n"):
            parts = line.split()
            if len(parts) == 2 and parts[1] == str(pid) and parts[0].isdigit():
                out.append(int(parts[0]))
    except Exception:
        pass
    return out


def kill_tree(proc):
    """杀掉整棵进程树：先递归收集后代 pid（含 setsid / detached 逃出进程组的），再 SIGKILL 进程组与每个 pid；
    Windows 用 taskkill /T；最后兜底 kill 本进程。杀完再收集一轮，堵住杀的瞬间新 fork 出来的。"""
    if IS_WINDOWS:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except Exception:
            pass
    else:
        for _round in range(2):
            pids = _descendants(proc.pid)
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
            if not pids:
                break
    try:
        proc.kill()
    except Exception:
        pass


def _reap_leftovers(proc, seen_pids):
    """程序结束后无条件再收一次：进程组里还活着的，以及运行期间见过、现在已经脱离会话的后代。"""
    if IS_WINDOWS:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    for pid in list(seen_pids):
        if pid == proc.pid:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    for pid in _descendants(proc.pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def _pump(stream, sink, cap, over_event):
    """守护线程：逐块读到 sink（bytearray），超过 cap 后停止保存但继续排空，直到 EOF。
    用 read1：有数据就返回，不等凑满一块（否则子进程留着管道不关时，已写出的部分输出会一直拿不到）。"""
    read_chunk = getattr(stream, "read1", None) or stream.read
    try:
        while True:
            chunk = read_chunk(READ_CHUNK)
            if not chunk:
                break
            if len(sink) < cap:
                sink.extend(chunk)
                if len(sink) > cap:
                    over_event.set()
            else:
                over_event.set()
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _feed(stream, data):
    try:
        if data:
            stream.write(data)
        stream.close()
    except Exception:
        pass


def exec_process(argv, cwd, stdin_text, timeout_s, env):
    """运行一次，返回 dict(stdout, stderr, exitCode, timeMs, timedOut, outputLimit)。

    - stdout / stderr 由守护线程逐块读，累计超过 OUTPUT_CAP 立即杀进程树（outputLimit=True）；
    - 超时 / 异常 / Ctrl-C 一律先杀进程树再返回或抛出，不等管道 EOF；
    - spawn 前 chdir 到 cwd，结束后 chdir 回去，避免父进程的工作目录泄露给作答程序。
    """
    import threading
    kwargs = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        old_cwd = os.getcwd()
    except OSError:
        old_cwd = None
    t0 = time.perf_counter()
    proc = None
    try:
        try:
            os.chdir(cwd)
        except OSError:
            pass
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        except OSError as e:
            return {"stdout": "", "stderr": "无法启动进程：%s" % e, "exitCode": -1, "timeMs": 0,
                    "timedOut": False, "outputLimit": False, "truncated": False, "spawnFailed": True}
        out_buf, err_buf = bytearray(), bytearray()
        over = threading.Event()
        threads = [
            threading.Thread(target=_pump, args=(proc.stdout, out_buf, OUTPUT_CAP, over), daemon=True),
            threading.Thread(target=_pump, args=(proc.stderr, err_buf, OUTPUT_CAP, over), daemon=True),
            threading.Thread(target=_feed, args=(proc.stdin, (stdin_text or "").encode("utf-8")), daemon=True),
        ]
        for t in threads:
            t.start()
        timed_out = False
        output_limit = False
        deadline = t0 + timeout_s
        # 运行期间每隔一小段时间记一次后代 pid：程序干净退出后，它派生出来又脱离了会话的常驻进程
        # 已经找不到父子关系（ppid 变成 1），只能靠运行时留下的名单来收。
        seen_pids = set()
        next_scan = t0
        try:
            while True:
                if over.is_set():
                    output_limit = True
                    kill_tree(proc)
                    break
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    timed_out = True
                    kill_tree(proc)
                    break
                if not IS_WINDOWS and time.perf_counter() >= next_scan:
                    try:
                        seen_pids.update(_descendants(proc.pid))
                    except Exception:
                        pass
                    next_scan = time.perf_counter() + 0.25
                try:
                    proc.wait(timeout=min(remaining, 0.05))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if timed_out or output_limit:
                try:
                    proc.wait(timeout=5)
                except Exception:
                    kill_tree(proc)
            _reap_leftovers(proc, seen_pids)
        except BaseException:
            kill_tree(proc)
            _reap_leftovers(proc, seen_pids)
            raise
        ms = int((time.perf_counter() - t0) * 1000)
        for t in threads[:2]:
            t.join(timeout=0.5)
        out = bytes(out_buf)
        err = bytes(err_buf)
        truncated = output_limit
        if len(out) > OUTPUT_CAP:
            out, truncated = out[:OUTPUT_CAP], True
        if len(err) > OUTPUT_CAP:
            err, truncated = err[:OUTPUT_CAP], True
        return {"stdout": out.decode("utf-8", "replace"), "stderr": err.decode("utf-8", "replace"),
                "exitCode": proc.returncode, "timeMs": ms, "timedOut": timed_out, "outputLimit": output_limit,
                "truncated": truncated, "spawnFailed": False}
    finally:
        if old_cwd is not None:
            try:
                os.chdir(old_cwd)
            except OSError:
                pass


class Program:
    """把一份源码放进临时目录（Java 先编译），逐条用例运行；退出时删除临时目录。"""

    def __init__(self, lang, runtime, source):
        self.lang = lang
        self.runtime = runtime
        self.source = source
        self.dir = None
        self.compile_error = None
        self.env = child_env(lang)

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="coding-drill-")
        write_text(os.path.join(self.dir, MAIN_FILE[self.lang]), self.source)
        if self.lang == "java":
            self._compile()
        return self

    def __exit__(self, *exc):
        if self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)
        return False

    def _compile(self):
        argv = [self.runtime["javac"], "-encoding", "UTF-8", "Main.java"]
        r = exec_process(argv, self.dir, "", COMPILE_TIMEOUT_S, self.env)
        if r["timedOut"]:
            self.compile_error = "编译超时（%d 秒）" % COMPILE_TIMEOUT_S
        elif r["exitCode"] != 0:
            msg = (r["stderr"] or r["stdout"]).strip()
            self.compile_error = msg or ("编译失败（退出码 %s）" % r["exitCode"])

    def argv(self):
        if self.lang == "python":
            return [self.runtime["python"], "main.py"]
        if self.lang == "javascript":
            return [self.runtime["node"], "main.js"]
        return [self.runtime["java"], "-cp", ".", "Main"]

    def run(self, stdin_text, time_limit_ms):
        return exec_process(self.argv(), self.dir, stdin_text, max(0.05, time_limit_ms / 1000.0), self.env)


# ---------------------------------------------------------------- 判题核心

def derive_case_verdict(r, expected):
    if r.get("spawnFailed"):
        return False, "runtime_error"
    if r.get("outputLimit"):
        return False, "output_limit_exceeded"
    if r["timedOut"]:
        return False, "time_limit_exceeded"
    if r["exitCode"] != 0:
        return False, "runtime_error"
    ok = norm_output(r["stdout"]) == norm_output(expected)
    return ok, ("accepted" if ok else "wrong_answer")


def overall_verdict(case_results, compile_error):
    if compile_error:
        return "compile_error"
    total = len(case_results)
    passed = sum(1 for c in case_results if c["passed"])
    if total and passed == total:
        return "accepted"
    if passed > 0:
        return "partial"
    counts = {}
    for c in case_results:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    if not counts:
        return "wrong_answer"
    order = ["time_limit_exceeded", "output_limit_exceeded", "runtime_error", "wrong_answer"]
    return max(counts, key=lambda v: (counts[v], -order.index(v) if v in order else -9))


def judge_source(lang, runtime, source, cases, time_limit_ms):
    """对一份源码跑全部用例。返回 dict(compileError, cases[], earned, total, score, verdict, passedCount)。"""
    results = []
    compile_error = None
    with Program(lang, runtime, source) as prog:
        compile_error = prog.compile_error
        for case in cases:
            expected = case.get("expected")
            if compile_error:
                r = {"stdout": "", "stderr": compile_error, "exitCode": -1, "timeMs": 0, "timedOut": False}
                passed, verdict = False, "compile_error"
            else:
                r = prog.run(case.get("input", ""), time_limit_ms)
                passed, verdict = derive_case_verdict(r, expected)
                if expected is None:
                    passed = False
            results.append({
                "id": case.get("id"), "job": case.get("job", ""), "isSample": bool(case.get("isSample")),
                "score": case.get("score", 0), "catches": case.get("catches", "") or "",
                "input": case.get("input", ""), "expected": expected,
                "passed": passed, "verdict": verdict, "timeMs": r["timeMs"],
                "stdout": norm_output(r["stdout"]), "stderr": r["stderr"].strip()[:2000],
                "exitCode": r["exitCode"],
            })
    total = sum(_num(c.get("score")) for c in cases)
    earned = sum(_num(c["score"]) for c in results if c["passed"])
    score = round(earned / total * FULL_SCORE, 1) if total > 0 else 0.0
    return {"compileError": compile_error, "cases": results, "earned": earned, "total": total,
            "score": score, "verdict": overall_verdict(results, compile_error),
            "passedCount": sum(1 for c in results if c["passed"])}


def _num(x):
    if isinstance(x, bool):
        return 0
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0
    if v != v or v in (float("inf"), float("-inf")):
        return 0
    return int(v) if v == int(v) else v


def _is_finite_number(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return False
    return x == x and x not in (float("inf"), float("-inf"))


def _is_int_value(x):
    """JSON 里的整数：int，或值为整数的 float（2.0）。bool 不算。"""
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    return isinstance(x, float) and x == x and x not in (float("inf"), float("-inf")) and x == int(x)


VALID_DIFFICULTY = (1, 2, 3)
TL_MIN_MS, TL_MAX_MS = 100, 60000


def difficulty_error(value):
    """meta.difficulty 合法返回 None，否则返回一句说明。"""
    if not _is_int_value(value) or int(value) not in VALID_DIFFICULTY:
        return "meta.json 的 difficulty 必须是 1 / 2 / 3 的整数（简单 / 中等 / 困难），当前是：%r" % (value,)
    return None


# ---------------------------------------------------------------- 题包

class Drill:
    def __init__(self, drill_dir):
        self.dir = os.path.abspath(drill_dir)
        if not os.path.isdir(self.dir):
            raise UsageError("题目目录不存在：%s" % drill_dir)
        self.meta_path = os.path.join(self.dir, "meta.json")
        self.hidden = os.path.join(self.dir, ".hidden")
        self.tests_path = os.path.join(self.hidden, "tests.json")
        self.mutants_json_path = os.path.join(self.hidden, "mutants.json")
        self.meta = read_json(self.meta_path)
        if not isinstance(self.meta, dict):
            raise UsageError("meta.json 必须是对象")
        self.lang = normalize_lang(self.meta.get("language"))
        self.slug = str(self.meta.get("slug") or os.path.basename(self.dir))
        self.title = str(self.meta.get("title") or self.slug)
        tl = self.meta.get("timeLimitMs")
        if tl is None:
            tl = DEFAULT_TL_MS
        if not _is_int_value(tl):
            raise UsageError("meta.json 的 timeLimitMs 必须是 %d～%d 的整数毫秒，当前是：%r" % (TL_MIN_MS, TL_MAX_MS, tl))
        self.time_limit_ms = int(tl)
        if not (TL_MIN_MS <= self.time_limit_ms <= TL_MAX_MS):
            raise UsageError("meta.json 的 timeLimitMs 必须在 %d～%d 之间，当前是：%d" % (TL_MIN_MS, TL_MAX_MS, self.time_limit_ms))
        mode = str(self.meta.get("compareMode") or "trim")
        if mode != "trim":
            raise UsageError("compareMode 只支持 trim，当前是：%r" % mode)
        self.tests = read_json(self.tests_path)
        if not isinstance(self.tests, dict) or not isinstance(self.tests.get("cases"), list):
            raise UsageError("tests.json 必须是 {\"cases\": [...]}")
        self.cases = self.tests["cases"]
        if not self.cases:
            raise UsageError("tests.json 里没有用例")
        seen = set()
        for i, c in enumerate(self.cases):
            if not isinstance(c, dict):
                raise UsageError("tests.json 第 %d 条用例不是对象" % (i + 1))
            c.setdefault("id", "c%d" % (i + 1))
            c["id"] = str(c["id"])
            seen.add(c["id"])
            if not isinstance(c.get("input", ""), str):
                raise UsageError("用例 %s 的 input 必须是字符串" % c["id"])
            c.setdefault("input", "")
            c.setdefault("isSample", False)
            if c.get("score") is None:
                c["score"] = 0
            if not _is_finite_number(c["score"]):
                raise UsageError("用例 %s 的 score 必须是有限的数字，当前是：%r" % (c["id"], c["score"]))
            if c.get("job") is None:
                c["job"] = "sample" if c["isSample"] else ""
            if not isinstance(c["job"], str):
                raise UsageError("用例 %s 的 job 必须是字符串，当前是：%r" % (c["id"], c["job"]))
            if c.get("catches") is None:
                c["catches"] = ""
            if not isinstance(c["catches"], str):
                raise UsageError("用例 %s 的 catches 必须是字符串，当前是：%r" % (c["id"], c["catches"]))
            if "expected" not in c:
                c["expected"] = None
            if c["expected"] is not None and not isinstance(c["expected"], str):
                raise UsageError("用例 %s 的 expected 必须是字符串或 null" % c["id"])
        self.author_report_path = os.path.join(self.hidden, "author-report.json")

    # 文件位置
    def starter_path(self):
        if self.lang == "java":
            return os.path.join(self.dir, "starter", "Main.java")
        return os.path.join(self.dir, {"python": "starter.py", "javascript": "starter.js"}[self.lang])

    def solution_path(self):
        return os.path.join(self.dir, {"python": "solution.py", "javascript": "solution.js", "java": "Main.java"}[self.lang])

    def reference_path(self):
        if self.lang == "java":
            for p in (os.path.join(self.hidden, "reference", "Main.java"), os.path.join(self.hidden, "Main.java")):
                if os.path.isfile(p):
                    return p
            return os.path.join(self.hidden, "reference", "Main.java")
        return os.path.join(self.hidden, "reference" + EXT[self.lang])

    def mutant_path(self, file_name):
        base = os.path.join(self.hidden, "mutants")
        if self.lang == "java" and not str(file_name).endswith(".java"):
            return os.path.join(base, str(file_name), "Main.java")
        return os.path.join(base, str(file_name))

    def load_mutants(self):
        if not os.path.isfile(self.mutants_json_path):
            return []
        data = read_json(self.mutants_json_path)
        items = data.get("mutants") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise UsageError("mutants.json 必须是 {\"mutants\": [...]}")
        out = []
        for i, m in enumerate(items):
            if isinstance(m, str):
                m = {"file": m, "misconception": ""}
            if not isinstance(m, dict) or not m.get("file"):
                raise UsageError("mutants.json 第 %d 项缺 file" % (i + 1))
            out.append({"file": str(m["file"]), "misconception": str(m.get("misconception") or "")})
        return out

    def sample_case(self):
        for c in self.cases:
            if c.get("isSample"):
                return c
        return self.cases[0]

    def save_tests(self):
        write_json(self.tests_path, self.tests)

    def misconceptions_path(self):
        return os.path.join(os.path.dirname(self.dir), "misconceptions.md")

    def problem_path(self):
        return os.path.join(self.dir, "problem.md")

    def verified_files(self):
        """author 验证要记录、export 要核对的文件：tests.json、参考解、起步骨架、每个错解。返回 [(标签, 路径)]。"""
        files = [("tests.json", self.tests_path), ("reference", self.reference_path()), ("starter", self.starter_path())]
        try:
            for m in self.load_mutants():
                files.append(("mutant:" + m["file"], self.mutant_path(m["file"])))
        except UsageError:
            pass
        return files

    def file_hashes(self):
        out = {}
        for label, path in self.verified_files():
            out[label] = sha256_file(path) if os.path.isfile(path) else None
        return out


# ---------------------------------------------------------------- 基线程序

def _java_string_literal(s):
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32 or ord(ch) > 126:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


_JAVA_READ_ALL = (
    "import java.io.*;\n\npublic class Main {\n"
    "    static String readAll() throws IOException {\n"
    "        InputStream in = System.in;\n        ByteArrayOutputStream bos = new ByteArrayOutputStream();\n"
    "        byte[] buf = new byte[8192];\n        int n;\n"
    "        while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);\n"
    "        return new String(bos.toByteArray(), \"UTF-8\");\n    }\n"
)


def _java_program(body):
    """Java 8 兼容：readAll() 读完 stdin，body 里可用它。"""
    return _JAVA_READ_ALL + "    public static void main(String[] args) throws IOException {\n" + body + "    }\n}\n"


def constant_source(lang, text):
    """打印一个固定文本的程序。"""
    if lang == "python":
        return "import sys\nsys.stdout.write(%r)\n" % text
    if lang == "javascript":
        return "process.stdout.write(%s);\n" % json.dumps(text, ensure_ascii=False)
    return ("public class Main {\n    public static void main(String[] args) {\n"
            "        System.out.print(%s);\n    }\n}\n" % _java_string_literal(text))


def baseline_sources(lang, constant_text):
    """非解基线：打印样例输出 / 什么都不打印 / 原样回显 stdin / 只打印第一个·最后一个 token / 第一行·最后一行。"""
    if lang == "python":
        return {
            "constant": constant_source(lang, constant_text),
            "empty": "",
            "echo": "import sys\nsys.stdout.write(sys.stdin.read())\n",
            "first_token": "import sys\nd = sys.stdin.read().split()\nsys.stdout.write(d[0] if d else '')\n",
            "last_token": "import sys\nd = sys.stdin.read().split()\nsys.stdout.write(d[-1] if d else '')\n",
            "first_line": "import sys\nl = sys.stdin.read().replace('\\r\\n', '\\n').split('\\n')\nsys.stdout.write(l[0])\n",
            "last_line": "import sys\nl = sys.stdin.read().replace('\\r\\n', '\\n').rstrip('\\n').split('\\n')\nsys.stdout.write(l[-1])\n",
        }
    if lang == "javascript":
        head = "const s = require('fs').readFileSync(0, 'utf8');\n"
        return {
            "constant": constant_source(lang, constant_text),
            "empty": "",
            "echo": head + "process.stdout.write(s);\n",
            "first_token": head + "const d = s.split(/\\s+/).filter(Boolean);\nprocess.stdout.write(d.length ? d[0] : '');\n",
            "last_token": head + "const d = s.split(/\\s+/).filter(Boolean);\nprocess.stdout.write(d.length ? d[d.length - 1] : '');\n",
            "first_line": head + "process.stdout.write(s.replace(/\\r\\n/g, '\\n').split('\\n')[0]);\n",
            "last_line": head + "const l = s.replace(/\\r\\n/g, '\\n').replace(/\\n+$/, '').split('\\n');\nprocess.stdout.write(l[l.length - 1]);\n",
        }
    return {
        "constant": constant_source(lang, constant_text),
        "empty": "public class Main {\n    public static void main(String[] args) {\n    }\n}\n",
        "echo": _java_program("        System.out.print(readAll());\n        System.out.flush();\n"),
        "first_token": _java_program("        String t = readAll().trim();\n        String[] d = t.isEmpty() ? new String[0] : t.split(\"\\\\s+\");\n"
                                     "        System.out.print(d.length > 0 ? d[0] : \"\");\n"),
        "last_token": _java_program("        String t = readAll().trim();\n        String[] d = t.isEmpty() ? new String[0] : t.split(\"\\\\s+\");\n"
                                    "        System.out.print(d.length > 0 ? d[d.length - 1] : \"\");\n"),
        "first_line": _java_program("        String[] l = readAll().replace(\"\\r\\n\", \"\\n\").split(\"\\n\", -1);\n        System.out.print(l[0]);\n"),
        "last_line": _java_program("        String t = readAll().replace(\"\\r\\n\", \"\\n\").replaceAll(\"\\n+$\", \"\");\n"
                                   "        String[] l = t.split(\"\\n\", -1);\n        System.out.print(l[l.length - 1]);\n"),
    }


BASELINE_NAMES = ("constant", "empty", "echo", "starter", "first_token", "last_token", "first_line", "last_line")
BASELINE_LABEL = {"constant": "打印样例输出", "empty": "什么都不打印", "echo": "原样回显输入", "starter": "起步骨架原样提交",
                  "first_token": "只打印输入的第一个 token", "last_token": "只打印输入的最后一个 token",
                  "first_line": "只打印输入的第一行", "last_line": "只打印输入的最后一行"}
# 这几个基线允许拿到少量分（WARN），拿到一半以上才 ERROR
BASELINE_HALF_RULE = ("first_token", "last_token", "first_line", "last_line")


def baseline_unproven(res):
    """基线程序自己没跑起来（编译失败或每条用例都 runtime_error）→ 这个闸门什么都没证明。"""
    if res["compileError"]:
        return "编译失败"
    if res["cases"] and all(c["verdict"] == "runtime_error" for c in res["cases"]):
        return "每条用例都 runtime_error"
    return None


def guessable_constants(sample_input):
    """学生真正会交的常量：0、-1、1、样例输入的第一个 token。去重、保持顺序。"""
    out = []
    tokens = (sample_input or "").split()
    for v in ["0", "-1", "1"] + ([tokens[0]] if tokens else []):
        if v not in out:
            out.append(v)
    return out


# ---------------------------------------------------------------- author

class GateList:
    def __init__(self):
        self.items = []

    def add(self, name, level, message):
        self.items.append({"name": name, "level": level, "message": message})

    def ok(self, name, message):
        self.add(name, "OK", message)

    def error(self, name, message):
        self.add(name, "ERROR", message)

    def warn(self, name, message):
        self.add(name, "WARN", message)

    @property
    def errors(self):
        return [g for g in self.items if g["level"] == "ERROR"]

    @property
    def warnings(self):
        return [g for g in self.items if g["level"] == "WARN"]


def _ids(results, passed):
    return [c["id"] for c in results if c["passed"] == passed]


def cmd_author(args):
    drill = Drill(args.drill_dir)
    runtime = require_runtime(drill.lang)
    gates = GateList()
    print("出题验证：%s（%s）· %s · 时限 %dms" % (drill.slug, drill.title, LANG_LABEL[drill.lang], drill.time_limit_ms))

    report = {
        "slug": drill.slug, "title": drill.title, "language": drill.lang, "checkedAt": now_iso(),
        "refill": bool(args.refill), "ok": False, "errorCount": 0, "warnCount": 0,
        "gates": [], "reference": {"cases": [], "slowestMs": 0}, "baselines": {}, "mutants": [], "testsHash": "",
    }

    # 1. 参考解回填
    ref_path = drill.reference_path()
    if not os.path.isfile(ref_path):
        gates.error("solution_fail", "参考解不存在：%s" % os.path.relpath(ref_path, drill.dir))
        return _finish_author(drill, gates, report, "参考解缺失，后续闸门未跑")
    ref_src = read_text(ref_path)
    ref = judge_source(drill.lang, runtime, ref_src, drill.cases, drill.time_limit_ms)
    filled, refilled, mismatched, failed = 0, 0, 0, 0
    if ref["compileError"]:
        gates.error("solution_fail", "参考解编译失败：%s" % ref["compileError"].split("\n")[0][:300])
        failed = len(drill.cases)
    else:
        for case, r in zip(drill.cases, ref["cases"]):
            report["reference"]["cases"].append({"id": case["id"], "job": case.get("job", ""),
                                                 "verdict": "ok" if r["verdict"] in ("accepted", "wrong_answer") else r["verdict"],
                                                 "timeMs": r["timeMs"]})
            if r["verdict"] in ("time_limit_exceeded", "runtime_error", "compile_error", "output_limit_exceeded"):
                failed += 1
                detail = r["stderr"].split("\n")[-1][:200] if r["stderr"] else ""
                gates.error("solution_fail", "参考解在用例 %s 上 %s%s" % (case["id"], r["verdict"], ("：" + detail) if detail else ""))
                continue
            got = r["stdout"]
            if case["expected"] is None:
                case["expected"] = got
                filled += 1
            elif norm_output(case["expected"]) != got:
                if args.refill:
                    case["expected"] = got
                    refilled += 1
                else:
                    mismatched += 1
                    gates.error("solution_fail", "用例 %s 的 expected 与参考解实跑不一致（不覆盖；确认参考解正确后用 --refill）" % case["id"])
        report["reference"]["slowestMs"] = max((c["timeMs"] for c in ref["cases"]), default=0)
    if filled or refilled:
        drill.save_tests()
    line = "参考解：%d/%d 条用例跑通（最慢 %dms）" % (len(drill.cases) - failed, len(drill.cases), report["reference"]["slowestMs"])
    if filled:
        line += "；回填期望输出 %d 条" % filled
    if refilled:
        line += "；--refill 覆盖 %d 条" % refilled
    if mismatched:
        line += "；%d 条与已有 expected 不一致" % mismatched
    print(line)
    if failed or mismatched:
        return _finish_author(drill, gates, report, "参考解未通过（solution_fail），后续闸门未跑")
    gates.ok("solution_fail", "参考解跑通全部用例，期望输出均由实跑得到")
    slowest = report["reference"]["slowestMs"]
    if slowest * 3 > drill.time_limit_ms:
        gates.warn("time_limit", "时限 %dms 不到参考解最慢用时（%dms）的 3 倍" % (drill.time_limit_ms, slowest))
    elif drill.time_limit_ms > 2000 and slowest <= 300:
        gates.warn("time_limit", "参考解最慢 %dms，未超过 300ms，时限应填默认 2000 而不是 %d" % (slowest, drill.time_limit_ms))

    # 2. 静态闸门
    _static_gates(drill, gates)

    # 3. 基线
    sample = drill.sample_case()
    sources = baseline_sources(drill.lang, norm_output(sample.get("expected") or ""))
    starter_path = drill.starter_path()
    if os.path.isfile(starter_path):
        sources["starter"] = read_text(starter_path)
    else:
        sources["starter"] = None
    baseline_line = []
    half = FULL_SCORE / 2.0
    for name in BASELINE_NAMES:
        src = sources[name]
        gate = "baseline_" + name
        label = BASELINE_LABEL[name]
        if src is None:
            gates.error(gate, "起步骨架不存在：%s" % os.path.basename(starter_path))
            report["baselines"][name] = {"score": None, "passed": []}
            baseline_line.append("%s 缺失" % name)
            continue
        res = judge_source(drill.lang, runtime, src, drill.cases, drill.time_limit_ms)
        report["baselines"][name] = {"score": res["score"], "verdict": res["verdict"], "passed": _ids(res["cases"], True)}
        baseline_line.append("%s %s" % (name, fmt_score(res["score"])))
        unproven = baseline_unproven(res)
        if unproven:
            report["baselines"][name]["unproven"] = unproven
            gates.warn(gate, "「%s」这个基线程序未能运行（%s），该闸门未证明" % (label, unproven))
        elif res["score"] > 0:
            detail = "%s拿到 %s 分（通过 %s）" % (label, fmt_score(res["score"]), " ".join(_ids(res["cases"], True)))
            if name in BASELINE_HALF_RULE and res["score"] < half:
                gates.warn(gate, detail + "——期望输出是输入里的某个 token 或某一行；把更多分值放到答案不在输入里的用例上（authoring-rules §4.7）")
            else:
                gates.error(gate, detail)
        else:
            gates.ok(gate, "%s得 0 分" % label)
    print("基线：" + " / ".join(baseline_line))

    # 3b. 好猜的常量：0 / -1 / 1 / 样例输入的第一个 token（期望输出两两不同保证一个常量最多过一条，所以只 WARN）
    guess_hits, guess_unproven = [], []
    for value in guessable_constants(sample.get("input", "")):
        res = judge_source(drill.lang, runtime, constant_source(drill.lang, value), drill.cases, drill.time_limit_ms)
        key = "const:" + value
        report["baselines"][key] = {"score": res["score"], "verdict": res["verdict"], "passed": _ids(res["cases"], True)}
        unproven = baseline_unproven(res)
        if unproven:
            report["baselines"][key]["unproven"] = unproven
            guess_unproven.append("%s（%s）" % (value, unproven))
        elif res["score"] > 0:
            guess_hits.append("打印 %s 拿到 %s 分（通过 %s）" % (value, fmt_score(res["score"]), " ".join(_ids(res["cases"], True))))
    if guess_unproven:
        gates.warn("constant_guessable", "常量基线程序未能运行（%s），该闸门未证明" % "；".join(guess_unproven))
    elif guess_hits:
        gates.warn("constant_guessable", "；".join(guess_hits) + "——把 empty 用例的答案改成不那么好猜的值，或把分放到别的用例上（authoring-rules §4.8）")
    else:
        gates.ok("constant_guessable", "打印 0 / -1 / 1 / 样例首个 token 都得 0 分")
    if drill.lang != "java" and not os.path.isfile(drill.solution_path()):
        gates.warn("solution_file", "学生作答文件不存在：%s（应由起步骨架复制而来）" % os.path.basename(drill.solution_path()))

    # 4. 错解
    mutants = drill.load_mutants()
    if len(mutants) < 2:
        gates.error("mutants_count", "错解只有 %d 个，至少要 2 个" % len(mutants))
    elif len(mutants) == 2:
        gates.warn("mutants_count", "错解只有 2 个，建议 3 个")
    else:
        gates.ok("mutants_count", "错解 %d 个" % len(mutants))
    for m in mutants:
        path = drill.mutant_path(m["file"])
        entry = {"file": m["file"], "misconception": m["misconception"], "score": None, "passed": [], "failed": [], "status": ""}
        report["mutants"].append(entry)
        if not os.path.isfile(path):
            gates.error("mutant_missing", "错解文件不存在：%s" % os.path.relpath(path, drill.dir))
            entry["status"] = "missing"
            print("错解：%s 缺失" % m["file"])
            continue
        res = judge_source(drill.lang, runtime, read_text(path), drill.cases, drill.time_limit_ms)
        entry["score"] = res["score"]
        entry["verdict"] = res["verdict"]
        entry["passed"] = _ids(res["cases"], True)
        entry["failed"] = _ids(res["cases"], False)
        all_broken = bool(res["compileError"]) or all(c["verdict"] in ("runtime_error", "compile_error") for c in res["cases"])
        if all_broken:
            gates.warn("mutant_compile", "错解 %s 每条用例都编译/运行失败，不像人写的程序" % m["file"])
            entry["status"] = "broken"
        elif res["passedCount"] == len(res["cases"]) or (res["total"] > 0 and res["earned"] >= res["total"]):
            gates.error("mutant_full", "错解 %s 拿了满分（%s），用例集看不见这个误解：%s" % (m["file"], fmt_score(res["score"]), m["misconception"]))
            entry["status"] = "full"
        elif res["passedCount"] == 0:
            gates.warn("mutant_zero", "错解 %s 每条用例都挂，只证明它错，不证明用例有针对性" % m["file"])
            entry["status"] = "zero"
        else:
            gates.ok("mutant_" + m["file"], "错解 %s 得 %s 分（过 %s；挂 %s）" % (m["file"], fmt_score(res["score"]),
                                                                    " ".join(entry["passed"]) or "无", " ".join(entry["failed"]) or "无"))
            entry["status"] = "ok"
        print("错解：%s %s 分（过 %s · 挂 %s）%s" % (m["file"], fmt_score(res["score"]), " ".join(entry["passed"]) or "无",
                                                 " ".join(entry["failed"]) or "无", ("  " + m["misconception"]) if m["misconception"] else ""))
    # 反向检查：每条隐藏用例都应至少被一个（能运行的）错解挂掉，否则它写的 catches 没有错解来证明
    caught = set()
    for entry in report["mutants"]:
        if entry.get("status") in ("ok", "zero", "full"):
            caught.update(entry.get("failed") or [])
    uncaught = [c["id"] for c in drill.cases if not c.get("isSample") and c["id"] not in caught]
    if report["mutants"] and uncaught:
        gates.warn("case_uncaught", "隐藏用例 %s 没有被任何错解挂掉——它写的误解没有对应错解来证明（authoring-rules §5）" % " ".join(uncaught))
    elif report["mutants"]:
        gates.ok("case_uncaught", "每条隐藏用例都至少被一个错解挂掉")

    return _finish_author(drill, gates, report, None)


def _static_gates(drill, gates):
    cases = drill.cases
    samples = [c for c in cases if c.get("isSample")]
    hidden = [c for c in cases if not c.get("isSample")]

    derr = difficulty_error(drill.meta.get("difficulty"))
    if derr:
        gates.error("difficulty", derr)
    else:
        gates.ok("difficulty", "难度 %d" % int(drill.meta.get("difficulty")))

    if len(samples) != 1:
        gates.error("sample_count", "样例用例必须恰好 1 条，当前 %d 条" % len(samples))
    elif _num(samples[0].get("score")) != 0:
        gates.error("sample_count", "样例用例 %s 的 score 必须为 0，当前 %s" % (samples[0]["id"], samples[0].get("score")))
    elif samples[0].get("job") != "sample":
        gates.error("sample_count", "样例用例 %s 的 job 必须是 sample，当前 %r" % (samples[0]["id"], samples[0].get("job")))
    else:
        gates.ok("sample_count", "恰好 1 条样例，分值 0，job 为 sample")

    if len(hidden) in (4, 5):
        gates.ok("hidden_count", "隐藏用例 %d 条" % len(hidden))
    else:
        gates.error("hidden_count", "隐藏用例必须是 4 条或 5 条，当前 %d 条" % len(hidden))

    hidden_jobs = [c.get("job") or "" for c in hidden]
    sample_hidden = [c["id"] for c in hidden if c.get("job") == "sample"]
    dup_jobs = sorted({j for j in hidden_jobs if j and hidden_jobs.count(j) > 1})
    unknown_jobs = [c["id"] for c in cases if c.get("job") not in JOBS]
    if sample_hidden:
        gates.error("hidden_jobs", "隐藏用例不可用 sample 职责：%s" % " ".join(sample_hidden))
    elif dup_jobs:
        gates.error("hidden_jobs", "隐藏用例职责重复（%s），每条隐藏用例应各取不同职责" % " ".join(dup_jobs))
    elif unknown_jobs:
        gates.error("hidden_jobs", "job 取值必须在 %s 之内：%s" % ("/".join(JOBS), " ".join(unknown_jobs)))
    else:
        gates.ok("hidden_jobs", "隐藏用例职责两两不同：%s" % " ".join(hidden_jobs))

    low = [c["id"] for c in hidden if _num(c.get("score")) < 1]
    if low:
        gates.error("hidden_score", "隐藏用例分值必须 ≥ 1：%s" % " ".join(low))
    else:
        gates.ok("hidden_score", "每条隐藏用例分值 ≥ 1")
    total = sum(_num(c.get("score")) for c in hidden)
    if total > 0:
        gates.ok("score_sum", "隐藏用例总分 %s" % total)
    else:
        gates.error("score_sum", "隐藏用例分之和必须 > 0")
    hidden_scores = [_num(c.get("score")) for c in hidden]
    if hidden_scores and sorted(hidden_scores) not in ([2, 2, 3, 3], [2, 2, 2, 2, 2]):
        gates.warn("score_shape", "隐藏用例分值 %s 不是 2+3+2+3 或 2×5（authoring-rules §2）" % "+".join(str(s) for s in hidden_scores))

    ids = [c["id"] for c in cases]
    dup_ids = sorted({i for i in ids if ids.count(i) > 1})
    if dup_ids:
        gates.error("dup_id", "用例 id 重复：%s" % " ".join(dup_ids))
    else:
        gates.ok("dup_id", "用例 id 两两不同")

    labels = ["%s#%d" % (c["id"], i + 1) if c["id"] in dup_ids else c["id"] for i, c in enumerate(cases)]
    exp = [norm_output(c.get("expected") or "") for c in cases]
    inp = [c.get("input", "") for c in cases]
    dup = _dup_groups(labels, exp)
    if dup:
        gates.error("dup_output", "期望输出相同：%s" % "；".join(" = ".join(g) for g in dup))
    else:
        gates.ok("dup_output", "所有用例期望输出两两不同")
    dup_in = _dup_groups(labels, inp)
    if dup_in:
        gates.error("dup_input", "输入相同：%s" % "；".join(" = ".join(g) for g in dup_in))
    else:
        gates.ok("dup_input", "所有用例输入两两不同")
    empty_in = [l for l, v in zip(labels, inp) if v.strip() == ""]
    if empty_in:
        gates.error("empty_input", "输入为空：%s" % " ".join(empty_in))
    else:
        gates.ok("empty_input", "没有空输入")
    echo = [l for l, e, i in zip(labels, exp, inp) if e == norm_output(i)]
    if echo:
        gates.error("echo_case", "期望输出等于自己的输入（回显程序能过）：%s" % " ".join(echo))
    else:
        gates.ok("echo_case", "没有用例的输出等于输入")
    empty_exp = [l for l, v in zip(labels, exp) if v == ""]
    if empty_exp:
        gates.error("empty_expected", "期望输出为空（空程序能过）：%s" % " ".join(empty_exp))
    else:
        gates.ok("empty_expected", "没有空的期望输出")

    no_catches = [c["id"] for c in hidden if not str(c.get("catches") or "").strip()]
    if no_catches:
        gates.error("catches_missing", "隐藏用例的 catches 为空：%s" % " ".join(no_catches))
    else:
        gates.ok("catches_missing", "每条隐藏用例都写明了抓的误解")
    generic = [c["id"] for c in hidden if str(c.get("catches") or "").strip() and _catches_is_generic(c["catches"])]
    if generic:
        gates.warn("catches_generic", "catches 太笼统（短于 8 个字，或只有“边界/特殊情况/测试”这类词）：%s" % " ".join(generic))

    floats = [l for l, v in zip(labels, exp) if re.search(r"\d\.\d", v)]
    if floats:
        gates.error("float_out", "期望输出含小数（跨语言格式不稳，改问整数）：%s" % " ".join(floats))
    else:
        gates.ok("float_out", "期望输出不含小数")
    trailing = [l for l, v in zip(labels, exp) if any(line != line.rstrip(" \t") for line in v.split("\n"))]
    if trailing:
        gates.warn("trailing_ws", "期望输出有行以空格结尾：%s" % " ".join(trailing))
    else:
        gates.ok("trailing_ws", "期望输出没有行尾空格")

    # 以下来自 authoring-rules，作为提醒
    long_in = [c["id"] for c in cases if len(c.get("input", "").split("\n")) > 20]
    if long_in:
        gates.warn("input_lines", "输入超过 20 行（authoring-rules §1）：%s" % " ".join(long_in))
    if drill.time_limit_ms not in (1000, 2000, 3000):
        gates.warn("time_limit_value", "timeLimitMs 应填 1000 / 2000 / 3000，当前 %d" % drill.time_limit_ms)


_GENERIC_WORDS = ("边界情况", "特殊情况", "边界", "特殊", "测试", "情况", "用例", "检查", "常规", "一般", "普通", "正常", "极端", "异常", "错误", "例子", "案例")


def _catches_is_generic(text):
    t = re.sub(r"[\s\W_]+", "", str(text), flags=re.UNICODE)
    if len(t) < 8:
        return True
    for w in sorted(_GENERIC_WORDS, key=len, reverse=True):
        t = t.replace(w, "")
    return t == ""


def _dup_groups(labels, values):
    rev = {}
    for label, v in zip(labels, values):
        rev.setdefault(v, []).append(label)
    return [ids for ids in rev.values() if len(ids) > 1]


def _finish_author(drill, gates, report, abort_note):
    errors, warnings = gates.errors, gates.warnings
    report["gates"] = gates.items
    report["ok"] = not errors
    report["errorCount"] = len(errors)
    report["warnCount"] = len(warnings)
    if abort_note:
        report["note"] = abort_note
    if os.path.isfile(drill.tests_path):
        report["testsHash"] = sha256_file(drill.tests_path)
    report["files"] = drill.file_hashes()
    write_json(drill.author_report_path, report)
    md_path = os.path.join(drill.dir, "author-report.md")
    write_text(md_path, render_author_md(drill, report))
    print("闸门：")
    for g in gates.items:
        if g["level"] == "OK":
            continue
        print("  [%s] %s：%s" % (g["level"], g["name"], g["message"]))
    if not errors and not warnings:
        print("  全部通过")
    if abort_note:
        print("  " + abort_note)
    verdict = "通过" if not errors else "未通过"
    print("结论：%s（%d ERROR，%d WARN）· 报告 author-report.md" % (verdict, len(errors), len(warnings)))
    return 0 if not errors else 1


def render_author_md(drill, report):
    lines = ["# 出题验证报告：%s" % drill.title, "",
             "- 题号：`%s` · 语言：%s · 时限：%dms · 检查时间：%s" % (drill.slug, LANG_LABEL[drill.lang], drill.time_limit_ms, report["checkedAt"]),
             "- 结论：**%s**（%d ERROR，%d WARN）%s" % ("通过" if report["ok"] else "未通过", report["errorCount"], report["warnCount"],
                                                   "· 本次使用 --refill 覆盖了已有期望输出" if report.get("refill") else ""),
             ""]
    if report.get("note"):
        lines += ["> " + report["note"], ""]
    lines += ["## 闸门", "", "| 闸门 | 结果 | 说明 |", "|---|---|---|"]
    for g in report["gates"]:
        lines.append("| %s | %s | %s |" % (g["name"], g["level"], g["message"].replace("|", "\\|")))
    lines += ["", "## 参考解", ""]
    if report["reference"]["cases"]:
        lines += ["| 用例 | 职责 | 结果 | 用时 |", "|---|---|---|---|"]
        for c in report["reference"]["cases"]:
            lines.append("| %s | %s | %s | %dms |" % (c["id"], c["job"], c["verdict"], c["timeMs"]))
    else:
        lines.append("（参考解未跑通）")
    lines += ["", "## 基线（非解程序的得分；前四个必须 0 分，token / 行基线过半即不合格，常量基线 > 0 提醒）", ""]
    if report["baselines"]:
        lines += ["| 基线 | 得分 | 通过的用例 |", "|---|---|---|"]
        for name in list(BASELINE_NAMES) + [k for k in report["baselines"] if k.startswith("const:")]:
            b = report["baselines"].get(name)
            if not b:
                continue
            score = "缺失" if b["score"] is None else fmt_score(b["score"])
            if b.get("unproven"):
                score += "（未能运行）"
            lines.append("| %s | %s | %s |" % (name.replace("|", "\\|"), score, " ".join(b["passed"]) or "无"))
    else:
        lines.append("（未跑）")
    lines += ["", "## 错解", ""]
    if report["mutants"]:
        lines += ["| 文件 | 误解 | 得分 | 通过 | 未通过 |", "|---|---|---|---|---|"]
        for m in report["mutants"]:
            lines.append("| %s | %s | %s | %s | %s |" % (m["file"], m["misconception"].replace("|", "\\|"),
                                                       "缺失" if m["score"] is None else fmt_score(m["score"]),
                                                       " ".join(m["passed"]) or "无", " ".join(m["failed"]) or "无"))
    else:
        lines.append("（没有错解）")
    lines += ["", "本报告不含隐藏用例的输入与期望输出。", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 作答文件静态扫描

# 没有沙箱：judge 前扫一遍作答文件，命中进程 / 文件 / 网络关键词就拒跑（--allow-io 跳过）。
_SCAN_PATTERNS = {
    "python": [
        ("subprocess", r"\bsubprocess\b"), ("os.system", r"\bos\s*\.\s*system\b"), ("os.popen", r"\bos\s*\.\s*popen\b"),
        ("os.fork", r"\bos\s*\.\s*fork\w*\b"), ("os.setsid", r"\bos\s*\.\s*setsid\b"), ("os.getppid", r"\bos\s*\.\s*getppid\b"),
        ("os.exec*", r"\bos\s*\.\s*exec\w*\b"), ("os.spawn*", r"\bos\s*\.\s*spawn\w*\b"), ("os.posix_spawn", r"\bos\s*\.\s*posix_spawn\w*\b"),
        ("multiprocessing", r"\bmultiprocessing\b"), ("concurrent.futures", r"\bconcurrent\s*\.\s*futures\b"), ("ctypes", r"\bctypes\b"),
        ("getppid", r"\bgetppid\b"), ("/proc/", r"/proc/"), ("lsof", r"\blsof\b"), ("socket", r"\bsocket\b"),
        ("urllib", r"\burllib\b"), ("http", r"\bhttps?\b"), ("open(", r"\bopen\s*\("), ("pathlib", r"\bpathlib\b"),
        ("shutil", r"\bshutil\b"),
    ],
    "javascript": [
        ("child_process", r"\bchild_process\b"), ("worker_threads", r"\bworker_threads\b"), ("cluster", r"\bcluster\b"),
        ("process.ppid", r"\bprocess\s*\.\s*ppid\b"), ("net", r"\bnet\b"),
        ("http", r"\bhttps?\b"), ("dns", r"\bdns\b"),
    ],
    "java": [
        ("ProcessBuilder", r"\bProcessBuilder\b"), ("Runtime.getRuntime", r"\bRuntime\s*\.\s*getRuntime\b"),
        ("ProcessHandle", r"\bProcessHandle\b"), ("java.io.File", r"\bjava\.io\.File"), ("java.nio.file", r"\bjava\.nio\.file\b"),
        ("java.net", r"\bjava\.net\b"),
    ],
}
_JS_FS_ALLOWED = re.compile(r"""readFileSync\s*\(\s*(?:0|['"]/dev/stdin['"])""")
_JS_FS_MODULE = r"""require\s*\(\s*['"](?:node:)?fs(?:/promises)?['"]\s*\)"""
_JS_FS_FUNCS = ("readFileSync", "readFile", "writeFileSync", "writeFile", "appendFileSync", "appendFile", "readdirSync", "readdir",
                "existsSync", "exists", "openSync", "statSync", "lstatSync", "stat", "unlinkSync", "unlink", "mkdirSync", "mkdir",
                "createReadStream", "createWriteStream", "accessSync", "access", "rmSync", "rm", "rmdirSync", "rmdir",
                "copyFileSync", "copyFile", "renameSync", "rename", "realpathSync", "realpath", "readlinkSync", "readlink",
                "opendirSync", "opendir", "readSync", "readvSync", "openAsBlob", "promises")
_JS_FS_RULES = [
    ("fs（非 readFileSync(0)）", re.compile(r"\bfs\s*\.\s*(?!ALLOWED\b)\w+")),
    ("fs（非 readFileSync(0)）", re.compile(_JS_FS_MODULE + r"\s*\.\s*(?!ALLOWED\b)\w+")),
    ("fs/promises", re.compile(r"""require\s*\(\s*['"](?:node:)?fs/promises['"]""")),
    ("fs（解构）", re.compile(r"\{[^}]*\}\s*=\s*" + _JS_FS_MODULE)),
    ("fs（import）", re.compile(r"""\bimport\b[^;\n]*\bfrom\s*['"](?:node:)?fs(?:/promises)?['"]""")),
    ("fs 调用", re.compile(r"\b(?:%s)\s*\(" % "|".join(re.escape(f) for f in _JS_FS_FUNCS))),
]


def scan_source(lang, source):
    """返回命中列表 [(行号, 关键词, 行文本)]。"""
    hits = []
    patterns = [(k, re.compile(rx)) for k, rx in _SCAN_PATTERNS.get(lang, [])]
    for i, line in enumerate(source.replace("\r\n", "\n").split("\n"), 1):
        seen = set()
        for key, rx in patterns:
            if rx.search(line) and key not in seen:
                seen.add(key)
                hits.append((i, key, line))
        if lang == "javascript":
            masked = _JS_FS_ALLOWED.sub("ALLOWED", line)
            for key, rx in _JS_FS_RULES:
                m = rx.search(masked)
                if not m:
                    continue
                if key == "fs（解构）":
                    names = re.findall(r"\w+", m.group(0).split("}")[0])
                    if all(n == "readFileSync" for n in names):
                        continue
                if key not in seen:
                    seen.add(key)
                    hits.append((i, key, line))
    return hits


def check_source_safety(lang, source, path, allow_io):
    hits = scan_source(lang, source)
    if not hits or allow_io:
        return hits
    lines = ["作答文件命中进程 / 文件 / 网络关键词，未运行：%s" % path]
    for lineno, key, text in hits:
        lines.append("  第 %d 行 [%s]：%s" % (lineno, key, text.strip()[:160]))
    lines.append("  没有沙箱；确认这些代码无害后加 --allow-io 再判。")
    raise UsageError("\n".join(lines))


# ---------------------------------------------------------------- judge

def cmd_judge(args):
    drill = Drill(args.drill_dir)
    runtime = require_runtime(drill.lang)
    sol_path = os.path.abspath(args.file) if args.file else drill.solution_path()
    if not os.path.isfile(sol_path):
        raise UsageError("作答文件不存在：%s" % sol_path)
    unfilled = [c["id"] for c in drill.cases if c.get("expected") is None]
    if unfilled:
        raise UsageError("用例 %s 的 expected 还是 null，请先运行 judge.py author 回填" % " ".join(unfilled))
    source = read_text(sol_path)
    scan_hits = check_source_safety(drill.lang, source, sol_path, getattr(args, "allow_io", False))
    if scan_hits:
        print("提示：--allow-io 已跳过静态扫描（命中 %d 处）" % len(scan_hits))
    res = judge_source(drill.lang, runtime, source, drill.cases, drill.time_limit_ms)
    starter_path = drill.starter_path()
    same_as_starter = os.path.isfile(starter_path) and norm_output(read_text(starter_path)) == norm_output(source)

    # 揭开规则：样例总是可见；隐藏用例默认只揭开第一条未通过的
    first_fail = None
    for c in res["cases"]:
        if not c["isSample"] and not c["passed"]:
            first_fail = c["id"]
            break
    for c in res["cases"]:
        c["revealed"] = bool(c["isSample"] or args.reveal_all or c["id"] == first_fail)

    new_entries = append_misconceptions(drill, res["cases"], res["verdict"], same_as_starter)

    print("判题：%s（%s）· 文件 %s" % (drill.slug, drill.title, os.path.relpath(sol_path, os.getcwd()) if _is_relative(sol_path) else sol_path))
    print("得分 %s / %d · 判定 %s（通过 %d/%d 条）" % (fmt_score(res["score"]), FULL_SCORE, res["verdict"], res["passedCount"], len(res["cases"])))
    if res["compileError"]:
        print("编译失败：")
        print(indent_block(res["compileError"][:1500], "    "))
    print_case_table(res["cases"], show_hidden_all=False)
    if new_entries:
        print("错题本新增 %d 条：" % len(new_entries))
        for e in new_entries:
            print("  " + e)
    else:
        print("错题本：无新增")

    report = {
        "slug": drill.slug, "title": drill.title, "language": drill.lang, "file": _report_path(sol_path),
        "judgedAt": now_iso(), "score": res["score"], "fullScore": FULL_SCORE, "earned": res["earned"], "total": res["total"],
        "verdict": res["verdict"], "passedCount": res["passedCount"], "caseCount": len(res["cases"]),
        "compileError": res["compileError"], "revealAll": bool(args.reveal_all),
        "cases": [public_case(c) for c in res["cases"]],
        "newMisconceptions": new_entries,
    }
    write_json(os.path.join(drill.dir, "report.json"), report)
    write_text(os.path.join(drill.dir, "report.md"), render_report_md(report))
    write_text(os.path.join(drill.dir, "report.html"), render_report_html(report))
    print("报告：report.json / report.md / report.html")
    return 0 if res["verdict"] == "accepted" else 1


def _is_relative(path):
    try:
        rel = os.path.relpath(path, os.getcwd())
        return not rel.startswith("..")
    except ValueError:
        return False


def _report_path(path):
    """写进报告的作答文件路径：工作区内用相对路径，工作区外只留文件名——报告会被截图、导出、放进仓库，不该带本机绝对路径。"""
    if _is_relative(path):
        return os.path.relpath(path, os.getcwd()).replace(os.sep, "/")
    return os.path.basename(path)


def public_case(c):
    """报告里的用例：未揭开的隐藏用例不带输入输出。"""
    out = {"id": c["id"], "job": c["job"], "isSample": c["isSample"], "score": c["score"], "passed": c["passed"],
           "verdict": c["verdict"], "timeMs": c["timeMs"], "catches": c["catches"], "revealed": c["revealed"]}
    if c["revealed"]:
        out["input"] = c["input"]
        out["expected"] = norm_output(c["expected"])
        out["actual"] = c["stdout"]
        if c["stderr"] and c["verdict"] in ("runtime_error", "time_limit_exceeded"):
            out["stderr"] = c["stderr"][:1000]
    return out


def print_case_table(cases, show_hidden_all):
    print("用例   职责        结果    用时")
    for c in cases:
        status = "通过" if c["passed"] else "未通过"
        tag = ""
        if not c["passed"] and c["verdict"] != "wrong_answer":
            tag = "  " + c["verdict"]
        print("%-6s %-10s %-6s %5dms%s" % (c["id"], c["job"] or "-", status, c["timeMs"], tag))
        reveal = show_hidden_all or c.get("revealed", False)
        if reveal:
            if not c["isSample"] and not show_hidden_all and not c["passed"]:
                print("      （已揭开这条隐藏用例）")
            print("      输入：")
            print(indent_block(c["input"], "        "))
            print("      期望：")
            print(indent_block(norm_output(c["expected"]), "        "))
            if not c["passed"] or show_hidden_all:
                print("      实际：")
                print(indent_block(c["stdout"], "        "))
            if not c["passed"] and c["stderr"] and c["verdict"] in ("runtime_error", "time_limit_exceeded"):
                print("      stderr：")
                print(indent_block(c["stderr"][:800], "        "))
        elif not c["passed"] and c["catches"]:
            print("      这条用例抓的是：%s" % c["catches"])


def fold_line(text):
    """折成单行：所有空白（含换行）压成一个空格。"""
    return " ".join(str(text or "").split())


def append_misconceptions(drill, cases, overall, same_as_starter):
    """追加到 drills/misconceptions.md，同题同条不重复。只记真正的误解：
    该用例 wrong_answer、整题不是 compile_error、作答不是起步骨架原样。TLE / runtime_error 的用例不记。"""
    if overall == "compile_error" or same_as_starter:
        return []
    path = drill.misconceptions_path()
    existing = read_text(path) if os.path.isfile(path) else ""
    existing_lines = [l.strip() for l in existing.split("\n")]
    new_entries = []
    seen_now = set()
    for c in cases:
        if c["passed"] or c["verdict"] != "wrong_answer" or not fold_line(c["catches"]):
            continue
        key = " · %s · %s" % (drill.slug, fold_line(c["catches"]))
        if key in seen_now or any(l.endswith(key) for l in existing_lines):
            continue
        seen_now.add(key)
        new_entries.append("- %s%s" % (today(), key))
    if new_entries:
        header = "" if existing.strip() else "# 错题本\n\n"
        body = existing
        if body and not body.endswith("\n"):
            body += "\n"
        write_text(path, header + body + "\n".join(new_entries) + "\n")
    return new_entries


def _md_cell(text):
    """表格单元格：折成单行并转义竖线。"""
    return fold_line(text).replace("|", "\\|")


def render_report_md(rep):
    lines = ["# 判题报告：%s" % rep["title"], "",
             "- 题号：`%s` · 语言：%s · 判题时间：%s" % (rep["slug"], LANG_LABEL[rep["language"]], rep["judgedAt"]),
             "- 得分：**%s / %d** · 判定：**%s** · 通过 %d/%d 条" % (fmt_score(rep["score"]), rep["fullScore"], rep["verdict"], rep["passedCount"], rep["caseCount"]),
             ""]
    if rep["compileError"]:
        lines += ["## 编译失败", "", "```", rep["compileError"][:1500], "```", ""]
    lines += ["## 用例", "", "| 用例 | 职责 | 结果 | 用时 | 说明 |", "|---|---|---|---|---|"]
    for c in rep["cases"]:
        note = ""
        if not c["passed"]:
            note = c["verdict"] if c["verdict"] != "wrong_answer" else ""
            if c["catches"]:
                note = (note + " · " if note else "") + "抓的是：" + c["catches"]
        lines.append("| %s | %s | %s | %dms | %s |" % (_md_cell(c["id"]), _md_cell(c["job"] or "-"), "通过" if c["passed"] else "未通过", c["timeMs"], _md_cell(note)))
    for c in rep["cases"]:
        if not c.get("revealed"):
            continue
        title = "样例 %s" % c["id"] if c["isSample"] else "隐藏用例 %s（%s）" % (c["id"], "已揭开" if not c["passed"] else "全部揭开")
        lines += ["", "### " + title, "", "输入：", "```", c.get("input", ""), "```", "期望：", "```", c.get("expected", ""), "```"]
        if not c["passed"]:
            lines += ["实际：", "```", c.get("actual", ""), "```"]
            if c.get("stderr"):
                lines += ["stderr：", "```", c["stderr"], "```"]
    lines += ["", "## 错题本新增", ""]
    if rep["newMisconceptions"]:
        lines += rep["newMisconceptions"]
    else:
        lines.append("无")
    lines.append("")
    return "\n".join(lines)


_HTML_CSS = """
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#ffffff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de;
--ok:#1a7f37;--okbg:#dafbe1;--bad:#cf222e;--badbg:#ffebe9;--code:#f0f2f5;--accent:#0969da}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--fg:#e6edf3;--muted:#8b949e;--line:#30363d;
--ok:#3fb950;--okbg:#12261e;--bad:#f85149;--badbg:#2d1416;--code:#0d1117;--accent:#58a6ff}}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.card{max-width:860px;margin:0 auto;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px 28px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px}.meta{color:var(--muted);font-size:13px}
.score{display:flex;align-items:baseline;gap:12px;margin:16px 0}.score b{font-size:40px;line-height:1}
.score .full{color:var(--muted)}.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:13px;font-weight:600}
.badge.ok{background:var(--okbg);color:var(--ok)}.badge.bad{background:var(--badbg);color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:13px}td.ms{white-space:nowrap;color:var(--muted)}
.catches{color:var(--muted);font-size:13px}pre{margin:6px 0 10px;padding:10px 12px;background:var(--code);border:1px solid var(--line);
border-radius:8px;overflow-x:auto;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;word-break:break-all}
.reveal{margin-top:12px;padding:12px 14px;border:1px solid var(--line);border-radius:10px}.reveal h3{margin:0 0 6px;font-size:14px}
.label{font-size:12px;color:var(--muted);margin-top:6px}ul{padding-left:20px}.empty{color:var(--muted)}
"""


def render_report_html(rep):
    e = html.escape
    accepted = rep["verdict"] == "accepted"
    rows = []
    for c in rep["cases"]:
        note = ""
        if not c["passed"]:
            if c["verdict"] != "wrong_answer":
                note = e(c["verdict"])
            if c["catches"]:
                note += ('<div class="catches">这条用例抓的是：%s</div>' % e(c["catches"]))
        rows.append('<tr><td>%s</td><td>%s</td><td><span class="badge %s">%s</span></td><td class="ms">%dms</td><td>%s</td></tr>'
                    % (e(str(c["id"])), e(c["job"] or "-"), "ok" if c["passed"] else "bad", "通过" if c["passed"] else "未通过", c["timeMs"], note))
    reveals = []
    for c in rep["cases"]:
        if not c.get("revealed"):
            continue
        title = "样例 %s" % e(str(c["id"])) if c["isSample"] else "隐藏用例 %s（已揭开）" % e(str(c["id"]))
        block = ['<div class="reveal"><h3>%s</h3>' % title,
                 '<div class="label">输入</div><pre>%s</pre>' % e(c.get("input", "")),
                 '<div class="label">期望输出</div><pre>%s</pre>' % e(c.get("expected", ""))]
        if not c["passed"]:
            block.append('<div class="label">实际输出</div><pre>%s</pre>' % e(c.get("actual", "")))
            if c.get("stderr"):
                block.append('<div class="label">stderr</div><pre>%s</pre>' % e(c["stderr"]))
        block.append("</div>")
        reveals.append("".join(block))
    compile_block = ""
    if rep["compileError"]:
        compile_block = '<h2>编译失败</h2><pre>%s</pre>' % e(rep["compileError"][:1500])
    mis = ("<ul>" + "".join("<li>%s</li>" % e(m[2:] if m.startswith("- ") else m) for m in rep["newMisconceptions"]) + "</ul>") \
        if rep["newMisconceptions"] else '<p class="empty">无</p>'
    return ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>%s · 判题报告</title><style>%s</style></head><body><div class=\"card\">"
            "<h1>%s</h1><div class=\"meta\">%s · %s · %s</div>"
            "<div class=\"score\"><b>%s</b><span class=\"full\">/ %d</span><span class=\"badge %s\">%s</span>"
            "<span class=\"meta\">通过 %d/%d 条</span></div>%s"
            "<h2>用例</h2><table><thead><tr><th>用例</th><th>职责</th><th>结果</th><th>用时</th><th>说明</th></tr></thead><tbody>%s</tbody></table>"
            "%s<h2>错题本新增</h2>%s</div></body></html>\n"
            % (e(rep["title"]), _HTML_CSS, e(rep["title"]), e(rep["slug"]), e(LANG_LABEL[rep["language"]]), e(rep["judgedAt"]),
               fmt_score(rep["score"]), rep["fullScore"], "ok" if accepted else "bad", e(rep["verdict"]),
               rep["passedCount"], rep["caseCount"], compile_block, "".join(rows), "".join(reveals), mis))


# ---------------------------------------------------------------- run

def cmd_run(args):
    drill = Drill(args.drill_dir)
    runtime = require_runtime(drill.lang)
    path = os.path.abspath(args.program)
    if not os.path.isfile(path):
        raise UsageError("程序文件不存在：%s" % path)
    res = judge_source(drill.lang, runtime, read_text(path), drill.cases, drill.time_limit_ms)
    print("试跑：%s（%s）· 程序 %s" % (drill.slug, drill.title, path))
    print("得分 %s / %d · 判定 %s（通过 %d/%d 条）" % (fmt_score(res["score"]), FULL_SCORE, res["verdict"], res["passedCount"], len(res["cases"])))
    if res["compileError"]:
        print("编译失败：")
        print(indent_block(res["compileError"][:1500], "    "))
    for c in res["cases"]:
        c["revealed"] = True
    print_case_table(res["cases"], show_hidden_all=True)
    return 0 if res["verdict"] == "accepted" else 1


# ---------------------------------------------------------------- export

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _inline_html(text):
    parts = []
    pos = 0
    for m in _INLINE_CODE.finditer(text):
        parts.append(_BOLD.sub(r"<strong>\1</strong>", html.escape(text[pos:m.start()])))
        parts.append("<code>%s</code>" % html.escape(m.group(1)))
        pos = m.end()
    parts.append(_BOLD.sub(r"<strong>\1</strong>", html.escape(text[pos:])))
    return "".join(parts)


def md_to_html(md):
    """极简 Markdown → HTML：标题、段落、围栏代码块、无序/有序列表、行内代码与加粗。"""
    out = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    para = []
    list_tag = None

    def flush_para():
        if para:
            out.append("<p>%s</p>" % _inline_html(" ".join(s.strip() for s in para)))
            del para[:]

    def close_list():
        nonlocal list_tag
        if list_tag:
            out.append("</%s>" % list_tag)
            list_tag = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_para()
            close_list()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(code)))
            i += 1
            continue
        if stripped == "":
            flush_para()
            close_list()
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para()
            close_list()
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, _inline_html(m.group(2).strip()), level))
            i += 1
            continue
        m_ul = re.match(r"^[-*+]\s+(.*)$", stripped)
        m_ol = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if m_ul or m_ol:
            flush_para()
            tag = "ul" if m_ul else "ol"
            if list_tag != tag:
                close_list()
                out.append("<%s>" % tag)
                list_tag = tag
            out.append("<li>%s</li>" % _inline_html((m_ul or m_ol).group(1)))
            i += 1
            continue
        if list_tag:
            close_list()
        para.append(line)
        i += 1
    flush_para()
    close_list()
    return "\n".join(out)


def cmd_export(args):
    drill = Drill(args.drill_dir)
    if not os.path.isfile(drill.author_report_path):
        raise UsageError("题包尚未通过 author 验证（没有 .hidden/author-report.json），拒绝导出")
    ar = read_json(drill.author_report_path)
    if not ar.get("ok"):
        raise UsageError("author 验证有 %s 个 ERROR，拒绝导出；请修题后重新运行 judge.py author" % ar.get("errorCount", "?"))
    if ar.get("testsHash") and ar["testsHash"] != sha256_file(drill.tests_path):
        raise UsageError("tests.json 在 author 验证之后被改动过，请重新运行 judge.py author 再导出")
    recorded = ar.get("files")
    if not isinstance(recorded, dict):
        raise UsageError("author-report.json 没有记录文件校验值（旧版本生成），请重新运行 judge.py author 再导出")
    current = drill.file_hashes()
    changed = [label for label in set(recorded) | set(current) if recorded.get(label) != current.get(label)]
    if changed:
        raise UsageError("以下文件在 author 验证之后被改动过（或新增 / 删除）：%s；请重新运行 judge.py author 再导出" % "、".join(sorted(changed)))
    unfilled = [c["id"] for c in drill.cases if c.get("expected") is None]
    if unfilled:
        raise UsageError("用例 %s 的 expected 仍为 null，请重新运行 judge.py author" % " ".join(unfilled))
    derr = difficulty_error(drill.meta.get("difficulty"))
    if derr:
        raise UsageError(derr + "；拒绝导出")
    difficulty = int(drill.meta.get("difficulty"))
    problem_path = drill.problem_path()
    if not os.path.isfile(problem_path):
        raise UsageError("题面不存在：problem.md")
    problem_md = read_text(problem_path)
    if re.search(r"<待回填[^>\n]*>", problem_md):
        raise UsageError("problem.md 里还有「<待回填…>」占位，请把样例输入输出回填进题面后再导出")
    sample = drill.sample_case()
    md_norm = problem_md.replace("\r\n", "\n")
    missing = []
    if sample.get("input", "").replace("\r\n", "\n") not in md_norm:
        missing.append("输入")
    if norm_output(sample.get("expected")) not in md_norm:
        missing.append("期望输出")
    if missing:
        raise UsageError("stem_sample_mismatch：problem.md 没有逐字包含样例用例 %s 的%s，题面示例与 tests.json 必须一致；拒绝导出"
                         % (sample["id"], "与".join(missing)))
    starter_path = drill.starter_path()
    ref_path = drill.reference_path()
    for p in (starter_path, ref_path):
        if not os.path.isfile(p):
            raise UsageError("文件不存在：%s" % p)
    total = sum(_num(c.get("score")) for c in drill.cases)
    intents = []
    for c in drill.cases:
        job = c.get("job") or ("sample" if c.get("isSample") else "hidden")
        intents.append(("%s: %s" % (job, fold_line(c["catches"]))) if c.get("catches") else job)
    pack = {
        "stem": md_to_html(problem_md),
        "difficulty": difficulty,
        "point": FULL_SCORE,
        "coding": {
            "languages": [drill.lang],
            "defaultLanguage": drill.lang,
            "starterCode": {drill.lang: read_text(starter_path)},
            "solutionCode": {drill.lang: read_text(ref_path)},
            "judgeMode": "testcases",
            "ioMode": "stdin_stdout",
            "compareMode": "trim",
            "testCases": [{"input": c.get("input", ""), "expectedOutput": norm_output(c["expected"]),
                           "isSample": bool(c.get("isSample")), "score": _num(c.get("score"))} for c in drill.cases],
            "timeLimitMs": drill.time_limit_ms,
            "memoryLimitMb": 256,
            "totalScore": total,
        },
        "authoring": {
            "caseIntent": intents,
            "mutants": [m["misconception"] for m in drill.load_mutants()],
            "difficultyReason": str(drill.meta.get("difficultyReason") or ""),
        },
        "meta": {"slug": drill.slug, "title": drill.title, "topic": drill.meta.get("topic", ""),
                 "mode": drill.meta.get("mode", ""), "exportedAt": now_iso()},
    }
    out_path = os.path.abspath(args.out) if args.out else os.path.join(drill.dir, "export.json")
    write_json(out_path, pack)
    print("导出：%s（%s）→ %s" % (drill.slug, drill.title, out_path))
    print("用例 %d 条（总分 %s）· 错解 %d 个 · 难度 %d" % (len(drill.cases), total, len(pack["authoring"]["mutants"]), difficulty))
    return 0


# ---------------------------------------------------------------- doctor

def cmd_doctor(args):
    print("coding-drill 环境检查（judge.py 由 Python %d.%d.%d 运行，%s）" % (sys.version_info[0], sys.version_info[1], sys.version_info[2], sys.platform))
    worst = 0
    for lang in LANGS:
        rt = detect_runtime(lang)
        if rt["ok"]:
            where = rt.get("python") or rt.get("node") or rt.get("javac")
            print("  [OK]   %-10s %s（%s）" % (LANG_LABEL[lang], rt["version"], where))
        elif lang == "python":
            print("  [缺失] %-10s %s —— judge.py 自身需要 Python 3.8+" % (LANG_LABEL[lang], rt["reason"]))
            worst = 2
        else:
            print("  [警告] %-10s %s —— 缺 %s 运行时，不出 %s 题" % (LANG_LABEL[lang], rt["reason"], LANG_LABEL[lang], LANG_LABEL[lang]))
    print("提示：没有沙箱，运行前请先审阅生成的代码；每条用例超时 %dms（可在 meta.json 改），编译超时 %d 秒。" % (DEFAULT_TL_MS, COMPILE_TIMEOUT_S))
    return worst


# ---------------------------------------------------------------- 入口

def build_parser():
    p = argparse.ArgumentParser(prog="judge.py", description="coding-drill 判题脚本")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("doctor", help="查看本机可用运行时")
    a = sub.add_parser("author", help="出题验证")
    a.add_argument("drill_dir")
    a.add_argument("--refill", action="store_true", help="允许用参考解实跑覆盖已有的 expected")
    j = sub.add_parser("judge", help="判学生作答")
    j.add_argument("drill_dir")
    j.add_argument("--file", help="作答文件（默认 solution.* / Main.java）")
    j.add_argument("--reveal-all", action="store_true", help="揭开全部隐藏用例")
    j.add_argument("--allow-io", action="store_true", help="跳过作答文件的进程 / 文件 / 网络关键词扫描（确认无害后再加）")
    r = sub.add_parser("run", help="对任意程序跑全部用例")
    r.add_argument("drill_dir")
    r.add_argument("program")
    x = sub.add_parser("export", help="导出题包 JSON")
    x.add_argument("drill_dir")
    x.add_argument("--out", help="输出文件（默认 <drill-dir>/export.json）")
    return p


def _sigterm_to_interrupt(signum, frame):
    raise KeyboardInterrupt()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        signal.signal(signal.SIGTERM, _sigterm_to_interrupt)
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"doctor": cmd_doctor, "author": cmd_author, "judge": cmd_judge, "run": cmd_run, "export": cmd_export}
    if not args.command:
        parser.print_help()
        return 2
    try:
        return handlers[args.command](args)
    except UsageError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中断（正在运行的程序已终止，临时目录已清理）", file=sys.stderr)
        return 2
    except Exception as e:
        print("错误：%s：%s" % (type(e).__name__, e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
