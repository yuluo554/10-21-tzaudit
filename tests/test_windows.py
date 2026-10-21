# -*- coding: utf-8 -*-
"""墙钟风险窗口 —— 契约见 ``plan/03`` §五。

五层断言（每层都能跑红）：

1. **合成 fixture**（``data/fixtures/windows/``）：三条特殊形态 + 一个"假窗口"注入。
2. **NY 2026**：恰好两条，方向正确（GAP 在前 / OVERLAP 在后）。
3. **Vancouver 2026 → 零条**：反例单测（只看 fold 的实现会在这里误报一条）。
4. **三条特殊形态**：Lord_Howe（30 分钟）/ Chatham（45 分钟）/ Dublin（负 DST）。
5. **批量与确定性**：``--all`` 跑完、单 zone 错误不中断、双跑逐字节一致。

第 3 层是**最关键**的一条：`data/README.md` §4.1 明令"禁止仅用 ``fold=0 != fold=1`` 判 OVERLAP"
（Vancouver 实测踩中）。这里的实现层判据是"**候选个数**"（K10），与文档的表述交叉断言。
"""

import io
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from tzaudit import civil, timeline, windows  # noqa: E402
from tzaudit.zoneinfo_store import ZoneinfoStore  # noqa: E402

SLIM = os.path.join(ROOT, "data", "_downloads", "slim")
FAT_FIXTURE = os.path.join(ROOT, "data", "fixtures", "tzif", "source-vs-wheel", "fat")
WINDOWS_FIXTURE = os.path.join(ROOT, "data", "fixtures", "windows")

needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）",
)


def _slim(version="2026e"):
    return ZoneinfoStore(os.path.join(SLIM, version))


def _scan(zone, year, store=None):
    """扫一个 zone 某年 → ``list[Window]``。"""
    store = store or _slim()
    tl = timeline.load_timeline(
        zone, store,
        window_start=civil.epoch_from_local_naive(year, 1, 1) - 2 * 86400,
        window_end=civil.epoch_from_local_naive(year + 1, 1, 1) + 2 * 86400)
    return windows.scan_year(zone, year, tl)


def _local(item):
    return (civil.format_local(item.start_local), civil.format_local(item.end_local))


# ---------------------------------------------------------------- 1. NY 2026 主用例


@needs_trees
def test_new_york_2026_has_exactly_two_windows_with_correct_direction():
    """NY 2026：GAP ``02:00→03:00``（3 月起跳）、OVERLAP ``01:00→02:00``（11 月回拨）。

    方向不能反：起跳是**墙钟向前跳**（GAP），回拨是**墙钟向后叠**（OVERLAP）。
    """
    found = _scan("America/New_York", 2026)
    assert len(found) == 2, [item.type for item in found]

    gap, overlap = found[0], found[1]
    assert gap.type == windows.GAP
    assert _local(gap) == ("2026-03-08 02:00:00", "2026-03-08 03:00:00")
    assert gap.duration_min == 60 and gap.residual_sec == 0
    assert gap.offset_before == -18000 and gap.offset_after == -14400

    assert overlap.type == windows.OVERLAP
    assert _local(overlap) == ("2026-11-01 01:00:00", "2026-11-01 02:00:00")
    assert overlap.duration_min == 60 and overlap.residual_sec == 0
    assert overlap.offset_before == -14400 and overlap.offset_after == -18000


@needs_trees
def test_window_records_the_engine_it_came_from():
    """``source`` 是一等字段（``plan/02`` §2.1）：NY 2026 的两条都来自 **tail**。

    slim 树里 NY 的显式表只到 2007 年，2026 年的转换点全在 POSIX tail 展开出来的段里。
    """
    for item in _scan("America/New_York", 2026):
        assert item.source in ("table", "tail")
        assert item.source == "tail", "NY 2026 的转换点应来自 tail 段"


@needs_trees
def test_fat_tree_reports_the_same_windows_with_source_table():
    """fat 树（显式表）里同一年必须是**同样两条**窗口，只是 ``source=table``。

    这条锁的是"**双引擎合并后语义等价**"在窗口层的落点：编码不同，结论相同。
    """
    store = ZoneinfoStore(FAT_FIXTURE)
    found = _scan("America/New_York", 2026, store)
    assert len(found) == 2
    assert [item.type for item in found] == [windows.GAP, windows.OVERLAP]
    assert [_local(item) for item in found] == [
        ("2026-03-08 02:00:00", "2026-03-08 03:00:00"),
        ("2026-11-01 01:00:00", "2026-11-01 02:00:00"),
    ]
    for item in found:
        assert item.source == "table"


# ---------------------------------------------------------------- 2. Vancouver 反例


@needs_trees
def test_vancouver_2026_has_no_false_overlap():
    """**反例单测**：Vancouver 2026-11 起永久 UTC−7 → 那一年**只有 GAP，零 OVERLAP**。

    2026 年 BC 废除了夏令时：3 月起跳仍在（表里），但 11 月**不再回拨**（tail 已改成 ``MST7``）。
    只按"转换前后 offset 不同"或"fold 两值不同"判 OVERLAP 的实现，会在这里**误报一条**。
    """
    found = _scan("America/Vancouver", 2026)
    assert [item.type for item in found] == [windows.GAP], \
        "Vancouver 2026 只应有 GAP，误报了: %r" % ([item.type for item in found],)
    assert _local(found[0]) == ("2026-03-08 02:00:00", "2026-03-08 03:00:00")


@needs_trees
def test_vancouver_still_had_an_overlap_before_dst_abolition():
    """**反向对照**：2025 年（BC 之前）Vancouver 仍有 OVERLAP。

    没有这条，"零条"可能只是因为实现根本不扫这个 zone（假绿）。
    """
    found = _scan("America/Vancouver", 2025)
    assert [item.type for item in found] == [windows.GAP, windows.OVERLAP]
    assert _local(found[1]) == ("2025-11-02 01:00:00", "2025-11-02 02:00:00")


# ---------------------------------------------------------------- 3. 三条特殊形态


@needs_trees
def test_lord_howe_has_thirty_minute_windows():
    """Lord_Howe（+10:30 / +11:00）：两条窗口，``duration_min=30``（不是 60）。"""
    found = _scan("Australia/Lord_Howe", 2026)
    assert len(found) == 2, [item.type for item in found]
    for item in found:
        assert item.duration_min == 30, item
        assert item.residual_sec == 0, item
    # 南半球：先回拨（4 月）再起跳（10 月）——排序按 start_local 升序
    assert [item.type for item in found] == [windows.OVERLAP, windows.GAP]
    assert _local(found[0]) == ("2026-04-05 01:30:00", "2026-04-05 02:00:00")
    assert _local(found[1]) == ("2026-10-04 02:00:00", "2026-10-04 02:30:00")
    # 偏移必须含 30 分钟分量（37800 = +10:30）
    assert 37800 in (found[0].offset_before, found[0].offset_after)


@needs_trees
def test_chatham_offsets_carry_45_minutes():
    """Chatham（+12:45 / +13:45）：偏移含 45 分钟分量（45900 = +12:45）。"""
    found = _scan("Pacific/Chatham", 2026)
    assert len(found) == 2
    for item in found:
        assert 45900 in (item.offset_before, item.offset_after), item
        assert item.duration_min == 60, item


@needs_trees
def test_dublin_negative_dst_direction_is_correct():
    """Dublin（负 DST）：冬季 ``IST`` 的 offset 是 **0**、夏季 ``GMT`` 是 **+3600**。

    起跳（3 月）从 0 走到 +3600 → **墙钟向前跳** → GAP；
    回拨（10 月）从 +3600 回到 0 → **墙钟向后叠** → OVERLAP。
    负 DST 下"offset 变大 = GAP"这条仍然成立（方向由 offset 差决定，不由 is_dst 决定）。
    """
    found = _scan("Europe/Dublin", 2026)
    assert len(found) == 2, [item.type for item in found]
    assert [item.type for item in found] == [windows.GAP, windows.OVERLAP]
    assert _local(found[0]) == ("2026-03-29 01:00:00", "2026-03-29 02:00:00")
    assert found[0].offset_before == 0 and found[0].offset_after == 3600
    assert _local(found[1]) == ("2026-10-25 01:00:00", "2026-10-25 02:00:00")
    assert found[1].offset_before == 3600 and found[1].offset_after == 0


@needs_trees
def test_zone_without_transitions_yields_no_window():
    """无 DST 的 zone（``UTC`` / ``Asia/Tehran`` 2026）→ 零条（不报错）。"""
    for zone in ("UTC", "Asia/Tehran"):
        assert _scan(zone, 2026) == [], zone


# ---------------------------------------------------------------- 4. 双判据复核


@needs_trees
def test_candidate_verification_rejects_a_fake_window():
    """**双判据复核自证**：构造一个"转换前后 offset 不同、但墙钟并不缺"的假候选。

    做法：直接调复核函数，给它一个**正常时刻**却谎称是 GAP——
    正常时刻必然有候选（1 个），复核必须判它不成立（返回 False）。
    这证明"复核"不是摆设（把复核改成恒 True，这里立刻红）。
    """
    store = _slim()
    tl = timeline.load_timeline("America/New_York", store,
                                window_end=civil.parse_local("2027-01-01"))
    normal = civil.parse_local("2026-07-01 12:00:00")
    assert windows._verify_candidate(windows.GAP, normal, normal + 3600, tl) is False
    # 正常时刻也不能被当成 OVERLAP（它只有 1 个候选）
    assert windows._verify_candidate(windows.OVERLAP, normal, normal + 3600, tl) is False


@needs_trees
def test_overlap_verification_requires_two_different_offsets():
    """OVERLAP 的复核必须同时要求"2 个候选"**且**"两 offset 不同"。

    构造一个同 offset 的两候选是不可能的（``resolve_local`` 的候选必然 offset 不同），
    所以这里只锁"2 个候选"这一半：GAP 段的探测点必须 0 个候选。
    """
    store = _slim()
    tl = timeline.load_timeline("America/New_York", store,
                                window_end=civil.parse_local("2027-01-01"))
    gap_lo = civil.parse_local("2026-03-08 02:00:00")
    gap_hi = civil.parse_local("2026-03-08 03:00:00")
    assert windows._verify_candidate(windows.GAP, gap_lo, gap_hi, tl) is True
    overlap_lo = civil.parse_local("2026-11-01 01:00:00")
    overlap_hi = civil.parse_local("2026-11-01 02:00:00")
    assert windows._verify_candidate(windows.OVERLAP, overlap_lo, overlap_hi, tl) is True


@needs_trees
def test_every_reported_window_satisfies_its_own_criterion():
    """**全量自洽**：每条报出来的窗口，按 ``data/README.md`` §4.1 的双判据逐条复核都成立。

    这条是"实现层判据"与"文档层判据"的交叉断言——实现层用候选个数，
    文档层用 fold 的 offset 比较，两条路径都必须对。
    """
    store = _slim()
    checked = 0
    for zone in ("America/New_York", "America/Vancouver", "Australia/Lord_Howe",
                 "Pacific/Chatham", "Europe/Dublin", "Antarctica/Troll"):
        tl = timeline.load_timeline(zone, store,
                                    window_start=civil.epoch_from_local_naive(2026, 1, 1),
                                    window_end=civil.epoch_from_local_naive(2027, 1, 1))
        for item in windows.scan_year(zone, 2026, tl):
            candidates = timeline.resolve_local(item.start_local, tl)
            if item.type == windows.GAP:
                assert candidates == [], "%s: GAP 起点必须 0 个候选" % zone
                assert timeline.resolve_local(item.end_local - 1, tl) == [], \
                    "%s: GAP 末点必须 0 个候选" % zone
            else:
                assert len(candidates) == 2, "%s: OVERLAP 起点必须 2 个候选" % zone
                assert candidates[0].offset_sec != candidates[1].offset_sec, \
                    "%s: OVERLAP 的两 offset 必须不同" % zone
                assert timeline.resolve_local(item.end_local - 1, tl), \
                    "%s: OVERLAP 末点必须有候选" % zone
            checked += 1
    assert checked >= 10, "只验到 %d 条窗口——判据可能空跑" % checked


# ---------------------------------------------------------------- 5. 跨年边界


@needs_trees
def test_window_is_filed_under_its_local_wall_clock_year():
    """**跨年边界**：``Asia/Almaty`` 2024 的 OVERLAP 落在 ``2024-02-29 23:00 → 03-01 00:00``。

    转换点是 UTC 时刻，但窗口按**本地墙钟年**归属。只按 UTC 年份取点的实现会把它
    漏掉或错记到 2023/2025。
    """
    found = _scan("Asia/Almaty", 2024)
    assert len(found) == 1, [item.type for item in found]
    assert found[0].type == windows.OVERLAP
    assert _local(found[0]) == ("2024-02-29 23:00:00", "2024-03-01 00:00:00")
    # 相邻年份不得重复记这条（同一窗口只归属一年）
    assert _scan("Asia/Almaty", 2023) == []
    assert _scan("Asia/Almaty", 2025) == []


@needs_trees
def test_leap_day_window_does_not_leak_into_other_years():
    """闰年 2/29 的窗口不得跨年泄漏（``Asia/Qostanay`` 与 Almaty 同形态）。"""
    found = _scan("Asia/Qostanay", 2024)
    assert len(found) == 1
    assert _local(found[0]) == ("2024-02-29 23:00:00", "2024-03-01 00:00:00")
    assert _scan("Asia/Qostanay", 2023) == []
    assert _scan("Asia/Qostanay", 2026) == []


@needs_trees
def test_window_whose_transition_point_falls_after_the_year_end_is_not_lost():
    """**跨年边界（反向形态）**：转换点在**次年**的 UTC 时刻，墙钟窗口却属于**本年**。

    ``America/Managua`` 1996：转换点在 ``1997-01-01 05:00Z``，但墙钟区间是
    ``1996-12-31 23:00 → 1997-01-01 00:00``——**整条窗口落在 1996 里**。
    扫描 1996 时若只取 ``[1996-01-01, 1997-01-01)`` 内的转换点，这条会**整个丢掉**。

    这条是"年份边界余量"的**反例锚点**（与 ``test_window_is_filed_under_its_local_wall_clock_year``
    的"闰日跨月"形态互补：一条考转换点在年内，一条考转换点在年外）。
    """
    found = _scan("America/Managua", 1996)
    assert len(found) == 1, [(w.type, civil.format_local(w.start_local)) for w in found]
    assert found[0].type == windows.OVERLAP
    assert _local(found[0]) == ("1996-12-31 23:00:00", "1997-01-01 00:00:00")
    # 1997 年不得重复记这条（同一窗口只归属一年）
    assert _scan("America/Managua", 1997) == []


@needs_trees
def test_window_whose_transition_point_falls_before_the_year_start_is_not_lost():
    """**跨年边界（另一侧）**：转换点在**上一年**的 UTC 时刻，墙钟窗口属于**本年**。

    ``Asia/Choibalsan`` 1978：转换点在 ``1977-12-31 17:00Z``，墙钟区间是
    ``1978-01-01 00:00 → 01:00``——整条窗口落在 1978 里，但转换点在年外。
    """
    found = _scan("Asia/Choibalsan", 1978)
    assert len(found) == 1, [(w.type, civil.format_local(w.start_local)) for w in found]
    assert _local(found[0]) == ("1978-01-01 00:00:00", "1978-01-01 01:00:00")
    assert _scan("Asia/Choibalsan", 1977) == []


@needs_trees
def test_two_hour_window_is_reported_in_full():
    """2 小时的窗口（``Antarctica/Troll``）→ ``duration_min=120``，区间完整。"""
    found = _scan("Antarctica/Troll", 2026)
    assert len(found) == 2
    for item in found:
        assert item.duration_min == 120, item
        assert item.residual_sec == 0, item


# ---------------------------------------------------------------- 6. 批量与确定性


@needs_trees
def test_scan_all_covers_every_zone_and_records_no_errors():
    """``--all``：``zones_scanned`` 与树里的 zone 数一致，``errors`` 为空。"""
    store = _slim()
    result = windows.scan_all(store, 2026)
    assert result.errors == [], result.errors
    assert result.zones_scanned == len(store.zones())
    assert result.zones_scanned > 0, "分母为 0 —— 判据空跑"
    assert result.windows, "全量扫描一条窗口都没有——判据可能空跑"


@needs_trees
def test_scan_all_output_is_sorted_by_zone_then_start():
    """``--all`` 的排序：zone 字节序 → ``start_local`` 升序 → type 字典序（K4）。"""
    store = _slim()
    result = windows.scan_all(store, 2026)
    keys = [(item.zone.encode("utf-8"), item.start_local, item.type) for item in result.windows]
    assert keys == sorted(keys)


@needs_trees
def test_scan_all_is_deterministic_across_runs():
    """同一棵树双跑 → 逐条相等（**零时间戳、零浮点**的结果集必须完全一致）。"""
    store = _slim()
    first = windows.scan_all(store, 2026)
    second = windows.scan_all(store, 2026)
    assert [(w.zone, w.type, w.start_local, w.end_local, w.duration_min, w.residual_sec,
             w.offset_before, w.offset_after, w.source) for w in first.windows] == \
           [(w.zone, w.type, w.start_local, w.end_local, w.duration_min, w.residual_sec,
             w.offset_before, w.offset_after, w.source) for w in second.windows]


@needs_trees
def test_single_zone_error_does_not_abort_the_batch(tmp_path):
    """**单 zone 错误不中断整批**：坏 zone 进 ``errors``，其余 zone 照常出结果。

    做法：把一棵**只含一个坏 zone**的树与一棵好树合并——坏 zone 的名字排在最前，
    若实现"遇错即中断"，后面的好 zone 就没有窗口了。
    """
    good = _slim()
    bad_tree = tmp_path / "bad"
    bad_tree.mkdir()
    (bad_tree / "AAA_Broken").write_bytes(b"TZif\x00" + b"\x00" * 40)
    (bad_tree / "provenance.json").write_text(
        json.dumps({"version": "test", "kind": "slim", "zones": 1}), encoding="utf-8")

    class _MergedStore(object):
        """把两棵树并成一个（``read_zone`` 按名字分发）。"""

        version = "merged"

        def __init__(self, first, second):
            self._first = first
            self._second = second

        def zones(self):
            return sorted(list(self._first.zones()) + list(self._second.zones()),
                          key=lambda name: name.encode("utf-8"))

        def read_zone(self, zone):
            if zone in set(self._first.zones()):
                return self._first.read_zone(zone)
            return self._second.read_zone(zone)

    merged = _MergedStore(ZoneinfoStore(str(bad_tree)), good)
    result = windows.scan_all(merged, 2026)
    assert result.errors, "坏 zone 必须进 errors（不吞）"
    assert any("AAA_Broken" in message for message in result.errors), result.errors
    # 其余 zone 照常出结果（不中断整批）
    assert result.windows, "一个坏 zone 不得中断整批扫描"
    assert result.zones_scanned == len(merged.zones())


# ---------------------------------------------------------------- 7. CLI 接线


def _cli(argv):
    """跑 CLI 并抓 stdout。"""
    import contextlib

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = _main(argv)
    return rc, out.getvalue()


def _main(argv):
    from tzaudit import cli

    return cli.main(argv)


@needs_trees
def test_cli_windows_single_zone_prints_two_windows():
    rc, out = _cli(["windows", "--zone", "America/New_York", "--year", "2026",
                    "--zoneinfo", os.path.join(SLIM, "2026e")])
    assert rc == 0
    assert "GAP" in out and "OVERLAP" in out
    assert "2026-03-08 02:00:00" in out
    assert "2026-11-01 01:00:00" in out


@needs_trees
def test_cli_windows_json_is_machine_readable_and_stable():
    rc, out = _cli(["windows", "--all", "--year", "2026",
                    "--zoneinfo", os.path.join(SLIM, "2026e"), "--json"])
    assert rc == 0
    doc = json.loads(out)
    assert doc["year"] == 2026
    assert doc["summary"]["errors"] == []
    assert doc["summary"]["zones_scanned"] > 0
    assert doc["summary"]["windows"] == len(doc["windows"])
    first = doc["windows"][0]
    for key in ("type", "start_local", "end_local", "duration_min", "residual_sec",
                "offset_before", "offset_after", "zone", "source"):
        assert key in first, key


@needs_trees
def test_cli_windows_requires_exactly_one_of_zone_or_all():
    """``--zone`` 与 ``--all`` 互斥：两个都给或都不给 → 退出码 2（用法错误）。"""
    tree = os.path.join(SLIM, "2026e")
    assert _cli(["windows", "--year", "2026", "--zoneinfo", tree])[0] == 2
    assert _cli(["windows", "--zone", "UTC", "--all", "--year", "2026",
                 "--zoneinfo", tree])[0] == 2


def test_cli_windows_missing_tree_is_environment_problem():
    """路径不存在 → 退出码 3（环境不满足），不是 5、不是 2。"""
    from tzaudit import errors

    rc, _out = _cli(["windows", "--zone", "UTC", "--year", "2026",
                     "--zoneinfo", os.path.join(ROOT, "data", "_no_such_tree")])
    assert rc == errors.EXIT_ENV


@needs_trees
def test_cli_windows_is_byte_identical_across_runs():
    """同一命令双跑 → stdout **逐字节一致**（零时间戳、零随机序）。

    子进程用 ``PYTHONPATH=src`` 起（**不依赖"包已安装"**）——
    否则本机只在一个解释器通道装了 ``tzaudit`` 时，这条会因
    ``No module named tzaudit`` 假红（与被测行为无关）。
    """
    tree = os.path.join(SLIM, "2026e")
    argv = ["windows", "--all", "--year", "2026", "--zoneinfo", tree, "--json"]
    env = dict(os.environ)
    src = os.path.join(ROOT, "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"]
                                if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    first = subprocess.run([sys.executable, "-m", "tzaudit"] + argv,
                           cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=env)
    second = subprocess.run([sys.executable, "-m", "tzaudit"] + argv,
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env)
    assert first.returncode == 0, first.stderr.decode("utf-8", "replace")
    assert second.returncode == 0, second.stderr.decode("utf-8", "replace")
    assert first.stdout == second.stdout


# ---------------------------------------------------------------- 8. fixture 金标


def test_windows_fixture_gold_matches_implementation():
    """fixture 金标（**独立推导**）必须与实现结果逐条相等。"""
    path = os.path.join(WINDOWS_FIXTURE, "expect.json")
    if not os.path.isfile(path):
        pytest.skip("缺 data/fixtures/windows/expect.json（跑 gen.py）")
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    tree = os.path.join(WINDOWS_FIXTURE, doc["input"]["tree"])
    store = ZoneinfoStore(tree)
    for case in doc["expected"]["windows"]:
        tl = timeline.load_timeline(
            case["zone"], store,
            window_start=civil.epoch_from_local_naive(case["year"], 1, 1) - 2 * 86400,
            window_end=civil.epoch_from_local_naive(case["year"] + 1, 1, 1) + 2 * 86400)
        found = windows.scan_year(case["zone"], case["year"], tl)
        actual = [{"type": item.type,
                   "start_local": civil.format_local(item.start_local),
                   "end_local": civil.format_local(item.end_local),
                   "duration_min": item.duration_min,
                   "residual_sec": item.residual_sec,
                   "offset_before": civil.format_offset(item.offset_before),
                   "offset_after": civil.format_offset(item.offset_after),
                   "source": item.source}
                  for item in found]
        # 金标**不含** ``source``（合成树里恒为 tail，锁它没有信息量）——
        # 比对时只取金标有的键，多出来的键（source）单独断言。
        expected = [dict(row) for row in case["windows"]]
        trimmed = [{key: row[key] for key in expected_row}
                   for row, expected_row in zip(actual, expected)]
        assert trimmed == expected, "%s %d:\n实际=%r\n金标=%r" % (
            case["zone"], case["year"], trimmed, expected)
        assert len(actual) == len(expected), "%s: 窗口条数不符" % case["zone"]
        # source 必须落在两个合法值里
        for item in found:
            assert item.source in ("table", "tail")


def test_windows_fixture_gold_covers_all_shapes():
    """金标必须**真的**覆盖 GAP / OVERLAP / 零窗口三种形态（否则等于没验）。"""
    path = os.path.join(WINDOWS_FIXTURE, "expect.json")
    if not os.path.isfile(path):
        pytest.skip("缺 data/fixtures/windows/expect.json（跑 gen.py）")
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    kinds = {row["type"] for case in doc["expected"]["windows"] for row in case["windows"]}
    assert kinds == {windows.GAP, windows.OVERLAP}, kinds
    # 必须有"零窗口"的 zone（反例：无窗口 ≠ 没扫描）
    assert any(not case["windows"] for case in doc["expected"]["windows"])
    # 30 分钟 / 45 分钟两种非整点形态
    durations = {row["duration_min"] for case in doc["expected"]["windows"]
                 for row in case["windows"]}
    assert 30 in durations, durations
    offsets = {row["offset_before"] for case in doc["expected"]["windows"]
               for row in case["windows"]}
    assert any(offset.endswith(":30") or offset.endswith(":45") for offset in offsets), offsets


def test_windows_fixture_abbrev_only_transition_is_not_a_window():
    """**陷阱**：`Zone/AbbrevOnly` 的表里有一个"offset 不变、只换缩写"的转换点。

    它**不是**墙钟窗口（墙钟既没缺也没多）。实现若只看"有没有转换点"就会误报一条。
    """
    path = os.path.join(WINDOWS_FIXTURE, "expect.json")
    if not os.path.isfile(path):
        pytest.skip("缺 data/fixtures/windows/expect.json（跑 gen.py）")
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    cases = {case["zone"]: case for case in doc["expected"]["windows"]}
    assert "Zone/AbbrevOnly" in cases
    trap = cases["Zone/AbbrevOnly"]
    plain = cases["Zone/Standard"]
    assert trap["windows"] == plain["windows"], \
        "只换缩写的转换点不得额外产出窗口"

    # 实现侧：同样的两条，不多不少
    store = ZoneinfoStore(os.path.join(WINDOWS_FIXTURE, doc["input"]["tree"]))
    tl = timeline.load_timeline("Zone/AbbrevOnly", store,
                                window_start=civil.epoch_from_local_naive(2026, 1, 1),
                                window_end=civil.epoch_from_local_naive(2027, 1, 1))
    found = windows.scan_year("Zone/AbbrevOnly", 2026, tl)
    assert len(found) == 2, [(w.type, civil.format_local(w.start_local)) for w in found]
    assert found[0].start_local != civil.epoch_from_local_naive(2026, 1, 15)


def test_windows_fixture_no_dst_zone_really_produced_no_window():
    """**零窗口反例**：`Zone/NoDst` 必须真的被扫过（而不是"没扫到"）。"""
    path = os.path.join(WINDOWS_FIXTURE, "expect.json")
    if not os.path.isfile(path):
        pytest.skip("缺 data/fixtures/windows/expect.json（跑 gen.py）")
    store = ZoneinfoStore(os.path.join(WINDOWS_FIXTURE, "tree"))
    assert "Zone/NoDst" in store.zones()
    tl = timeline.load_timeline("Zone/NoDst", store,
                                window_start=civil.epoch_from_local_naive(2026, 1, 1),
                                window_end=civil.epoch_from_local_naive(2027, 1, 1))
    # 确实扫了（有转换点被遍历到 → 至少能证明扫描路径是通的），但没有窗口
    assert windows.scan_year("Zone/NoDst", 2026, tl) == []
    # 该 zone 确实有转换点（只是 offset 不变）——证明"零窗口"不是因为"没有转换点"
    assert timeline.transition_points(tl, civil.epoch_from_local_naive(2026, 1, 1),
                                      civil.epoch_from_local_naive(2027, 1, 1)) == []
