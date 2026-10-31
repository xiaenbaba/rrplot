# -*- coding: utf-8 -*-
"""示例:最简单级制冷循环 —— 布局与 economizer_cycle 相同的论文风格。

冷凝器/蒸发器用 7 点之字盘管且同尺寸,节流元件用毛细管图元。
状态点:1 压缩机吸气 / 2 压缩机排气 / 3 冷凝器出口 / 4 蒸发器出口
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, make_partial, parts, use_font

use_font()

comp_part = make_partial(parts.make_compressor(80, style="centrifugal"),
                         {"discharge": (0, -80), "suction": (0, 80)})

d = Diagram(width=780, height=500)

comp = d.add(comp_part, loc=(640, 245), label="")
cond = d.add(parts.make_heat_exchanger(240, 62, shape="rect_zigzag7"),
             "冷凝器", loc=(360, 40))
cap = d.add(parts.capillary, "毛细管", loc=(90, 250))
evap = d.add(parts.make_heat_exchanger(240, 62, shape="rect_zigzag7"),
             "蒸发器", loc=(360, 425))

d.text(530, 262, "压缩机", size=20, ha="right", boxed=True)

# ---------- 管路 ----------
# 压缩机排气 -> 上行 -> 左行 -> 冷凝器
d.pipe(comp["discharge"], cond["right"], via=[(640, 40)], head_at=(0.6,),
       states=[("2", 0.35)])
# 冷凝器出液 -> 左行 -> 下行 -> 毛细管
d.pipe(cond["left"], cap["in"], via=[(90, 40)], states=[("3", 0.3, 1)])
# 毛细管 -> 下行 -> 右行 -> 蒸发器
d.pipe(cap["out"], evap["left"], via=[(90, 425)], states=[("4", 0.3, 1)])
# 蒸发器 -> 右行 -> 上行 -> 压缩机吸气
d.pipe(evap["right"], comp["suction"], via=[(640, 425)],
       head_at=(0.8,), states=[("1", 0.35, -1)])

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "simple_cycle.png")
d.save(out)
print("已生成:", out)
