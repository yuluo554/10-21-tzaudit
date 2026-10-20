# -*- coding: utf-8 -*-
"""TZif（v1–v4）字节解析 —— 契约见 ``plan/03`` §二。

**本模块只做"字节 → 结构"**：不读时钟、不读环境、不做任何墙钟判定（判定在 ``timeline``）。
落地里程碑：**M1**（`bench/run.py --check` 的"全量树零解析错误"判据需要它）。
M2 在它之上做 ``posix_tz`` + ``timeline`` 合并与本地反解。

实现要点（逐条对应 ``plan/03`` §二）：

1. 魔数 ``TZif`` + 版本字节（``\\0`` = v1，``2``/``3``/``4``）。
2. 44 字节 v1 头；版本 ≥ 2 时**按 v1 计数算出 v1 块长度并跳过**，再读第二头 + 64 位数据块，
   **语义取第二块**。``raw_counts`` 同时保留两块的 ``timecnt``（v1 块是格式占位，仍需可解析）。
3. 转换点 → 类型索引 → ``(utoff, isdst, abbrind)`` → 从字符串表截取缩写。
4. footer = 两段数据块之后的 ``\\n<POSIX TZ>\\n``；空串记 ``None``。
5. ``is_slim`` = **footer 非空 且 v1 块转换点数 < ``SLIM_MAX_TRANSITIONS``**。
   slim 构建把 v1 块压扁（``timecnt=0``）、把真实转换点放进 v2 块，所以判据必须落在
   **v1 块**——落在 v2 块会把"表很长"的 slim 文件误判为非 slim。该值**仅供输出说明**，
   不参与任何判定（口径见 ``plan/03`` §二 第 6 条）。

失败路径：魔数不符 / 长度不足 / ``typecnt=0`` / 类型索引越界 / ``abbrind`` 越界
→ :class:`TzifParseError`（退出码 3，带 ``zone`` 与字节偏移）。**不返回部分结果**。
"""

from __future__ import print_function

import struct

MAGIC = b"TZif"
HEADER_SIZE = 44

#: ``is_slim`` 的启发式阈值（只作用于 **v1 块**转换点数；仅用于输出说明，不参与判定）
SLIM_MAX_TRANSITIONS = 2

#: 版本字节 → 版本串。RFC 8536 §3.1 只定义 ``\0``/``2``/``3``/``4``；``'1'`` 一并接受
#: （个别工具写 ``'1'``），其余一律报错。
_VERSION_BYTES = {0: "1", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4"}


class TzifParseError(Exception):
    """TZif 字节损坏（退出码 3）。带 zone 与字节偏移，便于定位。"""

    def __init__(self, message, zone="<bytes>", offset=None):
        self.zone = zone
        self.offset = offset
        where = "" if offset is None else " @%d" % offset
        super(TzifParseError, self).__init__("%s: %s%s" % (zone, message, where))


class TzifData(object):
    """解析结果。字段语义见 ``plan/03`` §二。

    ``transitions`` 升序，每项 ``(utc:int, offset_sec:int, is_dst:bool, abbr:str)``。
    ``footer`` 是 POSIX TZ 串（无 tail 时为 None）。
    """

    __slots__ = ("version", "transitions", "initial", "footer", "is_slim", "raw_counts")

    def __init__(self, version, transitions, initial, footer, is_slim, raw_counts):
        self.version = version
        self.transitions = transitions
        self.initial = initial
        self.footer = footer
        self.is_slim = is_slim
        self.raw_counts = raw_counts

    def __repr__(self):  # pragma: no cover - 调试用
        return "TzifData(v=%s, transitions=%d, footer=%r, is_slim=%r)" % (
            self.version, len(self.transitions), self.footer, self.is_slim)


def _read_header(buf, off, zone):
    """读 44 字节头 → ``(version, counts)``；``counts`` 按文件顺序六元组。"""
    if len(buf) < off + HEADER_SIZE:
        raise TzifParseError("头部不足 44 字节（文件截断）", zone, off)
    if buf[off:off + 4] != MAGIC:
        raise TzifParseError("魔数不是 TZif", zone, off)
    ver_byte = buf[off + 4]
    version = _VERSION_BYTES.get(ver_byte)
    if version is None:
        raise TzifParseError("未知版本字节 0x%02x" % ver_byte, zone, off + 4)
    # 文件顺序：isutcnt, isstdcnt, leapcnt, timecnt, typecnt, charcnt
    counts = struct.unpack_from(">6I", buf, off + 20)
    return version, counts


def _block_size(counts, time_size):
    """一个数据块的字节长度（用于跳过 v1 块 / 定位 footer）。"""
    isutcnt, isstdcnt, leapcnt, timecnt, typecnt, charcnt = counts
    return (timecnt * (time_size + 1)      # 转换时刻 + 类型索引
            + typecnt * 6                  # ttinfo
            + charcnt                      # 缩写字符串表
            + leapcnt * (time_size + 4)    # 闰秒记录（occur + corr）
            + isstdcnt + isutcnt)


def _parse_block(buf, off, counts, time_size, zone):
    """解析一个数据块 → ``(transitions, initial)``。"""
    isutcnt, isstdcnt, leapcnt, timecnt, typecnt, charcnt = counts
    del isutcnt, isstdcnt, leapcnt  # 只影响块长度，已由 _block_size 计入

    if typecnt == 0:
        raise TzifParseError("typecnt=0（无可用的时间类型）", zone, off)
    block_end = off + _block_size(counts, time_size)
    if block_end > len(buf):
        raise TzifParseError("数据块越过文件末尾（截断）", zone, block_end)

    times_off = off
    types_off = times_off + timecnt * time_size
    ttinfo_off = types_off + timecnt
    chars_off = ttinfo_off + typecnt * 6
    chars = buf[chars_off:chars_off + charcnt]

    def abbr_at(index):
        if index >= charcnt:
            raise TzifParseError("abbrind=%d 越界（charcnt=%d）" % (index, charcnt),
                                 zone, chars_off + index)
        end = chars.find(b"\x00", index)
        if end < 0:
            end = len(chars)
        return chars[index:end].decode("ascii", "replace")

    types = []
    for i in range(typecnt):
        base = ttinfo_off + i * 6
        utoff = struct.unpack_from(">i", buf, base)[0]
        is_dst = buf[base + 4] != 0
        types.append((utoff, is_dst, abbr_at(buf[base + 5])))

    transitions = []
    for i in range(timecnt):
        utc = struct.unpack_from(">q" if time_size == 8 else ">i",
                                 buf, times_off + i * time_size)[0]
        index = buf[types_off + i]
        if index >= typecnt:
            raise TzifParseError(
                "转换点 %d 的类型索引 %d 越界（typecnt=%d）" % (i, index, typecnt),
                zone, types_off + i)
        utoff, is_dst, abbr = types[index]
        transitions.append((utc, utoff, is_dst, abbr))

    # 首个转换点之前：取第一条**标准时**类型（``tzfile(5)``），无则取类型 0。
    initial = types[0]
    for entry in types:
        if not entry[1]:
            initial = entry
            break
    return transitions, initial


def _split_footer(buf, off, zone):
    """两段数据块之后是 ``\\n<POSIX TZ>\\n``；空串 → ``None``。"""
    rest = buf[off:]
    if not rest:
        return None
    if rest[:1] != b"\n":
        # 头/块长度算错才会走到这里——宁可报错也不"猜"。
        raise TzifParseError("footer 不是以换行开头", zone, off)
    end = rest.rfind(b"\n")
    if end <= 0:
        raise TzifParseError("footer 未以换行闭合", zone, off)
    return rest[1:end].decode("ascii", "replace") or None


def parse(data, zone="<bytes>"):
    """把 TZif 字节解析成 :class:`TzifData`（**不返回部分结果**）。"""
    if not isinstance(data, (bytes, bytearray)):
        raise TzifParseError("输入不是 bytes", zone, 0)
    buf = bytes(data)

    version, v1_counts = _read_header(buf, 0, zone)
    v1_size = _block_size(v1_counts, 4)

    if version == "1":
        transitions, initial = _parse_block(buf, HEADER_SIZE, v1_counts, 4, zone)
        rest_off = HEADER_SIZE + v1_size
        # v1 规范里没有 footer；万一有尾巴，按"可选 footer"宽容处理，不谎报损坏。
        footer = _split_footer(buf, rest_off, zone) if rest_off < len(buf) else None
        raw_counts = {"v1": v1_counts[3], "v2": 0}
        # v1 文件没有 v2 块可言，一律不算 slim。
        return TzifData(version, transitions, initial, footer, False, raw_counts)

    # 版本 ≥ 2：v1 块只是向后兼容占位，语义以第二块为准。
    second_off = HEADER_SIZE + v1_size
    _version2, v2_counts = _read_header(buf, second_off, zone)
    block2_off = second_off + HEADER_SIZE
    transitions, initial = _parse_block(buf, block2_off, v2_counts, 8, zone)
    footer = _split_footer(buf, block2_off + _block_size(v2_counts, 8), zone)

    raw_counts = {"v1": v1_counts[3], "v2": v2_counts[3]}
    is_slim = bool(footer) and v1_counts[3] < SLIM_MAX_TRANSITIONS
    return TzifData(version, transitions, initial, footer, is_slim, raw_counts)