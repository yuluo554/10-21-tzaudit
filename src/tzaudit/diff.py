# -*- coding: utf-8 -*-
"""版本差异分类 —— 契约见 ``plan/03`` §六。**骨架期**。"""

from __future__ import print_function

from .errors import NotImplementedYet

#: 四类（互斥）+ 固定判定顺序（第一位优先）。口径见 ``data/README.md`` §4.3。
CLASS_ORDER = ("history_reinterpreted", "future_rule", "abbreviation_only", "alias_only")


class Change(object):
    """一条 zone 分类记录。"""

    __slots__ = ("zone", "class_", "window", "before", "after", "evidence", "note")

    def __init__(self, zone, class_, window, before, after, evidence, note=""):
        self.zone = zone
        self.class_ = class_
        self.window = window
        self.before = before
        self.after = after
        self.evidence = evidence
        self.note = note


class DiffResult(object):
    __slots__ = ("changes", "summary")

    def __init__(self, changes, summary):
        self.changes = changes
        self.summary = summary


def diff_trees(old_store, new_store, window=None, zone=None):
    """两棵树的差异分类。M4 实现。"""
    raise NotImplementedYet("版本差异分类尚未实现（M4）；契约见 plan/03 §六")
