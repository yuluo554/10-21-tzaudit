#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fixture · 同语义的 slim / fat 两种 TZif 编码（`plan/04` §三 第 1 行）。

**注入了什么**：同一套规则（``EST5EDT,M3.2.0,M11.1.0``）的三种编码——

| 文件 | 形态 | 表内转换点 | footer |
|---|---|---|---|
| ``fat.tzif`` | zic ``-b fat`` 形态：显式表覆盖 1970–2035，v1 块也带全表 | 132 | 有 |
| ``slim.tzif`` | zic ``-b slim`` 形态：显式表只到 1987，v1 块压扁为空表 | 36 | 有 |
| ``tail_only.tzif`` | 极端 slim：表为空，语义**全在** footer | 0 | 有 |

**为什么需要它**：slim 树里大量 zone 的语义靠 POSIX tail 承载（表里看不到）。若只读表，
三者会被判成"三个完全不同的 zone"。本 fixture 断言：**重叠区间内**三者的
``to_local`` / ``resolve_local`` 逐点一致（Q1 定案：不要求版本号相同，只要求重叠区间语义等价）。

```bash
py -3.12 data/fixtures/tzif/slim-vs-fat/gen.py           # 写产物
py -3.12 data/fixtures/tzif/slim-vs-fat/gen.py --check   # 重生成并逐字节比对
```
"""

from __future__ import print_function

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORT_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, SUPPORT_DIR)

import _support as S  # noqa: E402

FOOTER = "EST5EDT,M3.2.0,M11.1.0"
STD_OFFSET = -18000
DST_OFFSET = -14400
START_RULE = ("M", 3, 2, 0, 7200)     # M3.2.0/2
END_RULE = ("M", 11, 1, 0, 7200)      # M11.1.0/2

#: 重叠区间（三者都有明确定义的范围）；超出它的部分**不参与比对**
OVERLAP_START = S._epoch(1970, 1, 1)
OVERLAP_END = S._epoch(2036, 1, 1)

#: 抽样本地时刻（覆盖：标准时 / DST / GAP 03-08 02:30 / OVERLAP 11-01 01:30）
SAMPLE_LOCALS = [
    "2026-01-15 12:00:00",
    "2026-07-01 12:00:00",
    "2026-03-08 02:30:00",
    "2026-11-01 01:30:00",
    "2026-03-08 01:59:59",
    "2026-03-08 03:00:00",
    "2026-11-01 00:59:59",
    "2026-11-01 02:00:00",
]

TYPES = [
    (STD_OFFSET, False, "EST"),
    (DST_OFFSET, True, "EDT"),
]


def _transitions(first_year, last_year):
    """``first_year``–``last_year``（含）每年的两条转换，直接给**类型索引**。"""
    out = []
    for year in range(first_year, last_year + 1):
        for utc, to_dst in S.year_transitions(year, STD_OFFSET, DST_OFFSET,
                                              START_RULE, END_RULE):
            out.append((utc, 1 if to_dst else 0))
    out.sort()
    return out


def _sample_local_epoch(text):
    import datetime
    dt = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    return (dt - datetime.datetime(1970, 1, 1)).days * 86400 + \
        dt.hour * 3600 + dt.minute * 60 + dt.second


def _expected_candidates(local):
    """**独立**算期望候选（不调产品代码）：段区间包含式，直接从规则推导。"""
    return S.wall_candidates(local, STD_OFFSET, DST_OFFSET, START_RULE, END_RULE)


def build(root):
    files = {
        "fat.tzif": S.build_tzif(_transitions(1970, 2035), TYPES, FOOTER, slim=False),
        "slim.tzif": S.build_tzif(_transitions(1970, 1987), TYPES, FOOTER, slim=True),
        "tail_only.tzif": S.build_tzif([], TYPES, FOOTER, slim=True),
    }
    for name, data in files.items():
        S.write_bytes(os.path.join(root, name), data)

    expect = {
        "fixture": "tzif/slim-vs-fat",
        "why": "同一套规则三种编码；重叠区间内 to_local / resolve_local 必须逐点一致",
        "input": {
            "footer": FOOTER,
            "std_offset_sec": STD_OFFSET,
            "dst_offset_sec": DST_OFFSET,
            "overlap_start": OVERLAP_START,
            "overlap_end": OVERLAP_END,
            "files": [
                {"name": "fat.tzif", "table_transitions": len(_transitions(1970, 2035))},
                {"name": "slim.tzif", "table_transitions": len(_transitions(1970, 1987))},
                {"name": "tail_only.tzif", "table_transitions": 0},
            ],
        },
        "expected": {
            # 每个抽样本地时刻的 UTC 候选（0 = GAP，1 = OK，2 = OVERLAP）
            "candidates": [
                {"local": _sample_local_epoch(text),
                 "utc": _expected_candidates(_sample_local_epoch(text))}
                for text in SAMPLE_LOCALS
            ],
        },
    }
    S.write_json(os.path.join(root, "expect.json"), expect)


NAMES = ["fat.tzif", "slim.tzif", "tail_only.tzif", "expect.json"]

if __name__ == "__main__":
    sys.exit(S.run_generators(__file__, build, NAMES, sys.argv[1:]))
