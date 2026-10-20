# -*- coding: utf-8 -*-
"""TZif（v1–v4）字节解析 —— 契约见 ``plan/03`` §二。

**骨架期**：只有数据类与入口签名，解析逻辑由 M2 落地。
"""

from __future__ import print_function

from .errors import NotImplementedYet


class TzifParseError(Exception):
    """TZif 字节损坏（退出码 3）。带 zone 与字节偏移，便于定位。"""


class TzifData(object):
    """解析结果。字段语义见 ``plan/03`` §二。

    ``transitions`` 升序，每项 ``(utc:int, offset_sec:int, is_dst:bool, abbr:str)``。
    ``footer`` 是 POSIX TZ 串（无 tail 时为 None）。
    """

    __slots__ = ("version", "transitions", "initial", "footer", "is_slim", "raw_counts")

    def __init__(self, version, transitions, initial, footer, is_slim, raw_counts):
        self.version = version
        self.transitions = transitions
        self.initial = initial
        self.footer = footer
        self.is_slim = is_slim
        self.raw_counts = raw_counts


def parse(data, zone="<bytes>"):
    """把 TZif 字节解析成 :class:`TzifData`。M2 实现。"""
    raise NotImplementedYet("TZif 解析器尚未实现（M2）；契约见 plan/03 §二")
