# -*- coding: utf-8 -*-
"""依赖方向守门：下层不得 import 上层。

分层见 ``plan/02`` §一。这条用 AST 扫描实现，不靠人记。
"""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "tzaudit")

#: 模块 → 允许 import 的同包模块（不含自身）
ALLOWED = {
    "errors": set(),
    "civil": set(),
    "serialize": set(),
    "zoneinfo_store": {"errors"},
    "tzif": {"errors"},
    "posix_tz": {"errors"},
    "timeline": {"errors", "tzif", "posix_tz", "zoneinfo_store", "civil"},
    "windows": {"errors", "timeline", "civil"},
    "diff": {"errors", "timeline", "zoneinfo_store", "civil"},
    "audit": {"errors", "timeline", "diff", "civil"},
    "report": {"errors"},
    "cli": {"errors", "civil", "serialize", "zoneinfo_store", "timeline",
            "windows", "diff", "audit", "report", "__init__"},
    "__main__": {"cli"},
    "__init__": set(),
}


def _package_imports(path):
    """返回该文件从本包 import 的模块名集合（含相对 import 与 from pkg import sub）。"""
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                # from . import x  /  from .mod import x
                if node.module:
                    found.add(node.module.split(".")[0])
                else:
                    for alias in node.names:
                        # `from . import x`：x 可能是子模块，也可能是包内属性（如 __version__）
                        if alias.name.startswith("_"):
                            continue
                        found.add(alias.name.split(".")[0])
            elif node.module and node.module.startswith("tzaudit."):
                found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tzaudit."):
                    found.add(alias.name.split(".")[1])
    return found


def test_layers_do_not_import_upwards():
    problems = []
    scanned = 0
    for name in sorted(os.listdir(PKG)):
        if not name.endswith(".py"):
            continue
        module = name[:-3]
        scanned += 1
        assert module in ALLOWED, "新模块 %s 未在 ALLOWED 里声明依赖面（先补 plan/02 §一）" % module
        imports = _package_imports(os.path.join(PKG, name))
        illegal = imports - ALLOWED[module] - {module}
        if illegal:
            problems.append("%s.py 非法 import: %s" % (module, ", ".join(sorted(illegal))))
    assert scanned >= 12, "只扫到 %d 个模块——AST 守门可能空跑" % scanned
    assert problems == [], "\n".join(problems)


def test_reference_implementation_is_not_imported_by_package():
    """独立参照实现必须在 tests/，生产模块禁止 import 它（否则对拍变成自我验证）。"""
    problems = []
    for name in sorted(os.listdir(PKG)):
        if not name.endswith(".py"):
            continue
        imports = _package_imports(os.path.join(PKG, name))
        if "reference" in imports:
            problems.append(name)
    assert problems == [], "生产模块 import 了参照实现: %s" % problems
