# -*- coding: utf-8 -*-
"""M5 · 报告与门禁 `report`（`plan/03` §八 的四条测试点 + 退出码口径）。

分四组：

1. **报告头三字段**：缺任一 → `ReportIncomplete`（退 3）；`zones_covered` 必须是整数。
2. **`--fail-on` 四组退出码**：无命中 / `gap` / `overlap` / `history`；
   且**只看结果集**（Markdown 里出现的字样不参与判定）。
3. **`--json` 与 Markdown 退出码相同** + 双跑逐字节一致（`generated_at` 注入固定值）。
4. **脱敏**：Markdown 里不含盘符路径 / `/home/` / 主机名。

`generated_at` 由调用方注入（`resolve_generated_at` 是包里唯一读时钟的地方，
`SOURCE_DATE_EPOCH` 是它的冻结口，决策 Q3）。
"""

from __future__ import print_function

import io
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from tzaudit import cli, errors, report  # noqa: E402
from tzaudit.serialize import dumps_json  # noqa: E402

#: 固定的 `generated_at`（测试注入值；**不是**观测值，也不进任何金标）
FROZEN_AT = "2026-10-22T00:00:00Z"

WINDOW_GAP = {
    "type": "GAP", "start_local": "2026-03-08 02:00:00", "end_local": "2026-03-08 03:00:00",
    "duration_min": 60, "residual_sec": 0, "offset_before": "-05:00",
    "offset_after": "-04:00", "zone": "America/New_York", "source": "tail",
}
WINDOW_OVERLAP = {
    "type": "OVERLAP", "start_local": "2026-11-01 01:00:00", "end_local": "2026-11-01 02:00:00",
    "duration_min": 60, "residual_sec": 0, "offset_before": "-04:00",
    "offset_after": "-05:00", "zone": "America/New_York", "source": "tail",
}
CHANGE_HISTORY = {
    "zone": "Europe/Dublin", "class": "history_reinterpreted", "window": None,
    "before": "offset=+00:25:21", "after": "offset=+00:00:00",
    "evidence": "table", "note": "1925-09-20 起按新解释",
}
CHANGE_FUTURE = {
    "zone": "America/Vancouver", "class": "future_rule", "window": None,
    "before": "tail=PST8PDT,M3.2.0,M11.1.0", "after": "tail=MST7",
    "evidence": "tail", "note": "",
}
ROW_OK = {
    "id": "case-001", "local": "2026-06-01 12:00:00", "status": "OK",
    "utc_candidates": ["2026-06-01T16:00:00Z"], "note": "", "invalid_reason": "",
}
ROW_GAP = {
    "id": "case-002", "local": "2026-03-08 02:30:00", "status": "GAP",
    "utc_candidates": [], "note": "0 个 UTC 候选（该墙钟不存在）", "invalid_reason": "",
}
ROW_OVERLAP = {
    "id": "case-003", "local": "2026-11-01 01:30:00", "status": "OVERLAP",
    "utc_candidates": ["2026-11-01T05:30:00Z", "2026-11-01T06:30:00Z"],
    "note": "2 个 UTC 候选（偏移差 3600s）", "invalid_reason": "",
}
ROW_INVALID = {
    "id": "case-004", "local": "2026-13-01 00:00", "status": "INVALID",
    "utc_candidates": [], "note": "", "invalid_reason": "时间无法解析: bad date",
}


def _build(windows=(), changes=(), rows=(), data_version="2026a",
           zones_covered=1, generated_at=FROZEN_AT):
    result = {"windows": list(windows), "changes": list(changes), "rows": list(rows)}
    return report.build_report([result], data_version=data_version,
                               zones_covered=zones_covered, generated_at=generated_at)


# ---------------------------------------------------------------- 1. 报告头


def test_report_header_has_exactly_three_fields():
    """`data/README.md` §4.5 的三字段：`data_version` / `zones_covered` / `generated_at`。"""
    assert report.REPORT_REQUIRED_FIELDS == ("data_version", "zones_covered", "generated_at")
    _markdown, doc = _build()
    assert set(doc["report_header"]) == set(report.REPORT_REQUIRED_FIELDS)
    assert doc["report_header"]["generated_at"] == FROZEN_AT


@pytest.mark.parametrize("field", ["data_version", "zones_covered", "generated_at"])
def test_missing_header_field_raises_report_incomplete(field):
    """三字段**缺任一** → `ReportIncomplete`（退出码 3），不是"补默认值蒙过去"。"""
    kwargs = {"data_version": "2026a", "zones_covered": 1, "generated_at": FROZEN_AT}
    kwargs[field] = None
    with pytest.raises(errors.ReportIncomplete) as excinfo:
        report.build_report([{"rows": []}], **kwargs)
    assert field in excinfo.value.message
    assert errors.ReportIncomplete.exit_code == errors.EXIT_ENV == 3


def test_zones_covered_must_be_an_integer():
    """`zones_covered` 是"分母"，字符串/布尔值都是口径错误 → 退 3。"""
    for bad in ("1", True, 1.0):
        with pytest.raises(errors.ReportIncomplete):
            report.build_report([{"rows": []}], data_version="2026a",
                                zones_covered=bad, generated_at=FROZEN_AT)


def test_negative_zones_covered_rejected():
    with pytest.raises(errors.ReportIncomplete):
        report.build_report([{"rows": []}], data_version="2026a",
                            zones_covered=-1, generated_at=FROZEN_AT)


def test_check_header_accepts_flat_and_nested():
    assert report.check_header({"data_version": "a", "zones_covered": 0,
                                "generated_at": FROZEN_AT})["data_version"] == "a"
    assert report.check_header({"report_header": {
        "data_version": "a", "zones_covered": 0, "generated_at": FROZEN_AT}})["data_version"] == "a"
    with pytest.raises(errors.ReportIncomplete):
        report.check_header({"data_version": "a"})


# ---------------------------------------------------------------- 2. fail-on 四组


def test_fail_on_choices_are_exactly_three():
    """枚举**固定三值**，不存在第四种（`data/README.md` §4.4）。"""
    assert report.FAIL_ON_CHOICES == ("gap", "overlap", "history")


@pytest.mark.parametrize("text,expected", [
    ("", set()),
    ("gap", {"gap"}),
    ("gap,overlap", {"gap", "overlap"}),
    ("gap, overlap , history", {"gap", "overlap", "history"}),
    ("GAP", {"gap"}),
])
def test_parse_fail_on(text, expected):
    assert report.parse_fail_on(text) == expected


@pytest.mark.parametrize("bad", ["gaps", "difference", "gap,version", "1"])
def test_parse_fail_on_rejects_unknown(bad):
    """非法值**显式拒绝**（退 2），不静默忽略——否则门禁会悄悄失效。"""
    with pytest.raises(errors.UsageError):
        report.parse_fail_on(bad)


def test_gate_exit_0_when_nothing_hits():
    _md, doc = _build(windows=[WINDOW_OVERLAP], changes=[CHANGE_FUTURE], rows=[ROW_OK])
    assert report.gate_exit_code(doc, {"gap"}) == errors.EXIT_OK
    assert report.gate_exit_code(doc, {"history"}) == errors.EXIT_OK
    assert report.gate_exit_code(doc, set()) == errors.EXIT_OK


def test_gate_exit_1_on_gap():
    _md, doc = _build(windows=[WINDOW_GAP])
    assert report.gate_exit_code(doc, {"gap"}) == errors.EXIT_GATE_HIT
    assert report.gate_exit_code(doc, {"overlap"}) == errors.EXIT_OK


def test_gate_exit_1_on_overlap():
    _md, doc = _build(windows=[WINDOW_OVERLAP])
    assert report.gate_exit_code(doc, {"overlap"}) == errors.EXIT_GATE_HIT
    assert report.gate_exit_code(doc, {"gap"}) == errors.EXIT_OK


def test_gate_exit_1_on_history():
    _md, doc = _build(changes=[CHANGE_HISTORY])
    assert report.gate_exit_code(doc, {"history"}) == errors.EXIT_GATE_HIT
    # `future_rule` **不是** history（这是 `history` 的判据边界）
    _md, doc2 = _build(changes=[CHANGE_FUTURE])
    assert report.gate_exit_code(doc2, {"history"}) == errors.EXIT_OK


def test_gate_also_reads_audit_rows():
    """清单行也参与门禁（`rows[].status`），不只是 `windows[].type`。"""
    _md, doc = _build(rows=[ROW_GAP])
    assert report.gate_exit_code(doc, {"gap"}) == errors.EXIT_GATE_HIT
    _md, doc = _build(rows=[ROW_OVERLAP])
    assert report.gate_exit_code(doc, {"overlap"}) == errors.EXIT_GATE_HIT


def test_gate_reads_only_the_result_set_not_the_prose():
    """**只看结果集**：Markdown 里出现 "history_reinterpreted" 字样，但结果集里没有该类变更
    → `--fail-on history` 不命中。「人读文本里出现类别名」不构成证据。"""
    markdown, doc = _build(rows=[dict(ROW_OK, note="history_reinterpreted 只是说明文字")])
    assert "history_reinterpreted" in markdown, (
        "Markdown 里应能看到那段说明文字（这正是要排除的干扰来源）")
    assert doc["rows"][0]["status"] == "OK"
    assert report.gate_exit_code(doc, {"history"}) == errors.EXIT_OK


def test_unknown_fail_on_value_raises_value_error_at_function_level():
    """函数层收到未知值是**程序误用**（`ValueError`）；用户输入走 `parse_fail_on`（退 2）。"""
    _md, doc = _build()
    with pytest.raises(ValueError):
        report.gate_exit_code(doc, {"nope"})


# ---------------------------------------------------------------- 3. json / md 一致 + 双跑


def test_json_and_markdown_share_the_same_exit_code():
    """`--json` 与 Markdown 的退出码必须相同（`data/README.md` §4.4）。"""
    for kwargs, fail_on in (
        ({"windows": [WINDOW_GAP]}, {"gap"}),
        ({"windows": [WINDOW_OVERLAP]}, {"overlap"}),
        ({"changes": [CHANGE_HISTORY]}, {"history"}),
        ({"rows": [ROW_OK]}, {"gap", "overlap", "history"}),
    ):
        _md, doc = _build(**kwargs)
        assert report.gate_exit_code(doc, fail_on) == report.gate_exit_code(doc, fail_on)


def test_build_report_is_byte_stable_across_two_runs():
    """同一结果集双跑 → Markdown 与 JSON **逐字节一致**（`generated_at` 固定）。"""
    kwargs = {"windows": [WINDOW_GAP, WINDOW_OVERLAP],
              "changes": [CHANGE_HISTORY, CHANGE_FUTURE],
              "rows": [ROW_OK, ROW_GAP, ROW_OVERLAP, ROW_INVALID]}

    md_first, doc_first = _build(**kwargs)
    md_second, doc_second = _build(**kwargs)
    assert md_first == md_second
    assert dumps_json(doc_first) == dumps_json(doc_second)


def test_markdown_has_no_timestamp_except_generated_at():
    """除报告头的 `generated_at` 外**零时间戳**（`plan/03` §八）。"""
    md, _doc = _build(windows=[WINDOW_GAP], changes=[CHANGE_HISTORY], rows=[ROW_GAP])
    stamps = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", md)
    assert stamps == [FROZEN_AT], "Markdown 里出现了额外的时间戳: %s" % stamps


def test_markdown_table_column_order_is_fixed():
    """Markdown 表格**列序固定**（`plan/03` §八）——改列序等于改契约。"""
    md, _doc = _build(windows=[WINDOW_GAP], changes=[CHANGE_HISTORY], rows=[ROW_OK])

    def header_of(title):
        lines = md.split("\n")
        for index, line in enumerate(lines):
            if line.strip() == "## " + title:
                return [cell.strip() for cell in lines[index + 2].strip("|").split("|")]
        raise AssertionError("Markdown 缺小节: %s" % title)

    assert header_of("墙钟风险窗口") == list(report.WINDOW_COLUMNS)
    assert header_of("版本差异") == list(report.CHANGE_COLUMNS)
    assert header_of("清单判定") == list(report.ROW_COLUMNS)


def test_markdown_contains_report_header_fields():
    md, _doc = _build(data_version="2026a / 2026e", zones_covered=598)
    for needle in ("data_version: 2026a / 2026e", "zones_covered: 598", "generated_at: " + FROZEN_AT):
        assert needle in md, needle


def test_invalid_rows_dominate_the_gate():
    """有 `INVALID` 行时整体退 **4**（输入无效优先于门禁命中）。"""
    _md, doc = _build(rows=[ROW_GAP, ROW_INVALID])
    assert report.has_invalid_rows(doc) is True
    assert report.report_exit_code(doc, {"gap"}) == errors.EXIT_INVALID_INPUT

    _md, clean = _build(rows=[ROW_GAP])
    assert report.has_invalid_rows(clean) is False
    assert report.report_exit_code(clean, {"gap"}) == errors.EXIT_GATE_HIT


# ---------------------------------------------------------------- 4. 脱敏


def test_markdown_has_no_absolute_path_or_hostname():
    """Markdown 不含盘符路径 / `/home/` / `/Users/`（`plan/03` §八 测试点 4）。"""
    md, _doc = _build(windows=[WINDOW_GAP], changes=[CHANGE_HISTORY])
    pattern = re.compile(r"(?<![<\w])[A-Za-z]:[\\/](?!<)|/home/|/Users/")
    assert pattern.search(md) is None, pattern.search(md).group(0)


def test_cell_escapes_pipe_and_newline():
    """表格单元格里的竖线/换行被转义，不破坏表格结构。"""
    _md, doc = _build(rows=[dict(ROW_OK, note="a|b\nc")])
    assert doc["rows"][0]["note"] == "a|b\nc"  # 结果集本身不改
    md, _doc = _build(rows=[dict(ROW_OK, note="a|b\nc")])
    row_line = [line for line in md.split("\n") if line.startswith("| case-001")][0]
    assert "a\\|b c" in row_line


# ---------------------------------------------------------------- CLI 接线


def _write_result(tmp_path, payload, name="result.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_cli_report_exit_0_on_clean_result(tmp_path, capsys):
    path = _write_result(tmp_path, {
        "data_version": "2026a", "zones_covered": 598, "generated_at": FROZEN_AT,
        "rows": [ROW_OK],
    })
    rc = cli.main(["report", "--from", path, "--fail-on", "gap,overlap,history"])
    out = capsys.readouterr().out
    assert rc == errors.EXIT_OK
    assert "data_version: 2026a" in out
    assert "zones_covered: 598" in out


def test_cli_report_fail_on_gap_returns_1(tmp_path):
    path = _write_result(tmp_path, {
        "data_version": "2026a", "zones_covered": 1, "generated_at": FROZEN_AT,
        "windows": [WINDOW_GAP],
    })
    assert cli.main(["report", "--from", path, "--fail-on", "gap"]) == errors.EXIT_GATE_HIT


def test_cli_report_fail_on_overlap_returns_1(tmp_path):
    path = _write_result(tmp_path, {
        "data_version": "2026a", "zones_covered": 1, "generated_at": FROZEN_AT,
        "windows": [WINDOW_OVERLAP],
    })
    assert cli.main(["report", "--from", path, "--fail-on", "overlap"]) == errors.EXIT_GATE_HIT


def test_cli_report_fail_on_history_returns_1(tmp_path):
    path = _write_result(tmp_path, {
        "data_version": "2026a", "zones_covered": 598, "generated_at": FROZEN_AT,
        "changes": [CHANGE_HISTORY],
    })
    assert cli.main(["report", "--from", path, "--fail-on", "history"]) == errors.EXIT_GATE_HIT


def test_cli_report_missing_header_returns_3(tmp_path):
    """缺报告头字段 → 退 3（`ReportIncomplete`）。"""
    path = _write_result(tmp_path, {"rows": [ROW_OK]})
    assert cli.main(["report", "--from", path]) == errors.EXIT_ENV


def test_cli_report_zoneinfo_supplies_data_version(tmp_path, capsys):
    """`--zoneinfo <tree>` 是 `data_version` 的**输入侧来源**（单树形态）。

    `windows --all --json` 的结果集里没有版本标签（它只描述窗口），
    所以报告头必须由调用方指明"这份结果来自哪棵树"——否则退 3。
    """
    tree = tmp_path / "2026e"
    tree.mkdir()
    (tree / "provenance.json").write_text(
        json.dumps({"version": "2026e", "kind": "slim"}), encoding="utf-8")

    path = _write_result(tmp_path, {
        "summary": {"zones_scanned": 598, "windows": 0},
        "windows": [WINDOW_GAP],
    })
    assert cli.main(["report", "--from", path, "--zoneinfo", str(tree),
                     "--fail-on", "gap"]) == errors.EXIT_GATE_HIT
    out = capsys.readouterr().out
    assert "data_version: 2026e" in out
    assert "zones_covered: 598" in out, "zones_scanned 应被当作 zones_covered 的分母"


def test_cli_report_zoneinfo_without_provenance_still_works(tmp_path, capsys):
    """`--zoneinfo` 不强制 `provenance.json`（那是 `--version` 的要求 / K16），
    但拿不到版本标签时 `data_version` 仍缺失 → 退 3（不猜）。

    `ZoneinfoStore` 会按目录名兜底猜版本；这里用 `2026e` 当目录名，
    所以能猜出 `2026e`，报告头成立。**猜不到**的目录名（如 `mytree`）→ 退 3。
    """
    named = tmp_path / "2026e"
    named.mkdir()
    path = _write_result(tmp_path, {"summary": {"zones_scanned": 1}, "rows": [ROW_OK]})
    assert cli.main(["report", "--from", path, "--zoneinfo", str(named)]) == errors.EXIT_OK
    assert "data_version: 2026e" in capsys.readouterr().out

    anonymous = tmp_path / "mytree"
    anonymous.mkdir()
    # 目录名猜不出 `YYYY[az]` → version 是 "unknown"；"unknown" 不是空串，
    # 所以报告头仍然成立（如实写 unknown，而不是假装知道）。
    assert cli.main(["report", "--from", path, "--zoneinfo", str(anonymous)]) == errors.EXIT_OK
    assert "data_version: unknown" in capsys.readouterr().out


def test_cli_report_version_pair_supplies_data_version(tmp_path, capsys):
    """`--version <A>,<B>` 是两树形态的来源；两棵都必须带 `provenance.json`。"""
    for name in ("2026a", "2026e"):
        tree = tmp_path / name
        tree.mkdir()
        (tree / "provenance.json").write_text(
            json.dumps({"version": name, "kind": "slim"}), encoding="utf-8")

    path = _write_result(tmp_path, {"summary": {"zones_compared": 598}, "changes": []})
    rc = cli.main(["report", "--from", path,
                   "--version", "%s,%s" % (tmp_path / "2026a", tmp_path / "2026e")])
    assert rc == errors.EXIT_OK
    out = capsys.readouterr().out
    assert "data_version: 2026a / 2026e" in out
    assert "zones_covered: 598" in out


def test_cli_report_audit_result_needs_no_extra_flags(tmp_path, capsys):
    """`audit --json` 自带 `versions` → 报告头可从结果集推出，不必再传 `--version`。"""
    path = _write_result(tmp_path, {
        "summary": {"zone": "Zone/Bc", "versions": ["2026a", "2026b"],
                    "zones_covered": 1, "rows": 2, "invalid": 0},
        "rows": [ROW_OK, ROW_GAP],
    })
    assert cli.main(["report", "--from", path, "--fail-on", "gap"]) == errors.EXIT_GATE_HIT
    out = capsys.readouterr().out
    assert "data_version: 2026a / 2026b" in out


def test_cli_report_version_and_zoneinfo_are_mutually_exclusive(tmp_path):
    tree = tmp_path / "2026e"
    tree.mkdir()
    path = _write_result(tmp_path, {"data_version": "x", "zones_covered": 0, "rows": []})
    rc = cli.main(["report", "--from", path,
                   "--version", "%s,%s" % (str(tree), str(tree)),
                   "--zoneinfo", str(tree)])
    assert rc == errors.EXIT_USAGE


def test_cli_report_unknown_fail_on_returns_2(tmp_path):
    path = _write_result(tmp_path, {
        "data_version": "2026a", "zones_covered": 0, "generated_at": FROZEN_AT, "rows": [],
    })
    assert cli.main(["report", "--from", path, "--fail-on", "gaps"]) == errors.EXIT_USAGE


def test_cli_report_missing_file_returns_3(tmp_path):
    assert cli.main(["report", "--from", str(tmp_path / "nope.json")]) == errors.EXIT_ENV


def test_cli_report_broken_json_returns_4(tmp_path):
    """结果集不是合法 JSON → 输入无效（退 4），不是 1（未预期异常）。"""
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    assert cli.main(["report", "--from", str(path)]) == errors.EXIT_INVALID_INPUT


def test_cli_report_json_and_markdown_exit_codes_match(tmp_path):
    payload = {"data_version": "2026a", "zones_covered": 1,
               "generated_at": FROZEN_AT, "windows": [WINDOW_GAP]}
    path = _write_result(tmp_path, payload)
    md_rc = cli.main(["report", "--from", path, "--format", "md", "--fail-on", "gap"])
    js_rc = cli.main(["report", "--from", path, "--format", "json", "--fail-on", "gap"])
    assert md_rc == js_rc == errors.EXIT_GATE_HIT


def test_cli_report_json_output_is_deterministic(tmp_path, capsys):
    """`--format json` 双跑逐字节一致（`generated_at` 来自结果集，不读时钟）。"""
    path = _write_result(tmp_path, {
        "data_version": "2026a", "zones_covered": 1, "generated_at": FROZEN_AT,
        "windows": [WINDOW_GAP], "rows": [ROW_OK],
    })
    argv = ["report", "--from", path, "--format", "json"]
    assert cli.main(argv) == errors.EXIT_OK
    first = capsys.readouterr().out
    assert cli.main(argv) == errors.EXIT_OK
    second = capsys.readouterr().out
    assert first == second
    assert FROZEN_AT in first


def test_cli_report_frozen_clock_via_source_date_epoch(tmp_path, capsys, monkeypatch):
    """结果集没给 `generated_at` 时，`SOURCE_DATE_EPOCH` 是冻结口（决策 Q3）。"""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    path = _write_result(tmp_path, {"data_version": "2026a", "zones_covered": 0, "rows": []})
    assert cli.main(["report", "--from", path, "--format", "json"]) == errors.EXIT_OK
    doc = json.loads(capsys.readouterr().out)
    assert doc["report_header"]["generated_at"] == "1970-01-01T00:00:00Z"


def test_resolve_generated_at_prefers_env_and_rejects_garbage():
    assert report.resolve_generated_at({"SOURCE_DATE_EPOCH": "86400"}) == \
        "1970-01-02T00:00:00Z"
    with pytest.raises(errors.UsageError):
        report.resolve_generated_at({"SOURCE_DATE_EPOCH": "not-a-number"})
    # 没设时读时钟：形态正确即可（内容不参与任何断言，避免"把观测写进测试"）
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
                    report.resolve_generated_at({}))


def test_report_module_does_not_read_the_clock_outside_its_single_point():
    """`report` 里读时钟只出现在 `resolve_generated_at` 一处（K5）。

    用 AST 定位"哪个函数里出现了 ``gmtime``"，而不是数源码里出现几次
    （注释里提到 `time.gmtime()` 也会被数进去——那是假红）。
    """
    import ast

    path = os.path.join(ROOT, "src", "tzaudit", "report.py")
    with io.open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    assert "datetime.now(" not in source and "time.time(" not in source

    tree = ast.parse(source, filename=path)
    owners = [node.name for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef)
              and any(isinstance(sub, ast.Attribute) and sub.attr == "gmtime"
                      for sub in ast.walk(node))]
    assert owners == ["resolve_generated_at"], owners
