#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""tzdata 版本包获取器（构建期工具；**运行期零网络**指的是 CLI，不是本脚本）。

产出（全部落在 ``--out``，默认 ``data/_downloads``，已 gitignore）：
  <out>/tzdata<ver>.tar.gz         原始发布包（不入仓）
  <out>/<ver>/NEWS                 解包后的必要文本（M1 选择入仓）
  <out>/<ver>/leap-seconds.list
  <out>/<ver>/version
  <out>/<ver>/provenance.json      URL + sha256 + 版本 + 实测 zones

**骨架期**：参数面与退出码已定，下载与解包由 M1 落地（当前退 5）。
这样"文档点名的工具"有实物，且不会假装已能下载。
"""

from __future__ import print_function

import argparse
import sys

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ENV = 3
EXIT_NOT_READY = 5

BASE_URL = "https://data.iana.org/time-zones/releases"
REQUIRED_TEXT = ("NEWS", "leap-seconds.list", "version")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fetch_tzdb.py",
        description="下载 IANA tzdata 发布包并记录 provenance（构建期工具，M1 实现）",
    )
    parser.add_argument("--versions", required=True,
                        help="逗号分隔的版本号，如 2026a,2026b,2026c,2026d,2026e")
    parser.add_argument("--out", default="data/_downloads", help="输出目录（默认 data/_downloads）")
    parser.add_argument("--check", action="store_true",
                        help="只校验已下载件的 sha256 与 provenance，不联网")
    parser.add_argument("--timeout", type=int, default=60, help="单文件超时秒数（默认 60）")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    if not versions:
        sys.stderr.write("fetch_tzdb: --versions 不能为空\n")
        return EXIT_USAGE
    sys.stderr.write(
        "fetch_tzdb: 下载/解包尚未实现（M1）。\n"
        "已规划入口：%s/tzdata<ver>.tar.gz\n"
        "请求版本：%s\n"
        "输出目录：%s\n"
        % (BASE_URL, ", ".join(versions), args.out)
    )
    return EXIT_NOT_READY


if __name__ == "__main__":
    sys.exit(main())
