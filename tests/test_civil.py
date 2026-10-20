# -*- coding: utf-8 -*-
"""civil 换算的正确性：用标准库 datetime **全量交叉证伪**（不抽样）。

时间算术的错误几乎全在边界（闰年 / 月末 / 负年份 / 世纪年），抽样必然漏。
"""

import datetime

import pytest

from tzaudit import civil

# (y, m, d) 覆盖：闰年边界、月末、世纪年、1970 前。
# 注意：标准库 `datetime` 的 MINYEAR = 1、且不支持负年份，所以负年份/0 年**无法用 datetime 交叉证伪**
# —— 它们由 tests/test_civil_negative.py 的"往返 + 等差"性质测试覆盖（见下一条断言）。
CASES = [
    (1970, 1, 1), (1969, 12, 31), (2000, 2, 29), (1900, 3, 1), (2100, 2, 28),
    (2026, 3, 8), (2026, 11, 1), (1925, 9, 20), (1979, 5, 26), (1, 1, 1),
    (1600, 2, 29), (2400, 2, 29), (2024, 2, 29), (2023, 3, 1), (9999, 12, 31),
]


@pytest.mark.parametrize("y,m,d", CASES)
def test_days_from_civil_matches_datetime(y, m, d):
    expected = (datetime.date(y, m, d) - datetime.date(1970, 1, 1)).days
    assert civil.days_from_civil(y, m, d) == expected
    assert civil.civil_from_days(expected) == (y, m, d)


def test_full_range_cross_check_every_day_1900_2100():
    """1900–2100 每一天都与 datetime 对拍（73049 天，全量而非抽样）。"""
    base = datetime.date(1970, 1, 1)
    start = datetime.date(1900, 1, 1)
    end = datetime.date(2100, 12, 31)
    day = start
    checked = 0
    while day <= end:
        epoch_days = (day - base).days
        assert civil.days_from_civil(day.year, day.month, day.day) == epoch_days
        assert civil.civil_from_days(epoch_days) == (day.year, day.month, day.day)
        day += datetime.timedelta(days=1)
        checked += 1
    expected = (end - start).days + 1
    assert expected > 70000, "分母太小: %d" % expected
    assert checked == expected, "只扫到 %d 天，应为 %d" % (checked, expected)


def test_negative_years_via_arithmetic_properties():
    """负年份/0 年不在 `datetime` 支持范围 → 用性质交叉证伪（全量等差 + 往返）。

    性质 1：civil_from_days 的连续输出必须**逐日递增且无跳日**（等价于 days_from_civil 是它的逆）。
    性质 2：days_from_civil(civil_from_days(n)) == n 对连续 3000 天成立。
    """
    start_days = civil.days_from_civil(-200, 1, 1)
    assert start_days < 0
    prev = civil.civil_from_days(start_days)
    for offset in range(1, 3000):
        n = start_days + offset
        cur = civil.civil_from_days(n)
        assert civil.days_from_civil(*cur) == n, "往返失败: n=%d -> %r" % (n, cur)
        # 日期必须严格前进（按 (y,m,d) 字典序即可，同一历法下成立）
        assert cur > prev, "非单调: %r -> %r" % (prev, cur)
        prev = cur


def test_year_zero_and_negative_leap_years():
    assert civil.is_leap(0) and civil.is_leap(-4) and civil.is_leap(-400)
    assert not civil.is_leap(-1) and not civil.is_leap(-100)
    assert civil.days_in_month(-4, 2) == 29
    assert civil.days_in_month(-3, 2) == 28


def test_epoch_round_trip_including_negative():
    for epoch in (-2208988800, -1, 0, 1, 1767225600, 4102444800, 253402300799):
        parts = civil.local_naive_from_epoch(epoch)
        assert civil.epoch_from_local_naive(*parts) == epoch


def test_leap_year_rules():
    assert civil.is_leap(2000) and civil.is_leap(2024) and civil.is_leap(-4)
    assert not civil.is_leap(1900) and not civil.is_leap(2100) and not civil.is_leap(2023)


def test_days_in_month_boundaries():
    assert civil.days_in_month(2024, 2) == 29
    assert civil.days_in_month(2023, 2) == 28
    assert civil.days_in_month(2026, 4) == 30
    assert civil.days_in_month(2026, 1) == 31
    with pytest.raises(ValueError):
        civil.days_in_month(2026, 0)
    with pytest.raises(ValueError):
        civil.days_in_month(2026, 13)


def test_invalid_dates_are_rejected():
    for bad in [(2026, 2, 30), (2026, 13, 1), (2026, 4, 31), (2026, 0, 1)]:
        with pytest.raises(ValueError):
            civil.days_from_civil(*bad)


def test_format_offset_is_east_positive():
    assert civil.format_offset(-18000) == "-05:00"
    assert civil.format_offset(45900) == "+12:45"
    assert civil.format_offset(37800) == "+10:30"
    assert civil.format_offset(0) == "+00:00"
    assert civil.format_offset(-34200) == "-09:30"


def test_parse_local_accepts_documented_forms():
    assert civil.parse_local("2026-03-08 02:30") == civil.epoch_from_local_naive(2026, 3, 8, 2, 30)
    assert civil.parse_local("2026-03-08T02:30:15") == civil.epoch_from_local_naive(2026, 3, 8, 2, 30, 15)
    assert civil.parse_local("2026-03-08") == civil.epoch_from_local_naive(2026, 3, 8)
    assert civil.parse_local("  2026-03-08 02:30  ") == civil.epoch_from_local_naive(2026, 3, 8, 2, 30)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "2026-03-08T02:30:00Z",
        "2026-03-08 02:30:00+05:00",
        "2026-02-30 10:00",
        "not-a-date",
        "2026-03-08 25:00",
        "2026-03-08 02:30:00 extra",
    ],
)
def test_parse_local_rejects_invalid(bad):
    with pytest.raises(ValueError):
        civil.parse_local(bad)


def test_no_float_in_civil_module():
    """civil 全整数运算：源码里不得出现 float() / round()（确定性纪律）。"""
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "src", "tzaudit", "civil.py")
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    assert "float(" not in source
    assert "round(" not in source
