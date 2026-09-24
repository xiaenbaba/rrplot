# -*- coding: utf-8 -*-
"""示例:带经济器(EEV1/EEV2 两级节流)的制冷循环 —— 用 cycleplot 库组装。

回路:压缩机排气 -> 冷凝器 -> 分流
        主路: EEV1 -> 经济器 -> EEV2 -> 蒸发器 -> 压缩机吸气
        支路: 冷凝器出液 -> 经济器另一侧吸热 -> 经济器补气出口 -> 压缩机补气口
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, make_partial, parts, use_font

use_font()

comp_part = make_partial(parts.make_compressor(80, style="centrifugal"),
                         {"discharge": (0, -80), "suction": (0, 80),
                          "vapor_inj": (-80, 0)})

d = Diagram(width=780, height=520)

comp = d.add(comp_part, loc=(700, 245), label="")
cond = d.add(parts.make_heat_exchanger(240, 62, shape="rect_zigzag7"),
             "冷凝器", loc=(430, 40))
eev1 = d.add(parts.valve, loc=(150, 95))
econ = d.add(parts.economizer, "经济器", loc=(150, 230))
eev2 = d.add(parts.valve, loc=(150, 340))
evap = d.add(parts.make_heat_exchanger(190, 60, shape="rect_zigzag7"),
             "蒸发器", loc=(440, 425))

d.text(600, 262, "压缩机", size=20, ha="right", bg=True)
d.text(190, 95, "EEV$_1$", size=20, ha="left")
d.text(190, 340, "EEV$_2$", size=20, ha="left")

# ---------- 管路 ----------
# 压缩机排气 -> 冷凝器
d.pipe(comp["discharge"], cond["right"], via=[(700, 40)], head_at=(0.6,))
# 冷凝器出液 -> 左行 -> 经济器左侧(主路进液)
d.pipe(cond["left"], econ["left"], via=[(40, 40), (40, 230)])
# 支路:主液管 -> EEV1 -> 经济器顶部
d.pipe((150, 40), eev1["top"], head=False)
d.pipe(eev1["bottom"], econ["top"])
# 经济器底部 -> EEV2 -> 蒸发器
d.pipe(econ["bottom"], eev2["top"], head=False)
d.pipe(eev2["bottom"], evap["left"], via=[(150, 425)])
# 蒸发器 -> 压缩机吸气
d.pipe(evap["right"], comp["suction"], via=[(700, 425)])
# 经济器补气出口 -> 压缩机补气口
d.pipe(econ["right"], comp["vapor_inj"], via=[(620, 230)])

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "economizer_cycle.png")
d.save(out)
print("已生成:", out)
