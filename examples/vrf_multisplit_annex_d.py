# -*- coding: utf-8 -*-
"""示例:多联机(VRF)系统图 + 现场测试测点标注 —— 按 GB/T 27941—2026 附录 D
图 D.3(带中间喷射支路系统)/表 D.2 布置运行参数测点。

基础布局与 vrf_multisplit.py 完全一致(画布加高容纳标引序号说明),
标注层为 GB 标准风格:管线上的实心圆点 = 温度传感器,
细引线 + 下划线序号 = 标引序号;压力测点利用图中已有的压力表(P)标注;
电能表(圆 + 闪电)按标准画在机壳外左上/右上。

测点语义对照(表 D.2):
  1/1' 气液分离器进/出口温度   2 压缩机壳体中部温度(选测)
  3/3' 压缩机排气管/油分出口温度   4 室外环境空气温度
  5 室外换热器进(制热)出(制冷)口温度   6 室内机总管温度
  7 中间换热器节流侧入口温度   8 喷射支路制冷剂温度
  9 气液分离器进口压力(充注支路静压)   10 压缩机排气压力
  11 压缩机输入电功率   12/13 室外/室内机电能表
管路交叉不画接点,T 型三通用黑圆点标记;坐标 1 单位 = 1 像素,y 向下。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import Circle, Polygon, Rectangle

from rrplot import Diagram, use_font
from rrplot.parts import (
    make_compressor,
    make_expansion_valve_x,
    make_four_way_round,
    make_globe_valve,
    make_heat_exchanger,
    make_intermediate_hex,
    make_oil_separator,
    make_partial,
    make_separator_utube,
)
from rrplot.style import LW_PIPE

use_font()

INK = "#000000"

# 画布加高至 1130:上部 0~800 为系统图(与 vrf_multisplit 相同),下部放图例
d = Diagram(width=1440, height=1130)


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
fw = d.add(make_partial(
    make_four_way_round(r=30, mark=False, name="四通阀"),
    ports={"exhaust": (0, 30), "evaporator": (0, -30),
           "condenser": (-30, 0), "suction": (30, 0)},
    dirs={"exhaust": "s", "evaporator": "n", "condenser": "w",
          "suction": "e"}), None, loc=(525, 190))
oil = d.add(make_oil_separator(w=30, h=60, stub=8), None, loc=(525, 307))
comp = d.add(make_compressor(r=60, style="圆形", name="压缩机"),
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
xv_out = d.add(make_expansion_valve_x(orient="v"), None, loc=(200, 595))
xv_in1 = d.add(make_expansion_valve_x(orient="v"), None, loc=(1049, 600))
xv_in2 = d.add(make_expansion_valve_x(orient="v"), None, loc=(1224, 600))
xv_eev = d.add(make_partial(make_expansion_valve_x(orient="h"),
                            ports={"in": (10, 0), "out": (-10, 0)},
                            dirs={"in": "e", "out": "w"}), None,
               loc=(640, 668))
hx = d.add(make_intermediate_hex(w=190, h=80), "中间换热器",
           loc=(485, 690))

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
d.pipe(comp["top"], oil["left"], via=[(410, 292)], head=False)
d.pipe(oil["top"], fw["exhaust"], head=False)
d.pipe(oil["bottom"], (525, 360), head=False)
d.ax.plot([525, 518, 532, 518, 532, 525], [360, 368, 376, 384, 392, 400],
          color=INK, lw=LW_PIPE, solid_capstyle="round",
          solid_joinstyle="round")
d.pipe((525, 400), (525, 489), head=False)
dot(525, 489)
d.pipe(fw["condenser"], coil_out["top"], via=[(200, 190)], head=False)
d.pipe(coil_out["bottom"], hx["main_in"], head=False)
d.pipe(hx["main_out"], liq_stop["in"], head=False)
d.pipe(liq_stop["out"], (1224, 712), head=False)
dot(700, 712)
d.pipe((700, 712), xv_eev["in"], head=False)
d.pipe(xv_eev["out"], hx["sub_in"], head=False)
d.pipe(hx["sub_out"], comp["left"],
       via=[(340, 668), (340, 405)], head=False)
acc_in = acc["in"].point
d.pipe(fw["suction"], acc["in"],
       via=[(686, 190), (686, acc_in[1] - 49), (acc_in[0], acc_in[1] - 49)],
       head=False)
d.pipe(acc["out"], comp["bottom"], via=[(410, 489)], head=False)
d.pipe(fw["evaporator"], (760, 200), via=[(525, 105), (760, 105)],
       head=False)
d.pipe((760, 200), gas_stop["in"], head=False)
d.pipe(gas_stop["out"], (1224, 200), head=False)

# ===================== 室内机管路 =====================
for cx, xv in ((1049, xv_in1), (1224, xv_in2)):
    d.pipe((cx, 200), (cx, 330), head=False)
    d.pipe((cx, 525), xv["in"], head=False)
    d.pipe(xv["out"], (cx, 712), head=False)
dot(1049, 200)
dot(1049, 712)

# ===================== 检修附件 =====================
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
d.pipe((525, 244), (562, 244), head=False)
d.ax.add_patch(Circle((574, 244), 12, facecolor="white", edgecolor=INK,
                      lw=1.0, zorder=5))
d.text(574, 244, "P", size=12)


# ===================== 测点标注层(GB/T 27941—2026 附录 D) =====================
def sensor(x, y, r=4.5):
    """温度/压力测点:管线上的实心圆点。"""
    d.ax.add_patch(Circle((x, y), r, facecolor=INK, edgecolor="none",
                          zorder=8))


def leader(pts):
    """标引细引线。"""
    xs, ys = zip(*pts)
    d.ax.plot(xs, ys, color=INK, lw=0.9, zorder=7,
              solid_capstyle="round", solid_joinstyle="round")


def ref_num(x, y, s, ha="left", size=15):
    """标引序号:数字 + 下划线(GB 标准风格)。"""
    d.text(x, y, s, size=size, ha=ha)
    px = size * 100 / 72.0            # 字号 pt → px
    w = 0.62 * px * len(s)            # 数字文本宽粗估
    x0 = {"left": x, "right": x - w, "center": x - w / 2}[ha]
    uy = y + 0.46 * px + 2
    d.ax.plot([x0, x0 + w], [uy, uy], color=INK, lw=1.0, zorder=7)


def energy_meter(x, y, r=15):
    """电能表:圆 + 闪电符号(标准图 12/13 画法)。"""
    d.ax.add_patch(Circle((x, y), r, facecolor="white", edgecolor=INK,
                          lw=1.4, zorder=6))
    bolt = [(3, -9), (-6, 3), (-1, 3), (-3, 9), (6, -2), (1, -2)]
    d.ax.add_patch(Polygon([(x + dx, y + dy) for dx, dy in bolt],
                           closed=True, facecolor=INK, edgecolor=INK,
                           zorder=7))


# 12/13 电能表(机壳外左上/右上,标准图画法)
energy_meter(95, 45)
ref_num(118, 45, "12", ha="left")
energy_meter(1360, 45)
ref_num(1337, 45, "13", ha="right")

# 4 室外环境空气温度:开放空间中的感温点
sensor(140, 250)
leader([(140, 228), (140, 246)])
ref_num(140, 218, "4", ha="center")

# 3 压缩机排气管温度:排气竖管(压缩机顶 → 油分进口)
sensor(410, 320)
leader([(386, 304), (408, 317)])
ref_num(382, 300, "3", ha="right")

# 3' 油分离器出口温度:油分顶 → 四通阀 D 口竖管(排气压力表下方)
sensor(525, 256)
leader([(498, 240), (522, 254)])
ref_num(494, 236, "3'", ha="right")

# 2 压缩机壳体(或外保温)中部温度:壳体左上缘(选测)
sensor(368, 363)
leader([(336, 338), (364, 360)])
ref_num(332, 334, "2", ha="right")

# 10 压缩机排气压力:排气管上已有压力表
leader([(596, 231), (584, 236)])
ref_num(600, 227, "10", ha="left")

# 1 气液分离器制冷剂进口温度:进口竖管(充注三通下方)
sensor(686, 420)
leader([(692, 420), (712, 416)])
ref_num(716, 414, "1", ha="left")

# 1' 气液分离器制冷剂出口温度:出气 horizontal 管油分回油三通东侧
sensor(600, 489)
leader([(622, 493), (644, 506)])
ref_num(648, 510, "1'", ha="left")

# 9 气液分离器制冷剂进口压力:充注支路压力表(支路无流动,静压相同)
leader([(886, 342), (895, 340)])
ref_num(899, 338, "9", ha="left")

# 11 压缩机输入电功率:压缩机中心
d.ax.add_patch(Circle((410, 405), 2.5, facecolor=INK, edgecolor="none",
                      zorder=8))
leader([(366, 462), (406, 409)])
ref_num(360, 470, "11", ha="left")

# 8 喷射支路制冷剂温度:喷射竖管(中间换热器副路出口 → 压缩机补气口)
sensor(340, 560)
leader([(362, 576), (344, 566)])
ref_num(366, 584, "8", ha="left")

# 5 室外机换热器制冷剂出(制冷)口温度:底部液管水平段(膨胀阀下游)
sensor(330, 712)
leader([(304, 688), (326, 708)])
ref_num(300, 684, "5", ha="right")

# 7 中间换热器节流侧入口温度:电子膨胀阀出口 → 副路进口之间
sensor(605, 668)
leader([(622, 686), (608, 672)])
ref_num(630, 694, "7", ha="right")

# 6 室内机制冷剂进(制冷)出(制热)口总管温度:液管检修阀下游总管
sensor(890, 712)
leader([(902, 694), (892, 706)])
ref_num(906, 688, "6", ha="left")

# ===================== 标引序号说明(表 D.2) =====================
d.text(45, 800, "标引序号说明(现场测试测点 · GB/T 27941—2026 表 D.2):",
       size=14, ha="left", weight="bold")

LEG_L = [
    "1 ——气液分离器制冷剂进口温度 T1/℃ ±0.5(必测);",
    "1'——气液分离器制冷剂出口温度 T1'/℃ ±0.5(计气分漏热时代替 1);",
    "2 ——压缩机壳体(或外保温)中部温度 T2/℃ ±0.5(选测,壳体无保温时用 T3);",
    "3 ——压缩机排气管温度 T3/℃ ±0.5(必测);",
    "3'——油分离器出口温度 T3'/℃ ±0.5(计油分漏热时代替 3);",
    "4 ——室外环境空气温度 T4/℃ ±0.5(必测);",
    "5 ——室外机换热器制冷剂进(制热)出(制冷)口温度 T5/℃ ±0.5(必测);",
    "6 ——室内机制冷剂进(制冷)出(制热)口总管温度 T6/℃ ±0.5(必测)。",
]
LEG_R = [
    "7 ——中间换热器节流侧入口温度 T7/℃ ±0.5(必测);",
    "8 ——喷射支路制冷剂温度 T8/℃ ±0.5(必测);",
    "9 ——气液分离器制冷剂进口压力 psuc ±2.0%(必测,取充注支路静压);",
    "10——压缩机排气压力 pdis ±2.0%(必测);",
    "11——压缩机输入电功率 Wc/W ±3.0%(必测,含曲轴箱电加热);",
    "12——室外机电能表电能值 Bout,i/kW·h ±2.0%(必测);",
    "13——室内机电能表电能值 Bin,i/kW·h ±2.0%(选测,可用整机−室外差值)。",
]
for i, s in enumerate(LEG_L):
    d.text(45, 830 + i * 24, s, size=12, ha="left")
for i, s in enumerate(LEG_R):
    d.text(660, 830 + i * 24, s, size=12, ha="left")

d.text(45, 1014,
       "· 方法选择(D.4.1):吸气过热度 > 5 ℃ 且等熵压缩效率 < 0.8"
       " → 用 CEC 法;否则用 CVE 法。",
       size=12, ha="left")
d.text(45, 1038,
       "· 检验工况(表 D.1):压缩机额定频率、室内机全部运行、额定风量、稳定运行 > 1.5 h;",
       size=12, ha="left")
d.text(45, 1060,
       "  采样间隔 ≤ 5 min(除霜阶段 ≤ 30 s),避开除霜/回油模式(D.2.1/D.2.3)。",
       size=12, ha="left")
d.text(45, 1082,
       "· 现场能效:EERf = CCCf/ECf,COPf = CHCf/EHf(式 D.24/D.25);"
       "调试折算见 7.2.5 式(13)。",
       size=12, ha="left")

d.text(720, 1112,
       "多联机系统现场测试测点布置(带中间喷射支路系统"
       " · 依 GB/T 27941—2026 附录 D 图 D.3)",
       size=15, weight="bold")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "vrf_multisplit_annex_d.png")
d.save(out, out.replace(".png", ".svg"))
print("已生成:", out)
