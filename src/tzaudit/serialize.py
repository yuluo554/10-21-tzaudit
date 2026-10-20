# -*- coding: utf-8 -*-
"""写盘与序列化单点 —— 全项目**唯一**允许写产物的地方。

为什么单点：多个子命令各写各的 ``open()+json.dump()``，迟早出现"一个带 BOM 一个不带"
"一个 sort_keys 一个不排""一个 CRLF 一个 LF"的漂移（skill「确定性写盘单点」条）。

冻结契约（改动即口径变更，需走决策记录）：
- JSON：``ensure_ascii=False`` + ``sort_keys=True`` + ``indent=2`` + ``\\n`` 结尾
- 文本：``\\n`` 行尾 + 结尾换行
- 写盘：临时文件 + ``os.replace``（原子；中断不留半个产物）
- 编码：UTF-8，**不写 BOM**
"""

from __future__ import print_function

import io
import json
import os
import tempfile


def dumps_json(obj):
    """规范化 JSON 文本（保证"文件 == 管道"）。"""
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    return text + "\n"


def dumps_text(text):
    """规范化文本：CRLF → LF，补结尾换行，去 BOM。"""
    if text.startswith(u"\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_bytes_atomic(path, data):
    """原子写字节；任何异常都不留临时文件。"""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.isdir(directory):
        raise IOError("output directory does not exist: %s" % directory)
    fd, tmp = tempfile.mkstemp(prefix=".tzaudit-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        finally:
            pass
        raise


def write_text_atomic(path, text):
    """原子写文本（UTF-8 + LF）。"""
    write_bytes_atomic(path, dumps_text(text).encode("utf-8"))


def write_json_atomic(path, obj):
    """原子写规范化 JSON。"""
    write_bytes_atomic(path, dumps_json(obj).encode("utf-8"))


def emit(text, stream=None):
    """输出到 stdout（统一走这里：保证行尾与编码一致）。"""
    import sys

    out = stream if stream is not None else sys.stdout
    out.write(dumps_text(text))
    out.flush()


def read_text(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return fh.read()
