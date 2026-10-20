# -*- coding: utf-8 -*-
"""零网络守门：包内不得出现网络客户端 import / 调用。

判据落 AST + 源码文本两层：
- AST：``import socket`` / ``from urllib import request`` 等（含 ``from X import Y`` 与相对导入）
- 文本：``urlopen`` / ``http://`` 等（兜底，防止动态 import）
"""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "tzaudit")

FORBIDDEN_ROOTS = {"socket", "urllib", "http", "requests", "ftplib", "telnetlib",
                   "smtplib", "ssl", "xmlrpc", "asyncio", "aiohttp", "httpx"}
FORBIDDEN_TEXT = ["urlopen", "urllib", "requests.get", "http.client", "socket.socket"]


def _modules():
    for name in sorted(os.listdir(PKG)):
        if name.endswith(".py"):
            yield name, os.path.join(PKG, name)


def test_no_network_imports_in_package():
    problems = []
    scanned = 0
    for name, path in _modules():
        scanned += 1
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_ROOTS:
                        problems.append("%s: import %s" % (name, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if root in FORBIDDEN_ROOTS:
                        problems.append("%s: from %s import ..." % (name, node.module))
                elif node.level:
                    for alias in node.names:
                        if alias.name.split(".")[0] in FORBIDDEN_ROOTS:
                            problems.append("%s: from . import %s" % (name, alias.name))
    assert scanned >= 12, "只扫到 %d 个模块——判据可能空跑" % scanned
    assert problems == [], "\n".join(problems)


def test_no_network_call_text():
    problems = []
    for name, path in _modules():
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        for needle in FORBIDDEN_TEXT:
            if needle in source:
                problems.append("%s: 含 %r" % (name, needle))
    assert problems == [], "\n".join(problems)


def test_no_reads_of_tz_or_locale_env():
    """确定性纪律：不读 TZ 环境变量、不调 time.tzset、不读 locale。"""
    problems = []
    for name, path in _modules():
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        for needle in ('"TZ"', "'TZ'", "tzset", "setlocale", "getlocale"):
            if needle in source:
                problems.append("%s: 含 %r" % (name, needle))
    assert problems == [], "\n".join(problems)


def test_only_report_may_read_the_clock():
    """除 ``report.generated_at`` 外，包内不得读时钟。"""
    problems = []
    for name, path in _modules():
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        for needle in ("time.time(", "datetime.now(", "datetime.utcnow(", "time.localtime("):
            if needle in source:
                problems.append("%s: 含 %r" % (name, needle))
    assert problems == [], "\n".join(problems)
