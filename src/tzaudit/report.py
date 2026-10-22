# -*- coding: utf-8 -*-
"""报告与门禁 —— 契约见 ``plan/03`` §八；口径只引用 ``data/README.md`` §4.4 / §4.5。

三件事都在本模块，且**都是纯函数**（除 ``resolve_generated_at`` 外不碰外部状态）：

1. :func:`build_report` —— 把若干子命令的结果集合并成 ``(markdown, doc)`` 双轨。
   ``doc`` 可 ``--json`` 输出，``md`` 给人读；两者由**同一份 doc** 渲染，不允许各算一遍。
2. :func:`check_header` —— 报告头三字段（``data_version`` / ``zones_covered`` /
   ``generated_at``）缺一即 :class:`ReportIncomplete`（退 3）。
3. :func:`gate_exit_code` —— ``--fail-on`` 只看**结果集**，不看人读文本。

确定性纪律（K5）：``generated_at`` 是**唯一**允许的时间戳，且必须由调用方注入；
本模块**不读时钟**（``cli`` 在入口把它算好传进来，测试由此可固定值）。

依赖面（K3）：只 import ``errors``——report 不许 import ``audit`` / ``diff`` / ``windows``，
结果集一律按"字典或带 ``as_dict()`` 的对象"接收（鸭子类型）。这条由
``tests/test_architecture.py::ALLOWED`` 守门。
"""

from __future__ import print_function

import os
import time

from .errors import EXIT_GATE_HIT, EXIT_INVALID_INPUT, EXIT_OK, ReportIncomplete, UsageError

#: 报告头三字段（缺一即不合规；口径见 ``data/README.md`` §4.5）
REPORT_REQUIRED_FIELDS = ("data_version", "zones_covered", "generated_at")

#: ``--fail-on`` 的合法枚举（固定三种，不存在第四种）
FAIL_ON_CHOICES = ("gap", "overlap", "history")

#: 结果集里三类载荷的键名（与各子命令 ``--json`` 的键一致）
SECTION_KEYS = ("windows", "changes", "rows")

#: Markdown 三个表格的**固定列序**（`plan/03` §八：列序固定，不随数据变）
WINDOW_COLUMNS = ("type", "zone", "start_local", "end_local", "duration_min",
                  "residual_sec", "offset_before", "offset_after", "source")
CHANGE_COLUMNS = ("zone", "class", "evidence", "before", "after", "note")
ROW_COLUMNS = ("id", "local", "status", "utc_candidates", "note", "invalid_reason")


#: 报告时间戳的形态（``generated_at`` 是**唯一**允许的时间戳）
GENERATED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

#: 冻结时钟的环境变量（决策 Q3）：设了就按它算 ``generated_at``，不看系统时钟。
SOURCE_DATE_EPOCH_ENV = "SOURCE_DATE_EPOCH"


def resolve_generated_at(environ=None):
    """算 ``generated_at`` —— 本模块是**唯一**允许读时钟的地方（K5 / ``plan/03`` §八）。

    ``SOURCE_DATE_EPOCH`` 优先（测试与可复现构建的冻结口，决策 Q3）；否则取当前 UTC。
    ``build_report`` **不**调它：时间戳由调用方注入，测试才能固定值。

    返回 ``YYYY-MM-DDTHH:MM:SSZ``。
    """
    env = os.environ if environ is None else environ
    frozen = env.get(SOURCE_DATE_EPOCH_ENV)
    if frozen not in (None, ""):
        try:
            seconds = int(str(frozen).strip())
        except ValueError:
            raise UsageError("%s 必须是整秒：%r" % (SOURCE_DATE_EPOCH_ENV, frozen))
        stamp = time.gmtime(seconds)
    else:
        # ``time.gmtime()``（不传参）= 当前 UTC；刻意不用 epoch 秒再换算：
        # 包里"读时钟"只出现在这一行，且永远走 UTC，不碰本地时区/夏令时。
        stamp = time.gmtime()
    return time.strftime(GENERATED_AT_FORMAT, stamp)


# ---------------------------------------------------------------- 结果集归一


def _as_dict(result):
    """结果集 → 普通字典（对象有 ``as_dict()`` 就用它；已是字典就原样）。"""
    if isinstance(result, dict):
        return result
    as_dict = getattr(result, "as_dict", None)
    if as_dict is None:
        raise ReportIncomplete("结果集既不是 dict 也没有 as_dict()：%r" % (type(result).__name__,))
    return as_dict()


def _collect(results):
    """把若干结果集摊平成 ``{windows, changes, rows, summaries}``。"""
    buckets = dict((key, []) for key in SECTION_KEYS)
    summaries = []
    for result in results or ():
        doc = _as_dict(result)
        for key in SECTION_KEYS:
            value = doc.get(key)
            if value:
                buckets[key].extend(value)
        if doc.get("summary") is not None:
            summaries.append(doc["summary"])
    return buckets, summaries


def _require_header(data_version, zones_covered, generated_at):
    """三字段归一 + 校验。**缺任一即退 3**（``data/README.md`` §4.5）。"""
    header = {
        "data_version": data_version,
        "zones_covered": zones_covered,
        "generated_at": generated_at,
    }
    missing = [name for name in REPORT_REQUIRED_FIELDS if header[name] in (None, "")]
    if missing:
        raise ReportIncomplete("报告头缺字段: %s" % ", ".join(missing))
    if not isinstance(zones_covered, int) or isinstance(zones_covered, bool):
        raise ReportIncomplete("zones_covered 必须是整数：%r" % (zones_covered,))
    if zones_covered < 0:
        raise ReportIncomplete("zones_covered 不得为负：%r" % (zones_covered,))
    return header


def check_header(doc):
    """校验报告头三字段。缺任一 → :class:`ReportIncomplete`。"""
    if not isinstance(doc, dict):
        raise ReportIncomplete("报告根节点必须是对象")
    header = doc.get("report_header", doc)
    missing = [name for name in REPORT_REQUIRED_FIELDS if header.get(name) in (None, "")]
    if missing:
        raise ReportIncomplete("报告头缺字段: %s" % ", ".join(missing))
    return header


# ---------------------------------------------------------------- 门禁


def parse_fail_on(text):
    """``--fail-on`` 的字符串 → 集合。非法值**显式拒绝**（退 2），不静默忽略。

    空串 → 空集合（= 不开门禁）。逗号分隔，允许空白与重复。
    """
    if text is None:
        return set()
    chosen = set()
    for chunk in str(text).replace("，", ",").split(","):
        item = chunk.strip().lower()
        if not item:
            continue
        if item not in FAIL_ON_CHOICES:
            raise UsageError("--fail-on 只接受 %s（逗号分隔）；实得 %r"
                             % (" / ".join(FAIL_ON_CHOICES), chunk.strip()))
        chosen.add(item)
    return chosen


def gate_exit_code(doc, fail_on):
    """按结果集计算门禁退出码（只看结果集，不看人读文本）。

    ``fail_on`` 是 ``FAIL_ON_CHOICES`` 的子集；未知值应由 CLI 层以用法错误拒绝
    （:func:`parse_fail_on`）。这里对未知值抛 ``ValueError``——那是程序误用，不是用户输入。
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
        hit = hit or any(item.get("type") == "GAP" for item in windows)
        hit = hit or any(item.get("status") == "GAP" for item in rows)
    if "overlap" in fail_on:
        hit = hit or any(item.get("type") == "OVERLAP" for item in windows)
        hit = hit or any(item.get("status") == "OVERLAP" for item in rows)
    if "history" in fail_on:
        hit = hit or any(item.get("class") == "history_reinterpreted" for item in changes)

    return EXIT_GATE_HIT if hit else EXIT_OK


def has_invalid_rows(doc):
    """结果集里是否存在 ``INVALID`` 清单行（`data/README.md` §4.4：整体退 4）。"""
    return any(item.get("status") == "INVALID" for item in (doc.get("rows") or []))


def report_exit_code(doc, fail_on):
    """``report`` 的退出码：**输入无效（4）优先于门禁命中（1）**。

    理由：坏行说明结果集本身不完整，此时"门禁是否命中"不是一个可信的结论；
    先让调用方去修清单，再谈门禁（§4.4 的码表是全部子命令共用的）。
    """
    if has_invalid_rows(doc):
        return EXIT_INVALID_INPUT
    return gate_exit_code(doc, fail_on)


# ---------------------------------------------------------------- 渲染


def _cell(value):
    """Markdown 单元格：``None`` → 空；换行/竖线转义（不破坏表格）。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value)
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _table(columns, rows):
    lines = ["| " + " | ".join(columns) + " |",
             "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_cell(row.get(column)) for column in columns) + " |")
    return lines


def _count_by_status(rows):
    out = {}
    for row in rows:
        status = row.get("status")
        if status is None:
            continue
        out[status] = out.get(status, 0) + 1
    return out


def build_report(results, data_version, zones_covered, generated_at):
    """构造 ``(markdown, doc)`` 双轨报告。

    ``results``：结果集序列——每项是 ``dict`` 或带 ``as_dict()`` 的对象
    （``windows.ScanResult`` / ``diff.DiffResult`` / ``audit.AuditResult`` 都符合）。
    三个载荷键（``windows`` / ``changes`` / ``rows``）各自摊平；顺序**保持调用方给的顺序**
    （各子命令已按自己的口径排好，报告层不再重排）。

    ``data_version`` / ``zones_covered`` / ``generated_at`` **必须由调用方给**：
    前两个来自被审计的树，最后一个来自 ``cli``（测试注入固定值）。本函数不读时钟。
    """
    header = _require_header(data_version, zones_covered, generated_at)
    buckets, summaries = _collect(results)

    doc = {
        "report_header": header,
        "summary": {
            "windows": len(buckets["windows"]),
            "changes": len(buckets["changes"]),
            "rows": len(buckets["rows"]),
            "invalid_rows": sum(1 for row in buckets["rows"] if row.get("status") == "INVALID"),
            "row_status": _count_by_status(buckets["rows"]),
            "sections": summaries,
        },
    }
    for key in SECTION_KEYS:
        if buckets[key]:
            doc[key] = buckets[key]

    return _render_markdown(doc), doc


def _render_markdown(doc):
    header = doc["report_header"]
    summary = doc["summary"]
    lines = [
        "# tzaudit 报告",
        "",
        "- data_version: %s" % _cell(header["data_version"]),
        "- zones_covered: %d" % header["zones_covered"],
        "- generated_at: %s" % _cell(header["generated_at"]),
        "",
        "## 汇总",
        "",
        "| 项 | 数 |",
        "|---|---|",
        "| 墙钟窗口 | %d |" % summary["windows"],
        "| 版本变更 | %d |" % summary["changes"],
        "| 清单行 | %d |" % summary["rows"],
        "| 清单坏行 | %d |" % summary["invalid_rows"],
    ]

    windows = doc.get("windows") or []
    lines.extend(["", "## 墙钟风险窗口", ""])
    if windows:
        lines.extend(_table(WINDOW_COLUMNS, windows))
    else:
        lines.append("（无）")

    changes = doc.get("changes") or []
    lines.extend(["", "## 版本差异", ""])
    if changes:
        lines.extend(_table(CHANGE_COLUMNS, changes))
    else:
        lines.append("（无）")

    rows = doc.get("rows") or []
    lines.extend(["", "## 清单判定", ""])
    if rows:
        lines.extend(_table(ROW_COLUMNS, rows))
    else:
        lines.append("（无）")

    return "\n".join(lines) + "\n"
