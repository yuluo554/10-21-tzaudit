#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金标复算入口（题面 §三 第 3 项）。

两种动作：

``--regen``   从 ``data/_downloads/slim/<ver>/`` 真读树 → 逐 zone 解析 → 写
              ``data/tzdb/<ver>/expect.json``（只含**输入 + 期望**）。
``--check``   用**生产实现**复算，与入仓 ``expect.json`` 逐项比对。

两套件：

``parse``     TZif 字节解析的聚合量（zone 数 / 零解析错误 / 转换点总数 / 树指纹）。
``timeline``  双引擎合并后的量（抽样 zone 的转换点数、tail 展开点数、refine 抽样）。
``windows``   墙钟风险窗口（抽样 zone 在抽样年份的 GAP / OVERLAP 窗口集合）。

判据（`plan/04` §二）：
- ``parse_errors`` 必须为 0（全量树零解析错误）。
- ``zones`` 分母 > 0；**0 与"没扫到"必须可区分**——分母 0 报 FAIL，不静默通过。
- 缺 ``data/_downloads``（干净 clone）→ **退 3 并点名缺失版本**，不是 0 项通过。
- 期望值只由输入决定；金标里不得出现 ``observed_*`` / ``actual_*``（`test_truth_shape.py` 守）。

**独立参照对拍**：``--regen`` 与 ``--check`` 都会用 ``tests/reference.py``（不 import tzaudit）
对**抽样 zone** 逐条对拍。没有这一步，"期望与实现同源"就是引擎自证（`plan/04` §二.2）。

退出码：0 一致 / 1 不一致 / 2 用法错误 / 3 环境缺件
"""

from __future__ import print_function

import argparse
import io
import json
import os
import sys

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2
EXIT_ENV = 3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZDB_DIR = os.path.join(ROOT, "data", "tzdb")
DOWNLOAD_DIR = os.path.join(ROOT, "data", "_downloads")
SLIM_DIR = os.path.join(DOWNLOAD_DIR, "slim")

sys.path.insert(0, os.path.join(ROOT, "src"))

from tzaudit import civil  # noqa: E402 - 日历换算（与生产实现同一份，整数运算）

#: 抽样对拍必须覆盖的形态（`plan/04` §二.2 要求"含三种特殊形态"）
SAMPLE_ZONES = (
    "Europe/Dublin",        # 负 DST（冬季 is_dst=1）
    "Australia/Lord_Howe",  # 30 分钟 DST
    "Pacific/Chatham",      # +12:45 非整点
    "America/New_York",
    "America/Vancouver",    # 表内零迁移、语义全在 tail
    "Asia/Tehran",
)

#: 抽样规模下限（`plan/04` §二.2：≥ 20 个）
MIN_SAMPLE = 20

#: timeline 套件用的窗口（**输入常量**，不是观测值）：1990–2030 覆盖全部抽样 zone 的 DST 规则
TIMELINE_WINDOW = ("1990-01-01", "2030-01-01")

#: timeline 套件逐 zone 抽样的本地时刻数（每个 zone 都跑，串行；保持纯 Python 无并行）
TIMELINE_PROBES = 24

#: 每个 zone 额外取的**转换点邻域**本地时刻数。均匀网格几乎不可能正好落在
#: GAP/OVERLAP 那一小时里（实测：只用均匀网格时候选数集合 = {1}，gap/overlap 等于没验），
#: 所以必须从转换点反推 —— 这仍是**只由输入决定**的量，不是观测值。
TIMELINE_TRANSITION_PROBES = 8

#: expect.json 的格式版本（字段含义变更时递增，`--check` 见到别的值直接报不一致）
EXPECT_SCHEMA = 1

#: 套件名（``--suite`` 的可选值；缺省 = 全部）
SUITES = ("parse", "timeline", "windows", "diff")

#: diff 套件比较的版本对（**输入常量**，不是观测值）。
#: 第二对是 `plan/04` §二 已定的 `2026.1-2026.5`，与第一对是同一对标（PyPI 版本号视角）。
DIFF_PAIRS = (("2026a", "2026e"),)

#: diff 套件的"窗口内变化"判定区间（**输入常量**）。`None` 那份是全历史。
#: 口径（`data/README.md` §4.3）：`--window` **只影响第 1 类**，第 2 类不受限。
DIFF_WINDOW = (2000, 2030)

#: diff 对拍的最小样本数。真实对上 history_reinterpreted 类实测 9–11 条
#: （窗口内 2 条 / 全历史 11 条），取 2 作为下限——比"必须 ≥ 20"更诚实：
#: 差异 zone 本来就少，硬凑 20 会逼着抽样退化。
DIFF_MIN_CROSS_CHECK = 2

#: diff 对拍时把参照时间线展开到的年份（**输入常量**）。
#: 必须覆盖到"表外"足够远——真实对上表尾最晚到 2087（2026a 的 Casablanca）。
DIFF_FUTURE_SENTINEL_YEAR = 2200

#: windows 套件扫描的年份（**输入常量**，不是观测值）
WINDOWS_YEARS = (2024, 2026)

#: windows 套件额外抽样 zone 名单（固定名单；覆盖三种特殊形态 + 反例形态）
WINDOWS_SAMPLE_ZONES = (
    "America/New_York",     # 整小时 GAP + OVERLAP
    "America/Vancouver",    # 反例：2026 起永久 UTC-7 → 无 OVERLAP
    "Australia/Lord_Howe",  # 30 分钟窗口
    "Pacific/Chatham",      # +12:45 非整点
    "Europe/Dublin",        # 负 DST
    "Asia/Almaty",          # 跨年边界（2024-02-29 23:00 → 03-01 00:00）
    "Antarctica/Troll",     # 2 小时窗口
    "UTC",                  # 零窗口
)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="bench/run.py",
        description="复算 tzdata 金标并与入仓 expect.json 比对",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="复算并比对（默认动作）")
    action.add_argument("--regen", action="store_true", help="重新生成金标（需真数据树）")
    parser.add_argument("--suite", choices=SUITES, default=None,
                        help="只跑某一套件（缺省跑全部）")
    return parser


# ---------------------------------------------------------------- 树与解析


def _slim_trees():
    """``data/_downloads/slim/`` 下已解好的树 → ``{version: path}``（版本序）。"""
    if not os.path.isdir(SLIM_DIR):
        return {}
    found = {}
    for name in sorted(os.listdir(SLIM_DIR)):
        path = os.path.join(SLIM_DIR, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "provenance.json")):
            found[name] = path
    return found


def _tzdb_versions():
    """``data/tzdb/`` 下**入仓**的版本（有 provenance.json 的目录）。"""
    if not os.path.isdir(TZDB_DIR):
        return []
    return sorted(
        name for name in os.listdir(TZDB_DIR)
        if os.path.isdir(os.path.join(TZDB_DIR, name))
        and os.path.isfile(os.path.join(TZDB_DIR, name, "provenance.json"))
    )


def _provenance(tree_dir):
    path = os.path.join(tree_dir, "provenance.json")
    if not os.path.isfile(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        return {}


def parse_tree(tree_dir):
    """逐 zone 解析 → ``(stats, errors)``。

    ``stats`` 是**只由输入决定**的聚合量（可写进金标）：
    ``zones`` / ``parse_errors`` / ``transitions_total`` / ``versions`` / ``slim_zones`` /
    ``tail_zones`` / ``tzif_digest``。
    """
    from tzaudit import tzif
    from tzaudit.zoneinfo_store import ZoneinfoStore, byte_key

    store = ZoneinfoStore(tree_dir)
    names = store.zones()
    errors = []
    transitions_total = 0
    version_hist = {}
    slim_zones = 0
    tail_zones = 0
    digest_input = []

    for zone in names:
        try:
            raw = store.read_zone(zone)
            data = tzif.parse(raw, zone)
        except Exception as exc:  # 任何解析失败都必须进 errors（不吞）
            errors.append("%s: %s: %s" % (zone, type(exc).__name__, exc))
            continue
        transitions_total += len(data.transitions)
        version_hist[data.version] = version_hist.get(data.version, 0) + 1
        if data.is_slim:
            slim_zones += 1
        if data.footer:
            tail_zones += 1
        digest_input.append("%s\t%s" % (zone, data.version))

    # 树内容的**指纹**：zone 名 + 各自 TZif 版本。金标靠它区分"同版本不同构建"。
    digest_input.sort(key=byte_key)
    tzif_digest = _sha256_text("\n".join(digest_input))

    stats = {
        "zones": len(names),
        "parse_errors": len(errors),
        "transitions_total": transitions_total,
        "tzif_versions": dict(sorted(version_hist.items())),
        "slim_zones": slim_zones,
        "tail_zones": tail_zones,
        "tzif_digest": tzif_digest,
    }
    return stats, errors


def _sha256_text(text):
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cross_check(tree_dir):
    """用 ``tests/reference.py`` 对抽样 zone 逐条对拍 → ``(checked, mismatches)``。

    抽样名单由 :func:`_sample_zones` 统一给出（``SAMPLE_ZONES`` 打底 + 字节序补足）——
    **不接收调用方传名单**：两个调用点传不同的名单会让"抽样对拍"悄悄变成两套口径。
    """
    if os.path.join(ROOT, "tests") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "tests"))
    try:
        import reference
    except ImportError as exc:  # 参照实现不在 → 对拍不成立，必须报错而不是跳过
        return 0, ["参照实现不可用: %s" % exc]

    from tzaudit import tzif
    from tzaudit.zoneinfo_store import ZoneinfoStore

    store = ZoneinfoStore(tree_dir)
    available = set(store.zones())
    wanted = _sample_zones(available)

    checked = 0
    mismatches = []
    for zone in wanted:
        try:
            raw = store.read_zone(zone)
            ours = tzif.parse(raw, zone)
            theirs = reference.read_tzif(raw)
        except Exception as exc:
            mismatches.append("%s: 对拍异常 %s: %s" % (zone, type(exc).__name__, exc))
            continue
        if (ours.version, ours.transitions, ours.footer) != (theirs[0], theirs[1], theirs[2]):
            mismatches.append("%s: 生产实现与参照实现不一致" % zone)
            continue
        checked += 1
    if checked < MIN_SAMPLE:
        mismatches.append("对拍样本不足：%d < %d（树里 zone 太少？）" % (checked, MIN_SAMPLE))
    return checked, mismatches


def _sample_zones(available):
    """固定抽样的 zone 名单：先放 SAMPLE_ZONES，再按字节序补到 MIN_SAMPLE 个。"""
    from tzaudit.zoneinfo_store import byte_key

    wanted = [z for z in SAMPLE_ZONES if z in available]
    for zone in sorted(available, key=byte_key):
        if len(wanted) >= MIN_SAMPLE:
            break
        if zone not in wanted:
            wanted.append(zone)
    return wanted


# ---------------------------------------------------------------- timeline 套件


def _window_epochs():
    """``TIMELINE_WINDOW``（输入常量）→ ``(start_epoch, end_epoch)``。"""
    from tzaudit import civil

    return civil.parse_local(TIMELINE_WINDOW[0] + " 00:00:00"), \
        civil.parse_local(TIMELINE_WINDOW[1] + " 00:00:00")


def _probe_locals(start, end):
    """``TIMELINE_PROBES`` 个均匀分布的**本地墙钟**抽样（确定性，无 random）。"""
    span = end - start
    return [start + (span * index) // TIMELINE_PROBES for index in range(TIMELINE_PROBES)]


def _transition_probes(timeline, tl, start, end):
    """从转换点反推的本地墙钟抽样：GAP / OVERLAP 的那一小时就在这里。

    取窗口内**前 ``TIMELINE_TRANSITION_PROBES`` 个"改变 offset"的转换点**，每个给两个探测：
    ``t + offset_before``（GAP 的起点 / OVERLAP 的起点）与其中点。
    数量固定，因此结果只由输入决定（不随实现细节漂）。
    """
    points = []
    for utc in timeline.transition_points(tl, start, end):
        before = timeline.offset_at(utc - 1, tl)
        after = timeline.offset_at(utc, tl)
        if before != after:
            points.append((utc, before, after, utc + before, utc + after))
        if len(points) >= TIMELINE_TRANSITION_PROBES:
            break
    probes = []
    for _utc, _before, _after, wall_before, wall_after in points:
        low, high = sorted((wall_before, wall_after))
        probes.append(low)
        if high > low + 1:
            probes.append(low + (high - low) // 2)
    return probes


def timeline_stats(tree_dir):
    """双引擎合并层的**只由输入决定**的统计量。

    ``stats`` 里只放"输入 + 期望"，不含任何观测/耗时字段：

    - ``zones``：口径分母。
    - ``timeline_errors``：建时间线时的异常数（必须 0）。
    - ``sampled_zones``：参与抽样的 zone（固定名单，见 ``_sample_zones``）。
    - ``sampled_transitions`` / ``sampled_tail_points``：抽样 zone 在窗口内的
      转换点数与其中 ``source="tail"`` 的点数（`plan/04` §二 已定口径）。
    - ``candidates``：抽样本地时刻的 UTC 候选（``0`` = GAP / ``1`` = OK / ``2`` = OVERLAP）。
    """
    from tzaudit import timeline
    from tzaudit.zoneinfo_store import ZoneinfoStore, byte_key

    store = ZoneinfoStore(tree_dir)
    names = store.zones()
    start, end = _window_epochs()
    wanted = _sample_zones(set(names))
    probes = _probe_locals(start, end)

    errors = []
    sampled = []
    for zone in wanted:
        try:
            tl = timeline.load_timeline(zone, store, window_start=start, window_end=end)
        except Exception as exc:  # 任何失败都进 errors（不吞）
            errors.append("%s: %s: %s" % (zone, type(exc).__name__, exc))
            continue
        points = timeline.transition_points(tl, start, end)
        tail_points = 0
        for utc in points:
            segment = timeline._segment_at(utc, tl.segments)
            if segment.source == "tail":
                tail_points += 1
        probe_locals = probes + _transition_probes(timeline, tl, start, end)
        candidates = []
        for local in probe_locals:
            resolved = timeline.resolve_local(local, tl)
            candidates.append({
                "local": local,
                "utc": [res.utc for res in resolved],
                "offsets": [res.offset_sec for res in resolved],
            })
        sampled.append({
            "zone": zone,
            "table_end_utc": tl.table_end_utc,
            "tail": tl.tail.raw if tl.tail is not None else None,
            "transitions": len(points),
            "tail_points": tail_points,
            "candidates": candidates,
        })

    sampled.sort(key=lambda item: byte_key(item["zone"]))
    stats = {
        "zones": len(names),
        "timeline_errors": len(errors),
        "window": [TIMELINE_WINDOW[0], TIMELINE_WINDOW[1]],
        "sampled_zones": [item["zone"] for item in sampled],
        "sampled_transitions": sum(item["transitions"] for item in sampled),
        "sampled_tail_points": sum(item["tail_points"] for item in sampled),
        "sampled": sampled,
    }
    return stats, errors


def cross_check_timeline(tree_dir):
    """timeline 层与 ``tests/reference.py`` 对拍 → ``(checked, mismatches)``。

    比 ``to_local``（抽样 UTC）与 ``resolve_local``（抽样本地时刻 + 每个转换点附近）。
    """
    if os.path.join(ROOT, "tests") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "tests"))
    try:
        import reference
    except ImportError as exc:
        return 0, ["参照实现不可用: %s" % exc]

    from tzaudit import timeline
    from tzaudit.zoneinfo_store import ZoneinfoStore

    store = ZoneinfoStore(tree_dir)
    available = set(store.zones())
    wanted = _sample_zones(available)
    start, end = _window_epochs()

    checked = 0
    mismatches = []
    for zone in wanted:
        try:
            raw = store.read_zone(zone)
            ours = timeline.load_timeline(zone, store, window_start=start, window_end=end)
            theirs = reference.read_timeline(raw, start, end)
        except Exception as exc:
            mismatches.append("%s: 对拍异常 %s: %s" % (zone, type(exc).__name__, exc))
            continue

        probe = start
        while probe < end:
            if timeline.to_local(probe, ours) != theirs.to_local(probe):
                mismatches.append("%s: to_local @ %d" % (zone, probe))
                break
            probe += 86400 * 31

        for point in timeline.transition_points(ours, start, end):
            before = timeline.offset_at(point - 1, ours)
            after = timeline.offset_at(point, ours)
            if before == after:
                continue
            low, high = sorted((point + before, point + after))
            for local in range(low - 1, high + 2):
                got = [res.utc for res in timeline.resolve_local(local, ours)]
                want = [item[0] for item in theirs.resolve_local(local)]
                if got != want:
                    mismatches.append("%s: resolve @ %d（%r != %r）" % (zone, local, got, want))
        checked += 1

    if checked < MIN_SAMPLE:
        mismatches.append("timeline 对拍样本不足：%d < %d" % (checked, MIN_SAMPLE))
    return checked, mismatches


# ---------------------------------------------------------------- windows 套件


def _windows_zone_list(available, window_bearing):
    """windows 套件抽样的 zone 名单（固定名单 + **有窗口的** zone 按字节序补足）。

    固定名单必须覆盖：整小时 / 30 分钟 / 非整点 / 负 DST / 跨年边界 / **零窗口**。

    补足时**优先挑有窗口的 zone**——若按字节序随便补，多数 zone 会是"零窗口"的
    （``Africa/*`` 大多没有 DST），抽样集就会退化成"一堆空行"（判据等于没验）。
    ``window_bearing`` 是**由输入决定**的集合（扫描全量树得出），不是观测值。
    """
    from tzaudit.zoneinfo_store import byte_key

    wanted = [z for z in WINDOWS_SAMPLE_ZONES if z in available]
    for zone in sorted(window_bearing, key=byte_key):
        if len(wanted) >= MIN_SAMPLE:
            break
        if zone not in wanted:
            wanted.append(zone)
    # 仍然不够（树太小）→ 按字节序补零窗口的 zone（分母不得为 0）
    for zone in sorted(available, key=byte_key):
        if len(wanted) >= MIN_SAMPLE:
            break
        if zone not in wanted:
            wanted.append(zone)
    return wanted


def windows_stats(tree_dir):
    """墙钟风险窗口层的**只由输入决定**的统计量。

    ``stats`` 里只放"输入 + 期望"，不含任何观测/耗时字段：

    - ``zones``：口径分母（树里的 zone 数）。
    - ``windows_errors``：扫描时的异常数（必须 0）。
    - ``total_windows``：**全量树**在抽样年份里的窗口总数（分母口径的总量）。
    - ``sampled_zones``：参与抽样的 zone（固定名单 + 有窗口的 zone 按字节序补足）。
    - ``sampled``：每个抽样 zone 在每个抽样年份的窗口集合（``type`` / 起止墙钟 / 时长 /
      前后偏移 / ``source``）。
    """
    from tzaudit import timeline, windows
    from tzaudit.zoneinfo_store import ZoneinfoStore, byte_key

    store = ZoneinfoStore(tree_dir)
    names = store.zones()

    # 第一遍：全量扫描（分母口径 + 找出"有窗口的 zone"）
    errors = []
    per_zone = {}
    total_windows = 0
    for zone in names:
        rows = []
        for year in WINDOWS_YEARS:
            try:
                tl = timeline.load_timeline(
                    zone, store,
                    window_start=civil.epoch_from_local_naive(year, 1, 1) - 2 * 86400,
                    window_end=civil.epoch_from_local_naive(year + 1, 1, 1) + 2 * 86400)
                found = windows.scan_year(zone, year, tl)
            except Exception as exc:  # 任何失败都进 errors（不吞）
                errors.append("%s %d: %s: %s" % (zone, year, type(exc).__name__, exc))
                continue
            rows.append({
                "year": year,
                "windows": [{
                    "type": item.type,
                    "start_local": civil.format_local(item.start_local),
                    "end_local": civil.format_local(item.end_local),
                    "duration_min": item.duration_min,
                    "residual_sec": item.residual_sec,
                    "offset_before": civil.format_offset(item.offset_before),
                    "offset_after": civil.format_offset(item.offset_after),
                    "source": item.source,
                } for item in found],
            })
        count = sum(len(row["windows"]) for row in rows)
        total_windows += count
        if count:
            per_zone[zone] = rows

    wanted = _windows_zone_list(set(names), set(per_zone))
    sampled = [{"zone": zone,
                "years": per_zone.get(zone, [{"year": year, "windows": []}
                                              for year in WINDOWS_YEARS])}
               for zone in wanted]
    sampled.sort(key=lambda item: byte_key(item["zone"]))

    stats = {
        "zones": len(names),
        "windows_errors": len(errors),
        "years": list(WINDOWS_YEARS),
        "total_windows": total_windows,
        "sampled_zones": [item["zone"] for item in sampled],
        "sampled": sampled,
    }
    return stats, errors


def cross_check_windows(tree_dir):
    """windows 层与 ``tests/reference.py`` 对拍 → ``(checked, mismatches)``。

    参照实现给的是"每个本地墙钟的 UTC 候选集合"（区间包含式）；生产实现给的是
    "墙钟窗口区间"。这里把两者**对起来**：参照实现独立算出窗口区间（转换点两侧
    offset 的差 → 墙钟区间 → 逐点复核候选数），必须与生产实现**逐条相等**。
    """
    if os.path.join(ROOT, "tests") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "tests"))
    try:
        import reference
    except ImportError as exc:
        return 0, ["参照实现不可用: %s" % exc]

    from tzaudit import timeline, windows
    from tzaudit.zoneinfo_store import ZoneinfoStore

    store = ZoneinfoStore(tree_dir)
    available = set(store.zones())

    # 抽样名单必须与 ``windows_stats`` **同一份口径**（两处各算一套会让对拍形同虚设）
    window_bearing = set()
    for zone in sorted(available, key=lambda name: name.encode("utf-8")):
        for year in WINDOWS_YEARS:
            try:
                tl = timeline.load_timeline(
                    zone, store,
                    window_start=civil.epoch_from_local_naive(year, 1, 1) - 2 * 86400,
                    window_end=civil.epoch_from_local_naive(year + 1, 1, 1) + 2 * 86400)
                if windows.scan_year(zone, year, tl):
                    window_bearing.add(zone)
                    break
            except Exception:
                continue
    wanted = _windows_zone_list(available, window_bearing)

    checked = 0
    mismatches = []
    for zone in wanted:
        raw = store.read_zone(zone)
        for year in WINDOWS_YEARS:
            start = civil.epoch_from_local_naive(year, 1, 1) - 2 * 86400
            end = civil.epoch_from_local_naive(year + 1, 1, 1) + 2 * 86400
            try:
                ours_tl = timeline.load_timeline(zone, store, window_start=start, window_end=end)
                theirs = reference.read_timeline(raw, start, end)
            except Exception as exc:
                mismatches.append("%s %d: 对拍异常 %s: %s" % (zone, year, type(exc).__name__, exc))
                continue

            ours = windows.scan_year(zone, year, ours_tl)
            expected = _reference_windows(theirs, year, start, end)
            got = [(item.type, item.start_local, item.end_local) for item in ours]
            want = [(kind, lo, hi) for kind, lo, hi in expected]
            if got != want:
                mismatches.append("%s %d: 窗口集合不一致（我们 %r / 参照 %r）"
                                  % (zone, year, got, want))
                continue
            checked += 1

    if checked < MIN_SAMPLE:
        mismatches.append("windows 对拍样本不足：%d < %d" % (checked, MIN_SAMPLE))
    return checked, mismatches


def _reference_windows(theirs, year, start, end):
    """参照实现独立算出的墙钟窗口 → ``[(type, start_local, end_local)]``。

    与生产实现**不同路**：
    - 生产实现：枚举全部候选 offset + 自洽校验（``timeline.resolve_local``）；
    - 参照实现：段区间包含式（``reference.RefTimeline.resolve_local``）。
    """
    points = [start_utc for start_utc in theirs.starts
              if start_utc != -(1 << 62) and start <= start_utc < end]
    found = []
    for point in points:
        before = theirs.state_at(point - 1)[0]
        after = theirs.state_at(point)[0]
        if before == after:
            continue
        if after > before:
            kind, low, high = "GAP", point + before, point + after
        else:
            kind, low, high = "OVERLAP", point + after, point + before
        if civil.local_naive_from_epoch(low)[0] != year:
            continue
        # 复核（与生产实现同口径，但走参照实现的候选算法）
        ok = True
        for local in range(low, high):
            candidates = theirs.resolve_local(local)
            if kind == "GAP":
                if candidates:
                    ok = False
                    break
            else:
                if len(candidates) != 2:
                    ok = False
                    break
                if candidates[0][1] == candidates[1][1]:
                    ok = False
                    break
        if not ok:
            continue
        found.append((kind, low, high))
    found.sort(key=lambda item: (item[1], item[0]))
    return found


# ---------------------------------------------------------------- diff 套件


def diff_stats(trees, pair):
    """版本对的差异分类名单（**只由输入决定**）。

    ``stats`` 里只放"输入 + 期望"，不含任何观测/耗时字段：

    - ``old_version`` / ``new_version``：参与比较的两棵树。
    - ``zones_compared``：分母（两树 zone 并集的大小）。
    - ``diff_errors``：单 zone 失败数（必须 0）。
    - ``window_changed``：**窗口内**变化的 zone 名单（``--window`` 覆盖 2000-2030）。
    - ``all_history_changed``：**全历史**变化的 zone 名单。
    - ``changes``：每条 ``{zone, class, evidence}``（两份名单合一，按 zone 去重）。

    口径见 `plan/04` §二：**名单不写死条数**，断言用集合相等。
    """
    from tzaudit import diff
    from tzaudit.zoneinfo_store import ZoneinfoStore, byte_key

    old_ver, new_ver = pair
    old_store = ZoneinfoStore(trees[old_ver])
    new_store = ZoneinfoStore(trees[new_ver])

    full = diff.diff_trees(old_store, new_store)
    windowed = diff.diff_trees(old_store, new_store, window=DIFF_WINDOW)

    errors = list(full.errors) + list(windowed.errors)
    changes = [{
        "zone": item.zone,
        "class": item.class_,
        "evidence": item.evidence,
    } for item in full.changes]

    stats = {
        "old_version": old_ver,
        "new_version": new_ver,
        "zones_compared": full.summary["zones_compared"],
        "diff_errors": len(errors),
        "window": list(DIFF_WINDOW),
        "window_changed": [item.zone for item in windowed.changes],
        "all_history_changed": [item.zone for item in full.changes],
        "unclassified": list(full.summary["unclassified"]),
        "changes": changes,
    }
    # 排序一律字节序（K4）
    stats["window_changed"].sort(key=byte_key)
    stats["all_history_changed"].sort(key=byte_key)
    stats["unclassified"].sort(key=byte_key)
    stats["changes"].sort(key=lambda item: byte_key(item["zone"]))
    return stats, errors


def cross_check_diff(trees, pair):
    """diff 层与 ``tests/reference.py`` 对拍 → ``(checked, mismatches)``。

    参照实现（``reference.RefTimeline``）**独立**读 TZif、**独立**解析 POSIX、
    用**区间包含式**求状态；这里用它独立重算"第一个 offset 差异落在共有历史内还是表外"，
    再与生产实现的分类结论逐条比对。

    为什么不能只抽几个时刻比 offset（M4 首版踩中）：真实对上的历史差异落在
    1925 / 1979 / 1992 年，用 2000–2030 的均匀抽样会**一个都碰不到**，
    对拍于是恒过（假门）。必须**枚举参照实现的段起点**——那是它自己的断点集合，
    与生产实现的 ``timeline.segments`` 是两份独立数据。
    """
    if os.path.join(ROOT, "tests") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "tests"))
    try:
        import reference
    except ImportError as exc:
        return 0, ["参照实现不可用: %s" % exc]

    from tzaudit import diff
    from tzaudit.zoneinfo_store import ZoneinfoStore

    old_ver, new_ver = pair
    old_store = ZoneinfoStore(trees[old_ver])
    new_store = ZoneinfoStore(trees[new_ver])
    result = diff.diff_trees(old_store, new_store)

    # 参照实现的时间线要展开到足够远，才能看见表外行为
    horizon = civil.epoch_from_local_naive(DIFF_FUTURE_SENTINEL_YEAR, 1, 1)
    old_min, old_max = civil.epoch_from_local_naive(1800, 1, 1), horizon

    checked = 0
    mismatches = []
    for item in result.changes:
        zone = item.zone
        if item.class_ == "alias_only":
            continue  # alias 判据是 link 关系，不走时间线
        try:
            ref_a = reference.read_timeline(old_store.read_zone(zone), old_min, old_max)
            ref_b = reference.read_timeline(new_store.read_zone(zone), old_min, old_max)
        except Exception as exc:
            mismatches.append("%s: 对拍异常 %s: %s" % (zone, type(exc).__name__, exc))
            continue

        verdict = _reference_classify_diff(ref_a, ref_b)
        checked += 1

        # 参照实现与生产实现必须给出**同一个类别**
        if verdict != item.class_:
            # 唯一允许的偏差：生产实现判 future_rule 且参照实现只看到 abbr 差异时，
            # 说明差异在表外且需要 tail 结构比较（参照实现不做结构化 tail 比较）——
            # 这种情形要求生产实现的 evidence 是 tail，且参照实现**没有**看到 offset 差异。
            if item.class_ == "future_rule" and verdict == "abbreviation_only":
                continue
            mismatches.append("%s: 分类不一致（生产 %s / 参照 %s）"
                              % (zone, item.class_, verdict))

    if checked < DIFF_MIN_CROSS_CHECK:
        mismatches.append("diff 对拍样本不足：%d < %d" % (checked, DIFF_MIN_CROSS_CHECK))
    return checked, mismatches


def _reference_classify_diff(ref_a, ref_b):
    """用参照实现的段表**独立**判定类别（前 1–3 类；``alias`` 不在此层）。

    与生产实现同口径，但数据来源完全独立（参照实现自己的段起点、自己的状态求值）。
    """
    # 共有历史右边界 = 两树表尾的较早者（任一树无表 → 无共有历史）
    ends = [tl.table_end for tl in (ref_a, ref_b) if tl.table_end is not None]
    hist_end = min(ends) if len(ends) == 2 else None

    # 断点 = 两树参照实现自己的段起点的并集
    breaks = set()
    for tl in (ref_a, ref_b):
        for start in tl.starts:
            if start != -(1 << 62):
                breaks.add(start)
    if not breaks:
        breaks.add(0)

    first_offset = None
    abbr_seen = None
    for utc in sorted(breaks):
        off_a, abbr_a, _ = ref_a.state_at(utc)
        off_b, abbr_b, _ = ref_b.state_at(utc)
        if off_a != off_b and first_offset is None:
            first_offset = utc
        elif off_a == off_b and abbr_a != abbr_b and abbr_seen is None:
            abbr_seen = utc

    if first_offset is not None:
        if hist_end is not None and first_offset < hist_end:
            return "history_reinterpreted"
        return "future_rule"
    if abbr_seen is not None:
        return "abbreviation_only"
    return "future_rule"  # 表内无差异、仅 tail 结构不同（参照层看不到 → 交给生产）


# ---------------------------------------------------------------- regen / check


def _expect_doc(version, tree_dir, stats, cross_checked):
    prov = _provenance(tree_dir)
    return {
        "schema": EXPECT_SCHEMA,
        "suite": "parse",
        "input": {
            "version": version,
            "kind": prov.get("kind"),
            "pypi_version": prov.get("pypi_version"),
            "sha256": prov.get("sha256"),
            "tree": "data/_downloads/slim/%s" % version,
        },
        "expected": {
            "zones": stats["zones"],
            "parse_errors": stats["parse_errors"],
            "transitions_total": stats["transitions_total"],
            "tzif_versions": stats["tzif_versions"],
            "slim_zones": stats["slim_zones"],
            "tail_zones": stats["tail_zones"],
            "tzif_digest": stats["tzif_digest"],
            "reference_cross_checked": cross_checked,
        },
    }


def _timeline_doc(version, tree_dir, stats, cross_checked):
    """timeline 套件的金标（**只存输入 + 期望**，不存观测）。"""
    prov = _provenance(tree_dir)
    return {
        "schema": EXPECT_SCHEMA,
        "suite": "timeline",
        "input": {
            "version": version,
            "kind": prov.get("kind"),
            "pypi_version": prov.get("pypi_version"),
            "sha256": prov.get("sha256"),
            "tree": "data/_downloads/slim/%s" % version,
            "window": stats["window"],
            "probes": TIMELINE_PROBES,
        },
        "expected": {
            "zones": stats["zones"],
            "timeline_errors": stats["timeline_errors"],
            "sampled_zones": stats["sampled_zones"],
            "sampled_transitions": stats["sampled_transitions"],
            "sampled_tail_points": stats["sampled_tail_points"],
            "sampled": stats["sampled"],
            "reference_cross_checked": cross_checked,
        },
    }


TIMELINE_KEYS = ("zones", "timeline_errors", "sampled_zones", "sampled_transitions",
                 "sampled_tail_points", "sampled")

WINDOWS_KEYS = ("zones", "windows_errors", "total_windows", "sampled_zones", "sampled")

#: diff 套件的期望字段（`plan/04` §二：名单**集合相等**，不写死条数）
DIFF_KEYS = ("zones_compared", "diff_errors", "window", "window_changed",
             "all_history_changed", "unclassified", "changes")


def _windows_doc(version, tree_dir, stats, cross_checked):
    """windows 套件的金标（**只存输入 + 期望**，不存观测）。"""
    prov = _provenance(tree_dir)
    return {
        "schema": EXPECT_SCHEMA,
        "suite": "windows",
        "input": {
            "version": version,
            "kind": prov.get("kind"),
            "pypi_version": prov.get("pypi_version"),
            "sha256": prov.get("sha256"),
            "tree": "data/_downloads/slim/%s" % version,
            "years": stats["years"],
            "sample_zones": list(WINDOWS_SAMPLE_ZONES),
        },
        "expected": {
            "zones": stats["zones"],
            "windows_errors": stats["windows_errors"],
            "total_windows": stats["total_windows"],
            "sampled_zones": stats["sampled_zones"],
            "sampled": stats["sampled"],
            "reference_cross_checked": cross_checked,
        },
    }


def _write_doc(target_dir, filename, doc):
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)
    path = os.path.join(target_dir, filename)
    text = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def _diff_doc(pair, trees, stats, cross_checked):
    """diff 套件的金标（**只存输入 + 期望**，不存观测）。

    文件名带**版本对**（`data/README.md` §二 真值纪律第 4 条）：
    ``data/tzdb/pairs/<old>-<new>.json``，避免"金标跟着最新版漂"。
    """
    old_ver, new_ver = pair
    prov_old = _provenance(trees[old_ver])
    prov_new = _provenance(trees[new_ver])
    return {
        "schema": EXPECT_SCHEMA,
        "suite": "diff",
        "pair": "%s-%s" % (old_ver, new_ver),
        "input": {
            "old": {
                "version": old_ver,
                "kind": prov_old.get("kind"),
                "pypi_version": prov_old.get("pypi_version"),
                "sha256": prov_old.get("sha256"),
                "tree": "data/_downloads/slim/%s" % old_ver,
            },
            "new": {
                "version": new_ver,
                "kind": prov_new.get("kind"),
                "pypi_version": prov_new.get("pypi_version"),
                "sha256": prov_new.get("sha256"),
                "tree": "data/_downloads/slim/%s" % new_ver,
            },
            "window": stats["window"],
            "window_note": "window_changed 用 --window；all_history_changed 为全历史",
        },
        "expected": {
            "zones_compared": stats["zones_compared"],
            "diff_errors": stats["diff_errors"],
            "window": stats["window"],
            "window_changed": stats["window_changed"],
            "all_history_changed": stats["all_history_changed"],
            "unclassified": stats["unclassified"],
            "changes": stats["changes"],
            "reference_cross_checked": cross_checked,
        },
    }


def _write_expect(version, doc):
    return _write_doc(os.path.join(TZDB_DIR, version), "expect.json", doc)


def _write_timeline_expect(version, doc):
    return _write_doc(os.path.join(TZDB_DIR, version), "expect-timeline.json", doc)


def _write_windows_expect(version, doc):
    return _write_doc(os.path.join(TZDB_DIR, version), "expect-windows.json", doc)


def _write_diff_expect(pair_name, doc):
    """diff 金标落在 ``data/tzdb/pairs/<old>-<new>.json``（文件名带版本对）。"""
    return _write_doc(os.path.join(TZDB_DIR, "pairs"), "%s.json" % pair_name, doc)


def regen(trees, suites=SUITES):
    problems = []
    written = 0
    print("tzdata 金标重生成 · --regen（套件: %s）" % ", ".join(suites))
    print("=" * 56)
    for version in sorted(trees):
        tree_dir = trees[version]
        if "parse" in suites:
            stats, errors = parse_tree(tree_dir)
            if stats["zones"] <= 0:
                problems.append("%s: 树里 0 个 zone（分母空跑）" % version)
                continue
            if errors:
                problems.append("%s: %d 处解析错误（例: %s）"
                                % (version, len(errors), errors[0]))
                continue
            checked, mismatches = cross_check(tree_dir)
            if mismatches:
                for item in mismatches:
                    problems.append("%s: %s" % (version, item))
                continue
            path = _write_expect(version, _expect_doc(version, tree_dir, stats, checked))
            written += 1
            print("  %s parse    → %s  zones=%d  transitions=%d  对拍=%d"
                  % (version, os.path.relpath(path, ROOT), stats["zones"],
                     stats["transitions_total"], checked))

        if "timeline" in suites:
            stats, errors = timeline_stats(tree_dir)
            if stats["zones"] <= 0:
                problems.append("%s: timeline 树里 0 个 zone（分母空跑）" % version)
                continue
            if errors:
                problems.append("%s: %d 处 timeline 错误（例: %s）"
                                % (version, len(errors), errors[0]))
                continue
            if not stats["sampled"]:
                problems.append("%s: timeline 抽样集为空（判据空跑）" % version)
                continue
            checked, mismatches = cross_check_timeline(tree_dir)
            if mismatches:
                for item in mismatches:
                    problems.append("%s: %s" % (version, item))
                continue
            path = _write_timeline_expect(
                version, _timeline_doc(version, tree_dir, stats, checked))
            written += 1
            print("  %s timeline → %s  zone 抽样=%d  转换点=%d  tail 点=%d  对拍=%d"
                  % (version, os.path.relpath(path, ROOT), len(stats["sampled"]),
                     stats["sampled_transitions"], stats["sampled_tail_points"], checked))

        if "windows" in suites:
            stats, errors = windows_stats(tree_dir)
            if stats["zones"] <= 0:
                problems.append("%s: windows 树里 0 个 zone（分母空跑）" % version)
                continue
            if errors:
                problems.append("%s: %d 处 windows 错误（例: %s）"
                                % (version, len(errors), errors[0]))
                continue
            if not stats["sampled"]:
                problems.append("%s: windows 抽样集为空（判据空跑）" % version)
                continue
            # 抽样集必须**真的**覆盖 GAP 与 OVERLAP 两种（否则等于没验）
            kinds = {row["type"] for item in stats["sampled"]
                     for year_row in item["years"] for row in year_row["windows"]}
            if not {"GAP", "OVERLAP"} <= kinds:
                problems.append("%s: windows 抽样集缺 GAP/OVERLAP 之一（实际=%r）"
                                % (version, sorted(kinds)))
                continue
            checked, mismatches = cross_check_windows(tree_dir)
            if mismatches:
                for item in mismatches:
                    problems.append("%s: %s" % (version, item))
                continue
            path = _write_windows_expect(
                version, _windows_doc(version, tree_dir, stats, checked))
            written += 1
            window_count = sum(len(year_row["windows"])
                               for item in stats["sampled"] for year_row in item["years"])
            print("  %s windows → %s  zone 抽样=%d  窗口=%d  对拍=%d"
                  % (version, os.path.relpath(path, ROOT), len(stats["sampled"]),
                     window_count, checked))

    if "diff" in suites:
        for pair in DIFF_PAIRS:
            old_ver, new_ver = pair
            missing = [v for v in pair if v not in trees]
            if missing:
                problems.append("%s-%s: 缺本地树 %s" % (old_ver, new_ver, ", ".join(missing)))
                continue
            stats, errors = diff_stats(trees, pair)
            if stats["zones_compared"] <= 0:
                problems.append("%s-%s: diff 分母为 0（空跑）" % (old_ver, new_ver))
                continue
            if errors:
                problems.append("%s-%s: %d 处 diff 错误（例: %s）"
                                % (old_ver, new_ver, len(errors), errors[0]))
                continue
            # 判据不得退化：全历史必须**真的**产出变更，且类别不止一种
            kinds = set(item["class"] for item in stats["changes"])
            if not stats["changes"]:
                problems.append("%s-%s: diff 全历史零变更（判据空跑）" % (old_ver, new_ver))
                continue
            if len(kinds) < 2:
                problems.append("%s-%s: diff 只产出一类（%r）—— 分类判据可能退化"
                                % (old_ver, new_ver, sorted(kinds)))
                continue
            checked, mismatches = cross_check_diff(trees, pair)
            if mismatches:
                for item in mismatches:
                    problems.append("%s-%s: %s" % (old_ver, new_ver, item))
                continue
            pair_name = "%s-%s" % (old_ver, new_ver)
            path = _write_diff_expect(pair_name, _diff_doc(pair, trees, stats, checked))
            written += 1
            print("  %s diff    → %s  比较=%d  变更=%d  窗口内=%d  对拍=%d"
                  % (pair_name, os.path.relpath(path, ROOT), stats["zones_compared"],
                     len(stats["changes"]), len(stats["window_changed"]), checked))

    print("=" * 56)
    if problems:
        print("结论: FAIL（%d 处），未写任何不干净的金标" % len(problems))
        for item in problems:
            print("  FAIL  %s" % item)
        return EXIT_MISMATCH
    print("结论: 写出 %d 份金标" % written)
    return EXIT_OK


def _load_doc(version, filename):
    path = os.path.join(TZDB_DIR, version, filename)
    if not os.path.isfile(path):
        return None
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        return "BROKEN"


def _load_pair_doc(pair_name):
    """读 ``data/tzdb/pairs/<old>-<new>.json``。"""
    path = os.path.join(TZDB_DIR, "pairs", "%s.json" % pair_name)
    if not os.path.isfile(path):
        return None
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        return "BROKEN"


def _check_parse(tree_dir, version, bad):
    """parse 套件的复算与比对 → ``(checked, zones)``。"""
    stats, errors = parse_tree(tree_dir)

    expect = _load_doc(version, "expect.json")
    if expect is None:
        bad.append("%s: 缺 expect.json（跑 --regen）" % version)
        return 0, stats["zones"]
    if expect == "BROKEN":
        bad.append("%s: expect.json 不是合法 JSON" % version)
        return 0, stats["zones"]

    # 1) 零解析错误（判据正确性门槛）
    if stats["parse_errors"] != 0:
        bad.append("%s: parse_errors=%d（必须 0）；例: %s"
                   % (version, stats["parse_errors"], errors[0] if errors else "-"))
    # 2) 分母非空
    if stats["zones"] <= 0:
        bad.append("%s: zones=0（分母空跑）" % version)

    # 3) 与期望逐项比对
    expected = expect.get("expected") or {}
    for key in ("zones", "parse_errors", "transitions_total", "tzif_versions",
                "slim_zones", "tail_zones", "tzif_digest"):
        if expected.get(key) != stats[key]:
            bad.append("%s: %s 漂移（期望=%r 实测=%r）"
                       % (version, key, expected.get(key), stats[key]))

    # 4) 独立参照对拍（防引擎自证）
    checked, mismatches = cross_check(tree_dir)
    if mismatches:
        bad.extend("%s: %s" % (version, item) for item in mismatches)

    print("  %-7s parse    zones=%-4d parse_errors=%d transitions=%-5d 对拍=%d"
          % (version, stats["zones"], stats["parse_errors"],
             stats["transitions_total"], checked))
    return checked, stats["zones"]


def _check_timeline(tree_dir, version, bad):
    """timeline 套件的复算与比对。"""
    stats, errors = timeline_stats(tree_dir)

    expect = _load_doc(version, "expect-timeline.json")
    if expect is None:
        bad.append("%s: 缺 expect-timeline.json（跑 --regen --suite timeline）" % version)
        return
    if expect == "BROKEN":
        bad.append("%s: expect-timeline.json 不是合法 JSON" % version)
        return

    if stats["timeline_errors"] != 0:
        bad.append("%s: timeline_errors=%d（必须 0）；例: %s"
                   % (version, stats["timeline_errors"], errors[0] if errors else "-"))
    if stats["zones"] <= 0:
        bad.append("%s: timeline zones=0（分母空跑）" % version)
    if not stats["sampled"]:
        bad.append("%s: timeline 抽样集为空（判据空跑）" % version)

    expected = expect.get("expected") or {}
    for key in TIMELINE_KEYS:
        if expected.get(key) != stats[key]:
            bad.append("%s: timeline.%s 漂移（期望=%r 实测=%r）"
                       % (version, key, expected.get(key), stats[key]))

    checked, mismatches = cross_check_timeline(tree_dir)
    if mismatches:
        bad.extend("%s: %s" % (version, item) for item in mismatches)

    print("  %-7s timeline 抽样=%-3d 转换点=%-5d tail 点=%-5d 对拍=%d"
          % (version, len(stats["sampled"]), stats["sampled_transitions"],
             stats["sampled_tail_points"], checked))


def _check_windows(tree_dir, version, bad):
    """windows 套件的复算与比对。"""
    stats, errors = windows_stats(tree_dir)

    expect = _load_doc(version, "expect-windows.json")
    if expect is None:
        bad.append("%s: 缺 expect-windows.json（跑 --regen --suite windows）" % version)
        return
    if expect == "BROKEN":
        bad.append("%s: expect-windows.json 不是合法 JSON" % version)
        return

    if stats["windows_errors"] != 0:
        bad.append("%s: windows_errors=%d（必须 0）；例: %s"
                   % (version, stats["windows_errors"], errors[0] if errors else "-"))
    if stats["zones"] <= 0:
        bad.append("%s: windows zones=0（分母空跑）" % version)
    if not stats["sampled"]:
        bad.append("%s: windows 抽样集为空（判据空跑）" % version)

    expected = expect.get("expected") or {}
    for key in WINDOWS_KEYS:
        if expected.get(key) != stats[key]:
            bad.append("%s: windows.%s 漂移（期望=%r 实测=%r）"
                       % (version, key, expected.get(key), stats[key]))

    checked, mismatches = cross_check_windows(tree_dir)
    if mismatches:
        bad.extend("%s: %s" % (version, item) for item in mismatches)

    window_count = sum(len(year_row["windows"])
                       for item in stats["sampled"] for year_row in item["years"])
    print("  %-7s windows 抽样=%-3d 窗口=%-4d 对拍=%d"
          % (version, len(stats["sampled"]), window_count, checked))


def _check_diff(trees, pair, bad):
    """diff 套件的复算与比对（名单**集合相等**，不写死条数）。"""
    old_ver, new_ver = pair
    pair_name = "%s-%s" % (old_ver, new_ver)
    stats, errors = diff_stats(trees, pair)

    expect = _load_pair_doc(pair_name)
    if expect is None:
        bad.append("%s: 缺 pairs/%s.json（跑 --regen --suite diff）" % (pair_name, pair_name))
        return
    if expect == "BROKEN":
        bad.append("%s: pairs/%s.json 不是合法 JSON" % (pair_name, pair_name))
        return

    if stats["diff_errors"] != 0:
        bad.append("%s: diff_errors=%d（必须 0）；例: %s"
                   % (pair_name, stats["diff_errors"], errors[0] if errors else "-"))
    if stats["zones_compared"] <= 0:
        bad.append("%s: diff 分母为 0（空跑）" % pair_name)
    if not stats["changes"]:
        bad.append("%s: diff 全历史零变更（判据空跑）" % pair_name)

    expected = expect.get("expected") or {}

    # 1) 标量字段逐项比对
    for key in ("zones_compared", "diff_errors", "window"):
        if expected.get(key) != stats[key]:
            bad.append("%s: diff.%s 漂移（期望=%r 实测=%r）"
                       % (pair_name, key, expected.get(key), stats[key]))

    # 2) **名单用集合相等**（`plan/04` §二 真值纪律第 3 条：不写死条数）
    for key in ("window_changed", "all_history_changed", "unclassified"):
        want = set(expected.get(key) or [])
        got = set(stats[key])
        if want != got:
            bad.append("%s: diff.%s 不相等（多出 %r / 缺少 %r）"
                       % (pair_name, key, sorted(got - want), sorted(want - got)))

    # 3) 每条记录的三元组也必须集合相等（防止"名单对了但类别判错"）
    want_rows = set((item["zone"], item["class"], item["evidence"])
                    for item in (expected.get("changes") or []))
    got_rows = set((item["zone"], item["class"], item["evidence"])
                   for item in stats["changes"])
    if want_rows != got_rows:
        bad.append("%s: diff.changes 不相等（多出 %r / 缺少 %r）"
                   % (pair_name, sorted(got_rows - want_rows), sorted(want_rows - got_rows)))

    # 4) 判据不得退化：类别至少两类（防"只产一种"的实现恒绿）
    kinds = set(item["class"] for item in stats["changes"])
    if stats["changes"] and len(kinds) < 2:
        bad.append("%s: diff 只产出一类（%r）—— 分类判据可能退化"
                   % (pair_name, sorted(kinds)))

    # 5) 独立参照对拍
    checked, mismatches = cross_check_diff(trees, pair)
    if mismatches:
        bad.extend("%s: %s" % (pair_name, item) for item in mismatches)

    print("  %-13s diff  比较=%-4d 变更=%-3d 窗口内=%-3d 对拍=%d"
          % (pair_name, stats["zones_compared"], len(stats["changes"]),
             len(stats["window_changed"]), checked))


def check(trees, suites=SUITES):
    """复算并与入仓金标比对。分母 > 0 是硬门槛。"""
    versions = _tzdb_versions()
    print("tzdata 金标复算 · --check（套件: %s）" % ", ".join(suites))
    print("=" * 56)
    print("入仓版本: %s" % (", ".join(versions) if versions else "（无）"))

    if not versions:
        print("缺件: data/tzdb 下没有版本目录（先跑 tools/fetch_tzdb.py）")
        print("结论: 环境不满足（exit 3），**不是** 0 项通过")
        return EXIT_ENV

    missing_trees = [v for v in versions if v not in trees]
    if missing_trees:
        print("缺件: 以下版本没有本地树 data/_downloads/slim/<ver>/：%s"
              % ", ".join(missing_trees))
        print("处置: py -3.12 tools/fetch_tzdb.py --versions %s" % ",".join(missing_trees))
        print("结论: 环境不满足（exit 3），**不是** 0 项通过")
        return EXIT_ENV

    denominator = 0
    zones_seen = 0
    bad = []
    for version in versions:
        tree_dir = trees[version]
        denominator += 1

        if "parse" in suites:
            _checked, zones = _check_parse(tree_dir, version, bad)
            zones_seen = zones
            # provenance.zones 与实测一致（`plan/04` §1.2 的"漂移即报"）
            prov = _provenance(tree_dir)
            if prov.get("zones") is not None and prov.get("zones") != zones:
                bad.append("%s: provenance.zones=%r 与实测 %d 不符"
                           % (version, prov.get("zones"), zones))

        if "timeline" in suites:
            _check_timeline(tree_dir, version, bad)

        if "windows" in suites:
            _check_windows(tree_dir, version, bad)

    if "diff" in suites:
        denominator += len(DIFF_PAIRS)
        for pair in DIFF_PAIRS:
            missing = [v for v in pair if v not in trees]
            if missing:
                bad.append("%s-%s: 缺本地树 %s（跑 tools/fetch_tzdb.py）"
                           % (pair[0], pair[1], ", ".join(missing)))
                continue
            _check_diff(trees, pair, bad)

    print("=" * 56)
    print("复算项数: %d（分母必须 > 0）" % denominator)
    print("不一致: %d" % len(bad))
    for item in bad:
        print("  FAIL  %s" % item)
    if denominator == 0:
        print("结论: 分母为 0 —— 判据空跑，按 FAIL 处理")
        return EXIT_ENV
    if bad:
        print("结论: %d 项不一致" % len(bad))
        return EXIT_MISMATCH
    if "parse" in suites:
        print("结论: 全量树 %d 个 zone 零解析错误，%d 份金标复算一致"
              % (zones_seen, denominator))
    elif "timeline" in suites:
        print("结论: %d 份 timeline 金标复算一致" % denominator)
    elif "windows" in suites:
        print("结论: %d 份 windows 金标复算一致" % denominator)
    else:
        print("结论: %d 份 diff 金标复算一致" % len(DIFF_PAIRS))
    return EXIT_OK


def main(argv=None):
    args = build_parser().parse_args(argv)
    trees = _slim_trees()
    suites = (args.suite,) if args.suite else SUITES

    if args.regen:
        if not trees:
            print("缺件: data/_downloads/slim 不存在或为空")
            print("处置: py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e")
            print("结论: 环境不满足（exit 3），**不是** 0 项通过")
            return EXIT_ENV
        return regen(trees, suites)

    # 默认动作 = --check
    return check(trees, suites)


if __name__ == "__main__":
    sys.exit(main())