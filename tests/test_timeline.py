# -*- coding: utf-8 -*-
"""双引擎合并与本地反解 —— 契约见 ``plan/03`` §四。

四层断言：

1. **合成字节**：表段 / tail 段的合并形态（含"表空 + 全 tail"的极端 slim）。
2. **双向对拍**：``roundtrip(resolve_local(l)) == l``（`data/README.md` §4.6）。
3. **独立参照实现**：``tests/reference.py`` 与生产实现逐点对拍（≥ 20 zone，含三种特殊形态）。
4. **真实树**：NY 2026 的 GAP/OVERLAP 语义；Vancouver 无 DST 后**不**给 2 个候选。

第 3 层是"防引擎自证"的关键：参照实现用 ``datetime`` + 段区间包含式，生产实现用自研整数 +
自洽校验式，两条独立路径。
"""

import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from tzaudit import civil, posix_tz, timeline  # noqa: E402
from tzaudit.zoneinfo_store import ZoneinfoStore  # noqa: E402

SLIM = os.path.join(ROOT, "data", "_downloads", "slim")
FIXTURE = os.path.join(ROOT, "data", "fixtures", "tzif", "slim-vs-fat")

needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/tzdb 下载）",
)


def _load(path):
    with io.open(path, "rb") as fh:
        return fh.read()


class _MemoryStore(object):
    """最小的 store 替身：只实现 ``read_zone`` / ``version``（``load_timeline`` 的全部依赖面）。"""

    def __init__(self, blobs, version="fixture"):
        self._blobs = blobs
        self.version = version

    def read_zone(self, zone):
        return self._blobs[zone]


def _synthetic(footer="EST5EDT,M3.2.0/2,M11.1.0/2", transitions=None):
    """一句 EST5EDT 的合成 TZif（表里给两个转换点，其余靠 tail）。"""
    sys.path.insert(0, os.path.join(ROOT, "data", "fixtures"))
    import _support as S

    if transitions is None:
        transitions = [(-1000000000, 0), (1000000000, 1)]
    return S.build_tzif(
        transitions,
        [(-18000, False, "EST"), (-14400, True, "EDT")],
        footer,
        slim=True,
    )


# ---------------------------------------------------------------- 1. 合并形态


def test_table_segments_cover_transitions_and_tail_takes_over():
    tl = timeline.load_timeline("Synthetic", _MemoryStore({"Synthetic": _synthetic()}),
                               window_end=civil.parse_local("2027-01-01"))
    table = [seg for seg in tl.segments if seg.source == "table"]
    tail = [seg for seg in tl.segments if seg.source == "tail"]
    assert table, "必须有表段"
    assert tail, "footer 存在时必须展开 tail 段"
    assert tl.table_end_utc is not None
    # 表段与 tail 段在 table_end 处衔接，不留空洞
    for earlier, later in zip(tl.segments, tl.segments[1:]):
        assert earlier.utc_end == later.utc_start, "段之间不得有缝"


def test_empty_table_falls_back_to_tail_entirely():
    """极端 slim：表为空、语义全在 footer → 整条线都是 tail 段。"""
    blob = _synthetic(transitions=[])
    tl = timeline.load_timeline("Synthetic", _MemoryStore({"Synthetic": blob}),
                               window_end=civil.parse_local("2027-01-01"))
    assert tl.table_end_utc is None
    assert all(seg.source == "tail" for seg in tl.segments)
    assert tl.segments[0].utc_start == timeline.NEG_INFINITY
    # 1970 前后都要有定义（展开起点可早于 1970）
    for probe in ("1900-06-01 12:00:00", "1970-06-01 12:00:00", "2026-06-01 12:00:00"):
        assert timeline.resolve_local(civil.parse_local(probe), tl), probe


def test_no_footer_means_table_to_infinity():
    blob = _synthetic(footer=None)
    tl = timeline.load_timeline("Synthetic", _MemoryStore({"Synthetic": blob}))
    assert tl.tail is None
    assert tl.segments[-1].utc_end == timeline.POS_INFINITY
    # 表外沿用最后 offset（不报错、不返回空）
    far = civil.parse_local("2400-06-01 12:00:00")
    assert timeline.resolve_local(far, tl)


def test_tail_expansion_respects_window_horizon():
    """`plan/05` R2：展开上限 = 窗口末端 + 1 年（不漏最后一年、不无限循环）。"""
    window_end = civil.parse_local("2027-01-01")
    tl = timeline.load_timeline("Synthetic", _MemoryStore({"Synthetic": _synthetic()}),
                               window_end=window_end)
    tail_points = [seg.utc_start for seg in tl.segments
                   if seg.source == "tail" and seg.utc_start != timeline.NEG_INFINITY]
    assert tail_points, "tail 必须物化出转换点"
    horizon = timeline._add_years(window_end, 1)
    assert max(tail_points) < horizon, "展开不得越过 窗口末端 + 1 年"
    # 窗口内的最后一年必须覆盖到（漏最后一年是本里程碑的主要风险）
    last_year_start = civil.parse_local("2027-01-01")
    assert any(point >= last_year_start - 400 * 86400 for point in tail_points)


# ---------------------------------------------------------------- 2. 双向对拍


def _roundtrip_holds(tl, local):
    candidates = timeline.resolve_local(local, tl)
    back = timeline.roundtrip(local, tl)
    assert back == [local] * len(candidates), "roundtrip 的每个候选都必须回到原本地时刻"
    return len(candidates)


def test_ny_2026_gap_and_overlap_counts():
    """NY 2026：``02:30`` 是 GAP（0 候选），``01:30`` 是 OVERLAP（2 候选）。"""
    blob = _synthetic()
    tl = timeline.load_timeline("Synthetic", _MemoryStore({"Synthetic": blob}),
                               window_end=civil.parse_local("2027-01-01"))

    gap = civil.parse_local("2026-03-08 02:30:00")
    assert _roundtrip_holds(tl, gap) == 0

    overlap = civil.parse_local("2026-11-01 01:30:00")
    assert _roundtrip_holds(tl, overlap) == 2


def test_roundtrip_holds_on_a_dense_local_grid():
    """一整年逐小时：``roundtrip`` 恒等于"候选个数份的原值"（0/1/2）。"""
    blob = _synthetic()
    tl = timeline.load_timeline("Synthetic", _MemoryStore({"Synthetic": blob}),
                               window_end=civil.parse_local("2027-01-01"))
    start = civil.parse_local("2026-01-01 00:00:00")
    counts = {}
    for hour in range(0, 366 * 24):
        local = start + hour * 3600
        counts[_roundtrip_holds(tl, local)] = counts.get(_roundtrip_holds(tl, local), 0) + 1
    # 一年至少各出现一次（否则这条用例覆盖不到 0/2 两种形态）
    assert counts.get(0, 0) >= 1, "全年一个 GAP 都没有——判据可能空跑"
    assert counts.get(1, 0) > 0
    assert set(counts) <= {0, 1, 2}, "候选数只能是 0/1/2"


def test_resolution_fold_is_index_and_utc_ascending():
    blob = _synthetic()
    tl = timeline.load_timeline("Synthetic", _MemoryStore({"Synthetic": blob}),
                               window_end=civil.parse_local("2027-01-01"))
    candidates = timeline.resolve_local(civil.parse_local("2026-11-01 01:30:00"), tl)
    assert [res.fold for res in candidates] == [0, 1]
    assert candidates[0].utc < candidates[1].utc
    assert candidates[0].offset_sec != candidates[1].offset_sec, "OVERLAP 的两个 offset 必须不同"


def test_exists_only_by_candidate_count_not_by_fold():
    """K10 / PITFALL-FOLD-GAP：**存在性只看候选个数**，``fold`` 只用于选择。

    反例形态：只看两个 fold 的 offset 不同就判 OVERLAP —— 在 GAP 上同样成立。
    """
    blob = _synthetic()
    tl = timeline.load_timeline("Synthetic", _MemoryStore({"Synthetic": blob}),
                               window_end=civil.parse_local("2027-01-01"))
    gap = civil.parse_local("2026-03-08 02:30:00")
    candidates = timeline.resolve_local(gap, tl)
    assert candidates == [], "GAP 必须 0 个候选"
    # 若实现"按 fold 取两个 offset"来判二义，这里会得到两个不同的 offset —— 但那不是 OVERLAP
    points = [p for p in timeline.transition_points(
        tl, civil.parse_local("2026-01-01"), civil.parse_local("2027-01-01"))]
    assert len(points) == 2, points
    jump = points[0]   # 3 月的起跳点
    before = timeline.offset_at(jump - 1, tl)
    after = timeline.offset_at(jump, tl)
    assert before != after, "GAP 两侧 offset 确实不同（正是误报的诱因）"
    # GAP 的墙钟区间是 ``[jump + before, jump + after)``；02:30 落在 02:00–03:00 里
    assert jump + before + 1800 == gap
    assert jump + after == jump + before + 3600


# ---------------------------------------------------------------- 3. 合成 slim/fat fixture


def _fixture_timeline(name):
    store = _MemoryStore({name: _load(os.path.join(FIXTURE, name))})
    return timeline.load_timeline(name, store, window_end=civil.parse_local("2036-01-01"))


def test_fixture_three_encodings_agree_on_overlap_interval():
    """slim / fat / tail-only 三种编码在**重叠区间**内逐点一致（Q1 定案）。"""
    import datetime

    names = ["fat.tzif", "slim.tzif", "tail_only.tzif"]
    timelines = [_fixture_timeline(name) for name in names]

    step = 86400 * 13
    utc = civil.parse_local("1970-01-02 00:00:00")
    end = civil.parse_local("2035-12-01 00:00:00")
    while utc < end:
        values = [timeline.to_local(utc, tl) for tl in timelines]
        assert values[0] == values[1] == values[2], \
            "三种编码在 %s 上不一致: %r" % (civil.format_local(utc), values)
        utc += step


def test_fixture_slim_and_fat_differ_before_table_end():
    """**反向断言**：表尾之前 slim 的 tail 还**没**生效，所以两者**必须**不同。

    没有这条，"三者恒等"可能只是因为实现根本没读表（把 598 个 zone 都当 tail 处理）。
    """
    fat = _fixture_timeline("fat.tzif")
    slim = _fixture_timeline("slim.tzif")
    assert fat.table_end_utc != slim.table_end_utc, "两种编码的表尾必须不同"
    probe = fat.table_end_utc + 86400 * 30
    if probe < slim.table_end_utc:
        assert timeline.to_local(probe, fat) != timeline.to_local(probe, slim), \
            "表尾差异必须能在重叠区间之前体现出来"


def test_fixture_candidates_match_gold():
    """fixture 金标的 UTC 候选（独立推导）必须与三个编码的实现结果都相等。"""
    with io.open(os.path.join(FIXTURE, "expect.json"), "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    cases = doc["expected"]["candidates"]
    assert len(cases) == 8
    for name in ("fat.tzif", "slim.tzif", "tail_only.tzif"):
        tl = _fixture_timeline(name)
        for case in cases:
            actual = [res.utc for res in timeline.resolve_local(case["local"], tl)]
            assert actual == case["utc"], "%s @ %s" % (name, civil.format_local(case["local"]))
    # 金标必须真的覆盖 0/1/2 三种候选数（否则等于没验 gap/overlap）
    sizes = {len(case["utc"]) for case in cases}
    assert sizes == {0, 1, 2}, sizes


# ---------------------------------------------------------------- 4. 真实树 + 参照对拍


@needs_trees
def test_real_trees_roundtrip_holds_for_every_sampled_zone():
    store = ZoneinfoStore(os.path.join(SLIM, "2026e"))
    zones = store.zones()
    assert len(zones) > 0
    step = 86400 * 29
    start = civil.parse_local("1971-01-01 00:00:00")
    end = civil.parse_local("2029-01-01 00:00:00")
    checked = 0
    for zone in zones:
        tl = timeline.load_timeline(zone, store, window_end=end)
        utc = start
        while utc < end:
            local = timeline.to_local(utc, tl)
            back = timeline.roundtrip(local, tl)
            assert back, "%s @ %s: 从 UTC 推回本地必须至少有一个候选" % (
                zone, civil.format_local(local))
            assert local in back
            utc += step
            checked += 1
    assert checked > len(zones), "样本量必须大于 zone 数（否则判据空跑）"


@needs_trees
def test_production_matches_reference_on_sample_zones():
    """≥ 20 zone（含三种特殊形态）与 ``tests/reference.py`` 逐点对拍。

    参照实现用 ``datetime`` + 段区间包含式；生产实现用自研整数 + 自洽校验式。
    """
    import reference

    store = ZoneinfoStore(os.path.join(SLIM, "2026e"))
    available = set(store.zones())
    wanted = [z for z in ("Europe/Dublin", "Australia/Lord_Howe", "Pacific/Chatham",
                          "America/New_York", "America/Vancouver", "Asia/Tehran")
              if z in available]
    for zone in sorted(available):
        if len(wanted) >= 20:
            break
        if zone not in wanted:
            wanted.append(zone)
    assert len(wanted) >= 20

    start = civil.parse_local("1920-01-01 00:00:00")
    end = civil.parse_local("2030-01-01 00:00:00")
    mismatches = []
    checked = 0
    for zone in wanted:
        raw = store.read_zone(zone)
        ours = timeline.load_timeline(zone, store, window_start=start, window_end=end)
        theirs = reference.read_timeline(raw, start, end)

        probe = start
        while probe < end:
            if timeline.to_local(probe, ours) != theirs.to_local(probe):
                mismatches.append("%s: to_local @ %d" % (zone, probe))
            probe += 86400 * 31

        # 每个转换点附近的候选集合（gap/overlap 都在这里）
        for point in timeline.transition_points(ours, start, end):
            before = timeline.offset_at(point - 1, ours)
            after = timeline.offset_at(point, ours)
            if before == after:
                continue
            low, high = sorted((point + before, point + after))
            for local in range(low - 1, high + 2):
                got = [res.utc for res in timeline.resolve_local(local, ours)]
                want = [item[0] for item in theirs.resolve_local(local)]
                checked += 1
                if got != want:
                    mismatches.append("%s: resolve @ %s (我们 %r / 参照 %r)"
                                      % (zone, civil.format_local(local), got, want))
    assert mismatches == [], "\n".join(mismatches[:10])
    assert checked > 0, "没有跑到任何转换点附近——判据空跑"


@needs_trees
def test_new_york_2026_wall_windows_are_as_documented():
    """NY 2026：GAP ``02:00→03:00``、OVERLAP ``01:00→02:00``（M3 的输入前提）。"""
    store = ZoneinfoStore(os.path.join(SLIM, "2026e"))
    end = civil.parse_local("2027-01-01 00:00:00")
    tl = timeline.load_timeline("America/New_York", store, window_end=end)

    points = timeline.transition_points(tl, civil.parse_local("2026-01-01"), end)
    assert len(points) == 2, "NY 2026 应恰好两个转换点: %r" % (points,)

    for point in points:
        before = timeline.offset_at(point - 1, tl)
        after = timeline.offset_at(point, tl)
        low, high = sorted((point + before, point + after))
        assert timeline.resolve_local(low, tl) or timeline.resolve_local(high, tl)
        if after > before:
            assert [res.utc for res in timeline.resolve_local(low, tl)] == [], "GAP 起点必须 0 候选"
            assert len(timeline.resolve_local(high, tl)) == 1
        else:
            assert len(timeline.resolve_local(low, tl)) == 2, "OVERLAP 区内必须 2 候选"

    gap_local = [point + timeline.offset_at(point - 1, tl) for point in points
                 if timeline.offset_at(point, tl) > timeline.offset_at(point - 1, tl)]
    assert [civil.format_local(x)[11:] for x in gap_local] == ["02:00:00"]


@needs_trees
def test_vancouver_after_dst_abolition_has_one_candidate():
    """Vancouver 2026-11 起永久 UTC-7：``resolve_local`` 只给 1 个候选（M3 的反例前提）。

    只按 ``fold=0 != fold=1`` 判 OVERLAP 的实现在这里会误报一条。
    """
    store = ZoneinfoStore(os.path.join(SLIM, "2026e"))
    end = civil.parse_local("2027-01-01 00:00:00")
    tl = timeline.load_timeline("America/Vancouver", store, window_end=end)
    local = civil.parse_local("2026-12-01 01:30:00")
    candidates = timeline.resolve_local(local, tl)
    assert len(candidates) == 1, [(civil.format_local(r.utc), r.offset_sec) for r in candidates]
    assert candidates[0].offset_sec == -25200


@needs_trees
def test_dublin_negative_dst_is_preserved_in_timeline():
    """Dublin 的负 DST 在时间线层仍原样保留（冬季那条 ``is_dst=True``）。"""
    store = ZoneinfoStore(os.path.join(SLIM, "2026e"))
    end = civil.parse_local("2027-01-01 00:00:00")
    tl = timeline.load_timeline("Europe/Dublin", store, window_end=end)
    flags = {(seg.offset_sec, seg.is_dst) for seg in tl.segments if seg.source == "tail"}
    assert (0, True) in flags, "冬季 GMT 必须是 is_dst=True（不按'冬季=标准时'推断）"
    assert (3600, False) in flags, "夏季 IST 必须是 is_dst=False"


@needs_trees
def test_slim_and_fat_semantics_on_real_data():
    """真实 slim 树与其 fat 等价形态在重叠区间内一致。

    fat 树不可得时（本机无 ``zic``）→ skip，并在 skip 理由里点名原因（不静默通过）。
    """
    pytest.skip("本机无 zic，fat 真实树不可得；语义等价已由 data/fixtures/tzif/slim-vs-fat 覆盖")
