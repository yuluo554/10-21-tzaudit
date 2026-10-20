# -*- coding: utf-8 -*-
"""序列化单点契约：JSON 规范化、原子写、CRLF 归一。"""

import io
import json
import os

import pytest

from tzaudit import serialize


def test_dumps_json_is_canonical():
    text = serialize.dumps_json({"b": 1, "a": [1, 2], "中文": "值"})
    assert text == '{\n  "a": [\n    1,\n    2\n  ],\n  "b": 1,\n  "中文": "值"\n}\n'
    assert text.endswith("\n")
    assert "\\u" not in text  # ensure_ascii=False


def test_dumps_text_normalises_line_endings_and_trailing_newline():
    assert serialize.dumps_text("a\r\nb\rc") == "a\nb\nc\n"
    assert serialize.dumps_text("a\n") == "a\n"
    assert serialize.dumps_text("\ufeffa") == "a\n"


def test_write_json_atomic_round_trip(tmp_path):
    target = tmp_path / "out.json"
    serialize.write_json_atomic(str(target), {"z": 1, "a": 2})
    raw = target.read_bytes()
    assert raw == serialize.dumps_json({"z": 1, "a": 2}).encode("utf-8")
    assert json.loads(raw.decode("utf-8")) == {"a": 2, "z": 1}


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "x.json"
    serialize.write_json_atomic(str(target), {"k": 1})
    leftovers = [n for n in os.listdir(str(tmp_path)) if n.startswith(".tzaudit-")]
    assert leftovers == []


def test_write_to_missing_directory_raises(tmp_path):
    with pytest.raises(IOError):
        serialize.write_json_atomic(str(tmp_path / "nope" / "x.json"), {})


def test_no_bom_written(tmp_path):
    target = tmp_path / "y.txt"
    serialize.write_text_atomic(str(target), "\ufeffhello")
    assert not target.read_bytes().startswith(b"\xef\xbb\xbf")


def test_emit_writes_normalised_text():
    buf = io.StringIO()
    serialize.emit("a\r\nb", stream=buf)
    assert buf.getvalue() == "a\nb\n"
