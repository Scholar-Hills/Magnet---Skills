#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用层验收脚本：真的起服务、真的收稿、真的过闸。

只用标准库。每一项都打 PASS/FAIL，退出码非 0 表示有失败项。
模拟通道（REDPEN_ALLOW_MOCK=1）只用来跑通链路，结果会标 simulated，
脚本会如实说明「模型这一段不是真实调用」。

用法：
    python3 tests/e2e.py
"""

import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(APP_DIR, "server.py")
SAMPLE = os.path.join(APP_DIR, "static", "sample-notice.txt")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  —— " + detail) if detail and not ok else ""))
    return ok


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class Client(object):
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def raw(self, path, body=None, method=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(self.base + path, data=data, headers=headers,
                                     method=method or ("POST" if data else "GET"))
        try:
            with self.opener.open(req, timeout=60) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)

    def call(self, path, body=None):
        status, raw, _headers = self.raw(path, body)
        try:
            return status, json.loads(raw.decode("utf-8"))
        except Exception:
            return status, {"_raw": raw[:200]}

    def cookie(self):
        for cookie in self.jar:
            if cookie.name == "rp_sid":
                return cookie.value
        return None


class Server(object):
    def __init__(self, data_dir, extra_env=None):
        self.data_dir = data_dir
        self.port = free_port()
        env = dict(os.environ)
        env.update({
            "PORT": str(self.port),
            "HOST": "127.0.0.1",
            "REDPEN_DATA_DIR": data_dir,
            "REDPEN_ALLOW_MOCK": "1",
            "PYTHONUNBUFFERED": "1",
        })
        env.pop("REDPEN_FAULT", None)
        env.pop("REDPEN_LLM_BASE_URL", None)
        env.pop("REDPEN_LLM_API_KEY", None)
        env.update(extra_env or {})
        self.proc = subprocess.Popen([sys.executable, SERVER], cwd=APP_DIR, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.base = "http://127.0.0.1:%d" % self.port
        self._wait()

    def _wait(self):
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(self.base + "/healthz", timeout=1) as resp:
                    if resp.status == 200:
                        return
            except Exception:
                time.sleep(0.15)
        raise RuntimeError("服务没有起来")

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def wait_job(client, job_id, limit=90):
    deadline = time.time() + limit
    job = None
    while time.time() < deadline:
        status, data = client.call("/api/job?id=" + job_id)
        job = data.get("job") or {}
        if job.get("status") != "running":
            return job
        time.sleep(0.25)
    return job or {"status": "timeout"}


def sample_text():
    with open(SAMPLE, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- 用例

def test_main_flow(base_env):
    """1 收稿 → 生成 → 校验 → 定位 → 下载；2 第二版；3 原样提交。"""
    data = tempfile.mkdtemp(prefix="rp-data-")
    server = Server(data, base_env)
    client = Client(server.base)
    try:
        status, boot = client.call("/api/bootstrap")
        check("首页可用（/api/bootstrap 200）", status == 200 and boot.get("ok"))
        check("引擎脚本就位", boot.get("engine", {}).get("ready") is True)

        status, draft = client.call("/api/draft", {"text": sample_text()})
        check("交稿成功，收成第 1 版", status == 200 and draft.get("version") == 1,
              json.dumps(draft, ensure_ascii=False)[:200])

        status, brief = client.call("/api/brief", {
            "audience": "小学生家长，多数在通勤路上用手机读",
            "purpose": "读完知道改到哪天、要怎么回复",
            "worries": ["读起来像在推卸责任", "截止日期说不清"],
        })
        check("写作目的写入 brief", status == 200 and brief.get("brief", {}).get("lang") == "zh")

        status, gen = client.call("/api/generate", {"request_id": "flow-1"})
        job = wait_job(client, gen["job"]["id"]) if status == 200 else {}
        check("生成任务完成（真实过闸）", job.get("status") == "done",
              json.dumps(job.get("error"), ensure_ascii=False)[:300])
        result = job.get("result") or {}
        check("四个阶段都跑完", all(s["state"] == "done" for s in job.get("stages", [])),
              json.dumps(job.get("stages"), ensure_ascii=False)[:300])
        check("批注数量与锚定数一致", result.get("total") == len(result.get("marks", [])) + len(result.get("unlocated", [])),
              "total=%s located=%s unlocated=%s" % (result.get("total"), len(result.get("marks", [])),
                                                    len(result.get("unlocated", []))))
        check("有批注钉回原文", result.get("anchored_count", 0) > 0)
        check("模拟结果被标注", result.get("simulated") is True)

        # 定位区间必须真的能切出那句引文
        spans_ok = True
        for mark in result.get("marks", [])[:8]:
            block = result["blocks"][mark["block"]]
            piece = block["text"][mark["start"]:mark["end"]]
            if not mark["quote"].startswith(piece[:6]):
                spans_ok = False
        check("定位区间与引文对得上", spans_ok)

        status, raw, headers = client.raw("/api/download?version=1")
        body = raw.decode("utf-8", "replace")
        check("下载红笔稿（HTML）", status == 200 and "红笔改稿" in body and "anchor" not in headers.get("Content-Type", ""),
              "status=%s" % status)
        check("下载件是引擎原样渲染", "未能定位" in body or "批注（" in body)

        status, report, _ = client.raw("/api/report?version=1")
        check("引擎原页可打开", status == 200 and len(report) > 2000)

        # 3 原样提交不虚增版本
        status, same = client.call("/api/draft", {"text": sample_text()})
        check("原样提交不生成新版本", status == 200 and same.get("created_version") is False
              and same.get("version") == 1, json.dumps(same, ensure_ascii=False)[:200])

        # 2 用户自己改一句 → 第 2 版
        revised = sample_text().replace("我们也很无奈，希望各位家长理解",
                                        "具体安排由区里统一确定，改期不是学校单方面的决定")
        status, second = client.call("/api/draft", {"text": revised})
        check("改一句后收成第 2 版", status == 200 and second.get("created_version") is True
              and second.get("version") == 2, json.dumps(second, ensure_ascii=False)[:200])

        status, gen2 = client.call("/api/generate", {"request_id": "flow-2"})
        job2 = wait_job(client, gen2["job"]["id"]) if status == 200 else {}
        check("第 2 版生成完成", job2.get("status") == "done",
              json.dumps(job2.get("error"), ensure_ascii=False)[:300])
        result2 = job2.get("result") or {}
        compare = [line for line in (result2.get("stats") or []) if "上一版" in line]
        check("报出与上一版的比较", any("消失了" in line for line in compare), str(compare)[:200])
        check("第 2 版批注仍钉在原文上", result2.get("anchored_count", 0) > 0)

        status, _raw, _h = client.raw("/api/report?version=1")
        check("第 1 版仍能查看", status == 200)

        # 会话隔离
        other = Client(server.base)
        status, other_state = other.call("/api/state")
        check("另一个访客看不到这份稿子",
              status == 200 and other_state.get("state", {}).get("has_draft") is False)
        status, _r, _h = other.raw("/api/download?version=1")
        check("另一个访客下载不到这份红笔稿", status == 404)

        # 输入上限
        status, too_long = client.call("/api/draft", {"text": "字" * 20001})
        check("超长稿件被拒（413）", status == 413, str(status))

        # 重复提交同一个 request_id 不重复建任务
        status, dup = client.call("/api/generate", {"request_id": "flow-2"})
        check("同一 request_id 复用同一个任务",
              status == 200 and dup.get("job", {}).get("id") == gen2.get("job", {}).get("id"))
    finally:
        server.stop()
        shutil.rmtree(data, ignore_errors=True)


def test_bad_quote(base_env):
    """4 故意交一条不存在的引文：应用如实列出「未能定位」，不伪造位置。"""
    data = tempfile.mkdtemp(prefix="rp-data-")
    env = dict(base_env)
    env["REDPEN_FAULT"] = "bad_quote"
    server = Server(data, env)
    client = Client(server.base)
    try:
        client.call("/api/draft", {"text": sample_text()})
        client.call("/api/brief", {"audience": "家长", "purpose": "知道改期", "worries": []})
        status, gen = client.call("/api/generate", {"request_id": "bad-1"})
        job = wait_job(client, gen["job"]["id"]) if status == 200 else {}
        check("含错引文时任务仍按校验结果结束", job.get("status") in ("done", "failed"), str(job.get("status")))
        result = job.get("result") or {}
        unlocated = result.get("unlocated") or []
        check("错引文被单列成「未能定位」", len(unlocated) >= 1, json.dumps(unlocated, ensure_ascii=False)[:300])
        if unlocated:
            item = unlocated[0]
            check("未定位条目带原因、没有被摆进正文",
                  bool(item.get("reason")) and item.get("block") is None and item.get("start") is None,
                  json.dumps(item, ensure_ascii=False)[:300])
        check("锚定率按真实比例给出",
              abs(result.get("anchored_ratio", 0) - result.get("anchored_count", 0) / max(1, result.get("total", 1))) < 0.0002)
    finally:
        server.stop()
        shutil.rmtree(data, ignore_errors=True)


def test_shape_failure(base_env):
    """5 形状不合格：校验器拒收，应用把原话交回，不伪造结果。"""
    data = tempfile.mkdtemp(prefix="rp-data-")
    env = dict(base_env)
    env["REDPEN_FAULT"] = "shape"
    server = Server(data, env)
    client = Client(server.base)
    try:
        client.call("/api/draft", {"text": sample_text()})
        client.call("/api/brief", {"audience": "家长", "purpose": "知道改期", "worries": []})
        status, gen = client.call("/api/generate", {"request_id": "shape-1"})
        job = wait_job(client, gen["job"]["id"]) if status == 200 else {}
        check("形状不合格时任务失败", job.get("status") == "failed", str(job.get("status")))
        errors = (job.get("error") or {}).get("errors") or []
        check("失败时带回校验器原话", len(errors) >= 1, json.dumps(job.get("error"), ensure_ascii=False)[:300])
        check("失败后没有生成红笔稿", client.raw("/api/report?version=1")[0] == 404)
        status, state = client.call("/api/state")
        check("失败后稿件仍在", state.get("state", {}).get("has_draft") is True)
    finally:
        server.stop()
        shutil.rmtree(data, ignore_errors=True)


def test_llm_failure_then_retry(base_env):
    """5 模型调用失败：输入保留、错误可读、换个正常服务就能重试成功。"""
    data = tempfile.mkdtemp(prefix="rp-data-")
    env = dict(base_env)
    env["REDPEN_FAULT"] = "llm_error"
    first = Server(data, env)
    cookie = None
    try:
        client = Client(first.base)
        client.call("/api/draft", {"text": sample_text()})
        client.call("/api/brief", {"audience": "家长", "purpose": "知道改期", "worries": []})
        status, gen = client.call("/api/generate", {"request_id": "fail-1"})
        job = wait_job(client, gen["job"]["id"]) if status == 200 else {}
        check("模型调用失败时任务失败", job.get("status") == "failed", str(job.get("status")))
        message = (job.get("error") or {}).get("message") or ""
        check("失败信息可读", "失败" in message or "模型" in message, message[:120])
        cookie = client.cookie()
    finally:
        first.stop()

    second = Server(data, base_env)
    try:
        client = Client(second.base)
        client.jar.set_cookie(http.cookiejar.Cookie(
            version=0, name="rp_sid", value=cookie or "", port=None, port_specified=False,
            domain="127.0.0.1", domain_specified=False, domain_initial_dot=False,
            path="/", path_specified=True, secure=False, expires=None, discard=True,
            comment=None, comment_url=None, rest={}, rfc2109=False))
        status, state = client.call("/api/state")
        check("重试时稿件还在", state.get("state", {}).get("has_draft") is True)
        status, gen = client.call("/api/generate", {"request_id": "fail-2"})
        job = wait_job(client, gen["job"]["id"]) if status == 200 else {}
        check("同一篇稿子可以重试成功", job.get("status") == "done",
              json.dumps(job.get("error"), ensure_ascii=False)[:300])
    finally:
        second.stop()
        shutil.rmtree(data, ignore_errors=True)


def test_unconfigured_model():
    """没有模型配置时如实报错，不伪造批注。"""
    data = tempfile.mkdtemp(prefix="rp-data-")
    server = Server(data, {})
    try:
        # 关掉模拟通道：起一个不带 REDPEN_ALLOW_MOCK 的实例
        server.stop()
        env = dict(os.environ)
        env.update({"PORT": str(free_port()), "HOST": "127.0.0.1", "REDPEN_DATA_DIR": data})
        for key in ("REDPEN_ALLOW_MOCK", "REDPEN_FAULT", "REDPEN_LLM_BASE_URL",
                    "REDPEN_LLM_API_KEY", "REDPEN_LLM_MODEL"):
            env.pop(key, None)
        proc = subprocess.Popen([sys.executable, SERVER], cwd=APP_DIR, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = "http://127.0.0.1:%s" % env["PORT"]
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1)
                break
            except Exception:
                time.sleep(0.15)
        try:
            client = Client(base)
            status, boot = client.call("/api/bootstrap")
            check("未配置模型时状态是未配置", boot.get("model", {}).get("configured") is False)
            client.call("/api/draft", {"text": sample_text()})
            status, gen = client.call("/api/generate", {"request_id": "nokey-1"})
            check("未配置模型时生成被拒（503）", status == 503, str(status))
            check("拒的时候说清缺什么", "REDPEN_LLM" in (gen.get("message") or ""), gen.get("message", "")[:120])
        finally:
            proc.terminate()
            proc.wait(timeout=8)
    finally:
        shutil.rmtree(data, ignore_errors=True)


def main():
    base_env = {}
    test_main_flow(base_env)
    test_bad_quote(base_env)
    test_shape_failure(base_env)
    test_llm_failure_then_retry(base_env)
    test_unconfigured_model()

    failed = [row for row in RESULTS if not row[1]]
    print("\n%d 项检查，%d 项通过，%d 项失败" % (len(RESULTS), len(RESULTS) - len(failed), len(failed)))
    if failed:
        print("失败项：")
        for name, _ok, detail in failed:
            print("  - %s %s" % (name, detail))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
