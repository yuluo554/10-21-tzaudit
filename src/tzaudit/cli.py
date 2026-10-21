# -*- coding: utf-8 -*-
"""命令行入口 —— 契约见 ``plan/03`` §一 / §九。

**唯一**读 ``sys.argv`` 的地方；测试一律传 ``argv``。
退出码语义单点在 ``errors`` / ``data/README.md`` §4.4。
"""

from __future__ import print_function

import argparse
import json
import sys

from . import __version__, civil
from .errors import (
    EXIT_ENV,
    EXIT_OK,
    EXIT_USAGE,
    NotImplementedYet,
    TzAuditError,
    UsageError,
)
from .serialize import dumps_json, emit

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


def _unimplemented(command):
    """尚未落地的子命令（M3 后只剩 ``diff`` / ``audit`` / ``report``）。

    退出码 5（功能未就绪）是**临时**语义：每个子命令落地时在同一提交里退役它
    （`errors` 常量 → 本函数 → `tests/test_exit_codes.py` → 文档，四处同步）。
    """
    raise NotImplementedYet(
        "子命令 %s 的解析层尚未实现（见 plan/03）；当前可用：version、windows"
        % command
    )


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
        return _unimplemented(args.command)
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
