# -*- coding: utf-8 -*-
"""示例:热泵(制热模式)循环 —— 压缩机-油分-四通阀-冷凝器-膨胀阀-蒸发器-气液分离器。

流程(状态点 1~6):
  压缩机排气(2) → 油分离器(分离油滴,底部回油) → 四通阀 D
  → C → 冷凝器(3→4) → 膨胀阀 → 蒸发器(5) → 四通阀 E
  → S → 气液分离器(U 形管液封,防液击) → 压缩机吸气(1)。
四通阀口别字母手工标注在接管侧(部件自动标注会压在管上);
部件全部来自 cycleplot.parts,压缩机吸气口经 make_partial 挪到顶部。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, make_partial, use_font
from cycleplot.parts import (bowtie_valve_dome, four_way_round,
                             make_heat_exchanger, make_scroll_chord,
                             oil_separator, separator_utube)

use_font()

d = Diagram(width=1240, height=880)

# ===================== 部件 =====================
# 压缩机:涡旋式,吸气口挪到顶部(自上方接管,让开左侧气液分离器的出管)
comp = d.add(make_partial(make_scroll_chord(), {"suction": (0, -85)}),
             "压缩机", loc=(300, 640), label_offset=(0, 118))
oil = d.add(oil_separator, "油分离器", loc=(1020, 200))
fw = d.add(four_way_round, "", loc=(420, 240), mark=False)  # 口别字母手标
cond = d.add(make_heat_exchanger(200, 90, shape="rect_zigzag7"),
             "冷凝器", loc=(760, 240))
tev = d.add(bowtie_valve_dome, "膨胀阀", loc=(860, 480))
evap = d.add(make_heat_exchanger(200, 90, shape="rect_zigzag7"),
             "蒸发器", loc=(620, 600))
sep = d.add(separator_utube, "气液分离器", loc=(160, 400))

d.text(464, 330, "四通阀", ha="left", size=17)
for s, x, y in (("D", 444, 188), ("C", 476, 222), ("E", 444, 294),
                ("S", 364, 220)):
    d.text(x, y, s, size=14)
d.text(60, 40, "制热模式：D→C，E→S", ha="left", size=15)

# ===================== 管路 =====================
# 排气:压缩机 → 绕行右侧 → 自上方进油分顶部
d.pipe(comp["discharge"], oil["top"],
       via=[(460, 640), (460, 700), (1160, 700), (1160, 80), (1020, 80)],
       head_at=(0.1, 0.7, 0.97))
# 油分干气出口 → 四通阀 D(顶部进)
d.pipe(oil["left"], fw["exhaust"], via=[(420, 156)], head_at=(0.5,))
# 四通阀 C → 冷凝器
d.pipe(fw["condenser"], cond["left"], head_at=(0.5,))
# 冷凝器 → 膨胀阀(东口进)
d.pipe(cond["right"], tev["in"], via=[(940, 240)], head_at=(0.6,))
# 膨胀阀 → 蒸发器
d.pipe(tev["out"], evap["right"], via=[(790, 480)], head_at=(0.55,))
# 蒸发器 → 四通阀 E(底部进)
d.pipe(evap["left"], fw["evaporator"], via=[(420, 600)], head_at=(0.5,))
# 四通阀 S → 气液分离器进气
d.pipe(fw["suction"], sep["in"], via=[(116, 240)], head_at=(0.4,))
# 气液分离器出气 → 压缩机吸气(顶部)
d.pipe(sep["out"], comp["suction"], via=[(300, 325)], head_at=(0.65,))
# 油分回油口(接压缩机曲轴箱,图中以短管示意)
d.pipe(oil["bottom"], (1020, 364), head_at=(0.85,))
d.text(1042, 352, "回油", ha="left", size=15)

# ===================== 状态点 =====================
for s, x, y in (("1", 275, 500), ("2", 415, 618), ("3", 610, 218),
                ("4", 918, 372), ("5", 766, 540), ("6", 443, 545)):
    d.text(x, y, s, size=22)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "heat_pump_cycle.png")
d.save(out)
print("已生成:", out)