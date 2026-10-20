#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""脱敏门：扫描仓库文本，禁止本机路径 / 用户名 / 回环代理 / 私有绝对路径入仓。

四条规则（与 skill 的 check-desensitized 模板同口径）：
  R1 盘符绝对路径（C:\\ / D:/ 等），占位符 <user> / <repo> 放行
  R2 MSYS 用户路径（/c/Users/…）
  R3 本机用户名（ASUS）与已知用户目录
  R4 回环代理端口（127.0.0.1:<port> / localhost:<port>）

自豁免：本脚本自身（规则里必然写出被禁止的字面量）与 .git/ 目录。
worktree 里 .git 是**文件**不是目录，也要跳过（否则 1 处假红）。

退出码：0 干净 / 1 有命中 / 2 用法错误。
"""

from __future__ import print_function

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", "bench/out"}
SKIP_FILES = {os.path.join(ROOT, "tools", "check-desensitized.py")}
TEXT_EXT = {
    ".md", ".py", ".toml", ".yml", ".yaml", ".json", ".txt", ".cfg", ".ini",
    ".sh", ".ps1", ".mjs", ".js", ".cjs", ".gitignore", ".gitattributes",
}

RULES = [
    (
        "R1 盘符绝对路径",
        re.compile(r"(?<![<\w])[A-Za-z]:[\\/](?!<)(?:Users|ProgramData|Program Files|Windows|Temp)[\\/]"),
    ),
    ("R2 MSYS 用户路径", re.compile(r"/[a-z]/Users/(?!<)")),
    ("R3 本机用户名", re.compile(r"(?<![\w<])ASUS(?![\w>])")),
    ("R4 回环代理端口", re.compile(r"(?:127\.0\.0\.1|localhost):\d{4,5}")),
]

# 占位符 / 公开镜像放行（负向前瞻已处理 <user> 形态；这里处理整行豁免关键词）
ALLOW_LINE = re.compile(r"<user>|<repo>|<local-proxy>|C:/Users/<|pypi\.tuna|goproxy\.cn")


def iter_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT).replace("\\", "/")
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and ("%s/%s" % (rel_dir, d)).lstrip("./") not in SKIP_DIRS
        ]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if full in SKIP_FILES:
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in TEXT_EXT and name not in (".gitignore", ".gitattributes"):
                continue
            yield full


def scan():
    hits = []
    scanned = 0
    for path in iter_files():
        scanned += 1
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except (IOError, OSError):
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for lineno, line in enumerate(lines, 1):
            if ALLOW_LINE.search(line):
                continue
            for label, pattern in RULES:
                if pattern.search(line):
                    hits.append((rel, lineno, label, line.strip()[:120]))
                    break
    return scanned, hits


def main():
    scanned, hits = scan()
    sys.stdout.write("脱敏门 · 4 条规则（盘符 / MSYS 用户路径 / 本机用户名 / 回环代理）\n")
    sys.stdout.write("=" * 56 + "\n")
    for rel, lineno, label, text in hits:
        sys.stdout.write("FAIL  %s:%d  [%s]  %s\n" % (rel, lineno, label, text))
    sys.stdout.write("=" * 56 + "\n")
    sys.stdout.write("这轮扫到：%d 份文本文件；豁免：本脚本自身 + .git/\n" % scanned)
    sys.stdout.write("结论: %s\n" % ("全绿" if not hits else "%d 处命中" % len(hits)))
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())
