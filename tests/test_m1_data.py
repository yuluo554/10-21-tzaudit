# -*- coding: utf-8 -*-
"""M1 数据先行：TZif 解析器 + 入仓数据形态 + 金标复算入口。

这一组测试**不联网**（跑 CI 时 ``data/_downloads`` 通常不存在），分三层：

1. **合成字节**：解析器的边界与失败路径（v1 / v2 / 截断 / 越界）。
2. **入仓件形态**：``data/tzdb/*/provenance.json`` 与 ``NEWS`` 摘录必须齐、字段必须对。
3. **金标与复算入口**：``expect.json`` 形态；``bench/run.py --check`` 在**有/无**本地树
   两种环境下分别退 0 / 退 3（后者必须**点名缺件**，不许 0 项静默通过）。

"真实数据"相关的断言（全量 598 zone 零解析错误、与参照实现对拍）在 ``_needs_trees``
标记下：有 ``data/_downloads/slim`` 才跑。CI 没有下载缓存时这些用例 skip 而不是假绿。
"""

from __future__ import print_function

import ast
import io
import json
import os
import struct
import subprocess
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from tzaudit import tzif  # noqa: E402
from tzaudit.zoneinfo_store import ZoneinfoStore  # noqa: E402

TZDB = os.path.join(ROOT, "data", "tzdb")
SLIM = os.path.join(ROOT, "data", "_downloads", "slim")

VERSIONS = ("2026a", "2026b", "2026c", "2026d", "2026e")

#: 必需字段（`plan/04` §1.2 + M1 DoD）
REQUIRED_PROVENANCE = ("version", "kind", "source_url", "sha256", "retrieved", "zones")


# ---------------------------------------------------------------- 合成字节工具


def _ttinfo(utoff, is_dst, abbrind):
    return struct.pack(">iBB", utoff, 1 if is_dst else 0, abbrind)


def _build_tzif(version, transitions, types, abbrs, footer=None):
    """构造一份最小 TZif（v1 或 v2）。

    ``transitions`` = [(utc, type_index)]；``types`` = [(utoff, is_dst, abbrind)]；
    ``abbrs`` = 缩写表字符串（``\\0`` 分隔，以 ``\\0`` 结尾）。
    """
    abbr_blob = ("".join(a + "\x00" for a in abbrs)).encode("ascii")
    times = b"".join(struct.pack(">i", t) for t, _ in transitions)
    indices = bytes(bytearray(i for _, i in transitions))
    ttinfos = b"".join(_ttinfo(*t) for t in types)

    def block(width):
        if width == 8:
            tm = b"".join(struct.pack(">q", t) for t, _ in transitions)
        else:
            tm = times
        return tm + indices + ttinfos + abbr_blob

    counts = (0, 0, 0, len(transitions), len(types), len(abbr_blob))
    header = b"TZif" + (b"\x00" if version == "1" else version.encode("ascii")) + b"\x00" * 15
    header += struct.pack(">6I", *counts)

    if version == "1":
        return header + block(4)

    # v1 块压扁（slim 形态：v1 timecnt=0），真实转换点在 v2 块。
    # 注意：**两个头的版本字节都是 '2'**（实测 2026e 树如此；写成 \0 会被解析器判成 footer 错位）。
    v1_counts = (0, 0, 0, 0, len(types), len(abbr_blob))
    v1_header = b"TZif" + version.encode("ascii") + b"\x00" * 15 + struct.pack(">6I", *v1_counts)
    v1_block = b"".join(_ttinfo(*t) for t in types) + abbr_blob
    v2_header = b"TZif" + version.encode("ascii") + b"\x00" * 15 + struct.pack(">6I", *counts)
    out = v1_header + v1_block + v2_header + block(8)
    if footer is not None:
        out += b"\n" + footer.encode("ascii") + b"\n"
    return out


def _sample_v2():
    return _build_tzif(
        "2",
        transitions=[(0, 0), (1000, 1)],
        types=[(-18000, False, 0), (-14400, True, 4)],
        abbrs=["EST", "EDT"],
        footer="EST5EDT,M3.2.0,M11.1.0",
    )


# ---------------------------------------------------------------- 1. 解析器


def test_parse_v2_roundtrip_of_synthetic_bytes():
    data = tzif.parse(_sample_v2(), "Synthetic/Zone")
    assert data.version == "2"
    assert data.transitions == [
        (0, -18000, False, "EST"),
        (1000, -14400, True, "EDT"),
    ]
    assert data.footer == "EST5EDT,M3.2.0,M11.1.0"
    assert data.raw_counts == {"v1": 0, "v2": 2}


def test_slim_is_decided_by_v1_block_not_v2():
    """slim 判据必须落在 **v1 块**：v1 压扁 + v2 表长 = slim。

    若判据误落在 v2 块（"表短才算 slim"），这里 v2 有 2 个转换点就会判成非 slim。
    """
    data = tzif.parse(_sample_v2())
    assert data.raw_counts["v1"] == 0 and data.raw_counts["v2"] == 2
    assert data.is_slim is True


def test_footer_absent_is_none():
    data = tzif.parse(_build_tzif(
        "2", transitions=[(0, 0)], types=[(0, False, 0)], abbrs=["UTC"], footer=None))
    assert data.footer is None
    assert data.is_slim is False  # 无 footer 一定不是 slim


def test_v1_file_parses_and_is_never_slim():
    data = tzif.parse(_build_tzif(
        "1", transitions=[(0, 0)], types=[(3600, False, 0)], abbrs=["CET"]))
    assert data.version == "1"
    assert data.transitions == [(0, 3600, False, "CET")]
    assert data.is_slim is False


def test_initial_is_first_standard_type():
    """首转换点之前取**第一条标准时**类型（tzfile(5)），不是盲目取类型 0。"""
    data = tzif.parse(_build_tzif(
        "2",
        transitions=[(0, 1)],
        # 缩写表 = "CEST\0CET\0"：CEST 在 0、CET 在 5（4 是 NUL，写 4 会取到空串）
        types=[(7200, True, 0), (3600, False, 5)],   # 类型 0 是 DST，类型 1 是标准
        abbrs=["CEST", "CET"],
        footer="CET-1CEST,M3.5.0,M10.5.0/3",
    ))
    assert data.initial == (3600, False, "CET")


@pytest.mark.parametrize("blob,needle", [
    (b"NOPE" + b"\x00" * 40, "魔数"),
    (b"TZif", "头部不足"),
    (b"TZif\x00" + b"\x00" * 15 + struct.pack(">6I", 0, 0, 0, 0, 0, 0), "typecnt=0"),
])
def test_parse_failures_raise_tzif_parse_error(blob, needle):
    with pytest.raises(tzif.TzifParseError) as exc:
        tzif.parse(blob, "Broken/Zone")
    assert needle in str(exc.value)
    assert exc.value.zone == "Broken/Zone"


def test_truncated_block_raises_instead_of_index_error():
    good = _sample_v2()
    for cut in (20, 50, len(good) - 10):
        with pytest.raises(tzif.TzifParseError):
            tzif.parse(good[:cut], "Truncated")


def test_type_index_out_of_range_is_reported():
    blob = _build_tzif("2", transitions=[(0, 5)], types=[(0, False, 0)], abbrs=["UTC"])
    with pytest.raises(tzif.TzifParseError) as exc:
        tzif.parse(blob, "Bad/Index")
    assert "类型索引" in str(exc.value)


def test_abbr_index_out_of_range_is_reported():
    blob = _build_tzif("2", transitions=[(0, 0)], types=[(0, False, 99)], abbrs=["UTC"])
    with pytest.raises(tzif.TzifParseError) as exc:
        tzif.parse(blob, "Bad/Abbr")
    assert "abbrind" in str(exc.value)


def test_reference_implementation_matches_on_synthetic_bytes():
    import reference

    raw = _sample_v2()
    ours = tzif.parse(raw, "Synthetic/Zone")
    theirs = reference.read_tzif(raw)
    assert (ours.version, ours.transitions, ours.footer) == theirs


# ---------------------------------------------------------------- 2. 入仓件形态


def test_all_five_versions_are_committed():
    present = sorted(
        name for name in os.listdir(TZDB)
        if os.path.isdir(os.path.join(TZDB, name))
        and os.path.isfile(os.path.join(TZDB, name, "provenance.json"))
    ) if os.path.isdir(TZDB) else []
    assert present == list(VERSIONS), "入仓版本不齐: %r" % (present,)


@pytest.mark.parametrize("version", VERSIONS)
def test_provenance_has_required_fields(version):
    path = os.path.join(TZDB, version, "provenance.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        prov = json.load(fh)
    missing = [k for k in REQUIRED_PROVENANCE if k not in prov]
    assert missing == [], "%s 的 provenance 缺字段: %s" % (version, missing)
    assert prov["version"] == version
    assert prov["kind"] == "slim", "Q1 定案：金标两棵树必须是 slim（K14）"
    assert len(prov["sha256"]) == 64 and all(c in "0123456789abcdef" for c in prov["sha256"])
    assert isinstance(prov["zones"], int) and prov["zones"] > 0
    assert prov["source_url"].startswith("https://")
    # 源码包凭据也必须留（两个来源都可复现）
    assert len(prov.get("source_sha256", "")) == 64


@pytest.mark.parametrize("version", VERSIONS)
def test_provenance_is_normalized_json(version):
    from tzaudit.serialize import dumps_json

    path = os.path.join(TZDB, version, "provenance.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    assert dumps_json(json.loads(raw)) == raw, "%s/provenance.json 不是规范化 JSON" % version


def test_news_excerpts_pin_the_two_historical_quotes():
    """`plan/01` §1.4 引用的两句必须**逐字**在入仓 NEWS 里。

    注意 2026d 原文用的是 U+2019 弯引号（``Iran’s``），不是 ASCII 撇号——
    这里按原文断言，防"顺手把弯引号改成直引号"。
    """
    with io.open(os.path.join(TZDB, "2026e", "NEWS"), "r", encoding="utf-8") as fh:
        news_e = fh.read()
    with io.open(os.path.join(TZDB, "2026d", "NEWS"), "r", encoding="utf-8") as fh:
        news_d = fh.read()

    assert "In 1925 Ireland fell back on 09-20 not 10-04" in news_e
    assert u"Iran\u2019s 1979-05-26 spring forward was at 00:00, not 24:00." in news_d


@pytest.mark.parametrize("version", VERSIONS)
def test_news_excerpt_is_only_the_latest_release_block(version):
    """NEWS 摘录 = 首版发布块（不是整份 260KB 历史）。"""
    path = os.path.join(TZDB, version, "NEWS")
    with io.open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    releases = [line for line in text.split("\n") if line.startswith("Release ")]
    assert len(releases) == 1, "%s/NEWS 含 %d 个 Release 头（应只留首版）" % (
        version, len(releases))
    # 上游 2026b 的 NEWS 头确实误写成 "Release 2026a"（原样保留，不代改上游数据）
    if version != "2026b":
        assert releases[0].startswith("Release %s " % version)


@pytest.mark.parametrize("version", VERSIONS)
def test_version_file_matches_directory(version):
    path = os.path.join(TZDB, version, "version")
    with io.open(path, "r", encoding="utf-8") as fh:
        assert fh.read().strip() == version


# ---------------------------------------------------------------- 3. 金标形态


@pytest.mark.parametrize("version", VERSIONS)
def test_expect_shape(version):
    path = os.path.join(TZDB, version, "expect.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["suite"] == "parse"
    assert doc["input"]["version"] == version
    assert doc["input"]["kind"] == "slim"
    expected = doc["expected"]
    assert expected["parse_errors"] == 0, "金标里 parse_errors 必须为 0"
    assert expected["zones"] > 0, "分母必须 > 0（0 与'没扫到'必须可区分）"
    assert expected["reference_cross_checked"] >= 20, "对拍样本必须 ≥ 20（plan/04 §二.2）"
    assert expected["tzif_digest"]


def test_expect_has_no_absolute_paths():
    """金标里的 tree 是**仓库相对路径**，不是本机绝对路径。"""
    for version in VERSIONS:
        path = os.path.join(TZDB, version, "expect.json")
        with io.open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "data/_downloads/slim/" in text
        assert ":\\" not in text and ":/Users/" not in text


def test_pairs_gold_is_filled_by_m4_not_guessed():
    """``pairs/2026a-2026e.json`` **已由 M4 复算回填**（不再是骨架）。

    M1 时它是骨架：``status="skeleton"`` + 两份名单为 ``null`` + ``classes_pending=true``
    ——那条断言防的是"为了让 M4 的表看起来有内容，先填一堆名单"（把金标变成猜测）。

    **M4 落地后本条随之改写**（不是删掉）：骨架的禁止换成了**回填的自证**——
    名单必须真的算过（非 null）、类别必须真的出现、且必须留下"由 diff 复算"的痕迹。
    这正是 `plan/04` §二 的真值纪律：未计算 ≠ 空集。
    """
    path = os.path.join(TZDB, "pairs", "2026a-2026e.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    # 1) 身份：仍是同一对树，仍是 slim（K14）
    assert doc["pair"] == "2026a-2026e"
    assert doc["input"]["old"]["version"] == "2026a"
    assert doc["input"]["new"]["version"] == "2026e"
    assert doc["input"]["old"]["kind"] == "slim"
    assert doc["input"]["new"]["kind"] == "slim"

    # 2) 不再是骨架：M4 已回填（骨架期的两个标记必须都消失）
    assert doc.get("status") != "skeleton", "M4 已落地，金标不得仍是骨架"
    assert "pending_milestone" not in doc, "回填后不得再留 pending_milestone"

    # 3) 名单必须真的算过（null = 没算；空列表 = 算过且为空，本数据下有变更）
    expected = doc["expected"]
    assert expected["window_changed"] is not None, "未计算不得写成 null 蒙过"
    assert expected["all_history_changed"] is not None
    assert expected["all_history_changed"], "本数据对确有变更（空列表才是可疑）"

    # 4) 类别必须真的出现，且是四类口径里的名字
    from tzaudit import diff as diff_module

    kinds = set(item["class"] for item in expected["changes"])
    assert kinds, "changes 不得为空"
    assert kinds <= set(diff_module.CLASS_ORDER), kinds

    # 5) 必须留下"由生产实现复算过"的凭据（参照对拍的样本数）
    assert expected["reference_cross_checked"] > 0, "必须记明对拍样本数"
    assert "classes_pending" not in expected, "回填后不得再留 classes_pending"


# ---------------------------------------------------------------- 4. bench/run.py 入口


def _stats_for_bytes(raw, zone):
    """单 zone 的期望统计量（与 bench/run.py 的 parse_tree 同口径，供假仓库造金标用）。"""
    import hashlib

    data = tzif.parse(raw, zone)
    digest = hashlib.sha256(("%s	%s" % (zone, data.version)).encode("utf-8")).hexdigest()
    return {
        "zones": 1,
        "parse_errors": 0,
        "transitions_total": len(data.transitions),
        "tzif_versions": {data.version: 1},
        "slim_zones": 1 if data.is_slim else 0,
        "tail_zones": 1 if data.footer else 0,
        "tzif_digest": digest,
    }


def _run_bench(args, cwd=None, script=None):
    """跑 ``bench/run.py``。``script`` 指定时跑**那个副本**（它按自身位置推 ROOT）。"""
    cmd = [sys.executable, script or os.path.join(ROOT, "bench", "run.py")] + list(args)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, cwd=cwd or ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=env)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def test_bench_reports_missing_versions_instead_of_passing(tmp_path):
    """干净 clone 形态（无 data/_downloads）→ **退 3 并点名缺件**。

    这条是"0 项通过"的反面：判据必须能区分"全对"与"根本没数据"。
    做法 = 把 bench/run.py 复制到一个没有 ``_downloads`` 的临时仓库根下，跑**那个副本**
    （它按 ``__file__`` 推 ROOT，因此看到的是临时仓库的 data/，不是真仓库的）。
    """
    fake = tmp_path / "repo"
    (fake / "bench").mkdir(parents=True)
    (fake / "data").mkdir()
    (fake / "src").mkdir()
    (fake / "tests").mkdir()
    # 只带"入仓件"（tzdb），**不带**下载缓存
    import shutil
    shutil.copytree(str(TZDB), str(fake / "data" / "tzdb"))
    fake_script = str(fake / "bench" / "run.py")
    shutil.copy(str(os.path.join(ROOT, "bench", "run.py")), fake_script)
    shutil.copytree(str(os.path.join(ROOT, "src", "tzaudit")), str(fake / "src" / "tzaudit"))
    shutil.copy(str(os.path.join(ROOT, "tests", "reference.py")),
                str(fake / "tests" / "reference.py"))

    rc, out = _run_bench(["--check"], cwd=str(fake), script=fake_script)
    assert rc == 3, out
    assert "缺件" in out
    for version in VERSIONS:
        assert version in out, "缺件提示必须点名 %s:\n%s" % (version, out)
    assert "0 项通过" in out


def test_bench_rejects_unknown_suite():
    """未知套件名必须退 2（显式拒绝，不回落）。

    **M3 补记**：``windows`` 曾是"未知套件"的样板（2026-10-21 起它是第三套件），
    所以这里换成真正不存在的名字。
    """
    rc, out = _run_bench(["--check", "--suite", "no-such-suite"])
    assert rc == 2, out


def test_bench_check_and_regen_are_mutually_exclusive():
    rc, out = _run_bench(["--check", "--regen"])
    assert rc == 2, out


# ---- 变异自证：这两条证明"判据能跑红"（否则是假门）----------------------


def test_bench_actually_counts_parse_errors(tmp_path):
    """**变异自证**：树里塞一个坏 TZif，`parse_errors` 必须 > 0 且退出非 0。

    没有这条，"吞掉解析错误"的改动（`except: pass`）会让所有金标恒绿——
    M1 实测踩过：把 `errors.append` 改成 `pass`，原有测试**全绿**（假门）。
    """
    import shutil

    fake = tmp_path / "repo"
    (fake / "bench").mkdir(parents=True)
    (fake / "data").mkdir()
    (fake / "src").mkdir()
    (fake / "tests").mkdir()

    # 一棵最小树：一个合法 zone + 一个"魔数对但块截断"的坏 zone
    tree = fake / "data" / "_downloads" / "slim" / "2026a"
    tree.mkdir(parents=True)
    (tree / "Good").write_bytes(_sample_v2())
    (tree / "Bad").write_bytes(_sample_v2()[:60])
    (tree / "provenance.json").write_text(
        '{"version": "2026a", "kind": "slim", "zones": 2}', encoding="utf-8")

    tzdb = fake / "data" / "tzdb" / "2026a"
    tzdb.mkdir(parents=True)
    (tzdb / "provenance.json").write_text(
        '{"version": "2026a", "kind": "slim", "zones": 2}', encoding="utf-8")
    # 期望值取"好 zone 的实测值"，这样唯一的失败来源就是那个坏 zone 的 parse_errors
    _good_stats = _stats_for_bytes(_sample_v2(), "Good")
    (tzdb / "expect.json").write_text(
        json.dumps({
            "schema": 1, "suite": "parse",
            "input": {"version": "2026a", "kind": "slim"},
            "expected": dict(_good_stats, reference_cross_checked=20),
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(str(os.path.join(ROOT, "src", "tzaudit")),
                    str(fake / "src" / "tzaudit"))
    shutil.copy(str(os.path.join(ROOT, "tests", "reference.py")),
                str(fake / "tests" / "reference.py"))
    script = str(fake / "bench" / "run.py")
    shutil.copy(str(os.path.join(ROOT, "bench", "run.py")), script)

    rc, out = _run_bench(["--check"], cwd=str(fake), script=script)
    assert rc != 0, "坏 zone 必须让 --check 非 0 退出:\n%s" % out
    assert "parse_errors=" in out
    assert "parse_errors=0" not in out, "坏 zone 被吞了（parse_errors 仍报 0）:\n%s" % out


def test_bench_detects_expect_drift(tmp_path):
    """**变异自证**：把金标的期望值改一个字节，`--check` 必须报漂移。

    没有这条，"跳过逐项比对"的改动（`if False and ...`）会让复算恒绿——
    M1 实测踩过：把比对条件短路后，原有测试**全绿**（假门）。
    """
    import shutil

    fake = tmp_path / "repo"
    (fake / "bench").mkdir(parents=True)
    (fake / "data").mkdir()
    (fake / "src").mkdir()
    (fake / "tests").mkdir()

    tree = fake / "data" / "_downloads" / "slim" / "2026a"
    tree.mkdir(parents=True)
    (tree / "Good").write_bytes(_sample_v2())
    (tree / "provenance.json").write_text(
        '{"version": "2026a", "kind": "slim", "zones": 1}', encoding="utf-8")

    tzdb = fake / "data" / "tzdb" / "2026a"
    tzdb.mkdir(parents=True)
    (tzdb / "provenance.json").write_text(
        '{"version": "2026a", "kind": "slim", "zones": 1}', encoding="utf-8")
    # 故意写一个错的期望 zones（1 vs 999）
    (tzdb / "expect.json").write_text(
        json.dumps({
            "schema": 1, "suite": "parse",
            "input": {"version": "2026a", "kind": "slim"},
            "expected": {"zones": 999, "parse_errors": 0, "transitions_total": 0,
                         "tzif_versions": {}, "slim_zones": 0, "tail_zones": 0,
                         "tzif_digest": "", "reference_cross_checked": 20},
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    shutil.copytree(str(os.path.join(ROOT, "src", "tzaudit")),
                    str(fake / "src" / "tzaudit"))
    shutil.copy(str(os.path.join(ROOT, "tests", "reference.py")),
                str(fake / "tests" / "reference.py"))
    script = str(fake / "bench" / "run.py")
    shutil.copy(str(os.path.join(ROOT, "bench", "run.py")), script)

    rc, out = _run_bench(["--check"], cwd=str(fake), script=script)
    assert rc != 0, "期望值漂移必须让 --check 非 0:\n%s" % out
    assert "zones 漂移" in out, out


# ---------------------------------------------------------------- 5. 真实树（需下载缓存）


needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）",
)


@needs_trees
@pytest.mark.parametrize("version", VERSIONS)
def test_real_tree_parses_with_zero_errors(version):
    """全量树零解析错误 + 分母非空（M1 的判据正确性门槛）。"""
    tree = os.path.join(SLIM, version)
    store = ZoneinfoStore(tree)
    zones = store.zones()
    assert len(zones) > 0, "分母为 0 —— 判据空跑"

    errors = []
    for zone in zones:
        try:
            tzif.parse(store.read_zone(zone), zone)
        except Exception as exc:  # noqa: BLE001 - 这里就是要收全部失败
            errors.append("%s: %s" % (zone, exc))
    assert errors == [], "%s 有 %d 个 zone 解析失败：\n%s" % (
        version, len(errors), "\n".join(errors[:10]))


@needs_trees
def test_provenance_zones_matches_measured():
    """`plan/04` §1.2：``zones`` 是实测回填，漂移即报。"""
    for version in VERSIONS:
        measured = len(ZoneinfoStore(os.path.join(SLIM, version)).zones())
        path = os.path.join(TZDB, version, "provenance.json")
        with io.open(path, "r", encoding="utf-8") as fh:
            prov = json.load(fh)
        assert prov["zones"] == measured, "%s: provenance.zones=%r 实测=%d" % (
            version, prov["zones"], measured)


@needs_trees
def test_bench_check_passes_with_real_trees():
    rc, out = _run_bench(["--check"])
    assert rc == 0, out
    assert "parse_errors=0" in out
    # 分母 = 五版本 × 各套件 + `DIFF_PAIRS` 的对数（M4 加 diff 套件后从 5 变 6）。
    # 这里断言"分母与套件清单自洽"，而**不写死**具体数字——M5 再加套件时不必改这条。
    expected = 5 + len(_diff_pairs())
    assert "复算项数: %d" % expected in out, out


def _diff_pairs():
    """从 `bench/run.py` 读 `DIFF_PAIRS`（不 import，避免它 `sys.path` 副作用）。"""
    path = os.path.join(ROOT, "bench", "run.py")
    with io.open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DIFF_PAIRS":
            return ast.literal_eval(node.value)
    raise AssertionError("bench/run.py 里找不到 DIFF_PAIRS")


@needs_trees
def test_special_form_zones_are_present_and_parsed():
    """三种特殊形态（负 DST / 30 分钟 / 45 分钟）在真实树里可解析且偏移原样保留。"""
    store = ZoneinfoStore(os.path.join(SLIM, "2026e"))
    zones = set(store.zones())
    for zone in ("Europe/Dublin", "Australia/Lord_Howe", "Pacific/Chatham"):
        assert zone in zones

    # Lord_Howe 标准时 +10:30、DST +11:00；Chatham 标准时 +12:45
    lord = tzif.parse(store.read_zone("Australia/Lord_Howe"), "Australia/Lord_Howe")
    offsets = {t[1] for t in lord.transitions}
    assert 37800 in offsets, "Lord_Howe 必须有 +10:30（37800）"

    chatham = tzif.parse(store.read_zone("Pacific/Chatham"), "Pacific/Chatham")
    ch_offsets = {t[1] for t in chatham.transitions}
    assert 45900 in ch_offsets, "Chatham 必须有 +12:45（45900）"

    # Dublin：负 DST —— 冬季那条的 is_dst 必须为 True（不按"冬季=标准时"推断）
    dublin = tzif.parse(store.read_zone("Europe/Dublin"), "Europe/Dublin")
    assert any(is_dst for _, _, is_dst, _ in dublin.transitions), \
        "Dublin 的负 DST 形态丢了：没有任何 is_dst=True 的转换点"


@needs_trees
def test_reference_cross_check_on_all_zones():
    """全量 598 zone 与参照实现逐条对拍（不是只抽样）。

    抽样对拍已由 ``bench/run.py`` 做；这里做**全量**，把"引擎自证"的门槛压到最低。
    """
    import reference

    store = ZoneinfoStore(os.path.join(SLIM, "2026e"))
    mismatches = []
    for zone in store.zones():
        raw = store.read_zone(zone)
        ours = tzif.parse(raw, zone)
        theirs = reference.read_tzif(raw)
        if (ours.version, ours.transitions, ours.footer) != theirs:
            mismatches.append(zone)
    assert mismatches == [], "与参照实现不一致: %r" % (mismatches[:10],)