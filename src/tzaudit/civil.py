# -*- coding: utf-8 -*-
"""civil ↔ epoch 换算（纯整数，无 datetime 依赖）。

为什么自研：项目要求"同一输入双跑逐字节一致"，且内部不读系统时区/locale。
``datetime`` 的 ``astimezone`` 依赖系统 zoneinfo，与"不读系统时区"纪律冲突；
本模块只做**日历算术**，不涉及任何时区。

算法：Howard Hinnant 的 ``days_from_civil`` / ``civil_from_days``（proleptic Gregorian，
支持负年份）。正确性由 ``tests/test_civil.py`` 用标准库 ``datetime`` **全量交叉证伪**。

约定：
- ``epoch`` = 自 1970-01-01T00:00:00Z 起的**整秒**（可为负）。
- ``days`` = 自 1970-01-01 起的**整日**（可为负）。
- 所有函数只接受 int，**不接受 float**（AST 守门禁止 float）。
"""

from __future__ import division

SECONDS_PER_DAY = 86400

#: 每月天数（平年）
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def is_leap(year):
    """proleptic Gregorian 闰年判据（含负年份与 0 年）。"""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year, month):
    if month < 1 or month > 12:
        raise ValueError("month out of range: %r" % (month,))
    if month == 2 and is_leap(year):
        return 29
    return _MONTH_DAYS[month - 1]


def days_from_civil(year, month, day):
    """(y, m, d) → 自 1970-01-01 起的天数。"""
    if month < 1 or month > 12:
        raise ValueError("month out of range: %r" % (month,))
    if day < 1 or day > days_in_month(year, month):
        raise ValueError("day out of range: %r-%r-%r" % (year, month, day))
    y = year - 1 if month <= 2 else year
    # Hinnant 原文是 C 的截断除法（`(y >= 0 ? y : y-399) / 400`）；
    # Python 的 `//` 是**向下取整**，等价形式就是直接 `y // 400`（少一次修正）。
    era = y // 400
    yoe = y - era * 400  # [0, 399]
    mp = (month + 9) % 12  # 3 月为 0
    doy = (153 * mp + 2) // 5 + day - 1  # [0, 365]
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy  # [0, 146096]
    return era * 146097 + doe - 719468


def civil_from_days(days):
    """自 1970-01-01 起的天数 → (y, m, d)。"""
    z = days + 719468
    # 同上：C 的 `(z >= 0 ? z : z-146096) / 146097` 在 Python 里就是向下取整。
    era = z // 146097
    doe = z - era * 146097  # [0, 146096]
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365  # [0, 399]
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)  # [0, 365]
    mp = (5 * doy + 2) // 153  # [0, 11]
    d = doy - (153 * mp + 2) // 5 + 1  # [1, 31]
    m = mp + 3 if mp < 10 else mp - 9  # [1, 12]
    return (y + 1 if m <= 2 else y, m, d)


def epoch_from_local_naive(year, month, day, hour=0, minute=0, second=0):
    """把"无时区的本地墙钟"当作纯日历数转成 epoch（**不加任何偏移**）。

    调用方负责加减 offset。这就是"墙钟秒"语义的落点（PITFALL-WALLSEC）。
    """
    for name, value in (("hour", hour), ("minute", minute), ("second", second)):
        if not isinstance(value, int):
            raise TypeError("%s must be int" % name)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59 or second < 0 or second > 59:
        raise ValueError("time out of range: %02d:%02d:%02d" % (hour, minute, second))
    return days_from_civil(year, month, day) * SECONDS_PER_DAY + hour * 3600 + minute * 60 + second


def local_naive_from_epoch(epoch):
    """epoch → (y, m, d, H, M, S)，纯日历拆分（不含偏移）。"""
    days, rem = divmod(int(epoch), SECONDS_PER_DAY)
    y, m, d = civil_from_days(days)
    return (y, m, d, rem // 3600, (rem % 3600) // 60, rem % 60)


def format_local(epoch):
    """``YYYY-MM-DD HH:MM:SS``（负年份用 ``-YYYY``，宽度不补零到 4 位以外）。"""
    y, m, d, hh, mm, ss = local_naive_from_epoch(epoch)
    year = ("%04d" % y) if y >= 0 else ("-%04d" % (-y))
    return "%s-%02d-%02d %02d:%02d:%02d" % (year, m, d, hh, mm, ss)


def format_offset(offset_sec):
    """偏移秒 → ``+HH:MM[:SS]``（东为正；输出层用，与 POSIX 的西为正相反）。"""
    sign = "+" if offset_sec >= 0 else "-"
    total = abs(int(offset_sec))
    hh, rem = divmod(total, 3600)
    mm, ss = divmod(rem, 60)
    if ss:
        return "%s%02d:%02d:%02d" % (sign, hh, mm, ss)
    return "%s%02d:%02d" % (sign, hh, mm)


def parse_local(text):
    """解析 ``YYYY-MM-DD HH:MM[:SS]``（也接受 ``T`` 分隔与纯日期）。

    失败抛 ``ValueError``（调用方决定是 ``INVALID`` 还是用法错误）。
    **不接受**带偏移/时区后缀的串——本工具的输入是"本地墙钟"。
    """
    s = text.strip()
    if not s:
        raise ValueError("empty local time")
    if s.endswith("Z") or "+" in s[10:] or (s.count("-") > 2 and "T" not in s):
        raise ValueError("local time must not carry offset/zone suffix: %r" % text)
    s = s.replace("T", " ")
    parts = s.split()
    if len(parts) == 1:
        date_part, time_part = parts[0], "00:00:00"
    elif len(parts) == 2:
        date_part, time_part = parts
    else:
        raise ValueError("too many fields: %r" % text)
    try:
        y, m, d = [int(x) for x in date_part.split("-")]
    except (ValueError, TypeError):
        raise ValueError("bad date: %r" % date_part)
    chunks = time_part.split(":")
    if len(chunks) not in (2, 3):
        raise ValueError("bad time: %r" % time_part)
    try:
        nums = [int(x) for x in chunks]
    except (ValueError, TypeError):
        raise ValueError("bad time: %r" % time_part)
    if len(nums) == 2:
        nums.append(0)
    return epoch_from_local_naive(y, m, d, nums[0], nums[1], nums[2])
