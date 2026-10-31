# -*- coding: utf-8 -*-
"""EVI 涡旋压缩热泵 —— 经济器补气循环原理图(制热模式)。

主线:涡旋压缩机(带喷气增焓口) -> 冷凝器 -> 主路 EEV1 -> 经济器
      -> EEV2 -> 蒸发器 -> 回压缩机吸气;
支路:冷凝器出液经 EEV1 节流入经济器闪蒸,中压气体自经济器右侧引出、
      自压缩机顶部补气口(vapor_inj)补入,实现中间补气、提升低温制热量与能效。

用 rrplot 库组装:部件只需声明 loc,管路用「端口 + 走点」描述,
拐角正交化、状态点/温压测点标注由库自动编译。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, make_partial, parts, use_font

use_font()

d = Diagram(width=860, height=540)

# 涡旋压缩机:工厂默认端口是 left/right/top/bottom,补气口从底部(0,95)
# 改到顶部(0,-95)并起用循环图惯用口名,使补气管自上方接入、与吸气管错开。
comp_part = make_partial(
    parts.make_compressor(style="scroll", name="涡旋压缩机"),
    {"suction": (-95, 0), "discharge": (95, 0), "vapor_inj": (0, -95)})
comp = d.add(comp_part, "涡旋压缩机", loc=(720, 250),
             label_offset=(92, 52), label_ha="left")
cond = d.add(parts.make_heat_exchanger(240, 64, shape="rect_zigzag7"),
             "冷凝器(室内侧)", loc=(430, 60))
eev1 = d.add(parts.valve, loc=(150, 110))
econ = d.add(parts.make_economizer(w=32, h=130, style="plate", n_plates=10),
             "经济器", loc=(150, 240))
eev2 = d.add(parts.valve, loc=(150, 360))
evap = d.add(parts.make_heat_exchanger(190, 60, shape="rect_zigzag7"),
             "蒸发器(室外侧)", loc=(430, 440))

# EEV 文字标注(阀部件本身不带标签)
d.text(196, 110, "EEV$_1$", size=18, ha="left")
d.text(196, 360, "EEV$_2$", size=18, ha="left")

# ---------- 管路 ----------
# 1. 压缩机排气 -> 冷凝器
d.pipe(comp["discharge"], cond["right"], via=[(815, 60)],
       states=[("2", 0.55)], head_at=(0.6,))
# 2. 冷凝器出液 -> 左行 -> 经济器左侧(主路进液)
d.pipe(cond["left"], econ["left"], via=[(60, 60), (60, 240)],
       states=[("3", 0.25)], head_at=(0.4,))
# 3. 支路取液 -> EEV1 -> 经济器顶部
d.pipe((150, 60), eev1["top"], head=False)
d.pipe(eev1["bottom"], econ["top"], states=[("3'", 0.5)])
# 4. 经济器底部 -> EEV2 -> 蒸发器
d.pipe(econ["bottom"], eev2["top"], head=False, states=[("4", 0.5)])
d.pipe(eev2["bottom"], evap["left"], via=[(150, 440)],
       states=[("5", 0.5)], head_at=(0.55,))
# 5. 蒸发器 -> 压缩机吸气(自下方竖直接入左侧吸气口)
d.pipe(evap["right"], comp["suction"], via=[(625, 440)],
       states=[("1", 0.2)], head_at=(0.5,))
# 6. 经济器补气出口 -> 压缩机顶部喷气口(自上方绕入)
d.pipe(econ["right"], comp["vapor_inj"], via=[(170, 150), (720, 150)],
       states=[("6", 0.5)], head_at=(0.6,))

# 温压测点(绝对坐标,白底圆圈)
d.sensor(792, 148, r"$T_2$")
d.sensor(592, 330, r"$T_1$")
d.sensor(45, 110, r"$T_3$")
d.sensor(150, 478, r"$T_5$")
d.sensor(300, 200, r"$T_6$")

# 标题
d.text(20, 20, "EVI 喷气增焓热泵 · 经济器补气循环", size=20, ha="left")

# ---------- 出图(render 一次,分别存位图与矢量) ----------
here = os.path.dirname(os.path.abspath(__file__))
out_png = os.path.join(here, "evi_cycle.png")
out_svg = os.path.join(here, "evi_cycle.svg")
d.render()
d.fig.savefig(out_png, dpi=100, bbox_inches="tight", pad_inches=0.05)
d.fig.savefig(out_svg, bbox_inches="tight", pad_inches=0.05)
print("已生成:", out_png)
print("已生成:", out_svg)
