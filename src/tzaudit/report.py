# -*- coding: utf-8 -*-
"""报告与门禁 —— 契约见 ``plan/03`` §八。

骨架期已实现的是**纯函数部分**（头部字段契约 + 门禁退出码），它们不依赖任何解析结果，
因此可以在没有数据的情况下被测试锁住；Markdown/JSON 渲染由 M5 落地。
"""

from __future__ import print_function

from .errors import NotImplementedYet, ReportIncomplete

#: 报告头三字段（缺一即不合规；口径见 ``data/README.md`` §4.5）
REPORT_REQUIRED_FIELDS = ("data_version", "zones_covered", "generated_at")

#: ``--fail-on`` 的合法枚举（固定三种，不存在第四种）
FAIL_ON_CHOICES = ("gap", "overlap", "history")


def check_header(doc):
    """校验报告头三字段。缺任一 → :class:`ReportIncomplete`。"""
    if not isinstance(doc, dict):
        raise ReportIncomplete("报告根节点必须是对象")
    header = doc.get("report_header", doc)
    missing = [name for name in REPORT_REQUIRED_FIELDS if header.get(name) in (None, "")]
    if missing:
        raise ReportIncomplete("报告头缺字段: %s" % ", ".join(missing))
    return header


def gate_exit_code(doc, fail_on):
    """按结果集计算门禁退出码（只看结果集，不看人读文本）。

    ``fail_on`` 是 ``FAIL_ON_CHOICES`` 的子集；未知值应由 CLI 层以用法错误拒绝。
    """
    fail_on = set(fail_on or ())
    unknown = fail_on - set(FAIL_ON_CHOICES)
    if unknown:
        raise ValueError("unknown --fail-on value: %s" % ", ".join(sorted(unknown)))

    windows = doc.get("windows") or []
    changes = doc.get("changes") or []
    rows = doc.get("rows") or []

    hit = False
    if "gap" in fail_on:
        hit = hit or any(w.get("type") == "GAP" for w in windows)
        hit = hit or any(r.get("status") == "GAP" for r in rows)
    if "overlap" in fail_on:
        hit = hit or any(w.get("type") == "OVERLAP" for w in windows)
        hit = hit or any(r.get("status") == "OVERLAP" for r in rows)
    if "history" in fail_on:
        hit = hit or any(c.get("class") == "history_reinterpreted" for c in changes)

    from .errors import EXIT_GATE_HIT, EXIT_OK

    return EXIT_GATE_HIT if hit else EXIT_OK


def build_report(results, data_version, zones_covered, generated_at):
    """构造 Markdown + JSON 双轨报告。M5 实现。"""
    raise NotImplementedYet("报告渲染尚未实现（M5）；契约见 plan/03 §八")
