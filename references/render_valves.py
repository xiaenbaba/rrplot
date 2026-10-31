# -*- coding: utf-8 -*-
"""渲染制冷循环侧全部 9 种阀体图元"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts, use_font

use_font()

d = Diagram(width=1450, height=300)

valves = [
    (parts.valve, "通用蝶形阀"),
    (parts.expansion_valve, "电子膨胀阀"),
    (parts.four_way_valve, "四通阀(方体)"),
    (parts.four_way_round, "四通阀(圆菱形)"),
    (parts.globe_valve, "截止阀"),
    (parts.solenoid_valve, "电磁阀"),
    (parts.bowtie_valve, "对顶三角阀(裸)"),
    (parts.bowtie_valve_dome, "膨胀阀(穹顶)"),
    (parts.bowtie_valve_solenoid, "电磁阀(对顶三角)"),
]

for i, (part, name) in enumerate(valves):
    x = 80 + i * 150
    y = 120
    d.add(part, None, loc=(x, y))
    d.text(x, y + 90, name, size=14, ha="center")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "valves_refrigeration.png")
d.save(out)
print("已生成:", out)