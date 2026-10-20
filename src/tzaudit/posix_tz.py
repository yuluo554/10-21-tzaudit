# -*- coding: utf-8 -*-
"""POSIX TZ 串解析与规则展开 —— 契约见 ``plan/03`` §三。

**骨架期**：只有数据类与入口签名，解析逻辑由 M2 落地。
"""

from __future__ import print_function

from .errors import NotImplementedYet


class PosixTzError(Exception):
    """POSIX TZ 串不合法（退出码 3）。不做宽容解析。"""


class Rule(object):
    """一条 DST 规则：``kind ∈ {"J", "N", "M"}`` + ``time_sec``（**墙钟秒**）。"""

    __slots__ = ("kind", "n", "month", "week", "weekday", "time_sec")

    def __init__(self, kind, time_sec, n=None, month=None, week=None, weekday=None):
        self.kind = kind
        self.time_sec = time_sec
        self.n = n
        self.month = month
        self.week = week
        self.weekday = weekday


class PosixTz(object):
    """``std offset [dst [offset] [,start[/time],end[/time]]]`` 的解析结果。

    偏移一律**东为正的秒数**（解析层已把 POSIX 的"西为正"翻转）。
    """

    __slots__ = ("std", "dst", "start", "end", "raw")

    def __init__(self, std, dst, start, end, raw):
        self.std = std
        self.dst = dst
        self.start = start
        self.end = end
        self.raw = raw

    @property
    def has_dst(self):
        return self.dst is not None


def parse(text):
    """解析 POSIX TZ 串。M2 实现。"""
    raise NotImplementedYet("POSIX TZ 解析器尚未实现（M2）；契约见 plan/03 §三")
