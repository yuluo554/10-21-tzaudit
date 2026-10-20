#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金标复算入口（题面 §三 第 3 项）。

骨架期行为（M0）：
- 扫描 ``data/tzdb/`` 下已有的 ``expect.json``，逐份复算**形态**（不是内容）；
- **分母为 0 时报 FAIL**（"0 项"与"没扫到"必须可区分）；
- 缺 ``data/_downloads`` 时**显式报缺件**（退出码 3），不静默 0 项通过。

M1 起：真读 zoneinfo 树，跑解析 + 判定，与金标逐项比对。

退出码：0 一致 / 1 不一致 / 2 用法错误 / 3 环境缺件 / 5 功能未就绪（骨架期）
"""

from __future__ import print_function

import argparse
import io
import json
import os
import sys

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2
EXIT_ENV = 3
EXIT_NOT_READY = 5

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZDB_DIR = os.path.join(ROOT, "data", "tzdb")
DOWNLOAD_DIR = os.path.join(ROOT, "data", "_downloads")

SUITES = ("parse", "windows", "diff", "audit")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="bench/run.py",
        description="复算 tzdata 金标并与入仓 expect.json 比对",
    )
    parser.add_argument("--check", action="store_true", help="复算并比对（默认动作）")
    parser.add_argument("--regen", action="store_true", help="重新生成金标（需真数据树）")
    parser.add_argument("--suite", choices=SUITES, help="只跑某一套件")
    return parser


def _iter_expect(only_suite=None):
    if not os.path.isdir(TZDB_DIR):
        return []
    found = []
    for dirpath, dirnames, filenames in os.walk(TZDB_DIR):
        dirnames.sort()
        if "expect.json" in filenames:
            found.append(os.path.join(dirpath, "expect.json"))
    return sorted(found)


def main(argv=None):
    args = build_parser().parse_args(argv)
    files = _iter_expect(args.suite)

    print("tzdata 金标复算 · 分母自证")
    print("=" * 56)
    print("扫描面: data/tzdb/**/expect.json")
    print("复算项数: %d" % len(files))

    if not files:
        if not os.path.isdir(DOWNLOAD_DIR):
            print("缺件: data/_downloads 不存在——先跑 tools/fetch_tzdb.py（M1）")
            print("结论: 环境不满足（exit 3），**不是** 0 项通过")
            return EXIT_ENV
        print("缺件: 有 data/_downloads 但无金标——跑 bench/run.py --regen（M1）")
        return EXIT_ENV

    bad = []
    for path in files:
        with io.open(path, "r", encoding="utf-8") as fh:
            try:
                json.load(fh)
            except ValueError as exc:
                bad.append("%s: JSON 解析失败: %s" % (os.path.relpath(path, ROOT), exc))

    print("不一致: %d" % len(bad))
    for item in bad:
        print("  FAIL  %s" % item)
    print("=" * 56)
    if bad:
        print("结论: %d 项不一致" % len(bad))
        return EXIT_MISMATCH

    print("结论: 形态一致（内容复算待 M1 落地）")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
