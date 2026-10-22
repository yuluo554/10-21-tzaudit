# -*- coding: utf-8 -*-
"""M5 金标：audit 套件的形态与复算入口（`plan/03` §七 / §十）。

三件事（与 M3/M4 的金标测试同构）：

1. **金标形态**：`data/tzdb/pairs/<old>-<new>.audit.json` 只存输入 + 期望；
   清单非空、**四类状态里至少三类**（只有 OK 等于判据空跑）、且含"两版本一致"的对照。
2. **复算入口**：`bench/run.py --check --suite audit` 有树时退 0，缺件时退 3。
3. **变异自证**：改金标一条 status / 删一条行 / 改一条候选 UTC / 把实现改坏
   —— 判据必须**都能跑红**。M3/M4 的教训：判据写好了不等于能跑红。
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
PAIRS = os.path.join(TZDB, "pairs")
SLIM = os.path.join(ROOT, "data", "_downloads", "slim")

#: 入仓的版本对（`bench/run.py::AUDIT_PAIRS` 必须与它一致）
PAIR_NAMES = ("2026a-2026e",)

#: 金标必需的期望字段
EXPECTED_KEYS = ("audit_errors", "rows", "single_version", "statuses",
                 "same_utc_two_walls", "reference_cross_checked")

needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）",
)


def _gold_path(name):
    return os.path.join(PAIRS, "%s.audit.json" % name)


def _load_gold(name):
    with io.open(_gold_path(name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_gold(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


# ---------------------------------------------------------------- 1. 金标形态


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_audit_expect_exists_and_has_required_fields(name):
    path = _gold_path(name)
    assert os.path.isfile(path), "缺 %s（跑 bench/run.py --regen --suite audit）" % path
    doc = _load_gold(name)

    assert doc["suite"] == "audit"
    assert doc["pair"] == name
    assert doc["input"]["old"]["version"] == name.split("-")[0]
    assert doc["input"]["new"]["version"] == name.split("-")[1]
    # K14：主金标两侧都必须是 slim
    assert doc["input"]["old"]["kind"] == "slim"
    assert doc["input"]["new"]["kind"] == "slim"

    expected = doc["expected"]
    for key in EXPECTED_KEYS:
        assert key in expected, "%s 缺字段 %s" % (name, key)

    assert expected["audit_errors"] == 0, "判定必须零错误"
    assert expected["rows"], "清单行不得为空"
    assert expected["reference_cross_checked"] == len(expected["rows"]), (
        "每条清单行都必须被参照实现对拍过（对拍少的等于没验）")


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_audit_expect_covers_status_shapes(name):
    """**判据不得退化**：至少三类 status，且四类里有基准锚点。

    `VERSION_CHANGED` 必须是真实数据里的一条（Dublin 1925 历史重解释），
    不是"只在 fixture 里能出现"的摆设。
    """
    doc = _load_gold(name)
    statuses = set(doc["expected"]["statuses"])
    assert len(statuses) >= 3, "status 只有 %r —— 清单判据可能退化" % sorted(statuses)
    assert {"GAP", "OVERLAP", "OK"} <= statuses, statuses
    assert "VERSION_CHANGED" in statuses, (
        "真实树上必须有一条 VERSION_CHANGED 锚点（否则该判据只有 fixture 覆盖）")

    # 每一类都要有具体行（statuses 只是投影）
    seen = set(item["status"] for item in doc["expected"]["rows"])
    assert seen == statuses


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_audit_expect_has_an_unchanged_control(name):
    """必须有"两版本一致"的对照行（`OK`）——否则"全报 VERSION_CHANGED"也能绿。"""
    doc = _load_gold(name)
    ok_rows = [item for item in doc["expected"]["rows"] if item["status"] == "OK"]
    assert ok_rows, "缺 OK 对照行"
    # 对照行在单树模式下也必须是 OK
    singles = {(item["zone"], item["local"]): item["status"]
               for item in doc["expected"]["single_version"]}
    for row in ok_rows:
        assert singles[(row["zone"], row["local"])] == "OK"


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_audit_single_version_never_reports_version_changed(name):
    """单树模式**不可能**出现 `VERSION_CHANGED`（`plan/03` §七）。"""
    doc = _load_gold(name)
    leaked = [item for item in doc["expected"]["single_version"]
              if item["status"] == "VERSION_CHANGED"]
    assert leaked == [], leaked


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_audit_expect_records_same_utc_two_walls(name):
    """金标必须记下"同一 UTC 两版本两墙钟"的对账（Cal.com 场景的招牌输出）。

    Dublin 1925 的 `1925-09-20T02:30:00Z`：2026a 下是 03:30 墙钟、2026e 下是 02:30
    —— 差 −3600 秒（2026e 把 1925 年的转换重写成"夏令时回拨"）。
    """
    doc = _load_gold(name)
    pairs = doc["expected"]["same_utc_two_walls"]
    assert pairs, "必须至少记一条（否则 BC 类场景没有真实数据锚点）"
    for item in pairs:
        assert item["delta_sec"] != 0, "delta=0 的条目不该进对账表"
        assert item["wall_old"] != item["wall_new"]
    dublin = [item for item in pairs if item["zone"] == "Europe/Dublin"]
    assert dublin, "Dublin 1925 的对账条目必须在内（真实历史重解释）"


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_audit_expect_input_lists_the_times(name):
    """输入侧必须写明清单（zone + local），金标才能被独立复核。"""
    doc = _load_gold(name)
    times = doc["input"]["times"]
    assert times, "input.times 不得为空"
    for item in times:
        assert set(item) == {"zone", "local"}
    assert len(times) == len(doc["expected"]["rows"])


# ---------------------------------------------------------------- 2. 复算入口


def _run_bench(args, cwd=None, script=None):
    target = script or os.path.join(ROOT, "bench", "run.py")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(cwd or ROOT, "src")
    proc = subprocess.Popen([sys.executable, str(target)] + list(args),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=str(cwd or ROOT), env=env)
    out = proc.communicate()[0].decode("utf-8", "replace")
    return proc.returncode, out


@needs_trees
def test_bench_check_audit_exit_0():
    """`--check --suite audit` 退 0（有树 + 金标一致）。"""
    rc, out = _run_bench(["--check", "--suite", "audit"])
    assert rc == 0, out
    assert "audit 金标复算一致" in out, out


def test_bench_check_audit_missing_tree_exits_3(tmp_path):
    """缺本地树 → **退 3**（不是 0 项通过）。"""
    fake = tmp_path / "fake"
    (fake / "bench").mkdir(parents=True)
    (fake / "data").mkdir()
    (fake / "src").mkdir()
    shutil.copytree(str(TZDB), str(fake / "data" / "tzdb"))
    shutil.copytree(str(os.path.join(ROOT, "src", "tzaudit")),
                    str(fake / "src" / "tzaudit"))
    script = fake / "bench" / "run.py"
    shutil.copy(str(os.path.join(ROOT, "bench", "run.py")), str(script))

    rc, out = _run_bench(["--check", "--suite", "audit"], cwd=str(fake), script=script)
    assert rc == 3, out
    assert "环境不满足" in out, out


# ---------------------------------------------------------------- 3. 变异自证


def _fake_repo(tmp_path):
    """造一个**假仓库**（副本）：`bench/run.py` 按 `__file__` 推 ROOT，必须跑副本。"""
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


def _prepare_fake_trees(fake, versions=("2026a", "2026e")):
    """假仓库里放两棵真树，并清掉其它版本目录（让分母可控）。"""
    for version in versions:
        source = os.path.join(SLIM, version)
        if not os.path.isdir(source):
            pytest.skip("需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）")
        tree = fake / "data" / "_downloads" / "slim" / version
        tree.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, str(tree))
    for name in os.listdir(str(fake / "data" / "tzdb")):
        path = fake / "data" / "tzdb" / name
        if name in ("pairs",) or name in versions:
            continue
        if path.is_dir():
            shutil.rmtree(str(path))
    # 只留 audit 金标，避免别的套件的期望干扰"唯一差异"
    pairs = fake / "data" / "tzdb" / "pairs"
    for name in os.listdir(str(pairs)):
        if not name.endswith(".audit.json"):
            (pairs / name).unlink()
    return versions


def _regen_audit_gold(fake, script):
    rc, out = _run_bench(["--regen", "--suite", "audit"], cwd=str(fake), script=script)
    assert rc == 0, out
    path = fake / "data" / "tzdb" / "pairs" / "2026a-2026e.audit.json"
    assert path.is_file(), out
    return path


def test_bench_detects_audit_status_drift(tmp_path):
    """**变异自证**：把金标一条 `status` 改掉 → `--check` 必须非 0。

    这条锚的是"逐行 status 相等"——实现判错类会被抓。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)
    path = _regen_audit_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    row = [item for item in doc["expected"]["rows"] if item["status"] == "OK"][0]
    row["status"] = "OVERLAP"
    _write_gold(path, doc)

    rc, out = _run_bench(["--check", "--suite", "audit"], cwd=str(fake), script=script)
    assert rc != 0, "status 漂移必须让 --check 非 0:\n%s" % out
    assert "audit.rows" in out, out


def test_bench_detects_audit_row_dropped(tmp_path):
    """**变异自证**：从金标里删掉一条行 → 必须报"不相等"。

    锚的是"清单行一条都不能少"（不静默跳过）。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)
    path = _regen_audit_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert len(doc["expected"]["rows"]) >= 2
    doc["expected"]["rows"] = doc["expected"]["rows"][:-1]
    doc["expected"]["single_version"] = doc["expected"]["single_version"][:-1]
    _write_gold(path, doc)

    rc, out = _run_bench(["--check", "--suite", "audit"], cwd=str(fake), script=script)
    assert rc != 0, "少一条行必须让 --check 非 0:\n%s" % out
    assert "audit.rows" in out, out


def test_bench_detects_audit_candidate_utc_drift(tmp_path):
    """**变异自证**：改一条候选 UTC（状态仍是 OVERLAP）→ 必须报漂移。

    锚的是"候选值本身也是期望的一部分"——只比 status 的实现会被抓。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)
    path = _regen_audit_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    row = [item for item in doc["expected"]["rows"]
           if item["status"] == "OVERLAP" and item["utc_candidates"]][0]
    row["utc_candidates"][0] = "1999-01-01T00:00:00Z"
    _write_gold(path, doc)

    rc, out = _run_bench(["--check", "--suite", "audit"], cwd=str(fake), script=script)
    assert rc != 0, "候选 UTC 漂移必须让 --check 非 0:\n%s" % out
    assert "audit.rows" in out, out


def test_bench_detects_audit_single_version_leak(tmp_path):
    """**变异自证**：金标里把单树模式的一条写成 `VERSION_CHANGED` → 必须报错。

    锚的是"单树模式不可能出现 VERSION_CHANGED"这条语义。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)
    path = _regen_audit_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["expected"]["single_version"][0]["status"] = "VERSION_CHANGED"
    _write_gold(path, doc)

    rc, out = _run_bench(["--check", "--suite", "audit"], cwd=str(fake), script=script)
    assert rc != 0, "单树模式出现 VERSION_CHANGED 必须让 --check 非 0:\n%s" % out
    assert "single_version" in out or "VERSION_CHANGED" in out, out


@needs_trees
def test_bench_detects_degenerate_all_ok_audit(tmp_path):
    """**变异自证**（判据本身）：把**实现**改成永远返回 OK → `--check` 必须报"退化"。

    靶子必须是**实现**（改 `src/`），不是金标：改金标会先被"逐行不相等"拦掉，
    测不到"判据退化"那条分支。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)
    _regen_audit_gold(fake, script)

    audit_path = fake / "src" / "tzaudit" / "audit.py"
    original = audit_path.read_text(encoding="utf-8")
    audit_path.write_text(
        original
        + "\n\n# --- 变异：所有行一律 OK（用于验证 bench 的退化判据）---\n"
        + "_orig_judge = _judge\n"
        + "\n\n"
        + "def _judge(item, timelines):\n"
        + "    row = _orig_judge(item, timelines)\n"
        + "    if row.status != INVALID:\n"
        + "        row = Row(row.id, row.local, OK, row.utc_candidates, '', '')\n"
        + "    return row\n",
        encoding="utf-8")

    rc, out = _run_bench(["--check", "--suite", "audit"], cwd=str(fake), script=script)
    assert rc != 0, "永远返回 OK 的实现必须被拒:\n%s" % out
    assert "退化" in out or "只产出" in out, out
