# -*- coding: utf-8 -*-
"""版本差异分类 —— 契约见 ``plan/03`` §六；判定口径只引用 ``data/README.md`` §4.3。

四类**互斥**、判定顺序**固定**（:data:`CLASS_ORDER`，取第一条成立者，同一 zone 只输出一条）：

1. ``history_reinterpreted`` —— 两树**共有表历史**（``utc <= min(两树表尾)``）内，
   UTC 时刻对应的本地墙钟发生变化。``evidence`` = ``table`` / ``tail``（差异来自哪台引擎）。
2. ``future_rule`` —— 表**之外**的行为变化：先比表外展开，再比 tail 的**规范化结构**
   （``std/dst/start/end`` 四元组，由 ``posix_tz.PosixTz.normalized`` 提供——本模块
   **不重写**规则展开）。表相同但 tail 不同**必须**落这里
   （Vancouver 2026.1→2026.5：``PST8PDT,M3.2.0,M11.1.0`` → ``MST7``）。
3. ``abbreviation_only`` —— 转换点 ``utc/offset`` 全同，仅 ``abbr`` 不同 → ``evidence=abbr``。
4. ``alias_only`` —— 仅 link/alias 集合变化，且**已排除** 1–3（由顺序结构保证，
   不可能吸收任何 offset/规则变化）。link 判据 = 内容 sha256 相同
   （``zoneinfo_store.links()``），**不靠文件名推断**（Windows 解包会丢符号链接）。

依赖面（K3）：只 import ``errors`` / ``timeline`` / ``zoneinfo_store`` / ``civil``——
**不碰** ``tzif`` / ``posix_tz`` / ``windows``。规则展开与日历算术都在下游模块里。

**比较方法**：两条时间线上的 state 是**分段常量**，所以"窗口内是否存在任一 UTC 时刻
两树 ``to_local`` 不同"可以用**断点枚举**精确回答，不需要抽样：取两树段起点（表转换点 +
已物化的 tail 转换点）的并集，在每个断点处比一次右值即可覆盖全部区间。
``to_local`` 的差异等价于 offset 的差异（``utc + offset``），本模块直接比 offset。

性能：两棵树里**逐字节相同**的 zone 直接跳过（只查 link 目标是否变化），
只有内容不同的 zone 才建时间线。2026a→2026e 实测 598 个 zone 里 20 个内容不同。
"""

from __future__ import print_function

from . import civil, timeline
from .errors import EnvironmentProblem, UsageError
from .zoneinfo_store import byte_key

#: 四类（互斥）+ 固定判定顺序（第一位优先）。口径见 ``data/README.md`` §4.3（K11）。
CLASS_ORDER = ("history_reinterpreted", "future_rule", "abbreviation_only", "alias_only")

HISTORY_REINTERPRETED = CLASS_ORDER[0]
FUTURE_RULE = CLASS_ORDER[1]
ABBREVIATION_ONLY = CLASS_ORDER[2]
ALIAS_ONLY = CLASS_ORDER[3]

#: 表尾之后继续展开的跨度（年）。tail 规则按年重复，30 年足够暴露任何规则差异；
#: 更远的行为由 tail 的**规范化结构**比较兜底（不依赖物化段）。
_FUTURE_YEARS = 30

#: 建时间线时 tail 物化的上界（**只影响"转换点在哪"**）。``timeline.state_at`` 对
#: tail 走解析式求值，因此超出物化范围的 UTC 也能正确回答——这里只是给断点枚举兜底。
_PROVISIONAL_YEAR = 2200


class Change(object):
    """一条 zone 分类记录（``plan/03`` §六）。

    - ``class_``：:data:`CLASS_ORDER` 之一（**同一 zone 只出现一次**）。
    - ``window``：``(开始年, 结束年)`` 或 ``None``（= 全历史）。
    - ``before`` / ``after``：**摘要**（如 ``tail=PST8PDT,M3.2.0,M11.1.0`` /
      ``offset=-04:00``），不是全文；全文在 ``timeline`` 里，不复制进本结构。
    - ``evidence``：``table`` / ``tail`` / ``abbr`` / ``link``。
    """

    __slots__ = ("zone", "class_", "window", "before", "after", "evidence", "note")

    def __init__(self, zone, class_, window, before, after, evidence, note=""):
        self.zone = zone
        self.class_ = class_
        self.window = window
        self.before = before
        self.after = after
        self.evidence = evidence
        self.note = note

    def __repr__(self):  # pragma: no cover - 调试用
        return "Change(%s, %s, evidence=%s)" % (self.zone, self.class_, self.evidence)

    def as_dict(self):
        """``--json`` 的一条记录（**不含**任何时间戳）。"""
        return {
            "zone": self.zone,
            "class": self.class_,
            "window": list(self.window) if self.window is not None else None,
            "before": self.before,
            "after": self.after,
            "evidence": self.evidence,
            "note": self.note,
        }


class DiffResult(object):
    """一次比较的结果集。

    ``changes`` 按 zone 的 UTF-8 字节序（K4）；``summary`` 是可直接 ``--json`` 的字典；
    ``errors`` 是单 zone 失败（**不中断整批**，与 ``windows.scan_all`` 同口径）。
    """

    __slots__ = ("changes", "summary", "errors")

    def __init__(self, changes, summary, errors=None):
        self.changes = changes
        self.summary = summary
        self.errors = errors if errors is not None else []

    def as_dict(self):
        return {
            "changes": [item.as_dict() for item in self.changes],
            "summary": self.summary,
        }


class _Difference(object):
    """一处断点上的差异（内部用，不进 ``--json``）。"""

    __slots__ = ("kind", "utc", "offset_before", "offset_after", "abbr_before",
                 "abbr_after", "source_before", "source_after")

    def __init__(self, kind, utc, offset_before, offset_after, abbr_before, abbr_after,
                 source_before, source_after):
        self.kind = kind                      # "offset" | "abbr"
        self.utc = utc
        self.offset_before = offset_before
        self.offset_after = offset_after
        self.abbr_before = abbr_before
        self.abbr_after = abbr_after
        self.source_before = source_before
        self.source_after = source_after


# ---------------------------------------------------------------- 窗口


def parse_window(text):
    """``--window <开始年>-<结束年>`` → ``(开始年, 结束年)``（闭区间，整数年）。

    非法形态抛 :class:`UsageError`（退出码 2）。**不接受**别的写法：
    只认 ``YYYY-YYYY``，避免"两个数字之间到底是什么分隔符"的二义性。
    """
    raw = (text or "").strip()
    parts = raw.split("-")
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise UsageError("--window 必须是 <开始年>-<结束年>，例如 2000-2030；收到: %r" % text)
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError:
        raise UsageError("--window 的年份必须是整数；收到: %r" % text)
    if start > end:
        raise UsageError("--window 的开始年不得晚于结束年：%d > %d" % (start, end))
    return (start, end)


def _prepare_window(window):
    """``window`` 参数 → ``(years, (start_epoch, end_epoch))``；``None`` 表示全历史。"""
    if window is None:
        return None, None
    if isinstance(window, (tuple, list)):
        if len(window) != 2:
            raise UsageError("window 必须是 (开始年, 结束年)；收到: %r" % (window,))
        years = (int(window[0]), int(window[1]))
    else:
        years = parse_window(window)
    if years[0] > years[1]:
        raise UsageError("window 的开始年不得晚于结束年：%d > %d" % (years[0], years[1]))
    return years, (
        civil.epoch_from_local_naive(years[0], 1, 1),
        civil.epoch_from_local_naive(years[1] + 1, 1, 1),
    )


# ---------------------------------------------------------------- 比较原语


def _provisional_end():
    """tail 物化的临时上界（纯日历算术，不读时钟）。"""
    return civil.epoch_from_local_naive(_PROVISIONAL_YEAR, 1, 1)


def _load(zone, store):
    """建时间线（tail 物化到 ``_PROVISIONAL_YEAR``，够断点枚举用）。"""
    return timeline.load_timeline(zone, store, window_end=_provisional_end())


def _first_point(tl):
    """该时间线**表内**最早的真实断点（首段从 ``NEG_INFINITY`` 起，不算）。"""
    for seg in tl.segments:
        if seg.utc_start == timeline.NEG_INFINITY:
            continue
        return seg.utc_start
    return None


def _scan_bounds(tl_a, tl_b):
    """断点枚举的扫描区间 ``[lo, hi]``（都含）。

    - ``lo`` = 两树最早断点前 1 天（两树在更早处都是常数，取一个探测点即可）。
    - ``hi`` = 两树较晚的表尾 + :data:`_FUTURE_YEARS` 年，且不超过物化上界。
    """
    firsts = [p for p in (_first_point(tl_a), _first_point(tl_b)) if p is not None]
    lo = (min(firsts) - civil.SECONDS_PER_DAY) if firsts else 0

    ends = [tl.table_end_utc for tl in (tl_a, tl_b) if tl.table_end_utc is not None]
    base = max(ends) if ends else lo
    hi = base + _FUTURE_YEARS * 366 * civil.SECONDS_PER_DAY
    limit = _provisional_end()
    if hi > limit:
        hi = limit
    if hi <= lo:
        hi = lo + civil.SECONDS_PER_DAY
    return lo, hi


def _differences(tl_a, tl_b, lo, hi):
    """``[lo, hi]`` 内两时间线的全部差异（按 utc 升序，每个断点最多一条）。

    两树 state 都是**分段常量**，断点取"两树段起点的并集 + lo"，在每个断点比右值
    即可覆盖全部区间——不需要抽样，也不会漏掉"相邻断点之间"。
    """
    breaks = set([lo])
    for tl in (tl_a, tl_b):
        for seg in tl.segments:
            if lo < seg.utc_start <= hi:
                breaks.add(seg.utc_start)

    out = []
    for utc in sorted(breaks):
        off_a, abbr_a, _dst_a = timeline.state_at(utc, tl_a)
        off_b, abbr_b, _dst_b = timeline.state_at(utc, tl_b)
        if off_a == off_b and abbr_a == abbr_b:
            continue
        kind = "offset" if off_a != off_b else "abbr"
        out.append(_Difference(
            kind, utc, off_a, off_b, abbr_a, abbr_b,
            timeline.segment_source_at(utc, tl_a),
            timeline.segment_source_at(utc, tl_b),
        ))
    return out


def _history_end(tl_a, tl_b):
    """两树**共有表历史**的右边界 = 两树表尾的较早者。

    任一树**没有表**（``table_end_utc is None``）时，没有"共有表历史"，
    返回 ``None`` —— 此时一切差异都归第 2 类（表外），不会误判成历史重解释。
    """
    ends = [tl.table_end_utc for tl in (tl_a, tl_b) if tl.table_end_utc is not None]
    if len(ends) < 2:
        return None
    return min(ends)


def _tail_structure(tl):
    """tail 的**规范化结构**（只比对 offset/规则语义，**不含缩写**）。

    - 无 tail → ``None``：表尾之后的行为完全由表决定，已由"表外 offset 差异"覆盖。
    - 有 tail 但无 DST 规则（``MST7`` / ``<+01>-1``）→ ``("const", offset)``：
      这是**常数段**，与"有规则"在结构上必须**可区分**（否则 Vancouver 的
      ``PST8PDT,…`` → ``MST7`` 会因一侧返回 ``None`` 而被结构比较放过）。
    - 有规则 → ``("rules", std_offset, dst_offset, start, end)``，规则四元组由
      :meth:`posix_tz.PosixTz.normalized` 提供（本模块**不重写**规则展开）。

    **缩写不入结构**：tail 里的 `IST`→`GMT` 这类只换名字的差异按第 3 类
    （``abbreviation_only``）判——结构比较若带上缩写，会把命名调整错判成
    ``future_rule``（``data/README.md`` §4.3 第 3 条）。
    """
    tail = getattr(tl, "tail", None)
    if tail is None:
        return None
    if not tail.has_rules:
        return ("const", tail.std[0])
    normalized = tail.normalized()
    return ("rules", normalized["std"][0], (normalized["dst"] or [None])[0],
            normalized["start"], normalized["end"])


def _tail_text(tl):
    tail = getattr(tl, "tail", None)
    return tail.raw if tail is not None else "none"


def _offset_text(offset_sec):
    return "offset=%s" % civil.format_offset(offset_sec)


def _evidence_of(*sources):
    """差异来自哪台引擎：任一侧是 ``tail`` 就记 ``tail``，否则 ``table``。"""
    return "tail" if "tail" in sources else "table"


def _utc_text(utc):
    return "%sZ" % civil.format_local(utc)


# ---------------------------------------------------------------- 单 zone 判定


def _history_candidate(diffs, hist_end, win):
    """第 1 类：**共有历史内**（且落在 `--window` 内，若给了）的 offset 变化。

    边界是**严格小于** ``hist_end``：表覆盖 ``[首个转换点, 表尾)``，而**表尾那个点
    本身归 tail 管**（``timeline.state_at`` 对 ``utc >= table_end_utc`` 走解析式）。
    用 ``<=`` 会把"tail 在表尾处的状态不同"错判成历史重解释——M4 实测踩中：
    合成 fixture 的 ``Zone/TailRule`` 表尾 1990-11-04 恰好是两树 tail 的分歧点。
    """
    for item in diffs:
        if item.kind != "offset":
            continue
        if hist_end is not None and item.utc >= hist_end:
            continue
        if win is not None and not (win[0] <= item.utc < win[1]):
            continue
        return (
            _offset_text(item.offset_before),
            _offset_text(item.offset_after),
            _evidence_of(item.source_before, item.source_after),
            "共有历史内的墙钟↔UTC 映射差异 @ %s（旧 %s / 新 %s）"
            % (_utc_text(item.utc), item.source_before, item.source_after),
        )
    return None


def _future_candidate(diffs, hist_end, tl_a, tl_b):
    """第 2 类：表**之外**的行为变化。

    两个子判定，按口径原文的顺序：

    a. **先比 tail 的规范化结构**（``std/dst/start/end`` 四元组）。表相同但 tail
       不同**必须**落这里（Vancouver 的 ``PST8PDT,…`` → ``MST7``）。
    b. 再比"表尾之后的 offset 展开"：一侧把规则物化成显式转换点时，结构可能相同
       而物化点不同——这仍是表外行为变化。
    """
    struct_a = _tail_structure(tl_a)
    struct_b = _tail_structure(tl_b)
    if struct_a != struct_b:
        return (
            "tail=%s" % _tail_text(tl_a),
            "tail=%s" % _tail_text(tl_b),
            "tail",
            "tail 的规范化结构不同（std/dst/start/end 四元组）",
        )

    for item in diffs:
        if item.kind != "offset":
            continue
        if hist_end is not None and item.utc < hist_end:
            continue
        return (
            _offset_text(item.offset_before),
            _offset_text(item.offset_after),
            _evidence_of(item.source_before, item.source_after),
            "表外行为变化：首个差异 @ %s（旧 %s / 新 %s）"
            % (_utc_text(item.utc), item.source_before, item.source_after),
        )
    return None


def _abbrev_candidate(diffs):
    """第 3 类：**全体** offset 相同（口径是"转换点与 offset 全同"，不是"窗口内全同"），
    仅缩写不同。"""
    if any(item.kind == "offset" for item in diffs):
        return None
    for item in diffs:
        if item.kind != "abbr":
            continue
        return (
            "abbr=%s" % item.abbr_before,
            "abbr=%s" % item.abbr_after,
            "abbr",
            "转换点与 offset 全同，仅缩写自 %s 起不同" % _utc_text(item.utc),
        )
    return None


#: 前三类的判据函数（第 4 类 ``alias_only`` 需要 link 表，在调用方判——它必须排在
#: 语义判定**之后**，这是"不得吸收规则变化"的结构保证）。
#: 键 = 类名，值 = 判据；**遍历顺序取自** :data:`CLASS_ORDER`，所以调换
#: ``CLASS_ORDER`` 的成员顺序会真的改变判定顺序（变异测试锚在这条上）。
_CRITERIA = {
    HISTORY_REINTERPRETED: _history_candidate,
    FUTURE_RULE: _future_candidate,
    ABBREVIATION_ONLY: _abbrev_candidate,
}


def _classify(tl_a, tl_b, win):
    """四类判定（**顺序取自** :data:`CLASS_ORDER`）→ ``(class_, before, after, evidence, note)``
    或 ``None``。

    顺序即口径（K11）：``history → future → abbrev``，取**第一条成立者**——这就是
    "同一 zone 只输出一条"的结构保证。``alias_only`` 在调用方判（它需要 link 表，
    且必须排在语义判定之后）。
    """
    lo, hi = _scan_bounds(tl_a, tl_b)
    diffs = _differences(tl_a, tl_b, lo, hi)
    hist_end = _history_end(tl_a, tl_b)

    for cls in CLASS_ORDER:
        criterion = _CRITERIA.get(cls)
        if criterion is None:
            continue  # alias_only 由调用方判
        if cls == FUTURE_RULE:
            found = criterion(diffs, hist_end, tl_a, tl_b)
        elif cls == HISTORY_REINTERPRETED:
            found = criterion(diffs, hist_end, win)
        else:
            found = criterion(diffs)
        if found is None:
            continue
        before, after, evidence, note = found
        return (cls, before, after, evidence, note)

    return None


def _link_signature(links, zone):
    """该 zone 的 link 关系摘要 → ``(as_alias_of, aliases_of_me)``。

    **两个方向都算**：``alias_only`` 的定义是"zone 在 link 集合中新增/消失"
    （``data/README.md`` §4.3），而"消失"可能发生在**两侧**：

    - 本 zone 原本是别人的别名，现在不是了（``as_alias_of`` 变 ``None``）；
    - 本 zone 原本是规范名、别人挂在它下面，现在别人不挂了（``aliases_of_me`` 变空）。

    只看 ``links.get(zone)``（第一项）会漏掉后一种——M4 实测踩中：
    旧树 ``LinkB → LinkA``，新树 ``LinkB`` 独立出去后，``LinkA`` 的
    ``links.get()`` 两侧都是 ``None``，看起来"没变化"，但它的别名集合从
    ``("Zone/LinkB",)`` 变成了空。
    """
    aliases = tuple(sorted((name for name, target in links.items() if target == zone),
                           key=byte_key))
    return (links.get(zone), aliases)


def _link_text(links, zone):
    """该 zone 的 link 摘要（人读）：``self`` / ``link=<canonical>`` / ``aliases=<...>``。"""
    as_alias_of, aliases = _link_signature(links, zone)
    parts = []
    if as_alias_of is not None:
        parts.append("link=%s" % as_alias_of)
    if aliases:
        parts.append("aliases=%s" % ",".join(aliases))
    return " ".join(parts) if parts else "self"


def _diff_one(name, old_store, new_store, in_old, in_new, old_links, new_links, years, win):
    """单个 zone → ``(Change|None, unclassified: bool)``。

    ``unclassified`` = 两树语义确有差异，但**在给定 window 下四类都不成立**。
    典型现场：`--window 2020-2030` 排除了唯一的历史 offset 变化（如 link 变成真 zone
    后 LMT 从 ``-07:52:58`` 变 ``-08:00``），而第 3 类要求"**所有** offset 全同"、
    第 4 类要求"**无任何** offset 差异"——于是四类都不该命中。
    这种情况**不静默丢弃**：记进 ``summary.unclassified``（与 `plan/03` §六
    "取第一条成立者"不矛盾——四类互斥但**不穷尽**，如实报告比伪造一类更可信）。
    """
    if not in_old:
        return Change(name, ALIAS_ONLY, years, "absent", _link_text(new_links, name),
                      "link", "zone 只在新树中存在（新增）"), False
    if not in_new:
        return Change(name, ALIAS_ONLY, years, _link_text(old_links, name), "absent",
                      "link", "zone 只在旧树中存在（移除）"), False

    raw_a = old_store.read_zone(name)
    raw_b = new_store.read_zone(name)

    if raw_a == raw_b:
        # 字节相同 → 语义必然相同；只有 link 关系变化才是一条 alias 记录
        if _link_signature(old_links, name) == _link_signature(new_links, name):
            return None, False
        return Change(name, ALIAS_ONLY, years, _link_text(old_links, name),
                      _link_text(new_links, name), "link",
                      "zone 内容不变，link 关系变化"), False

    tl_a = _load(name, old_store)
    tl_b = _load(name, new_store)

    found = _classify(tl_a, tl_b, win)
    if found is None:
        # 走到这里 = 前三类都不成立。**先确认"真的没有任何 offset/规则差异"**，
        # 否则 alias_only 会吸收语义变化（口径明令禁止）。注意这里的扫描**不看 window**：
        # alias_only 的判据是"无任何 offset/规则差异"，不是"窗口内无差异"。
        if _differences(tl_a, tl_b, *_scan_bounds(tl_a, tl_b)):
            return None, True  # 四类都不成立 → 如实记进 summary.unclassified
        if _link_signature(old_links, name) == _link_signature(new_links, name):
            return None, False  # 只多了冗余转换点：没有语义差异，也不是变 link
        return Change(name, ALIAS_ONLY, years, _link_text(old_links, name),
                      _link_text(new_links, name), "link",
                      "规则与 offset 无差异，仅 link 关系变化"), False

    class_, before, after, evidence, note = found
    return Change(name, class_, years, before, after, evidence, note), False


# ---------------------------------------------------------------- 入口


def diff_trees(old_store, new_store, window=None, zone=None):
    """两棵 zoneinfo 树的差异分类（``plan/03`` §六）。

    - ``window``：``(开始年, 结束年)`` 或 ``"YYYY-YYYY"``；``None`` = 全历史。
      **只影响第 1 类**（``history_reinterpreted``）的判定区间；第 2 类始终按
      "表外 + tail" 判，不受窗口限制（``data/README.md`` §4.3）。
    - ``zone``：只比较该 zone（不存在于任何一棵树 → ``EnvironmentProblem``，退出码 3）。

    返回 :class:`DiffResult`：``changes`` 按 zone 字节序，同一 zone 最多一条。
    """
    years, win = _prepare_window(window)
    old_zones = set(old_store.zones())
    new_zones = set(new_store.zones())

    if zone is not None:
        if zone not in old_zones and zone not in new_zones:
            raise EnvironmentProblem("zone 不存在: %s（两棵树都没有）" % zone)
        names = [zone]
    else:
        names = sorted(old_zones | new_zones, key=byte_key)

    old_links = old_store.links()
    new_links = new_store.links()

    changes = []
    errors = []
    unclassified = []
    for name in names:
        try:
            record, skipped = _diff_one(name, old_store, new_store, name in old_zones,
                                        name in new_zones, old_links, new_links, years, win)
        except Exception as exc:  # noqa: BLE001 - 单 zone 失败不许中断整批
            errors.append("%s: %s: %s" % (name, type(exc).__name__, exc))
            continue
        if skipped:
            unclassified.append(name)
        if record is not None:
            changes.append(record)

    changes.sort(key=lambda item: byte_key(item.zone))
    unclassified.sort(key=byte_key)

    counts = dict((cls, 0) for cls in CLASS_ORDER)
    for item in changes:
        counts[item.class_] += 1

    summary = {
        "old_version": getattr(old_store, "version", "unknown"),
        "new_version": getattr(new_store, "version", "unknown"),
        "window": list(years) if years is not None else None,
        "zones_compared": len(names),
        "changes": len(changes),
        "classes": counts,
        "unclassified": unclassified,
        "zone_set_equal": old_zones == new_zones,
        "errors": list(errors),
    }
    return DiffResult(changes, summary, errors)
