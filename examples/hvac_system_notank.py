# -*- coding: utf-8 -*-
"""示例:实际的无水箱直供系统(按参考照片拓扑复刻)。

与 examples/hvac_system.py 的带水箱版不同,本图按参考图的真实拓扑走:

  供水(红):主机 → 防冻阀 → 立管 x=810(顶端放气件 + 三个阀门)
      ├─ y=225 东行干管 → 两台风机盘管下口(经波纹管)
      └─ 南下过回水总管 → 阀 → 分水器(供) → 地暖盘管
  回水:
      · 风机盘管上口 → 波纹管 → 紫色立管 → 顶部紫色干管 y=90
        → 西端 x=760 南下汇入蓝色总管;
      · 地暖 → 分水器(进) → 南绕 y=645 → x=1150 北上汇入总管;
  蓝色总管 y=432(补水阀、膨胀罐就地接管) → 水泵 → 主机回水口。

对照参考图新增的局部图元:立管阀门(竖向对顶三角)、立管顶端放气件、
膨胀罐(挂在总管下方的绿色罐)。风机盘管两个水口都用 moves 挪到左侧
(上口回水、下口供水),与参考图一致。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

from rrplot import Diagram, use_font
from rrplot._primitives import line, txt
from rrplot.hvac import (
    anti_freeze_valve,
    auto_vent,
    ball_valve,
    corrugated_pipe,
    fan_coil,
    floor_heating,
    heat_pump,
    return_manifold,
    supply_manifold,
    water_pump,
)
from rrplot.parts import Part

use_font()

RED, PURPLE, BLUE, GREEN = "#e53935", "#7b3ff2", "#1677ff", "#2e9e58"


# ===================== 局部图元(参考图特有) =====================
def _vvalve(ax, x, y, label=None, **kw):
    """立管上的阀门:竖向对顶三角 + 白心圆。"""
    ax.add_patch(Polygon([(x - 14, y - 18), (x + 14, y - 18), (x, y)],
                         closed=True, facecolor=RED, edgecolor=RED, lw=1))
    ax.add_patch(Polygon([(x - 14, y + 18), (x + 14, y + 18), (x, y)],
                         closed=True, facecolor=RED, edgecolor=RED, lw=1))
    ax.add_patch(__import__("matplotlib.patches", fromlist=["Circle"])
                 .Circle((x, y), 4.5, facecolor="white", edgecolor=RED, lw=1.5))


VV = Part("阀门", _vvalve, {"n": (0, -16), "s": (0, 16)})


def _riser_top(ax, x, y, label=None, **kw):
    """立管顶端的放气/安全件(参考图红色立式件)。"""
    line(ax, [(x, y), (x, y - 16)], lw=2.4, color=RED)
    ax.add_patch(Rectangle((x - 11, y - 46), 22, 30, facecolor="#fdecec",
                           edgecolor=RED, lw=2))
    line(ax, [(x - 14, y - 46), (x + 14, y - 46)], lw=2.6, color=RED)
    line(ax, [(x, y - 46), (x, y - 54)], lw=2, color=RED)
    line(ax, [(x - 7, y - 54), (x + 7, y - 54)], lw=2.6, color=RED)


RISER_TOP = Part("放气件", _riser_top, {"bottom": (0, 0)})


def _exp_tank(ax, x, y, label=None, **kw):
    """膨胀罐:总管下方的绿色胶囊罐。"""
    line(ax, [(x, y), (x, y + 12)], lw=2.4, color=GREEN)
    ax.add_patch(FancyBboxPatch((x - 14, y + 14), 28, 46,
                                boxstyle="round,pad=14",
                                facecolor="#e7f7ee", edgecolor=GREEN, lw=2))
    if label:
        txt(ax, x + 40, y + 46, label, size=16, ha="left")


TANK = Part("膨胀罐", _exp_tank, {"top": (0, 0)})

# 分水器 moves:口挪到汇管/圆心上,免得留空隙(与带水箱版相同)
MAN_MOVE = {"main": (25, 50), "loop1": (145, 30),
            "loop2": (145, 50), "loop3": (145, 70)}
FCU_MOVE = {"water_out": (0, 35), "water_in": (0, 70)}

d = Diagram(width=1880, height=680)

# ===================== 部件 =====================
hp = d.add(heat_pump(scale=1.4, bridge=26,
                     moves={"water_out": (160, 20), "water_in": (160, 80)}),
           "空气能主机", loc=(150, 390))
vg = d.add(anti_freeze_valve(scale=0.5, bridge=14, label_dy=-45),
           "防冻阀", loc=(470, 348))

# 蓝色总管:水泵、补水阀、膨胀罐(自西向东)
pump = d.add(water_pump(scale=0.8, bridge=20,
                        moves={"in": (160, 50), "out": (0, 50)}),
             "水泵", loc=(400, 432))
vmk = d.add(ball_valve(scale=0.45, bridge=10, label_dy=-45),
            "补水阀", loc=(520, 432))
d.add(TANK, "膨胀罐", loc=(620, 432))

# 红色立管:顶端放气件 + 上下串三个立式阀
rtop = d.add(RISER_TOP, "", loc=(810, 200))
vA = d.add(VV, "", loc=(810, 255))
vB = d.add(VV, "", loc=(810, 315))
vC = d.add(VV, "", loc=(810, 390))

# 顶部紫色干管 + 自动排气阀
vent = d.add(auto_vent(scale=0.7), "", loc=(760, 40))
d.text(780, 38, "自动排气阀", ha="left", size=17)

# 风机盘管:两个水口都挪到左侧(上口回水接波纹管,下口供水)
bell1u = d.add(corrugated_pipe(scale=0.5), "", loc=(1302, 150))
bell1l = d.add(corrugated_pipe(scale=0.5), "", loc=(1302, 185))
fcu1 = d.add(fan_coil(scale=1.0, moves=FCU_MOVE, bridge=20, label_dy=0),
             "风机盘管", loc=(1430, 165))
bell2u = d.add(corrugated_pipe(scale=0.5), "", loc=(1579, 151.5))
bell2l = d.add(corrugated_pipe(scale=0.5), "", loc=(1579, 183))
fcu2 = d.add(fan_coil(scale=0.9, moves=FCU_MOVE, bridge=20, label_dy=0),
             "风机盘管", loc=(1700, 165))
d.text(1302, 124, "不锈钢波纹管", size=15)
d.text(1579, 124, "不锈钢波纹管", size=15)

# 地暖 + 分水器
spA = d.add(floor_heating(scale=1.0), "", loc=(1500, 300))
spB = d.add(floor_heating(scale=1.0), "", loc=(1500, 450))
d.text(1500, 375, "地暖", size=19)
manSup = d.add(supply_manifold(scale=0.75, moves=MAN_MOVE),
               "分水器（供）", loc=(1230, 560))
manRet = d.add(return_manifold(scale=0.75, moves=MAN_MOVE),
               "分水器（进）", loc=(1420, 560))
vf = d.add(ball_valve(scale=0.4, bridge=10), "", loc=(860, 600))

# ===================== 管路 =====================
# ---- 供水(红):主机 → 防冻阀 → 立管 ----
d.pipe(hp["water_out"], vg["in"], color=RED, head_at=(0.6,))
d.pipe(vg["out"], (810, 348), color=RED, head_at=(0.35, 0.8))
# 立管上行:两个立阀之间、阀与 T 之间、顶端放气件
d.pipe((810, 348), vB["s"], color=RED)
d.pipe(vB["n"], vA["s"], color=RED)
d.pipe(vA["n"], (810, 225), color=RED)
d.pipe((810, 225), rtop["bottom"], color=RED, head_at=(0.5,))
# 立管下行:过回水总管 → 阀 C → 分水器(自上而下先 n 后 s)
d.pipe((810, 348), vC["n"], color=RED, head_at=(0.6,))
d.pipe(vC["s"], (810, 600), color=RED, head_at=(0.35, 0.8))

# 东行供水干管 → 两台盘管下口
d.pipe((810, 225), (1240, 225), color=RED, head_at=(0.3, 0.75))
d.pipe((1240, 225), (1530, 225), color=RED, head_at=(0.35, 0.85))
d.pipe((1240, 225), (1240, 185), color=RED, head_at=(0.5,))
d.pipe((1240, 185), bell1l["in"], color=RED, head_at=(0.5,))
d.pipe(bell1l["out"], fcu1["water_in"], color=RED)
d.pipe((1530, 225), (1530, 183), color=RED, head_at=(0.5,))
d.pipe((1530, 183), bell2l["in"], color=RED)
d.pipe(bell2l["out"], fcu2["water_in"], color=RED)

# 立管底部 → 阀 → 分水器(供)
d.pipe((810, 600), vf["in"], color=RED)
d.pipe(vf["out"], manSup["main"], via=[(1189, 600)],
       color=RED, head_at=(0.3, 0.75))
# 分水器(供) → 地暖(loop1 上北,loop2 先东再北)
d.pipe(manSup["loop1"], spA["in"], via=[(1330, 545), (1330, 300)],
       color=RED, head_at=(0.3, 0.8))
d.pipe(manSup["loop2"], spB["in"], via=[(1355, 560), (1355, 450)],
       color=RED, head_at=(0.35, 0.85))
# 地暖 → 分水器(进):共用东侧 x=1660 回水立管
d.pipe(spA["out"], manRet["loop1"], via=[(1660, 300), (1660, 545)],
       color=BLUE, head_at=(0.3, 0.8))
d.pipe(spB["out"], manRet["loop2"], via=[(1660, 450), (1660, 560)],
       color=BLUE, head_at=(0.35, 0.85))

# 分水器(进)总回水:南绕 y=645 到 x=1150 北上汇入蓝色总管
# (若向西直插,必与红色立管 x=810 及分水器标签相撞)
d.pipe(manRet["main"], (1150, 432),
       via=[(1379, 595), (1330, 595), (1330, 645), (1150, 645)],
       color=BLUE, head_at=(0.15, 0.45, 0.8))

# ---- 盘管回水(紫):上口 → 波纹管 → 立管 → 顶部干管 → 西端南下 ----
d.pipe(fcu1["water_out"], bell1u["out"], color=PURPLE)
d.pipe(bell1u["in"], (1240, 150), color=PURPLE)
d.pipe((1240, 150), (1240, 90), color=PURPLE, head_at=(0.45,))
d.pipe(fcu2["water_out"], bell2u["out"], color=PURPLE)
d.pipe(bell2u["in"], (1530, 151.5), color=PURPLE)
d.pipe((1530, 151.5), (1530, 90), color=PURPLE, head_at=(0.45,))
d.pipe((1530, 90), (760, 90), color=PURPLE, head_at=(0.3, 0.75))
# 起点插进排气阀引管,盖住端口间隙
d.pipe((760, 60), (760, 90), color=PURPLE, head_at=(0.8,))
d.pipe((760, 90), (760, 432), color=PURPLE, head_at=(0.4,))

# ---- 蓝色总管:汇合后西行 → 补水阀 → 水泵 → 主机 ----
d.pipe((1150, 432), (760, 432), color=BLUE, head_at=(0.3, 0.75))
d.pipe((760, 432), vmk["out"], color=BLUE, head_at=(0.4,))
d.pipe(vmk["in"], pump["in"], color=BLUE, head_at=(0.5,))
d.pipe(pump["out"], hp["water_in"], color=BLUE, head_at=(0.6,))

# 风机盘管送风气流(绿箭头,参考图有)
d.pipe((1370, 210), (1300, 210), color=GREEN, head_at=(0.75,))
d.pipe((1646, 210), (1576, 210), color=GREEN, head_at=(0.75,))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "hvac_system_notank.png")
d.save(out)
print("已生成:", out)
