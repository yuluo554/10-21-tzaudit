# -*- coding: utf-8 -*-
"""zoneinfo 树访问层：目录扫描、zone→路径、版本标签、link 识别。

只读文件，不做任何时区解释（解释在 ``tzif`` / ``posix_tz`` / ``timeline``）。
排序一律按 UTF-8 字节序 —— 不依赖文件系统遍历顺序（确定性纪律）。
"""

from __future__ import print_function

import hashlib
import io
import json
import os
import re

from .errors import EnvironmentProblem

VERSION_DIR_RE = re.compile(r"^(\d{4}[a-z])$")
VERSION_PKG_RE = re.compile(r"^(\d{4}\.\d+)$")

#: 树根下这两个目录不是 zone（tzdata wheel 与已编译树都可能有）
_NON_ZONE_DIRS = {".", "..", "posix", "right"}

#: 这些文件名不是 zone
_NON_ZONE_FILES = {"iso3166.tab", "zone.tab", "zone1970.tab", "leapseconds", "tzdata.zi",
                   "leap-seconds.list", "NEWS", "version", "provenance.json", "SECURITY", "LICENSE",
                   "Makefile", "README", "theory.html", "tz-link.html", "backward", "etcetera"}


def byte_key(text):
    """排序键：UTF-8 字节序（跨平台稳定；不用 locale）。"""
    return text.encode("utf-8")


def is_zone_name(name):
    if not name or name.startswith(".") or name in _NON_ZONE_FILES:
        return False
    if name.endswith((".tab", ".html", ".json", ".list", ".txt", ".md", ".gz", ".tar")):
        return False
    return True


TZIF_MAGIC = b"TZif"


def looks_like_tzif(path):
    """zone 的判据 = 文件以 ``TZif`` 魔数开头，**不是**"路径长得像 zone"。

    实测教训（2026-10-21）：首版只按文件名过滤，把仓库里的 ``plan/*.md`` / ``README`` 一类
    文本误数成 zone（``version --zoneinfo .`` 曾报 27 个 zone）。判据必须是**内容特征**。
    """
    try:
        with io.open(path, "rb") as fh:
            return fh.read(4) == TZIF_MAGIC
    except (IOError, OSError):
        return False


class ZoneinfoStore(object):
    """一棵已解包的 zoneinfo 树（slim 或 fat）。"""

    def __init__(self, root, version=None, kind=None):
        self.root = os.path.abspath(root)
        if not os.path.isdir(self.root):
            raise EnvironmentProblem("zoneinfo 目录不存在: %s" % root)
        self._meta = self._load_provenance()
        self.version = version or self._meta.get("version") or self._guess_version()
        self.kind = kind or self._meta.get("kind") or "unknown"
        self._links = None

    # ---- 元信息 -------------------------------------------------

    def _load_provenance(self):
        path = os.path.join(self.root, "provenance.json")
        if not os.path.isfile(path):
            return {}
        try:
            with io.open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except ValueError:
            return {}

    def _guess_version(self):
        base = os.path.basename(os.path.normpath(self.root))
        for pattern in (VERSION_DIR_RE, VERSION_PKG_RE):
            m = pattern.match(base)
            if m:
                return m.group(1)
        return "unknown"

    # ---- zone 列表 ----------------------------------------------

    def _walk(self):
        """递归产出 (zone_name, abs_path)，只含 **TZif 魔数** 开头的文件。"""
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = os.path.relpath(dirpath, self.root)
            if rel_dir == ".":
                rel_dir = ""
            dirnames[:] = sorted(
                (d for d in dirnames if not d.startswith(".") and d not in ("posix", "right", "__pycache__")),
                key=byte_key,
            )
            for name in sorted(filenames, key=byte_key):
                if not is_zone_name(name):
                    continue
                full = os.path.join(dirpath, name)
                if not looks_like_tzif(full):
                    continue
                zone = (rel_dir.replace(os.sep, "/") + "/" + name) if rel_dir else name
                yield zone, full

    def zones(self):
        """全部 zone 名（字节序）。不含 ``posix/`` ``right/`` 子树。"""
        return sorted((zone for zone, _ in self._walk()), key=byte_key)

    def path_for(self, zone):
        path = os.path.join(self.root, *zone.split("/"))
        if not os.path.isfile(path):
            raise EnvironmentProblem("zone 不存在: %s（树: %s）" % (zone, self.root))
        return path

    def read_zone(self, zone):
        with io.open(self.path_for(zone), "rb") as fh:
            return fh.read()

    # ---- link 识别 ----------------------------------------------

    def links(self):
        """识别 link：内容 sha256 相同即视为同一 zone 的别名。

        **不用符号链接判断** —— Windows 解包会丢符号链接，slim wheel 里也常是副本文件。
        返回 ``{zone: canonical_zone}``（自身映射不进结果）。
        """
        if self._links is not None:
            return self._links
        by_hash = {}
        for zone, path in self._walk():
            try:
                with io.open(path, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
            except (IOError, OSError):
                continue
            by_hash.setdefault(digest, []).append(zone)
        links = {}
        for digest in sorted(by_hash):
            names = sorted(by_hash[digest], key=byte_key)
            if len(names) < 2:
                continue
            canonical = names[0]
            for other in names[1:]:
                links[other] = canonical
        self._links = links
        return links

    # ---- 呈现 ---------------------------------------------------

    def describe(self):
        return {
            "root": os.path.basename(os.path.normpath(self.root)),
            "version": self.version,
            "kind": self.kind,
            "zones": len(self.zones()),
        }
