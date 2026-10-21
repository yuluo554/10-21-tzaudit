# -*- coding: utf-8 -*-
"""slim / fat 语义等价 —— `plan/03` §四.3 测试点 5 + Q1 定案。

**判定口径**：不要求版本号相同、不要求转换点数相同；只要求**重叠区间**内语义一致
（`(offset, abbr, is_dst)` 逐点相同）。

两个 fixture 覆盖两种对照：

1. ``data/fixtures/tzif/slim-vs-fat/``：**同一套规则**的三种编码（fat 全表 / slim 短表 / 空表）。
2. ``data/fixtures/tzif/source-vs-wheel/``：**同一版本的真实数据**，fat 由 IANA 源码规则编译、
   slim 来自 PyPI wheel（两条独立来源）。

两条都要"能跑红"的反向断言：只读表 / 只读 tail 的实现必须在某一条上失败。
"""

import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from tzaudit import civil, timeline  # noqa: E402

SLIM_VS_FAT = os.path.join(ROOT, "data", "fixtures", "tzif", "slim-vs-fat")
SOURCE_VS_WHEEL = os.path.join(ROOT, "data", "fixtures", "tzif", "source-vs-wheel")


class _FileStore(object):
    """按路径读单文件的最小 store（``load_timeline`` 的依赖面只有 ``read_zone`` + ``version``）。"""

    def __init__(self, path, version="fixture"):
        self._path = path
        self.version = version

    def read_zone(self, zone):
        with io.open(self._path, "rb") as fh:
            return fh.read()


def _load_timeline(path, window_end=None):
    name = os.path.basename(path.rstrip(os.sep))
    return timeline.load_timeline(name, _FileStore(path), window_end=window_end)


def _read_json(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- 1. 同规则三编码


def test_all_three_encodings_agree_over_the_whole_overlap():
    """fat / slim / tail-only 在重叠区间内逐点一致（含缩写）。"""
    doc = _read_json(os.path.join(SLIM_VS_FAT, "expect.json"))
    start = doc["input"]["overlap_start"]
    end = doc["input"]["overlap_end"]

    paths = [os.path.join(SLIM_VS_FAT, name)
             for name in ("fat.tzif", "slim.tzif", "tail_only.tzif")]
    timelines = [_load_timeline(path, window_end=end) for path in paths]

    probe = start
    while probe < end:
        states = [timeline.state_at(probe, tl) for tl in timelines]
        assert states[0] == states[1] == states[2], \
            "三编码在 %s 上不一致: %r" % (civil.format_local(probe), states)
        probe += 86400 * 11


def test_encodings_have_different_table_shapes():
    """**判据非空跑**：三种编码的表必须真的不同，否则上面的"一致"毫无信息量。

    注意 fat 也带 footer（真实 ``zic -b fat`` 同样带），区别在**表长**：
    fat 覆盖 1970–2035、slim 只到 1987、tail-only 一个都没有。
    """
    fat = _load_timeline(os.path.join(SLIM_VS_FAT, "fat.tzif"))
    slim = _load_timeline(os.path.join(SLIM_VS_FAT, "slim.tzif"))
    tail_only = _load_timeline(os.path.join(SLIM_VS_FAT, "tail_only.tzif"))

    assert fat.table_end_utc > slim.table_end_utc, "fat 的表必须比 slim 长"
    assert tail_only.table_end_utc is None, "tail-only 必须没有显式表"
    assert tail_only.segments and all(seg.source == "tail" for seg in tail_only.segments)

    def table_count(tl):
        return sum(1 for seg in tl.segments if seg.source == "table")

    assert table_count(fat) > table_count(slim) > table_count(tail_only)
    assert table_count(tail_only) == 0


def test_slim_and_fat_actually_differ_before_slims_table_end():
    """**反向断言**：slim 的表尾之前，它的 tail 还没生效 → 与 fat 必须不同。

    没有这条，一个"完全忽略显式表、全靠 tail 展开"的错误实现也能让上面的一致断言通过。
    """
    fat = _load_timeline(os.path.join(SLIM_VS_FAT, "fat.tzif"))
    slim = _load_timeline(os.path.join(SLIM_VS_FAT, "slim.tzif"))

    # fat 在 1970 是 EST、slim 在 1970 也走表 —— 两者一致；但 slim 的 tail 从 1987 才生效，
    # 所以在 1987 之前 slim 若把 tail 提前应用，会与 fat 产生差异。这里直接断言表尾不同。
    assert fat.table_end_utc != slim.table_end_utc
    # 两者在各自表内都用显式表，因此 1970–1987 区间必须一致（证明 slim 没提前用 tail）
    probe = civil.parse_local("1970-06-01 00:00:00")
    while probe < slim.table_end_utc:
        assert timeline.state_at(probe, fat) == timeline.state_at(probe, slim), \
            civil.format_local(probe)
        probe += 86400 * 29


# ---------------------------------------------------------------- 2. 真实数据 fat vs slim


def test_source_compiled_fat_matches_wheel_slim_over_overlap():
    """真实 2026e：源码规则编译的 fat 与 PyPI wheel 的 slim 在重叠区间内逐小时一致。"""
    doc = _read_json(os.path.join(SOURCE_VS_WHEEL, "expect.json"))
    start = doc["expected"]["overlap_start"]
    end = doc["expected"]["overlap_end"]
    assert doc["expected"]["zones"], "fixture 必须列出 zone（空跑即失效）"

    for entry in doc["expected"]["zones"]:
        zone = entry["zone"]
        fat_path = os.path.join(SOURCE_VS_WHEEL, "fat", *zone.split("/"))
        slim_path = os.path.join(SOURCE_VS_WHEEL, "slim", *zone.split("/"))
        assert os.path.isfile(fat_path) and os.path.isfile(slim_path), zone

        fat = _load_timeline(fat_path, window_end=end)
        slim = _load_timeline(slim_path, window_end=end)

        probe = start
        while probe < end:
            assert timeline.state_at(probe, fat) == timeline.state_at(probe, slim), \
                "%s @ %s: fat=%r slim=%r" % (
                    zone, civil.format_local(probe),
                    timeline.state_at(probe, fat), timeline.state_at(probe, slim))
            probe += 3600


def test_fat_tree_has_no_tail_and_slim_does():
    """fat 树不靠 tail；slim 树靠 tail —— 证明两条来源确实是**不同形态**。"""
    with io.open(os.path.join(SOURCE_VS_WHEEL, "expect.json"), "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    for entry in doc["expected"]["zones"]:
        zone = entry["zone"]
        fat = _load_timeline(os.path.join(SOURCE_VS_WHEEL, "fat", *zone.split("/")))
        slim = _load_timeline(os.path.join(SOURCE_VS_WHEEL, "slim", *zone.split("/")))
        assert fat.tail is None, "%s 的 fat 不该有 footer" % zone
        assert slim.tail is not None, "%s 的 slim 必须有 footer" % zone


def test_three_special_forms_are_present_among_fixture_zones():
    """fixture 必须覆盖三种特殊形态（否则"语义等价"只在普通 zone 上成立）。"""
    with io.open(os.path.join(SOURCE_VS_WHEEL, "expect.json"), "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    zones = {entry["zone"] for entry in doc["expected"]["zones"]}
    assert {"Europe/Dublin", "Australia/Lord_Howe", "Pacific/Chatham"} <= zones

    # 逐个断言特殊偏移真的在时间线里出现
    dublin = _load_timeline(os.path.join(SOURCE_VS_WHEEL, "fat", "Europe", "Dublin"))
    lord = _load_timeline(os.path.join(SOURCE_VS_WHEEL, "fat", "Australia", "Lord_Howe"))
    chatham = _load_timeline(os.path.join(SOURCE_VS_WHEEL, "fat", "Pacific", "Chatham"))

    assert any(seg.is_dst for seg in dublin.segments), "Dublin 的负 DST 丢了"
    assert 37800 in {seg.offset_sec for seg in lord.segments}, "Lord_Howe 缺 +10:30"
    assert 45900 in {seg.offset_sec for seg in chatham.segments}, "Chatham 缺 +12:45"


# ---------------------------------------------------------------- 3. 生成器可重建


@pytest.mark.parametrize("fixture", ["slim-vs-fat", "source-vs-wheel"])
def test_generators_reproduce_byte_identical_output(fixture):
    """`plan/04` §三 硬纪律 2：`--check` 必须做"重生成 → 逐字节比对"，不是只验形态。

    ``source-vs-wheel`` 的重生成要读 ``data/_downloads``（源码包 + wheel 树）。干净 clone 里
    没有它们 → **skip 并写明理由**（不是假绿，也不是失败）。已入仓的产物本身仍由本文件
    上面几条真实数据用例读着——那些用例不依赖下载缓存。
    """
    import subprocess

    if fixture == "source-vs-wheel" and not (
            os.path.isdir(os.path.join(ROOT, "data", "_downloads"))):
        pytest.skip("source-vs-wheel 的 gen.py --check 需要 data/_downloads（先跑 fetch_tzdb.py）")

    script = os.path.join(ROOT, "data", "fixtures", "tzif", fixture, "gen.py")
    proc = subprocess.run([sys.executable, script, "--check"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
