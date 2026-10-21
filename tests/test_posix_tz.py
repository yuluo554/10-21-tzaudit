# -*- coding: utf-8 -*-
"""POSIX TZ 解析 —— 契约见 ``plan/03`` §三，口径见 ``data/README.md`` §4.2。

三层断言：

1. **形态覆盖**：§4.2 的全部写法（尖括号缩写 / 西为正 / 三类规则 / 负 ``/time`` / 无逗号段）。
2. **三条技术坑的反例**：每条坑一个**能跑红**的断言（`plan/03` §三 测试点 1–4）。
3. **fixture 金标**：``data/fixtures/posix/three-rule-forms/`` 逐条比对（含中间量）。

第 2 层是关键：三条坑在对称时区上"改对了也看不出"，所以断言必须落在**符号与秒数**上。
"""

import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from tzaudit import civil, posix_tz  # noqa: E402

FIXTURE = os.path.join(ROOT, "data", "fixtures", "posix", "three-rule-forms")


def _parse(text):
    return posix_tz.parse(text)


# ---------------------------------------------------------------- 1. 形态覆盖


def test_bare_std_has_no_dst():
    """``EST5``：只有标准时；**西为正** → 东为正的 -18000。"""
    tz = _parse("EST5")
    assert tz.std == (-18000, "EST")
    assert tz.dst is None
    assert tz.start is None and tz.end is None
    assert tz.has_dst is False


def test_dst_name_without_offset_takes_std_plus_one_hour():
    """``EST5EDT``：DST 偏移缺省 = std + 1h，规则段缺省。"""
    tz = _parse("EST5EDT")
    assert tz.std == (-18000, "EST")
    assert tz.dst == (-14400, "EDT")
    assert tz.start is None and tz.end is None
    assert tz.has_rules is False, "没有规则段就不能展开"


def test_explicit_dst_offset_overrides_default():
    tz = _parse("IST-1GMT0,M10.5.0,M3.5.0/1")
    assert tz.std == (3600, "IST")
    assert tz.dst == (0, "GMT")


def test_full_form_with_rules():
    tz = _parse("EST5EDT,M3.2.0,M11.1.0")
    assert tz.std == (-18000, "EST")
    assert tz.dst == (-14400, "EDT")
    assert tz.start.kind == "M" and tz.start.month == 3 and tz.start.week == 2
    assert tz.start.weekday == 0
    assert tz.end.month == 11 and tz.end.week == 1
    assert tz.start.time_sec == 7200, "缺省 /time = 02:00 墙钟"
    assert tz.end.time_sec == 7200


def test_angle_bracket_abbr_is_preferred_over_bare_letters():
    """``<+1245>`` 必须整体当缩写；否则 ``+`` 会被当偏移符号。"""
    tz = _parse("<+1245>-12:45<+1345>,M9.5.0/2:45,M4.1.0/3:45")
    assert tz.std == (45900, "+1245")
    assert tz.dst == (49500, "+1345")
    assert tz.start.time_sec == 9900, "2:45 = 9900 秒"
    assert tz.end.time_sec == 13500, "3:45 = 13500 秒"


def test_gmt_style_zero_offset():
    tz = _parse("UTC0")
    assert tz.std == (0, "UTC")
    assert tz.dst is None


@pytest.mark.parametrize("text,offset", [
    ("EST5", -18000),
    ("MST7", -25200),
    ("<+1245>-12:45<+1345>,M9.5.0/2:45,M4.1.0/3:45", 45900),
    ("ACST-9:30", 34200),
    ("<+0545>-5:45", 20700),
    ("<+00>0", 0),
])
def test_west_positive_is_flipped_to_east_positive(text, offset):
    """K8：POSIX 偏移**西为正**，解析层翻成**东为正**。"""
    assert _parse(text).std[0] == offset


# ---------------------------------------------------------------- 2. 三类规则 + /time


@pytest.mark.parametrize("text,kind,n", [
    ("EST5EDT,J60/2,J300/2", "J", 60),
    ("EST5EDT,59/2,300/2", "N", 59),
])
def test_rule_kinds(text, kind, n):
    tz = _parse(text)
    assert tz.start.kind == kind and tz.start.n == n


def test_rule_m_form_fields():
    tz = _parse("EST5EDT,M3.5.0/2,M10.5.0/2")
    start = tz.start
    assert (start.kind, start.month, start.week, start.weekday) == ("M", 3, 5, 0)


@pytest.mark.parametrize("text,time_sec", [
    ("EST5EDT,M3.2.0/2,M11.1.0/2", 7200),
    ("EST5EDT,M3.2.0/0,M11.1.0/1", 0),
    ("<-03>3<-02>,M3.5.0/-2,M10.5.0/-1", -7200),
    ("EET-2EEST,M3.4.4/50,M10.4.4/50", 180000),      # ≥ 24h 是合法的
    ("EET-2EEST,M3.4.4/26,M10.5.0", 93600),
])
def test_slash_time_is_parsed_as_wall_seconds_not_offset(text, time_sec):
    """K9：``/time`` 只解析成**墙钟秒**，解析层不做偏移加减。

    反例：``/2`` 若被当成"偏移 2 小时减去"，``time_sec`` 会变成 0 或 -7200。
    """
    tz = _parse(text)
    assert tz.start.time_sec == time_sec


# ---------------------------------------------------------------- 3. 三条技术坑的反例


def test_pitfall_west_positive_sign_actually_matters():
    """PITFALL-WEST 反例：对称时区（UTC+5 vs UTC-5）必须能区分。

    只断言 ``est.std[0] == -18000`` 还不够——把符号写成 ``+18000`` 的实现会在
    "UTC+5 的符号也是 +18000" 这种断言下同形。这里用**成对**断言把两个方向都钉死。
    """
    west = _parse("EST5")
    east = _parse("CET-1")
    assert west.std[0] == -18000
    assert east.std[0] == 3600
    assert west.std[0] != east.std[0], "符号翻反会让两者同号"


def test_pitfall_wall_seconds_expands_to_07z_not_02z():
    """PITFALL-WALLSEC 反例：``M3.2.0/2`` 在 NY 上展开得 ``07:00Z``。

    把 ``/2`` 误当"UTC 偏移"（``local + 2h``）会得 ``04:00Z``；误当"从 00:00Z 起算"
    会得 ``02:00Z``。本断言把正确值与这两种错法**同时**写出来，任一种都跑不绿。
    """
    from tzaudit import timeline

    tz = _parse("EST5EDT,M3.2.0/2,M11.1.0/2")
    (utc, _offset, _abbr, to_dst) = timeline._year_transitions(tz, 2026)[0]

    assert to_dst is True
    assert civil.format_local(utc) == "2026-03-08 07:00:00"
    wall = civil.epoch_from_local_naive(2026, 3, 8, 2, 0, 0)
    assert utc == wall - tz.std[0], "起跳按**标准时**墙钟解释"
    # 两种典型错法的值都必须与正确值不同（防"改对了也看不出"）
    assert utc != wall + tz.start.time_sec
    assert utc != wall - tz.start.time_sec


def test_pitfall_wall_seconds_governs_fall_back_too():
    """回拨按 **DST** 墙钟解释：NY ``M11.1.0/2`` → 本地 02:00 EDT → ``06:00Z``。"""
    from tzaudit import timeline

    tz = _parse("EST5EDT,M3.2.0/2,M11.1.0/2")
    (utc, _offset, _abbr, to_dst) = timeline._year_transitions(tz, 2026)[1]
    assert to_dst is False
    assert civil.format_local(utc) == "2026-11-01 06:00:00"
    assert utc == civil.epoch_from_local_naive(2026, 11, 1, 2, 0, 0) - tz.dst[0]


def test_pitfall_mst7_has_no_dst_at_all():
    """``MST7`` → ``dst is None``；下游不应凭空造出 DST 转换。"""
    tz = _parse("MST7")
    assert tz.dst is None
    assert tz.has_dst is False
    assert tz.has_rules is False


def test_rule_boundary_j60_is_march_first_even_in_leap_year():
    """``J60`` = 3/1（**跳过** 2/29）；闰年也一样。"""
    from tzaudit import timeline

    leap = timeline._rule_local_epoch(posix_tz.Rule("J", 0, n=60), 2024)
    common = timeline._rule_local_epoch(posix_tz.Rule("J", 0, n=60), 2026)
    assert civil.local_naive_from_epoch(leap)[:3] == (2024, 3, 1)
    assert civil.local_naive_from_epoch(common)[:3] == (2026, 3, 1)


def test_rule_boundary_bare_59_is_feb_29_in_leap_year():
    """裸 ``59`` = 一年第 60 天 = **含** 2/29；闰年落 2/29，平年落 3/1。"""
    from tzaudit import timeline

    leap = timeline._rule_local_epoch(posix_tz.Rule("N", 0, n=59), 2024)
    common = timeline._rule_local_epoch(posix_tz.Rule("N", 0, n=59), 2026)
    assert civil.local_naive_from_epoch(leap)[:3] == (2024, 2, 29)
    assert civil.local_naive_from_epoch(common)[:3] == (2026, 3, 1)


def test_rule_m35_is_last_sunday():
    """``M3.5.0`` = 3 月最后一个周日；2026 年是 3/29，2027 年是 3/28。"""
    from tzaudit import timeline

    for year, expected in ((2026, (2026, 3, 29)), (2027, (2027, 3, 28))):
        epoch = timeline._rule_local_epoch(posix_tz.Rule("M", 0, month=3, week=5, weekday=0), year)
        assert civil.local_naive_from_epoch(epoch)[:3] == expected


# ---------------------------------------------------------------- 4. 失败路径


@pytest.mark.parametrize("text,needle", [
    ("", "空串"),
    ("EST", "缺少 std 偏移"),
    ("ES5", "至少 3 个字母"),
    ("<EST5", "尖括号未闭合"),
    ("EST5EDT,M3.2.0", "恰好两段"),
    ("EST5EDT,M13.2.0,M11.1.0", "月份越界"),
    ("EST5EDT,M3.6.0,M11.1.0", "周序越界"),
    ("EST5EDT,M3.2.7,M11.1.0", "星期越界"),
    ("EST5EDT,J0/2,J300/2", "Jn 越界"),
    ("EST5EDT,366/2,300/2", "n 越界"),
    ("EST5EDT,M3.2.0/25:70,M11.1.0", "越界"),
    ("EST5EDT,M3.2.0/,M11.1.0", "为空"),
    ("EST5", None),   # 合法：用来确认 parametrize 的 needle=None 分支不被误用
])
def test_invalid_strings_raise_posix_tz_error(text, needle):
    if needle is None:
        assert posix_tz.parse(text) is not None
        return
    with pytest.raises(posix_tz.PosixTzError) as exc:
        posix_tz.parse(text)
    assert needle in str(exc.value), "%r 的错误信息里应含 %r: %s" % (text, needle, exc.value)


def test_non_string_input_is_rejected():
    with pytest.raises(posix_tz.PosixTzError):
        posix_tz.parse(None)


def test_never_guesses_a_rule():
    """不做宽容解析：缺规则的 ``EST5EDT`` 不得凭空补一个美式规则。"""
    tz = _parse("EST5EDT")
    assert tz.start is None and tz.end is None
    assert tz.has_rules is False


# ---------------------------------------------------------------- 5. fixture 金标


def _load_fixture():
    with io.open(os.path.join(FIXTURE, "expect.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_fixture_covers_all_seven_cases():
    doc = _load_fixture()
    names = [case["name"] for case in doc["expected"]["cases"]]
    assert names == [
        "west_positive", "wall_seconds", "no_dst", "quarter_hour_chatham",
        "negative_dst_dublin", "negative_slash_time", "default_time",
    ]
    # 输入的 name/tz 必须与期望侧一一对应（防"期望侧多一条、输入侧少一条"）
    assert [case["name"] for case in doc["input"]["cases"]] == names
    assert [case["tz"] for case in doc["input"]["cases"]] == \
           [case["tz"] for case in doc["expected"]["cases"]]


@pytest.mark.parametrize("index", range(7))
def test_fixture_case_matches_parser_output(index):
    """fixture 的**中间量**必须与解析结果逐项一致（不只比最终展开）。"""
    doc = _load_fixture()
    case = doc["expected"]["cases"][index]
    tz = posix_tz.parse(case["tz"])
    expected = case["expected"]

    assert tz.std[0] == expected["std_offset_sec"], case["name"]
    if expected["dst_offset_sec"] is None:
        assert tz.dst is None, case["name"]
        assert expected["transitions"] == []
        return
    assert tz.dst[0] == expected["dst_offset_sec"], case["name"]
    assert tz.start.time_sec == expected["start_time_sec"], case["name"]
    assert tz.end.time_sec == expected["end_time_sec"], case["name"]


@pytest.mark.parametrize("index", range(7))
def test_fixture_transitions_match_independent_expansion(index):
    """金标的展开值由 ``gen.py`` 的独立规则表算出，这里用产品实现复算。"""
    from tzaudit import timeline

    doc = _load_fixture()
    case = doc["expected"]["cases"][index]
    tz = posix_tz.parse(case["tz"])
    expected = [(item["utc"], item["to_dst"]) for item in case["expected"]["transitions"]]

    if not tz.has_rules:
        assert expected == []
        return
    actual = timeline._year_transitions(tz, case["year"])
    assert [(utc, to_dst) for utc, _offset, _abbr, to_dst in actual] == expected, case["name"]


def test_fixture_generator_is_byte_stable():
    """fixture 的生成器必须能重生成出**逐字节一致**的产物（`plan/04` §三 硬纪律 2）。"""
    import subprocess

    script = os.path.join(FIXTURE, "gen.py")
    proc = subprocess.run([sys.executable, script, "--check"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
