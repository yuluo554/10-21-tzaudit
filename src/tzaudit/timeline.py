# -*- coding: utf-8 -*-
"""双引擎合并（TZif 表 + POSIX tail）与本地反解 —— 契约见 ``plan/03`` §四。

两条引擎的边界（``plan/02`` §2.2，唯一实现点）：

- **表段**：TZif 的显式转换点，覆盖 ``[首个转换点, 最后一个转换点)``，``source="table"``。
  首转换点之前用 ``TzifData.initial``（RFC 8536：第一条标准时类型）。
- **tail 段**：``utc >= table_end_utc`` 之后按 POSIX 规则**逐年展开**，``source="tail"``。
  无 footer（``tail is None``）时沿用最后一个 offset，表到无穷。
- **冲突**：显式转换点优先；tail 只在其后生效。**不做事后"修正"**。

展开上限（`plan/05` R2）：``请求窗口末端 + 1 年``。展开起点可早于 1970 —— slim 树的历史区间
也可能靠 tail，所以按**日历年**回推，不从"现在"起算（本模块不读时钟）。

``/time`` 是**墙钟秒**（K9 / PITFALL-WALLSEC）：规则给出的时刻先当"本地那天的墙钟"，
再用**转换前**的 offset 换成 UTC（起跳用 std、回拨用 dst）——这就是 ``plan/03`` §三
测试点 3 断言的 ``M3.2.0/2`` 在 NY 得 ``07:00Z``（而不是 ``02:00Z``）的来历。

存在性**只由候选个数决定**（K10 / PITFALL-FOLD-GAP）：0 = GAP，1 = OK，2 = OVERLAP；
``fold`` 只用于在两个候选里**选择**，不参与存在性判断。
"""

from __future__ import print_function

from . import civil, posix_tz, tzif

#: 时间线两端的哨兵（int，避免 ``None`` 参与二分；远大于任何 64 位 epoch 的实用范围）
NEG_INFINITY = -(1 << 62)
POS_INFINITY = (1 << 62)

#: 调用方不传窗口时的 tail 展开跨度（年）。**不是产品语义**，只是防无限展开的安全上限；
#: M3/M4 一律传显式窗口，届时以窗口末端 + 1 年为准（`plan/05` R2）。
DEFAULT_TAIL_YEARS = 30

_SECONDS_PER_DAY = civil.SECONDS_PER_DAY

#: 平年每月天数（``Jn`` 的日期映射用；**必须**忽略 2/29）
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


class Segment(object):
    """时间线的一段：``[utc_start, utc_end)`` 内 offset 恒定。"""

    __slots__ = ("utc_start", "utc_end", "offset_sec", "abbr", "is_dst", "source")

    def __init__(self, utc_start, utc_end, offset_sec, abbr, is_dst, source):
        self.utc_start = utc_start
        self.utc_end = utc_end
        self.offset_sec = offset_sec
        self.abbr = abbr
        self.is_dst = is_dst
        self.source = source  # "table" | "tail"

    def __repr__(self):  # pragma: no cover - 调试用
        return "Segment(%d, %d, %d, %r, %r, %r)" % (
            self.utc_start, self.utc_end, self.offset_sec, self.abbr, self.is_dst, self.source)


class Timeline(object):
    """某 zone 在某棵树下的统一时间线。字段固定（``plan/02`` §2.1）。"""

    __slots__ = ("zone", "version", "segments", "tail", "table_end_utc", "_offsets")

    def __init__(self, zone, version, segments, tail=None, table_end_utc=None):
        self.zone = zone
        self.version = version
        self.segments = segments
        self.tail = tail
        self.table_end_utc = table_end_utc
        self._offsets = None


class Resolution(object):
    """一个本地墙钟时刻的一个 UTC 候选。``fold`` = 候选序号（0/1，PEP 495 的选择位）。"""

    __slots__ = ("utc", "offset_sec", "abbr", "is_dst", "fold")

    def __init__(self, utc, offset_sec, abbr, is_dst, fold):
        self.utc = utc
        self.offset_sec = offset_sec
        self.abbr = abbr
        self.is_dst = is_dst
        self.fold = fold

    def __repr__(self):  # pragma: no cover - 调试用
        return "Resolution(%d, %d, %r, %r, fold=%d)" % (
            self.utc, self.offset_sec, self.abbr, self.is_dst, self.fold)


# ---------------------------------------------------------------- 日历工具


def _add_years(epoch, years):
    """同一月日、N 年之后（2/29 → 非闰年退到 2/28）。用于"窗口末端 + 1 年"。"""
    days, rem = divmod(int(epoch), _SECONDS_PER_DAY)
    year, month, day = civil.civil_from_days(days)
    target = year + years
    if month == 2 and day == 29 and not civil.is_leap(target):
        day = 28
    return civil.days_from_civil(target, month, day) * _SECONDS_PER_DAY + rem


def _year_of(epoch):
    return civil.civil_from_days(int(epoch) // _SECONDS_PER_DAY)[0]


def _nonleap_date(n):
    """``Jn`` 的 1–365 → (月, 日)，**按平年映射**（J60 在闰年也落 3/1）。"""
    if not 1 <= n <= 365:
        raise posix_tz.PosixTzError("Jn 越界: %r" % (n,))
    remaining = n
    for index, dim in enumerate(_MONTH_DAYS):
        if remaining <= dim:
            return index + 1, remaining
        remaining -= dim
    raise posix_tz.PosixTzError("Jn 越界: %r" % (n,))  # pragma: no cover


def _rule_local_epoch(rule, year):
    """规则在 ``year`` 年的**本地墙钟**时刻（纯日历，不含任何 offset 加减 —— K9）。"""
    if rule.kind == "J":
        month, day = _nonleap_date(rule.n)
        days = civil.days_from_civil(year, month, day)
    elif rule.kind == "N":
        # POSIX 的裸 n：0 = 1 月 1 日，**含** 2/29（闰年 n=59 就是 2/29）。
        days = civil.days_from_civil(year, 1, 1) + rule.n
    elif rule.kind == "M":
        first = civil.days_from_civil(year, rule.month, 1)
        # 1970-01-01 是星期四 → 0=周日 的编号下 weekday = (days + 4) % 7。
        weekday_of_first = (first + 4) % 7
        day = 1 + (rule.weekday - weekday_of_first) % 7 + (rule.week - 1) * 7
        dim = civil.days_in_month(year, rule.month)
        while day > dim:
            day -= 7
        days = first + day - 1
    else:  # pragma: no cover - 构造上不可达
        raise posix_tz.PosixTzError("未知规则类型: %r" % (rule.kind,))
    return days * _SECONDS_PER_DAY + rule.time_sec


def _year_transitions(tail, year):
    """tail 在 ``year`` 年的两条转换 → ``[(utc, offset, abbr, is_dst)]``（升序）。

    起跳（DST 开始）的 ``/time`` 按**标准时**解释，回拨（DST 结束）按 **DST 墙钟**解释——
    这正是 tzcode/glibc 的语义，也是 ``plan/03`` §三 测试点 3 的金标（NY ``M3.2.0/2`` → ``07:00Z``）。
    """
    start_local = _rule_local_epoch(tail.start, year)
    end_local = _rule_local_epoch(tail.end, year)
    start_utc = start_local - tail.std[0]
    end_utc = end_local - tail.dst[0]
    out = [
        (start_utc, tail.dst[0], tail.dst[1], True),
        (end_utc, tail.std[0], tail.std[1], False),
    ]
    out.sort()
    return out


def _tail_state_at(tail, utc):
    """tail 在 ``utc`` 时刻的 ``(offset_sec, abbr, is_dst)``。

    无 DST（或只有 dst 名没有规则段）时恒为 std —— 不猜"实现定义的缺省规则"。
    """
    if not tail.has_rules:
        return tail.std[0], tail.std[1], False

    year = _year_of(utc)
    best = None
    # 跨年规则（南半球 10 月起跳、次年 4 月回拨）必须看前后两年才不漏。
    for probe in (year - 1, year, year + 1):
        for entry in _year_transitions(tail, probe):
            if entry[0] <= utc and (best is None or entry[0] > best[0]):
                best = entry
    if best is None:  # pragma: no cover - 展开起点之前
        return tail.std[0], tail.std[1], False
    return best[1], best[2], best[3]


def _expand_tail(tail, from_utc, to_utc):
    """把 tail 在 ``[from_utc, to_utc)`` 内逐年展开 → 升序转换点列表。"""
    if not tail.has_rules or to_utc <= from_utc:
        return []
    first_year = _year_of(from_utc) - 1
    last_year = _year_of(to_utc) + 1
    out = []
    for year in range(first_year, last_year + 1):
        for entry in _year_transitions(tail, year):
            if from_utc <= entry[0] < to_utc:
                out.append(entry)
    out.sort()
    return out


# ---------------------------------------------------------------- 构造


def load_timeline(zone, store, window_start=None, window_end=None):
    """读文件 → 解析 → 合并成 :class:`Timeline`。

    ``window_end`` 只影响 **tail 的物化范围**（``window_end + 1 年``，`plan/05` R2），
    不影响表段。查找（``to_local`` / ``resolve_local``）对 tail 走解析式求值，
    因此窗口之外的 UTC 也能正确回答——物化段只是给 M3/M4 提供 ``source="tail"`` 证据。
    """
    data = tzif.parse(store.read_zone(zone), zone)
    tail = posix_tz.parse(data.footer) if data.footer else None

    segments = []
    transitions = data.transitions
    table_end = None
    if transitions:
        table_end = transitions[-1][0]
        initial = data.initial
        segments.append(Segment(NEG_INFINITY, transitions[0][0],
                                initial[0], initial[2], initial[1], "table"))
        # 表覆盖 ``[首个转换点, 最后一个转换点)``（plan/02 §2.2 第 2 条）：
        # 最后一个转换点之后由 tail 接管；无 tail 时最后一段到无穷。
        for index, (utc, offset_sec, is_dst, abbr) in enumerate(transitions):
            if index + 1 == len(transitions):
                if tail is not None:
                    continue
                end = POS_INFINITY
            else:
                end = transitions[index + 1][0]
            segments.append(Segment(utc, end, offset_sec, abbr, is_dst, "table"))
    elif tail is None:
        # 空表且无 tail：整条线就是 initial 的常数 offset。
        initial = data.initial
        segments.append(Segment(NEG_INFINITY, POS_INFINITY,
                                initial[0], initial[2], initial[1], "table"))

    if tail is not None:
        anchor = table_end if table_end is not None else 0
        if window_end is not None:
            horizon = _add_years(window_end, 1)
        else:
            base = window_start if window_start is not None else anchor
            horizon = _add_years(base, DEFAULT_TAIL_YEARS)
        points = _expand_tail(tail, anchor, horizon) if horizon > anchor else []
        offset_sec, abbr, is_dst = _tail_state_at(tail, anchor)
        cursor = anchor
        for utc, next_offset, next_abbr, next_is_dst in points:
            if utc > cursor:
                segments.append(Segment(cursor, utc, offset_sec, abbr, is_dst, "tail"))
            cursor = utc
            offset_sec, abbr, is_dst = next_offset, next_abbr, next_is_dst
        segments.append(Segment(cursor, POS_INFINITY, offset_sec, abbr, is_dst, "tail"))
        if table_end is None:
            # 空表 + tail：tail 负责整条线（含 anchor 之前）。
            segments[0].utc_start = NEG_INFINITY

    return Timeline(zone, getattr(store, "version", "unknown"), segments, tail, table_end)


# ---------------------------------------------------------------- 查询


def _segment_at(utc, segments):
    """二分找覆盖 ``utc`` 的段（首段从 ``NEG_INFINITY`` 起，故一定有解）。

    手写二分而不用 ``bisect``：``bisect`` 需要先物化 ``starts`` 列表，598 zone × 全量
    窗口扫描时这笔分配是纯浪费；``key=`` 参数又要 3.10+（K15 底线是 3.8）。
    """
    lo, hi = 0, len(segments)
    while lo < hi:
        mid = (lo + hi) // 2
        if segments[mid].utc_start <= utc:
            lo = mid + 1
        else:
            hi = mid
    return segments[lo - 1 if lo else 0]


def state_at(utc, timeline):
    """``utc`` 时刻的 ``(offset_sec, abbr, is_dst)``。tail 生效区走解析式求值。"""
    if timeline.tail is not None and (timeline.table_end_utc is None
                                      or utc >= timeline.table_end_utc):
        return _tail_state_at(timeline.tail, utc)
    seg = _segment_at(utc, timeline.segments)
    return seg.offset_sec, seg.abbr, seg.is_dst


def offset_at(utc, timeline):
    """``utc`` 时刻的 UTC 偏移（东为正，秒）。M3 的 ``offset(t_i - 1)`` / ``offset(t_i)`` 用它。"""
    return state_at(utc, timeline)[0]


def to_local(utc, timeline):
    """UTC → 本地墙钟 epoch（= ``utc + offset``）。"""
    return int(utc) + offset_at(utc, timeline)


def offsets(timeline):
    """该时间线出现过的全部 offset（升序、去重）—— 反解的候选集合。

    结果缓存在 ``Timeline._offsets``：``--all`` 扫全量 zone 时每个 zone 要反解上百次，
    每次重扫 segment 会把 O(n) 变成 O(n²)。
    """
    if timeline._offsets is not None:
        return timeline._offsets
    seen = set(seg.offset_sec for seg in timeline.segments)
    if timeline.tail is not None:
        seen.add(timeline.tail.std[0])
        if timeline.tail.dst is not None:
            seen.add(timeline.tail.dst[0])
    timeline._offsets = sorted(seen)
    return timeline._offsets


def resolve_local(local, timeline):
    """本地墙钟 → 0/1/2 个 UTC 候选（按 utc 升序，``fold`` = 序号）。

    候选判据：``utc = local - o`` 之后，``to_local(utc) == local``（自洽）。
    同 utc 只留一条；**存在性只看个数**（K10 / PITFALL-FOLD-GAP）。
    """
    local = int(local)
    found = []
    seen = set()
    for candidate in offsets(timeline):
        utc = local - candidate
        if utc in seen:
            continue
        if to_local(utc, timeline) != local:
            continue
        seen.add(utc)
        offset_sec, abbr, is_dst = state_at(utc, timeline)
        found.append(Resolution(utc, offset_sec, abbr, is_dst, 0))
    found.sort(key=lambda res: res.utc)
    for index, res in enumerate(found):
        res.fold = index
    return found


def roundtrip(local, timeline):
    """``local`` → 候选 UTC → 回到本地墙钟（``data/README.md`` §4.6）。

    0 个候选 → 空列表（GAP）；1 个 → ``[local]``（OK）；2 个 → ``[local, local]``（OVERLAP）。
    """
    return [to_local(res.utc, timeline) for res in resolve_local(local, timeline)]


def transition_points(timeline, start_utc, end_utc):
    """``[start_utc, end_utc)`` 内的全部转换点（表 + 物化 tail），升序去重。"""
    points = []
    for seg in timeline.segments:
        if seg.utc_start == NEG_INFINITY:
            continue
        if start_utc <= seg.utc_start < end_utc:
            points.append(seg.utc_start)
    return sorted(set(points))


def describe(timeline):
    """摘要（给 ``--json`` / 金标用）：只由输入决定，无时间戳。"""
    tail = timeline.tail
    return {
        "zone": timeline.zone,
        "version": timeline.version,
        "table_end_utc": timeline.table_end_utc,
        "segments": len(timeline.segments),
        "table_segments": sum(1 for s in timeline.segments if s.source == "table"),
        "tail_segments": sum(1 for s in timeline.segments if s.source == "tail"),
        "tail": tail.raw if tail is not None else None,
    }
