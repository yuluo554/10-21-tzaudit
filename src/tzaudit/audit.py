# -*- coding: utf-8 -*-
"""本地时间清单审计 —— 契约见 ``plan/03`` §七。**骨架期**。"""

from __future__ import print_function

from .errors import NotImplementedYet

GAP = "GAP"
OVERLAP = "OVERLAP"
VERSION_CHANGED = "VERSION_CHANGED"
OK = "OK"
INVALID = "INVALID"


class Row(object):
    """一条输入时刻的判定。"""

    __slots__ = ("id", "local", "status", "utc_candidates", "note", "invalid_reason")

    def __init__(self, id_, local, status, utc_candidates=(), note="", invalid_reason=""):
        self.id = id_
        self.local = local
        self.status = status
        self.utc_candidates = list(utc_candidates)
        self.note = note
        self.invalid_reason = invalid_reason


class AuditResult(object):
    __slots__ = ("rows", "summary")

    def __init__(self, rows, summary):
        self.rows = rows
        self.summary = summary


def audit_rows(rows, zone, versions=None):
    """逐行判定。M5 实现。"""
    raise NotImplementedYet("清单审计尚未实现（M5）；契约见 plan/03 §七")
