# -*- coding: utf-8 -*-
"""示例:FTVI 闪发罐喷气增焓系统图 —— 参考图复刻(黑白线稿)。

回路:压缩机排气 → 冷凝器 → 电子膨胀阀 → 闪发罐顶部进液(状态 6);
      闪发罐液相(底部,状态 4') → 电子膨胀阀 → 蒸发器(状态 5')
      → 压缩机吸气口(状态 1);
      闪发罐气相(上侧) → 压缩机补气口(状态 7)。
节流元件用圆X电子膨胀阀图元;随线箭头指示流向,
状态点 1/4'/5'/6/7/8/9 按参考图标注。坐标 1 单位 = 1 像素,y 向下。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, use_font
from rrplot.parts import (
    make_compressor,
    make_expansion_valve_x,
    make_heat_exchanger,
    make_vessel,
)

use_font()

d = Diagram(width=760, height=580)

# ===================== 部件 =====================
cond = d.add(make_heat_exchanger(200, 56, shape="rect_zigzag7",
                                 name="冷凝器"), None, loc=(330, 70))
evap = d.add(make_heat_exchanger(200, 56, shape="rect_zigzag7",
                                 name="蒸发器"), None, loc=(330, 490))
tank = d.add(make_vessel(w=66, h=130, liquid=0.42), None, loc=(110, 300))
comp = d.add(make_compressor(r=42, style="圆形"), None, loc=(600, 272))
xv1 = d.add(make_expansion_valve_x(orient="v"), None, loc=(110, 165))
xv2 = d.add(make_expansion_valve_x(orient="v"), None, loc=(110, 425))

# ===================== 标题与状态点 =====================
d.text(330, 28, "冷凝器", size=15)
d.text(330, 450, "蒸发器", size=15)
d.text(155, 296, "闪蒸器", size=15, ha="left")
d.text(126, 165, "节流阀", size=14, ha="left")
d.text(126, 425, "节流阀", size=14, ha="left")
d.text(128, 208, "6", size=13, ha="left")
d.text(124, 390, "4′", size=13, ha="left")
d.text(128, 462, "5′", size=13, ha="left")
d.text(614, 420, "1", size=13, ha="left")
d.text(612, 220, "8", size=13, ha="left")
d.text(636, 308, "9", size=13, ha="left")
d.text(540, 298, "7", size=13, ha="right")

# ===================== 管路 =====================
# 排气:压缩机顶部 → 冷凝器右口(状态 2)
d.pipe(comp["top"], cond["right"], via=[(600, 70)], head_at=(0.3, 0.7))
# 冷凝器左口 → 电子膨胀阀 → 闪发罐顶部进液(状态 6)
d.pipe(cond["left"], xv1["in"], via=[(110, 70)])
d.pipe(xv1["out"], tank["top"])
# 液相:闪发罐底部 → 电子膨胀阀 → 蒸发器左口(状态 4' → 5')
d.pipe(tank["bottom"], xv2["in"])
d.pipe(xv2["out"], evap["left"], via=[(110, 490)])
# 吸气:蒸发器右口 → 压缩机底部吸气口(状态 1)
d.pipe(evap["right"], comp["bottom"], via=[(600, 490)], head_at=(0.3, 0.7))
# 补气:闪发罐气相出口 → 压缩机左侧补气口(状态 7)
d.pipe(tank["vapor"], comp["left"])

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "ftvi_cycle.png")
d.save(out, out.replace(".png", ".svg"))
print("已生成:", out)
