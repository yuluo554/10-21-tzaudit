# -*- coding: utf-8 -*-
"""墙钟风险窗口（GAP / OVERLAP）—— 契约见 ``plan/03`` §五。

判定口径**只引用** ``data/README.md`` §4.1（双判据单点定义），本文不复制第二份。

核心思想（K10 / PITFALL-FOLD-GAP）：**存在性只由候选个数决定**。

1. 取该年覆盖的转换点 ``t_i``（表 + 物化 tail）。
2. 对每个转换点：``before = offset(t_i - 1)``、``after = offset(t_i)``。
   - ``after > before`` → 候选 GAP，墙钟区间 ``[t_i + before, t_i + after)``。
   - ``after < before`` → 候选 OVERLAP，墙钟区间 ``[t_i + after, t_i + before)``。
   - ``after == before`` → 不是墙钟窗口（只换缩写），跳过。
3. **逐候选复核双判据**（"宁漏不误报"）：对候选区间内取探测点跑 ``resolve_local``——
   GAP 段必须 **0 个候选**；OVERLAP 段必须 **2 个候选且两 offset 不同**。
   任一不满足 → **丢弃该候选**。
4. 排序：``start_local`` 升序 → 同起点 ``type`` 字典序（``GAP`` < ``OVERLAP``）。

**为什么必须复核**：只看"转换前后 offset 不同"会漏掉**转换点两侧 offset 相同但墙钟仍异常**的
形态；只看 fold 会在 GAP 上误报 OVERLAP（Vancouver 实测踩中）。两条判据并存才既不漏也不误。

依赖面（K26）：只 import ``errors`` / ``timeline`` / ``civil``——**不碰** ``tzif`` / ``posix_tz`` /
``zoneinfo_store``。规则展开与日历算术都在 ``timeline`` / ``civil`` 里，本模块不重写一遍。
"""

from __future__ import print_function

from . import civil, timeline

GAP = "GAP"
OVERLAP = "OVERLAP"

#: 窗口类型字典序（``GAP`` < ``OVERLAP``）—— ``data/README.md`` §4.1 的排序口径
TYPE_ORDER = (GAP, OVERLAP)

#: 扫描窗口在年份边界外多留的余量（秒）。
#: 为什么需要：转换点是 **UTC 时刻**，而窗口按**本地墙钟年份**归属。
#: 一条落在 ``12-31 23:00 UTC`` 的转换点，其墙钟区间可能整个落进**次年**；
#: 只按 UTC 年份取点会把这条窗口**漏掉**（或错记到别的年份）。
#: 余量取 2 天：真实时区偏移的绝对值 ≤ 16 小时（实测 2026e 树最大 57368 秒 ≈ 15.94h），
#: 2 天足够覆盖任何"偏移差"造成的跨年，同时不会把相邻年份的窗口拉进来。
_YEAR_MARGIN_SEC = 2 * 86400

#: 复核探测点的间隔（秒）：整分钟网格。
_PROBE_STEP = 60

#: 区间短于这个秒数时**逐秒**探测（不到 3 分钟）。
_PROBE_EXHAUSTIVE_LIMIT = 180


class Window(object):
    """一条墙钟窗口。字段与 ``--json`` 输出一一对应。

    - ``type``：``GAP`` / ``OVERLAP``
    - ``start_local`` / ``end_local``：本地墙钟区间（``[start, end)``，秒级 epoch）
    - ``duration_min`` / ``residual_sec``：整分钟 + 秒级残差（残差**不并进**分钟）
    - ``offset_before`` / ``offset_after``：转换前后的 UTC 偏移（东为正，秒）
    - ``zone`` / ``source``：zone 名与判定依据的引擎（``table`` / ``tail``）
    """

    __slots__ = ("type", "start_local", "end_local", "duration_min", "residual_sec",
                 "offset_before", "offset_after", "zone", "source")

    def __init__(self, type_, start_local, end_local, duration_min, residual_sec,
                 offset_before, offset_after, zone, source):
        self.type = type_
        self.start_local = start_local
        self.end_local = end_local
        self.duration_min = duration_min
        self.residual_sec = residual_sec
        self.offset_before = offset_before
        self.offset_after = offset_after
        self.zone = zone
        self.source = source

    def __repr__(self):  # pragma: no cover - 调试用
        return "Window(%s, %s, %s, %d+%ds, %d->%d, %s, %s)" % (
            self.type, civil.format_local(self.start_local),
            civil.format_local(self.end_local), self.duration_min, self.residual_sec,
            self.offset_before, self.offset_after, self.zone, self.source)

    def as_dict(self):
        """``--json`` 的一条记录（**不含**任何时间戳；偏移用字符串便于人读）。"""
        return {
            "type": self.type,
            "start_local": civil.format_local(self.start_local),
            "end_local": civil.format_local(self.end_local),
            "duration_min": self.duration_min,
            "residual_sec": self.residual_sec,
            "offset_before": civil.format_offset(self.offset_before),
            "offset_after": civil.format_offset(self.offset_after),
            "zone": self.zone,
            "source": self.source,
        }


class ScanResult(object):
    """一次扫描的结果集（单个 zone 或全量）。

    ``zones_scanned`` = 实际扫描的 zone 数（``--all`` 的分母；``plan/04`` §四：
    ``summary.zones`` 必须与扫描数一致——"0 与没扫到"必须可区分）。
    """

    __slots__ = ("zone", "year", "windows", "errors", "zones_scanned")

    def __init__(self, zone, year, windows, errors=None, zones_scanned=0):
        self.zone = zone
        self.year = year
        self.windows = windows
        self.errors = errors if errors is not None else []
        self.zones_scanned = zones_scanned

    def as_dict(self):
        doc = {
            "zone": self.zone,
            "year": self.year,
            "windows": [item.as_dict() for item in self.windows],
        }
        if self.errors:
            doc["errors"] = list(self.errors)
        return doc


# ---------------------------------------------------------------- 复核（双判据）


def _probe_points(start_local, end_local):
    """复核探测点（本地墙钟 epoch，升序）。

    - 区间短于 3 分钟 → **逐秒**探测（不漏秒级边界）。
    - 否则 → 整分钟网格 + 首/中/末三点。
    """
    length = end_local - start_local
    if length <= 0:
        return []
    if length < _PROBE_EXHAUSTIVE_LIMIT:
        return list(range(start_local, end_local))
    points = set(range(start_local, end_local, _PROBE_STEP))
    points.add(start_local + length // 2)
    points.add(end_local - 1)
    return sorted(points)


def _verify_candidate(kind, start_local, end_local, tl):
    """复核一个候选窗口：GAP 必须 0 个候选，OVERLAP 必须 2 个且 offset 不同。

    返回 ``True`` = 候选成立（保留）；``False`` = 候选不成立（**丢弃**）。

    这条复核是"宁漏不误报"的落点：只看转换前后 offset 不同不够，
    只看 fold 更会在 GAP 上误报 OVERLAP。
    """
    for probe in _probe_points(start_local, end_local):
        candidates = timeline.resolve_local(probe, tl)
        if kind == GAP:
            if len(candidates) != 0:
                return False
        else:
            if len(candidates) != 2:
                return False
            if candidates[0].offset_sec == candidates[1].offset_sec:
                return False
    return True


# ---------------------------------------------------------------- 扫描


def _year_window(year):
    """年份的扫描窗口（含边界余量）→ ``(start_utc, end_utc)``。

    余量的理由见 :data:`_YEAR_MARGIN_SEC`。
    """
    start = civil.epoch_from_local_naive(year, 1, 1) - _YEAR_MARGIN_SEC
    end = civil.epoch_from_local_naive(year + 1, 1, 1) + _YEAR_MARGIN_SEC
    return start, end


def _segment_source(tl, utc):
    """转换点落在哪个引擎（``table`` / ``tail``）—— ``source`` 是一等字段（``plan/02`` §2.1）。

    走 ``timeline.segment_source_at``（不自己重写"表尾那个转换点归 tail"的规则）。
    """
    return timeline.segment_source_at(utc, tl)


def _scan(tl, year, window_start, window_end):
    """扫一条时间线在 ``year`` 的全部墙钟窗口 → ``list[Window]``。"""
    zone = tl.zone
    found = []
    for point in timeline.transition_points(tl, window_start, window_end):
        before = timeline.offset_at(point - 1, tl)
        after = timeline.offset_at(point, tl)
        if before == after:
            continue  # 只换缩写，不是墙钟窗口
        if after > before:
            kind = GAP
            start_local = point + before
            end_local = point + after
        else:
            kind = OVERLAP
            start_local = point + after
            end_local = point + before
        # 窗口按**本地墙钟年份**归属（UTC 年份 ≠ 墙钟年份，跨年会错）
        if civil.local_naive_from_epoch(start_local)[0] != year:
            continue
        if not _verify_candidate(kind, start_local, end_local, tl):
            continue  # 宁漏不误报：复核不通过就丢弃
        duration = end_local - start_local
        found.append(Window(
            kind, start_local, end_local,
            duration // 60, duration % 60,
            before, after, zone, _segment_source(tl, point),
        ))
    found.sort(key=lambda item: (item.start_local, item.type))
    return found


def scan_year(zone, year, tl):
    """扫描某 zone 某年的 GAP / OVERLAP 墙钟窗口。

    ``tl`` = :func:`tzaudit.timeline.load_timeline` 的结果（**调用方给窗口**，
    本模块不读时钟、不自己开树）。返回 ``list[Window]``，按 ``start_local`` 升序、
    同起点按 ``type`` 字典序。
    """
    window_start, window_end = _year_window(year)
    return _scan(tl, year, window_start, window_end)


def scan_all(store, year):
    """全量 zone 批量扫描。

    单 zone 异常 → 记进 ``result.errors``，**不中断整批**（``plan/03`` §五）。
    返回 :class:`ScanResult`；``errors` 非空时调用方应以退出码 3 收尾
    （环境不满足——"这台机器上有 zone 读不了"）。
    """
    window_start, window_end = _year_window(year)
    windows = []
    errors = []
    zones = 0
    for zone in store.zones():
        zones += 1
        try:
            tl = timeline.load_timeline(zone, store,
                                        window_start=window_start, window_end=window_end)
            windows.extend(_scan(tl, year, window_start, window_end))
        except Exception as exc:  # noqa: BLE001 - 单 zone 失败不许中断整批
            errors.append("%s: %s: %s" % (zone, type(exc).__name__, exc))
    # 排序：zone 字节序 → start_local 升序 → type 字典序（K4）
    windows.sort(key=lambda item: (item.zone.encode("utf-8"), item.start_local, item.type))
    return ScanResult(None, year, windows, errors, zones_scanned=zones)


def scan_tree(store, zone, year):
    """扫**单个** zone（``--zone`` 模式）→ :class:`ScanResult`。

    zone 不存在 / 解析失败 → 抛 ``EnvironmentProblem``（退出码 3），**不静默返回空**。
    """
    window_start, window_end = _year_window(year)
    tl = timeline.load_timeline(zone, store, window_start=window_start, window_end=window_end)
    return ScanResult(zone, year, _scan(tl, year, window_start, window_end), zones_scanned=1)
