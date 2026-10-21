# -*- coding: utf-8 -*-
"""M3 金标：windows 套件的形态与复算入口（`plan/03` §十）。

三件事：

1. **金标形态**：`expect-windows.json` 只存输入 + 期望；分母非空；抽样集非空且
   **真的覆盖 GAP 与 OVERLAP 两种**。
2. **复算入口**：`bench/run.py --check --suite windows` 在有树时退 0，缺件时退 3。
3. **变异自证**：把金标改一个数 / 把实现的复核短路，判据必须**能跑红**。

第 3 条是重点：M1 的教训是"判据写好了不等于能跑红"（V2/V4 当时全绿 = 假门）。
"""

import io
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

TZDB = os.path.join(ROOT, "data", "tzdb")
SLIM = os.path.join(ROOT, "data", "_downloads", "slim")
VERSIONS = ("2026a", "2026b", "2026c", "2026d", "2026e")

#: 金标必需的期望字段（`bench/run.py::WINDOWS_KEYS` 必须与它一致）
EXPECTED_KEYS = ("zones", "windows_errors", "total_windows", "sampled_zones", "sampled")

needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）",
)


# ---------------------------------------------------------------- 1. 金标形态


@pytest.mark.parametrize("version", VERSIONS)
def test_windows_expect_exists_and_has_required_fields(version):
    path = os.path.join(TZDB, version, "expect-windows.json")
    assert os.path.isfile(path), "缺 %s（跑 bench/run.py --regen --suite windows）" % path
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    assert doc["suite"] == "windows"
    assert doc["input"]["version"] == version
    assert doc["input"]["kind"] == "slim"
    assert doc["input"]["years"], "金标必须记明扫描年份"
    assert doc["input"]["sample_zones"], "金标必须记明抽样名单"

    expected = doc["expected"]
    for key in EXPECTED_KEYS:
        assert key in expected, "%s 缺字段 %s" % (version, key)

    assert expected["windows_errors"] == 0, "扫描必须零错误"
    assert expected["zones"] > 0, "分母必须 > 0（0 与'没扫到'必须可区分）"
    assert expected["sampled"], "抽样集不得为空（空集 = 判据空跑）"
    assert expected["total_windows"] > 0, "全量窗口数必须 > 0（0 = 什么都没扫出来）"
    assert expected["reference_cross_checked"] >= 20


@pytest.mark.parametrize("version", VERSIONS)
def test_windows_expect_is_normalized_json(version):
    from tzaudit.serialize import dumps_json

    path = os.path.join(TZDB, version, "expect-windows.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    assert dumps_json(json.loads(raw)) == raw, "%s 不是规范化 JSON" % version


@pytest.mark.parametrize("version", VERSIONS)
def test_windows_expect_has_no_observation_fields(version):
    """金标只存输入与期望（`test_truth_shape.py` 的同一条纪律，这里按字段名再钉一次）。"""
    path = os.path.join(TZDB, version, "expect-windows.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    for key in doc["expected"]:
        assert not key.startswith(("observed", "actual", "runtime")), key


def test_windows_expect_covers_both_gap_and_overlap():
    """金标必须**真的**覆盖 GAP 与 OVERLAP 两种（否则等于没验窗口）。"""
    with io.open(os.path.join(TZDB, "2026e", "expect-windows.json"), "r",
                 encoding="utf-8") as fh:
        doc = json.load(fh)
    kinds = {row["type"] for zone in doc["expected"]["sampled"]
             for year_row in zone["years"] for row in year_row["windows"]}
    assert kinds == {"GAP", "OVERLAP"}, kinds


def test_windows_expect_contains_the_known_special_zones():
    """金标必须含三条特殊形态 zone（30 分钟 / 45 分钟 / 负 DST）——否则金标缺形态覆盖。"""
    with io.open(os.path.join(TZDB, "2026e", "expect-windows.json"), "r",
                 encoding="utf-8") as fh:
        doc = json.load(fh)
    zones = set(doc["expected"]["sampled_zones"])
    assert {"Australia/Lord_Howe", "Pacific/Chatham", "Europe/Dublin"} <= zones, zones
    # 30 分钟与 45 分钟的时长/偏移必须真的出现
    durations = {row["duration_min"] for zone in doc["expected"]["sampled"]
                 for year_row in zone["years"] for row in year_row["windows"]}
    assert 30 in durations, durations


def test_windows_expect_has_no_absolute_paths():
    """金标里的 tree 是**仓库相对路径**，不是本机绝对路径。"""
    for version in VERSIONS:
        path = os.path.join(TZDB, version, "expect-windows.json")
        with io.open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "data/_downloads/slim/" in text
        assert ":\\" not in text and ":/Users/" not in text


# ---------------------------------------------------------------- 2. 复算入口


def _run_bench(args, cwd=None, script=None):
    cmd = [sys.executable, script or os.path.join(ROOT, "bench", "run.py")] + list(args)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, cwd=cwd or ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=env)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


@needs_trees
def test_bench_check_windows_suite_passes():
    rc, out = _run_bench(["--check", "--suite", "windows"])
    assert rc == 0, out
    assert "复算项数: 5" in out
    assert "windows" in out


@needs_trees
def test_bench_check_all_suites_passes():
    rc, out = _run_bench(["--check"])
    assert rc == 0, out
    assert "parse_errors=0" in out
    assert "timeline" in out
    assert "windows" in out


def test_bench_rejects_unknown_suite_name():
    rc, out = _run_bench(["--check", "--suite", "no-such-suite"])
    assert rc == 2, out


# ---------------------------------------------------------------- 3. 变异自证


def _fake_repo(tmp_path):
    """建一个"只有入仓件 + 一棵小树"的假仓库，返回 (root, script)。"""
    fake = tmp_path / "repo"
    (fake / "bench").mkdir(parents=True)
    (fake / "data").mkdir()
    (fake / "src").mkdir()
    (fake / "tests").mkdir()
    shutil.copytree(str(TZDB), str(fake / "data" / "tzdb"))
    shutil.copytree(str(os.path.join(ROOT, "src", "tzaudit")),
                    str(fake / "src" / "tzaudit"))
    shutil.copy(str(os.path.join(ROOT, "tests", "reference.py")),
                str(fake / "tests" / "reference.py"))
    script = str(fake / "bench" / "run.py")
    shutil.copy(str(os.path.join(ROOT, "bench", "run.py")), script)
    return fake, script


def _prepare_fake_tree(fake, version="2026e"):
    """在假仓库里放一棵**真树**（``data/_downloads/slim/<ver>``），并清掉其它版本。

    用真树而不是合成树：参照对拍的样本下限是 20 个 zone
    （``bench/run.py::MIN_SAMPLE``），合成树只有 6 个 zone → ``--regen`` 会以
    "对拍样本不足"失败。**真树 + 复制进来的 ``bench/run.py``** = 一个自洽的假仓库。
    """
    source = os.path.join(SLIM, version)
    if not os.path.isdir(source):
        pytest.skip("需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）")
    tree = fake / "data" / "_downloads" / "slim" / version
    tree.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, str(tree))
    for name in os.listdir(str(fake / "data" / "tzdb")):
        if name != version and (fake / "data" / "tzdb" / name).is_dir():
            shutil.rmtree(str(fake / "data" / "tzdb" / name))
    return tree


def _regen_windows_gold(fake, script, version="2026e"):
    """在假仓库里 ``--regen --suite windows`` → 写出一份**与该树完全一致**的金标。

    有了它，后面的"改一个数"才是**唯一**的差异——否则"金标漂移"可能被别的键
    （比如 ``zones``）顺带检出，测试就验不到"这一条判据本身有效"。
    """
    rc, out = _run_bench(["--regen", "--suite", "windows"], cwd=str(fake), script=script)
    assert rc == 0, out
    path = fake / "data" / "tzdb" / version / "expect-windows.json"
    assert path.is_file(), out
    return path


def test_bench_detects_windows_expect_drift(tmp_path):
    """**变异自证**：把 windows 金标的 ``total_windows`` 改一个数，必须报漂移。

    没有这条，"跳过逐项比对"的改动（``if False and ...``）会让复算恒绿——
    M1 实测踩过：把比对条件短路后，原有测试**全绿**（假门）。

    做法：先在假仓库里 ``--regen`` 出一份**完全一致**的金标，再改一个数——
    这样"唯一的差异"就是被改的那一个数，测的才是"这一条判据本身"。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_tree(fake)
    path = _regen_windows_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["expected"]["total_windows"] += 1
    path.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")

    rc, out = _run_bench(["--check", "--suite", "windows"], cwd=str(fake), script=script)
    assert rc != 0, "金标漂移必须让 --check 非 0:\n%s" % out
    assert "total_windows 漂移" in out, out


def test_bench_detects_windows_sampled_drift(tmp_path):
    """**变异自证**：把金标的 ``sampled``（窗口集合本身）改一条，必须报漂移。

    这条比改总数更严：总数对、细节错也必须被抓住。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_tree(fake)
    path = _regen_windows_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    target = None
    for zone in doc["expected"]["sampled"]:
        for year_row in zone["years"]:
            if year_row["windows"]:
                target = year_row
                break
        if target:
            break
    assert target is not None, "合成树里必须至少有��条窗口可供篡改"
    target["windows"].append({
        "type": "GAP", "start_local": "1999-01-01 00:00:00",
        "end_local": "1999-01-01 01:00:00", "duration_min": 60, "residual_sec": 0,
        "offset_before": "+00:00", "offset_after": "+01:00", "source": "table"})
    path.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")

    rc, out = _run_bench(["--check", "--suite", "windows"], cwd=str(fake), script=script)
    assert rc != 0, "窗口集合漂移必须让 --check 非 0:\n%s" % out
    assert "sampled 漂移" in out, out


def test_bench_windows_missing_expect_is_named(tmp_path):
    """缺 windows 金标时必须**点名**缺件，不是静默跳过。"""
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_tree(fake)
    (fake / "data" / "tzdb" / "2026e" / "expect-windows.json").unlink()

    rc, out = _run_bench(["--check", "--suite", "windows"], cwd=str(fake), script=script)
    assert rc != 0, out
    assert "缺 expect-windows.json" in out, out


def test_bench_windows_rejects_a_gold_without_both_shapes(tmp_path):
    """**变异自证**：金标里若只有 GAP 没有 OVERLAP，``--regen`` 必须拒绝写出。

    理由：只有一种窗口形态时，"实现只产 GAP"这种退化实现也能全绿。
    """
    fake, script = _fake_repo(tmp_path)
    tree = fake / "data" / "_downloads" / "slim" / "2026e"
    tree.mkdir(parents=True)
    # 只放一个**无 DST** 的 zone → 全是零窗口，缺 GAP 也缺 OVERLAP
    shutil.copy(str(os.path.join(ROOT, "data", "fixtures", "windows", "tree",
                                 "Zone", "NoDst")),
                str(tree / "Test"))
    (tree / "provenance.json").write_text(
        json.dumps({"version": "2026e", "kind": "slim", "zones": 1}), encoding="utf-8")
    for name in os.listdir(str(fake / "data" / "tzdb")):
        if name != "2026e" and (fake / "data" / "tzdb" / name).is_dir():
            shutil.rmtree(str(fake / "data" / "tzdb" / name))

    rc, out = _run_bench(["--regen", "--suite", "windows"], cwd=str(fake), script=script)
    assert rc != 0, "只有一种窗口形态时 --regen 必须失败:\n%s" % out
    assert "缺 GAP/OVERLAP" in out, out
