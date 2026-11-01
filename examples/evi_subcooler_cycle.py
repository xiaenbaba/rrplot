# -*- coding: utf-8 -*-
"""普通热泵常见的 EVI 过冷器式喷气增焓回路。

本例采用普通热泵常见的过冷器四口接法,按参考图连接主路与喷气支路。

主路:压缩机右口排气 → 冷凝器 → 分流点 → 过冷器右口进、左口出
     → 主路膨胀阀 → 蒸发器底口进、顶口出 → 压缩机左口吸气。
支路:冷凝器出口分流 → 补气膨胀阀 → 过冷器底口进、顶口出
     → 电磁阀 → 压缩机底部补气口。

过冷器复用 make_heat_exchanger 的四个端口。左右口属于主路盘管,
上下口属于壳侧喷气支路,两路仅换热、不混合。分流点在过冷器主路
入口之前,与 evi_cycle.py 的主路出口分流接法不同。
压缩机双弦水平布置;蒸发器、冷凝器采用对角交叉样式,过冷器保留之字盘管。
1~9 沿用参考图编号,其中 2/3 为压缩机内部的示意编号。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import Circle
from matplotlib.transforms import Affine2D

from rrplot import Diagram, use_font
from rrplot.parts import (
    make_bowtie_valve,
    make_compressor,
    make_heat_exchanger,
)


def _horizontal_compressor(r=60):
    """圆形机身和四个端口保持原位,内部双弦旋转为水平。"""
    part = make_compressor(r=r, name="涡旋压缩机")
    draw_vertical = part.draw

    def draw(ax, x, y, label=None, **kw):
        start = len(ax.lines)
        draw_vertical(ax, x, y, label=label, **kw)
        transform = Affine2D().rotate_deg_around(x, y, 90) + ax.transData
        for chord in ax.lines[start:]:
            chord.set_transform(transform)

    part.draw = draw
    return part


def build_diagram():
    """构建示意图,返回画布供交互显示或导出。"""
    d = Diagram(width=1000, height=850)

    # 直接使用图元端口连接,压缩机左口吸气、右口排气、底口补气。
    comp = d.add(_horizontal_compressor(), None, loc=(290, 160))
    cond = d.add(make_heat_exchanger(200, 60, shape="rect_x", name="冷凝器"),
                 None, loc=(620, 160))
    evap = d.add(make_heat_exchanger(70, 180, shape="rect_x", name="蒸发器"),
                 None, loc=(130, 445))
    subcooler = d.add(make_heat_exchanger(220, 88, name="过冷器"),
                      None, loc=(580, 590))
    main_valve = d.add(make_bowtie_valve(actuator="dome", name="主路膨胀阀"),
                       None, loc=(330, 590))
    branch_valve = d.add(make_bowtie_valve(actuator="dome",
                                           name="补气膨胀阀"),
                         None, loc=(710, 750))
    solenoid = d.add(make_bowtie_valve(actuator="solenoid", sol_len=48,
                                       name="补气电磁阀"),
                     None, loc=(460, 410))

    # 标题与设备名称。黑白线稿沿用项目现有阀门和换热器图元。
    d.text(500, 30, "EVI 喷气增焓循环（过冷器四口接法）", size=20, weight="bold")
    d.text(500, 64, "主路：右进左出  ·  喷气支路：底进顶出", size=11)
    d.text(620, 106, "冷凝器", size=16)
    d.text(380, 235, "涡旋压缩机", size=16, ha="left")
    d.text(72, 445, "蒸\n发\n器", size=16)
    d.text(640, 518, "过冷器", size=16)
    d.text(330, 633, "主路膨胀阀", size=13)
    d.text(758, 744, "补气膨胀阀", size=13, ha="left")
    d.text(508, 368, "电磁阀", size=14, ha="left")

    # 排气 → 冷凝器 → 入口分流点(5)。
    split = (860, 590)
    d.pipe(comp["right"], cond["left"], head_size=10)
    d.pipe(cond["right"], split, via=[(860, 160)],
           head_at=(0.62,), head_size=10)
    d.ax.add_patch(Circle(split, 4, facecolor="black", edgecolor="none", zorder=6))
    d.text(884, 565, "主路分流", size=11, ha="left")

    # 主路:过冷器右进左出 → 主路膨胀阀 → 蒸发器底进顶出 → 压缩机。
    d.pipe(split, subcooler["right"], head_size=10)
    d.pipe(subcooler["left"], main_valve["in"], head_size=10)
    d.pipe(main_valve["out"], evap["bottom"], via=[(130, 590)], head_size=10)
    d.pipe(evap["top"], comp["left"], via=[(130, 160)],
           head_at=(0.35,), head_size=10)

    # 喷气支路:入口分流 → 补气膨胀阀 → 过冷器底口(8)。
    d.pipe(split, branch_valve["in"], via=[(860, 750)],
           head_at=(0.35, 0.8), head_size=10)
    d.pipe(branch_valve["out"], subcooler["bottom"], via=[(580, 750)],
           head_at=(0.7,), head_size=10)

    # 过冷器顶口 → 电磁阀 → 压缩机底部补气口(9)。
    d.pipe(subcooler["top"], solenoid["in"], via=[(580, 410)], head_size=10)
    d.pipe(solenoid["out"], comp["bottom"], via=[(290, 410)],
           head_at=(0.7,), head_size=10)

    # 参考图编号独立放置,避免自动标注偏移与阀体/短管重叠。
    for number, x, y in (("1", 209, 142), ("2", 246, 163),
                         ("3", 334, 163), ("4", 374, 142),
                         ("5", 828, 568), ("6", 447, 568),
                         ("7", 293, 568), ("8", 552, 713),
                         ("9", 314, 256)):
        d.text(x, y, number, size=14)

    d.text(500, 802, "主路：冷凝器 → 过冷器右口 → 左口 → 膨胀阀 → 蒸发器",
           size=10, color="#555555")
    d.text(500, 827,
           "喷气支路：冷凝器出口分流 → 膨胀阀 → 过冷器底口 → 顶口 "
           "→ 电磁阀 → 压缩机补气口", size=10, color="#555555")
    return d


if __name__ == "__main__":
    use_font()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "evi_subcooler_cycle.png")
    with build_diagram() as diagram:
        diagram.save(out, out.replace(".png", ".svg"), dpi=140)
    print("已生成:", out)
