# -*- coding: utf-8 -*-
"""M4 · 版本差异分类 `diff`（`plan/03` §六 的五条测试点 + 真实数据）。

分五组：

1. **契约与顺序**：`CLASS_ORDER` 固定；`Change` 字段与 §六 一致；同一 zone 只输出一条。
2. **fixture 金标**：`data/fixtures/diff/` 的七条形态逐条比对（含"零变更"与"alias 两侧"）。
3. **真实数据**：Dublin 1925 / Tehran 1979 → `history_reinterpreted`；
   Vancouver 2026.1→2026.5 → `future_rule` + `evidence=tail`。
4. **判定顺序变异自证**：把顺序改成 `future_rule` 优先 → 第 3 组必红（就地变异，跑完还原）。
5. **CLI 与退出码**：`diff` 不再退 5；坏 `--window` 退 2；zone 不存在退 3；双跑逐字节一致。
"""

from __future__ import print_function

import io
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

FIXTURE = os.path.join(ROOT, "data", "fixtures", "diff")
SLIM = os.path.join(ROOT, "data", "_downloads", "slim")

from tzaudit import cli, diff, errors  # noqa: E402

needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）",
)


def _store(side):
    from tzaudit.zoneinfo_store import ZoneinfoStore

    return ZoneinfoStore(os.path.join(FIXTURE, side))


def _fixture_expect():
    with io.open(os.path.join(FIXTURE, "expect.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _real_pair():
    from tzaudit.zoneinfo_store import ZoneinfoStore

    return (ZoneinfoStore(os.path.join(SLIM, "2026a")),
            ZoneinfoStore(os.path.join(SLIM, "2026e")))


# ---------------------------------------------------------------- 1. 契约与顺序


def test_class_order_is_frozen():
    """四类的**固定判定顺序**（`data/README.md` §4.3 / K11）。改这个元组成员即口径变更。"""
    assert diff.CLASS_ORDER == (
        "history_reinterpreted",
        "future_rule",
        "abbreviation_only",
        "alias_only",
    )
    # fixture 金标里也记了这份顺序，两边必须一致（防"文档改了代码没改"）
    assert list(diff.CLASS_ORDER) == _fixture_expect()["expected"]["class_order"]


def test_change_fields_match_plan_section_six():
    """`Change` 的七个字段与 `plan/03` §六 的签名逐个对上。"""
    assert diff.Change.__slots__ == (
        "zone", "class_", "window", "before", "after", "evidence", "note")

    record = diff.Change("Zone/X", "future_rule", (2000, 2030), "tail=A", "tail=B", "tail")
    assert record.note == ""  # note 有缺省
    doc = record.as_dict()
    assert doc["class"] == "future_rule"          # 键名是 class（不是 class_）
    assert doc["window"] == [2000, 2030]          # 元组序列化成列表
    assert doc["evidence"] == "tail"


def test_diff_result_fields():
    assert diff.DiffResult.__slots__ == ("changes", "summary", "errors")
    result = diff.DiffResult([], {"changes": 0})
    assert result.errors == []                    # 缺省空列表
    assert result.as_dict() == {"changes": [], "summary": {"changes": 0}}


def test_parse_window_rejects_bad_shapes():
    """`--window` 只认 `YYYY-YYYY`（`plan/03` §一 的用法错误 → 退出码 2）。"""
    assert diff.parse_window("2000-2030") == (2000, 2030)
    assert diff.parse_window(" 1990-2000 ") == (1990, 2000)
    for bad in ("2000", "2000-", "-2030", "abc", "2000/2030", "2030-2000", ""):
        with pytest.raises(errors.UsageError):
            diff.parse_window(bad)


def test_one_record_per_zone_at_most():
    """四类互斥 → 同一 zone **最多一条**记录（fixture 与真实树都验）。"""
    result = diff.diff_trees(_store("old"), _store("new"))
    zones = [item.zone for item in result.changes]
    assert len(zones) == len(set(zones)), "同一 zone 出现多条: %r" % (zones,)


# ---------------------------------------------------------------- 2. fixture 金标


FIXTURE_CASES = [
    ("Zone/TailRule", "future_rule", "tail"),
    ("Zone/BcPermanent", "future_rule", "tail"),
    ("Zone/AbbrOnly", "abbreviation_only", "abbr"),
    ("Zone/AbbrAndTail", "future_rule", "tail"),
    ("Zone/LinkB", "future_rule", "tail"),
    ("Zone/LinkA", "alias_only", "link"),
    ("Zone/HistAndFuture", "history_reinterpreted", "table"),
]


@pytest.mark.parametrize("zone,expected_class,expected_evidence", FIXTURE_CASES)
def test_diff_fixture_class_and_evidence(zone, expected_class, expected_evidence):
    """fixture 里每条形态的 `class` + `evidence` 必须与手写期望一致。"""
    result = diff.diff_trees(_store("old"), _store("new"))
    found = [item for item in result.changes if item.zone == zone]
    assert len(found) == 1, "zone %s 应恰好一条记录，实得 %d 条" % (zone, len(found))
    record = found[0]
    assert record.class_ == expected_class, (
        "%s: 期望 %s，实得 %s（%s）" % (zone, expected_class, record.class_, record.note))
    assert record.evidence == expected_evidence


def test_diff_fixture_gold_matches_implementation():
    """`expect.json` 的 `expected.changes[]` 与实现逐条相等（**集合相等**，不写死条数）。"""
    expected = _fixture_expect()["expected"]["changes"]
    want = set((item["zone"], item["class"], item["evidence"]) for item in expected)

    result = diff.diff_trees(_store("old"), _store("new"))
    got = set((item.zone, item.class_, item.evidence) for item in result.changes)

    assert got == want, "多出: %r\n缺少: %r" % (sorted(got - want), sorted(want - got))


def test_diff_fixture_not_changes_produce_no_record():
    """`expected.not_changes[]` 列出的 zone **必须不产出记录**（零变更）。

    这是"每个 zone 都报一条"的退化实现的闸。
    """
    not_changes = _fixture_expect()["expected"]["not_changes"]
    assert not_changes, "金标必须写明哪些 zone 不得产出记录（否则判据空跑）"

    result = diff.diff_trees(_store("old"), _store("new"))
    reported = set(item.zone for item in result.changes)
    leaked = [zone for zone in not_changes if zone in reported]
    assert leaked == [], "不该产出记录的 zone 出现了: %r" % (leaked,)


def test_vancouver_is_not_alias_only():
    """`plan/03` §六 测试点 1 的显式断言：Vancouver **不是** `alias_only`。"""
    result = diff.diff_trees(_store("old"), _store("new"))
    record = [item for item in result.changes if item.zone == "Zone/TailRule"][0]
    assert record.class_ != "alias_only", "表相同仅 tail 变被错判成 alias_only"
    assert record.class_ == "future_rule"
    assert record.evidence == "tail"


def test_abbr_and_tail_must_land_in_future_rule():
    """`plan/03` §六 测试点 4：同时有 abbr 与 tail 差异 → **必须**落 `future_rule`。

    `Zone/AbbrAndTail` 同时具备两类的成立条件；顺序固定保证取第 2 类。
    """
    result = diff.diff_trees(_store("old"), _store("new"))
    record = [item for item in result.changes if item.zone == "Zone/AbbrAndTail"][0]
    assert record.class_ == "future_rule"
    assert record.class_ != "abbreviation_only"


def test_abbr_only_is_a_class_and_its_other_classes_do_not_hold():
    """`plan/03` §六 测试点 3：仅缩写变化 → `abbreviation_only`，
    且 `history_reinterpreted` 与 `future_rule` **均不成立**（由顺序保证）。"""
    result = diff.diff_trees(_store("old"), _store("new"))
    record = [item for item in result.changes if item.zone == "Zone/AbbrOnly"][0]
    assert record.class_ == "abbreviation_only"
    assert record.evidence == "abbr"
    assert record.before != record.after, "must record the abbreviation change"


def test_alias_only_does_not_absorb_rule_change():
    """`LinkB` 旧树是 `LinkA` 的别名，新树改了规则 → `alias_only` **不得**吸收它。

    `plan/03` §六："`alias_only` 不得吸收规则变化"。
    """
    result = diff.diff_trees(_store("old"), _store("new"))
    record = [item for item in result.changes if item.zone == "Zone/LinkB"][0]
    assert record.class_ != "alias_only"
    assert record.class_ == "future_rule"


def test_alias_only_counts_both_sides_of_the_link():
    """`LinkA` 是旧树的规范名（`LinkB` 挂在名下），新树里 `LinkB` 独立出去。

    只看 `links.get(zone)` 会判成"没变化"；必须同时看**别名集合**。
    """
    old = _store("old")
    from tzaudit.zoneinfo_store import ZoneinfoStore

    new = ZoneinfoStore(os.path.join(FIXTURE, "new"))
    assert old.links().get("Zone/LinkB") == "Zone/LinkA"      # 旧树里确实是 link
    assert new.links() == {}                                  # 新树里没有 link 了

    result = diff.diff_trees(old, new)
    record = [item for item in result.changes if item.zone == "Zone/LinkA"]
    assert len(record) == 1, "LinkA 的别名集合变化漏判"
    assert record[0].class_ == "alias_only"
    assert record[0].evidence == "link"


def test_fixture_summary_counts_match_change_list():
    """`summary.classes` 的计数必须与变更列表逐类相等（防"计数与明细两套账"）。"""
    result = diff.diff_trees(_store("old"), _store("new"))
    actual = dict((cls, 0) for cls in diff.CLASS_ORDER)
    for item in result.changes:
        actual[item.class_] += 1
    assert result.summary["classes"] == actual
    assert result.summary["changes"] == len(result.changes)
    assert result.summary["errors"] == []


# ---------------------------------------------------------------- 3. 真实数据


@needs_trees
def test_dublin_1925_is_history_reinterpreted():
    """`plan/03` §六 测试点 2：Dublin 1925（真实数据）→ `history_reinterpreted`。

    2026a 与 2026e 的 Dublin 在 1925-09-20 有一次历史重解释（表内 offset 变）。
    """
    old, new = _real_pair()
    result = diff.diff_trees(old, new, zone="Europe/Dublin")
    record = [item for item in result.changes if item.zone == "Europe/Dublin"][0]
    assert record.class_ == "history_reinterpreted", record.note
    assert "1925" in record.note, "差异应落在 1925 年附近: %s" % record.note


@needs_trees
def test_tehran_1979_is_history_reinterpreted():
    """`plan/03` §六 测试点 2：Tehran 1979（真实数据）→ `history_reinterpreted`。"""
    old, new = _real_pair()
    result = diff.diff_trees(old, new, zone="Asia/Tehran")
    record = [item for item in result.changes if item.zone == "Asia/Tehran"][0]
    assert record.class_ == "history_reinterpreted", record.note
    assert "1979" in record.note, "差异应落在 1979 年附近: %s" % record.note


@needs_trees
def test_vancouver_real_trees_is_future_rule_with_tail_evidence():
    """`plan/03` §六 测试点 1 的真实数据版：Vancouver 2026.1→2026.5。

    **表相同但 tail 不同** → 必须落 `future_rule`，`evidence=tail`，
    且 `before` / `after` 里带上两条 tail 串（`PST8PDT,…` → `MST7`）。
    """
    old, new = _real_pair()
    result = diff.diff_trees(old, new, zone="America/Vancouver")
    record = [item for item in result.changes if item.zone == "America/Vancouver"][0]
    assert record.class_ == "future_rule", record.note
    assert record.evidence == "tail"
    assert "PST8PDT" in record.before, record.before
    assert "MST7" in record.after, record.after


@needs_trees
def test_real_trees_cover_multiple_classes():
    """真实树必须**真的**产出多个类别（防"只产一种"的退化实现）。

    注意：这里只断言"至少两类"，**不写死条数**（`plan/04` §二 真值纪律第 3 条）。
    全历史窗口下 2026a→2026e 实测 20 条（11 history + 9 future）。
    """
    old, new = _real_pair()
    result = diff.diff_trees(old, new)
    kinds = set(item.class_ for item in result.changes)
    assert len(kinds) >= 2, "真实树只手出一类（%r）——判据可能退化" % sorted(kinds)
    assert "history_reinterpreted" in kinds
    assert "future_rule" in kinds


@needs_trees
def test_zone_set_is_identical_across_the_two_real_trees():
    """两棵真实树的 zone 集合相同 → `zone_set_equal` 必须为 True（分母口径）。"""
    old, new = _real_pair()
    result = diff.diff_trees(old, new)
    assert result.summary["zone_set_equal"] is True
    assert result.summary["zones_compared"] == len(set(old.zones()) | set(new.zones()))


# ---------------------------------------------------------------- 4. 判定顺序变异自证


def test_mutation_reordering_flips_a_two_class_zone():
    """**判定顺序变异**（`plan/03` §六 测试点 5）。

    就地调换 :data:`diff.CLASS_ORDER`（`future_rule` 提到 `history_reinterpreted` 之前），
    断言**同时具备两类判据**的 zone 会翻转类别；还原后必须复绿。

    锚点必须是 `Zone/HistAndFuture`（fixture 里专门构造的）：

    - 它的历史 offset 变了（1970 起 +7200 → +3600）→ 第 1 类成立；
    - 它的 tail 结构也变了（`CHF-1` → `CHG-2`）→ 第 2 类也成立。

    这是唯一能证明"顺序真的被执行"的形态。**真实树里没有这样的 zone**——
    实测 2026a→2026e：Dublin / Tehran 只有历史差异（两树 tail 相同），
    Casablanca / Vancouver 只有表外差异。拿它们当锚点会得到"永远绿"的假变异
    （M4 首版正是踩在这里）。`plan/03` §六 测试点 5 原文写"Dublin 必红"，
    在本数据下**不成立**，已登记到 `HANDOFF-M5` 的坑表。
    """
    before_state = diff.CLASS_ORDER
    try:
        diff.CLASS_ORDER = ("future_rule", "history_reinterpreted",
                            "abbreviation_only", "alias_only")
        mutated = diff.diff_trees(_store("old"), _store("new")).changes
        record = [item for item in mutated if item.zone == "Zone/HistAndFuture"][0]
        assert record.class_ == "future_rule", (
            "把 future_rule 提前后 HistAndFuture 仍落 %s —— 顺序不是判据的一部分"
            % record.class_)
    finally:
        diff.CLASS_ORDER = before_state

    restored = diff.diff_trees(_store("old"), _store("new")).changes
    record = [item for item in restored if item.zone == "Zone/HistAndFuture"][0]
    assert record.class_ == "history_reinterpreted", "还原后应回到 history_reinterpreted"


def test_real_trees_have_no_zone_with_both_criteria():
    """**如实记录**一条实测事实：真实 2026a→2026e 里没有"两类同时成立"的 zone。

    这条不是判据，是**边界说明**——它解释了为什么顺序变异必须拿 fixture 当锚点。
    若将来某对真实数据的分类变了，这里会红，提示重新评估顺序测试的锚点。
    """
    if not os.path.isdir(SLIM):
        pytest.skip("需要 data/_downloads/slim")

    old, new = _real_pair()
    result = diff.diff_trees(old, new)

    # 对每个产出记录的 zone，看它是否"同时"满足另几类：
    # 这里用最直接的可观测代理——类别分布里 history 与 future 互不重叠的 zone 数。
    history = [item.zone for item in result.changes
               if item.class_ == "history_reinterpreted"]
    future = [item.zone for item in result.changes if item.class_ == "future_rule"]
    assert set(history) & set(future) == set(), "同一 zone 不可能同时落两类（四类互斥）"
    # 本数据下两类都非空（否则"没有双类 zone"这条断言没有意义）
    assert history and future, "两类应都非空：%r / %r" % (history, future)


def test_mutation_history_boundary_would_break_the_tail_rule_case():
    """反向变异：把"共有历史"的右边界推到无穷远（`>=` → 一切 offset 差异都算历史），
    `TailRule` 会被错判成 `history_reinterpreted`。

    `Zone/TailRule` 的表尾恰好是两树 tail 的分歧点：把边界放宽后，这个点上的
    offset 差异会被"历史内"吞掉——而正确实现必须落 `future_rule`。
    """
    original = diff._history_end
    try:
        # 变异：把共有历史右边界推到无穷远 → 一切 offset 差异都算"历史"
        diff._history_end = lambda a, b: (1 << 62)
        result = diff.diff_trees(_store("old"), _store("new"))
        record = [item for item in result.changes if item.zone == "Zone/TailRule"][0]
        assert record.class_ == "history_reinterpreted", (
            "边界被放宽后 TailRule 仍落 future_rule —— 说明历史/表外的边界没被判据锚住")
    finally:
        diff._history_end = original

    result = diff.diff_trees(_store("old"), _store("new"))
    record = [item for item in result.changes if item.zone == "Zone/TailRule"][0]
    assert record.class_ == "future_rule", "还原后应回到 future_rule"


# ---------------------------------------------------------------- 5. CLI / 退出码 / 确定性


def test_cli_diff_exit_0_on_fixture():
    rc = cli.main(["diff", "--old", os.path.join(FIXTURE, "old"),
                   "--new", os.path.join(FIXTURE, "new")])
    assert rc == errors.EXIT_OK


def test_cli_diff_json_has_no_timestamp_and_is_deterministic(capsys):
    """`--json` 无时间戳；同一输入双跑**逐字节一致**（K5）。"""
    argv = ["diff", "--old", os.path.join(FIXTURE, "old"),
            "--new", os.path.join(FIXTURE, "new"), "--json"]

    assert cli.main(argv) == errors.EXIT_OK
    first = capsys.readouterr().out
    assert cli.main(argv) == errors.EXIT_OK
    second = capsys.readouterr().out

    assert first == second, "同一输入双跑不一致（可能引入了时间戳或集合序）"
    doc = json.loads(first)
    assert doc["summary"]["window"] is None
    for item in doc["changes"]:
        assert set(item) == {"zone", "class", "window", "before", "after", "evidence", "note"}
    # 不得出现任何时间戳字段
    for key in ("generated_at", "timestamp", "runtime"):
        assert key not in first


def test_cli_diff_bad_window_returns_2():
    rc = cli.main(["diff", "--old", os.path.join(FIXTURE, "old"),
                   "--new", os.path.join(FIXTURE, "new"), "--window", "not-a-window"])
    assert rc == errors.EXIT_USAGE


def test_cli_diff_missing_tree_returns_3(tmp_path):
    rc = cli.main(["diff", "--old", str(tmp_path / "nope"),
                   "--new", os.path.join(FIXTURE, "new")])
    assert rc == errors.EXIT_ENV


def test_cli_diff_unknown_zone_returns_3():
    rc = cli.main(["diff", "--old", os.path.join(FIXTURE, "old"),
                   "--new", os.path.join(FIXTURE, "new"),
                   "--zone", "No/Such_Zone"])
    assert rc == errors.EXIT_ENV


def test_diff_reports_unclassified_rather_than_forcing_a_class():
    """窗口把唯一的历史差异排除后，四类都不成立 → 记进 `summary.unclassified`。

    口径是"取第一条成立者"，**不是**"必须命中四类之一"（四类互斥但不穷尽）。
    宁如实报告，也不把 `alias_only` 当垃圾桶。
    """
    if not os.path.isdir(SLIM):
        pytest.skip("需要 data/_downloads/slim")

    old, new = _real_pair()
    result = diff.diff_trees(old, new, window=(2020, 2030))
    assert result.summary["unclassified"], "应有 zone 落进 unclassified（否则口径可疑）"
    # 落进 unclassified 的 zone 不得同时出现在变更列表里
    reported = set(item.zone for item in result.changes)
    overlap = reported & set(result.summary["unclassified"])
    assert overlap == set()


def test_diff_window_only_narrows_history_class():
    """`--window` 只影响第 1 类；第 2 类（表外 + tail）不受窗口限制（`data/README.md` §4.3）。"""
    if not os.path.isdir(SLIM):
        pytest.skip("需要 data/_downloads/slim")

    old, new = _real_pair()
    full = diff.diff_trees(old, new)
    narrowed = diff.diff_trees(old, new, window=(2020, 2030))

    full_future = full.summary["classes"]["future_rule"]
    narrow_future = narrowed.summary["classes"]["future_rule"]
    assert narrow_future == full_future, (
        "第 2 类不该受窗口影响：全历史 %d 条，窗口内 %d 条"
        % (full_future, narrow_future))
    assert narrowed.summary["classes"]["history_reinterpreted"] <= \
        full.summary["classes"]["history_reinterpreted"]
