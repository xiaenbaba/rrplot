# -*- coding: utf-8 -*-
"""示例:涡旋压缩机 + 过冷器(经济器)补气循环 —— 用 cycleplot 库组装。

状态点:1 吸气 / 4 排气 / 5 分流点 / 6 过冷器主路出口 / 7 膨胀阀后
       8 膨胀器后补气 / 9 补气口回压缩机
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, make_partial, parts, use_font

use_font()

subcooler = make_partial(parts.make_rect(260, 110),
                         {"vapor_out": (-65, -55)}, dirs={"vapor_out": "n"})
subcooler.name = "过冷器"

d = Diagram(width=880, height=740)

# ---------- 部件 ----------
comp_part = make_partial(
    parts.make_compressor(style="scroll", name="涡旋压缩机"),
    {"suction": (-95, 0), "discharge": (95, 0), "vapor_inj": (0, 95)})
comp = d.add(comp_part, "涡旋压缩机", loc=(310, 110),
             label_offset=(92, 52), label_ha="left")
evap = d.add(parts.evaporator, loc=(102, 305), label="")
cond = d.add(parts.make_heat_exchanger(205, 86, shape="rect_zigzag7"),
             "冷凝器", loc=(607, 95))
sc = d.add(subcooler, loc=(570, 505))
d.add(parts.square_wave, loc=(458, 505))
valve_eev = d.add(parts.valve, loc=(288, 505))
valve_sol = d.add(parts.valve, loc=(505, 375))
valve_exp = d.add(parts.valve, loc=(672, 660))

# ---------- 手工标注文字 ----------
d.text(655, 428, "过冷器")
d.text(102, 305, "蒸\n发\n器")
d.text(288, 556, "膨胀阀")
d.text(560, 372, "电磁阀", ha="left")
d.text(700, 585, "膨胀器")

# ---------- 管路 ----------
# 蒸发器 -> 压缩机吸气 (点1)
d.pipe(evap["out"], comp["suction"], via=[(102, 110)], states=[("1", 0.55)])
# 压缩机排气 -> 冷凝器 (点4)
d.pipe(comp["discharge"], cond["left"], via=[(505, 100)],
       states=[("4", 0.35)])
# 冷凝器出口 -> 右侧下行总管
d.pipe(cond["right"], (790, 660), via=[("e", 790)], head_at=(0.3, 0.9))
# 点5:总管 -> 过冷器主路进口
d.pipe((790, 505), sc["right"], states=[("5", 0.5)])
# 过冷器主路出口 -> 膨胀阀 (点6) -> 蒸发器 (点7)
d.pipe(sc["left"], valve_eev["right"], states=[("6", 0.5)])
d.pipe(valve_eev["left"], evap["in"], via=[(102, 505)],
       states=[("7", 0.28)])
# 点8:总管 -> 膨胀器 -> 过冷器底部(补气支路)
d.pipe((790, 660), valve_exp["right"], states=[("8", 0.5)])
d.pipe(valve_exp["left"], (560, 560), via=[(560, 660)])
# 点9:过冷器补气出口 -> 电磁阀 -> 压缩机补气口
d.pipe(sc["vapor_out"], valve_sol["bottom"])
d.pipe(valve_sol["left"], comp["vapor_inj"], via=[(310, 375)],
       states=[("9", 0.82)])

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "superheat_cycle.png")
d.save(out)
print("已生成:", out)
