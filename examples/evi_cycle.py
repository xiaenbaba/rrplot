# -*- coding: utf-8 -*-
"""多联机 / VRF 常见的 EVI 经济器喷气增焓系统图。

这张图把 EVI 循环拆成五个容易追踪的流路:

* 红色:压缩机排气和冷凝器出口的高压侧;
* 橙色:冷凝后的高压液体;
* 蓝色:经过 EEV-1 后进入经济器的中间压力主路;
* 紫色:经济器副路出口回到压缩机补气口;
* 青色:蒸发器出口回压缩机吸气口的低压回气。

这类回路常用于多联机室外机,主路为 冷凝器 → EEV-1 → 经济器主路
→ EEV-2 → 蒸发器,
喷气支路从经济器主路出口、EEV-2 之前分流，
经 EEV-3 → 经济器副路 → 压缩机补气口。
经济器竖直布置:主路右侧自上向下,副路左侧自下向上,两路逆流。
三个电子膨胀阀的编号与控制功能分别标在阀旁，状态点编号沿管线标注。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from rrplot import Diagram, make_partial, use_font
from rrplot.parts import (
    make_compressor,
    make_expansion_valve_x,
    make_heat_exchanger,
    make_intermediate_hex,
)
from rrplot.style import FONT_STACK

use_font()

# 留出右侧阀门说明和底部图例空间,避免文字压住管路。
d = Diagram(width=1050, height=820)

# 统一的流程颜色,箭头与接点共同标明主路和喷气支路。
DISCHARGE = "#c43d3d"       # 排气/冷凝器高压气
LIQUID = "#c2761b"          # 冷凝器出口高压液体
INTERMEDIATE = "#2f67b1"    # 经济器主路中间压力
INJECTION = "#7b4aa8"       # 补气支路
SUCTION = "#138a8a"         # 蒸发器出口低压回气


# ===================== 部件 =====================
comp = d.add(make_compressor(r=42, style="圆形"), None, loc=(180, 390))
cond = d.add(make_heat_exchanger(200, 56, shape="rect_zigzag7"),
             None, loc=(440, 130))
evap = d.add(make_heat_exchanger(200, 56, shape="rect_zigzag7", name="蒸发器"),
             None, loc=(440, 690))
# 原图元为 190 × 80,竖放时交换宽高,保持外壳与通道间距的比例。
economizer = d.add(make_intermediate_hex(w=80, h=190, orient="v"), None,
                    loc=(736, 390))
main_x = economizer["main_in"].point[0]
sub_x = economizer["sub_in"].point[0]

# 主路预节流、主路蒸发节流、喷气支路节流。
eev1 = d.add(make_expansion_valve_x(orient="v"), None, loc=(main_x, 215))
eev2 = d.add(make_expansion_valve_x(orient="v"), None, loc=(main_x, 615))
# 喷气支路向左折后向上节流:阀门与副路底部入口对齐。
eev3 = d.add(make_partial(
    make_expansion_valve_x(orient="v"),
    ports={"in": (0, 10), "out": (0, -10)},
    dirs={"in": "s", "out": "n"}), None, loc=(sub_x, 520))


# ===================== 标题与设备标注 =====================
d.text(500, 28, "EVI 经济器喷气增焓制冷循环", size=21, weight="bold")
d.text(500, 57, "双级节流 · 中间换热器过冷 · 压缩机中间压力补气",
        size=11, color="#555555")

d.text(440, 88, "冷凝器", size=15, weight="bold")
d.text(440, 744, "蒸发器", size=15, weight="bold")
d.text(112, 390, "压缩机", size=15, weight="bold", ha="right")
d.text(810, 390, "中间换热器\n（经济器）", size=15, weight="bold", ha="left")

# 阀门标签用白底,即使与折线路径靠近也保持可读。
d.text(820, 215, "EEV-1\n主路预节流", size=11, ha="left", boxed=True)
d.text(sub_x - 40, 520, "EEV-3\n喷气支路节流", size=11, ha="right", boxed=True)
d.text(820, 615, "EEV-2\n蒸发器节流", size=11, ha="left", boxed=True)

# 经济器两条竖直通道分别连接顶部和底部端口。
d.text(sub_x, 390, "副\n路\n↑", size=12, color=INJECTION, boxed=True)
d.text(main_x, 390, "主\n路\n↓", size=12, color=INTERMEDIATE, boxed=True)


# ===================== 管路 =====================
# 1) 压缩机排气 → 冷凝器左口(状态 2)。
d.pipe(comp["top"], cond["left"], via=[(180, 130)],
       color=DISCHARGE, head_at=(0.52,),
       states=[{"text": "2", "at": 0.48, "side": -1, "size": 13}])

# 2) 冷凝器出口 → EEV-1。这里不分出喷气支路。
d.pipe(cond["right"], eev1["in"], via=[(main_x, 130)],
       color=LIQUID, head_at=(0.6,),
       states=[{"text": "3", "at": 0.65, "side": -1, "size": 13}])

# 3) EEV-1 → 经济器主路顶部入口,主路在右侧向下流动。
d.pipe(eev1["out"], economizer["main_in"],
       color=INTERMEDIATE, head_at=(0.58,),
       states=[{"text": "4", "at": 0.50, "side": -1, "size": 13}])

# 4) 主路从经济器底部流出后分流:向下去 EEV-2,向左经 EEV-3 去副路。
split = (main_x, 560)
d.pipe(economizer["main_out"], split, color=INTERMEDIATE,
       head_at=(0.5,))
d.ax.add_patch(Circle(split, 5, facecolor=INTERMEDIATE, edgecolor="white",
                      lw=1.2, zorder=7))
d.text(820, 560, "主路出口分流", size=10, ha="left",
        color=INTERMEDIATE)
d.pipe(split, eev3["in"], via=[(sub_x, 560)],
       color=INTERMEDIATE, head_at=(0.5,))
d.pipe(eev3["out"], economizer["sub_in"],
       color=INJECTION, head_at=(0.58,),
       states=[{"text": "6", "at": 0.60, "side": -1, "size": 13}])

# 5) 主路出口分流点 → EEV-2 → 蒸发器右口(状态 5)。
# 之字盘管连接左右两口,按本图流向从右口进入、左口流出。
d.pipe(split, eev2["in"], color=INTERMEDIATE, head_at=(0.50,))
d.pipe(eev2["out"], evap["right"], via=[(main_x, 690)],
       color=SUCTION, head_at=(0.58,),
       states=[{"text": "5", "at": 0.63, "side": 1, "size": 13}])

# 6) 经济器副路顶部出口 → 压缩机补气口(状态 7)。
d.pipe(economizer["sub_out"], comp["right"],
       via=[(sub_x, 245), (370, 245), (370, 390)], color=INJECTION,
       head_at=(0.35, 0.85),
       states=[{"text": "7", "at": 0.78, "side": -1, "size": 13}])

# 7) 蒸发器左口 → 压缩机底部吸气口(状态 1)。
d.pipe(evap["left"], comp["bottom"],
       via=[(180, 690)], color=SUCTION,
       head_at=(0.40, 0.82),
       states=[{"text": "1", "at": 0.30, "side": 1, "size": 13}])


# ===================== 图例与说明 =====================
legend_handles = [
    Line2D([0], [0], color=DISCHARGE, lw=2.2, label="排气 / 高压气"),
    Line2D([0], [0], color=LIQUID, lw=2.2, label="冷凝液 / 高压液"),
    Line2D([0], [0], color=INTERMEDIATE, lw=2.2, label="经济器主路"),
    Line2D([0], [0], color=INJECTION, lw=2.2, label="喷气补气支路"),
    Line2D([0], [0], color=SUCTION, lw=2.2, label="蒸发回气 / 吸气"),
]
d.ax.legend(handles=legend_handles, loc="upper left",
            bbox_to_anchor=(0.79, 0.97), ncol=1,
            prop={"family": FONT_STACK, "size": 9},
            frameon=True, framealpha=0.95, handlelength=2.5,
            columnspacing=1.5)
d.text(505, 794,
        "状态点: 1 吸气 · 2 排气 · 3 冷凝液 · 4 经济器主路入口 · "
        "5 蒸发器入口 · 6 喷气支路入口 · 7 补气",
        size=9, color="#555555")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evi_cycle.png")
d.save(out, out.replace(".png", ".svg"), dpi=140)
print("已生成:", out)


