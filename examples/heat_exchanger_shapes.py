# -*- coding: utf-8 -*-
"""示例:换热器 5 种标准 PFD 形态对照(对照 references/pfd_symbol_palette.py)。

由 references/pfd_symbols.heat_exchanger 移植为 make_heat_exchanger。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, parts, use_font

use_font()

COLS = (130, 410, 690, 970, 1250)

ITEMS = [
    (COLS[0], "circle", "圆 + 之字盘管"),
    (COLS[1], "rect", "矩形 + 之字盘管"),
    (COLS[2], "rect_zigzag", "矩形 + 蛇形盘管"),
    (COLS[3], "rect_zigzag7", "矩形 + 7点之字"),
    (COLS[4], "rect_diag", "矩形 + 对角线"),
]

d = Diagram(width=1400, height=320)

for cx, shape, tag in ITEMS:
    d.add(parts.make_heat_exchanger(120, 120, shape=shape, name=tag),
          tag, loc=(cx, 150))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "heat_exchanger_shapes.png")
d.save(out)
print("已生成:", out)
