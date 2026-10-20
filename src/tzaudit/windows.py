# -*- coding: utf-8 -*-
"""墙钟风险窗口 —— 契约见 ``plan/03`` §五。**骨架期**。"""

from __future__ import print_function

from .errors import NotImplementedYet

GAP = "GAP"
OVERLAP = "OVERLAP"


class Window(object):
    """一条墙钟窗口。字段与 ``--json`` 输出一一对应。"""

    __slots__ = ("type", "start_local", "end_local", "duration_min", "residual_sec",
                 "offset_before", "offset_after", "zone", "source")

    def __init__(self, type_, start_local, end_local, duration_min, residual_sec,
                 offset_before, offset_after, zone, source):
        self.type = type_
        self.start_local = start_local
        self.end_local = end_local
        self.duration_min = duration_min
        self.residual_sec = residual_sec
        self.offset_before = offset_before
        self.offset_after = offset_after
        self.zone = zone
        self.source = source


def scan_year(zone, year, timeline):
    """扫描某 zone 某年的 gap/overlap。M3 实现。"""
    raise NotImplementedYet("墙钟窗口扫描尚未实现（M3）；契约见 plan/03 §五")


def scan_all(store, year):
    """全量 zone 批量扫描。M3 实现。"""
    raise NotImplementedYet("批量扫描尚未实现（M3）；契约见 plan/03 §五")
