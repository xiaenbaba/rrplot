# -*- coding: utf-8 -*-
"""示例:SVG 图元 + cycleplot 走线(路线一)。

部件来自 references/hvacsvg/symbols/ 的 SVG 符号,经 load_svg_part 变成
cycleplot 部件;管路、拐角、标签仍由引擎编译。回路:
  空气能主机 -> 球阀 -> 水泵 -> 蓄热水箱 -> (回水) -> 空气能主机
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, load_svg_part, use_font

use_font()

SYM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "references", "hvacsvg", "symbols")

d = Diagram(width=1050, height=560)

host = d.add(load_svg_part(os.path.join(SYM, "01_空气能主机.svg"), bridge=24),
             "空气能主机", loc=(130, 180))
valve = d.add(load_svg_part(os.path.join(SYM, "17_球阀.svg"), bridge=12),
              "球阀", loc=(350, 170))
pump = d.add(load_svg_part(os.path.join(SYM, "02_水泵.svg"), bridge=20),
             "水泵", loc=(570, 170))
tank = d.add(load_svg_part(os.path.join(SYM, "04_蓄热水箱.svg"),
                          ports={"upper": "upper", "lower": "lower"}, bridge=27),
             "蓄热水箱", loc=(850, 188))

# 供水:主机 -> 球阀 -> 水泵 -> 水箱上接口(同一水平线,直连)
d.pipe(host["water_out"], valve["in"])
d.pipe(valve["out"], pump["in"])
d.pipe(pump["out"], tank["upper"])
# 回水:水箱下接口 -> 下行 -> 左行 -> 上行 -> 进主机
d.pipe(tank["lower"], host["water_in"],
       via=[(770, 430), (30, 430), (30, 190)], head_at=(0.35,))

d.text(40, 455, "回水", ha="left")
d.text(700, 155, "供水", ha="left")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "hvacsvg_demo.png")
d.save(out)
print("已生成:", out)
