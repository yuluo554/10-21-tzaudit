# -*- coding: utf-8 -*-
"""金标形态守门：``expect.json`` 只存**输入与期望**，不得存观测值。

为什么：冻结"观测"会让基准退化成"比对两份预先算好的答案"——引擎全坏也全绿
（skill「真值只存输入与期望」条）。
"""

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIRS = [
    os.path.join(ROOT, "data", "tzdb"),
    os.path.join(ROOT, "data", "fixtures"),
]

FORBIDDEN_PREFIXES = ("observed_", "actual_", "runtime_")
FORBIDDEN_KEYS = {"observed", "actual", "result_runtime"}


def _iter_expect_files():
    for base in DATA_DIRS:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for name in sorted(filenames):
                if name == "expect.json":
                    yield os.path.join(dirpath, name)


def _walk_keys(obj, path="$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key, path + "." + str(key)
            for item in _walk_keys(value, path + "." + str(key)):
                yield item
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            for item in _walk_keys(value, "%s[%d]" % (path, index)):
                yield item


def test_expect_files_have_no_observation_fields():
    files = list(_iter_expect_files())
    bad = []
    for path in files:
        with io.open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        for key, where in _walk_keys(doc):
            if key in FORBIDDEN_KEYS or key.startswith(FORBIDDEN_PREFIXES):
                bad.append("%s: %s" % (os.path.relpath(path, ROOT), where))
    assert bad == [], "金标里出现观测字段:\n" + "\n".join(bad)


def test_expect_files_have_no_absolute_paths_or_user_names():
    """金标不得含绝对路径 / 主机名 / 用户名（脱敏 + 可复现）。"""
    import re

    absolute = re.compile(r"(?<![<\w])[A-Za-z]:[\\/](?!<)|/home/|/Users/")
    files = list(_iter_expect_files())
    bad = []
    for path in files:
        with io.open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if absolute.search(text):
            bad.append(os.path.relpath(path, ROOT))
    assert bad == [], "金标含绝对路径: %s" % bad


def test_expect_files_are_byte_stable_json():
    """金标必须是规范化 JSON（``sort_keys`` + 2 空格 + LF 尾），否则跨平台比对必漂。"""
    from tzaudit.serialize import dumps_json

    files = list(_iter_expect_files())
    bad = []
    for path in files:
        with io.open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        doc = json.loads(raw)
        if dumps_json(doc) != raw:
            bad.append(os.path.relpath(path, ROOT))
    assert bad == [], "金标不是规范化 JSON（用 serialize.write_json_atomic 重写）: %s" % bad
