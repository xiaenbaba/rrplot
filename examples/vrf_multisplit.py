# -*- coding: utf-8 -*-
"""示例:多联机(VRF)系统图 —— 复刻参考图布局(黑白线稿)。

按用户要求:不画墙体,不加编号标注。布局对照参考重绘图:
室外机:压缩机排气上行进油分离器侧口(左上),顶部出四通阀 D 口,
       底部回油经毛细管接回吸气管;
       四通阀 C 口西行 → 室外换热器(矩形 + X 交叉线)
       → 底部膨胀阀 → 液管总管 → 中间换热器主路 → 液管检修阀出机;
       喷气支路(经济器副路):主路出换热器后三通引出 → 电子膨胀阀节流
       → 中间换热器副路进口(右侧,与主路出口同侧),闪发气自副路
       出口(左侧,与主路进口同侧)引出 → 西折上行进压缩机增焓入口;
       回油:油分底部经毛细管三通接入吸气管;
       四通阀 S 口东行下行 → 气液分离器(U 形管)→ 西行回压缩机回气口(底部);
       四通阀 E 口走高线绕至右侧气管总管 → 气管检修阀 → 出机。
       充注口(带压力表)接在气液分离器入口支路上。
室内机:气管总管立管 ↓ 室内换热器 1…n(矩形 + X 交叉线)
       → 底部膨胀阀 → 液管总管汇合出机。
管路交叉不画接点,T 型三通用黑圆点标记;坐标 1 单位 = 1 像素,y 向下。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import Circle, Rectangle

from rrplot import Diagram, use_font
from rrplot.parts import (
    make_compressor,
    make_expansion_valve_x,
    make_four_way_round,
    make_globe_valve,
    make_heat_exchanger,
    make_oil_separator,
    make_partial,
    make_separator_utube,
)
from rrplot.style import LW_PIPE

use_font()

INK = "#000000"

d = Diagram(width=1440, height=800)


def dot(x, y, r=3.5):
    """T 型三通接点。"""
    d.ax.add_patch(Circle((x, y), r, facecolor=INK, edgecolor="none",
                          zorder=6))


# ===================== 机壳与标题 =====================
for bx, by, bw, bh in ((30, 75, 900, 685), (995, 75, 405, 685)):
    d.ax.add_patch(Rectangle((bx, by), bw, bh, fill=False, edgecolor=INK,
                             lw=1.5, linestyle=(0, (6, 5)), zorder=0.5))
d.text(480, 45, "室外机", size=17, weight="bold")
d.text(1197, 45, "室内机", size=17, weight="bold")

# ===================== 部件 =====================
# 四通阀:圆体 + 内菱形;按参考图取向 D 口朝下、S 口朝东
fw = d.add(make_partial(
    make_four_way_round(r=30, mark=False, name="四通阀"),
    ports={"exhaust": (0, 30), "evaporator": (0, -30),
           "condenser": (-30, 0), "suction": (30, 0)},
    dirs={"exhaust": "s", "evaporator": "n", "condenser": "w",
          "suction": "e"}), None, loc=(525, 190))
oil = d.add(make_oil_separator(w=30, h=60, stub=8), None, loc=(525, 307))
comp = d.add(make_compressor(r=60, style="centrifugal", name="压缩机"),
             None, loc=(410, 405))
acc = d.add(make_separator_utube(w=90, h=90, stub=12, flip=True), None,
            loc=(738, 546))
gas_stop = d.add(make_globe_valve(w=27, h=20, stem=10, handle=18), None,
                 loc=(820, 200))
liq_stop = d.add(make_globe_valve(w=27, h=20, stem=10, handle=18), None,
                 loc=(820, 712))
coil_out = d.add(make_heat_exchanger(w=90, h=210, shape="rect_x",
                                     name="室外换热器"), None, loc=(200, 420))
coil1 = d.add(make_heat_exchanger(w=58, h=195, shape="rect_x",
                                  name="室内换热器"), None, loc=(1049, 427.5))
coil2 = d.add(make_heat_exchanger(w=58, h=195, shape="rect_x",
                                  name="室内换热器"), None, loc=(1224, 427.5))
# 膨胀阀:圆 + 内接 X(端口式图元,无短管,管线分两段接圆周);
# 竖直管路用 orient="v"(in 顶口/out 底口)
xv_out = d.add(make_expansion_valve_x(orient="v"), None, loc=(200, 595))
xv_in1 = d.add(make_expansion_valve_x(orient="v"), None, loc=(1049, 600))
xv_in2 = d.add(make_expansion_valve_x(orient="v"), None, loc=(1224, 600))
# 喷气支路电子膨胀阀:水平管路流向东→西,in/out 对调(默认西→东)
xv_eev = d.add(make_partial(make_expansion_valve_x(orient="h"),
                            ports={"in": (10, 0), "out": (-10, 0)},
                            dirs={"in": "e", "out": "w"}), None,
               loc=(640, 668))
# 中间换热器:素面矩形串在液管总管上,主/副两路接口分列左右两边
d.ax.add_patch(Rectangle((390, 650), 190, 80, facecolor="white",
                         edgecolor=INK, lw=1.2))
d.text(485, 690, "中间换热器", size=13, boxed=True)

# 竖排器件名
d.text(200, 420, "室外换热器", size=14, rot=90, boxed=True)
d.text(1049, 427, "室内换热器1", size=13, rot=90, boxed=True)
d.text(1224, 427, "室内换热器n", size=13, rot=90, boxed=True)
d.text(1150, 427, "···", size=22)

# ===================== 文字标注 =====================
d.text(445, 152, "四通阀", size=15)
d.text(549, 298, "油分离器", ha="left", size=14)
d.text(487, 530, "压缩机", ha="left", size=15)
d.text(178, 595, "膨胀阀", ha="right", size=14)
d.text(640, 634, "电子膨胀阀", size=13)
d.text(738, 612, "气液分离器", size=14)
d.text(820, 158, "气管检修阀", size=14)
d.text(820, 740, "液管检修阀", size=14)
d.text(870, 434, "充注口", size=13)
d.text(1071, 600, "膨胀阀", ha="left", size=14)

# ===================== 室外机管路 =====================
# 排气:压缩机顶部上行 → 油分离器侧口(左上);油分顶部 → 四通阀 D 口
d.pipe(comp["top"], oil["left"], via=[(410, 292)], head=False)
d.pipe(oil["top"], fw["exhaust"], head=False)
# 回油:油分底部 → 毛细管(弹簧段)→ 三通接入吸气管
d.pipe(oil["bottom"], (525, 360), head=False)
d.ax.plot([525, 518, 532, 518, 532, 525], [360, 368, 376, 384, 392, 400],
          color=INK, lw=LW_PIPE, solid_capstyle="round",
          solid_joinstyle="round")
d.pipe((525, 400), (525, 489), head=False)
dot(525, 489)
# 四通阀 C 口西行 → 室外换热器顶部;底部经膨胀阀入液管总管,
# 主路沿中间换热器下侧水平穿过(主/副路接口关于中心对称)
d.pipe(fw["condenser"], coil_out["top"], via=[(200, 190)], head=False)
d.pipe(coil_out["bottom"], xv_out["in"], head=False)
d.pipe(xv_out["out"], (580, 712), head=False)
# 液管:中间换热器主路出口 → 液管检修阀 → 出机接室内机液管总管
d.pipe((580, 712), liq_stop["in"], head=False)
d.pipe(liq_stop["out"], (1224, 712), head=False)
dot(700, 712)
# 喷气支路(经济器副路):主路出换热器后三通引出,向上左折经电子膨胀阀
# 节流,水平穿过中间换热器副路(进口右侧、出口左侧,与主路同侧对齐),
# 出换热器后西折上行进压缩机增焓入口
d.pipe((700, 712), xv_eev["in"], head=False)
d.pipe(xv_eev["out"], comp["left"],
       via=[(340, 668), (340, 405)], head=False)
# 副路闪发气自左侧出口(与主路进口同侧)引出 → 西折上行
# → 压缩机增焓入口(左侧)
d.pipe((390, 668), comp["left"],
       via=[(340, 668), (340, 405)], head=False)
# 吸气:四通阀 S 口东行下行 → 气液分离器;U 形管出气西行 → 压缩机回气口(底部)
acc_in = acc["in"].point
d.pipe(fw["suction"], acc["in"],
       via=[(686, 190), (686, acc_in[1] - 49), (acc_in[0], acc_in[1] - 49)],
       head=False)
d.pipe(acc["out"], comp["bottom"], via=[(410, 489)], head=False)
# 气管:四通阀 E 口走高线绕至右侧,下行接气管总管
d.pipe(fw["evaporator"], (760, 200), via=[(525, 105), (760, 105)],
       head=False)
d.pipe((760, 200), gas_stop["in"], head=False)
d.pipe(gas_stop["out"], (1224, 200), head=False)

# ===================== 室内机管路 =====================
# 气管总管立管 ↓ 换热器顶部;换热器底部 → 膨胀阀 → 液管总管
# 首台立管与总管相交为 T 型三通;总管至末台(n)立管处截止,不画接点
for cx, xv in ((1049, xv_in1), (1224, xv_in2)):
    d.pipe((cx, 200), (cx, 330), head=False)
    d.pipe((cx, 525), xv["in"], head=False)
    d.pipe(xv["out"], (cx, 712), head=False)
dot(1049, 200)
dot(1049, 712)

# ===================== 检修附件 =====================
# 充注口:气液分离器入口支路三通 → 截止阀 → 压力表 → 加氟嘴
charge_valve = d.add(make_globe_valve(w=27, h=20, stem=10, handle=18),
                     None, loc=(820, 310))
d.pipe((686, 310), charge_valve["in"], head=False)
d.pipe(charge_valve["out"], (870, 310), head=False)
d.pipe((870, 310), (870, 332), head=False)
d.ax.add_patch(Circle((870, 345), 13, facecolor="white", edgecolor=INK,
                      lw=1.0, zorder=5))
d.text(870, 345, "P", size=12)
d.pipe((870, 358), (870, 410), head=False)
dot(686, 310)
# 压力表:排气管(油分/四通阀之间)一只
d.pipe((525, 244), (562, 244), head=False)
d.ax.add_patch(Circle((574, 244), 12, facecolor="white", edgecolor=INK,
                      lw=1.0, zorder=5))
d.text(574, 244, "P", size=12)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "vrf_multisplit.png")
d.save(out, out.replace(".png", ".svg"))
print("已生成:", out)
