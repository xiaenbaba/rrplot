# -*- coding: utf-8 -*-
"""示例:低压罐图元 —— 展示顶平底圆立式低压罐的形貌与端口。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, parts, use_font

use_font()

d = Diagram(width=760, height=560)

a = d.add(parts.low_pressure_tank, "低压罐(默认)", loc=(160, 280))
b = d.add(parts.make_low_pressure_tank(90, 220, liquid=0.5),
          "低压罐(放大/液位0.5)", loc=(470, 280))

# 端口核对标注
for node, tag in ((a, "a"), (b, "b")):
    d.text(*node["top"].point, "top", size=12)
    d.text(*node["bottom"].point, "bottom", size=12)
    d.text(*node["vapor"].point, "vapor", size=12)
    d.text(*node["left"].point, "left", size=12)
    d.text(*node["right"].point, "right", size=12)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "low_pressure_tank_demo.png")
d.save(out)
print("已生成:", out)
