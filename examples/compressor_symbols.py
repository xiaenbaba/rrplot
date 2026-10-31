# -*- coding: utf-8 -*-
"""示例:压缩机 6 种型式符号对照(标准 PFD 画法)。

对照 references/compressor_symbols.py,符号已移植进 rrplot.parts。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts, use_font

use_font()

R = 80
COLS = (150, 450, 750)
ROWS = (150, 420)

ITEMS = [
    (COLS[0], ROWS[0], "centrifugal", "离心式"),
    (COLS[1], ROWS[0], "rotor", "通用旋转式"),
    (COLS[2], ROWS[0], "axial", "轴流式"),
    (COLS[0], ROWS[1], "recip", "往复式"),
    (COLS[1], ROWS[1], "screw", "螺杆式"),
    (COLS[2], ROWS[1], "scroll", "涡旋式"),
]

d = Diagram(width=900, height=620)

for cx, cy, style, tag in ITEMS:
    d.add(parts.make_compressor(R, style=style), tag, loc=(cx, cy))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "compressor_symbols.png")
d.save(out)
print("已生成:", out)
