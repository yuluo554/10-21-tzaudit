# -*- coding: utf-8 -*-
"""fixture 生成器的共用件：确定性 TZif 构造 + POSIX 规则展开。

**只给 ``data/fixtures/*/gen.py`` 用**，不进 ``src/``（不进产品）。

纪律（``plan/04`` §三）：
- 禁 ``random`` / 禁读时钟 / 禁 ``set`` 迭代序；本文件不 import 它们。
- 产物**不含时间戳**；写盘一律 ``\\n`` 行尾、UTF-8 无 BOM。
- 这里的字节布局是**手写**的（RFC 8536），不复用 ``src/tzaudit/tzif.py`` 的任何常量——
  生成器与被测解析器必须各写一遍，否则"生成器写错、解析器跟着错"会互相掩盖。
"""

from __future__ import print_function

import datetime
import io
import json
import os
import struct

MAGIC = b"TZif"

#: v1 块的转换时刻是**有符号 32 位**（RFC 8536 §3.1）；超出范围的点只进 v2 块
#: （真实 ``zic`` 在 2038 之后也是这么切的）。
INT32_MIN = -2147483648
INT32_MAX = 2147483647

#: 平年每月天数（``Jn`` 映射用，**忽略** 2/29）
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


# ---------------------------------------------------------------- TZif 构造


def _ttinfo(utoff, is_dst, abbrind):
    return struct.pack(">iBB", utoff, 1 if is_dst else 0, abbrind)


def build_tzif(transitions, types, footer=None, slim=False):
    """构造一份 TZif v2。

    ``transitions`` = ``[(utc, type_index)]``（升序）；``types`` = ``[(utoff, is_dst, abbr)]``；
    ``footer`` = POSIX TZ 串或 ``None``。

    ``slim=True`` 时 v1 块**压扁成空表**（slim 构建的真实形态：v1 只留类型与缩写），
    真实转换点全在 v2 块；``slim=False`` 时 v1 块携带同一批转换点（fat 形态）。
    """
    abbr_blob = b"".join((a + "\x00").encode("ascii") for a in types_abbrs(types))
    # abbrind 必须按**字节偏移**算（不是类型序号）。
    abbrind = {}
    cursor = 0
    for name in types_abbrs(types):
        if name not in abbrind:
            abbrind[name] = cursor
        cursor += len(name) + 1
    ttinfos = b"".join(_ttinfo(off, dst, abbrind[name]) for off, dst, name in types)

    def header(counts):
        # 两个头的版本字节都是 '2'（实测 2026e 树如此；写成 \0 会让 footer 定位错位）。
        return MAGIC + b"2" + b"\x00" * 15 + struct.pack(">6I", *counts)

    full_counts = (0, 0, 0, len(transitions), len(types), len(abbr_blob))
    if slim:
        v1_counts = (0, 0, 0, 0, len(types), len(abbr_blob))
        v1_block = ttinfos + abbr_blob
    else:
        # fat 的 v1 块：**只放落在 32 位上界内的转换点**（2038 之后的点只进 v2 块）——
        # 真实 ``zic`` 的 fat 构建就是这个形态，32 位越界的写入会被 struct 拒绝。
        narrow = [(t, i) for t, i in transitions if INT32_MIN <= t <= INT32_MAX]
        v1_counts = (0, 0, 0, len(narrow), len(types), len(abbr_blob))
        v1_block = _data_block(narrow, ttinfos, abbr_blob, 4)
    out = header(v1_counts) + v1_block + header(full_counts) \
        + _data_block(transitions, ttinfos, abbr_blob, 8)
    if footer is not None:
        out += b"\n" + footer.encode("ascii") + b"\n"
    return out


def _data_block(pairs, ttinfos, abbr_blob, width):
    """一个数据块：转换时刻 + 类型索引 + ttinfo + 缩写表。"""
    if pairs:
        fmt = ">%dq" % len(pairs) if width == 8 else ">%di" % len(pairs)
        times = struct.pack(fmt, *[t for t, _ in pairs])
    else:
        times = b""
    indices = bytes(bytearray(i for _, i in pairs))
    return times + indices + ttinfos + abbr_blob


def types_abbrs(types):
    """类型表里的缩写（保持首次出现顺序，供 abbrind 计算）。"""
    seen = []
    for _, _, name in types:
        if name not in seen:
            seen.append(name)
    return seen


# ---------------------------------------------------------------- 日历（生成期用 datetime）


def _epoch(year, month, day, hour=0, minute=0, second=0):
    """naive 日历数 → epoch 秒（**不加**偏移）。"""
    base = datetime.datetime(1970, 1, 1)
    delta = datetime.datetime(year, month, day) - base
    return delta.days * 86400 + hour * 3600 + minute * 60 + second


def _nonleap_md(n):
    for index, dim in enumerate(_MONTH_DAYS):
        if n <= dim:
            return index + 1, n
        n -= dim
    raise ValueError("Jn 越界: %r" % (n,))


def dim(year, month):
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    return _MONTH_DAYS[month - 1]


def rule_local_epoch(rule, year):
    """规则在 ``year`` 年的**本地墙钟** epoch。``rule`` = ``(kind, n/mm, w, d, time_sec)``。

    这里刻意用 ``datetime`` 做日历（生成期工具），与产品侧的自研整数算法**不是同一份代码**。
    """
    kind = rule[0]
    if kind == "J":
        month, day = _nonleap_md(rule[1])
    elif kind == "N":
        base = datetime.datetime(year, 1, 1) + datetime.timedelta(days=rule[1])
        month, day = base.month, base.day
    elif kind == "M":
        _, month, week, weekday = rule[0], rule[1], rule[2], rule[3]
        first = datetime.datetime(year, month, 1)
        first_wd = (first.weekday() + 1) % 7     # 周一=0 → POSIX 周日=0
        day = 1 + (weekday - first_wd) % 7 + (week - 1) * 7
        while day > dim(year, month):
            day -= 7
    else:  # pragma: no cover
        raise ValueError("未知规则: %r" % (rule,))
    time_sec = rule[-1]
    days = (datetime.datetime(year, month, day) - datetime.datetime(1970, 1, 1)).days
    return days * 86400 + time_sec


def year_transitions(year, std_offset, dst_offset, start_rule, end_rule):
    """一年的两条转换 ``[(utc, to_dst)]``。

    起跳按**标准时**墙钟、回拨按 **DST** 墙钟解释（tzcode 语义，也是产品实现的语义）。
    """
    start_utc = rule_local_epoch(start_rule, year) - std_offset
    end_utc = rule_local_epoch(end_rule, year) - dst_offset
    return [(start_utc, True), (end_utc, False)]


def year_of_epoch(epoch):
    """epoch → 本地日历年（把 epoch 当纯日历数，不加偏移）。"""
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(epoch))).year


epoch_year = year_of_epoch


def wall_candidates(local, std_offset, dst_offset, start_rule, end_rule, span=3):
    """**独立推导**某个本地墙钟的 UTC 候选（段区间包含式，不调产品代码）。

    ``span`` 是向两侧额外看的年数——跨年规则（南半球）必须看前后两年才不漏。
    """
    year = year_of_epoch(local)
    edges = []
    for probe in range(year - span, year + span + 1):
        for utc, to_dst in year_transitions(probe, std_offset, dst_offset,
                                            start_rule, end_rule):
            edges.append((utc, dst_offset if to_dst else std_offset))
    edges.sort()

    out = []
    for index, (utc, offset) in enumerate(edges):
        end = edges[index + 1][0] if index + 1 < len(edges) else utc + 366 * 86400
        if utc + offset <= local < end + offset:
            out.append(local - offset)
    return sorted(set(out))


# ---------------------------------------------------------------- 写盘 / 比对


def write_bytes(path, data):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with io.open(path, "wb") as fh:
        fh.write(data)


def write_json(path, obj):
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read_bytes(path):
    with io.open(path, "rb") as fh:
        return fh.read()


def compare_tree(expected_root, actual_root, names):
    """逐文件比对（``---`` 表示缺件，也算不一致）。"""
    problems = []
    for rel in names:
        left = os.path.join(expected_root, *rel.split("/"))
        right = os.path.join(actual_root, *rel.split("/"))
        if not os.path.isfile(left):
            problems.append("入仓件缺失: %s" % rel)
            continue
        if not os.path.isfile(right):
            problems.append("重生成件缺失: %s" % rel)
            continue
        if read_bytes(left) != read_bytes(right):
            problems.append("逐字节不一致: %s" % rel)
    return problems


def run_generators(module_file, build, names, argv):
    """``gen.py`` 的统一主流程：``--check`` 重生成到临时目录并逐字节比对；否则写盘。"""
    import tempfile

    here = os.path.dirname(os.path.abspath(module_file))
    check = "--check" in argv

    if not check:
        build(here)
        print("%s: 写出 %d 份产物" % (os.path.basename(here), len(names)))
        return 0

    scratch = tempfile.mkdtemp(prefix="tzaudit-fixture-")
    try:
        build(scratch)
        problems = compare_tree(here, scratch, names)
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)

    if problems:
        print("%s: FAIL（%d 处）" % (os.path.basename(here), len(problems)))
        for item in problems:
            print("  FAIL  %s" % item)
        return 1
    print("%s: PASS（%d 份产物逐字节一致）" % (os.path.basename(here), len(names)))
    return 0
