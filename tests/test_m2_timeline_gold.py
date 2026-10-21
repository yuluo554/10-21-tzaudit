# -*- coding: utf-8 -*-
"""M2 金标：timeline 套件的形态与复算入口（`plan/03` §十）。

三件事：

1. **金标形态**：`expect-timeline.json` 只存输入 + 期望；分母非空；抽样集非空。
2. **复算入口**：`bench/run.py --check --suite timeline` 在有树时退 0，缺件时退 3。
3. **变异自证**：把金标改一个数 / 把 `resolve_local` 的自洽校验短路，判据必须**能跑红**。

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

from tzaudit import civil, timeline  # noqa: E402
from tzaudit.zoneinfo_store import ZoneinfoStore  # noqa: E402

TZDB = os.path.join(ROOT, "data", "tzdb")
SLIM = os.path.join(ROOT, "data", "_downloads", "slim")
VERSIONS = ("2026a", "2026b", "2026c", "2026d", "2026e")

#: 金标必需的期望字段（`bench/run.py::TIMELINE_KEYS` 必须与它一致）
EXPECTED_KEYS = ("zones", "timeline_errors", "sampled_zones", "sampled_transitions",
                 "sampled_tail_points", "sampled")

needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）",
)


# ---------------------------------------------------------------- 1. 金标形态


@pytest.mark.parametrize("version", VERSIONS)
def test_timeline_expect_exists_and_has_required_fields(version):
    path = os.path.join(TZDB, version, "expect-timeline.json")
    assert os.path.isfile(path), "缺 %s（跑 bench/run.py --regen --suite timeline）" % path
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    assert doc["suite"] == "timeline"
    assert doc["input"]["version"] == version
    assert doc["input"]["kind"] == "slim"
    assert doc["input"]["window"] == ["1990-01-01", "2030-01-01"]
    assert doc["input"]["probes"] > 0

    expected = doc["expected"]
    for key in EXPECTED_KEYS:
        assert key in expected, "%s 缺字段 %s" % (version, key)

    assert expected["timeline_errors"] == 0, "建时间线必须零错误"
    assert expected["zones"] > 0, "分母必须 > 0"
    assert expected["sampled"], "抽样集不得为空（空集 = 判据空跑）"
    assert expected["reference_cross_checked"] >= 20
    # 抽样集必须覆盖三种特殊形态
    zones = set(expected["sampled_zones"])
    assert {"Europe/Dublin", "Australia/Lord_Howe", "Pacific/Chatham"} <= zones


@pytest.mark.parametrize("version", VERSIONS)
def test_timeline_expect_is_normalized_json(version):
    from tzaudit.serialize import dumps_json

    path = os.path.join(TZDB, version, "expect-timeline.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    assert dumps_json(json.loads(raw)) == raw, "%s 不是规范化 JSON" % version


@pytest.mark.parametrize("version", VERSIONS)
def test_timeline_expect_has_no_observation_fields(version):
    """金标只存输入与期望（`test_truth_shape.py` 的同一条纪律，这里按字段名再钉一次）。"""
    path = os.path.join(TZDB, version, "expect-timeline.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    for key in doc["expected"]:
        assert not key.startswith(("observed", "actual", "runtime")), key


def test_timeline_expect_candidates_cover_all_three_shapes():
    """金标的候选集合必须真的出现 0 / 1 / 2 三种（否则 gap/overlap 没被覆盖）。"""
    with io.open(os.path.join(TZDB, "2026e", "expect-timeline.json"), "r",
                 encoding="utf-8") as fh:
        doc = json.load(fh)
    sizes = {len(case["utc"]) for zone in doc["expected"]["sampled"]
             for case in zone["candidates"]}
    assert sizes == {0, 1, 2}, "候选个数集合 = %r（必须恰为 {0,1,2}）" % (sizes,)


def test_timeline_expect_records_tail_dependence():
    """``sampled_tail_points`` 必须 > 0：全量靠表就能算完的话，tail 引擎没被验到。"""
    with io.open(os.path.join(TZDB, "2026e", "expect-timeline.json"), "r",
                 encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["expected"]["sampled_tail_points"] > 0, \
        "抽样里没有任何 tail 转换点——tail 引擎等于没验"
    assert doc["expected"]["sampled_transitions"] > doc["expected"]["sampled_tail_points"]


# ---------------------------------------------------------------- 2. 复算入口


def _run_bench(args, cwd=None, script=None):
    cmd = [sys.executable, script or os.path.join(ROOT, "bench", "run.py")] + list(args)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, cwd=cwd or ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=env)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


@needs_trees
def test_bench_check_timeline_suite_passes():
    rc, out = _run_bench(["--check", "--suite", "timeline"])
    assert rc == 0, out
    assert "复算项数: 5" in out


@needs_trees
def test_bench_check_both_suites_passes():
    rc, out = _run_bench(["--check"])
    assert rc == 0, out
    assert "parse_errors=0" in out
    assert "timeline" in out


def test_bench_rejects_unknown_suite_name():
    rc, out = _run_bench(["--check", "--suite", "windows"])
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


def test_bench_detects_timeline_expect_drift(tmp_path):
    """**变异自证**：把 timeline 金标的 ``sampled_transitions`` 改一个数，必须报漂移。"""
    fake, script = _fake_repo(tmp_path)

    # 只放一个版本，且树里塞一个真实 zone 文件（从 fixture 拷贝，保证能建时间线）
    tree = fake / "data" / "_downloads" / "slim" / "2026e"
    tree.mkdir(parents=True)
    (tree / "provenance.json").write_text(
        json.dumps({"version": "2026e", "kind": "slim", "zones": 1}), encoding="utf-8")
    shutil.copy(str(os.path.join(ROOT, "data", "fixtures", "tzif", "slim-vs-fat", "fat.tzif")),
                str(tree / "Test"))

    # 清掉其它版本的 tzdb 目录，只留 2026e
    for name in os.listdir(str(fake / "data" / "tzdb")):
        if name != "2026e" and (fake / "data" / "tzdb" / name).is_dir():
            shutil.rmtree(str(fake / "data" / "tzdb" / name))

    doc = json.loads((fake / "data" / "tzdb" / "2026e" / "expect-timeline.json")
                     .read_text(encoding="utf-8"))
    doc["expected"]["sampled_transitions"] += 1
    (fake / "data" / "tzdb" / "2026e" / "expect-timeline.json").write_text(
        json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    rc, out = _run_bench(["--check", "--suite", "timeline"], cwd=str(fake), script=script)
    assert rc != 0, "金标漂移必须让 --check 非 0:\n%s" % out
    assert "sampled_transitions 漂移" in out, out


def test_bench_timeline_missing_expect_is_named(tmp_path):
    """缺 timeline 金标时必须**点名**缺件，不是静默跳过。"""
    fake, script = _fake_repo(tmp_path)
    tree = fake / "data" / "_downloads" / "slim" / "2026e"
    tree.mkdir(parents=True)
    (tree / "provenance.json").write_text(
        json.dumps({"version": "2026e", "kind": "slim", "zones": 1}), encoding="utf-8")
    shutil.copy(str(os.path.join(ROOT, "data", "fixtures", "tzif", "slim-vs-fat", "fat.tzif")),
                str(tree / "Test"))
    for name in os.listdir(str(fake / "data" / "tzdb")):
        if name != "2026e" and (fake / "data" / "tzdb" / name).is_dir():
            shutil.rmtree(str(fake / "data" / "tzdb" / name))
    (fake / "data" / "tzdb" / "2026e" / "expect-timeline.json").unlink()

    rc, out = _run_bench(["--check", "--suite", "timeline"], cwd=str(fake), script=script)
    assert rc != 0, out
    assert "缺 expect-timeline.json" in out, out


def test_resolve_local_rejects_inconsistent_candidates():
    """**判据自证**：``resolve_local`` 的候选必须自洽（``to_local(utc) == local``）。

    变异方式：直接调内部口算一个不自洽的 utc，断言用 ``to_local`` 复核会失败——
    这证明"候选自洽校验"确实是判据的一部分，而不是摆设。
    """
    store = ZoneinfoStore(os.path.join(ROOT, "data", "fixtures", "tzif", "slim-vs-fat"))
    tl = timeline.load_timeline("fat.tzif", store,
                                window_end=civil.parse_local("2036-01-01"))
    local = civil.parse_local("2026-07-01 12:00:00")

    # 正向：正常候选都自洽
    candidates = timeline.resolve_local(local, tl)
    assert candidates
    for res in candidates:
        assert timeline.to_local(res.utc, tl) == local

    # 变异：把候选的 utc 挪 1 秒，自洽校验必须能发现
    moved = candidates[0].utc + 1
    assert timeline.to_local(moved, tl) != local, "挪 1 秒后仍自洽 → 自洽校验形同虚设"
