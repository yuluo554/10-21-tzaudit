# -*- coding: utf-8 -*-
"""退出码语义（``data/README.md`` §4.4 单点定义）+ 未就绪语义的退役闸。

骨架期的 ``EXIT_NOT_READY`` 是**临时**语义；每个子命令落地时必须在同一提交里
删掉常量与全部引用（见 ``plan/03`` §九）。本文件里的断言会随退役**逐条删除**，
所以每条都写了退役条件。
"""

import pytest

from tzaudit import cli, errors


def test_exit_code_constants_match_spec():
    """码值必须与 data/README.md §4.4 逐位一致（改动即口径变更）。"""
    assert errors.EXIT_OK == 0
    assert errors.EXIT_GATE_HIT == 1
    assert errors.EXIT_USAGE == 2
    assert errors.EXIT_ENV == 3
    assert errors.EXIT_INVALID_INPUT == 4


def test_usage_error_from_unknown_subcommand_returns_2():
    assert cli.main(["no-such-subcommand"]) == errors.EXIT_USAGE


def test_missing_required_argument_returns_2():
    assert cli.main(["windows", "--year", "2026"]) == errors.EXIT_USAGE


def test_no_subcommand_returns_2():
    assert cli.main([]) == errors.EXIT_USAGE


def test_unknown_format_returns_2_not_fallback():
    """未知 --format 必须显式拒绝（argparse choices），不回落默认值。"""
    assert cli.main(["report", "--format", "yaml"]) == errors.EXIT_USAGE


def test_not_ready_exit_code_is_5():
    """骨架期：未实现的子命令退 5（不是 0、不是 2）。

    退役条件：该子命令实现落地时，本测试随 ``_unimplemented`` 一起删除。

    **M3 已退役 ``windows``**（2026-10-21）：``windows`` 子命令落地，退出码 5 的
    适用范围收窄到 ``diff`` / ``audit`` / ``report`` 三条。
    """
    for argv in (
        ["diff", "--old", "a", "--new", "b"],
        ["audit", "--times", "t.txt", "--zone", "UTC"],
        ["report", "--from", "x.json"],
    ):
        assert cli.main(argv) == errors.EXIT_NOT_READY, argv


def test_windows_is_no_longer_not_ready(tmp_path):
    """**防复活**断言：``windows`` 落地后不得再退 5（退 3 = 环境不满足，才是它现在的语义）。

    这条是"幽灵语义复活"的闸：把 ``cli.main`` 的 ``windows`` 分派删掉、
    或把它改回 ``_unimplemented``，这里立刻红。
    """
    tree = tmp_path / "tree"
    tree.mkdir()
    rc = cli.main(["windows", "--zone", "America/New_York", "--year", "2026",
                   "--zoneinfo", str(tree)])
    assert rc != errors.EXIT_NOT_READY, "windows 落地后不得再退 5（功能未就绪）"


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
