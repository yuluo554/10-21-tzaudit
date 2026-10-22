#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fixture · BC 场景（同一 UTC 两版本两墙钟）—— `plan/04` §三；M5 必覆盖的形态。

**注入了什么**：一个 zone（``Zone/Bc``）的两棵树，模拟"官方放弃 DST、永久停在夏令时"
的省级立法（Cal.com #30104 的事故形态）：

| | 旧树 ``old/``（版本标签 2026a） | 新树 ``new/``（版本标签 2026b） |
|---|---|---|
| 表内历史 | 1970 → 2025-11 的完整季节转换（PST/PDT） | 1970 → **2025-03**（最后一个转换点是"起跳"，此后再不回拨） |
| tail | ``PST8PDT,M3.2.0,M11.1.0`` | ``MST7``（东 −7 永久，即"停在夏令时"） |
| 表尾自洽 | 表尾 PST(−8) 与 tail 的 std(−8) 一致 | 表尾 PDT(−7) 与 tail 的 −7 一致 |

两棵树**各自自洽**（表尾偏移与 tail 在该点的偏移一致），差异只有"未来是否回拨"
——这是 `plan/04` 的反例纪律：树不自洽时造出来的"窗口"是假的。

**为什么需要它**：`plan/03` §七 的五条测试点里有两条必须靠它：

1. ``VERSION_CHANGED`` 的判据 = **同一本地墙钟在两棵树下的 UTC 不同**。
   本 fixture 的 ``bc-version-changed`` 行（2026-12-15 12:00）在旧树下是
   12:00−(−8h)=**20:00Z**，在新树下是 12:00−(−7h)=**19:00Z** —— 正是"相差一小时"。
   换成"同一 UTC"视角：19:00Z 在旧树下是 **11:00**、在新树下是 **12:00**，
   这就是 Cal.com 事故里"同一时刻在两个版本的墙钟不一样"的复现口径。
2. **判定顺序**必须能被咬住：``bc-gap`` 行（2026-03-08 02:30）在旧树是 GAP
   （起跳跳掉了一小时）、在新树**存在**（新树没有起跳）。按
   ``INVALID → GAP → OVERLAP → VERSION_CHANGED → OK`` 必须报 **GAP**；
   把 ``VERSION_CHANGED`` 提前就会翻成 ``VERSION_CHANGED``（顺序变异锚点）。
   ``bc-overlap`` 同理：旧树 2 个候选、新树 1 个 → 必须报 **OVERLAP**。

**期望值的推导方式**：**不调产品代码**。每条期望由"注入了什么"直接算出
（偏移是输入常量：旧树冬 −8 / 夏 −7，新树恒 −7；UTC = 墙钟 − 偏移），
时间用 ``_support._epoch`` 做纯日历换算。

```bash
py -3.12 data/fixtures/audit/bc-scenario/gen.py            # 写产物
py -3.12 data/fixtures/audit/bc-scenario/gen.py --check    # 重生成并逐字节比对
```
"""

from __future__ import print_function

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
#: ``_support.py`` 在 ``data/fixtures/``——本文件在 ``data/fixtures/audit/bc-scenario/``，
#: 所以是**上两级**（`plan/04` §三 定的是 ``fixtures/<类>/<形态>/`` 两级目录）。
SUPPORT_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, SUPPORT_DIR)

import _support as S  # noqa: E402

#: zone 名（**刻意不用真实 zone 名**：真实树里没有这种"永久夏令时"的 zone）
ZONE = "Zone/Bc"

#: 旧树的版本标签（`--version` 的 A 侧；只用于报告头，不影响判定）
VERSION_OLD = "2026a"
#: 新树的版本标签（B 侧）
VERSION_NEW = "2026b"

#: 表内历史写到哪一年为止（**输入常量**）
TABLE_UNTIL_OLD = 2025     # 旧树：2025 年 11 月仍回拨 → 表尾 PST
TABLE_UNTIL_NEW = 2025     # 新树：2025 年 3 月最后一次起跳 → 表尾 PDT

#: 两套 tail（POSIX TZ 串；旧树继续季节性，新树永久 −7）
TAIL_OLD = "PST8PDT,M3.2.0,M11.1.0"
TAIL_NEW = "MST7"

#: 偏移（**东为正**的秒；与 POSIX 的西为正相反 —— K8 的落点在这里只作注释）
OFFSET_PST = -28800    # 旧树冬季 −8h
OFFSET_PDT = -25200    # 旧树夏季 −7h / 新树恒定 −7h

#: 类型表：0 = 标准时，1 = 夏令时
TYPES = [(OFFSET_PST, False, "PST"), (OFFSET_PDT, True, "PDT")]

#: 美加现行 DST 规则（起跳 / 回拨的**墙钟**秒：3 月第 2 个周日 02:00、11 月第 1 个周日 02:00）
RULE_START = ("M", 3, 2, 0, 7200)
RULE_END = ("M", 11, 1, 0, 7200)


def _seasonal_transitions(std_offset, dst_offset, from_year=1970, until_year=TABLE_UNTIL_OLD):
    """``from_year`` → ``until_year`` 的完整季节转换 ``[(utc, type_index)]``（升序）。

    起跳按标准时墙钟、回拨按 DST 墙钟解释（tzcode 语义）。
    """
    out = []
    for year in range(from_year, until_year + 1):
        for utc, to_dst in S.year_transitions(year, std_offset, dst_offset,
                                              RULE_START, RULE_END):
            out.append((utc, 1 if to_dst else 0))
    out.sort()
    return out


def _old_tree():
    """旧树：完整季节性历史 + ``PST8PDT`` tail（2026 年后继续夏令时）。

    表尾（2025-11 回拨）落在 PST(−8)，与 tail 的 std(−8) **一致** —— 树自洽。
    """
    return S.build_tzif(_seasonal_transitions(OFFSET_PST, OFFSET_PDT),
                        TYPES, TAIL_OLD, slim=True)


def _new_tree():
    """新树：历史同旧树，但**停在 2025 年 3 月的起跳**，此后再不回拨。

    表尾（2025-03 起跳）落在 PDT(−7)，与 tail ``MST7``（−7）**一致** —— 树自洽。
    这条树的语义就是 BC 立法后的形态："永久夏令时"。
    """
    transitions = [item for item in _seasonal_transitions(OFFSET_PST, OFFSET_PDT,
                                                          until_year=TABLE_UNTIL_NEW)
                   if S.year_of_epoch(item[0]) < 2025 or item[1] == 1]
    return S.build_tzif(transitions, TYPES, TAIL_NEW, slim=True)


#: 产物清单：``(相对路径, 内容工厂)``
ARTIFACTS = [
    ("old/" + ZONE, _old_tree),
    ("new/" + ZONE, _new_tree),
]

#: 清单（**输入**）。列序 ``id,local_time``；顺序即期望的输出行序。
TIMES = [
    ("bc-ok-summer", "2026-07-15 12:00"),
    ("bc-version-changed", "2026-12-15 12:00"),
    ("bc-gap", "2026-03-08 02:30"),
    ("bc-overlap", "2026-11-01 01:30"),
]


def _utc(month, day, hour, minute, offset):
    """墙钟 → UTC epoch（``墙钟 − 偏移``；纯日历换算，不调产品代码）。"""
    return S._epoch(2026, month, day, hour, minute, 0) - offset


def _expected_rows():
    """期望的逐条判定 —— 由"注入了什么"直接写出（不调产品代码）。

    ``utc_candidates`` 是**主树（旧树）**的候选；``versions`` 写明两侧候选，
    供"同一 UTC 两墙钟"那条断言核对。
    """
    return [
        {
            "id": "bc-ok-summer",
            "status": "OK",
            "why": "2026-07 两树都在夏令时 −7 → 12:00 都是 19:00Z",
            "utc_candidates": [_utc(7, 15, 12, 0, OFFSET_PDT)],
            "versions": {
                VERSION_OLD: [_utc(7, 15, 12, 0, OFFSET_PDT)],
                VERSION_NEW: [_utc(7, 15, 12, 0, OFFSET_PDT)],
            },
        },
        {
            "id": "bc-version-changed",
            "status": "VERSION_CHANGED",
            "why": "2026-12 旧树已回拨到 −8 → 20:00Z；新树仍 −7 → 19:00Z（相差一小时）",
            "utc_candidates": [_utc(12, 15, 12, 0, OFFSET_PST)],
            "versions": {
                VERSION_OLD: [_utc(12, 15, 12, 0, OFFSET_PST)],
                VERSION_NEW: [_utc(12, 15, 12, 0, OFFSET_PDT)],
            },
        },
        {
            "id": "bc-gap",
            "status": "GAP",
            "why": "2026-03-08 02:30 只在旧树不存在（起跳）；新树无起跳 → "
                   "按顺序必须报 GAP，不得被 VERSION_CHANGED 抢先",
            "utc_candidates": [],
            "versions": {
                VERSION_OLD: [],
                VERSION_NEW: [_utc(3, 8, 2, 30, OFFSET_PDT)],
            },
        },
        {
            "id": "bc-overlap",
            "status": "OVERLAP",
            "why": "2026-11-01 01:30 在旧树出现两次（−7 与 −8）；新树只有一次 → "
                   "按顺序必须报 OVERLAP",
            "utc_candidates": [_utc(11, 1, 1, 30, OFFSET_PDT), _utc(11, 1, 1, 30, OFFSET_PST)],
            "versions": {
                VERSION_OLD: [_utc(11, 1, 1, 30, OFFSET_PDT), _utc(11, 1, 1, 30, OFFSET_PST)],
                VERSION_NEW: [_utc(11, 1, 1, 30, OFFSET_PDT)],
            },
        },
    ]


def _provenance(version):
    """树的 provenance（``audit --version`` 要求每棵树都带它，Q4）。"""
    return {
        "version": version,
        "kind": "slim",
        "zones": 1,
        "source": "synthetic fixture（data/fixtures/audit/bc-scenario/gen.py 生成，非上游下载）",
    }


def build(root):
    for rel, factory in ARTIFACTS:
        S.write_bytes(os.path.join(root, *rel.split("/")), factory())

    for side, version in (("old", VERSION_OLD), ("new", VERSION_NEW)):
        S.write_json(os.path.join(root, side, "provenance.json"), _provenance(version))

    S.write_bytes(os.path.join(root, "times.txt"),
                  "".join("%s,%s\n" % (id_, local) for id_, local in TIMES).encode("ascii"))

    S.write_json(os.path.join(root, "expect.json"), {
        "fixture": "audit/bc-scenario",
        "why": "同一本地墙钟在两版本下映射到不同 UTC（BC 永久夏令时立法）；"
               "同时用两条行锚住判定顺序（旧树 GAP / OVERLAP 必须先于 VERSION_CHANGED）。"
               "期望值由注入的偏移常量手写，不调产品代码",
        "input": {
            "zone": ZONE,
            "times": "times.txt",
            "trees": {"A": "old", "B": "new"},
            "versions": {"A": VERSION_OLD, "B": VERSION_NEW},
            "injected": {
                "old": "完整季节历史 + tail %s（表尾 PST −8，与 tail std 一致）" % TAIL_OLD,
                "new": "历史到 2025-03 最后一次起跳为止 + tail %s（表尾 PDT −7，自洽）" % TAIL_NEW,
                "same_utc_two_wall_clocks": (
                    "19:00Z 在 %s 下是 11:00 墙钟（PST −8），在 %s 下是 12:00 墙钟（−7）"
                    % (VERSION_OLD, VERSION_NEW)),
            },
        },
        "expected": {
            "status_order": ["INVALID", "GAP", "OVERLAP", "VERSION_CHANGED", "OK"],
            "rows": _expected_rows(),
        },
    })

    # **第一层断言在写盘之后立刻跑**：`--check` 的重生成目录也走这条路，
    # 所以"生成器被改坏"与"两次坏成一样"都会被抓住（`plan/04` §三 第 2 条）。
    problems = _self_check(root)
    if problems:
        raise RuntimeError("fixture self-check FAIL（%d 处）:\n  %s"
                           % (len(problems), "\n  ".join(problems)))


NAMES = (["times.txt", "expect.json", "old/provenance.json", "new/provenance.json"]
         + [rel for rel, _ in ARTIFACTS])


def _self_check(root):
    """**第一层断言**：产物自身形态正确（``plan/04`` §三 第 2 条）。

    只做"重生成 → 逐字节比对"会漏掉"生成器被改坏但两次坏成一样"的情形，
    所以这里再查三件事：TZif 魔数、provenance 必备键、期望覆盖四种状态。
    """
    problems = []
    for rel, _factory in ARTIFACTS:
        path = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(path):
            problems.append("缺件: %s" % rel)
            continue
        with open(path, "rb") as fh:
            if fh.read(4) != b"TZif":
                problems.append("不是 TZif（缺魔数）: %s" % rel)
    for side in ("old", "new"):
        path = os.path.join(root, side, "provenance.json")
        if not os.path.isfile(path):
            problems.append("缺件: %s/provenance.json" % side)
            continue
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        for key in ("version", "kind"):
            if not doc.get(key):
                problems.append("%s/provenance.json 缺 %s" % (side, key))
    statuses = set(row["status"] for row in _expected_rows())
    if statuses != {"OK", "VERSION_CHANGED", "GAP", "OVERLAP"}:
        problems.append("期望未覆盖四类状态: %s" % sorted(statuses))
    return problems


if __name__ == "__main__":
    sys.exit(S.run_generators(__file__, build, NAMES, sys.argv[1:]))
