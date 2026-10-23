# -*- coding: utf-8 -*-
"""示例:热泵(制热模式)循环 —— 压缩机-油分-四通阀-冷凝器-膨胀阀-蒸发器-气液分离器。

流程(状态点 1~6):
  压缩机排气(2) → 油分离器(分离油滴,回油引至吸气管) → 四通阀 D
  → C → 冷凝器(3→4) → 膨胀阀 → 蒸发器(5) → 四通阀 E
  → S → 气液分离器(U 形管液封,防液击) → 压缩机吸气(1)。
四通阀口别字母手工标注在接管侧(部件自动标注会压在管上);
部件全部来自 cycleplot.parts,压缩机为圆形符号(顶部吸气/底部排气)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import Circle

from cycleplot import Diagram, use_font
from cycleplot.parts import (
    bowtie_valve_dome,
    compressor,
    four_way_round,
    make_heat_exchanger,
    oil_separator,
    separator_utube,
)

use_font()

d = Diagram(width=1240, height=880)

# ===================== 部件 =====================
# 压缩机:圆形符号(顶部吸气、底部排气,排气自下方绕行右侧进油分)
comp = d.add(compressor, "压缩机", loc=(300, 640), label_offset=(140, 0))
oil = d.add(oil_separator, "油分离器", loc=(1020, 200))
fw = d.add(four_way_round, "", loc=(420, 240), mark=False)  # 口别字母手标
cond = d.add(make_heat_exchanger(200, 90, shape="rect_x"),
             "冷凝器", loc=(760, 240))
tev = d.add(bowtie_valve_dome, "膨胀阀", loc=(860, 480))
evap = d.add(make_heat_exchanger(200, 90, shape="rect_x"),
             "蒸发器", loc=(620, 600))
sep = d.add(separator_utube, "气液分离器", loc=(160, 400))

d.text(464, 330, "四通阀", ha="left", size=17)
for s, x, y in (("D", 444, 188), ("C", 476, 222), ("E", 444, 294),
                ("S", 364, 220)):
    d.text(x, y, s, size=14)
d.text(60, 40, "制热模式：D→C，E→S", ha="left", size=15)

# ===================== 管路 =====================
# 排气:压缩机底部出 → 底部绕行右侧 → 上行进油分顶部
d.pipe(comp["discharge"], oil["top"],
       via=[(300, 782), (1160, 782), (1160, 80), (1020, 80)],
       head_at=(0.06, 0.72, 0.97))
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
# 油分回油 → 引至回气管(气液分离器→压缩机吸气段),T 型三通接入;
# 出油分先下行,左折回贴油分左侧窄缝(x=980,恰在 D 管端口外)上行,
# 高位左行横穿全场后,于回气管上方垂直下落接入,全程不穿任何部件
d.pipe(oil["bottom"], (246, 325),
       via=[(1020, 352), (980, 352), (980, 120), (246, 120)],
       head_at=(0.85,))
d.text(640, 104, "回油(至吸气管)", ha="center", size=15)
d.ax.add_patch(Circle((246, 325), 3.5, facecolor="#222222",
                      edgecolor="none", zorder=6))

# ===================== 状态点 =====================
for s, x, y in (("1", 318, 470), ("2", 340, 766), ("3", 610, 218),
                ("4", 918, 372), ("5", 766, 540), ("6", 443, 545)):
    d.text(x, y, s, size=22)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "heat_pump_cycle.png")
d.save(out)
print("已生成:", out)
