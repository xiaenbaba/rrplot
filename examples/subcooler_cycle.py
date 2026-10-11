# -*- coding: utf-8 -*-
"""示例:涡旋压缩机 + 过冷器(经济器)补气增焓循环 —— 参考图复刻。

状态点编号(与参考图一致):
  1 压缩机吸气   2 吸气腔   3 排气腔   4 压缩机排气 -> 冷凝器
  5 冷凝器出口(分流点)-> 过冷器主路   6 过冷器主路出口 -> 膨胀阀
  7 膨胀阀出口 -> 蒸发器   8 膨胀器出口 -> 过冷器壳侧(补气支路)
  9 过冷器壳侧补气 -> 电磁阀 -> 压缩机补气口

部件:全部来自库内 —— 冷凝器/蒸发器用 make_rect,过冷器用
make_heat_exchanger(矩形壳 + 三角折波),对顶三角阀(穹顶/电磁线圈)
用 bowtie_valve_dome / bowtie_valve_solenoid,涡旋压缩机(圆 + 收敛
双弦)用 make_scroll_chord。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, use_font
from cycleplot.parts import (bowtie_valve_dome, bowtie_valve_solenoid,
                             make_heat_exchanger, make_rect,
                             make_scroll_chord)

use_font()

LW = 1.6          # 管线线宽(参考图为粗线风格)
HEAD = 20         # 随线箭头大小
NUM = 24          # 状态点编号字号


# =========================
# 组装
# =========================
d = Diagram(width=880, height=760)

comp = d.add(make_scroll_chord(), "涡旋压缩机", loc=(250, 110),
             label_offset=(103, 61.2), label_ha="left")
evap = d.add(make_rect(78, 195, name="蒸发器"), "蒸\n发\n器", loc=(110, 330))
cond = d.add(make_rect(210, 88, name="冷凝器"), "冷凝器", loc=(640, 110))
# 过冷器用库内换热器(矩形壳 + 三角折波盘管),端口四边中点
sub = d.add(make_heat_exchanger(245, 105, shape="rect_zigzag7",
                                name="过冷器"), "", loc=(600, 520))

tev1 = d.add(bowtie_valve_dome, "膨胀阀", loc=(300, 520))
sol = d.add(bowtie_valve_solenoid, "", loc=(380, 388))
tev2 = d.add(bowtie_valve_dome, "", loc=(660, 668))

d.text(690, 448, "过冷器", size=18)
d.text(428, 356, "电磁阀", ha="left", size=17)   # 让开东侧进管,放管线上方
d.text(706, 612, "膨胀器", ha="left", size=17)

# =========================
# 管路(箭头位置用弧长比例 head_at 标)
# =========================
# 蒸发器 -> 压缩机吸气(1)
d.pipe(evap["top"], comp["suction"], via=[(110, 110)],
       lw=LW, head_size=HEAD, head_at=(0.35,))
# 压缩机排气(4)-> 冷凝器
d.pipe(comp["discharge"], cond["left"], lw=LW, head_size=HEAD,
       head_at=(0.5,))
# 冷凝器 -> 右侧立管 -> 膨胀器(途中 5 分流去 过冷器)
d.pipe(cond["right"], tev2["in"], via=[(800, 110), (800, 668)],
       lw=LW, head_size=HEAD, head_at=(0.35, 0.76))
# 5:立管 -> 过冷器主路进口
d.pipe((800, 520), sub["right"], lw=LW, head_size=HEAD, head_at=(0.5,))
# 6:过冷器主路出口 -> 膨胀阀
d.pipe(sub["left"], tev1["in"], lw=LW, head=False)
# 7:膨胀阀 -> 蒸发器
d.pipe(tev1["out"], evap["bottom"], via=[(110, 520)],
       lw=LW, head_size=HEAD, head_at=(0.34,))
# 9:过冷器壳侧补气 -> 电磁阀
d.pipe(sub["top"], sol["in"], via=[(600, 388)], lw=LW, head=False)
# 9:电磁阀 -> 压缩机补气口
d.pipe(sol["out"], comp["inj"], via=[(243, 388)],
       lw=LW, head_size=HEAD, head_at=(0.81,))
# 8:膨胀器 -> 过冷器壳侧底部
d.pipe(tev2["out"], sub["bottom"], via=[(600, 668)], lw=LW, head=False)

# =========================
# 状态点编号
# =========================
for s, x, y in (("1", 146, 76), ("2", 190, 97), ("3", 314, 98),
                ("4", 349, 92), ("9", 266, 206),
                ("5", 772, 500), ("6", 455, 500), ("7", 236, 500),
                ("8", 578, 700)):
    d.text(x, y, s, size=NUM)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "subcooler_cycle.png")
d.save(out)
print("已生成:", out)
