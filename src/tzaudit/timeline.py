# -*- coding: utf-8 -*-
"""双引擎合并（TZif 表 + POSIX tail）与本地反解 —— 契约见 ``plan/03`` §四。

**骨架期**：数据结构 + 入口签名；合并与反解由 M2 落地。
"""

from __future__ import print_function

from .errors import NotImplementedYet


class Segment(object):
    """时间线的一段：``[utc_start, utc_end)`` 内 offset 恒定。"""

    __slots__ = ("utc_start", "utc_end", "offset_sec", "abbr", "is_dst", "source")

    def __init__(self, utc_start, utc_end, offset_sec, abbr, is_dst, source):
        self.utc_start = utc_start
        self.utc_end = utc_end
        self.offset_sec = offset_sec
        self.abbr = abbr
        self.is_dst = is_dst
        self.source = source  # "table" | "tail"

    def __repr__(self):  # pragma: no cover - 调试用
        return "Segment(%d, %d, %d, %r, %r, %r)" % (
            self.utc_start, self.utc_end, self.offset_sec, self.abbr, self.is_dst, self.source)


class Timeline(object):
    """某 zone 在某棵树下的统一时间线。"""

    __slots__ = ("zone", "version", "segments", "tail", "table_end_utc")

    def __init__(self, zone, version, segments, tail=None, table_end_utc=None):
        self.zone = zone
        self.version = version
        self.segments = segments
        self.tail = tail
        self.table_end_utc = table_end_utc


class Resolution(object):
    """一个本地墙钟时刻的一个 UTC 候选。"""

    __slots__ = ("utc", "offset_sec", "abbr", "is_dst", "fold")

    def __init__(self, utc, offset_sec, abbr, is_dst, fold):
        self.utc = utc
        self.offset_sec = offset_sec
        self.abbr = abbr
        self.is_dst = is_dst
        self.fold = fold


def load_timeline(zone, store, window_start=None, window_end=None):
    """读文件 → 解析 → 合并。M2 实现。"""
    raise NotImplementedYet("时间线合并尚未实现（M2）；契约见 plan/03 §四")


def resolve_local(local, timeline):
    """本地墙钟 → 0/1/2 个 UTC 候选（升序）。M2 实现。"""
    raise NotImplementedYet("本地反解尚未实现（M2）；契约见 plan/03 §四")


def to_local(utc, timeline):
    """UTC → 本地墙钟 epoch。M2 实现。"""
    raise NotImplementedYet("UTC→本地尚未实现（M2）；契约见 plan/03 §四")


def roundtrip(local, timeline):
    """``local`` → 候选 UTC → 回到本地墙钟的列表（存在性判据的载体）。M2 实现。"""
    raise NotImplementedYet("roundtrip 尚未实现（M2）；契约见 data/README §4.6")
