#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fixture · 墙钟风险窗口的金标（`plan/04` §三；M3 必覆盖的形态）。

**注入了什么**：一棵**合成** zoneinfo 树（5 个 zone），每个 zone 注入一种形态：

| zone | 注入的形态 | 期望窗口 |
|---|---|---|
| ``Zone/Standard`` | 美式 DST（整小时） | GAP + OVERLAP，各 60 分钟 |
| ``Zone/HalfHour`` | 30 分钟 DST（Lord_Howe 式） | GAP + OVERLAP，各 30 分钟 |
| ``Zone/QuarterHour`` | +12:45 非整点（Chatham 式） | GAP + OVERLAP，各 60 分钟 |
| ``Zone/NegativeDst`` | 负 DST（Dublin 式：冬季 offset 为 0、夏季为 +3600） | GAP + OVERLAP，**方向仍按 offset 差** |
| ``Zone/NoDst`` | 无 DST（``MST7``） | **零条**（反例：无窗口不等于不扫描） |

外加一条**陷阱**：``Zone/AbbrevOnly`` 的某年有一次"offset 不变、只换缩写"的转换点。
它**不是**墙钟窗口，实现若只看"转换点存在"就会误报。

**为什么需要它**（`plan/03` §五 的三条反例必须能被独立复核）：

1. **GAP 与 OVERLAP 的方向**不能反——合成树里两种形态各自独立，金标逐条钉死。
2. **30 分钟 / 45 分钟**这类非整点形态，在真实树里能验，但**金标必须自带**一份，
   否则"只验了 NY"这种退化实现也能全绿。
3. **零窗口的 zone 必须真的零窗口**（``NoDst``）——防"不扫描直接返回空"。

**期望值的推导方式**：**不调产品代码**。用 ``_support.wall_candidates``
（段区间包含式 + 手写规则表）独立算出每个探测点的 UTC 候选数，再按"候选数 → 墙钟区间"
推导出窗口区间。与产品实现（枚举 offset + 自洽校验）是两条不同的推理路径。

```bash
py -3.12 data/fixtures/windows/gen.py            # 写产物
py -3.12 data/fixtures/windows/gen.py --check    # 重生成并逐字节比对
```
"""

from __future__ import print_function

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORT_DIR = os.path.dirname(HERE)
sys.path.insert(0, SUPPORT_DIR)

import _support as S  # noqa: E402

#: 被扫描的年份（固定输入常量，不是观测值）
YEAR = 2026

#: 每个 zone 的形态定义。
#: ``rules`` = ``(start_rule, end_rule)``，形如 ``("M", 3, 2, 0, 7200)`` = M3.2.0/2。
#: ``types`` = ``[(offset_sec, is_dst, abbr)]``；``footer`` = POSIX TZ 串。
ZONES = [
    {
        "name": "Zone/Standard",
        "footer": "EST5EDT,M3.2.0/2,M11.1.0/2",
        "std_offset": -18000,
        "dst_offset": -14400,
        "types": [(-18000, False, "EST"), (-14400, True, "EDT")],
        "rules": (("M", 3, 2, 0, 7200), ("M", 11, 1, 0, 7200)),
        "note": "美式整小时 DST",
    },
    {
        "name": "Zone/HalfHour",
        "footer": "<+1030>-10:30<+11>-11,M10.1.0/2,M4.1.0/2",
        "std_offset": 37800,
        "dst_offset": 39600,
        "types": [(37800, False, "+1030"), (39600, True, "+11")],
        "rules": (("M", 10, 1, 0, 7200), ("M", 4, 1, 0, 7200)),
        "note": "30 分钟 DST（Lord_Howe 式）；南半球：先回拨再起跳",
    },
    {
        "name": "Zone/QuarterHour",
        "footer": "<+1245>-12:45<+1345>,M9.5.0/2:45,M4.1.0/3:45",
        "std_offset": 45900,
        "dst_offset": 49500,
        "types": [(45900, False, "+1245"), (49500, True, "+1345")],
        "rules": (("M", 9, 5, 0, 9900), ("M", 4, 1, 0, 13500)),
        "note": "+12:45 非整点（Chatham 式）",
    },
    {
        "name": "Zone/NegativeDst",
        "footer": "IST-1GMT0,M10.5.0,M3.5.0/1",
        "std_offset": 3600,
        "dst_offset": 0,
        "types": [(3600, False, "IST"), (0, True, "GMT")],
        "rules": (("M", 10, 5, 0, 7200), ("M", 3, 5, 0, 3600)),
        "note": "负 DST（Dublin 式）：冬季 offset=0 且 is_dst=True",
    },
    {
        "name": "Zone/NoDst",
        "footer": "MST7",
        "std_offset": -25200,
        "dst_offset": None,
        "types": [(-25200, False, "MST")],
        "rules": (None, None),
        "note": "无 DST → 零窗口（反例：无窗口 ≠ 没扫描）",
    },
    {
        "name": "Zone/AbbrevOnly",
        "footer": "EST5EDT,M3.2.0/2,M11.1.0/2",
        "std_offset": -18000,
        "dst_offset": -14400,
        "types": [(-18000, False, "EST"), (-14400, True, "EDT")],
        "rules": (("M", 3, 2, 0, 7200), ("M", 11, 1, 0, 7200)),
        "note": "陷阱：表内额外插入一个'offset 不变、只换缩写'的转换点 → 不得报窗口",
        "extra_table_transitions": True,
    },
]

#: 表内转换点：只放"与 tail 不冲突"的早年点，让 tail 承担当年语义。
#: 合成树刻意用 **slim 形态**（v1 块压扁）：与真实 slim 树同形。
def _transitions(case):
    """该 zone 的表内转换点（只到 1990 年），类型索引固定为 0。"""
    if case["rules"][0] is None:
        return []
    out = []
    for year in range(1970, 1991):
        for utc, to_dst in S.year_transitions(year, case["std_offset"], case["dst_offset"],
                                              case["rules"][0], case["rules"][1]):
            out.append((utc, 1 if to_dst else 0))
    out.sort()
    if case.get("extra_table_transitions"):
        # 陷阱：在**被扫描的那一年**（YEAR）插一个"offset 不变、只换缩写"的转换点。
        # 它的 offset 与前后**完全相同**（-18000 = EST），所以**不是**墙钟窗口；
        # 实现若只看"有没有转换点"就会在这里误报一条。
        #
        # 位置选在 **1 月 15 日**（冬季，与 tail 的 EST 状态一致）：若放在夏天，
        # 表说"6 月是 EST"而 tail 说"6 月是 EDT"——那是**自相矛盾**的树，
        # 会在表/tail 交界处造出一条假窗口（不是我们要测的东西）。
        alias = (-18000, False, "XST")
        case["types"].append(alias)
        out.append((S._epoch(YEAR, 1, 15), 2))
        out.sort()
    return out


def _expected_windows(case):
    """**独立推导**该 zone 在 ``YEAR`` 的墙钟窗口（不调产品代码）。

    推导路径（与产品实现不同路）：
    - 用 ``_support.year_transitions`` 算出该年的两条转换 UTC；
    - 转换两侧的 offset 由手写的形态表给出（``std_offset`` / ``dst_offset``）；
    - 墙钟区间 = ``[utc + before, utc + after)``；
    - 再用 ``_support.wall_candidates``（段区间包含式）复核区间内的候选数：
      GAP 必须 0 个候选、OVERLAP 必须 2 个且 offset 不同——不满足就丢弃（宁漏不误报）。
    """
    if case["rules"][0] is None:
        return []

    std_offset = case["std_offset"]
    dst_offset = case["dst_offset"]
    pairs = S.year_transitions(YEAR, std_offset, dst_offset,
                               case["rules"][0], case["rules"][1])
    # pairs = [(utc, to_dst)]；起跳走向 dst、回拨走向 std
    windows_out = []
    for utc, to_dst in pairs:
        after = dst_offset if to_dst else std_offset
        before = std_offset if to_dst else dst_offset
        if after == before:
            continue
        if after > before:
            kind = "GAP"
            start_local = utc + before
            end_local = utc + after
        else:
            kind = "OVERLAP"
            start_local = utc + after
            end_local = utc + before
        if not _verified(kind, start_local, end_local, case):
            continue
        duration = end_local - start_local
        windows_out.append({
            "type": kind,
            "start_local": start_local,
            "end_local": end_local,
            "duration_min": duration // 60,
            "residual_sec": duration % 60,
            "offset_before": before,
            "offset_after": after,
        })
    windows_out.sort(key=lambda item: (item["start_local"], item["type"]))
    return windows_out


def _verified(kind, start_local, end_local, case):
    """独立复核：区间内的 UTC 候选数必须与窗口类型一致。

    用 ``_support.wall_candidates``（段区间包含式，与产品实现的"枚举 offset + 自洽校验"
    是两条不同的推理路径）。
    """
    std_offset = case["std_offset"]
    dst_offset = case["dst_offset"]
    if dst_offset is None:
        dst_offset = std_offset
    for probe in range(start_local, end_local):
        candidates = S.wall_candidates(probe, std_offset, dst_offset,
                                       case["rules"][0], case["rules"][1])
        if kind == "GAP":
            if candidates:
                return False
        else:
            if len(candidates) != 2:
                return False
    return True


def _format_local(epoch):
    """epoch → ``YYYY-MM-DD HH:MM:SS``（生成期工具用 ``datetime``，与产品侧自研算法不同路）。"""
    import datetime

    dt = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(epoch))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_offset(offset_sec):
    """秒 → ``+HH:MM``（东为正）。"""
    sign = "+" if offset_sec >= 0 else "-"
    total = abs(int(offset_sec))
    hh, rem = divmod(total, 3600)
    mm = rem // 60
    return "%s%02d:%02d" % (sign, hh, mm)


def build(root):
    tree = os.path.join(root, "tree")
    os.makedirs(tree, exist_ok=True)

    expected = []
    for case in ZONES:
        blob = S.build_tzif(_transitions(case), case["types"], case["footer"], slim=True)
        S.write_bytes(os.path.join(tree, *case["name"].split("/")), blob)

        rows = []
        for item in _expected_windows(case):
            rows.append({
                "type": item["type"],
                "start_local": _format_local(item["start_local"]),
                "end_local": _format_local(item["end_local"]),
                "duration_min": item["duration_min"],
                "residual_sec": item["residual_sec"],
                "offset_before": _format_offset(item["offset_before"]),
                "offset_after": _format_offset(item["offset_after"]),
            })
        expected.append({
            "zone": case["name"],
            "year": YEAR,
            "note": case["note"],
            "windows": rows,
        })

    S.write_json(os.path.join(root, "expect.json"), {
        "fixture": "windows/wall-clock-windows",
        "why": "GAP/OVERLAP 的方向 + 30 分钟 / 45 分钟 / 负 DST 三形态 + 零窗口反例；"
               "期望值由段区间包含式独立推导，不调产品代码",
        "input": {
            "tree": "tree",
            "year": YEAR,
            "zones": [{"name": case["name"], "footer": case["footer"],
                        "note": case["note"]} for case in ZONES],
        },
        "expected": {"windows": expected},
    })


NAMES = ["expect.json", "tree/Zone/Standard", "tree/Zone/HalfHour",
         "tree/Zone/QuarterHour", "tree/Zone/NegativeDst", "tree/Zone/NoDst",
         "tree/Zone/AbbrevOnly"]

if __name__ == "__main__":
    sys.exit(S.run_generators(__file__, build, NAMES, sys.argv[1:]))
