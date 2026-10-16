# -*- coding: utf-8 -*-
"""示例:多联机(VRF)系统流程图 —— 参考图风格的室外机 + 双室内机。

室外机:涡旋压缩机 → 油分离器(底部毛细管回油至吸气管) → 四通阀 → 室外换热器
       (轴流风机)→ 过滤器 → 单向阀 → 过冷器主管(上进/下出)→ 液管总线截止阀 → 出机;
室内机:液管总管 → 电子膨胀阀 → 换热器 → 气管并联汇入总管;
气管:两室内机汇合 → 总线截止阀 → 四通阀 E 口;
吸气:四通阀 S 口 → 气液分离器 → 压缩机;热气旁通与喷气增焓用虚线表示
       (喷气增焓:过冷器主管出口后分路 → 过冷膨胀阀 → 过冷器支管(右进/左出)
        → 喷气膨胀阀 → 压缩机补气口)。
制热换向由四通阀完成:气管、液管总线各串一只截止阀(检修隔离,运行时常开),
       双向可通;过滤器出口单向阀令制热回液只能经制热膨胀阀旁路进入室外换热器。
管路交叉不画接点,同色交叉处画跳线,T 型三通用黑圆点标记;坐标 1 单位 = 1 像素。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import Arc, Circle, Ellipse, Polygon, Rectangle

from cycleplot import Diagram, make_partial, use_font
from cycleplot.parts import (
    filter,
    four_way_round,
    make_bowtie_valve,
    make_check_valve,
    make_expansion_valve_eng,
    make_globe_valve,
    make_heat_exchanger,
    make_scroll_chord,
    make_separator_utube,
    make_solenoid_valve,
    make_subcooler,
    oil_separator,
)
from cycleplot.style import LW_PIPE

use_font()

RED = "#c62828"      # 高压排气 / 热气
GREEN = "#2e7d32"    # 低压气管 / 吸气
BLUE = "#1565c0"     # 液管
SLATE = "#455a64"    # 喷气 / 旁通(虚线)
NAVY = "#1f3864"

d = Diagram(width=1560, height=1040)

# ===================== 机壳与横幅 =====================
for bx, by, bw, bh in ((40, 80, 940, 900), (1060, 80, 480, 380),
                       (1060, 540, 480, 380)):
    d.ax.add_patch(Rectangle((bx, by), bw, bh, fill=False,
                             edgecolor="#333333", lw=2.2,
                             linestyle=(0, (6, 5)), zorder=0.5))
for bx, bw, name in ((60, 150, "室外机"), (1080, 165, "室内机 1"),
                     (1080, 165, "室内机 2")):
    by = 555 if name.endswith("2") else 95
    d.ax.add_patch(Rectangle((bx, by), bw, 36, facecolor=NAVY, zorder=3))
    d.text(bx + bw / 2, by + 18, name, size=16, weight="bold", color="white")
d.text(780, 45, "多联机(VRF)系统原理图", ha="center", size=17)

# ===================== 部件 =====================
comp = d.add(make_partial(make_scroll_chord(), {"discharge": (0, -85)}),
             "压缩机", loc=(140, 840), label_offset=(50, -140))
oil = d.add(oil_separator, None, loc=(140, 470))
fw = d.add(four_way_round, "", loc=(200, 230), mark=False)
cond = d.add(make_heat_exchanger(240, 110, shape="rect_zigzag7"), None,
             loc=(620, 250))
filt = d.add(filter, "过滤器", loc=(830, 250))
# 阀门统一用小号工厂参数(默认 r=34 偏大,取 ~75%)
eev_p = make_expansion_valve_eng(r=26)
hee = d.add(make_bowtie_valve(actuator="dome", w=60, h=34, dome_r=16,
                              stem=12), "制热膨胀阀", loc=(760, 340))
# 过冷器:矩形 + 中央竖线四接口(主管上进/下出,支管右进/左出,逆流错开)
sub = d.add(make_subcooler(w=64, h=150), None, loc=(700, 560))
sub_eev = d.add(eev_p, "过冷膨胀阀", loc=(790, 660))
bypass = d.add(make_solenoid_valve(r=26, stem=16, handle=32), "热气旁通阀",
               loc=(485, 610))
acc = d.add(make_separator_utube(flip=True), None, loc=(330, 790))
gee = d.add(eev_p, "喷气膨胀阀", loc=(600, 780))
# 液管/气管总线:截止阀(检修隔离用,运行时常开),双向可通
liq_stop = d.add(make_globe_valve(), "截止阀", loc=(935, 730))
gas_stop = d.add(make_globe_valve(), None, loc=(895, 930))
# 过滤器出口单向阀:挡住制热回液,使其只能走制热膨胀阀旁路进室外换热器
ck_c = d.add(make_check_valve(w=44, h=24, stub=10), None, loc=(912, 250))
eev1 = d.add(eev_p, "电子膨胀阀", loc=(1120, 200))
coil1 = d.add(make_heat_exchanger(240, 100, shape="rect_zigzag7"), None,
              loc=(1360, 200))
eev2 = d.add(eev_p, "电子膨胀阀", loc=(1120, 640))
coil2 = d.add(make_heat_exchanger(240, 100, shape="rect_zigzag7"), None,
              loc=(1360, 640))

# 室外换热器轴流风机(手绘:两翼片 + 轮毂 + 支架)
d.ax.add_patch(Ellipse((590, 150), 60, 20, facecolor=NAVY, zorder=1))
d.ax.add_patch(Ellipse((650, 150), 60, 20, facecolor=NAVY, zorder=1))
d.ax.add_patch(Circle((620, 150), 5, facecolor="white",
                      edgecolor=NAVY, lw=1.5, zorder=4))
d.ax.add_patch(Polygon([(612, 158), (628, 158), (634, 196), (606, 196)],
                       facecolor=NAVY, zorder=1))

# ===================== 文字标注 =====================
d.text(46, 625, "油分离器", ha="left", size=15)
d.text(326, 556, "回油毛细管", size=14)
d.text(100, 170, "四通阀", ha="left", size=15)
d.text(224, 178, "D", size=14)
d.text(256, 206, "C", size=14)
d.text(150, 266, "E", size=14, ha="right")
d.text(140, 206, "S", size=14, ha="right")
d.text(752, 210, "室外换热器", ha="left", size=15)
d.text(742, 560, "过冷器", ha="left", size=15)
d.text(400, 895, "气液分离器", ha="left", size=15)
d.text(895, 966, "截止阀", size=18)

# ===================== 室外机管路 =====================
# 排气:压缩机 → 升压绕行 → 油分顶部
d.pipe(comp["discharge"], oil["top"],
       via=[(140, 620), (230, 620), (230, 330), (140, 330)],
       color=RED, head_at=(0.12, 0.6))
# 油分干气 → 四通阀 D 口
d.pipe(oil["left"], fw["exhaust"],
       via=[(55, 426), (55, 150), (200, 150)], color=RED, head_at=(0.4,))
# 回油:油分底部 → 毛细管(之字形) → 三通接入 S→气液分离器吸气管
d.pipe(oil["bottom"], (250, 585), via=[(140, 585)], color=RED,
       head_at=(0.5,))
# 之字形毛细管(手绘折线:走线路由会把斜线正交化,这里直接画尖齿)
d.ax.plot([250, 258, 276, 294, 312, 330, 348, 366, 384, 402],
          [585, 573, 597, 573, 597, 573, 597, 573, 597, 585],
          color=RED, lw=LW_PIPE, solid_capstyle="round",
          solid_joinstyle="round")
d.pipe((402, 585), (420, 585), color=RED, head_at=(0.5,))
# 四通阀 C 口 → 室外换热器
d.pipe(fw["condenser"], cond["left"], via=[(500, 230)],
       color=RED, head_at=(0.5,))
# 室外换热器 → 过滤器 → 单向阀 → 液管立管 → 过冷器
d.pipe(cond["right"], filt["in"], color=BLUE, head=False)
d.pipe(filt["out"], ck_c["in"], color=BLUE, head=False)
d.pipe(ck_c["out"], sub["top"],
       via=[(950, 250), (950, 450), (700, 450)],
       color=BLUE, head_at=(0.3, 0.8))
# 制热膨胀阀旁路:液管立管三通 → 阀 → 室外换热器底部
d.pipe((950, 340), hee["in"], color=BLUE, head_at=(0.6,))
d.pipe(hee["out"], cond["bottom"], via=[(620, 340)],
       color=BLUE, head_at=(0.5,))
# 过冷器主管:上进 → 下出 → 液管总线截止阀 → 液管总管
d.pipe(sub["bottom"], liq_stop["in"], via=[(700, 730)],
       color=BLUE, head_at=(0.4,))
d.pipe(liq_stop["out"], (1010, 200), via=[(1010, 730)],
       color=BLUE, head_at=(0.7,))
# 过冷支路:主管出口后分一路 → 过冷膨胀阀 → 过冷器支管进(右口)
d.pipe((700, 660), sub_eev["in"], color=BLUE, head_at=(0.5,))
d.pipe(sub_eev["out"], sub["right"], via=[(860, 660), (860, 597.5)],
       color=BLUE, head_at=(0.3, 0.75))
# 液管总管 → 两台室内机电子膨胀阀
d.pipe((1010, 200), eev1["in"], color=BLUE, head_at=(0.5,))
d.pipe((1010, 640), eev2["in"], color=BLUE, head_at=(0.5,))
d.pipe(eev1["out"], coil1["left"], color=BLUE, head_at=(0.5,))
d.pipe(eev2["out"], coil2["left"], color=BLUE, head_at=(0.5,))

# ===================== 气管与吸气 =====================
# 室内机 1/2 气管 → 总线 → 截止阀 → 四通阀 E 口
d.pipe(coil1["bottom"], (1040, 500), via=[(1360, 500)],
       color=GREEN, head_at=(0.6,))
d.pipe((1040, 500), (1040, 930), color=GREEN, head_at=(0.85,))
d.pipe(coil2["bottom"], (1040, 930), via=[(1360, 930)],
       color=GREEN, head_at=(0.6,))
d.pipe((1040, 930), gas_stop["out"], color=GREEN, head_at=(0.5,))
d.pipe(gas_stop["in"], fw["evaporator"],
       via=[(250, 930), (250, 310), (200, 310)],
       color=GREEN, head_at=(0.2, 0.75))
# 四通阀 S 口 → 气液分离器(镜像件:in 在东侧,吸气自东直接进入)
d.pipe(fw["suction"], acc["in"],
       via=[(85, 230), (85, 290), (420, 290), (420, 700), (373.8, 700)],
       color=GREEN, head_at=(0.2, 0.7))
# 气液分离器 → 压缩机吸气(镜像件:out 在西侧,向西直接引出)
d.pipe(acc["out"], comp["suction"],
       via=[(277.8, 660), (48, 660), (48, 840)],
       color=GREEN, head_at=(0.35, 0.9))

# ===================== 旁通与喷气(虚线除外的热气旁通) =====================
# 热气旁通:排气管三通 → 电磁阀 → 气液分离器壳体
d.pipe((140, 640), bypass["in"], via=[(400, 640), (400, 610)],
       color=RED, head_at=(0.5,))
d.pipe(bypass["out"], (390, 745), via=[(560, 610), (560, 745)],
       color=RED, head_at=(0.3,))
# 喷气增焓(虚线):过冷器支管出(左口)→ 喷气膨胀阀 → 压缩机补气口
d.pipe(sub["left"], gee["out"], via=[(650, 522.5), (650, 780)],
       color=SLATE, linestyle="dashed", head_at=(0.25, 0.75))
d.pipe(gee["in"], comp["inj"],
       via=[(540, 780), (540, 960), (133.2, 960)],
       color=SLATE, linestyle="dashed", head_at=(0.5, 0.97))

# ===================== T 型三通接点 =====================
for jx, jy in ((140, 640), (950, 340), (1010, 640),
               (1040, 930), (420, 585), (700, 660)):
    d.ax.add_patch(Circle((jx, jy), 3.5, facecolor="#222222",
                          edgecolor="none", zorder=6))

# 排气立管与回油毛细管同色交叉:画跳线,表示不接通
d.ax.add_patch(Circle((230, 585), 8.5, facecolor="white",
                      edgecolor="none", zorder=5))
d.ax.plot([221.5, 238.5], [585, 585], color=RED, lw=LW_PIPE,
          solid_capstyle="butt", zorder=6)
d.ax.add_patch(Arc((230, 585), 17, 17, theta1=-90, theta2=90,
                   edgecolor=RED, lw=LW_PIPE, zorder=6))

# ===================== 图例(无框,底部居中) =====================
d.pipe((500, 1013), (550, 1013), color=BLUE, head_at=(0.5,))
d.text(558, 1013, "液管", ha="left", va="center", size=15)
d.pipe((620, 1013), (670, 1013), color=RED, head_at=(0.5,))
d.text(678, 1013, "排气/热气", ha="left", va="center", size=15)
d.pipe((780, 1013), (830, 1013), color=GREEN, head_at=(0.5,))
d.text(838, 1013, "低压吸气", ha="left", va="center", size=15)
d.pipe((940, 1013), (990, 1013), color=SLATE, linestyle="dashed",
       head=False)
d.text(998, 1013, "喷气增焓", ha="left", va="center", size=15)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "vrf_system.png")
d.save(out)
print("已生成:", out)
