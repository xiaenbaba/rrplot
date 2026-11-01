# -*- coding: utf-8 -*-
"""示例:压缩机两种机身对照 —— 圆形(圆体 + 双弦)与方形(胶囊壳体)。

对照 references/compressor_symbols.py,符号已移植进 rrplot.parts。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts, use_font

use_font()

R = 80
ITEMS = [
    (150, 180, "圆形", None),
    (450, 180, "方形", "压缩机"),
]

d = Diagram(width=600, height=360)

for cx, cy, style, label in ITEMS:
    d.add(parts.make_compressor(R, style=style), label, loc=(cx, cy))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "compressor_symbols.png")
d.save(out)
print("已生成:", out)
