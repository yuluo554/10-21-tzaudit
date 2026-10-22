# -*- coding: utf-8 -*-
"""退出码语义（``data/README.md`` §4.4 单点定义）+ 未就绪语义的退役闸。

骨架期的 ``EXIT_NOT_READY``（退出码 5）是**临时**语义：每个子命令落地时必须在同一提交里
删掉常量与全部引用（见 ``plan/03`` §九）。**M5（2026-10-22）已整项退役**——
五个子命令全部落地，这里只剩"防复活"断言：``src/`` 里不得再出现"功能未就绪"语义，
``audit`` / ``report`` 也不得再退 5。
"""

import os

import pytest

from tzaudit import cli, errors

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "tzaudit")


def test_exit_code_constants_match_spec():
    """码值必须与 data/README.md §4.4 逐位一致（改动即口径变更）。"""
    assert errors.EXIT_OK == 0
    assert errors.EXIT_GATE_HIT == 1
    assert errors.EXIT_USAGE == 2
    assert errors.EXIT_ENV == 3
    assert errors.EXIT_INVALID_INPUT == 4


def test_not_ready_semantics_is_gone_from_the_package():
    """**整项退役**的闸（M5）：``src/`` 里不得再有"功能未就绪"的任何形态。

    三处一起断言——常量、异常类、``cli._unimplemented``。任一处被"顺手加回来"
    （哪怕是给新子命令留占位），这条立刻红：**5 不再进入任何发布态口径**。
    """
    assert not hasattr(errors, "EXIT_NOT_READY"), "errors.EXIT_NOT_READY 必须已整项删除"
    assert not hasattr(errors, "NotImplementedYet"), "errors.NotImplementedYet 必须已整项删除"
    assert not hasattr(cli, "_unimplemented"), "cli._unimplemented 必须已整项删除"

    offenders = []
    for name in sorted(os.listdir(PKG)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(PKG, name)
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        if "NOT_READY" in source or "NotImplementedYet" in source or "未就绪" in source:
            offenders.append(name)
    assert offenders == [], "src/ 里仍有未就绪语义: %s" % offenders


def test_usage_error_from_unknown_subcommand_returns_2():
    assert cli.main(["no-such-subcommand"]) == errors.EXIT_USAGE


def test_missing_required_argument_returns_2():
    assert cli.main(["windows", "--year", "2026"]) == errors.EXIT_USAGE


def test_no_subcommand_returns_2():
    assert cli.main([]) == errors.EXIT_USAGE


def test_unknown_format_returns_2_not_fallback():
    """未知 --format 必须显式拒绝（argparse choices），不回落默认值。"""
    assert cli.main(["report", "--format", "yaml"]) == errors.EXIT_USAGE


def test_windows_is_no_longer_not_ready(tmp_path):
    """**防复活**断言：``windows`` 落地后不得再退 5（退 3 = 环境不满足，才是它现在的语义）。

    这条是"幽灵语义复活"的闸：把 ``cli.main`` 的 ``windows`` 分派删掉、
    或把它改回占位实现，这里立刻红。
    """
    tree = tmp_path / "tree"
    tree.mkdir()
    rc = cli.main(["windows", "--zone", "America/New_York", "--year", "2026",
                   "--zoneinfo", str(tree)])
    assert rc != 5, "windows 落地后不得再退 5（功能未就绪）"
    assert rc == errors.EXIT_ENV


def test_diff_is_no_longer_not_ready(tmp_path):
    """**防复活**断言（M4 新增）：``diff`` 落地后不得再退 5。

    空树上比较 → 两个 zone 集合都空 → 退 0（成功、零变更），**不是** 5。
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = cli.main(["diff", "--old", str(empty), "--new", str(empty)])
    assert rc != 5, "diff 落地后不得再退 5（功能未就绪）"
    assert rc == errors.EXIT_OK


def test_audit_is_no_longer_not_ready(tmp_path):
    """**防复活**断言（M5 新增）：``audit`` 落地后不得再退 5。

    清单能读、树是空目录 → 走到解析层后报"zone 不存在"（退 3），
    而不是"功能未就绪"。把 ``audit`` 分派删掉或改回占位，这里立刻红。
    """
    times = tmp_path / "times.txt"
    times.write_text("2026-03-08 02:30\n", encoding="utf-8")
    tree = tmp_path / "tree"
    tree.mkdir()
    rc = cli.main(["audit", "--times", str(times), "--zone", "UTC",
                   "--zoneinfo", str(tree)])
    assert rc != 5, "audit 落地后不得再退 5（功能未就绪）"
    assert rc == errors.EXIT_ENV, "空树里没有该 zone → 环境不满足"


def test_report_is_no_longer_not_ready(tmp_path):
    """**防复活**断言（M5 新增）：``report`` 落地后不得再退 5。

    一个字段齐备的结果集 → 退 0；缺报告头字段 → 退 3。两条都不是 5。
    """
    import json

    complete = tmp_path / "complete.json"
    complete.write_text(json.dumps({
        "data_version": "2026a", "zones_covered": 0,
        "generated_at": "2026-01-01T00:00:00Z",
        "rows": [{"id": "case-001", "local": "2026-01-01 00:00:00",
                  "status": "OK", "utc_candidates": [], "note": "", "invalid_reason": ""}],
    }), encoding="utf-8")
    rc = cli.main(["report", "--from", str(complete), "--format", "json"])
    assert rc != 5, "report 落地后不得再退 5（功能未就绪）"
    assert rc == errors.EXIT_OK

    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps({"rows": []}), encoding="utf-8")
    assert cli.main(["report", "--from", str(incomplete)]) == errors.EXIT_ENV


def test_environment_problem_maps_to_3(tmp_path):
    rc = cli.main(["version", "--zoneinfo", str(tmp_path / "does-not-exist")])
    assert rc == errors.EXIT_ENV


def test_version_subcommand_exit_0_on_empty_tree(tmp_path):
    rc = cli.main(["version", "--zoneinfo", str(tmp_path)])
    assert rc == errors.EXIT_OK


def test_missing_zone_reports_environment_problem(tmp_path):
    rc = cli.main(["version", "--zoneinfo", str(tmp_path), "--zone", "No/Where"])
    assert rc == errors.EXIT_ENV


@pytest.mark.parametrize("exc", [errors.UsageError, errors.EnvironmentProblem,
                                 errors.InvalidInput, errors.ReportIncomplete])
def test_exception_classes_carry_exit_code(exc):
    assert exc("x").exit_code == exc.exit_code
    assert isinstance(exc("x"), errors.TzAuditError)
