# -*- coding: utf-8 -*-
"""示例:换热器 3 种换热面形态对照(对照 references/pfd_symbol_palette.py)。

由 references/pfd_symbols.heat_exchanger 移植为 make_heat_exchanger。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts, use_font

use_font()

COLS = (130 + 280 * i for i in range(3))

ITEMS = [
    ("rect_diag", "矩形 + 对角线"),
    ("rect_x", "矩形 + 对角线交叉"),
    ("rect_zigzag7", "矩形 + 7点之字"),
]

d = Diagram(width=980, height=320)

for cx, (shape, tag) in zip(COLS, ITEMS):
    d.add(parts.make_heat_exchanger(120, 120, shape=shape, name=tag),
          tag, loc=(cx, 150))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "heat_exchanger_shapes.png")
d.save(out)
print("已生成:", out)
