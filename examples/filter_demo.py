# -*- coding: utf-8 -*-
"""示例:过滤器图元 —— 矩形 + 菱形网格,左右接管。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, parts, use_font

use_font()

d = Diagram(width=640, height=480)
d.add(parts.filter, "过滤器", loc=(320, 260))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "filter_demo.png")
d.save(out)
print("已生成:", out)
