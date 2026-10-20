# -*- coding: utf-8 -*-
"""退出码与异常类型 —— 全项目单点定义。

语义权威在 ``data/README.md`` §4.4；本模块只做**常量映射**，不另立第二套语义。
新增/退役退出码必须同步四处：本模块 → ``cli.py`` → ``tests/test_exit_codes.py`` → 文档。
"""

#: 成功且门禁未命中
EXIT_OK = 0
#: 门禁命中（--fail-on）
EXIT_GATE_HIT = 1
#: 用法错误（参数缺失/互斥/非法枚举）
EXIT_USAGE = 2
#: 环境不满足（路径不存在 / 缺 provenance / TZif 损坏）
EXIT_ENV = 3
#: 输入数据无效（清单坏行）
EXIT_INVALID_INPUT = 4
#: 功能未就绪（骨架期；模块落地后**整项退役**，见 plan/03 §九）
EXIT_NOT_READY = 5


class TzAuditError(Exception):
    """所有可预期错误的基类；``exit_code`` 决定 CLI 的退出码。"""

    exit_code = 1

    def __init__(self, message):
        super(TzAuditError, self).__init__(message)
        self.message = message


class UsageError(TzAuditError):
    exit_code = EXIT_USAGE


class EnvironmentProblem(TzAuditError):
    """路径不存在、缺 provenance、TZif 损坏等"这台机器做不了"的情形。"""

    exit_code = EXIT_ENV


class InvalidInput(TzAuditError):
    exit_code = EXIT_INVALID_INPUT


class ReportIncomplete(TzAuditError):
    """报告头三字段缺失（``data/README.md`` §4.5）。"""

    exit_code = EXIT_ENV


class NotImplementedYet(TzAuditError):
    """骨架期占位：子命令尚未实现。模块落地后必须删除本类及其全部引用。"""

    exit_code = EXIT_NOT_READY
