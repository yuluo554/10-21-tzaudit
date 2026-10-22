# -*- coding: utf-8 -*-
"""命令行入口 —— 契约见 ``plan/03`` §一 / §九。

**唯一**读 ``sys.argv`` 的地方；测试一律传 ``argv``。
退出码语义单点在 ``errors`` / ``data/README.md`` §4.4。
"""

from __future__ import print_function

import argparse
import json
import os
import sys

from . import __version__, audit, civil, report
from .errors import (
    EXIT_ENV,
    EXIT_INVALID_INPUT,
    EXIT_OK,
    EXIT_USAGE,
    EnvironmentProblem,
    InvalidInput,
    TzAuditError,
    UsageError,
)
from .serialize import dumps_json, emit, read_text

PROG = "tzaudit"


def _ensure_utf8_stdio():
    """入口编码加固：只在流不是 UTF-8 时 reconfigure（中文控制台 cp936 保持不动）。"""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding in ("utf8", "utf8mb4"):
            continue
        reconfigure = getattr(stream, "reconfigure", None)  # 3.7+
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


class _Parser(argparse.ArgumentParser):
    """把 argparse 的 ``SystemExit(2)`` 统一成 :class:`UsageError`，避免两种退出路径。"""

    def error(self, message):
        raise UsageError(message)


def build_parser():
    parser = _Parser(
        prog=PROG,
        description="本地时区数据版本漂移审计：墙钟风险窗口 / 版本差异分类 / 清单判定。",
        epilog="数值口径见 data/README.md §四；运行时零网络。",
    )
    parser.add_argument("--version", action="version", version="%s %s" % (PROG, __version__))

    sub = parser.add_subparsers(dest="command", metavar="<subcommand>")

    p_windows = sub.add_parser("windows", help="墙钟风险窗口（GAP / OVERLAP）")
    p_windows.add_argument("--zone", help="单个 zone 名，如 America/New_York")
    p_windows.add_argument("--all", action="store_true", help="全量 zone 批量")
    p_windows.add_argument("--year", type=int, required=True, help="年份，如 2026")
    p_windows.add_argument("--zoneinfo", required=True, help="zoneinfo 树目录")
    p_windows.add_argument("--json", action="store_true", help="输出 JSON（默认 Markdown）")

    p_diff = sub.add_parser("diff", help="两棵树之间的版本差异分类")
    p_diff.add_argument("--old", required=True, help="旧树目录")
    p_diff.add_argument("--new", required=True, help="新树目录")
    p_diff.add_argument("--window", help="<开始年>-<结束年>；缺省覆盖全历史")
    p_diff.add_argument("--zone", help="只比较该 zone")
    p_diff.add_argument("--json", action="store_true", help="输出 JSON")

    p_audit = sub.add_parser("audit", help="本地时刻清单审计")
    p_audit.add_argument("--times", help="清单文件（CSV: id,local_time 或一行一个时间戳）")
    p_audit.add_argument("--daily", help="HH:MM，按天展开（不接受 cron 表达式）")
    p_audit.add_argument("--year", type=int, help="--daily 展开的年份")
    p_audit.add_argument("--zone", help="zone 名")
    p_audit.add_argument("--zoneinfo", help="zoneinfo 树目录（单版本）")
    p_audit.add_argument("--version", dest="versions", help="两个树目录，逗号分隔 <A>,<B>")
    p_audit.add_argument("--json", action="store_true", help="输出 JSON")

    p_report = sub.add_parser("report", help="报告渲染 + CI 门禁")
    p_report.add_argument("--from", dest="from_path", help="读取已有 --json 结果")
    p_report.add_argument("--format", choices=("md", "json"), default="md", help="输出格式")
    p_report.add_argument(
        "--fail-on",
        default="",
        help="命中即以退出码 1 退出；逗号分隔，取 gap / overlap / history",
    )
    p_report.add_argument("--version", dest="versions", help="两棵树目录，逗号分隔 <A>,<B>")

    p_version = sub.add_parser("version", help="树/版本自检")
    p_version.add_argument("--zoneinfo", required=True, help="zoneinfo 树目录")
    p_version.add_argument("--zone", help="只看该 zone 是否存在")
    p_version.add_argument("--json", action="store_true", help="输出 JSON")

    return parser


def _run_version(args):
    from .zoneinfo_store import ZoneinfoStore

    store = ZoneinfoStore(args.zoneinfo)
    doc = store.describe()
    if args.zone:
        store.path_for(args.zone)  # 不存在则 EnvironmentProblem
        doc["zone"] = args.zone
        doc["zone_present"] = True
    if args.json:
        emit(dumps_json(doc))
    else:
        emit(
            "zoneinfo 树: %s\nversion: %s\nkind: %s\nzones: %d\n"
            % (doc["root"], doc["version"], doc["kind"], doc["zones"])
        )
    return EXIT_OK


def _render_windows(result, as_json):
    """把扫描结果渲染成 JSON 或 Markdown（**stdout 只含结果**）。"""
    if as_json:
        doc = {
            "year": result.year,
            "zones": result.zone,
            "windows": [item.as_dict() for item in result.windows],
            "summary": {
                "zones_scanned": result.zones_scanned,
                "windows": len(result.windows),
                "errors": list(result.errors),
            },
        }
        emit(dumps_json(doc))
        return

    lines = []
    for item in result.windows:
        lines.append(
            "%-8s %s → %s  (%dmin%s)  %s → %s  %s  source=%s"
            % (item.type,
               civil.format_local(item.start_local),
               civil.format_local(item.end_local),
               item.duration_min,
               ("+%ds" % item.residual_sec) if item.residual_sec else "",
               civil.format_offset(item.offset_before),
               civil.format_offset(item.offset_after),
               item.zone,
               item.source)
        )
    if not lines:
        lines.append("（%d 年无墙钟风险窗口）" % result.year)
    if result.errors:
        lines.append("")
        lines.append("错误 %d 处：" % len(result.errors))
        for message in result.errors:
            lines.append("  %s" % message)
    emit("\n".join(lines))


def _run_windows(args):
    """``windows`` 子命令：墙钟风险窗口（``plan/03`` §五）。

    ``--zone`` 与 ``--all`` 互斥（缺一即用法错误）。
    """
    from .windows import scan_all, scan_tree
    from .zoneinfo_store import ZoneinfoStore

    if bool(args.zone) == bool(args.all):
        raise UsageError("windows 必须且只能给出 --zone 或 --all 之一")

    store = ZoneinfoStore(args.zoneinfo)
    if args.all:
        result = scan_all(store, args.year)
    else:
        result = scan_tree(store, args.zone, args.year)

    _render_windows(result, args.json)
    if result.errors:
        # 环境不满足（这台机器上有 zone 读不了）——不中断整批，但退出码必须反映出来
        sys.stderr.write("%s: %d 个 zone 扫描失败\n" % (PROG, len(result.errors)))
        return EXIT_ENV
    return EXIT_OK


def _render_diff(result, as_json):
    """``diff`` 的渲染（**stdout 只含结果**；无时间戳）。"""
    if as_json:
        emit(dumps_json(result.as_dict()))
        return

    summary = result.summary
    lines = [
        "版本差异分类: %s → %s" % (summary["old_version"], summary["new_version"]),
        "窗口: %s" % ("全历史" if summary["window"] is None
                      else "%d-%d" % (summary["window"][0], summary["window"][1])),
        "比较 zone: %d    变更: %d" % (summary["zones_compared"], summary["changes"]),
    ]
    for cls in ("history_reinterpreted", "future_rule", "abbreviation_only", "alias_only"):
        lines.append("  %-24s %d" % (cls, summary["classes"][cls]))
    if summary["unclassified"]:
        lines.append("  四类均不成立（如实列出）: %s" % ", ".join(summary["unclassified"]))
    lines.append("")
    for item in result.changes:
        lines.append("%-26s %-24s %-6s %s → %s"
                     % (item.zone, item.class_, item.evidence, item.before, item.after))
    if not result.changes:
        lines.insert(len(lines) - 1, "（两棵树无可分类差异）")
    if result.errors:
        lines.append("")
        lines.append("错误 %d 处：" % len(result.errors))
        for message in result.errors:
            lines.append("  %s" % message)
    emit("\n".join(lines))


def _run_diff(args):
    """``diff`` 子命令：两棵树的版本差异分类（``plan/03`` §六）。"""
    from .diff import diff_trees
    from .zoneinfo_store import ZoneinfoStore

    old_store = ZoneinfoStore(args.old)
    new_store = ZoneinfoStore(args.new)
    result = diff_trees(old_store, new_store, window=args.window, zone=args.zone)

    _render_diff(result, args.json)
    if result.errors:
        # 环境不满足（这台机器上有 zone 读不了）——不中断整批，但退出码必须反映出来
        sys.stderr.write("%s: %d 个 zone 比较失败\n" % (PROG, len(result.errors)))
        return EXIT_ENV
    return EXIT_OK


def _render_audit(result, as_json):
    """``audit`` 的渲染（**stdout 只含结果**；无时间戳）。"""
    if as_json:
        emit(dumps_json(result.as_dict()))
        return

    summary = result.summary
    lines = [
        "清单审计: %s（树: %s）" % (summary["zone"], " → ".join(summary["versions"])),
        "行数: %d    坏行: %d" % (summary["rows"], summary["invalid"]),
    ]
    counts = summary["by_status"]
    lines.append("  " + "  ".join("%s=%d" % (status, counts.get(status, 0))
                                  for status in audit.STATUS_ORDER))
    lines.append("")
    for row in result.rows:
        if row.status == audit.INVALID:
            lines.append("%-14s %-16s %-15s %s"
                         % (row.id, row.local, row.status, row.invalid_reason))
            continue
        utcs = ", ".join(civil.format_utc(utc) for utc in row.utc_candidates) or "-"
        lines.append("%-14s %-19s %-15s %s%s"
                     % (row.id, row.local, row.status, utcs,
                        ("  " + row.note) if row.note else ""))
    if not result.rows:
        lines.append("（清单为空）")
    emit("\n".join(lines))


def _resolve_trees(args):
    """``audit`` / ``report`` 的树解析。

    - ``--version A,B``：两棵目录（K16 / Q4），**每棵都必须带 ``provenance.json``**，否则退 3。
    - ``--zoneinfo <dir>``：单棵树。
    两者互斥（缺一即用法错误）。
    """
    from .zoneinfo_store import ZoneinfoStore

    if args.versions:
        if getattr(args, "zoneinfo", None):
            raise UsageError("--version 与 --zoneinfo 互斥")
        parts = [part.strip() for part in str(args.versions).split(",")]
        if len(parts) != 2 or not all(parts):
            raise UsageError("--version 只接受两个树目录，逗号分隔 <A>,<B>；实得 %r" % (args.versions,))
        stores = []
        for part in parts:
            store = ZoneinfoStore(part)          # 不存在 → EnvironmentProblem（退 3）
            if not os.path.isfile(os.path.join(store.root, "provenance.json")):
                raise EnvironmentProblem(
                    "版本目录缺 provenance.json: %s（Q4：--version 只收本工具认识的树）" % part)
            stores.append(store)
        return stores

    if not getattr(args, "zoneinfo", None):
        raise UsageError("必须给出 --zoneinfo <dir> 或 --version <A>,<B> 之一")
    return [ZoneinfoStore(args.zoneinfo)]


def _run_audit(args):
    """``audit`` 子命令：本地时刻清单审计（``plan/03`` §七）。"""
    if not args.zone:
        raise UsageError("audit 需要 --zone <name>（清单里不含 zone）")
    if bool(args.times) == bool(args.daily):
        raise UsageError("audit 必须且只能给出 --times 或 --daily 之一")

    stores = _resolve_trees(args)

    if args.daily:
        rows = audit.expand_daily(args.daily, args.year)
    else:
        if args.year is not None:
            raise UsageError("--year 只与 --daily 搭配使用")
        try:
            text = read_text(args.times)
        except (IOError, OSError) as exc:
            raise EnvironmentProblem("清单读不了: %s: %s" % (args.times, exc))
        rows = audit.parse_times(text)

    result = audit.audit_rows(rows, args.zone, versions=stores)
    _render_audit(result, args.json)

    if result.summary["invalid"]:
        # 坏行**不静默跳过**：结果照常输出，但整体退 4（`data/README.md` §4.4）
        sys.stderr.write("%s: %d 行清单无法解析（已逐行记 INVALID）\n"
                         % (PROG, result.summary["invalid"]))
        return EXIT_INVALID_INPUT
    return EXIT_OK


def _report_inputs(args):
    """``report`` 的输入：``--from <json>``（已有结果）或串跑子命令。"""
    if not args.from_path:
        raise UsageError("report 需要 --from <json>（串跑形态见 plan/03 §一）")
    try:
        text = read_text(args.from_path)
    except (IOError, OSError) as exc:
        raise EnvironmentProblem("结果集读不了: %s: %s" % (args.from_path, exc))
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise InvalidInput("结果集不是合法 JSON: %s: %s" % (args.from_path, exc))
    if not isinstance(doc, dict):
        raise InvalidInput("结果集根节点必须是对象: %s" % (args.from_path,))
    return doc


def _first_present(*values):
    """取第一个**非 None 且非空串**的值（``0`` 是合法值，不能被 ``or`` 链吞掉）。"""
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        if isinstance(value, (list, tuple)) and not value:
            continue
        return value
    return None


def _derive_header(source):
    """从结果集推导报告头三字段。

    ``data_version`` / ``zones_covered`` 是**输入侧事实**（被审计的树），能从各子命令的
    ``--json`` 里取到；取不到就让 :func:`report.build_report` 抛 ``ReportIncomplete``（退 3）。
    ``generated_at`` 由本层注入（Q3：``SOURCE_DATE_EPOCH`` 优先，否则当前 UTC）——
    ``report`` 模块自己不读时钟。
    """
    header = source.get("report_header")
    header = header if isinstance(header, dict) else {}
    summary = source.get("summary")
    summary = summary if isinstance(summary, dict) else {}

    data_version = _first_present(
        source.get("data_version"),
        header.get("data_version"),
        summary.get("versions"),
        summary.get("version"),
    )
    if isinstance(data_version, (list, tuple)):
        data_version = " / ".join(str(item) for item in data_version)

    zones_covered = _first_present(
        source.get("zones_covered"),
        header.get("zones_covered"),
        summary.get("zones_covered"),
        summary.get("zones_scanned"),
        summary.get("zones_compared"),
    )
    generated_at = _first_present(header.get("generated_at"),
                                  source.get("generated_at"),
                                  report.resolve_generated_at())
    return data_version, zones_covered, generated_at


def _run_report(args):
    """``report`` 子命令：报告渲染 + CI 门禁（``plan/03`` §八）。"""
    source = _report_inputs(args)
    fail_on = report.parse_fail_on(args.fail_on)

    data_version, zones_covered, generated_at = _derive_header(source)
    if args.versions:
        # ``--version A,B`` 是报告头的**输入侧来源**（Q4：两个目录路径）——
        # 结果集里没写版本标签时用它补，而不是去猜。
        stores = _resolve_trees(args)
        data_version = " / ".join(str(store.version) for store in stores)

    markdown, built = report.build_report(
        [source], data_version=data_version,
        zones_covered=zones_covered, generated_at=generated_at)

    if args.format == "json":
        emit(dumps_json(built))
    else:
        emit(markdown)
    return report.report_exit_code(built, fail_on)


def main(argv=None):
    """返回退出码（不直接 ``sys.exit``，便于测试）。"""
    _ensure_utf8_stdio()
    parser = build_parser()
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except UsageError as exc:
        sys.stderr.write("%s: 用法错误: %s\n" % (PROG, exc.message))
        sys.stderr.write("试试 `%s --help`\n" % PROG)
        return EXIT_USAGE

    try:
        if args.command is None:
            parser.print_help(sys.stderr)
            return EXIT_USAGE
        if args.command == "version":
            return _run_version(args)
        if args.command == "windows":
            return _run_windows(args)
        if args.command == "diff":
            return _run_diff(args)
        if args.command == "audit":
            return _run_audit(args)
        if args.command == "report":
            return _run_report(args)
        # argparse 的 choices 已挡住未知子命令；走到这里是程序缺陷，不是用户输入。
        raise UsageError("未知子命令: %r" % (args.command,))
    except TzAuditError as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc.message))
        return exc.exit_code
    except KeyboardInterrupt:  # pragma: no cover
        sys.stderr.write("%s: 已中断\n" % PROG)
        return 130
    except Exception as exc:  # 未预期异常：不把栈写到 stdout
        sys.stderr.write("%s: internal error: %s: %s\n" % (PROG, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
