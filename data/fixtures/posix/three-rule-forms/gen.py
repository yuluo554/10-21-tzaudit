#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fixture · 三条技术坑的 POSIX tail 金标（`plan/04` §三 第 5 行 + `plan/03` §三 测试点）。

**注入了什么**（每条坑一个尾串，外加一条**反向**形态防"改对了也看不出"）：

| 尾串 | 坑 | 关键断言 |
|---|---|---|
| ``EST5EDT,M3.2.0/2,M11.1.0/2`` | PITFALL-WEST | ``EST5`` → **-18000**（不是 +18000） |
| 同上 | PITFALL-WALLSEC | ``M3.2.0/2`` 展开 → **2026-03-08 07:00Z**（不是 02:00Z） |
| ``MST7`` | 无 DST | ``dst is None``；展开零转换点 |
| ``<+1245>-12:45<+1345>,M9.5.0/2:45,M4.1.0/3:45`` | 非整点 + 西为正的对称反例 | ``+45900``；规则秒 = 2:45 = 9900 |
| ``IST-1GMT0,M10.5.0,M3.5.0/1`` | **负 DST**（爱尔兰式） | 起跳走向**负**偏移；``dublin_is_negative=True`` |
| ``<-03>3<-02>,M3.5.0/-2,M10.5.0/-1`` | 负 ``/time``（南美式） | ``time_sec = -7200``，仍按墙钟解释 |
| ``EST5EDT,M3.2.0,M11.1.0`` | 对照组（无 ``/time``） | 缺省 ``time_sec = 7200`` |

**为什么需要它**：这三条坑"改对了也看不出"——对称时区（UTC+5 对 UTC-5）在多数断言下同形。
因此金标不只存**结果**，还存**中间量**（``time_sec`` / ``offset_sec`` / 展开的 UTC）。

```bash
py -3.12 data/fixtures/posix/three-rule-forms/gen.py --check
```
"""

from __future__ import print_function

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORT_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, SUPPORT_DIR)

import _support as S  # noqa: E402

#: (名字, 尾串, 期望的 std/dst 偏移与规则, 展开年份)
CASES = [
    {
        "name": "west_positive",
        "tz": "EST5EDT,M3.2.0/2,M11.1.0/2",
        "std_offset_sec": -18000,
        "dst_offset_sec": -14400,
        "start_time_sec": 7200,
        "end_time_sec": 7200,
        "year": 2026,
        "note": "PITFALL-WEST：EST5 是 UTC-5",
    },
    {
        "name": "wall_seconds",
        "tz": "EST5EDT,M3.2.0/2,M11.1.0/2",
        "std_offset_sec": -18000,
        "dst_offset_sec": -14400,
        "start_time_sec": 7200,
        "end_time_sec": 7200,
        "year": 2026,
        "note": "PITFALL-WALLSEC：/2 是墙钟秒 → 07:00Z",
    },
    {
        "name": "no_dst",
        "tz": "MST7",
        "std_offset_sec": -25200,
        "dst_offset_sec": None,
        "start_time_sec": None,
        "end_time_sec": None,
        "year": 2026,
        "note": "无逗号段 = 无 DST（不是'缺省美式 DST'）",
    },
    {
        "name": "quarter_hour_chatham",
        "tz": "<+1245>-12:45<+1345>,M9.5.0/2:45,M4.1.0/3:45",
        "std_offset_sec": 45900,
        "dst_offset_sec": 49500,
        "start_time_sec": 9900,
        "end_time_sec": 13500,
        "year": 2026,
        "note": "+12:45 非整点；对称反例 = 西为正若写反会得 -45900",
    },
    {
        "name": "negative_dst_dublin",
        "tz": "IST-1GMT0,M10.5.0,M3.5.0/1",
        "std_offset_sec": 3600,
        "dst_offset_sec": 0,
        "start_time_sec": 7200,
        "end_time_sec": 3600,
        "year": 2026,
        "note": "负 DST：起跳走向**更小**的偏移（爱尔兰式）",
    },
    {
        "name": "negative_slash_time",
        "tz": "<-03>3<-02>,M3.5.0/-2,M10.5.0/-1",
        "std_offset_sec": -10800,
        "dst_offset_sec": -7200,
        "start_time_sec": -7200,
        "end_time_sec": -3600,
        "year": 2026,
        "note": "负 /time：可负、可为负整点（南美式）",
    },
    {
        "name": "default_time",
        "tz": "EST5EDT,M3.2.0,M11.1.0",
        "std_offset_sec": -18000,
        "dst_offset_sec": -14400,
        "start_time_sec": 7200,
        "end_time_sec": 7200,
        "year": 2026,
        "note": "对照组：缺省 /time = 02:00 墙钟",
    },
]


def _rule_from_tz(case):
    """从尾串里取出 (start_rule, end_rule)；无 DST 时为 None。

    这里**不复用产品的 parser**：本 fixture 的期望由 ``_support`` 的独立规则表给出。
    """
    return case.get("start_rule"), case.get("end_rule")


def _expanded(case):
    """规则在该年的展开 UTC（无 DST → 空列表）。"""
    start_rule = case.get("start_rule")
    end_rule = case.get("end_rule")
    if start_rule is None or end_rule is None:
        return []
    pairs = S.year_transitions(case["year"], case["std_offset_sec"],
                               case["dst_offset_sec"], start_rule, end_rule)
    return [{"utc": utc, "to_dst": to_dst} for utc, to_dst in sorted(pairs)]


#: 规则表（与本文件顶部的尾串一一对应；刻意手写，不从尾串反推）
RULES = {
    "west_positive": (("M", 3, 2, 0, 7200), ("M", 11, 1, 0, 7200)),
    "wall_seconds": (("M", 3, 2, 0, 7200), ("M", 11, 1, 0, 7200)),
    "no_dst": (None, None),
    "quarter_hour_chatham": (("M", 9, 5, 0, 9900), ("M", 4, 1, 0, 13500)),
    "negative_dst_dublin": (("M", 10, 5, 0, 7200), ("M", 3, 5, 0, 3600)),
    "negative_slash_time": (("M", 3, 5, 0, -7200), ("M", 10, 5, 0, -3600)),
    "default_time": (("M", 3, 2, 0, 7200), ("M", 11, 1, 0, 7200)),
}


def build(root):
    cases = []
    for case in CASES:
        start_rule, end_rule = RULES[case["name"]]
        enriched = dict(case, start_rule=start_rule, end_rule=end_rule)
        cases.append({
            "name": case["name"],
            "tz": case["tz"],
            "note": case["note"],
            "year": case["year"],
            "expected": {
                "std_offset_sec": case["std_offset_sec"],
                "dst_offset_sec": case["dst_offset_sec"],
                "start_time_sec": case["start_time_sec"],
                "end_time_sec": case["end_time_sec"],
                "transitions": _expanded(enriched),
            },
        })

    S.write_json(os.path.join(root, "expect.json"), {
        "fixture": "posix/three-rule-forms",
        "why": "三条技术坑（西为正 / 墙钟秒 / 无 DST 与负 DST）在对称时区上同形，必须存中间量",
        "input": {"cases": [{"name": c["name"], "tz": c["tz"], "year": c["year"]}
                            for c in cases]},
        "expected": {"cases": cases},
    })


NAMES = ["expect.json"]

if __name__ == "__main__":
    sys.exit(S.run_generators(__file__, build, NAMES, sys.argv[1:]))
