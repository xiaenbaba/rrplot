# -*- coding: utf-8 -*-
"""渲染制冷循环侧全部 6 种阀体图元"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts, use_font

use_font()

d = Diagram(width=1000, height=300)

valves = [
    (parts.four_way_round, "四通阀(圆菱形)"),
    (parts.globe_valve, "截止阀"),
    (parts.solenoid_valve, "电磁阀"),
    (parts.expansion_valve_eng, "电子膨胀阀(工程画法)"),
    (parts.expansion_valve_x, "膨胀阀(圆X)"),
    (parts.check_valve, "单向阀"),
]

for i, (part, name) in enumerate(valves):
    x = 80 + i * 150
    y = 120
    d.add(part, None, loc=(x, y))
    d.text(x, y + 90, name, size=14, ha="center")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "valves_refrigeration.png")
d.save(out)
print("已生成:", out)
