# -*- coding: utf-8 -*-
"""示例:四通阀(圆菱形)温控回路演示。

压缩机 → 四通阀 D(排气) → C(冷凝器) → 毛细管 → 蒸发器 → 四通阀 E,
压缩机回气接四通阀 S,构成完整制冷回路。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts
from rrplot.parts import make_heat_exchanger

d = Diagram(width=960, height=760, default_step=80)
comp = d.add(parts.compressor, loc=(450, 140))
valve = d.add(parts.four_way_round, loc=(450, 380))
cond = d.add(make_heat_exchanger(120, 160, shape="rect_zigzag7"),
             loc=(660, 380))
cap = d.add(parts.capillary, label="毛细管", loc=(790, 540))
evap = d.add(make_heat_exchanger(120, 160, shape="rect_zigzag7"),
             loc=(450, 640))

d.pipe(comp["discharge"], valve["exhaust"])
d.pipe(valve["condenser"], cond["left"])
d.pipe(cond["bottom"], cap["in"], via=[("s", 500), ("e", 790)])
d.pipe(cap["out"], evap["top"], via=[("n", 520), ("w", 450)])
d.pipe(evap["left"], valve["evaporator"], via=[("w", 330), ("n", 420),
                                               ("e", 450)])
d.pipe(valve["suction"], comp["suction"], via=[("w", 330), ("n", 45)])

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "four_way_round_demo.png")
d.save(out)
print("已生成:", out)
