# -*- coding: utf-8 -*-
"""M5 · 清单审计 `audit`（`plan/03` §七 的五条测试点 + 顺序变异 + CLI）。

分五组：

1. **契约**：`Row` 六字段与 §七 一致；`STATUS_ORDER` 固定；行序 == 输入序。
2. **四类各一条**（真实树 / fixture）：`GAP` / `OVERLAP` / `VERSION_CHANGED` / `OK`。
3. **BC 场景**：同一 UTC 在两版本下两个墙钟（`data/fixtures/audit/bc-scenario/`）。
4. **`--daily` 等价** + `INVALID` 不静默跳过 + 顺序变异自证。
5. **CLI 与退出码**：`--daily` 缺年退 2；坏行退 4；缺 `provenance.json` 退 3；
   双跑逐字节一致。
"""

from __future__ import print_function

import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

FIXTURE = os.path.join(ROOT, "data", "fixtures", "audit", "bc-scenario")
SLIM = os.path.join(ROOT, "data", "_downloads", "slim")

from tzaudit import audit, civil, cli, errors  # noqa: E402

needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）",
)


# ---------------------------------------------------------------- 辅助


def _store(path):
    from tzaudit.zoneinfo_store import ZoneinfoStore

    return ZoneinfoStore(path)


def _fixture_stores():
    return (_store(os.path.join(FIXTURE, "old")), _store(os.path.join(FIXTURE, "new")))


def _fixture_expect():
    with io.open(os.path.join(FIXTURE, "expect.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _fixture_times_text():
    with io.open(os.path.join(FIXTURE, "times.txt"), "r", encoding="utf-8") as fh:
        return fh.read()


def _audit_fixture():
    rows = audit.parse_times(_fixture_times_text())
    return audit.audit_rows(rows, _fixture_expect()["input"]["zone"],
                            versions=_fixture_stores())


def _real(version):
    return _store(os.path.join(SLIM, version))


# ---------------------------------------------------------------- 1. 契约


def test_row_fields_match_plan_section_seven():
    """`Row` 的六字段与 `plan/03` §七 逐字对应（改字段名即契约变更）。"""
    assert set(audit.Row.__slots__) == {"id", "local", "status", "utc_candidates",
                                        "note", "invalid_reason"}


def test_status_order_is_frozen():
    """判定顺序固定 `INVALID → GAP → OVERLAP → VERSION_CHANGED → OK`。"""
    assert audit.STATUS_ORDER == ("INVALID", "GAP", "OVERLAP", "VERSION_CHANGED", "OK")
    # 五个状态常量与顺序元组一一对应（漏一个就是"判定表少一条"）
    assert set(audit.STATUS_ORDER) == {audit.INVALID, audit.GAP, audit.OVERLAP,
                                       audit.VERSION_CHANGED, audit.OK}


def test_output_row_order_equals_input_row_order():
    """**行序保持输入序**（`plan/03` §七）：打乱输入后，输出仍是那个顺序。"""
    local_lines = [
        "line-a,2026-06-01 12:00",
        "line-b,2026-03-08 02:30",
        "line-c,2026-11-01 01:30",
        "line-d,2025-01-15 08:00",
    ]
    shuffled = [local_lines[2], local_lines[0], local_lines[3], local_lines[1]]
    rows = audit.parse_times("\n".join(shuffled) + "\n")
    result = audit.audit_rows(rows, "Zone/Bc",
                              versions=_fixture_stores())
    assert [row.id for row in result.rows] == [line.split(",")[0] for line in shuffled]


def test_same_local_twice_yields_two_ordered_candidates():
    """同一时刻的两个候选按 **UTC 升序**（`plan/03` §七）。"""
    rows = audit.parse_times("x,2026-11-01 01:30\n")
    result = audit.audit_rows(rows, "Zone/Bc", versions=_fixture_stores())
    row = result.rows[0]
    assert row.status == audit.OVERLAP
    assert len(row.utc_candidates) == 2
    assert row.utc_candidates == sorted(row.utc_candidates)


# ---------------------------------------------------------------- 2. 四类各一条


@needs_trees
def test_real_new_york_gap():
    """真实树：`2026-03-08 02:30` NY → `GAP`（0 个候选）。"""
    rows = audit.parse_times("case-001,2026-03-08 02:30\n")
    result = audit.audit_rows(rows, "America/New_York", versions=[_real("2026e")])
    row = result.rows[0]
    assert row.status == audit.GAP
    assert row.utc_candidates == []
    assert row.invalid_reason == ""


@needs_trees
def test_real_new_york_overlap():
    """真实树：`2026-11-01 01:30` NY → `OVERLAP`（2 个候选，偏移差 3600s）。"""
    rows = audit.parse_times("case-002,2026-11-01 01:30\n")
    result = audit.audit_rows(rows, "America/New_York", versions=[_real("2026e")])
    row = result.rows[0]
    assert row.status == audit.OVERLAP
    assert len(row.utc_candidates) == 2
    assert abs(row.utc_candidates[1] - row.utc_candidates[0]) == 3600
    assert "3600s" in row.note


@needs_trees
def test_real_new_york_ok():
    """真实树：夏天正午 → `OK`（唯一候选，且无 note）。"""
    rows = audit.parse_times("case-003,2026-06-01 12:00\n")
    result = audit.audit_rows(rows, "America/New_York", versions=[_real("2026e")])
    row = result.rows[0]
    assert row.status == audit.OK
    assert len(row.utc_candidates) == 1
    assert row.note == ""


def test_version_changed_requires_two_trees():
    """`VERSION_CHANGED` **只在给了两棵树时**可能成立（`plan/03` §七）。"""
    rows = audit.parse_times("bc-version-changed,2026-12-15 12:00\n")
    single = audit.audit_rows(rows, "Zone/Bc", versions=[_fixture_stores()[0]])
    assert single.rows[0].status == audit.OK, "单树模式下不可能出现 VERSION_CHANGED"

    double = audit.audit_rows(rows, "Zone/Bc", versions=_fixture_stores())
    assert double.rows[0].status == audit.VERSION_CHANGED


# ---------------------------------------------------------------- 3. BC 场景


def test_bc_fixture_matches_expected_rows():
    """`data/fixtures/audit/bc-scenario/` 的四条期望逐条比对（status + 候选 UTC）。"""
    expect = _fixture_expect()["expected"]
    result = _audit_fixture()

    assert [row.id for row in result.rows] == [item["id"] for item in expect["rows"]]
    for row, want in zip(result.rows, expect["rows"]):
        assert row.status == want["status"], "id=%s" % row.id
        assert list(row.utc_candidates) == list(want["utc_candidates"]), "id=%s" % row.id


def test_bc_same_utc_maps_to_two_wall_clocks():
    """**BC 场景的核心断言**：同一 UTC 在两版本下对应两个墙钟（相差一小时）。

    这是 Cal.com #30104 的复现口径——不是"同一本地时刻两个 UTC"，
    而是反过来看："19:00Z 在旧树是 11:00、在新树是 12:00"。
    """
    old_store, new_store = _fixture_stores()
    from tzaudit import timeline as timeline_mod
    from tzaudit.timeline import load_timeline

    utc = civil.epoch_from_local_naive(2026, 12, 15, 19, 0, 0)
    old_tl = load_timeline("Zone/Bc", old_store,
                           window_start=utc - 2 * 86400, window_end=utc + 2 * 86400)
    new_tl = load_timeline("Zone/Bc", new_store,
                           window_start=utc - 2 * 86400, window_end=utc + 2 * 86400)
    old_wall = timeline_mod.to_local(utc, old_tl)
    new_wall = timeline_mod.to_local(utc, new_tl)

    assert new_wall - old_wall == 3600, (
        "两版本应对同一 UTC 给出相差一小时的墙钟：%s vs %s"
        % (civil.format_local(old_wall), civil.format_local(new_wall)))
    assert civil.format_local(old_wall) == "2026-12-15 11:00:00"
    assert civil.format_local(new_wall) == "2026-12-15 12:00:00"


def test_bc_expected_versions_carry_both_sides():
    """期望里两侧候选都得写出（防"只记主树、忘了对照"的空心金标）。"""
    expect = _fixture_expect()
    for item in expect["expected"]["rows"]:
        assert set(item["versions"]) == set(expect["input"]["versions"].values()), item["id"]
        for side in item["versions"].values():
            assert isinstance(side, list)


# ---------------------------------------------------------------- 4. daily / INVALID / 顺序变异


@needs_trees
def test_daily_expansion_matches_equivalent_list():
    """`--daily 02:30 --year 2026` 与等价清单输出**逐字节一致**（除 id 前缀）。

    2026 是平年 → 365 条。用 NY 这棵树跑，两条路径的判定必须完全相同。
    """
    store = _real("2026e")
    daily_rows = audit.expand_daily("02:30", 2026)
    assert len(daily_rows) == 365, "2026 是平年，应展开 365 条"

    # 等价清单：把同一天的同一时刻写成文本再解析
    lines = ["%s,%s" % (item.id, civil.format_local(item.local)) for item in daily_rows]
    list_rows = audit.parse_times("\n".join(lines) + "\n")
    assert len(list_rows) == 365

    from_daily = audit.audit_rows(daily_rows, "America/New_York", versions=[store])
    from_list = audit.audit_rows(list_rows, "America/New_York", versions=[store])

    def _strip(rows):
        return [(row.id[len(audit.DAILY_ID_PREFIX):], row.local, row.status,
                 tuple(row.utc_candidates), row.note) for row in rows]

    assert _strip(from_daily.rows) == _strip(from_list.rows), (
        "--daily 与等价清单的判定不一致（除 id 前缀外应逐条相同）")


def test_daily_requires_year_and_does_not_default_to_now():
    """`--daily` 缺 `--year` → **退 2**（本项目不读时钟，不默认当前年）。"""
    with pytest.raises(errors.UsageError):
        audit.expand_daily("02:30", None)


@pytest.mark.parametrize("bad", ["25:00", "12:60", "not-a-clock", "*/5 * * * *", "12"])
def test_daily_rejects_bad_clock(bad):
    """非法 `--daily`（含 cron 表达式）→ 用法错误，不静默接受。"""
    with pytest.raises(errors.UsageError):
        audit.expand_daily(bad, 2026)


def test_invalid_rows_are_not_silently_dropped():
    """坏行（缺列 / 时间非法 / 空行）→ `INVALID` + 计数，**其余行照常判定**。"""
    text = (
        "good-1,2026-07-15 12:00\n"
        "a,b,c\n"                       # 列数不是 2
        ",2026-07-15 12:00\n"           # 缺 id
        "bad-time,2026-13-01 00:00\n"   # 月越界
        "\n"                             # 空行
        "good-2,2026-12-15 12:00\n"
    )
    rows = audit.parse_times(text)
    result = audit.audit_rows(rows, "Zone/Bc", versions=_fixture_stores())

    assert result.summary["invalid"] == 4, result.summary
    assert result.summary["rows"] == 6
    # 行序与输入序一致，坏行留在原地（不静默跳过）
    assert [row.status for row in result.rows] == [
        "OK", "INVALID", "INVALID", "INVALID", "INVALID", "VERSION_CHANGED"]
    # 其余行照常判定：good-2 仍然拿到 VERSION_CHANGED
    assert result.rows[-1].id == "good-2"
    assert result.rows[-1].status == "VERSION_CHANGED"
    # 坏行要能指出原因
    assert all(row.invalid_reason for row in result.rows if row.status == "INVALID")


def test_mutation_reordering_lets_version_changed_steal_gap():
    """**顺序变异自证**：把 `VERSION_CHANGED` 提到 `GAP` 之前 → `bc-gap` 翻成 VERSION_CHANGED。

    这是"判定顺序是判据的一部分"唯一的真锚点：`bc-gap` 在旧树是 GAP、在新树存在，
    两条判据同时成立，只有顺序能决定结果。还原后必须回到 GAP。
    """
    rows = audit.parse_times("bc-gap,2026-03-08 02:30\n")
    stores = _fixture_stores()

    assert audit.audit_rows(rows, "Zone/Bc", versions=stores).rows[0].status == audit.GAP

    original = audit.STATUS_ORDER
    try:
        audit.STATUS_ORDER = (audit.INVALID, audit.VERSION_CHANGED,
                              audit.GAP, audit.OVERLAP, audit.OK)
        flipped = audit.audit_rows(rows, "Zone/Bc", versions=stores).rows[0].status
        assert flipped == audit.VERSION_CHANGED, (
            "调换顺序后 bc-gap 应翻成 VERSION_CHANGED —— 说明顺序没被判据锚住")
    finally:
        audit.STATUS_ORDER = original

    assert audit.audit_rows(rows, "Zone/Bc", versions=stores).rows[0].status == audit.GAP


def test_invalid_is_decided_before_gap():
    """`INVALID` 排第一：坏行即使本地时刻能落在 GAP 段，也必须是 `INVALID`。"""
    rows = audit.parse_times("bad,2026-03-08 02:30:00junk\n")
    result = audit.audit_rows(rows, "America/New_York", versions=[_real("2026e")] if
                              os.path.isdir(SLIM) else [_fixture_stores()[0]])
    assert result.rows[0].status == audit.INVALID


# ---------------------------------------------------------------- 5. CLI / 退出码 / 确定性


def test_cli_audit_exit_0_on_fixture():
    rc = cli.main(["audit", "--times", os.path.join(FIXTURE, "times.txt"),
                   "--zone", "Zone/Bc",
                   "--version", "%s,%s" % (os.path.join(FIXTURE, "old"),
                                           os.path.join(FIXTURE, "new"))])
    assert rc == errors.EXIT_OK


def test_cli_audit_json_deterministic_and_timestamp_free(capsys):
    """`--json` 无时间戳；同一输入双跑**逐字节一致**（K5）。"""
    argv = ["audit", "--times", os.path.join(FIXTURE, "times.txt"),
            "--zone", "Zone/Bc",
            "--version", "%s,%s" % (os.path.join(FIXTURE, "old"),
                                    os.path.join(FIXTURE, "new")),
            "--json"]
    assert cli.main(argv) == errors.EXIT_OK
    first = capsys.readouterr().out
    assert cli.main(argv) == errors.EXIT_OK
    second = capsys.readouterr().out

    assert first == second, "同一输入双跑不一致（可能引入了时间戳或集合序）"
    doc = json.loads(first)
    assert set(doc) == {"rows", "summary"}
    for item in doc["rows"]:
        assert set(item) == {"id", "local", "status", "utc_candidates",
                             "note", "invalid_reason"}
    for key in ("generated_at", "timestamp", "runtime"):
        assert key not in first


def test_cli_audit_bad_rows_exit_4(tmp_path):
    """坏行 → 结果照常输出，但整体**退 4**（`data/README.md` §4.4）。"""
    path = tmp_path / "times.txt"
    path.write_text("good,2026-07-15 12:00\nbad,2026-13-01 00:00\n", encoding="utf-8")
    rc = cli.main(["audit", "--times", str(path), "--zone", "Zone/Bc",
                   "--version", "%s,%s" % (os.path.join(FIXTURE, "old"),
                                           os.path.join(FIXTURE, "new"))])
    assert rc == errors.EXIT_INVALID_INPUT


def test_cli_audit_daily_without_year_returns_2():
    """`--daily` 缺 `--year` → 退 2（不默认当前年）。"""
    rc = cli.main(["audit", "--daily", "02:30", "--zone", "Zone/Bc",
                   "--version", "%s,%s" % (os.path.join(FIXTURE, "old"),
                                           os.path.join(FIXTURE, "new"))])
    assert rc == errors.EXIT_USAGE


def test_cli_audit_times_and_daily_are_mutually_exclusive():
    rc = cli.main(["audit", "--daily", "02:30", "--year", "2026",
                   "--times", os.path.join(FIXTURE, "times.txt"),
                   "--zone", "Zone/Bc",
                   "--version", "%s,%s" % (os.path.join(FIXTURE, "old"),
                                           os.path.join(FIXTURE, "new"))])
    assert rc == errors.EXIT_USAGE


def test_cli_audit_requires_zone():
    rc = cli.main(["audit", "--times", os.path.join(FIXTURE, "times.txt"),
                   "--version", "%s,%s" % (os.path.join(FIXTURE, "old"),
                                           os.path.join(FIXTURE, "new"))])
    assert rc == errors.EXIT_USAGE


def test_cli_audit_version_requires_provenance(tmp_path):
    """`--version A,B` 的目录**必须带 provenance.json**，否则退 3（Q4 / K16）。"""
    bare = tmp_path / "bare"
    (bare / "Zone").mkdir(parents=True)
    (bare / "Zone" / "Bc").write_bytes(
        open(os.path.join(FIXTURE, "old", "Zone", "Bc"), "rb").read())
    rc = cli.main(["audit", "--times", os.path.join(FIXTURE, "times.txt"),
                   "--zone", "Zone/Bc",
                   "--version", "%s,%s" % (str(bare), os.path.join(FIXTURE, "new"))])
    assert rc == errors.EXIT_ENV


def test_cli_audit_version_takes_exactly_two_dirs():
    rc = cli.main(["audit", "--times", os.path.join(FIXTURE, "times.txt"),
                   "--zone", "Zone/Bc", "--version", os.path.join(FIXTURE, "old")])
    assert rc == errors.EXIT_USAGE


def test_cli_audit_missing_zone_in_tree_returns_3(tmp_path):
    rc = cli.main(["audit", "--times", os.path.join(FIXTURE, "times.txt"),
                   "--zone", "No/Such_Zone",
                   "--version", "%s,%s" % (os.path.join(FIXTURE, "old"),
                                           os.path.join(FIXTURE, "new"))])
    assert rc == errors.EXIT_ENV


def test_fixture_generator_check_passes():
    """`gen.py --check` 两层断言全过（形态 + 逐字节）。"""
    import subprocess

    script = os.path.join(FIXTURE, "gen.py")
    proc = subprocess.Popen([sys.executable, script, "--check"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0].decode("utf-8", "replace")
    assert proc.returncode == 0, out
    assert "逐字节一致" in out, out
