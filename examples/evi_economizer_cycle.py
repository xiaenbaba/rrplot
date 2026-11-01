# -*- coding: utf-8 -*-
"""普通热泵 EVI 经济器的另一种竖直排布方式。

本例按参考图使用四口换热器作为经济器:

* 主路:冷凝器出口分流 → 经济器顶部 → 经济器底部 → EEV2 → 蒸发器;
* 喷气支路:分流点 → EEV1 → 经济器左侧 → 经济器右侧
  → 压缩机补气口。

因此经济器的上下端口属于主路,左右端口属于喷气支路。该拓扑与
``evi_subcooler_cycle.py`` 的热力关系相同,只是换热器和阀门的排布
更接近常见的竖直经济器流程图。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matplotlib.patches import Circle
from matplotlib.transforms import Affine2D

from rrplot import Diagram, make_partial, use_font
from rrplot.parts import make_compressor, make_expansion_valve_x, make_heat_exchanger


def _horizontal_compressor(r=60):
    """圆形机身和端口保持原位,只将内部双弦旋转为水平。"""
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


def _westward_valve():
    """膨胀阀水平右进左出,用于经济器喷气支路。"""
    valve = make_expansion_valve_x(r=13, orient="h", name="EEV1")
    return make_partial(valve,
                        ports={"in": (13, 0), "out": (-13, 0)},
                        dirs={"in": "e", "out": "w"})


def build_diagram():
    """构建参考图对应的 EVI 经济器回路。"""
    d = Diagram(width=1000, height=760)

    comp = d.add(_horizontal_compressor(), None, loc=(760, 155))
    cond = d.add(make_heat_exchanger(190, 60, shape="rect_x", name="冷凝器"),
                 None, loc=(500, 90))
    evap = d.add(make_heat_exchanger(200, 60, shape="rect_x", name="蒸发器"),
                 None, loc=(500, 665))
    # 四口普通换热器:主路上下贯通,喷气支路左右贯通。
    economizer = d.add(make_heat_exchanger(80, 180, shape="rect_zigzag7",
                                           name="经济器"),
                       None, loc=(300, 390))
    eev1 = d.add(make_expansion_valve_x(r=13, orient="v", name="EEV1"),
                 None, loc=(150, 225))
    eev2 = d.add(make_expansion_valve_x(r=13, orient="v", name="EEV2"),
                 None, loc=(300, 535))
    eev1_side = d.add(_westward_valve(), None, loc=(150, 225))

    # 只保留一个阀体: eev1_side 复用反向端口,删除上面的临时节点。
    d._nodes.remove(eev1)
    eev1 = eev1_side

    # 标题与设备标签。
    d.text(500, 26, "EVI 喷气增焓循环（竖直经济器排布）", size=20,
           weight="bold")
    d.text(500, 54, "主路：经济器上进下出  ·  喷气支路：左进右出",
           size=11)
    d.text(500, 58, "")
    d.text(500, 122, "冷凝器", size=16)
    d.text(760, 242, "压缩机", size=16, ha="center")
    d.text(500, 718, "蒸发器", size=16)
    d.text(300, 390, "经济器", size=15, rot=90, boxed=True)
    d.text(94, 184, "EEV1\n喷气支路", size=12, ha="right", boxed=True)
    d.text(330, 535, "EEV2\n主路膨胀", size=12, ha="left", boxed=True)

    split = (850, 250)

    # 压缩机排气 → 冷凝器,冷凝器出口再向下到分流点。
    d.pipe(comp["right"], cond["right"], via=[(850, 90)],
           head_at=(0.55,))
    d.pipe(cond["left"], split, via=[(850, 90)], head_at=(0.68,))
    d.ax.add_patch(Circle(split, 4, facecolor="black", edgecolor="none",
                          zorder=6))
    d.text(870, 232, "分流点", size=10, ha="left")

    # 主路:分流点 → 经济器顶部 → 底部 → EEV2 → 蒸发器左口。
    d.pipe(split, economizer["top"], via=[(300, 250)],
           head_at=(0.5,))
    d.pipe(economizer["bottom"], eev2["in"], head_at=(0.5,))
    d.pipe(eev2["out"], evap["left"], via=[(300, 665)],
           head_at=(0.65,))

    # 蒸发器右口 → 压缩机左口吸气。
    d.pipe(evap["right"], comp["left"], via=[(650, 665), (650, 155)],
           head_at=(0.35, 0.82))

    # 喷气支路:分流点 → EEV1 → 经济器左口 → 右口 → 压缩机底部补气。
    d.pipe(split, eev1["in"], via=[(150, 250)], head_at=(0.45,))
    d.pipe(eev1["out"], economizer["left"],
           via=[(150, 390)], head_at=(0.55,))
    d.pipe(economizer["right"], comp["bottom"],
           via=[(450, 390), (450, 250), (760, 250)],
           head_at=(0.65,))

    # 参考图状态点编号。
    for number, x, y in (("1", 805, 205), ("2", 720, 185),
                         ("3", 650, 185), ("4", 620, 78),
                         ("5", 790, 275), ("6", 340, 493),
                         ("7", 340, 580), ("8", 116, 288),
                         ("9", 690, 238)):
        d.text(x, y, number, size=14)

    d.text(500, 744, "主路：冷凝器出口分流 → 经济器上口 → 下口 → EEV2 → 蒸发器",
           size=10, color="#555555")
    return d


if __name__ == "__main__":
    use_font()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "evi_economizer_cycle.png")
    with build_diagram() as diagram:
        diagram.save(out, out.replace(".png", ".svg"), dpi=140)
    print("已生成:", out)
