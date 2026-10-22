# -*- coding: utf-8 -*-
"""本地时间清单审计 —— 契约见 ``plan/03`` §七；存在性口径只引用 ``data/README.md`` §4.6。

判定顺序**固定**（:data:`STATUS_ORDER`，取第一条成立者）：

1. ``INVALID`` —— 清单行本身解析失败（缺列 / 时间非法 / 空行）。
2. ``GAP`` —— 主树 ``resolve_local`` 返回 **0** 个 UTC 候选。
3. ``OVERLAP`` —— 主树返回 **≥2** 个 UTC 候选。
4. ``VERSION_CHANGED`` —— **只在给了两棵树时**可能成立：两树候选的 **UTC 集合不同**。
5. ``OK`` —— 恰好 1 个候选，且（两树模式下）两树候选一致。

顺序是判据的一部分：一条"旧树 GAP、新树存在"的行，按顺序必须报 ``GAP``，
不能被 ``VERSION_CHANGED`` 抢先（``tests/test_audit.py`` 用顺序变异锚住这条）。

**行序保持输入序**（不排序、不去重）：清单是用户的时刻表，重排会让报告与原始清单错位。
同一行的多候选按 UTC 升序（``timeline.resolve_local`` 已保证）。

``INVALID`` 行**不静默跳过**：进结果 + 计数；调用方见到 ``summary["invalid"] > 0``
必须以退出码 4 收尾（``data/README.md`` §4.4），**其余行照常判定**。

依赖面（K3）：只 import ``errors`` / ``timeline`` / ``civil``——**不碰** ``tzif`` /
``posix_tz`` / ``zoneinfo_store``。树对象由调用方（``cli``）传入，与 ``windows`` 同口径。
"""

from __future__ import print_function

from . import civil, timeline
from .errors import UsageError

INVALID = "INVALID"
GAP = "GAP"
OVERLAP = "OVERLAP"
VERSION_CHANGED = "VERSION_CHANGED"
OK = "OK"

#: 判定顺序（第一位优先）。改这个元组成员或顺序 = 口径变更，`plan/03` §七 同步。
STATUS_ORDER = (INVALID, GAP, OVERLAP, VERSION_CHANGED, OK)

#: ``--daily`` 展开结果的行 id 前缀（与等价清单的 id 只差这个前缀）。
DAILY_ID_PREFIX = "daily-"

#: 清单没有 id 时自动生成的前缀（``line-001`` 起）。
LINE_ID_PREFIX = "line-"

#: 给 tail 物化定界时在行覆盖范围外扩的余量（秒）。查找走解析式求值，
#: 所以余量只影响"物化出哪些段"，不影响候选正确性；取 2 天覆盖墙钟/UTC 的年份错位。
_WINDOW_MARGIN_SEC = 2 * 86400


class Input(object):
    """一行输入（解析后的中间件，不进 ``--json``）。

    ``local`` 是墙钟 epoch（int）；解析失败时为 ``None``，原因进 ``invalid_reason``，
    原文留在 ``text``（``INVALID`` 行要把用户写的东西原样回显，便于定位）。
    """

    __slots__ = ("id", "local", "invalid_reason", "text")

    def __init__(self, id_, local, invalid_reason="", text=""):
        self.id = id_
        self.local = local
        self.invalid_reason = invalid_reason
        self.text = text

    def __repr__(self):  # pragma: no cover - 调试用
        return "Input(%r, %r, %r)" % (self.id, self.local, self.invalid_reason)


class Row(object):
    """一条输入时刻的判定（字段与 ``plan/03`` §七 冻结的六个一一对应）。

    - ``local``：规范化后的墙钟串；``INVALID`` 行回显清单原文
    - ``utc_candidates``：**主树**的 UTC 候选（epoch，升序）；GAP 行为空
    - ``note``：人读补充（两树差异时写明两侧候选）；``OK`` 行为空
    """

    __slots__ = ("id", "local", "status", "utc_candidates", "note", "invalid_reason")

    def __init__(self, id_, local, status, utc_candidates=(), note="", invalid_reason=""):
        self.id = id_
        self.local = local
        self.status = status
        self.utc_candidates = list(utc_candidates)
        self.note = note
        self.invalid_reason = invalid_reason

    def __repr__(self):  # pragma: no cover - 调试用
        return "Row(%s, %s, %s, %r)" % (self.id, self.local, self.status, self.utc_candidates)

    def as_dict(self):
        """``--json`` 的一条记录（**不含**任何时间戳）。"""
        return {
            "id": self.id,
            "local": self.local,
            "status": self.status,
            "utc_candidates": [civil.format_utc(utc) for utc in self.utc_candidates],
            "note": self.note,
            "invalid_reason": self.invalid_reason,
        }


class AuditResult(object):
    """一次清单审计的结果集。``summary`` 可直接进 ``--json``。"""

    __slots__ = ("rows", "summary")

    def __init__(self, rows, summary):
        self.rows = rows
        self.summary = summary

    def as_dict(self):
        return {"rows": [row.as_dict() for row in self.rows], "summary": self.summary}


class _Facts(object):
    """一行在（可能多棵）树下的判定事实——判定函数只读这些，不重复解析。"""

    __slots__ = ("resolved",)

    def __init__(self, resolved):
        self.resolved = resolved

    @property
    def primary(self):
        return self.resolved[0]

    @property
    def primary_count(self):
        return len(self.resolved[0])

    @property
    def versions_differ(self):
        """两树候选的 **UTC 集合**是否不同（候选数不同也算不同）。"""
        if len(self.resolved) < 2:
            return False
        first = set(item.utc for item in self.resolved[0])
        for other in self.resolved[1:]:
            if set(item.utc for item in other) != first:
                return True
        return False


def _holds_gap(facts):
    return facts.primary_count == 0


def _holds_overlap(facts):
    # 候选数 > 2 只可能出现在极旧的 LMT 段；语义上同样是"这段墙钟不唯一"。
    return facts.primary_count >= 2


def _holds_version_changed(facts):
    return facts.versions_differ


def _holds_ok(facts):
    # 兜底项：前四条都不成立时才算 OK（顺序由 STATUS_ORDER 保证它是最后一项）。
    return True


#: 判定表：状态 → 判据。``INVALID`` 在解析层决定，这里恒不成立。
_HOLDS = {
    INVALID: lambda facts: False,
    GAP: _holds_gap,
    OVERLAP: _holds_overlap,
    VERSION_CHANGED: _holds_version_changed,
    OK: _holds_ok,
}


# ---------------------------------------------------------------- 清单解析


def parse_times(text):
    """清单文本 → ``list[Input]``（**行序即输入序**）。

    两种承载形式（`plan/03` §七）：

    - ``id,local_time``：一行两列；列数不是 2 / 缺 id → ``INVALID``。
    - 一行一个时间戳：无 id 时自动 ``line-<行号三位>``。

    空行记 ``INVALID``（不静默丢弃），但**文件末尾**因换行产生的空行不算一行。
    """
    if text.startswith(u"\ufeff"):
        text = text[1:]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    out = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        fallback_id = "%s%03d" % (LINE_ID_PREFIX, number)
        if not line:
            out.append(Input(fallback_id, None, "空行", ""))
            continue
        if "," in line:
            parts = line.split(",")
            if len(parts) != 2:
                out.append(Input(fallback_id, None,
                                 "列数不是 2（需 id,local_time，实得 %d 列）" % len(parts), line))
                continue
            id_, local_text = parts[0].strip(), parts[1].strip()
            if not id_:
                out.append(Input(fallback_id, None, "缺 id", line))
                continue
        else:
            id_, local_text = fallback_id, line
        try:
            local = civil.parse_local(local_text)
        except ValueError as exc:
            out.append(Input(id_, None, "时间无法解析: %s" % exc, local_text))
            continue
        out.append(Input(id_, local, "", local_text))
    return out


def parse_clock(text):
    """``HH:MM``（或 ``HH:MM:SS``）→ ``(时, 分, 秒)``；非法即用法错误（退 2）。"""
    parts = str(text).strip().split(":")
    if len(parts) not in (2, 3):
        raise UsageError("--daily 只接受 HH:MM（不接受 cron 表达式）：%r" % (text,))
    try:
        nums = [int(part) for part in parts]
    except (TypeError, ValueError):
        raise UsageError("--daily 的时刻不是整数：%r" % (text,))
    if len(nums) == 2:
        nums.append(0)
    hour, minute, second = nums
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise UsageError("--daily 的时刻越界：%r" % (text,))
    return hour, minute, second


def expand_daily(hhmm, year):
    """``--daily HH:MM`` + ``year`` → 该年每天一条 :class:`Input`。

    **缺 ``year`` 即用法错误（退 2）**：本项目不读时钟，不把"当前年"当缺省。
    id 形如 ``daily-YYYY-MM-DD``（与等价清单只差前缀）。
    """
    if year is None:
        raise UsageError("--daily 必须同时给出 --year（本项目不默认当前年，不读时钟）")
    hour, minute, second = parse_clock(hhmm)
    out = []
    for month in range(1, 13):
        for day in range(1, civil.days_in_month(year, month) + 1):
            local = civil.epoch_from_local_naive(year, month, day, hour, minute, second)
            out.append(Input("%s%04d-%02d-%02d" % (DAILY_ID_PREFIX, year, month, day),
                             local, "", civil.format_local(local)))
    return out


# ---------------------------------------------------------------- 判定


def _row_window(rows):
    """按行覆盖的墙钟范围给 tail 物化定界（``(None, None)`` = 没有可判定的行）。"""
    values = [item.local for item in rows if item.local is not None]
    if not values:
        return None, None
    return min(values) - _WINDOW_MARGIN_SEC, max(values) + _WINDOW_MARGIN_SEC


def _format_utcs(resolutions):
    if not resolutions:
        return "(无)"
    return ", ".join(civil.format_utc(item.utc) for item in resolutions)


def _note(status, facts):
    """人读补充。**只由输入决定**（无时间戳、无机器信息）。"""
    if status == GAP:
        return "0 个 UTC 候选（该墙钟不存在）"
    if status == OVERLAP:
        first, second = facts.primary[0], facts.primary[1]
        return "%d 个 UTC 候选（偏移差 %ds）" % (
            facts.primary_count, abs(second.offset_sec - first.offset_sec))
    if status == VERSION_CHANGED:
        parts = ["树%d=%s" % (index + 1, _format_utcs(resolved))
                 for index, resolved in enumerate(facts.resolved)]
        return "两版候选不同: " + " / ".join(parts)
    return ""


def _judge(item, timelines):
    """单行判定：按 :data:`STATUS_ORDER` 遍历，取**第一条成立者**。"""
    if item.invalid_reason:
        return Row(item.id, item.text, INVALID, (), "", item.invalid_reason)

    resolved = [timeline.resolve_local(item.local, tl) for tl in timelines]
    facts = _Facts(resolved)
    local_text = civil.format_local(item.local)
    for status in STATUS_ORDER:
        if _HOLDS[status](facts):
            return Row(item.id, local_text, status,
                       [res.utc for res in facts.primary], _note(status, facts))
    raise AssertionError("STATUS_ORDER 未命中——判定表被改坏")  # pragma: no cover


def audit_rows(rows, zone, versions=None):
    """逐行判定 ``rows``（:func:`parse_times` / :func:`expand_daily` 的产物）。

    ``versions`` = 树对象的序列：**1 棵** = 单版本模式（``VERSION_CHANGED`` 不可能成立）；
    **2 棵** = 双版本模式（``--version A,B``：A 为主树，候选与基准都以 A 为准）。
    树对象由调用方给（``cli`` 负责"路径必须存在且带 ``provenance.json``"的校验）。
    """
    stores = tuple(versions or ())
    if not stores:
        raise UsageError("audit 需要一棵 zoneinfo 树（--zoneinfo <dir> 或 --version <A>,<B>）")
    if len(stores) > 2:
        raise UsageError("audit 最多接受两棵树（--version <A>,<B>）")

    window_start, window_end = _row_window(rows)
    timelines = [
        timeline.load_timeline(zone, store, window_start=window_start, window_end=window_end)
        for store in stores
    ]

    out = []
    counts = dict((status, 0) for status in STATUS_ORDER)
    for item in rows:
        row = _judge(item, timelines)
        counts[row.status] += 1
        out.append(row)

    summary = {
        "zone": zone,
        "versions": [str(getattr(store, "version", "unknown")) for store in stores],
        # 本次实际解析的 zone 数：清单审计只碰一个 zone（报告头的分母，§4.5）
        "zones_covered": 1,
        "rows": len(out),
        "invalid": counts[INVALID],
        "by_status": counts,
    }
    return AuditResult(out, summary)
