# -*- coding: utf-8 -*-
"""zoneinfo 树访问层：zone 判据必须是**内容特征**（TZif 魔数），不是文件名。

实测教训（2026-10-21）：首版只按扩展名过滤，`tzaudit version --zoneinfo .` 把仓库里的
计划文档数成了 27 个 zone。回归测试锁住"文本文件不是 zone"。
"""

import io
import os

import pytest

from tzaudit.errors import EnvironmentProblem
from tzaudit.zoneinfo_store import ZoneinfoStore, byte_key, looks_like_tzif


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "wb") as fh:
        fh.write(data)


def _minimal_tzif():
    """最小 TZif v1 头（含魔数与全零计数）——足够通过魔数判据，不要求能解析。"""
    header = b"TZif" + b"\x00" + b"\x00" * 15
    counts = (0).to_bytes(4, "big") * 6
    return header + counts


def test_text_files_are_not_counted_as_zones(tmp_path):
    tree = tmp_path / "tree"
    _write(str(tree / "America" / "New_York"), _minimal_tzif())
    _write(str(tree / "Europe" / "Dublin"), _minimal_tzif())
    # 这些都是"长得像 zone 名但内容不是 TZif"的文件
    _write(str(tree / "README"), b"not a zone\n")
    _write(str(tree / "zone.tab"), b"US\tAmerica/New_York\n")
    _write(str(tree / "NEWS"), b"Release 2026e\n")
    _write(str(tree / "plan"), b"# plan\n")

    store = ZoneinfoStore(str(tree))
    assert store.zones() == ["America/New_York", "Europe/Dublin"]


def test_zonedir_without_tzif_yields_zero(tmp_path):
    """纯文本目录 → 0 个 zone（这是"判据生效"的形态，不是异常）。"""
    _write(str(tmp_path / "README.md"), b"# hello\n")
    _write(str(tmp_path / "a.txt"), b"x\n")
    assert ZoneinfoStore(str(tmp_path)).zones() == []


def test_posix_and_right_subtrees_are_skipped(tmp_path):
    _write(str(tmp_path / "UTC"), _minimal_tzif())
    _write(str(tmp_path / "posix" / "UTC"), _minimal_tzif())
    _write(str(tmp_path / "right" / "UTC"), _minimal_tzif())
    assert ZoneinfoStore(str(tmp_path)).zones() == ["UTC"]


def test_version_from_provenance_then_dirname(tmp_path):
    tree = tmp_path / "2026a"
    _write(str(tree / "UTC"), _minimal_tzif())
    assert ZoneinfoStore(str(tree)).version == "2026a"

    wheel = tmp_path / "2026.1"
    _write(str(wheel / "UTC"), _minimal_tzif())
    assert ZoneinfoStore(str(wheel)).version == "2026.1"

    other = tmp_path / "some-tree"
    _write(str(other / "UTC"), _minimal_tzif())
    assert ZoneinfoStore(str(other)).version == "unknown"


def test_provenance_overrides_dirname(tmp_path):
    tree = tmp_path / "some-tree"
    _write(str(tree / "UTC"), _minimal_tzif())
    _write(str(tree / "provenance.json"),
           b'{"version": "2026e", "kind": "slim", "sha256": "deadbeef"}')
    store = ZoneinfoStore(str(tree))
    assert store.version == "2026e"
    assert store.kind == "slim"


def test_links_detected_by_content_hash_not_symlink(tmp_path):
    data = _minimal_tzif()
    _write(str(tmp_path / "A" / "Lima"), data)
    _write(str(tmp_path / "A" / "Lima_Alias"), data)
    _write(str(tmp_path / "A" / "Other"), data + b"extra")
    links = ZoneinfoStore(str(tmp_path)).links()
    assert links == {"A/Lima_Alias": "A/Lima"}


def test_missing_root_raises_environment_problem(tmp_path):
    with pytest.raises(EnvironmentProblem):
        ZoneinfoStore(str(tmp_path / "nope"))


def test_missing_zone_raises_environment_problem(tmp_path):
    _write(str(tmp_path / "UTC"), _minimal_tzif())
    with pytest.raises(EnvironmentProblem):
        ZoneinfoStore(str(tmp_path)).path_for("No/Where")


def test_byte_key_is_utf8_order():
    names = ["Zulu", "Asia", "America", "Åland"]
    assert sorted(names, key=byte_key) == sorted(names, key=lambda s: s.encode("utf-8"))
    assert looks_like_tzif.__name__ == "looks_like_tzif"
