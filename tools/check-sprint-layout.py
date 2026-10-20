#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""布局门（方法论装订第②件）。

把"项目还长在 ai-tool-project-sprint 方法论上"变成一条**可跑红**的断言。
判据一律落**仓库内文件**（不读 git 元数据：浅克隆下 tag / 历史深度会翻转）。

退出码：0 全绿 / 1 有 FAIL / 2 用法错误。

纪律（与 skill 的假门族逐条对齐）：
- 非空跑自证：每条判据都打印"这轮扫到了几个"；0 与"没扫到"必须可区分。
- 状态真值**不取自任何一个副本**：逐副本采集 Map<k, Set<done|pending>>，任一冲突即红。
- 表头定位：按表头找列号再取单元格，不用"行里含某个词"。
- 判据作用域：缺口表扫描面 = 表头 → 首条非表格行；匹配前剥掉行内代码与文件路径。
- 永不崩：每步 try/except，异常报一条 FAIL 并继续。
"""

from __future__ import print_function

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHECKS = []
SCANNED = {"docs": 0, "handoffs": 0, "copies": 0, "doc_tools": 0}


def add(check_id, ok, detail):
    CHECKS.append({"id": check_id, "ok": bool(ok), "detail": detail})


def read(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.isfile(path):
        return None
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "data/README.md",
    "plan/00-README总览.md",
    "plan/01-题目文档.md",
    "plan/02-架构与技术选型.md",
    "plan/03-模块详设.md",
    "plan/04-数据计划.md",
    "plan/05-里程碑与发布.md",
    "plan/06-交付对标与决策.md",
]

# 装订行：三个锚点必须**同现于一行**（顺序无关，用前瞻而不是 A.*B.*C）。
BINDING_LINE = re.compile(
    r"^>(?=.*ai-tool-project-sprint)(?=.*check-sprint-layout)(?=.*20\d{2}-\d{2}-\d{2}).*$",
    re.MULTILINE,
)

REQUIRED_SECTIONS = {
    "plan/00-README总览.md": ["文档索引", "决策记录", "承诺-证据台账", "里程碑"],
    "plan/01-题目文档.md": ["任务要求", "评分标准", "边界与非目标"],
    "plan/02-架构与技术选型.md": ["分层", "构建"],
    "plan/03-模块详设.md": ["接口", "判定顺序", "测试点"],
    "plan/04-数据计划.md": ["数据清单", "真值纪律", "数值口径"],
    "plan/05-里程碑与发布.md": ["DoD", "已知未验证项"],
    "plan/06-交付对标与决策.md": ["评分对标", "风险登记"],
    "data/README.md": ["依据查证记录", "数值口径"],
}

# HANDOFF 七节（超集合法：只断言"必需节都存在"，不断言节数相等）。
HANDOFF_SECTIONS = ["当前进度", "当前事实", "待办", "既定口径", "环境坑", "DoD", "命令速查"]
EXEMPT_MILESTONES = [0]  # M0 的收尾记录就是计划套件本身（已声明豁免）

STATUS_COPIES = [
    "plan/00-README总览.md",
    "plan/05-里程碑与发布.md",
    "README.md",
]

# 只认"状态行"：表格行且首格就是里程碑号（自由文本不参与判定）。
STATUS_LINE = re.compile(r"^\|\s*\*{0,2}M(\d+)\b")
PENDING_MARKERS = ["⬜", "🟡", "未开始", "未执行", "待执行", "待确认", "未验证"]

RELEASE_MILESTONE = 6

# 匹配前剥掉：行内代码、markdown 链接目标、文件名（避免"标识符撞状态 token"）。
INLINE_CODE = re.compile(r"`[^`]*`")
FILE_NAME = re.compile(r"[\w./-]+\.(?:md|py|json|yml|yaml|toml|txt|csv)")


def strip_identifiers(text):
    text = INLINE_CODE.sub(" ", text)
    text = FILE_NAME.sub(" ", text)
    return text


def milestone_ref(k):
    return re.compile(r"(^|[^0-9A-Za-z])M%d([^0-9]|$)" % k)


def check_required_files():
    missing = [rel for rel in REQUIRED_FILES if not os.path.isfile(os.path.join(ROOT, rel))]
    SCANNED["docs"] = len(REQUIRED_FILES) - len(missing)
    if missing:
        add("LAYOUT.FILES", False, "缺: " + ", ".join(missing))
    else:
        add("LAYOUT.FILES", True, "%d 份齐备" % SCANNED["docs"])


def check_binding_head():
    text = read("plan/00-README总览.md") or ""
    ok = bool(BINDING_LINE.search(text))
    add(
        "LAYOUT.BINDING_HEAD",
        ok,
        "plan/00 顶部有装订行（三锚点齐）"
        if ok
        else "plan/00 顶部缺装订行（需同行同现：方法论名 + 布局门命令 + 装订日期）",
    )


def check_sections():
    bad = []
    for rel, needles in REQUIRED_SECTIONS.items():
        text = read(rel)
        if text is None:
            continue
        missing = [n for n in needles if n not in text]
        if missing:
            bad.append("%s: %s" % (rel, "/".join(missing)))
    add(
        "LAYOUT.SECTIONS",
        not bad,
        "；".join(bad) if bad else "%d 份小节齐备" % len(REQUIRED_SECTIONS),
    )


def collect_states():
    """逐副本采集 Map<k, Set<state>>。真值不取自任何一个副本。"""
    states = {}
    for rel in STATUS_COPIES:
        text = read(rel)
        if text is None:
            continue
        SCANNED["copies"] += 1
        for line in text.split("\n"):
            m = STATUS_LINE.match(line)
            if not m:
                continue
            pending = any(mark in line for mark in PENDING_MARKERS)
            states.setdefault(int(m.group(1)), set()).add("pending" if pending else "done")
    return states


def check_status_agreement(states):
    conflicts = []
    for k in sorted(states):
        if len(states[k]) > 1:
            conflicts.append("M%d 在副本间状态不一致（%s）" % (k, " vs ".join(sorted(states[k]))))
    add(
        "LAYOUT.STATUS",
        not conflicts,
        "；".join(conflicts)
        if conflicts
        else "%d 处副本 × %d 个里程碑 状态全一致" % (SCANNED["copies"], len(states)),
    )


def check_handoffs(done):
    problems = []
    for k in sorted(done):
        if k in EXEMPT_MILESTONES:
            continue
        rel = "plan/HANDOFF-M%d.md" % k
        text = read(rel)
        if text is None:
            problems.append(rel + "(缺)")
            continue
        SCANNED["handoffs"] += 1
        lack = [n for n in HANDOFF_SECTIONS if n not in text]
        if lack:
            problems.append("%s(缺节: %s)" % (rel, "/".join(lack)))
    add(
        "LAYOUT.HANDOFFS",
        not problems,
        "；".join(problems) if problems else "%d 份交接单齐（M0 已声明豁免）" % SCANNED["handoffs"],
    )


def check_next_handoff(states):
    """"下一棒待办"必须已有交接单。

    理由：HANDOFF 是**收尾动作的产物**（写完才允许结束对话），不是"下一棒开工时再补"。
    只看 ✅ 里程碑时，M0 豁免会让这条判据在项目最早阶段恒为空跑（"0 份"与"没扫到"同形）。
    本条把"标了 ⬜ 下一步的那个里程碑"也纳入：它的交接单必须已经存在。
    """
    if not states:
        add("LAYOUT.NEXT_HANDOFF", False, "没采集到任何里程碑状态——判据空跑")
        return
    done = sorted(k for k, v in states.items() if "done" in v)
    nexts = sorted(k for k, v in states.items() if "pending" in v and "done" not in v)
    if not nexts:
        add("LAYOUT.NEXT_HANDOFF", True, "全部里程碑已完成（%d 个），无下一棒" % len(done))
        return
    target = nexts[0]
    rel = "plan/HANDOFF-M%d.md" % target
    text = read(rel)
    if text is None:
        add(
            "LAYOUT.NEXT_HANDOFF",
            False,
            "下一棒 M%d 无交接单 %s（收尾时必须先落盘再结束对话）" % (target, rel),
        )
        return
    SCANNED["handoffs"] += 1
    lack = [n for n in HANDOFF_SECTIONS if n not in text]
    add(
        "LAYOUT.NEXT_HANDOFF",
        not lack,
        ("%s 缺节: %s" % (rel, "/".join(lack))) if lack else "%s 在位且七节齐（下一棒 M%d）" % (rel, target),
    )


def check_stale_gaps(done):
    lines = (read("plan/06-交付对标与决策.md") or "").split("\n")
    header_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("|") and "缺口" in line:
            header_idx = i
            break
    if header_idx < 0:
        add("LAYOUT.GAPS", False, "plan/06 找不到含『缺口』表头的表（判据表搬走了？）")
        return
    cells = [c.strip() for c in lines[header_idx].split("|")]
    try:
        col = [i for i, c in enumerate(cells) if "缺口" in c][0]
    except IndexError:
        add("LAYOUT.GAPS", False, "缺口表头里定位不到『缺口』列")
        return
    stale = []
    scanned_rows = 0
    for line in lines[header_idx + 2:]:
        if not line.startswith("|"):
            break  # 表结束（不是"本行跳过"）
        scanned_rows += 1
        row_cells = line.split("|")
        cell = row_cells[col] if col < len(row_cells) else ""
        cell = strip_identifiers(cell)
        for k in done:
            if milestone_ref(k).search(cell):
                stale.append("plan/06 缺口列仍提 M%d: %s" % (k, cell.strip()))
    add(
        "LAYOUT.GAPS",
        not stale,
        "；".join(stale) if stale else "plan/06 缺口列扫了 %d 行，无已 ✅ 里程碑" % scanned_rows,
    )


def check_ledger(done):
    text = read("plan/00-README总览.md") or ""
    lines = text.split("\n")
    header_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("|") and "承诺" in line and "状态" in line:
            header_idx = i
            break
    if header_idx < 0:
        add("LAYOUT.LEDGER", False, "plan/00 找不到『承诺-证据台账』表头（承诺项 + 状态列）")
        return
    SCANNED["copies"] += 1
    bad = []
    rows = 0
    for line in lines[header_idx + 2:]:
        if not line.startswith("|"):
            break
        rows += 1
        cells = [c.strip() for c in line.split("|")]
        status = cells[-2] if len(cells) >= 2 else ""
        if not re.search(r"[⬜🟡]|未开始|待 M\d|待开工|未验证", status):
            continue
        for k in done:
            if milestone_ref(k).search(status):
                bad.append("台账行仍挂未完成: %s" % status[:60])
    add(
        "LAYOUT.LEDGER",
        (not bad) and rows > 0,
        "台账表 0 行——判据空跑"
        if rows == 0
        else ("；".join(bad) if bad else "台账 %d 行，已成 ✅ 的里程碑无未完成标记" % rows),
    )


def check_release_doc(done, all_milestones):
    release_milestone = RELEASE_MILESTONE
    if release_milestone not in done:
        add(
            "LAYOUT.RELEASE",
            True,
            "发布里程碑 M%d 未完成，收尾记录尚不适用（已扫 %d 个 ✅ 里程碑）"
            % (release_milestone, len(done)),
        )
        return
    rel = "plan/RELEASE-M%d.md" % release_milestone
    wrap = "plan/WRAPUP-M%d.md" % release_milestone
    text = read(rel)
    if text is None:
        if read(wrap) is not None:
            add("LAYOUT.RELEASE", True, "WRAPUP 形态")
            return
        add("LAYOUT.RELEASE", False, "缺 %s 或 %s" % (rel, wrap))
        return
    two_cols = bool(re.search(r"^##\s*一、tag 前事实", text, re.MULTILINE)) and bool(
        re.search(r"^##\s*二、tag 后追加", text, re.MULTILINE)
    )
    coverage = bool(re.search(r"^#{2,3}.*覆盖对账", text, re.MULTILINE))
    rows = len(re.findall(r"^\|.*(实现|不适用|待首推).*\|$", text, re.MULTILINE))
    add(
        "LAYOUT.RELEASE",
        two_cols and coverage and rows >= 3,
        "两栏:%s 覆盖对账小节:%s 三态行数:%d" % (two_cols, coverage, rows),
    )


TOOL_PATH = re.compile(r"tools/[\w.-]+\.(?:py|mjs|js|cjs|sh|ps1)")


def check_documented_tools_exist():
    docs = ["AGENTS.md"]
    plan_dir = os.path.join(ROOT, "plan")
    if os.path.isdir(plan_dir):
        docs += ["plan/" + f for f in sorted(os.listdir(plan_dir)) if f.endswith(".md")]
    referenced = set()
    for rel in docs:
        text = read(rel)
        if text is None:
            continue
        for m in TOOL_PATH.finditer(text):
            referenced.add(m.group(0))
    if not referenced:
        add(
            "LAYOUT.DOC_TOOLS",
            False,
            "扫了 %d 份文档，0 处 tools/ 引用——判据是空的（阳性对照失败）" % len(docs),
        )
        return
    SCANNED["doc_tools"] = len(referenced)
    missing = [rel for rel in sorted(referenced) if not os.path.isfile(os.path.join(ROOT, rel))]
    add(
        "LAYOUT.DOC_TOOLS",
        not missing,
        ("文档点名但不存在的工具: " + ", ".join(missing))
        if missing
        else "%d 个文档点名的 tools/ 脚本全部在位" % len(referenced),
    )


def main():
    steps = [
        check_required_files,
        check_binding_head,
        check_sections,
        check_documented_tools_exist,
    ]
    for step in steps:
        try:
            step()
        except Exception as exc:  # 永不崩：报一条 FAIL 并继续
            add(getattr(step, "__name__", "step"), False, "异常: %r" % (exc,))

    states = {}
    try:
        states = collect_states()
    except Exception as exc:
        add("LAYOUT.STATUS", False, "采集状态异常: %r" % (exc,))

    done = sorted(k for k, v in states.items() if "done" in v)
    all_milestones = sorted(states)

    for step in [
        lambda: check_status_agreement(states),
        lambda: check_handoffs(done),
        lambda: check_next_handoff(states),
        lambda: check_stale_gaps(done),
        lambda: check_ledger(done),
        lambda: check_release_doc(done, all_milestones),
    ]:
        try:
            step()
        except Exception as exc:
            add("step", False, "异常: %r" % (exc,))

    out = sys.stdout
    out.write("布局门（方法论装订） · 判据只落仓库内文件\n")
    out.write("=" * 56 + "\n")
    for c in CHECKS:
        out.write("%s  %s  %s\n" % ("PASS" if c["ok"] else "FAIL", c["id"], c["detail"]))
    out.write("=" * 56 + "\n")
    out.write(
        "这轮扫到：文档 %d / 交接单 %d / 状态副本 %d / 文档点名的工具 %d\n"
        % (SCANNED["docs"], SCANNED["handoffs"], SCANNED["copies"], SCANNED["doc_tools"])
    )
    failed = [c for c in CHECKS if not c["ok"]]
    out.write("结论: %s\n" % ("全绿" if not failed else "%d 项 FAIL" % len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
