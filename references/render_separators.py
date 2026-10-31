# -*- coding: utf-8 -*-
"""渲染气液分离器 / 油分离器对比图"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts, use_font

use_font()

d = Diagram(width=600, height=360)

d.add(parts.separator, "气液分离器", loc=(150, 180))
d.add(parts.oil_separator, "油分离器", loc=(400, 180))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "separators.png")
d.save(out)
print("已生成:", out)