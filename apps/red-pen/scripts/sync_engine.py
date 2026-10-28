#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 red-pen 引擎的脚本同步进应用目录（engine/）。

应用要能独立打包上线，引擎脚本必须在 apps/red-pen/engine/ 里。
这份脚本只做复制，不做改写：源就是仓库里的 red-pen/scripts/，
目标文件与源文件逐字节相同，并把每个文件的 sha256 记进 engine/MANIFEST.json，
方便事后核对「上线跑的是不是同一份校验器」。

用法：
    python3 apps/red-pen/scripts/sync_engine.py            # 同步
    python3 apps/red-pen/scripts/sync_engine.py --check    # 只核对，不写
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.join(APP_DIR, "engine")
REPO_ROOT = os.path.dirname(os.path.dirname(APP_DIR))
SOURCE_DIR = os.path.join(REPO_ROOT, "red-pen", "scripts")

# 引擎运行时需要的三个模块；selftest.py 属于仓库自测，不进应用。
FILES = ("redpen.py", "anchor.py", "banned_words.py")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def source_commit():
    try:
        out = subprocess.run(
            ["git", "-C", REPO_ROOT, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def plan():
    if not os.path.isdir(SOURCE_DIR):
        raise SystemExit("找不到引擎源码目录：red-pen/scripts/（应用需要与母仓同级）")
    rows = []
    for name in FILES:
        src = os.path.join(SOURCE_DIR, name)
        if not os.path.isfile(src):
            raise SystemExit("引擎源码缺文件：%s" % name)
        rows.append((name, src, sha256_file(src)))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="同步 red-pen 引擎脚本到 apps/red-pen/engine/")
    ap.add_argument("--check", action="store_true", help="只核对是否与源码一致，不写文件")
    args = ap.parse_args(argv)

    rows = plan()
    if args.check:
        bad = []
        for name, src, digest in rows:
            dst = os.path.join(ENGINE_DIR, name)
            if not os.path.isfile(dst):
                bad.append("%s 缺失" % name)
            elif sha256_file(dst) != digest:
                bad.append("%s 与源码不一致" % name)
        for line in bad:
            print("[不一致] %s" % line)
        print("核对完成：%s" % ("一致" if not bad else "%d 处不一致" % len(bad)))
        return 0 if not bad else 1

    os.makedirs(ENGINE_DIR, exist_ok=True)
    for name, src, _digest in rows:
        shutil.copyfile(src, os.path.join(ENGINE_DIR, name))
    manifest = {
        "source": "red-pen/scripts",
        "commit": source_commit(),
        "files": {name: digest for name, _src, digest in rows},
    }
    with open(os.path.join(ENGINE_DIR, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    for name, _src, digest in rows:
        print("同步 %s  %s" % (name, digest[:12]))
    print("引擎已同步到 engine/（commit %s）" % (manifest["commit"] or "未知"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
