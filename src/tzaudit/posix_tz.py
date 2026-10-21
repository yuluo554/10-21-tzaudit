# -*- coding: utf-8 -*-
"""POSIX TZ 串解析 —— 契约见 ``plan/03`` §三；规则展开在 ``timeline``（§四）。

本模块**只做"语法 → 结构"**：不做日历算术、不读时钟、不读环境。
"某条规则在某一年落到哪个 UTC 时刻"由 ``timeline`` 借 ``civil`` 完成，
因此 ``posix_tz`` 的依赖面仍然只有 ``errors``（K3 / ``plan/02`` §一）。

解析口径（唯一权威 ``data/README.md`` §4.2，本文只引用不复制）：

1. 缩写：``<+1245>`` 尖括号形式**优先**，否则取 3+ 个 ASCII 字母。
2. 偏移：``[+-]hh[:mm[:ss]]``，**西为正**；解析层翻成**东为正**的秒数（K8）。
   反例：``EST5`` → ``-18000``；``MST7`` → ``-25200``；``<+1245>-12:45`` → ``+45900``。
3. DST 偏移缺省 = std + 1 小时（东向快 1 小时）。
4. ``start`` / ``end``：``Jn``（1–365，跳过 2/29）／``n``（0–365，含 2/29）／
   ``Mm.w.d``（月 / 第 w 周 / 星期 d，``w=5`` 表示最后一个）。
5. ``/time`` 是**墙钟秒**（可负、可 ≥ 24h）；解析层只存 ``time_sec``，
   **不做任何偏移加减**（K9 / PITFALL-WALLSEC）。
6. 无逗号段 → 无 DST（如 ``MST7`` → ``dst is None``）。

失败路径：任何未知形态 → :class:`PosixTzError`（退出码 3）。**不做宽容解析**
（不"猜一个近似规则"）。
"""

from __future__ import print_function

#: ``/time`` 缺省 = 02:00 墙钟（POSIX 缺省值）
DEFAULT_RULE_TIME = 7200

#: DST 缺省比标准时快 1 小时（东向）
DEFAULT_DST_DELTA = 3600


class PosixTzError(Exception):
    """POSIX TZ 串不合法（退出码 3）。不做宽容解析。"""


class Rule(object):
    """一条 DST 规则：``kind ∈ {"J", "N", "M"}`` + ``time_sec``（**墙钟秒**）。

    - ``kind == "J"``：``n`` = 1–365，**跳过 2/29**。
    - ``kind == "N"``：``n`` = 0–365，**含 2/29**（POSIX 的裸 ``n`` 形式）。
    - ``kind == "M"``：``month`` / ``week``（1–5，5 = 最后一个）/ ``weekday``（0 = 周日）。
    """

    __slots__ = ("kind", "n", "month", "week", "weekday", "time_sec")

    def __init__(self, kind, time_sec, n=None, month=None, week=None, weekday=None):
        self.kind = kind
        self.time_sec = time_sec
        self.n = n
        self.month = month
        self.week = week
        self.weekday = weekday

    def __eq__(self, other):
        if not isinstance(other, Rule):
            return NotImplemented
        return (self.kind, self.n, self.month, self.week, self.weekday, self.time_sec) == \
               (other.kind, other.n, other.month, other.week, other.weekday, other.time_sec)

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __repr__(self):  # pragma: no cover - 调试用
        if self.kind == "M":
            body = "M%d.%d.%d" % (self.month, self.week, self.weekday)
        else:
            body = "%s%s" % ("" if self.kind == "N" else self.kind, self.n)
        return "Rule(%s/%d)" % (body, self.time_sec)


class PosixTz(object):
    """``std offset [dst [offset] [,start[/time],end[/time]]]`` 的解析结果。

    偏移一律**东为正的秒数**（解析层已把 POSIX 的"西为正"翻转）。
    ``std`` / ``dst`` 是 ``(offset_sec, abbr)`` 二元组。
    """

    __slots__ = ("std", "dst", "start", "end", "raw")

    def __init__(self, std, dst, start, end, raw):
        self.std = std
        self.dst = dst
        self.start = start
        self.end = end
        self.raw = raw

    @property
    def has_dst(self):
        return self.dst is not None

    @property
    def has_rules(self):
        """有 DST **且**有可展开的起止规则。``EST5EDT`` 这种缺规则串返回 False。"""
        return self.dst is not None and self.start is not None and self.end is not None

    def normalized(self):
        """规范化结构（M4 ``diff`` 比 tail 用）：不含 ``raw``，便于逐项比较。"""
        def rule(r):
            if r is None:
                return None
            return (r.kind, r.n, r.month, r.week, r.weekday, r.time_sec)

        return {
            "std": list(self.std),
            "dst": list(self.dst) if self.dst is not None else None,
            "start": rule(self.start),
            "end": rule(self.end),
        }

    def __repr__(self):  # pragma: no cover - 调试用
        return "PosixTz(%r)" % (self.raw,)


# ---------------------------------------------------------------- 语法工具


def _read_abbr(text, pos, which):
    """读缩写：``<...>`` 优先，否则 3+ 个 ASCII 字母。"""
    if pos >= len(text):
        raise PosixTzError("缺少 %s 缩写: %r" % (which, text))
    if text[pos] == "<":
        end = text.find(">", pos + 1)
        if end < 0:
            raise PosixTzError("%s 缩写的尖括号未闭合: %r" % (which, text))
        name = text[pos + 1:end]
        if not name:
            raise PosixTzError("%s 缩写为空: %r" % (which, text))
        if "<" in name or "," in name:
            raise PosixTzError("%s 缩写含非法字符: %r" % (which, name))
        return name, end + 1

    i = pos
    while i < len(text) and text[i].isalpha() and text[i].isascii():
        i += 1
    name = text[pos:i]
    if len(name) < 3:
        raise PosixTzError("%s 缩写至少 3 个字母: %r" % (which, text[pos:pos + 8]))
    return name, i


def _read_digits(text, pos, limit, which):
    start = pos
    while pos < len(text) and text[pos].isdigit() and text[pos].isascii():
        pos += 1
    if pos == start:
        raise PosixTzError("%s 缺数字: %r" % (which, text[start:start + 8]))
    if pos - start > limit:
        raise PosixTzError("%s 数字超过 %d 位: %r" % (which, limit, text[start:pos]))
    return int(text[start:pos]), pos


def _read_hms(text, pos, which):
    """``hh[:mm[:ss]]`` → 秒（无符号）。小时 1–3 位。"""
    hours, pos = _read_digits(text, pos, 3, which)
    total = hours * 3600
    for unit in (60, 1):
        if pos < len(text) and text[pos] == ":":
            pos += 1
            value, pos = _read_digits(text, pos, 2, which)
            if value > 59:
                raise PosixTzError("%s 的 %d 秒/分越界: %r" % (which, value, text))
            total += value * unit
        else:
            break
    return total, pos


def _read_offset(text, pos, which):
    """``[+-]hh[:mm[:ss]]`` → **西为正**的秒数（调用方负责翻符号）。"""
    if pos >= len(text):
        raise PosixTzError("缺少 %s 偏移: %r" % (which, text))
    sign = 1
    if text[pos] in "+-":
        if text[pos] == "-":
            sign = -1
        pos += 1
    value, pos = _read_hms(text, pos, which)
    return sign * value, pos


def _split_rule_body(text):
    """把 ``M3.2.0/2`` 切成 ``("M3.2.0", "/2")``；无 ``/`` 时后半为空串。"""
    slash = text.find("/")
    if slash < 0:
        return text, ""
    return text[:slash], text[slash:]


def _parse_rule(text, which):
    if not text:
        raise PosixTzError("%s 规则为空" % which)
    body, rest = _split_rule_body(text)
    if not body:
        raise PosixTzError("%s 规则缺主体: %r" % (which, text))

    if body[0] == "J":
        n = _int_body(body[1:], which, "Jn")
        if not 1 <= n <= 365:
            raise PosixTzError("%s 的 Jn 越界（1–365）: %r" % (which, body))
        rule = Rule("J", DEFAULT_RULE_TIME, n=n)
    elif body[0] == "M":
        parts = body[1:].split(".")
        if len(parts) != 3:
            raise PosixTzError("%s 的 Mm.w.d 形态不对: %r" % (which, body))
        month = _int_body(parts[0], which, "Mm.w.d")
        week = _int_body(parts[1], which, "Mm.w.d")
        weekday = _int_body(parts[2], which, "Mm.w.d")
        if not 1 <= month <= 12:
            raise PosixTzError("%s 的月份越界（1–12）: %r" % (which, body))
        if not 1 <= week <= 5:
            raise PosixTzError("%s 的周序越界（1–5，5=最后）: %r" % (which, body))
        if not 0 <= weekday <= 6:
            raise PosixTzError("%s 的星期越界（0–6）: %r" % (which, body))
        rule = Rule("M", DEFAULT_RULE_TIME, month=month, week=week, weekday=weekday)
    else:
        n = _int_body(body, which, "n")
        if not 0 <= n <= 365:
            raise PosixTzError("%s 的 n 越界（0–365）: %r" % (which, body))
        rule = Rule("N", DEFAULT_RULE_TIME, n=n)

    if rest:
        if rest[0] != "/":
            raise PosixTzError("%s 规则后缀不是 /time: %r" % (which, text))
        sign = 1
        tail = rest[1:]
        if tail[:1] in ("+", "-"):
            if tail[0] == "-":
                sign = -1
            tail = tail[1:]
        if not tail:
            raise PosixTzError("%s 的 /time 为空: %r" % (which, text))
        seconds, used = _read_hms(tail, 0, which + " /time")
        if used != len(tail):
            raise PosixTzError("%s 的 /time 有多余字符: %r" % (which, text))
        # K9：只存墙钟秒，**不做偏移加减**。
        rule.time_sec = sign * seconds
    return rule


def _int_body(text, which, form):
    if not text or not all(ch.isdigit() and ch.isascii() for ch in text):
        raise PosixTzError("%s 的 %s 不是纯数字: %r" % (which, form, text))
    return int(text)


# ---------------------------------------------------------------- 入口


def parse(text):
    """解析 POSIX TZ 串 → :class:`PosixTz`。失败抛 :class:`PosixTzError`。"""
    if not isinstance(text, str):
        raise PosixTzError("POSIX TZ 必须是字符串，收到 %r" % (type(text).__name__,))
    if not text:
        raise PosixTzError("POSIX TZ 是空串")

    pos = 0
    std_abbr, pos = _read_abbr(text, pos, "std")
    west, pos = _read_offset(text, pos, "std")
    # K8：POSIX 西为正 → 内部东为正。
    std = (-west, std_abbr)

    if pos >= len(text):
        return PosixTz(std, None, None, None, text)

    dst_abbr, pos = _read_abbr(text, pos, "dst")
    dst_offset = std[0] + DEFAULT_DST_DELTA
    if pos < len(text) and text[pos] != ",":
        west, pos = _read_offset(text, pos, "dst")
        dst_offset = -west
    dst = (dst_offset, dst_abbr)

    if pos >= len(text):
        # 只有 dst 名、没有规则段（如 ``EST5EDT``）：语法合法，规则缺省。
        # timeline 视为"无可展开规则"；M4 diff 仍能看见 std/dst 结构差异。
        return PosixTz(std, dst, None, None, text)

    if text[pos] != ",":
        raise PosixTzError("DST 段之后既不是 ',' 也不是串尾: %r" % (text[pos:],))

    parts = text[pos + 1:].split(",")
    if len(parts) != 2:
        raise PosixTzError("start/end 规则必须恰好两段: %r" % (text[pos + 1:],))
    start = _parse_rule(parts[0], "start")
    end = _parse_rule(parts[1], "end")
    return PosixTz(std, dst, start, end, text)
