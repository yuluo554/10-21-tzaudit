# -*- coding: utf-8 -*-
"""M4 金标：diff 套件的形态与复算入口（`plan/03` §六 / §十）。

三件事（与 M3 的 `test_m3_windows_gold.py` 同构）：

1. **金标形态**：`data/tzdb/pairs/<old>-<new>.json` 只存输入 + 期望；
   分母非空；名单**非空且类别不止一种**（否则判据空跑/退化）。
2. **复算入口**：`bench/run.py --check --suite diff` 有树时退 0，缺件时退 3。
3. **变异自证**：改金标一条名单 / 改一条 class，判据必须**能跑红**。

第 3 条是重点：M1 的教训是"判据写好了不等于能跑红"；M3 又补了一条——
**改实现时要跑行为测试，改 bench 判据时要跑真实 `--check`**（拿漂移测试当验证会引擎自证）。
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

#: 入仓的版本对（`bench/run.py::DIFF_PAIRS` 必须与它一致）
PAIR_NAMES = ("2026a-2026e",)

#: 金标必需的期望字段（`bench/run.py::DIFF_KEYS` 必须与它一致）
EXPECTED_KEYS = ("zones_compared", "diff_errors", "window", "window_changed",
                 "all_history_changed", "unclassified", "changes")

needs_trees = pytest.mark.skipif(
    not os.path.isdir(SLIM),
    reason="需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）",
)


def _pair_path(name):
    return os.path.join(PAIRS, "%s.json" % name)


def _load_pair(name):
    with io.open(_pair_path(name), "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- 1. 金标形态


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_diff_expect_exists_and_has_required_fields(name):
    path = _pair_path(name)
    assert os.path.isfile(path), "缺 %s（跑 bench/run.py --regen --suite diff）" % path
    doc = _load_pair(name)

    assert doc["suite"] == "diff"
    assert doc["pair"] == name
    assert doc["input"]["old"]["version"] == name.split("-")[0]
    assert doc["input"]["new"]["version"] == name.split("-")[1]
    # K14：主金标两侧都必须是 slim
    assert doc["input"]["old"]["kind"] == "slim"
    assert doc["input"]["new"]["kind"] == "slim"

    expected = doc["expected"]
    for key in EXPECTED_KEYS:
        assert key in expected, "%s 缺字段 %s" % (name, key)

    assert expected["diff_errors"] == 0, "比较必须零错误"
    assert expected["zones_compared"] > 0, "分母必须 > 0（0 与'没比到'必须可区分）"
    assert expected["all_history_changed"], "全历史变更名单不得为空（空 = 判据空跑）"
    assert expected["changes"], "变更记录不得为空"


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_diff_expect_is_normalized_json(name):
    from tzaudit.serialize import dumps_json

    with io.open(_pair_path(name), "r", encoding="utf-8") as fh:
        raw = fh.read()
    assert dumps_json(json.loads(raw)) == raw, "%s 不是规范化 JSON" % name


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_diff_expect_has_no_observation_fields(name):
    """金标只存输入与期望（`test_truth_shape.py` 的同一条纪律，按字段名再钉一次）。"""
    doc = _load_pair(name)
    for key in doc["expected"]:
        assert not key.startswith(("observed", "actual", "runtime")), key


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_diff_expect_has_no_absolute_paths(name):
    with io.open(_pair_path(name), "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "data/_downloads/slim/" in text
    assert ":\\" not in text and ":/Users/" not in text


def test_diff_expect_covers_multiple_classes():
    """金标必须**真的**覆盖多个类别（否则等于只验了一种分类）。"""
    doc = _load_pair("2026a-2026e")
    kinds = set(item["class"] for item in doc["expected"]["changes"])
    assert len(kinds) >= 2, "只覆盖了 %r —— 分类判据可能退化" % sorted(kinds)
    assert "history_reinterpreted" in kinds
    assert "future_rule" in kinds


def test_diff_expect_names_are_sorted_by_byte_order():
    """名单按 UTF-8 字节序（K4）。排序错会让跨平台比对漂。"""
    doc = _load_pair("2026a-2026e")
    for key in ("window_changed", "all_history_changed", "unclassified"):
        names = doc["expected"][key]
        assert names == sorted(names, key=lambda text: text.encode("utf-8")), key

    zones = [item["zone"] for item in doc["expected"]["changes"]]
    assert zones == sorted(zones, key=lambda text: text.encode("utf-8"))


def test_diff_expect_every_change_has_class_and_evidence():
    """每条记录必须有合法 `class` 与 `evidence`（`data/README.md` §4.3）。"""
    from tzaudit import diff

    doc = _load_pair("2026a-2026e")
    valid_evidence = {"table", "tail", "abbr", "link"}
    for item in doc["expected"]["changes"]:
        assert set(item) == {"zone", "class", "evidence"}, item
        assert item["class"] in diff.CLASS_ORDER, item
        assert item["evidence"] in valid_evidence, item


def test_diff_expect_one_record_per_zone():
    """四类互斥 → 名单里同一 zone 只出现一次。"""
    doc = _load_pair("2026a-2026e")
    zones = [item["zone"] for item in doc["expected"]["changes"]]
    assert len(zones) == len(set(zones)), "同一 zone 出现多条"


def test_diff_expect_window_changed_is_subset_of_all_history():
    """`window_changed`（窗口内）必须是 `all_history_changed`（全历史）的子集。

    口径（`data/README.md` §4.3）：`--window` **只收窄**第 1 类，不会新增变更。
    """
    doc = _load_pair("2026a-2026e")
    window_changed = set(doc["expected"]["window_changed"])
    all_changed = set(doc["expected"]["all_history_changed"])
    assert window_changed <= all_changed, sorted(window_changed - all_changed)


# ---------------------------------------------------------------- 2. 复算入口


def _run_bench(args, cwd=None, script=None):
    cmd = [sys.executable, script or os.path.join(ROOT, "bench", "run.py")] + list(args)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, cwd=cwd or ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=env)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


@needs_trees
def test_bench_check_diff_suite_passes():
    rc, out = _run_bench(["--check", "--suite", "diff"])
    assert rc == 0, out
    assert "diff" in out
    assert "对拍=" in out


@needs_trees
def test_bench_check_all_suites_passes():
    rc, out = _run_bench(["--check"])
    assert rc == 0, out
    assert "parse_errors=0" in out
    assert "timeline" in out
    assert "windows" in out
    assert "diff" in out


def test_bench_rejects_unknown_suite_name_diff_era():
    """`--suite` 的合法值现在含 `diff`；反例必须用一个**真的不存在**的名字。

    M3 的坑：把 `windows` 当反例，加新套件后那条测试假红。这里固定用 `no-such-suite`。
    """
    rc, out = _run_bench(["--check", "--suite", "no-such-suite"])
    assert rc == 2, out


# ---------------------------------------------------------------- 3. 变异自证


def _fake_repo(tmp_path):
    """建一个"只有入仓件 + 两棵小树"的假仓库，返回 (root, script)。"""
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
    """在假仓库里放**两棵真树**，并清掉其它版本目录。

    diff 套件要两棵树；只留 `DIFF_PAIRS` 涉及的两个版本，让 `--check` 的分母可控。
    """
    for version in versions:
        source = os.path.join(SLIM, version)
        if not os.path.isdir(source):
            pytest.skip("需要 data/_downloads/slim（先跑 tools/fetch_tzdb.py）")
        tree = fake / "data" / "_downloads" / "slim" / version
        tree.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, str(tree))
    for name in os.listdir(str(fake / "data" / "tzdb")):
        path = fake / "data" / "tzdb" / name
        if name == "pairs" or name in versions:
            continue
        if path.is_dir():
            shutil.rmtree(str(path))
    return versions


def _regen_diff_gold(fake, script):
    """在假仓库里 ``--regen --suite diff`` → 一份**与该对完全一致**的金标。

    有了它，后面的"改一项"才是**唯一**的差异。
    """
    rc, out = _run_bench(["--regen", "--suite", "diff"], cwd=str(fake), script=script)
    assert rc == 0, out
    path = fake / "data" / "tzdb" / "pairs" / "2026a-2026e.json"
    assert path.is_file(), out
    return path


def test_bench_detects_diff_expect_name_drift(tmp_path):
    """**变异自证**：从 `all_history_changed` 里删掉一个 zone，必须报"不相等"。

    这条锚的是"名单**集合相等**"（`plan/04` §二 真值纪律第 3 条）：
    实现少报一个 zone 必须能被抓。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)
    path = _regen_diff_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    names = doc["expected"]["all_history_changed"]
    assert len(names) >= 2, "合成对里至少要两个变更 zone 才能删一个"
    doc["expected"]["all_history_changed"] = names[:-1]
    path.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")

    rc, out = _run_bench(["--check", "--suite", "diff"], cwd=str(fake), script=script)
    assert rc != 0, "金标名单漂移必须让 --check 非 0:\n%s" % out
    assert "all_history_changed" in out, out


def test_bench_detects_diff_expect_class_drift(tmp_path):
    """**变异自证**：把一条记录的 `class` 改掉，必须报漂移。

    名单对、类别错也必须被抓住——否则"名单相等"这一条会被单类退化实现蒙过。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)
    path = _regen_diff_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    target = doc["expected"]["changes"][0]
    # 改成另一个**合法**类别（非法值会被上游拦掉，测不到比对逻辑）
    target["class"] = "alias_only" if target["class"] != "alias_only" else "future_rule"
    path.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")

    rc, out = _run_bench(["--check", "--suite", "diff"], cwd=str(fake), script=script)
    assert rc != 0, "类别漂移必须让 --check 非 0:\n%s" % out
    assert "changes" in out, out


def test_bench_detects_diff_expect_count_drift(tmp_path):
    """**变异自证**：把 `zones_compared` 改一个数，必须报漂移（分母口径被钉住）。"""
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)
    path = _regen_diff_gold(fake, script)

    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["expected"]["zones_compared"] += 1
    path.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")

    rc, out = _run_bench(["--check", "--suite", "diff"], cwd=str(fake), script=script)
    assert rc != 0, "分母漂移必须让 --check 非 0:\n%s" % out
    assert "zones_compared" in out, out


@needs_trees
def test_bench_detects_degenerate_single_class_diff(tmp_path):
    """**变异自证**（判据本身）：把**实现**改成只产一种类别 → `--check` 必须报"退化"。

    这条锚的是 `_check_diff` 的第 4 步（"类别至少两类"）。它防的是**实现退化**，
    不是金标写错——所以变异靶子必须是实现，不是金标。

    M3 的极性教训：改 `src/` 的实现就跑**行为测试**，改 bench 的判据就跑真实
    `--check`。这里是"用 `--check` 验一条 bench 判据"，靶子是实现（在假仓库里改
    `src/tzaudit/diff.py`，不动真仓库）。
    """
    fake, script = _fake_repo(tmp_path)
    _prepare_fake_trees(fake)

    # 变异：在假仓库的 diff.py 末尾追加一个"只产 future_rule"的包装。
    # 追加定义会**遮蔽**原函数（模块级重绑定），是真实的实现变异。
    diff_path = fake / "src" / "tzaudit" / "diff.py"
    original = diff_path.read_text(encoding="utf-8")
    diff_path.write_text(
        original
        + "\n\n# --- 变异：只产一种类别（用于验证 bench 的退化判据）---\n"
        + "_orig_diff_trees = diff_trees\n"
        + "\n\n"
        + "def diff_trees(old_store, new_store, window=None, zone=None):\n"
        + "    result = _orig_diff_trees(old_store, new_store, window, zone)\n"
        + "    result.changes = [c for c in result.changes if c.class_ != ALIAS_ONLY]\n"
        + "    for item in result.changes:\n"
        + "        item.class_ = FUTURE_RULE\n"
        + "    result.summary['changes'] = len(result.changes)\n"
        + "    return result\n",
        encoding="utf-8")

    rc, out = _run_bench(["--check", "--suite", "diff"], cwd=str(fake), script=script)
    assert rc != 0, "只产一类的实现必须被拒:\n%s" % out
    assert "退化" in out or "只产出一类" in out, out
