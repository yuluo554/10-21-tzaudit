#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""布局门的变异验证（10 组）——证明"门不是假门"。

纪律（skill 假门族 + 变异脚本三连条）：
- 替换前 assert marker 存在；替换后 assert 文件已变；还原后 assert 字节一致；
- 全部包 try/finally，绝不改动真实工作树（在临时副本里跑）；
- 每组断言"退出码由 0 变 1"，且 FAIL 行里出现预期判据 ID（避免"恰好别处红了"也算通过）；
- **每组必须先自证"变异真的改了字节"**：改动前后比对全副本指纹，若相同则该组报
  `FAIL（靶子已失效）` —— 一个 no-op 的靶子会**静默地**把"这条判据从未被证伪"伪装成"按预期"。
  （这就是 v9 曾失效的形态：靶子前提"还有未完成里程碑"随项目进度腐化，替换退化成 no-op。）

用法：
    py -3.12 tools/mutate-layout-gate.py            # 跑全部 10 组
    退出码 0 = 10/10 都按预期变红/保持绿；1 = 有组不符（含"靶子已失效"）
"""

from __future__ import print_function

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join("tools", "check-sprint-layout.py")

# 副本里必须齐全的路径（门要读的）
COPY = [
    "AGENTS.md", "README.md", "pyproject.toml", ".gitignore", ".gitattributes",
    "data", "plan", "src", "tests", "tools", "bench", ".github",
]


def copy_repo(dst):
    for name in COPY:
        src = os.path.join(ROOT, name)
        if not os.path.exists(src):
            continue
        target = os.path.join(dst, name)
        if os.path.isdir(src):
            shutil.copytree(src, target, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".pytest_cache"))
        else:
            shutil.copy2(src, target)


def repo_fingerprint(cwd):
    """全副本内容指纹（排序后逐个文件的相对路径 + 内容哈希）。

    用途：变异前后的**字节级**自证。指纹不变 ⟺ 该组变异是 no-op ⟹ 靶子已失效。
    """
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(cwd):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for fn in sorted(filenames):
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, cwd).replace(os.sep, "/")
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            try:
                with open(path, "rb") as fh:
                    digest.update(hashlib.sha256(fh.read()).digest())
            except (IOError, OSError):
                digest.update(b"<unreadable>")
    return digest.hexdigest()


def run_gate(cwd):
    proc = subprocess.run(
        [sys.executable, GATE], cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def read(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def mutate_file(cwd, rel, old, new):
    """三连断言：marker 存在 → 已变 → （返回还原函数）。"""
    path = os.path.join(cwd, rel)
    before = read(path)
    assert old in before, "marker 不存在于 %s: %r" % (rel, old[:50])
    after = before.replace(old, new, 1)
    assert after != before, "替换未产生字节变化: %s" % rel
    write(path, after)
    assert read(path) == after, "写入未生效: %s" % rel

    def restore():
        write(path, before)
        assert read(path) == before, "还原失败: %s" % rel

    return restore


def write_new(cwd, rel, text):
    path = os.path.join(cwd, rel)
    assert not os.path.exists(path), "目标已存在，不能当'新建'变异: %s" % rel
    write(path, text)

    def restore():
        if os.path.exists(path):
            os.remove(path)
        assert not os.path.exists(path), "清理失败: %s" % rel

    return restore


def delete_file(cwd, rel):
    path = os.path.join(cwd, rel)
    assert os.path.exists(path), "要删的文件不存在: %s" % rel
    backup = read(path)
    os.remove(path)
    assert not os.path.exists(path)

    def restore():
        write(path, backup)
        assert os.path.exists(path) and read(path) == backup, "还原失败: %s" % rel

    return restore


# ---------------------------------------------------------------- 10 组变异
def v1(cwd):
    return delete_file(cwd, "AGENTS.md")


def v2(cwd):
    return delete_file(cwd, "plan/03-模块详设.md")


def v3(cwd):
    text = read(os.path.join(cwd, "plan/00-README总览.md"))
    lines = text.split("\n")
    target = [ln for ln in lines if ln.startswith(">") and "ai-tool-project-sprint" in ln]
    assert len(target) == 1, "装订行不唯一"
    idx = lines.index(target[0])
    del lines[idx]
    write(os.path.join(cwd, "plan/00-README总览.md"), "\n".join(lines))
    backup = text

    def restore():
        write(os.path.join(cwd, "plan/00-README总览.md"), backup)

    return restore


def v4(cwd):
    """把 plan/05 里 M0 的 ✅ 改成 ⬜（与其余三处副本不一致）。"""
    path = os.path.join(cwd, "plan/05-里程碑与发布.md")
    text = read(path)
    needle = "| M0 | 出题定稿 + 方法论装订 + 可运行骨架 |"
    assert needle in text
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("| M0 |"):
            assert "✅" in line, "M0 行里没有 ✅"
            lines[i] = line.replace("✅ 已完成（2026-10-21）", "⬜ 未开始").replace("✅", "⬜")
            break
    write(path, "\n".join(lines))

    def restore():
        write(path, text)

    return restore


def v5(cwd):
    return delete_file(cwd, "plan/HANDOFF-M1.md")


def v6(cwd):
    """在缺口表的**「缺口」单元格**里写已 ✅ 的 M0。

    坑（本脚本实测）：首版把 G1 行的「关闭里程碑」从 M1 改成 M0 —— 门扫的是**「缺口」列**
    （按表头定位列号），改另一列当然不红。这正是 skill 的"变异靶子瞄错"形态：
    **先确认门扫的是哪一列，再决定改哪一格**。
    """
    path = os.path.join(cwd, "plan/06-交付对标与决策.md")
    text = read(path)
    lines = text.split("\n")
    header = next(i for i, ln in enumerate(lines) if ln.startswith("|") and "缺口" in ln)
    row = header + 2
    assert lines[row].startswith("| G1 |"), "缺口表第一行不是 G1"
    before = lines[row]
    assert "五版本真实数据未入仓" in before
    lines[row] = before.replace("五版本真实数据未入仓", "五版本真实数据未入仓（M0 遗留）", 1)
    assert lines[row] != before
    write(path, "\n".join(lines))

    def restore():
        write(path, text)
        assert read(path) == text

    return restore


def v7(cwd):
    path = os.path.join(cwd, "plan/00-README总览.md")
    text = read(path)
    assert "| TZif 四版本（v1–v4）解析 |" in text
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("| TZif 四版本（v1–v4）解析 |"):
            lines[i] = line.rsplit("|", 2)[0] + "| ⬜ 待 M0 |"
            break
    write(path, "\n".join(lines))

    def restore():
        write(path, text)

    return restore


def v9(cwd):
    """直接打 `LAYOUT.RELEASE` 的两条**独立子判据**（与里程碑状态无关）。

    坑（本脚本实测，D1）：最初 v9 的靶子是"把尚未完成的 M6 篡改成 ✅ 但不建 RELEASE 留档"
    —— 那要靠"**还有未完成里程碑**"这个会腐的前提。M6 真完成后三处副本本来就是 ✅，
    `.replace("⬜","✅")` 退化成 no-op ⇒ 变异没改任何字节 ⇒ 门当然不红 ⇒ `FAIL V9`，
    而四处文档仍写 10/10。**靶子随项目进度失效**是这类变异最隐蔽的失效形态。

    正解 = 打门自己的两条子判据（它们与里程碑状态无关，永远有效）：
      (a) 覆盖对账小节标题 —— 把「阶段 7 覆盖对账」标题里的「覆盖对账」改掉 → `coverage` 假；
      (b) 两栏标记 —— 把「## 二、tag 后追加」改成「## 二、tag 之后追加」→ `two_cols` 假。
    **两条同时打**，并在群里断言 FAIL 明细里 `两栏:False` 与 `覆盖对账小节:False` **同时**出现
    —— 这比"只删一处、只看 rc=1"强：若门悄悄丢掉了其中一条子判据，明细就不会出现对应的 False。
    """
    path = os.path.join(cwd, "plan/RELEASE-M6.md")
    before = read(path)
    after = before.replace("阶段 7 覆盖对账", "阶段 7 覆盖检查", 1)
    assert after != before, "覆盖对账标题未命中: plan/RELEASE-M6.md"
    after2 = after.replace("## 二、tag 后追加", "## 二、tag 之后追加", 1)
    assert after2 != after, "两栏标记未命中: plan/RELEASE-M6.md"
    write(path, after2)
    assert read(path) == after2

    def restore():
        write(path, before)
        assert read(path) == before, "还原失败: plan/RELEASE-M6.md"

    return restore


def v10(cwd):
    """在 plan/02 里新增一行引用一个不存在的 tools/ 脚本（路径在运行时拼，避免本文件自命中）。"""
    path = os.path.join(cwd, "plan/02-架构与技术选型.md")
    text = read(path)
    ghost = "tools/" + "ghost-tool" + ".py"
    write(path, text + "\n- 变异探针引用: `" + ghost + "`\n")

    def restore():
        write(path, text)

    return restore


#: (编号, 构造, 期望变红? , 期望命中的判据 ID 或 None, 期望在 FAIL 明细里同现的子串)
CASES = [
    ("V1", v1, True, "LAYOUT.FILES", ()),
    ("V2", v2, True, "LAYOUT.FILES", ()),
    ("V3", v3, True, "LAYOUT.BINDING_HEAD", ()),
    ("V4", v4, True, "LAYOUT.STATUS", ()),
    ("V5", v5, True, "LAYOUT.NEXT_HANDOFF", ()),
    ("V6", v6, True, "LAYOUT.GAPS", ()),
    ("V7", v7, True, "LAYOUT.LEDGER", ()),
    ("V8", None, False, None, ()),  # 反向对照：基线必须绿
    # V9 打了 LAYOUT.RELEASE 的**两条**子判据，明细里两条 False 必须同现
    # （门若悄悄丢了一条子判据，这里就不成立）。
    ("V9", v9, True, "LAYOUT.RELEASE", ("两栏:False", "覆盖对账小节:False")),
    ("V10", v10, True, "LAYOUT.DOC_TOOLS", ()),
]


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix="tzaudit-mutate-") as tmp:
        cwd = os.path.join(tmp, "repo")
        os.makedirs(cwd)
        copy_repo(cwd)

        rc, out = run_gate(cwd)
        if rc != 0:
            print("基线不绿，变异验证无意义：\n" + out)
            return 1
        print("基线: rc=0（%d 条判据全绿）" % out.count("PASS"))
        base_fp = repo_fingerprint(cwd)

        for name, mutate, expect_red, expect_id, expect_detail in CASES:
            if mutate is None:
                print("PASS  %s  反向对照：基线保持绿" % name)
                continue
            restore = None
            try:
                restore = mutate(cwd)
                # ---- 自证：变异必须真的改了字节（靶子失效会产生 no-op）----
                mut_fp = repo_fingerprint(cwd)
                if mut_fp == base_fp:
                    print("FAIL  %s  靶子已失效（变异是 no-op，没有改变任何字节）" % name)
                    failures.append(name)
                    restore()
                    restore = None
                    continue
                rc, out = run_gate(cwd)
                if expect_red:
                    missing = [s for s in expect_detail if s not in out]
                    ok = rc == 1 and expect_id in out and not missing
                    if ok:
                        detail = "变红且命中 " + expect_id
                    elif rc != 1:
                        detail = "rc=%d，期望命中 %s" % (rc, expect_id)
                    elif expect_id not in out:
                        detail = "rc=1 但 FAIL 未命中 %s" % expect_id
                    else:
                        detail = "FAIL 明细缺子串: %s" % " / ".join(missing)
                else:
                    ok = rc == 0
                    detail = "" if ok else "rc=%d，期望保持绿" % rc
                print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, detail))
                if not ok:
                    failures.append(name)
                    print(out)
            finally:
                if restore is not None:
                    restore()
            rc, out = run_gate(cwd)
            if rc != 0:
                failures.append(name + "-restore")
                print("FAIL  %s  还原后未复绿（rc=%d）\n%s" % (name, rc, out))
            if repo_fingerprint(cwd) != base_fp:
                failures.append(name + "-worktree")
                print("FAIL  %s  还原后副本指纹与基线不一致" % name)

    print("=" * 56)
    print("变异验证: %d/%d 组按预期" % (len(CASES) - len(failures), len(CASES)))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
