# -*- coding: utf-8 -*-
"""**独立参照实现**：TZif 字节读取 + POSIX tail 展开 + 本地反解。

为什么要有它：`bench/run.py --regen` 与 `--check` 都走生产实现，若期望值也只由生产实现生成，
那就是**引擎自证**——解析器写错时金标会跟着一起错，比对恒绿（`plan/04` §二.2）。

本文件的纪律：

1. **不 import `tzaudit` 的任何东西**（`test_architecture.py` 反向守门）。
2. **结构刻意与生产实现不同**：TZif 侧用"游标 + 一次性切片"（不共享 `_block_size`）；
   POSIX 侧用**正则整体匹配**（生产实现是逐光标手写）；日历算术用**标准库 `datetime`**
   （生产实现的 `civil.py` 是自研整数算法）。两边同时写错同一个偏移/规则的概率因此极低。
3. 只实现"够用来对拍"的部分：不做 `is_slim`、不做 `initial` 推断。

对拍口径（`bench/run.py` 抽样，≥ 20 zone，含 Dublin / Lord_Howe / Chatham）：
两边的 ``[(utc, offset_sec, is_dst, abbr)]`` 与 ``footer`` 必须**逐项相等**；
``timeline`` 层再比 ``to_local`` / ``resolve_local`` 的 UTC 候选集。
"""

from __future__ import print_function

import bisect
import datetime
import re
import struct

TZIF_MAGIC = b"TZif"

#: 1970-01-01 的 ``datetime.toordinal()``
_EPOCH_ORDINAL = 719163


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


def read_initial(raw):
    """首个转换点之前的标准时类型 ``(offset_sec, is_dst, abbr)``。

    生产实现在 ``tzif._parse_block`` 里做同样的事；这里独立再算一遍，
    好让 timeline 层的对拍也有"首段"可依（两边写错同一处的概率因此更低）。
    """
    ver = raw[4]
    if ver in (0x32, 0x33, 0x34):
        _v1, v1_end = _walk(raw, 0, wide=False)
        base, wide = v1_end, True
    else:
        base, wide = 0, False

    isutcnt, isstdcnt, leapcnt, timecnt, typecnt, charcnt = _counts(raw, base)
    width = 8 if wide else 4
    pos = base + 44
    idx_end = pos + timecnt * width + timecnt
    types_end = idx_end + typecnt * 6
    types = []
    for i in range(typecnt):
        off = idx_end + i * 6
        utoff = struct.unpack(">i", raw[off:off + 4])[0]
        is_dst = raw[off + 4] == 1
        name = raw[types_end + raw[off + 5]:types_end + charcnt].split(b"\x00")[0]
        types.append((utoff, is_dst, name.decode("ascii", "replace")))
    for entry in types:
        if not entry[1]:
            return entry
    return types[0] if types else (0, False, "UTC")  # pragma: no cover


# ================================================================ POSIX tail（正则整体匹配）
#
# 生产实现是"逐光标手写索引推进"；这里是**一条大正则整体匹配**。同一份口径，
# 两条完全不同的解析路径 —— 只有两边都对，结果才会相等。

_ABBR = r"(?:<[^<>,\s]+>|[A-Za-z]{3,})"
_HMS = r"[+-]?\d{1,3}(?::\d{1,2})?(?::\d{1,2})?"
_TZ_RE = re.compile(
    r"^(?P<std_abbr>%s)(?P<std_off>%s)"
    r"(?:(?P<dst_abbr>%s)(?P<dst_off>%s)?(?:,(?P<start>[^,]+),(?P<end>[^,]+))?)?$" % (_ABBR, _HMS, _ABBR, _HMS)
)
_RULE_RE = re.compile(
    r"^(?:(?:J(?P<jn>\d{1,3}))|(?:M(?P<mm>\d{1,2})\.(?P<mw>\d)\.(?P<md>\d))|(?P<n>\d{1,3}))"
    r"(?:/(?P<time>%s))?$" % _HMS
)


def _hms(text):
    """``[+-]hh[:mm[:ss]]`` → **带符号**秒数（不翻符号；调用方决定语义）。"""
    sign = 1
    if text[:1] in ("+", "-"):
        if text[0] == "-":
            sign = -1
        text = text[1:]
    parts = text.split(":")
    if not 1 <= len(parts) <= 3:
        raise ReferenceError("偏移形态不对: %r" % (text,))
    total = int(parts[0]) * 3600
    if len(parts) > 1:
        mm = int(parts[1])
        if mm > 59:
            raise ReferenceError("分钟越界: %r" % (text,))
        total += mm * 60
    if len(parts) > 2:
        ss = int(parts[2])
        if ss > 59:
            raise ReferenceError("秒越界: %r" % (text,))
        total += ss
    return sign * total


def _name(abbr):
    return abbr[1:-1] if abbr.startswith("<") else abbr


class RefRule(object):
    def __init__(self, kind, time_sec, n=None, month=None, week=None, weekday=None):
        self.kind = kind
        self.time_sec = time_sec
        self.n = n
        self.month = month
        self.week = week
        self.weekday = weekday


class RefPosixTz(object):
    def __init__(self, std, dst, start, end, raw):
        self.std = std              # (offset_sec, abbr)，**东为正**
        self.dst = dst
        self.start = start
        self.end = end
        self.raw = raw


def parse_posix(text):
    """独立 POSIX TZ 解析（**西为正 → 东为正**在此翻转）。"""
    m = _TZ_RE.match(text)
    if not m:
        raise ReferenceError("POSIX TZ 不匹配: %r" % (text,))
    std = (-_hms(m.group("std_off")), _name(m.group("std_abbr")))

    dst = None
    start = end = None
    if m.group("dst_abbr"):
        if m.group("dst_off") is None:
            dst = (std[0] + 3600, _name(m.group("dst_abbr")))
        else:
            dst = (-_hms(m.group("dst_off")), _name(m.group("dst_abbr")))
        if m.group("start"):
            start = _rule(m.group("start"))
            end = _rule(m.group("end"))
    return RefPosixTz(std, dst, start, end, text)


def _rule(text):
    m = _RULE_RE.match(text)
    if not m:
        raise ReferenceError("规则不匹配: %r" % (text,))
    time_sec = _hms(m.group("time")) if m.group("time") else 7200
    if m.group("jn") is not None:
        n = int(m.group("jn"))
        if not 1 <= n <= 365:
            raise ReferenceError("Jn 越界: %r" % (text,))
        return RefRule("J", time_sec, n=n)
    if m.group("mm") is not None:
        month, week, weekday = int(m.group("mm")), int(m.group("mw")), int(m.group("md"))
        if not (1 <= month <= 12 and 1 <= week <= 5 and 0 <= weekday <= 6):
            raise ReferenceError("Mm.w.d 越界: %r" % (text,))
        return RefRule("M", time_sec, month=month, week=week, weekday=weekday)
    n = int(m.group("n"))
    if not 0 <= n <= 365:
        raise ReferenceError("n 越界: %r" % (text,))
    return RefRule("N", time_sec, n=n)


# ================================================================ 日历（标准库 datetime）
#
# 生产实现用自研整数算法（civil.py）；这里用 datetime —— 两条独立路径。


def _epoch(dt):
    """naive ``datetime`` → epoch 秒（把 naive 当纯日历数，不加任何偏移）。"""
    return (dt.toordinal() - _EPOCH_ORDINAL) * 86400 + dt.hour * 3600 + dt.minute * 60 + dt.second


def _nonleap_md(n):
    """``Jn``：1–365 按**平年**映射到 (月, 日)（闰年也不改）。"""
    month_days = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    for index, dim in enumerate(month_days):
        if n <= dim:
            return index + 1, n
        n -= dim
    raise ReferenceError("Jn 越界")


def rule_local(rule, year):
    """规则在 ``year`` 年的本地墙钟 epoch（**不含**任何偏移加减）。"""
    if rule.kind == "J":
        month, day = _nonleap_md(rule.n)
    elif rule.kind == "N":
        base = datetime.datetime(year, 1, 1) + datetime.timedelta(days=rule.n)
        month, day = base.month, base.day
    else:
        first = datetime.datetime(year, rule.month, 1)
        # ``datetime.weekday()``：周一=0；POSIX 是周日=0。
        first_wd = (first.weekday() + 1) % 7
        day = 1 + (rule.weekday - first_wd) % 7 + (rule.week - 1) * 7
        while day > _dim(year, rule.month):
            day -= 7
        month = rule.month
    base = datetime.datetime(year, month, day)
    return _epoch(base) + rule.time_sec


def _dim(year, month):
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    return (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]


def year_of(epoch):
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=epoch)).year


class RefTimeline(object):
    """独立时间线：段表 + 区间包含式反解（与生产实现的"自洽校验式"不同路）。"""

    def __init__(self, transitions, initial, footer, window_start, window_end):
        self.raw_footer = footer
        self.tail = parse_posix(footer) if footer else None
        self.initial = initial

        self.starts = []          # 段起点（UTC，升序）
        self.offsets = []         # 段 offset
        self.abbrs = []
        self.is_dsts = []

        def push(start, offset, abbr, is_dst):
            self.starts.append(start)
            self.offsets.append(offset)
            self.abbrs.append(abbr)
            self.is_dsts.append(is_dst)

        if transitions:
            push(-(1 << 62), initial[0], initial[2], initial[1])
            for index, (utc, offset, is_dst, abbr) in enumerate(transitions):
                if index + 1 == len(transitions):
                    break           # 最后一个转换点之后交给 tail
                push(utc, offset, abbr, is_dst)
            self.table_end = transitions[-1][0]
        else:
            self.table_end = None
            if self.tail is None:
                push(-(1 << 62), initial[0], initial[2], initial[1])

        if self.tail is not None:
            anchor = self.table_end if self.table_end is not None else 0
            if window_end is None:
                horizon = anchor + 60 * 365 * 86400
            else:
                horizon = _plus_one_year(window_end)
            cursor = anchor
            state = self._tail_state(anchor)
            for utc, offset, abbr, is_dst in self._tail_points(anchor, horizon):
                if utc > cursor:
                    push(cursor, state[0], state[1], state[2])
                cursor = utc
                state = (offset, abbr, is_dst)
            push(cursor, state[0], state[1], state[2])
            if self.table_end is None and self.starts:
                self.starts[0] = -(1 << 62)

    # ---- tail ----
    def _tail_points(self, from_utc, to_utc):
        if self.tail is None or self.tail.start is None or to_utc <= from_utc:
            return []
        out = []
        for year in range(year_of(from_utc) - 1, year_of(to_utc) + 2):
            start_utc = rule_local(self.tail.start, year) - self.tail.std[0]
            end_utc = rule_local(self.tail.end, year) - self.tail.dst[0]
            for entry in ((start_utc, self.tail.dst[0], self.tail.dst[1], True),
                          (end_utc, self.tail.std[0], self.tail.std[1], False)):
                if from_utc <= entry[0] < to_utc:
                    out.append(entry)
        out.sort()
        return out

    def _tail_state(self, utc):
        if self.tail is None or self.tail.start is None:
            return (self.tail.std[0], self.tail.std[1], False) if self.tail else (0, "UTC", False)
        best = None
        for probe in (year_of(utc) - 1, year_of(utc), year_of(utc) + 1):
            start_utc = rule_local(self.tail.start, probe) - self.tail.std[0]
            end_utc = rule_local(self.tail.end, probe) - self.tail.dst[0]
            for entry in ((start_utc, self.tail.dst[0], self.tail.dst[1], True),
                          (end_utc, self.tail.std[0], self.tail.std[1], False)):
                if entry[0] <= utc and (best is None or entry[0] > best[0]):
                    best = entry
        if best is None:
            return (self.tail.std[0], self.tail.std[1], False)
        return (best[1], best[2], best[3])

    # ---- 查询 ----
    def state_at(self, utc):
        if self.tail is not None and (self.table_end is None or utc >= self.table_end):
            return self._tail_state(utc)
        index = bisect.bisect_right(self.starts, utc) - 1
        if index < 0:
            index = 0
        return (self.offsets[index], self.abbrs[index], self.is_dsts[index])

    def to_local(self, utc):
        return utc + self.state_at(utc)[0]

    def resolve_local(self, local):
        """**区间包含式**：段 ``[s, e)`` 的墙钟区间是 ``[s+o, e+o)``。

        与生产实现的"枚举 offset 再校验自洽"是两条不同的推理路径。
        """
        found = []
        for index in range(len(self.starts)):
            start = self.starts[index]
            end = self.starts[index + 1] if index + 1 < len(self.starts) else (1 << 62)
            offset = self.offsets[index]
            wall_start, wall_end = start + offset, end + offset
            if wall_start <= local < wall_end:
                found.append((local - offset, offset, self.abbrs[index], self.is_dsts[index]))
        found.sort()
        return found


def _plus_one_year(epoch):
    dt = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=epoch)
    try:
        nxt = dt.replace(year=dt.year + 1)
    except ValueError:              # 2/29 → 非闰年
        nxt = dt.replace(year=dt.year + 1, day=28)
    return _epoch(nxt)


def read_timeline(raw, window_start=0, window_end=None):
    """参照实现的时间线（表 + tail），与 ``timeline.load_timeline`` 对拍用。"""
    version, transitions, footer = read_tzif(raw)
    initial = read_initial(raw)
    return RefTimeline(transitions, initial, footer, window_start, window_end)