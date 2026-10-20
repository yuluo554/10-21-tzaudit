# -*- coding: utf-8 -*-
"""``python -m tzaudit`` 入口（与 ``tzaudit`` 控制台脚本等价）。"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
