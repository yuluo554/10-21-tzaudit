#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fixture · 从 IANA 源码包自建的 fat 树 vs PyPI slim 树（`plan/04` §三 第 1 行 / Q1 定案）。

**注入了什么**：**同一年（2026e）真实数据**的两种构建形态，各 6 个 zone：

- ``fat/``：由 ``tzdata2026e.tar.gz`` 的 ``Rule`` / ``Zone`` 行**编译**出的显式表
  （覆盖 1900–2037，转换点全部物化，**无** footer、不依赖 tail）。
- ``slim/``：从 PyPI wheel 的 slim 树原样拷贝（表只到 2020 前后，语义靠 footer 承载）。

**为什么需要它**：主金标两棵树都是 slim（Q1）。若没有一条"fat 与 slim 语义等价"的断言，
"slim 依赖 tail"这个结论就只是断言而非证据。本 fixture 给出**同源同版本**的对照：
fat 的转换点由 IANA 规则独立编译，slim 的转换点由上游 wheel 提供 —— 两条独立来源。

**已知偏差（如实标注）**：本机**无 ``zic``**（实测 2026-10-21），因此 fat 树由本脚本的规则
编译器生成，**不是** ``zic`` 的产物。编译器只覆盖这 6 个 zone 用到的形态；遇到不认识的行
直接报错（不猜）。编译结果的正确性由 ``tests/test_slim_fat.py`` 反向验证：与 wheel 的
显式表在 wheel 的表覆盖区间内逐点比对。

```bash
py -3.12 data/fixtures/tzif/source-vs-wheel/gen.py --check
```
"""

from __future__ import print_function

import datetime
import os
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORT_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, SUPPORT_DIR)

import _support as S  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(SUPPORT_DIR))
TARBALL = os.path.join(ROOT, "data", "_downloads", "tzdata2026e.tar.gz")
WHEEL_TREE = os.path.join(ROOT, "data", "_downloads", "slim", "2026e")

#: 6 个 zone：三种特殊形态（负 DST / 30 分钟 / 45 分钟）+ 表内零迁移 + 历史复杂 + 固定偏移
ZONES = [
    ("America/New_York", ("northamerica",)),
    ("America/Vancouver", ("northamerica",)),
    ("Europe/Dublin", ("europe",)),
    ("Australia/Lord_Howe", ("australasia",)),
    ("Pacific/Chatham", ("australasia",)),
    ("Asia/Tehran", ("asia",)),
]

#: fat 表的编译窗口（超出它的部分不参与比对）
FAT_FIRST_YEAR = 1900
FAT_LAST_YEAR = 2037

#: 重叠区间：两棵树都有明确语义的 UTC 范围
OVERLAP_START = S._epoch(1990, 1, 1)
OVERLAP_END = S._epoch(2030, 1, 1)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# ---------------------------------------------------------------- 源码读取


def _lines(members):
    """逐个成员产出 ``(member, fields)``；去掉注释与空行。"""
    with tarfile.open(TARBALL) as archive:
        for member in members:
            text = archive.extractfile(member).read().decode("utf-8")
            for raw in text.split("\n"):
                line = raw.split("#", 1)[0].rstrip()
                if not line.strip():
                    continue
                yield member, raw, line


def _parse_source(members):
    """→ ``(rules, zones)``；``zones[name]`` = ``[dict(std, rules, fmt, until_fields)]``。"""
    rules = {}
    zones = {}
    current = None
    for _member, raw, line in _lines(members):
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "Rule":
            rule = {
                "from": int(fields[2]),
                "to": int(fields[2]) if fields[3] == "only"
                      else (FAT_LAST_YEAR + 1 if fields[3] == "max" else int(fields[3])),
                "month": fields[5],
                "on": fields[6],
                "at": fields[7],
                "save": fields[8],
                "letter": fields[9] if len(fields) > 9 else "-",
            }
            rules.setdefault(fields[1], []).append(rule)
            current = None
        elif fields[0] == "Zone":
            current = fields[1]
            zones[current] = [_zone_entry(fields[2:])]
        elif fields[0] in ("Link", "Leap", "Expires"):
            current = None
        elif current is not None and raw[:1] in ("\t", " "):
            zones[current].append(_zone_entry(fields))
        else:
            current = None
    return rules, zones


def _zone_entry(fields):
    """``STDOFF RULES FORMAT [UNTIL...]`` → dict。"""
    if len(fields) < 3:
        raise ValueError("Zone 行字段不足: %r" % (fields,))
    return {"std": fields[0], "rules": fields[1], "fmt": fields[2],
            "until": fields[3:]}


# ---------------------------------------------------------------- 时间与日历


def _hms(text):
    """``[-]h[:mm[:ss]]`` → 秒。源码里偏移是**东为正**。"""
    sign = -1 if text.startswith("-") else 1
    body = text.lstrip("+-")
    parts = body.split(":")
    total = int(parts[0]) * 3600
    if len(parts) > 1:
        total += int(parts[1]) * 60
    if len(parts) > 2:
        total += int(parts[2])
    return sign * total


def _at_seconds(text):
    """规则/UNTL 的时间字段 → ``(seconds, kind)``；``kind`` ∈ ``{w, s, u}``。"""
    kind = "w"
    if text and text[-1] in "wsugz":
        suffix = text[-1]
        kind = {"w": "w", "s": "s", "u": "u", "g": "u", "z": "u"}[suffix]
        text = text[:-1]
    return _hms(text), kind


def _day_in_month(on, year, month):
    if on == "lastSun" or on.startswith("last"):
        weekday = WEEKDAYS.index(on[4:])
        day = S.dim(year, month)
        while (datetime.date(year, month, day).weekday() + 1) % 7 != weekday:
            day -= 1
        return day
    if ">=" in on:
        name, _, num = on.partition(">=")
        weekday = WEEKDAYS.index(name)
        day = int(num)
        while (datetime.date(year, month, day).weekday() + 1) % 7 != weekday:
            day += 1
        return day
    return int(on)


def _rule_wall_epoch(rule, year):
    """规则在 ``year`` 年的**日历时刻** + 该 ``at`` 的时间基准。

    ``kind`` 必须原样带出去（``w`` / ``s`` / ``u``）：Chatham 的规则全是 ``2:45s``
    （**标准时**基准），把它当墙钟会让回拨点整体偏 1 小时。
    """
    month = MONTHS.index(rule["month"]) + 1
    day = _day_in_month(rule["on"], year, month)
    seconds, kind = _at_seconds(rule["at"])
    return S._epoch(year, month, day) + seconds, kind


def _until_utc(fields, start_year, std_offset):
    """Zone 行的 UNTIL → UTC epoch（缺省月/日/时间：1 月 1 日 00:00 墙钟）。

    ``day`` 也可能是 ``Sun>=16`` / ``lastSun`` 这类表达式（如 ``2038 Mar Sun>=16``）。
    """
    year = int(fields[0])
    month = MONTHS.index(fields[1]) + 1 if len(fields) > 1 else 1
    if len(fields) > 2:
        day = _day_in_month(fields[2], year, month)
    else:
        day = 1
    seconds, kind = _at_seconds(fields[3]) if len(fields) > 3 else (0, "w")
    local = S._epoch(year, month, day) + seconds
    if kind == "u":
        return local
    return local - std_offset      # 'w' 与 's' 在本 fixture 的 6 个 zone 里等价


# ---------------------------------------------------------------- 编译


def _numeric_format(offset):
    """zic 的 ``%z`` 缩写形态：``+1030`` / ``+11`` / ``-0930``。"""
    sign = "+" if offset >= 0 else "-"
    total = abs(offset)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if seconds:
        return "%s%02d%02d%02d" % (sign, hours, minutes, seconds)
    if minutes:
        return "%s%02d%02d" % (sign, hours, minutes)
    return "%s%02d" % (sign, hours)


def _abbr(fmt, letter, offset, is_dst):
    """按 zic 口径造缩写。

    三种形态：

    - ``%z`` → 数值形态（``+1030``）。
    - ``E%sT`` → 用 letter 替换 ``%s``（``-`` 表示空串）。
    - ``GMT/IST`` → **斜杠对：左 = 标准时名、右 = DST 名**（zic 手册的语义）。
      爱尔兰用负 DST 建模，所以它的 ``IST/GMT`` 在 ``is_dst=False`` 时给 ``IST``、
      ``is_dst=True`` 时给 ``GMT``——看起来"反了"，实际正是 zic 的规则。
    """
    if fmt == "%z":
        return _numeric_format(offset)
    if "/" in fmt:
        standard, _, dst_name = fmt.partition("/")
        return dst_name if is_dst else standard
    if "%s" in fmt:
        return fmt.replace("%s", "" if letter == "-" else letter)
    return fmt


def _zone_candidates(entry, rules, lo_year, hi_year):
    """一个 zone entry 内的规则候选（按近似时刻升序）。

    ``approx`` 用标准时换算——只用于**排序**（转换之间相隔数月，小时级偏差不影响次序）。
    """
    std_offset = _hms(entry["std"])
    candidates = []
    for rule in rules[entry["rules"]]:
        for year in range(max(rule["from"], lo_year), min(rule["to"], hi_year) + 1):
            moment, kind = _rule_wall_epoch(rule, year)
            candidates.append({
                "moment": moment,
                "kind": kind,
                "save": _hms(rule["save"]),
                "letter": rule["letter"],
                "approx": moment if kind == "u" else moment - std_offset,
            })
    candidates.sort(key=lambda item: item["approx"])
    return candidates


def _resolve_entry_candidates(entry, candidates, std_offset):
    """候选 → ``[(utc, offset, is_dst, abbr)]``；``w`` 基准按**转换前**的偏移换算。"""
    resolved = []
    previous_offset = std_offset
    for item in candidates:
        if item["kind"] == "u":
            utc = item["moment"]
        elif item["kind"] == "s":
            utc = item["moment"] - std_offset
        else:
            utc = item["moment"] - previous_offset      # 转换**前**的墙钟
        offset = std_offset + item["save"]
        resolved.append((utc, offset, item["save"] != 0,
                         _abbr(entry["fmt"], item["letter"], offset, item["save"] != 0)))
        previous_offset = offset
    return resolved


def _entry_end_utc(entry, candidates, std_offset):
    """Zone 行的 UNTIL → UTC。

    ``UNTIL`` 的时间是**墙钟**，必须用**当时正在生效**的偏移换算——用 entry 的 std 偏移
    会让 Vancouver ``2026 Nov 1 2:00`` 差 1 小时（那时 DST 还在生效）。做法是迭代到不动点：
    先用 std 偏移取一个近似界 → 找出该界**之前**（严格早于）的最后一条规则 → 重算。

    严格早于是必须的：Vancouver 2026 的 UNTIL 与它的回拨规则落在**同一墙钟时刻**，
    把那条回拨算进来会得到 ``10:00Z``；上游 wheel 是 ``09:00Z``（回拨前的 PDT）。
    """
    if not entry["until"]:
        return None
    provisional = _until_utc(entry["until"], FAT_FIRST_YEAR, std_offset)
    for _attempt in range(4):
        in_effect = std_offset
        for item in candidates:                  # 候选是 dict（含 approx/moment/save）
            if item["approx"] < provisional:
                in_effect = std_offset + item["save"]
        refined = _until_utc(entry["until"], FAT_FIRST_YEAR, in_effect)
        if refined == provisional:
            return refined
        provisional = refined
    return provisional


def compile_zone(entries, rules):
    """Zone 定义 → ``[(utc, offset_sec, is_dst, abbr)]``（升序、无 footer）。

    逐 zone entry（各自有 std 偏移与生效区间 ``[cursor, end)``），区间内按年展开规则。
    **不借出区间外的年份**（借出会让 fat 比上游 wheel 早/晚一年起跳）。
    """
    transitions = []
    cursor = None      # 当前 entry 的生效起点（UTC）；None = 有史以来
    for entry in entries:
        std_offset = _hms(entry["std"])
        ruleset = entry["rules"]
        fmt = entry["fmt"]

        if ruleset == "-":
            transitions.append((cursor if cursor is not None else S._epoch(FAT_FIRST_YEAR, 1, 1),
                                std_offset, False, _abbr(fmt, "-", std_offset, False)))
            cursor = _entry_end_utc(entry, [], std_offset)
        elif ruleset not in rules:
            # RULES 字段也可以是**固定 save 偏移**（如 Dublin 的 ``1:00``），不是 ruleset 名。
            save = _hms(ruleset)
            offset = std_offset + save
            transitions.append((cursor if cursor is not None else S._epoch(FAT_FIRST_YEAR, 1, 1),
                                offset, save != 0, _abbr(fmt, "-", offset, save != 0)))
            cursor = _entry_end_utc(entry, [], std_offset)
        else:
            lo = S.epoch_year(cursor) if cursor is not None else FAT_FIRST_YEAR - 1
            candidates = _zone_candidates(entry, rules, lo, FAT_LAST_YEAR)
            end = _entry_end_utc(entry, candidates, std_offset)
            resolved = _resolve_entry_candidates(entry, candidates, std_offset)
            for utc, offset, is_dst, abbr in resolved:
                if cursor is not None and utc < cursor:
                    continue
                if end is not None and utc >= end:
                    continue
                transitions.append((utc, offset, is_dst, abbr))
            cursor = end
        if cursor is None:
            break

    transitions.sort(key=lambda item: item[0])
    # 同一 UTC 只留最后一条（"后写覆盖前写" = 源码里后行优先的语义）
    deduped = {}
    for utc, offset, is_dst, abbr in transitions:
        deduped[utc] = (utc, offset, is_dst, abbr)
    return [deduped[key] for key in sorted(deduped)]


def _tzif_from_table(transitions):
    """显式表 → TZif v2（**无 footer**：fat 形态不靠 tail）。"""
    types = []
    for _utc, offset, is_dst, abbr in transitions:
        entry = (offset, is_dst, abbr)
        if entry not in types:
            types.append(entry)
    if not types:
        types = [(0, False, "UTC")]
    index_of = {entry: index for index, entry in enumerate(types)}
    pairs = [(utc, index_of[(offset, is_dst, abbr)])
             for utc, offset, is_dst, abbr in transitions]
    return S.build_tzif(pairs, types, footer=None, slim=False)


# ---------------------------------------------------------------- 构建


def build(root):
    if not os.path.isfile(TARBALL) or not os.path.isdir(WHEEL_TREE):
        raise SystemExit("缺 data/_downloads（先跑 tools/fetch_tzdb.py）")

    members = sorted(set(sum((list(m) for _z, m in ZONES), [])))
    rules, zones = _parse_source(members)

    manifest = []
    for zone, _members in ZONES:
        entries = zones.get(zone)
        if not entries:
            raise SystemExit("源码里找不到 zone: %s" % zone)
        table = compile_zone(entries, rules)
        if not table:
            raise SystemExit("%s 编译出 0 个转换点" % zone)
        blob = _tzif_from_table(table)
        S.write_bytes(os.path.join(root, "fat", *zone.split("/")), blob)

        wheel_path = os.path.join(WHEEL_TREE, *zone.split("/"))
        S.write_bytes(os.path.join(root, "slim", *zone.split("/")),
                      S.read_bytes(wheel_path))

        manifest.append({
            "zone": zone,
            "fat_transitions": len(table),
            "fat_first_year": S.epoch_year(table[0][0]),
            "fat_last_year": S.epoch_year(table[-1][0]),
        })

    S.write_json(os.path.join(root, "expect.json"), {
        "fixture": "tzif/source-vs-wheel",
        "why": "同源同版本的 fat（源码规则编译）与 slim（上游 wheel）在重叠区间内语义等价",
        "known_deviation": "本机无 zic；fat 树由 gen.py 的规则编译器生成，不是 zic 产物",
        "input": {
            "source": "data/_downloads/tzdata2026e.tar.gz",
            "slim_tree": "data/_downloads/slim/2026e",
            "fat_range": [FAT_FIRST_YEAR, FAT_LAST_YEAR],
        },
        "expected": {
            "overlap_start": OVERLAP_START,
            "overlap_end": OVERLAP_END,
            "zones": manifest,
        },
    })


NAMES = ["expect.json"] + [
    "%s/%s" % (kind, zone) for kind in ("fat", "slim") for zone, _m in ZONES
]

if __name__ == "__main__":
    sys.exit(S.run_generators(__file__, build, NAMES, sys.argv[1:]))
