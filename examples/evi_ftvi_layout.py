# -*- coding: utf-8 -*-
"""按 FTVI 示例版式绘制的 EVI 过冷器喷气增焓循环。

冷凝器在上、蒸发器在下、过冷器在左、压缩机在右。主路使用过冷器
的上下端口,喷气支路使用左右端口:冷凝器出口分流后,一支经 EEV1
进入过冷器左口,从右口出来接压缩机补气口;主路从过冷器顶口进入,
底口出来经 EEV2 进入蒸发器。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import Circle

from rrplot import Diagram, use_font
from rrplot.parts import make_compressor, make_expansion_valve_x, make_heat_exchanger


def build_diagram():
    """构建 FTVI 版式的 EVI 图,返回 Diagram 实例。"""
    d = Diagram(width=760, height=580)
    cond = d.add(make_heat_exchanger(200, 56, shape="rect_x",
                                     name="冷凝器"), None, loc=(330, 70))
    evap = d.add(make_heat_exchanger(200, 56, shape="rect_x",
                                     name="蒸发器"), None, loc=(330, 490))
    # 过冷器之字竖向走线接顶/底口(主路),右端与压缩机补气口同高。
    subcooler = d.add(make_heat_exchanger(66, 150, shape="rect_zigzag7",
                                          orient="v", name="过冷器"),
                      None, loc=(110, 272))
    comp = d.add(make_compressor(r=42, style="圆形"), None, loc=(600, 272))
    # EEV1 竖直放在喷气支管中点:上口进、下口出,再接过冷器左口。
    eev1 = d.add(make_expansion_valve_x(r=10, orient="v", name="EEV1"),
                 None, loc=(40, 171))
    eev2 = d.add(make_expansion_valve_x(orient="v", name="EEV2"),
                 None, loc=(110, 410))

    # 设备位置和 FTVI 示例一致,顶部标签也沿用其留白方式。
    d.text(330, 28, "冷凝器", size=15)
    d.text(330, 450, "蒸发器", size=15)
    d.text(126, 180, "过冷器", size=15, ha="left")
    d.text(240, 306, "喷气支路", size=11, color="#555555")
    d.text(56, 171, "EEV1", size=13, ha="left")
    d.text(132, 412, "EEV2", size=13, ha="left")
    d.text(126, 56, "5", size=13, ha="left")
    d.text(74, 185, "6", size=13, ha="right")
    d.text(126, 360, "7", size=13, ha="left")
    d.text(44, 262, "8", size=13, ha="left")
    d.text(536, 254, "9", size=13, ha="left")
    d.text(614, 326, "1", size=13, ha="left")
    d.text(569, 275, "2", size=13, ha="left")
    d.text(631, 275, "3", size=13, ha="left")
    d.text(614, 222, "4", size=13, ha="left")
    d.text(540, 298, "压缩机", size=15, ha="right")

    # 分流三通:冷凝器出口水平引线末端向下出三通——
    # 一路垂直向下接过冷器顶口(主路),一路水平西行再折向下接 EEV1(喷气支路)。
    split = (110, 70)
    d.pipe(comp["top"], cond["right"], via=[(600, 70)], head_at=(0.3, 0.7))
    d.pipe(cond["left"], split, head_at=(0.55,))
    d.ax.add_patch(Circle(split, 4, facecolor="black", edgecolor="none",
                          zorder=6))
    d.pipe(split, subcooler["top"], head_at=(0.5,))
    d.pipe(subcooler["bottom"], eev2["in"])
    d.pipe(eev2["out"], evap["left"], via=[(110, 490)])
    d.pipe(split, eev1["in"], via=[(40, 70)], head_at=(0.5,))
    d.pipe(eev1["out"], subcooler["left"], via=[(40, 272)])
    d.pipe(subcooler["right"], comp["left"], head_at=(0.55,))
    d.pipe(evap["right"], comp["bottom"], via=[(600, 490)],
           head_at=(0.3, 0.7))
    return d


if __name__ == "__main__":
    use_font()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "evi_ftvi_layout.png")
    with build_diagram() as diagram:
        diagram.save(out, out.replace(".png", ".svg"), dpi=140)
    print("已生成:", out)
