#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""红笔改稿 · 独立网页应用的服务端（Python 标准库，单端口）。

职责边界：
* 收稿、写 brief、拿上下文包、过闸、出报告 —— 全部交给 `engine/redpen.py`，
  本文件不复制任何闸门逻辑。
* 模型调用在服务端完成（`llm.py`），浏览器拿不到任何凭据。
* 每个访客一个会话目录，稿件与下载文件按会话隔离。

启动：
    PORT=8787 python3 server.py
"""

import json
import mimetypes
import os
import re
import secrets
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import engine_bridge
import llm
from workspace import EngineError, Workspace

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")
DATA_DIR = os.environ.get("REDPEN_DATA_DIR") or os.path.join(APP_DIR, ".data")
SESSION_DIR = os.path.join(DATA_DIR, "sessions")

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8787"))

MAX_DRAFT_CHARS = 20000
MAX_BRIEF_FIELD = 300
MAX_WORRIES = 5
COOKIE = "rp_sid"
SID_RE = re.compile(r"^[a-f0-9]{32}$")
JOB_TIMEOUT = 300
MAX_ROUNDS = 3          # 首轮 + 最多两次自动修复

# 频率限制：动作 -> (次数, 窗口秒数)。按会话计。
RATE = {
    "draft": (30, 3600),
    "brief": (30, 3600),
    "generate": (10, 3600),
    "download": (120, 3600),
}
IP_RATE = (60, 3600)

JOBS = {}
JOBS_LOCK = threading.Lock()
RATE_HITS = {}
RATE_LOCK = threading.Lock()
SESSION_LOCKS = {}
SESSION_LOCKS_LOCK = threading.Lock()
JOB_SLOTS = threading.Semaphore(4)

STAGES = ("读取稿件", "分析表达", "校验引用", "整理红笔稿")


# ---------------------------------------------------------------- 会话

def session_root(sid):
    return os.path.join(SESSION_DIR, sid)


def ensure_session_dir(sid):
    root = session_root(sid)
    os.makedirs(os.path.join(root, "drafts"), exist_ok=True)
    meta = os.path.join(root, "meta.json")
    if not os.path.isfile(meta):
        with open(meta, "w", encoding="utf-8") as fh:
            json.dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S")}, fh)
    return root


def session_lock(sid):
    with SESSION_LOCKS_LOCK:
        lock = SESSION_LOCKS.get(sid)
        if lock is None:
            lock = threading.Lock()
            SESSION_LOCKS[sid] = lock
        return lock


def rate_ok(key, limit, window):
    now = time.time()
    with RATE_LOCK:
        hits = [t for t in RATE_HITS.get(key, []) if now - t < window]
        if len(hits) >= limit:
            RATE_HITS[key] = hits
            return False
        hits.append(now)
        RATE_HITS[key] = hits
        return True


# ---------------------------------------------------------------- 任务

def new_job(sid, request_id):
    job = {
        "id": secrets.token_hex(8),
        "sid": sid,
        "request_id": request_id,
        "status": "running",
        "stages": [{"name": name, "state": "pending", "detail": ""} for name in STAGES],
        "round": 1,
        "error": None,
        "result": None,
        "simulated": False,
        "started": time.time(),
    }
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    return job


def job_for(sid, request_id):
    with JOBS_LOCK:
        for job in JOBS.values():
            if job["sid"] == sid and request_id and job["request_id"] == request_id:
                return job
    return None


def running_job(sid):
    with JOBS_LOCK:
        for job in JOBS.values():
            if job["sid"] == sid and job["status"] == "running":
                return job
    return None


def set_stage(job, index, state, detail=""):
    job["stages"][index]["state"] = state
    if detail:
        job["stages"][index]["detail"] = detail


def public_job(job):
    data = {k: job[k] for k in ("id", "status", "stages", "round", "error", "simulated")}
    data["elapsed"] = round(time.time() - job["started"], 1)
    if job["status"] == "done":
        data["result"] = job["result"]
    return data


# ---------------------------------------------------------------- 生成流程

def run_job(job, ws):
    """真实阶段：读稿 → 调模型 → 过闸 → 出报告。每一步都有引擎或网络调用的实际结果。"""
    try:
        # 1 读取稿件：重新拿一次上下文包，保证 context_hash 来自引擎而不是上一屏的缓存
        set_stage(job, 0, "active")
        ctx = ws.context()
        set_stage(job, 0, "done", "第 %d 版 · 正文 %d 字" % (ctx["version"], len(ctx["draft_text"])))

        # 2/3 分析 → 校验：模型给批注，引擎说行不行；不过就带着原因再写一次
        feedback = None
        last = None
        for attempt in range(1, MAX_ROUNDS + 1):
            job["round"] = attempt
            set_stage(job, 1, "active", "第 %d 轮" % attempt if attempt > 1 else "")
            marks, meta = llm.generate(ctx, feedback, raw_draft=ws.raw_draft())
            job["simulated"] = meta.get("simulated", False)
            set_stage(job, 1, "done", "模型给出 %d 条批注%s" % (
                len(marks), "（模拟）" if meta.get("simulated") else ""))
            set_stage(job, 2, "active", "第 %d 轮校验" % attempt)
            review = ws.review(marks, ctx["context_hash"])
            last = review
            if review["ok"]:
                set_stage(job, 2, "done", "通过 · %s" % _ratio_text(ws))
                break
            set_stage(job, 2, "failed", "第 %d 轮没过：%d 处不合格" % (attempt, len(review["errors"])))
            if attempt == MAX_ROUNDS:
                raise JobFailure(
                    "校验没有通过（试了 %d 轮）。校验器的原话在下面，稿件和写作目的都保留着，可以直接重试。"
                    % MAX_ROUNDS,
                    errors=review["errors"], warnings=review["warnings"])
            feedback = "\n".join("- %s" % line for line in review["errors"][:12])
            set_stage(job, 2, "pending", "退回重写")

        # 4 整理红笔稿
        set_stage(job, 3, "active")
        record = ws.record()
        if record is None:
            raise JobFailure("校验通过了但读不到 marks.json，请重试。")
        payload = build_view(ws, record)
        payload["warnings"] = last["warnings"] if last else []
        payload["provider"] = meta.get("provider")
        payload["model"] = meta.get("model")
        payload["simulated"] = meta.get("simulated", False)
        payload["rounds"] = job["round"]
        payload["stats"] = ws.stats()["lines"]
        set_stage(job, 3, "done", "%d 条批注 · 钉住 %d 条" % (payload["total"], payload["anchored_count"]))
        job["result"] = payload
        job["status"] = "done"
    except JobFailure as exc:
        job["status"] = "failed"
        job["error"] = {"message": exc.message, "errors": exc.errors, "warnings": exc.warnings}
        for stage in job["stages"]:
            if stage["state"] == "active":
                stage["state"] = "failed"
    except llm.LLMError as exc:
        job["status"] = "failed"
        job["error"] = {"message": exc.message, "code": exc.code, "errors": [], "warnings": []}
        for stage in job["stages"]:
            if stage["state"] == "active":
                stage["state"] = "failed"
    except EngineError as exc:
        job["status"] = "failed"
        job["error"] = {"message": exc.message, "detail": exc.detail, "errors": [], "warnings": []}
        for stage in job["stages"]:
            if stage["state"] == "active":
                stage["state"] = "failed"
    except Exception:
        traceback.print_exc()
        job["status"] = "failed"
        job["error"] = {"message": "服务端出了意外错误，输入还在，可以重试。", "errors": [], "warnings": []}
        for stage in job["stages"]:
            if stage["state"] == "active":
                stage["state"] = "failed"
    finally:
        job["finished"] = time.time()


class JobFailure(Exception):
    def __init__(self, message, errors=None, warnings=None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []
        self.warnings = warnings or []


def _ratio_text(ws):
    record = ws.record() or {}
    marks = record.get("marks") or []
    anchored = sum(1 for m in marks if m.get("anchored"))
    ratio = record.get("anchored_ratio") or 0
    return "锚定率 %d%%（%d/%d）" % (round(ratio * 100), anchored, len(marks))


def build_view(ws, record):
    raw = ws.raw_draft()
    ctx = ws.context()
    vm = engine_bridge.view_model(raw, record, ctx["draft_text"])
    marks = record.get("marks") or []
    counts = record.get("level_counts") or {}
    return {
        "version": record.get("version") or ws.version(),
        "at": record.get("at"),
        "anchored_ratio": record.get("anchored_ratio") or 0.0,
        "counts": counts,
        "blocks": vm["blocks"],
        "marks": vm["marks"],
        "unlocated": vm["unlocated"],
        "priority": vm["priority"],
        "total": vm["total"],
        "anchored_count": vm["anchored_count"],
        "brief": ctx["brief"],
    }


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "redpen-app/1.0"
    protocol_version = "HTTP/1.1"

    # -------------------------------------------------- 工具
    def _cookie_sid(self):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and SID_RE.match(value or ""):
                return value
        return None

    def _sid(self):
        sid = self._cookie_sid()
        if sid:
            return sid
        sid = secrets.token_hex(16)
        self._new_sid = sid
        return sid

    def _send(self, code, body, content_type="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        sid = getattr(self, "_new_sid", None)
        if sid:
            secure = "; Secure" if self._is_https() else ""
            self.send_header("Set-Cookie", "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000%s"
                             % (COOKIE, sid, secure))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _is_https(self):
        proto = (self.headers.get("X-Forwarded-Proto") or "").lower()
        return proto == "https"

    def _json(self, code, payload, extra=None):
        self._send(code, json.dumps(payload, ensure_ascii=False), extra=extra)

    def _error(self, code, message, **extra):
        payload = {"ok": False, "message": message}
        payload.update(extra)
        self._json(code, payload)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise ValueError("请求体太大")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("请求体不是合法的 UTF-8 JSON")
        if not isinstance(data, dict):
            raise ValueError("请求体应当是一个 JSON 对象")
        return data

    def _client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def log_message(self, fmt, *args):
        # 只记方法、路径、状态；不记请求体，稿件内容不进日志。
        print("%s %s" % (time.strftime("%H:%M:%S"), fmt % args), flush=True)

    # -------------------------------------------------- 路由
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/":
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/bootstrap":
                return self._bootstrap()
            if path == "/api/state":
                return self._state()
            if path == "/api/job":
                return self._job(query)
            if path in ("/api/report", "/api/download"):
                return self._report(query, download=path.endswith("download"))
            if path == "/healthz":
                return self._json(200, {"ok": True})
            return self._error(404, "没有这个地址。")
        except Exception:
            traceback.print_exc()
            return self._error(500, "服务端出了意外错误。")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/draft":
                return self._draft()
            if path == "/api/brief":
                return self._brief()
            if path == "/api/generate":
                return self._generate()
            return self._error(404, "没有这个地址。")
        except ValueError as exc:
            return self._error(400, str(exc))
        except Exception:
            traceback.print_exc()
            return self._error(500, "服务端出了意外错误。")

    # -------------------------------------------------- 静态
    def _static(self, name):
        safe = os.path.normpath(name).lstrip("/")
        if safe.startswith("..") or os.path.isabs(safe):
            return self._error(404, "没有这个文件。")
        full = os.path.join(STATIC_DIR, safe)
        if not os.path.isfile(full):
            return self._error(404, "没有这个文件。")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            body = fh.read()
        extra = {"Cache-Control": "no-cache"}
        if safe.endswith(".html"):
            extra["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'")
        return self._send(200, body, ctype, extra)

    # -------------------------------------------------- 会话
    def _ws(self):
        sid = self._sid()
        root = ensure_session_dir(sid)
        return sid, root, Workspace(root)

    def _bootstrap(self):
        sid, root, ws = self._ws()
        sample_path = os.path.join(STATIC_DIR, "sample-notice.txt")
        sample = ""
        if os.path.isfile(sample_path):
            with open(sample_path, "r", encoding="utf-8") as fh:
                sample = fh.read()
        manifest = {}
        mpath = os.path.join(APP_DIR, "engine", "MANIFEST.json")
        if os.path.isfile(mpath):
            with open(mpath, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
        return self._json(200, {
            "ok": True,
            "model": llm.status(),
            "engine": {"ready": engine_bridge.engine_ready(),
                       "commit": (manifest.get("commit") or "")[:12]},
            "sample": sample,
            "limits": {"draft_chars": MAX_DRAFT_CHARS},
            "state": self._state_payload(ws),
        })

    def _state_payload(self, ws):
        payload = {"has_draft": False, "version": 0}
        if not ws.exists():
            return payload
        raw = ws.raw_draft()
        brief = ws.read_brief() or {}
        payload.update({
            "has_draft": raw is not None,
            "version": ws.version(),
            "chars": len(raw or ""),
            "raw": raw or "",
            "brief": brief,
        })
        record = ws.record()
        if record and raw is not None:
            stats = ws.stats()
            payload["review"] = {
                "exists": True,
                "version": record.get("version"),
                "at": record.get("at"),
                "stale": stats["stale"],
                "stats_lines": stats["lines"],
            }
            if not stats["stale"]:
                try:
                    payload["view"] = build_view(ws, record)
                except Exception:
                    payload["view"] = None
                    payload["review"]["render_error"] = True
        else:
            payload["review"] = {"exists": False}
        return payload

    def _state(self):
        _sid, _root, ws = self._ws()
        return self._json(200, {"ok": True, "state": self._state_payload(ws)})

    # -------------------------------------------------- 收稿
    def _draft(self):
        data = self._body()
        text = data.get("text")
        if not isinstance(text, str):
            raise ValueError("缺少稿件正文。")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            return self._error(400, "稿件是空的，先贴一段文字进来。")
        if len(text) > MAX_DRAFT_CHARS:
            return self._error(413, "稿件太长：%d 字，上限 %d 字。先切成一节一节地批。"
                               % (len(text), MAX_DRAFT_CHARS))
        sid, _root, ws = self._ws()
        if not rate_ok(("draft", sid), *RATE["draft"]):
            return self._error(429, "交稿太频繁了，休息一下再试。")
        with session_lock(sid):
            try:
                created, note = ws.init_text(text)
            except EngineError as exc:
                return self._error(400, exc.message, detail=exc.detail)
            ctx = ws.context()
        return self._json(200, {
            "ok": True,
            "created_version": created,
            "version": ctx["version"],
            "chars": len(ctx["draft_text"]),
            "note": note.splitlines()[0] if note else "",
            "brief": ws.read_brief() or {},
        })

    # -------------------------------------------------- 写作目的
    def _brief(self):
        data = self._body()
        audience = (data.get("audience") or "")
        purpose = (data.get("purpose") or "")
        worries = data.get("worries") or []
        if not isinstance(audience, str) or not isinstance(purpose, str):
            raise ValueError("audience / purpose 应当是字符串。")
        if not isinstance(worries, list) or any(not isinstance(w, str) for w in worries):
            raise ValueError("worries 应当是字符串数组。")
        if len(audience) > MAX_BRIEF_FIELD or len(purpose) > MAX_BRIEF_FIELD:
            return self._error(400, "每一项最多 %d 字。" % MAX_BRIEF_FIELD)
        worries = [w.strip() for w in worries if w.strip()][:MAX_WORRIES]
        if any(len(w) > MAX_BRIEF_FIELD for w in worries):
            return self._error(400, "「最担心」每一条最多 %d 字。" % MAX_BRIEF_FIELD)
        sid, _root, ws = self._ws()
        if not ws.exists() or ws.raw_draft() is None:
            return self._error(409, "还没有稿子，先交稿。")
        if not rate_ok(("brief", sid), *RATE["brief"]):
            return self._error(429, "改得太频繁了，稍后再试。")
        lang = data.get("lang") if data.get("lang") in ("zh", "en") else _guess_lang(ws.raw_draft())
        with session_lock(sid):
            before = ws.record()
            brief = ws.set_brief({"audience": audience, "purpose": purpose,
                                  "worries": worries, "lang": lang})
            ctx = ws.context()
        changed = before is not None and before.get("context_hash") != ctx["context_hash"]
        return self._json(200, {
            "ok": True,
            "brief": brief,
            "version": ctx["version"],
            "chars": len(ctx["draft_text"]),
            "invalidated": bool(changed),
        })

    # -------------------------------------------------- 生成
    def _generate(self):
        data = self._body()
        request_id = data.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("缺少 request_id。")
        request_id = request_id.strip()[:64]
        sid, _root, ws = self._ws()
        if not ws.exists() or ws.raw_draft() is None:
            return self._error(409, "还没有稿子，先交稿。")
        brief = ws.read_brief() or {}
        existing = job_for(sid, request_id)
        if existing:
            return self._json(200, {"ok": True, "job": public_job(existing), "reused": True})
        running = running_job(sid)
        if running:
            return self._json(200, {"ok": True, "job": public_job(running), "reused": True})
        st = llm.status()
        if not st["configured"]:
            return self._error(503, st["note"], model=st)
        if not rate_ok(("generate", sid), *RATE["generate"]):
            return self._error(429, "这一小时里已经批了太多次，休息一下再试。")
        if not JOB_SLOTS.acquire(blocking=False):
            return self._error(503, "现在同时在批的稿件有点多，过一会儿再试。")
        job = new_job(sid, request_id)

        def worker():
            try:
                with session_lock(sid):
                    run_job(job, ws)
            finally:
                JOB_SLOTS.release()

        threading.Thread(target=worker, daemon=True).start()
        return self._json(200, {"ok": True, "job": public_job(job), "reused": False})

    def _job(self, query):
        job_id = (query.get("id") or [""])[0]
        sid = self._sid()
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if job is None or job["sid"] != sid:
            return self._error(404, "没有这个任务。")
        if job["status"] == "running" and time.time() - job["started"] > JOB_TIMEOUT:
            job["status"] = "failed"
            job["error"] = {"message": "这个任务超时了，输入还在，可以重试。", "errors": [], "warnings": []}
        return self._json(200, {"ok": True, "job": public_job(job)})

    # -------------------------------------------------- 报告与下载
    def _report(self, query, download=False):
        sid, _root, ws = self._ws()
        if not ws.exists():
            return self._error(404, "还没有生成过红笔稿。")
        raw_version = (query.get("version") or [""])[0]
        if raw_version:
            if not raw_version.isdigit():
                return self._error(400, "版本号不对。")
            version = int(raw_version)
            if version < 1 or version > ws.version():
                return self._error(404, "没有这一版。")
            path = ws.report_path(None if version == ws.version() else version)
        else:
            version = ws.version()
            path = ws.report_path()
        if not os.path.isfile(path):
            return self._error(404, "这一版还没有红笔稿。")
        with open(path, "rb") as fh:
            body = fh.read()
        headers = {"Cache-Control": "no-store"}
        if download:
            name = "红笔稿-第%d版.html" % version
            headers["Content-Disposition"] = "attachment; filename=\"redpen-v%d.html\"; filename*=UTF-8''%s" % (
                version, urllib.parse.quote(name))
        else:
            headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:")
            headers["Content-Disposition"] = "inline"
        return self._send(200, body, "text/html; charset=utf-8", headers)


def _guess_lang(text):
    letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return "en" if letters > cjk * 3 else "zh"


def main():
    os.makedirs(SESSION_DIR, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("红笔改稿 · 服务已启动：http://%s:%d" % (HOST, PORT), flush=True)
    print("模型：%s" % llm.status()["note"], flush=True)
    if not engine_bridge.engine_ready():
        print("[警告] engine/ 里缺引擎脚本，先跑 python3 scripts/sync_engine.py", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)


if __name__ == "__main__":
    main()
