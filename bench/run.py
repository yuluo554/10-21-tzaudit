#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金标复算入口（题面 §三 第 3 项）。

两种动作：

``--regen``   从 ``data/_downloads/slim/<ver>/`` 真读树 → 逐 zone 解析 → 写
              ``data/tzdb/<ver>/expect.json``（只含**输入 + 期望**）。
``--check``   用**生产实现**复算，与入仓 ``expect.json`` 逐项比对。

判据（`plan/04` §二）：
- ``parse_errors`` 必须为 0（全量树零解析错误）。
- ``zones`` 分母 > 0；**0 与"没扫到"必须可区分**——分母 0 报 FAIL，不静默通过。
- 缺 ``data/_downloads``（干净 clone）→ **退 3 并点名缺失版本**，不是 0 项通过。
- 期望值只由输入决定；金标里不得出现 ``observed_*`` / ``actual_*``（`test_truth_shape.py` 守）。

**独立参照对拍**：``--regen`` 与 ``--check`` 都会用 ``tests/reference.py``（不 import tzaudit）
对**抽样 zone** 逐条对拍。没有这一步，"期望与实现同源"就是引擎自证（`plan/04` §二.2）。

退出码：0 一致 / 1 不一致 / 2 用法错误 / 3 环境缺件
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZDB_DIR = os.path.join(ROOT, "data", "tzdb")
DOWNLOAD_DIR = os.path.join(ROOT, "data", "_downloads")
SLIM_DIR = os.path.join(DOWNLOAD_DIR, "slim")

sys.path.insert(0, os.path.join(ROOT, "src"))

#: 抽样对拍必须覆盖的形态（`plan/04` §二.2 要求"含三种特殊形态"）
SAMPLE_ZONES = (
    "Europe/Dublin",        # 负 DST（冬季 is_dst=1）
    "Australia/Lord_Howe",  # 30 分钟 DST
    "Pacific/Chatham",      # +12:45 非整点
    "America/New_York",
    "America/Vancouver",    # 表内零迁移、语义全在 tail
    "Asia/Tehran",
)

#: 抽样规模下限（`plan/04` §二.2：≥ 20 个）
MIN_SAMPLE = 20

#: expect.json 的格式版本（字段含义变更时递增，`--check` 见到别的值直接报不一致）
EXPECT_SCHEMA = 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="bench/run.py",
        description="复算 tzdata 金标并与入仓 expect.json 比对",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="复算并比对（默认动作）")
    action.add_argument("--regen", action="store_true", help="重新生成金标（需真数据树）")
    parser.add_argument("--suite", choices=("parse",), default=None,
                        help="只跑某一套件（当前只有 parse）")
    return parser


# ---------------------------------------------------------------- 树与解析


def _slim_trees():
    """``data/_downloads/slim/`` 下已解好的树 → ``{version: path}``（版本序）。"""
    if not os.path.isdir(SLIM_DIR):
        return {}
    found = {}
    for name in sorted(os.listdir(SLIM_DIR)):
        path = os.path.join(SLIM_DIR, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "provenance.json")):
            found[name] = path
    return found


def _tzdb_versions():
    """``data/tzdb/`` 下**入仓**的版本（有 provenance.json 的目录）。"""
    if not os.path.isdir(TZDB_DIR):
        return []
    return sorted(
        name for name in os.listdir(TZDB_DIR)
        if os.path.isdir(os.path.join(TZDB_DIR, name))
        and os.path.isfile(os.path.join(TZDB_DIR, name, "provenance.json"))
    )


def _provenance(tree_dir):
    path = os.path.join(tree_dir, "provenance.json")
    if not os.path.isfile(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        return {}


def parse_tree(tree_dir):
    """逐 zone 解析 → ``(stats, errors)``。

    ``stats`` 是**只由输入决定**的聚合量（可写进金标）：
    ``zones`` / ``parse_errors`` / ``transitions_total`` / ``versions`` / ``slim_zones`` /
    ``tail_zones`` / ``tzif_digest``。
    """
    from tzaudit import tzif
    from tzaudit.zoneinfo_store import ZoneinfoStore, byte_key

    store = ZoneinfoStore(tree_dir)
    names = store.zones()
    errors = []
    transitions_total = 0
    version_hist = {}
    slim_zones = 0
    tail_zones = 0
    digest_input = []

    for zone in names:
        try:
            raw = store.read_zone(zone)
            data = tzif.parse(raw, zone)
        except Exception as exc:  # 任何解析失败都必须进 errors（不吞）
            errors.append("%s: %s: %s" % (zone, type(exc).__name__, exc))
            continue
        transitions_total += len(data.transitions)
        version_hist[data.version] = version_hist.get(data.version, 0) + 1
        if data.is_slim:
            slim_zones += 1
        if data.footer:
            tail_zones += 1
        digest_input.append("%s\t%s" % (zone, data.version))

    # 树内容的**指纹**：zone 名 + 各自 TZif 版本。金标靠它区分"同版本不同构建"。
    digest_input.sort(key=byte_key)
    tzif_digest = _sha256_text("\n".join(digest_input))

    stats = {
        "zones": len(names),
        "parse_errors": len(errors),
        "transitions_total": transitions_total,
        "tzif_versions": dict(sorted(version_hist.items())),
        "slim_zones": slim_zones,
        "tail_zones": tail_zones,
        "tzif_digest": tzif_digest,
    }
    return stats, errors


def _sha256_text(text):
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cross_check(tree_dir, zones):
    """用 ``tests/reference.py`` 对抽样 zone 逐条对拍 → ``(checked, mismatches)``。"""
    if os.path.join(ROOT, "tests") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "tests"))
    try:
        import reference
    except ImportError as exc:  # 参照实现不在 → 对拍不成立，必须报错而不是跳过
        return 0, ["参照实现不可用: %s" % exc]

    from tzaudit import tzif
    from tzaudit.zoneinfo_store import ZoneinfoStore

    store = ZoneinfoStore(tree_dir)
    available = set(store.zones())
    wanted = [z for z in SAMPLE_ZONES if z in available]
    for zone in sorted(available):
        if len(wanted) >= MIN_SAMPLE:
            break
        if zone not in wanted:
            wanted.append(zone)

    checked = 0
    mismatches = []
    for zone in wanted:
        try:
            raw = store.read_zone(zone)
            ours = tzif.parse(raw, zone)
            theirs = reference.read_tzif(raw)
        except Exception as exc:
            mismatches.append("%s: 对拍异常 %s: %s" % (zone, type(exc).__name__, exc))
            continue
        if (ours.version, ours.transitions, ours.footer) != (theirs[0], theirs[1], theirs[2]):
            mismatches.append("%s: 生产实现与参照实现不一致" % zone)
            continue
        checked += 1
    if checked < MIN_SAMPLE:
        mismatches.append("对拍样本不足：%d < %d（树里 zone 太少？）" % (checked, MIN_SAMPLE))
    return checked, mismatches


# ---------------------------------------------------------------- regen / check


def _expect_doc(version, tree_dir, stats, cross_checked):
    prov = _provenance(tree_dir)
    return {
        "schema": EXPECT_SCHEMA,
        "suite": "parse",
        "input": {
            "version": version,
            "kind": prov.get("kind"),
            "pypi_version": prov.get("pypi_version"),
            "sha256": prov.get("sha256"),
            "tree": "data/_downloads/slim/%s" % version,
        },
        "expected": {
            "zones": stats["zones"],
            "parse_errors": stats["parse_errors"],
            "transitions_total": stats["transitions_total"],
            "tzif_versions": stats["tzif_versions"],
            "slim_zones": stats["slim_zones"],
            "tail_zones": stats["tail_zones"],
            "tzif_digest": stats["tzif_digest"],
            "reference_cross_checked": cross_checked,
        },
    }


def _write_expect(version, doc):
    target_dir = os.path.join(TZDB_DIR, version)
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)
    path = os.path.join(target_dir, "expect.json")
    text = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def regen(trees):
    problems = []
    written = 0
    print("tzdata 金标重生成 · --regen")
    print("=" * 56)
    for version in sorted(trees):
        tree_dir = trees[version]
        stats, errors = parse_tree(tree_dir)
        if stats["zones"] <= 0:
            problems.append("%s: 树里 0 个 zone（分母空跑）" % version)
            continue
        if errors:
            problems.append("%s: %d 处解析错误（例: %s）"
                            % (version, len(errors), errors[0]))
            continue
        checked, mismatches = cross_check(tree_dir, SAMPLE_ZONES)
        if mismatches:
            for item in mismatches:
                problems.append("%s: %s" % (version, item))
            continue
        doc = _expect_doc(version, tree_dir, stats, checked)
        path = _write_expect(version, doc)
        written += 1
        print("  %s → %s  zones=%d  transitions=%d  对拍=%d"
              % (version, os.path.relpath(path, ROOT), stats["zones"],
                 stats["transitions_total"], checked))
    print("=" * 56)
    if problems:
        print("结论: FAIL（%d 处），未写任何不干净的金标" % len(problems))
        for item in problems:
            print("  FAIL  %s" % item)
        return EXIT_MISMATCH
    print("结论: 写出 %d 份金标" % written)
    return EXIT_OK


def _load_expect(version):
    path = os.path.join(TZDB_DIR, version, "expect.json")
    if not os.path.isfile(path):
        return None
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        return "BROKEN"


def check(trees):
    """复算并与入仓金标比对。分母 > 0 是硬门槛。"""
    versions = _tzdb_versions()
    print("tzdata 金标复算 · --check")
    print("=" * 56)
    print("入仓版本: %s" % (", ".join(versions) if versions else "（无）"))

    if not versions:
        print("缺件: data/tzdb 下没有版本目录（先跑 tools/fetch_tzdb.py）")
        print("结论: 环境不满足（exit 3），**不是** 0 项通过")
        return EXIT_ENV

    missing_trees = [v for v in versions if v not in trees]
    if missing_trees:
        print("缺件: 以下版本没有本地树 data/_downloads/slim/<ver>/：%s"
              % ", ".join(missing_trees))
        print("处置: py -3.12 tools/fetch_tzdb.py --versions %s" % ",".join(missing_trees))
        print("结论: 环境不满足（exit 3），**不是** 0 项通过")
        return EXIT_ENV

    denominator = 0
    bad = []
    for version in versions:
        tree_dir = trees[version]
        stats, errors = parse_tree(tree_dir)
        denominator += 1

        expect = _load_expect(version)
        if expect is None:
            bad.append("%s: 缺 expect.json（跑 --regen）" % version)
            continue
        if expect == "BROKEN":
            bad.append("%s: expect.json 不是合法 JSON" % version)
            continue

        # 1) 零解析错误（判据正确性门槛）
        if stats["parse_errors"] != 0:
            bad.append("%s: parse_errors=%d（必须 0）；例: %s"
                       % (version, stats["parse_errors"], errors[0] if errors else "-"))
        # 2) 分母非空
        if stats["zones"] <= 0:
            bad.append("%s: zones=0（分母空跑）" % version)

        # 3) 与期望逐项比对
        expected = expect.get("expected") or {}
        for key in ("zones", "parse_errors", "transitions_total", "tzif_versions",
                    "slim_zones", "tail_zones", "tzif_digest"):
            if expected.get(key) != stats[key]:
                bad.append("%s: %s 漂移（期望=%r 实测=%r）"
                           % (version, key, expected.get(key), stats[key]))

        # 4) provenance.zones 与实测一致（`plan/04` §1.2 的"漂移即报"）
        prov = _provenance(tree_dir)
        if prov.get("zones") is not None and prov.get("zones") != stats["zones"]:
            bad.append("%s: provenance.zones=%r 与实测 %d 不符"
                       % (version, prov.get("zones"), stats["zones"]))

        # 5) 独立参照对拍（防引擎自证）
        checked, mismatches = cross_check(tree_dir, SAMPLE_ZONES)
        if mismatches:
            bad.extend("%s: %s" % (version, item) for item in mismatches)

        print("  %-7s zones=%-4d parse_errors=%d transitions=%-5d 对拍=%d"
              % (version, stats["zones"], stats["parse_errors"],
                 stats["transitions_total"], checked))

    print("=" * 56)
    print("复算项数: %d（分母必须 > 0）" % denominator)
    print("不一致: %d" % len(bad))
    for item in bad:
        print("  FAIL  %s" % item)
    if denominator == 0:
        print("结论: 分母为 0 —— 判据空跑，按 FAIL 处理")
        return EXIT_ENV
    if bad:
        print("结论: %d 项不一致" % len(bad))
        return EXIT_MISMATCH
    print("结论: 全量树 %d 个 zone 零解析错误，%d 份金标复算一致"
          % (sum(_load_expect(v)["expected"]["zones"] for v in versions
                 if isinstance(_load_expect(v), dict)), denominator))
    return EXIT_OK


def main(argv=None):
    args = build_parser().parse_args(argv)
    trees = _slim_trees()

    if args.regen:
        if not trees:
            print("缺件: data/_downloads/slim 不存在或为空")
            print("处置: py -3.12 tools/fetch_tzdb.py --versions 2026a,2026b,2026c,2026d,2026e")
            print("结论: 环境不满足（exit 3），**不是** 0 项通过")
            return EXIT_ENV
        return regen(trees)

    # 默认动作 = --check
    if args.suite and args.suite != "parse":
        sys.stderr.write("bench/run.py: 未知套件 %r\n" % args.suite)
        return EXIT_USAGE
    return check(trees)


if __name__ == "__main__":
    sys.exit(main())