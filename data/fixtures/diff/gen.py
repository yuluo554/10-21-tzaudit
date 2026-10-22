#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fixture · 版本差异四类判定（`plan/04` §三；M4 必覆盖的形态）。

**注入了什么**：两组"旧树 / 新树"对，每组各注入一种版本漂移形态。

| 组 | 旧树 | 新树 | 注入的形态 | 期望分类 |
|---|---|---|---|---|
| ``vancouver-tail`` | ``old/Zone/TailRule`` | ``new/Zone/TailRule`` | 表**逐字节相同**，tail 由 ``PST8PDT,M3.2.0,M11.1.0`` 变 ``MST7`` | `future_rule` + `evidence=tail` |
| ``bc-2026b`` | ``old/Zone/BcPermanent`` | ``new/Zone/BcPermanent`` | 旧树 2026 起仍有 DST，新树 2026-11 起永久 UTC−7（表内多一条 + tail 变 ``MST7``） | `future_rule` + `evidence=tail` |

外加四条**互斥 / 顺序**反证（同一组里各一个 zone）：

| zone | 注入 | 期望 |
|---|---|---|
| ``Zone/AbbrOnly`` | 表内某点之后缩写由 ``AAA`` 改 ``BBB``，offset 全同 | `abbreviation_only` + `evidence=abbr` |
| ``Zone/AbbrAndTail`` | **同时**有缩写差异**与** tail 差异 | 必须落 `future_rule`（顺序优先），**不得**落 `abbreviation_only` |
| ``Zone/Identical`` | 两树逐字节相同 | **不是变更**（不产出记录） |
| ``Zone/LinkA`` + ``Zone/LinkB`` | 旧树两份副本（互为 link），新树 LinkB 内容改成独立规则 | `Zone/LinkB` 落 `future_rule`，`Zone/LinkA` 不产出 |

**为什么需要它**（`plan/03` §六 的五条测试点必须能被独立复核）：

1. **`future_rule` 的判据锚点**是 Vancouver 这个真实形态：**表完全相同、只有 tail 变**。
   没有这条，"实现直接比整份文件字节"也能全绿——那等于没判语义。
2. **四类互斥 + 判定顺序**必须有一条"同时命中两类"的反证（`AbbrAndTail`），
   否则"顺序固定"这条口径只是文档里的一句话。
3. **零变更必须零记录**（`Identical`）——防"每个 zone 都报一条"的退化实现。
4. **alias 不得吸收规则变化**（`LinkB`）——防"两份副本就把规则差异吞掉"。

**期望值的推导方式**：**不调产品代码**。每条期望直接由"注入了什么"手写得出
（形态 → 类别是 `data/README.md` §4.3 的定义，不需要复算）；树本身用
``_support.build_tzif`` 从手写类型表与 tail 串构造。

```bash
py -3.12 data/fixtures/diff/gen.py            # 写产物
py -3.12 data/fixtures/diff/gen.py --check    # 重生成并逐字节比对
```
"""

from __future__ import print_function

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORT_DIR = os.path.dirname(HERE)
sys.path.insert(0, SUPPORT_DIR)

import _support as S  # noqa: E402

#: 表内转换点写到的年份上界（**输入常量**，不是观测值）。
#: 表内只到 1990，之后的行为全由 tail 承载 —— 这正是"表相同、只有 tail 变"的前提。
TABLE_UNTIL = 1990

#: `vancouver-tail` 的旧 / 新 tail（**逐字**取自真实 2026.1 / 2026.5 的 slim wheel）。
TAIL_OLD_VANCOUVER = "PST8PDT,M3.2.0,M11.1.0"
TAIL_NEW_VANCOUVER = "MST7"

#: `bc-2026b` 的旧 / 新 tail：旧树 2026 起继续 DST，新树 2026-11 之后永久 UTC−7。
TAIL_OLD_BC = "MST7MDT,M3.2.0,M11.1.0"
TAIL_NEW_BC = "MST7"

#: 两套 DST 规则（起跳 / 回拨的墙钟秒）
RULES_US = (("M", 3, 2, 0, 7200), ("M", 11, 1, 0, 7200))

#: 新树里"2026-11-01 之后永久 UTC−7"的那条显式转换点（本地墙钟 → epoch）。
PERMANENT_UTC = S._epoch(2026, 11, 1, 2, 0, 0)

#: `vancouver-tail`：「表**逐字节相同**」是这条 fixture 的核心约束。
#: 因此两棵树用 **同一份** 类型表 + 同一份转换点 + 同一个 slim 形态，
#: 唯一的差异只有 footer。任何"顺手改了类型表"的改动都会让这条 fixture 失去意义。
VANCOUVER_TYPES = [(-28800, False, "PST"), (-25200, True, "PDT")]

BC_TYPES = [(-25200, False, "MST"), (-21600, True, "MDT")]

ID_TYPES = [(3600, False, "AAA")]


def _table_transitions(std_offset, dst_offset, rules, until=TABLE_UNTIL):
    """1970 → ``until`` 年的表内转换点（type 0 = std / 1 = dst）。"""
    out = []
    for year in range(1970, until + 1):
        for utc, to_dst in S.year_transitions(year, std_offset, dst_offset,
                                              rules[0], rules[1]):
            out.append((utc, 1 if to_dst else 0))
    out.sort()
    return out


def _vancouver_old():
    transitions = _table_transitions(-28800, -25200, RULES_US)
    return S.build_tzif(transitions, VANCOUVER_TYPES, TAIL_OLD_VANCOUVER, slim=True)


def _vancouver_new():
    # **同一批转换点、同一份类型表**——只有 footer 不同。
    transitions = _table_transitions(-28800, -25200, RULES_US)
    return S.build_tzif(transitions, VANCOUVER_TYPES, TAIL_NEW_VANCOUVER, slim=True)


def _bc_old():
    transitions = _table_transitions(-25200, -21600, RULES_US)
    return S.build_tzif(transitions, BC_TYPES, TAIL_OLD_BC, slim=True)


def _bc_new():
    """新树：表内**额外**多一条 2026-11-01 永久 UTC−7 的转换点，tail 也变 ``MST7``。

    这条是真实 2026b 的形态（BC 通过立法放弃 DST）：转换点进表 + tail 收成常数。
    """
    transitions = _table_transitions(-25200, -21600, RULES_US)
    # 2026-11-01 02:00 本地（MDT = -21600）→ UTC；此点之后永久 std
    transitions.append((PERMANENT_UTC - 21600, 0))
    transitions.sort()
    return S.build_tzif(transitions, BC_TYPES, TAIL_NEW_BC, slim=True)


# ---------------------------------------------------------------- 互斥反证组


def _abbr_only_old():
    """``Zone/AbbrOnly`` 旧树：表内一个转换点，type 0 = ``AAA``。

    **两树都没有 tail**——否则 tail 的结构比较会先命中，这条就测不到第 3 类。
    旧树只用一个类型（``id=0``），新树用两个（``id=1`` 指向 ``BBB``），
    所以两树**字节不同**、offset 相同、缩写不同 —— 正是第 3 类的定义。
    """
    return S.build_tzif([(S._epoch(1980, 1, 15), 0)], ID_TYPES, None, slim=True)


def _abbr_only_new():
    """新树：**同一转换点、同一 offset**，只把缩写 ``AAA`` 换成 ``BBB``。"""
    return S.build_tzif([(S._epoch(1980, 1, 15), 1)],
                        [(3600, False, "AAA"), (3600, False, "BBB")], None, slim=True)


def _abbr_and_tail_old():
    """``Zone/AbbrAndTail`` 旧树：缩写 ``AAA`` + tail ``AAA-1``（东 +1h）。

    tail 串必须是**合法 POSIX TZ**（``std offset`` 两段）：M4 首版写成 ``ABT1``
    （缺偏移）→ 解析器直接 ``PosixTzError``，fixture 生成期就炸。
    """
    return S.build_tzif([(S._epoch(1980, 1, 15), 0)], ID_TYPES, "AAA-1", slim=True)


def _abbr_and_tail_new():
    """新树：**同时**改缩写（``AAA``→``BBB``）与 tail（``AAA-1``→``BBB-2``，offset 也变）。

    第 2 类（`future_rule`：tail 的 std offset 由 +3600 变 +7200）必须先命中；
    若实现把 `abbreviation_only` 提到前面，这条 fixture 立刻暴露（会落成 abbr 类）。
    """
    return S.build_tzif([(S._epoch(1980, 1, 15), 1)],
                        [(3600, False, "AAA"), (3600, False, "BBB")], "BBB-2", slim=True)


def _identical():
    """``Zone/Identical``：两树**逐字节相同**（同一份 blob，零变更）。

    tail 用 ``IDT-3`` 这个**独有**串：若与 ``LinkA`` 同字节，它会被 ``links()`` 认成
    ``LinkA`` 的别名，于是"零变更"的期望会被"link 关系变化"顶掉（M4 首版踩中）。
    """
    return S.build_tzif([(S._epoch(1980, 1, 15), 0)], ID_TYPES, "IDT-3", slim=True)


def _link_a():
    """``Zone/LinkA``：与旧树的 ``LinkB`` 逐字节相同 → 旧树里两者互为 link。"""
    return S.build_tzif([(S._epoch(1980, 1, 15), 0)], ID_TYPES, "LNK-4", slim=True)


def _link_b_old():
    """``Zone/LinkB`` 旧树：与 ``LinkA`` 逐字节相同（内容 sha256 相同 → link 判据成立）。"""
    return _link_a()


def _link_b_new():
    """``Zone/LinkB`` 新树：改成自己的规则（tail ``LBK-5``，offset 与 ``LinkA`` 不同）。

    `alias_only` **不得**吸收这条：必须落 `future_rule`。
    """
    return S.build_tzif([(S._epoch(1980, 1, 15), 0)], ID_TYPES, "LBK-5", slim=True)


def _hist_and_future_old():
    """``Zone/HistAndFuture`` 旧树：历史 offset 是 ``+7200``，tail 也是 ``CHF-1``（+3600）。

    两个断点（1970 / 1990）让两树都有表、且**共有历史**非空。
    """
    return S.build_tzif(
        [(S._epoch(1970, 1, 15), 1), (S._epoch(1990, 1, 15), 1)],
        [(3600, False, "AAA"), (7200, False, "HST")], "CHF-1", slim=True)


def _hist_and_future_new():
    """新树：历史 offset 改成 ``+3600``，**同时** tail 改成 ``CHG-2``（+7200）。

    这条 zone 让**两类判据同时成立**——是"判定顺序"唯一的真锚点：

    - 第 1 类成立：1970-01-15 起旧树 +7200、新树 +3600，且该点在两树共有历史内；
    - 第 2 类也成立：tail 规范化结构不同（``CHF-1`` vs ``CHG-2``）。

    按 ``CLASS_ORDER`` 必须落第 1 类；把 ``future_rule`` 提前则翻成第 2 类。
    （真实树里没有这种 zone：Dublin/Tehran 只有历史差异，Casablanca 只有表外差异，
    所以顺序变异拿真实数据是**恒绿**的假锚点——M4 实测踩中。）
    """
    return S.build_tzif(
        [(S._epoch(1970, 1, 15), 0), (S._epoch(1990, 1, 15), 0)],
        [(3600, False, "AAA"), (7200, False, "HST")], "CHG-2", slim=True)


#: 产物清单：``(相对路径, 内容工厂)``。路径里 ``old/`` / ``new/`` 是两棵树。
ARTIFACTS = [
    ("old/Zone/TailRule", _vancouver_old),
    ("new/Zone/TailRule", _vancouver_new),
    ("old/Zone/BcPermanent", _bc_old),
    ("new/Zone/BcPermanent", _bc_new),
    ("old/Zone/AbbrOnly", _abbr_only_old),
    ("new/Zone/AbbrOnly", _abbr_only_new),
    ("old/Zone/AbbrAndTail", _abbr_and_tail_old),
    ("new/Zone/AbbrAndTail", _abbr_and_tail_new),
    ("old/Zone/Identical", _identical),
    ("new/Zone/Identical", _identical),
    ("old/Zone/LinkA", _link_a),
    ("new/Zone/LinkA", _link_a),
    ("old/Zone/LinkB", _link_b_old),
    ("new/Zone/LinkB", _link_b_new),
    ("old/Zone/HistAndFuture", _hist_and_future_old),
    ("new/Zone/HistAndFuture", _hist_and_future_new),
]


def _expected():
    """期望的分类名单（**手写**，由"注入了什么"直接得出，不调产品代码）。

    每条给出 ``zone`` / ``class`` / ``evidence``；``note`` 写明该条的判据锚点。
    """
    return [
        {
            "zone": "Zone/TailRule",
            "class": "future_rule",
            "evidence": "tail",
            "note": "表逐字节相同，仅 tail 由 PST8PDT,M3.2.0,M11.1.0 变 MST7",
        },
        {
            "zone": "Zone/BcPermanent",
            "class": "future_rule",
            "evidence": "tail",
            "note": "表内新增 2026-11 永久 UTC-7 + tail 收成 MST7（表外行为变化）",
        },
        {
            "zone": "Zone/AbbrOnly",
            "class": "abbreviation_only",
            "evidence": "abbr",
            "note": "转换点与 offset 全同，仅缩写 AAA 变 BBB",
        },
        {
            "zone": "Zone/AbbrAndTail",
            "class": "future_rule",
            "evidence": "tail",
            "note": "缩写与 tail 同时变 → 顺序优先，必须落 future_rule 而非 abbreviation_only",
        },
        {
            "zone": "Zone/LinkB",
            "class": "future_rule",
            "evidence": "tail",
            "note": "link 变成独立规则 → alias_only 不得吸收",
        },
        {
            "zone": "Zone/LinkA",
            "class": "alias_only",
            "evidence": "link",
            "note": "旧树 LinkB 挂在 LinkA 名下（别名集合非空），新树 LinkB 独立 → 别名集合变空",
        },
        {
            "zone": "Zone/HistAndFuture",
            "class": "history_reinterpreted",
            "evidence": "table",
            "note": "两类判据同时成立（历史 offset 变 + tail 变）→ 顺序优先取 history_reinterpreted；"
                    "把 future_rule 提前则翻成 future_rule（顺序变异锚点）。"
                    "evidence=table：历史差异落在表内转换点 1970-01-15",
        },
    ]


def build(root):
    for rel, factory in ARTIFACTS:
        path = os.path.join(root, *rel.split("/"))
        S.write_bytes(path, factory())

    S.write_json(os.path.join(root, "expect.json"), {
        "fixture": "diff/change-classes",
        "why": "四类变更的判定顺序与互斥：表相同仅 tail 变必须落 future_rule；"
               "abbr 与 tail 同时变必须按顺序取 future_rule；逐字节相同不得产出记录；"
               "link 不得吸收规则变化。期望值由注入形态直接手写，不调产品代码",
        "input": {
            "old_tree": "old",
            "new_tree": "new",
            "window": None,
            "window_note": "null = 全历史（data/README.md §4.3：--window 只影响第 1 类）",
            "injected": {
                "Zone/TailRule": "表逐字节相同，仅 footer 由 %s 变 %s"
                                 % (TAIL_OLD_VANCOUVER, TAIL_NEW_VANCOUVER),
                "Zone/BcPermanent": "footer %s 变 %s + 表内新增 2026-11-01 永久 UTC-7"
                                    % (TAIL_OLD_BC, TAIL_NEW_BC),
                "Zone/AbbrOnly": "同一转换点、同一 offset，缩写 AAA 变 BBB；两树均无 tail",
                "Zone/AbbrAndTail": "缩写 AAA 变 BBB，**同时** tail AAA-1 变 BBB-2（offset 变）",
                "Zone/Identical": "两树逐字节相同 → 零变更（不得产出记录）",
                "Zone/LinkA": "两树逐字节相同，且与旧树 LinkB 相同；"
                              "新树里 LinkB 独立 → LinkA 的别名集合变空",
                "Zone/LinkB": "旧树与 LinkA 逐字节相同（link 判据成立）；新树改成独立规则",
                "Zone/HistAndFuture": "历史 offset 7200→3600，**同时** tail CHF-1→CHG-2；"
                                      "两类判据同时成立，顺序必须取 history_reinterpreted",
            },
        },
        "expected": {
            "changes": _expected(),
            "not_changes": ["Zone/Identical"],
            "class_order": ["history_reinterpreted", "future_rule",
                            "abbreviation_only", "alias_only"],
        },
    })


NAMES = ["expect.json"] + [rel for rel, _ in ARTIFACTS]

if __name__ == "__main__":
    sys.exit(S.run_generators(__file__, build, NAMES, sys.argv[1:]))
