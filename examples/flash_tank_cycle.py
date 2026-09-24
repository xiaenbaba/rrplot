# -*- coding: utf-8 -*-
"""示例:闪发罐双级压缩循环 —— 用 cycleplot 引擎 + 标准 PFD 符号组装。

回路:冷凝器 -> EEV1 -> 闪发罐 -> 底部出液 EEV2 -> 蒸发器
                        -> 顶部闪发气 -> 两级压缩机之间的混合点
      蒸发器 -> 低压级压缩机 -> 高压级压缩机 -> 冷凝器

对照 references/refcycle_flashtank.py(该版用 schemdraw + 手写绝对坐标折线,
这里改用端口 + 走点,拐点由引擎自动补齐)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, parts, use_font

use_font()

CP_X, CP_R = 620, 70          # 两台压缩机的 x / 半径
CP1_Y, CP2_Y = 440, 190       # 低压级 / 高压级中心高度
VAPOR_Y = 315                 # 闪发气接入两级之间的高度

d = Diagram(width=800, height=660)

# ---------- 部件 ----------
cond = d.add(parts.make_heat_exchanger(200, 70, shape="rect_zigzag7"),
             "冷凝器", loc=(330, 60))
evap = d.add(parts.make_heat_exchanger(200, 70, shape="rect_zigzag7"),
             "蒸发器", loc=(330, 560))
tank = d.add(parts.make_vessel(70, 190), "闪发罐", loc=(90, 371))
eev1 = d.add(parts.valve, loc=(90, 170))
eev2 = d.add(parts.valve, loc=(90, 515))
lpc = d.add(parts.make_compressor(CP_R, style="centrifugal"), "低压级压缩机",
            loc=(CP_X, CP1_Y), label_offset=(-CP_R - 40, 0), label_ha="right")
hpc = d.add(parts.make_compressor(CP_R, style="centrifugal"), "高压级压缩机",
            loc=(CP_X, CP2_Y), label_offset=(-CP_R - 40, 0), label_ha="right")

d.text(145, 170, "EEV$_1$", ha="left")
d.text(145, 515, "EEV$_2$", ha="left")

# ---------- 管路 ----------
# 冷凝器 -> 左行 -> 下行 -> EEV1 -> 闪发罐顶部进液
d.pipe(cond["left"], eev1["top"], via=[(90, 60)])
d.pipe(eev1["bottom"], tank["top"])
# 闪发气 -> 两级之间的混合点(端点落在级间管线的中段,总线式接法)
d.pipe(tank["vapor"], (CP_X, VAPOR_Y))
# 闪发罐底部出液 -> EEV2 -> 蒸发器
d.pipe(tank["bottom"], eev2["top"])
d.pipe(eev2["bottom"], evap["left"], via=[(90, 560)])
# 蒸发器 -> 低压级吸气 -> 低压级排气 -> 高压级吸气
d.pipe(evap["right"], lpc["bottom"], via=[(CP_X, 560)])
d.pipe(lpc["top"], hpc["bottom"])
# 高压级排气 -> 上行 -> 左行 -> 冷凝器
d.pipe(hpc["top"], cond["right"], via=[(CP_X, 60)])

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "flash_tank_cycle.png")
d.save(out)
print("已生成:", out)
