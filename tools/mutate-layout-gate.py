#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""布局门的变异验证（10 组）——证明"门不是假门"。

纪律（skill 假门族 + 变异脚本三连条）：
- 替换前 assert marker 存在；替换后 assert 文件已变；还原后 assert 字节一致；
- 全部包 try/finally，绝不改动真实工作树（在临时副本里跑）；
- 每组断言"退出码由 0 变 1"，且 FAIL 行里出现预期判据 ID（避免"恰好别处红了"也算通过）。

用法：
    py -3.12 tools/mutate-layout-gate.py            # 跑全部 10 组
    退出码 0 = 10/10 都按预期变红/保持绿；1 = 有组不符
"""

from __future__ import print_function

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
    """把 M6 在四处副本都标 ✅，但不建 RELEASE 留档 → LAYOUT.RELEASE 必红。

    坑（本脚本实测）：最初在"台账行"那一步又存了一份 `backups` 快照，而那份快照是**改过之后**的
    ——还原时按 dict 顺序写，后写的那份把原始内容覆盖回去失败 → "还原后未复绿"。
    正解 = **每份文件只存一份原始快照**（在动任何字节之前采集）。
    """
    targets = [
        ("plan/00-README总览.md", "| M6 | 发布 |"),
        ("plan/05-里程碑与发布.md", "| M6 | 发布 |"),
        ("README.md", "| M6 | 发布：tag + Release + 发布留档 |"),
    ]
    backups = {}
    for rel, _ in targets:
        backups[rel] = read(os.path.join(cwd, rel))

    for rel, pattern in targets:
        path = os.path.join(cwd, rel)
        lines = read(path).split("\n")
        hit = False
        for i, line in enumerate(lines):
            if line.startswith(pattern):
                lines[i] = line.replace("⬜", "✅").replace("下一步", "")
                hit = True
                break
        assert hit, "%s 里找不到 M6 行: %r" % (rel, pattern)
        write(path, "\n".join(lines))

    path = os.path.join(cwd, "plan/00-README总览.md")
    lines = read(path).split("\n")
    for i, line in enumerate(lines):
        if line.startswith("| 发布三件套 |"):
            lines[i] = line.replace("⬜ 待 M6", "✅")
            break
    write(path, "\n".join(lines))

    def restore():
        for rel, content in backups.items():
            write(os.path.join(cwd, rel), content)
            assert read(os.path.join(cwd, rel)) == content, "还原失败: %s" % rel

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


#: (编号, 构造, 期望变红? , 期望命中的判据 ID 或 None)
CASES = [
    ("V1", v1, True, "LAYOUT.FILES"),
    ("V2", v2, True, "LAYOUT.FILES"),
    ("V3", v3, True, "LAYOUT.BINDING_HEAD"),
    ("V4", v4, True, "LAYOUT.STATUS"),
    ("V5", v5, True, "LAYOUT.NEXT_HANDOFF"),
    ("V6", v6, True, "LAYOUT.GAPS"),
    ("V7", v7, True, "LAYOUT.LEDGER"),
    ("V8", None, False, None),  # 反向对照：基线必须绿
    ("V9", v9, True, "LAYOUT.RELEASE"),
    ("V10", v10, True, "LAYOUT.DOC_TOOLS"),
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

        for name, mutate, expect_red, expect_id in CASES:
            if mutate is None:
                print("PASS  %s  反向对照：基线保持绿" % name)
                continue
            restore = None
            try:
                restore = mutate(cwd)
                rc, out = run_gate(cwd)
                if expect_red:
                    ok = rc == 1 and expect_id in out
                    detail = "" if ok else "rc=%d，期望命中 %s" % (rc, expect_id)
                else:
                    ok = rc == 0
                    detail = "" if ok else "rc=%d，期望保持绿" % rc
                print("%s  %s  %s" % ("PASS" if ok else "FAIL", name,
                                      "变红且命中 " + expect_id if ok and expect_red
                                      else ("保持绿" if ok else detail)))
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

    print("=" * 56)
    print("变异验证: %d/%d 组按预期" % (len(CASES) - len(failures), len(CASES)))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
