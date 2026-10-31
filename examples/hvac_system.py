# -*- coding: utf-8 -*-
"""示例:空气能 + 蓄热水箱 + 风机盘管/地暖 家用供暖系统。

部件用 rrplot.hvac 的代码图元(由 references/hvacsvg 的 SVG 符号转换),
管路按功能配色 —— 红 = 供水(热)  紫 = 回水干管  蓝 = 就地回水  绿 = 补水/安全。
两个回路:
  ① 主机 ↔ 水箱:主机热水进水箱上口,水箱下口经水泵回主机。
  ② 水箱 → 循环泵 → 过滤器 → 分水器/风机盘管 → 回水干管 → 水箱。
标签避让:水箱 label_dy=-97 提到箱体上方,风机盘管 label_dy=0 压在符号上,
排气阀标签移到符号右侧。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import Rectangle

from rrplot import Diagram, use_font
from rrplot._primitives import line, txt
from rrplot.hvac import (
    auto_vent,
    ball_valve,
    corrugated_pipe,
    electric_heater,
    fan_coil,
    floor_heating,
    heat_pump,
    makeup_valve,
    return_manifold,
    safety_valve,
    supply_manifold,
    thermal_tank,
    water_pump,
)
from rrplot.parts import Part
from rrplot.style import LINE

use_font()

RED, PURPLE, BLUE, GREEN = "#e53935", "#7b3ff2", "#1677ff", "#2e9e58"


def _filter(ax, x, y, label=None, **kw):
    ax.add_patch(Rectangle((x - 8, y - 12), 16, 24, facecolor="white",
                           edgecolor=LINE, lw=1.3))
    line(ax, [(x - 6, y + 7), (x + 6, y - 7)], lw=1.1, color=LINE)
    if label:
        txt(ax, x - 16, y + 40, label, size=15)   # 标签让开立管与混水阀


FILT = Part("过滤器", _filter, {"in": (-14, 0), "out": (14, 0)})


def valve(x, y, s=0.5, label=None):
    return d.add(ball_valve(scale=s, bridge=10), label, loc=(x, y))


d = Diagram(width=1880, height=680)

# ===================== 部件 =====================
# 主机:两个水口都挪到右侧(moves 改连接点坐标,bridge 引管跟着走)
hp = d.add(heat_pump(scale=1.4, bridge=26,
                     moves={"water_out": (160, 20), "water_in": (160, 80)}),
           "空气能主机", loc=(150, 350))
vsw = valve(430, 308, 0.6, "水路开关")          # 主机热水出管上的水路开关
pump1 = d.add(water_pump(bridge=20), "水泵",
              loc=(470, 470))                    # 主机回路循环泵(紫线)

# 蓄热水箱:标签挪到箱体上方(箱内有温度计,压图会叠字),右口下移作供水出
tank = d.add(thermal_tank(scale=1.5, bridge=44,
                          moves={"right": (160, 72)}, label_dy=-97),
             "蓄热水箱", loc=(770, 375))
elec = d.add(electric_heater(scale=0.5), "电加热",
             loc=(700, 450))                     # 挂在水箱下沿

# 管路上的水处理/安全件
safety = d.add(safety_valve(scale=0.6), "安全阀",
               loc=(742, 552))
makeup = d.add(makeup_valve(scale=0.6), "补水",
               loc=(975, 545))

# 供水干管:循环泵 + 过滤器
vcA = valve(940, 445, 0.45)
cpump = d.add(water_pump(scale=0.8, bridge=20), "循环泵",
              loc=(1050, 445))
vcB = valve(1169, 445, 0.45)
filt = d.add(FILT, "过滤器", loc=(1223, 445))    # out x=1237 即东侧立管

# 回水干管顶部 + 自动排气阀(标签放符号右侧,让开竖井)
vent = d.add(auto_vent(scale=0.7), "", loc=(945, 55))
d.text(1015, 52, "自动排气阀", ha="left", size=17)

# 负载1:风机盘管(经不锈钢波纹管接供水),标签压在符号上
bell1 = d.add(corrugated_pipe(scale=0.7), label="",
              loc=(1293, 215))
fcu1 = d.add(fan_coil(scale=1.0, label_dy=0),
             "风机盘管", loc=(1429, 238))
# 负载2:第二台风机盘管(东移让开 1 号机回水立管)
bell2 = d.add(corrugated_pipe(scale=0.7), label="",
              loc=(1595, 215))
fcu2 = d.add(fan_coil(scale=0.9, label_dy=0),
             "风机盘管", loc=(1723, 238))

# 负载3:地暖(两个盘管 + 分水器)
spA = d.add(floor_heating(scale=1.0), label="", loc=(1455, 350))
spB = d.add(floor_heating(scale=1.0), label="", loc=(1455, 490))
d.text(1455, 420, "地暖", size=19)
# 分水器拉开 160px,两组标签互不粘连;moves 把口挪到汇管/圆心上免得留空隙
MAN_MOVE = {"main": (25, 50), "loop1": (145, 30),
            "loop2": (145, 50), "loop3": (145, 70)}
manSup = d.add(supply_manifold(scale=0.75, moves=MAN_MOVE),
               "分水器（供）", loc=(1225, 578))
manRet = d.add(return_manifold(scale=0.75, moves=MAN_MOVE),
               "分水器（进）", loc=(1385, 578))
# 混水阀:out 正好落在 x=1237 落水管上,in 与分水器(供) main 同 x
vmix = valve(1201, 512, 0.45)

# ===================== 管路 =====================
# ---- 回路①:主机 → 水箱(红) ;水箱 → 水泵 → 主机(紫) ----
d.pipe(hp["water_out"], vsw["in"], color=RED, head_at=(0.6,))
d.pipe(vsw["out"], tank["upper"], via=[(655, 308), (655, 348)],
       color=RED, head_at=(0.5,))
d.pipe(tank["lower"], pump1["out"], via=[(625, 405), (625, 470)],
       color=PURPLE, head_at=(0.6,))
d.pipe(pump1["in"], hp["water_in"], via=[(300, 470), (300, 392)],
       color=PURPLE, head_at=(0.5,))

# ---- 回路②供水:水箱 → 阀 → 循环泵 → 阀 → 过滤器(红) ----
d.pipe(tank["right"], vcA["in"], via=[(890, 445)], color=RED, head_at=(0.5,))
d.pipe(vcA["out"], cpump["in"], color=RED, head_at=(0.7,))
d.pipe(cpump["out"], vcB["in"], color=RED, head_at=(0.7,))
d.pipe(vcB["out"], filt["in"], color=RED, head_at=(0.7,))

# 立管:过滤器后向上接 1 号波纹管;东送支管改走 y=290(原 y=168 会与
# 1 号机回水立管相交),从盘管与地暖之间的空档横穿
d.pipe(filt["out"], (1237, 215), color=RED, head_at=(0.35,))
d.pipe((1237, 215), bell1["in"], color=RED, head_at=(0.5,))
d.pipe(bell1["out"], fcu1["water_in"], color=RED, head_at=(0.6,))
d.pipe((1237, 290), bell2["in"], via=[(1539, 290)],
       color=RED, head_at=(0.4, 0.9))
d.pipe(bell2["out"], fcu2["water_in"], color=RED, head_at=(0.6,))

# 供水 → 分水器:过滤器后旁通向下,经混水阀进分水器(供)
d.pipe(filt["out"], vmix["out"], color=RED, head_at=(0.6,))
d.pipe(vmix["in"], manSup["main"], color=RED, head_at=(0.6,))
# 分水器(供) → 地暖盘管(loop1 直上,loop2 先东让开再北)
d.pipe(manSup["loop1"], spA["in"], via=[(1305, 350)],
       color=RED, head_at=(0.5,))
d.pipe(manSup["loop2"], spB["in"], via=[(1305, 578), (1305, 490)],
       color=RED, head_at=(0.5,))
# 地暖盘管 → 分水器(进):共用 x=1545 回水立管
d.pipe(spA["out"], manRet["loop1"], via=[(1545, 350), (1545, 563)],
       color=BLUE, head_at=(0.5,))
d.pipe(spB["out"], manRet["loop2"], via=[(1545, 490), (1545, 578)],
       color=BLUE, head_at=(0.5,))

# ---- 回路②回水:各负载就地回水(蓝)汇入顶部紫色干管 → 水箱 ----
d.pipe(fcu1["water_out"], (1509, 130), color=BLUE, head_at=(0.4,))
d.pipe(fcu2["water_out"], (1795, 130), color=BLUE, head_at=(0.4,))
# 顶部紫色回水干管:东到两台盘管回水与分水器总回水,西到排气阀与水箱
d.pipe((1825, 130), (905, 130), color=PURPLE, head=False)
d.pipe(vent["pipe"], (945, 130), color=PURPLE, head_at=(0.8,))
d.pipe((905, 130), (827, 345), via=[(905, 345)], color=PURPLE,
       head_at=(0.6,))
# 分水器(进)总回水:南侧绕行到东缘北上汇入顶部干管
# (若向西直插水箱,必与红色供水干管 y=445 相交)
d.pipe(manRet["main"], (1825, 130),
       via=[(1325, 570), (1325, 660), (1825, 660)],
       color=PURPLE, head_at=(0.3, 0.8))

# ---- 补水/安全(绿) ----
d.pipe((770, 430), safety["in"], via=[(770, 555)], color=GREEN,
       head_at=(0.7,))
d.pipe(safety["out"], makeup["in"], via=[(880, 555), (880, 545)],
       color=GREEN, head_at=(0.5,))
d.pipe(makeup["out"], (1105, 545), color=GREEN, head_at=(0.5,))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "hvac_system.png")
d.save(out)
print("已生成:", out)
