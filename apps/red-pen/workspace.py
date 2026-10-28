# -*- coding: utf-8 -*-
"""会话工作区：每个访客一个目录，引擎的 CLI 就是这里的唯一入口。

设计上只有一条纪律：**批注能不能上页面，由 `redpen.py review` 说了算。**
本模块不重写任何闸门、不修补 `marks.json`、不动 `draft.*`。
`review` 退出 1 时，这里只把它的 [ERROR] 原样带回去。
"""

import json
import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(APP_DIR, "engine", "redpen.py")

SLUG = "draft-01"
TIMEOUT = 90


class EngineError(Exception):
    """引擎以用法错误（退出 2）结束，或根本没跑起来。"""

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def _env():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


class Workspace(object):
    def __init__(self, root):
        self.root = root
        self.dir = os.path.join(root, "drafts", SLUG)

    # ------------------------------------------------------------ 基础
    def _run(self, args, stdin=None, timeout=TIMEOUT):
        if not os.path.isfile(ENGINE):
            raise EngineError("引擎脚本缺失：apps/red-pen/engine/redpen.py 不在。"
                              "先跑 python3 scripts/sync_engine.py。")
        cmd = [sys.executable, ENGINE] + args
        try:
            proc = subprocess.run(cmd, cwd=self.root, input=stdin, text=True,
                                  capture_output=True, timeout=timeout, env=_env())
        except subprocess.TimeoutExpired:
            raise EngineError("校验器运行超时（%d 秒），请重试。" % timeout)
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _ok(self, rc, out, err, what):
        if rc == 0:
            return out
        detail = (err or out).strip().splitlines()
        raise EngineError("%s 失败（退出码 %d）" % (what, rc), " / ".join(detail[-3:]))

    # ------------------------------------------------------------ 状态
    def exists(self):
        return os.path.isdir(self.dir)

    def draft_path(self):
        if not os.path.isdir(self.dir):
            return None
        for name in sorted(os.listdir(self.dir)):
            if name.startswith("draft."):
                return os.path.join(self.dir, name)
        return None

    def raw_draft(self):
        path = self.draft_path()
        if path is None:
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def version(self):
        hist = os.path.join(self.dir, "history")
        if not os.path.isdir(hist):
            return 1
        return 1 + len([n for n in os.listdir(hist) if n.startswith("v") and n[1:].isdigit()])

    def has_record(self):
        return os.path.isfile(os.path.join(self.dir, "marks.json"))

    def record(self):
        path = os.path.join(self.dir, "marks.json")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def read_brief(self):
        path = os.path.join(self.dir, "brief.json")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------ 收稿
    def init_text(self, text):
        """把正文送进 init（标准输入通道）。返回 (是否新版本, 引擎提示)。"""
        before = self.version() if self.exists() else 0
        rc, out, err = self._run(["init", SLUG, "--from", "-"], stdin=text)
        self._ok(rc, out, err, "收稿")
        after = self.version() if self.exists() else 0
        return after > before, out.strip()

    def set_brief(self, brief):
        """brief.json 只认四个键；这里自己拼，不把用户的表单直接当文件写。"""
        payload = {
            "audience": (brief.get("audience") or "").strip(),
            "purpose": (brief.get("purpose") or "").strip(),
            "worries": [w.strip() for w in (brief.get("worries") or []) if w and w.strip()],
            "lang": brief.get("lang") if brief.get("lang") in ("zh", "en") else "zh",
        }
        os.makedirs(self.dir, exist_ok=True)
        tmp = os.path.join(self.root, ".brief.tmp.json")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        try:
            rc, out, err = self._run(["brief", "set", SLUG, "--from", tmp])
            self._ok(rc, out, err, "写入写作目的")
        finally:
            if os.path.isfile(tmp):
                os.remove(tmp)
        return payload

    def context(self):
        rc, out, err = self._run(["context", SLUG])
        self._ok(rc, out, err, "读取上下文")
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            raise EngineError("上下文包不是合法 JSON。", out[:200])

    # ------------------------------------------------------------ 过闸
    def review(self, marks, context_hash):
        """写 inbox/marks.json → 跑 review。返回结构化结果，绝不吞掉 [ERROR]。"""
        box = os.path.join(self.dir, "inbox")
        os.makedirs(box, exist_ok=True)
        payload = {"context_hash": context_hash, "marks": marks}
        with open(os.path.join(box, "marks.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        rc, out, err = self._run(["review", SLUG])
        if rc == 2:
            raise EngineError("校验器拒绝了这次提交（用法或格式错误）", (err or out).strip()[:400])
        errors = [line[len("[ERROR] "):] for line in out.splitlines() if line.startswith("[ERROR] ")]
        warnings = [line[len("[WARN] "):] for line in out.splitlines() if line.startswith("[WARN] ")]
        return {"ok": rc == 0, "exit": rc, "errors": errors, "warnings": warnings,
                "stdout": out.strip(), "stderr": err.strip()}

    def stats(self):
        """引擎自己的新鲜度判断：退出 1 = 结果已作废。"""
        if not self.has_record():
            return {"ok": False, "stale": True, "lines": ["还没有通过校验的批注。"]}
        rc, out, err = self._run(["stats", SLUG])
        lines = [line for line in out.splitlines() if line.strip()]
        return {"ok": rc == 0, "stale": rc == 1, "lines": lines}

    def check(self):
        rc, out, err = self._run(["check", SLUG])
        return {"ok": rc == 0, "lines": [l for l in out.splitlines() if l.strip()]}

    # ------------------------------------------------------------ 产物
    def report_path(self, version=None):
        if version is None:
            return os.path.join(self.dir, "review.html")
        return os.path.join(self.dir, "history", "v%d" % version, "review.html")

    def archived_record(self, version):
        path = os.path.join(self.dir, "history", "v%d" % version, "marks.json")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def archived_draft(self, version):
        folder = os.path.join(self.dir, "history", "v%d" % version)
        if not os.path.isdir(folder):
            return None
        for name in sorted(os.listdir(folder)):
            if name.startswith("draft."):
                with open(os.path.join(folder, name), "r", encoding="utf-8") as fh:
                    return fh.read()
        return None
