# -*- coding: utf-8 -*-
"""**独立参照实现**：TZif v2 的最小读取器（只取"转换点 + footer"）。

为什么要有它：`bench/run.py --regen` 与 `--check` 都走生产实现，若期望值也只由生产实现生成，
那就是**引擎自证**——解析器写错时金标会跟着一起错，比对恒绿（`plan/04` §二.2）。

本文件的纪律：

1. **不 import `tzaudit` 的任何东西**（`test_architecture.py` 反向守门）。
2. **结构刻意与 `tzif.py` 不同**：这里用"游标 + 一次性切片"，不做 `_block_size` 复用，
   也不共享任何常量。两边同时写错同一个偏移的概率因此极低。
3. 只实现"够用来对拍"的部分：转换点列表与 footer。不做 `is_slim`、不做 `initial` 推断。

对拍口径（`bench/run.py` 抽样，≥ 20 zone，含 Dublin / Lord_Howe / Chatham）：
两边的 ``[(utc, offset_sec, is_dst, abbr)]`` 必须**逐项相等**。
"""

from __future__ import print_function

import struct

TZIF_MAGIC = b"TZif"


class ReferenceError(Exception):
    pass


def _counts(raw, base):
    """六元组（文件顺序：isutcnt, isstdcnt, leapcnt, timecnt, typecnt, charcnt）。"""
    return struct.unpack(">6I", raw[base + 20:base + 44])


def _walk(raw, base, wide):
    """读一个数据块 → (transitions, footer_offset)。

    刻意写成"算好五个切片起点再一次切"，与生产实现的逐字段 struct.unpack_from 不同路。
    """
    isutcnt, isstdcnt, leapcnt, timecnt, typecnt, charcnt = _counts(raw, base)
    if typecnt == 0:
        raise ReferenceError("typecnt=0")

    width = 8 if wide else 4
    pos = base + 44
    times_end = pos + timecnt * width
    idx_end = times_end + timecnt
    types_end = idx_end + typecnt * 6
    chars_end = types_end + charcnt
    leap_end = chars_end + leapcnt * (width + 4) + isstdcnt + isutcnt

    if leap_end > len(raw):
        raise ReferenceError("块越界")

    if timecnt:
        fmt = ">%d%s" % (timecnt, "q" if wide else "i")
        times = list(struct.unpack(fmt, raw[pos:times_end]))
        indices = list(raw[times_end:idx_end])
    else:
        times, indices = [], []

    abbrs = []
    for i in range(typecnt):
        off = idx_end + i * 6
        utoff = struct.unpack(">i", raw[off:off + 4])[0]
        is_dst = raw[off + 4] == 1
        abbrind = raw[off + 5]
        chunk = raw[types_end + abbrind:chars_end]
        name = chunk.split(b"\x00")[0].decode("ascii", "replace")
        abbrs.append((utoff, is_dst, name))

    transitions = []
    for t, index in zip(times, indices):
        if index >= typecnt:
            raise ReferenceError("类型索引越界")
        utoff, is_dst, name = abbrs[index]
        transitions.append((t, utoff, is_dst, name))

    return transitions, leap_end


def read_tzif(raw):
    """返回 ``(version, transitions, footer)``。只支持 v1 / v2+（v2 块为准）。"""
    if raw[:4] != TZIF_MAGIC:
        raise ReferenceError("非 TZif")
    ver = raw[4]
    if ver == 0:
        transitions, end = _walk(raw, 0, wide=False)
        return "1", transitions, None
    if ver not in (0x32, 0x33, 0x34):
        raise ReferenceError("未知版本字节")

    # 跳过 v1 块：它只是向后兼容占位。
    _v1, v1_end = _walk(raw, 0, wide=False)
    version = chr(ver)
    transitions, block_end = _walk(raw, v1_end, wide=True)

    footer = None
    if block_end < len(raw):
        tail = raw[block_end:]
        if tail.startswith(b"\n"):
            last = tail.rfind(b"\n")
            if last > 0:
                footer = tail[1:last].decode("ascii", "replace") or None
    return version, transitions, footer