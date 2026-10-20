# -*- coding: utf-8 -*-
"""把 src/ 加入 sys.path，使测试无需安装即可跑（也保证 CI 与本地同路径）。"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
