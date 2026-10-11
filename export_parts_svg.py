# -*- coding: utf-8 -*-
"""把 cycleplot.parts 里的全部图元各自导出为一张独立 SVG 到 SVG/。

每张 SVG 按部件实际外形紧裁(bbox_inches="tight"),可直接单张拷进论文/PPT。
覆盖三类:
  1) parts 模块内所有 Part 实例(压缩机默认型除外,它由下变体组代表);
  2) make_compressor 的 7 种型式变体;
  3) make_heat_exchanger 的 5 种换热面变体。

用法:
    python export_parts_svg.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib.pyplot as plt
from cycleplot import Diagram, parts, use_font
from cycleplot.parts import (COMPRESSOR_STYLES, HEX_SHAPES, Part,
                             make_compressor, make_heat_exchanger)

CANVAS = 600                     # 部件居中放置,紧裁后无留白
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SVG")


def export(part, label, fname):
    d = Diagram(width=CANVAS, height=CANVAS)
    d.add(part, label, loc=(CANVAS / 2, CANVAS / 2))
    path = os.path.join(OUT, fname)
    d.save(path, tight=True)
    plt.close(d.fig)
    print("  已导出:", fname)


COMPRESSOR_CN = {"centrifugal": "离心式", "rotor": "通用旋转式",
                 "axial": "轴流式", "recip": "往复式", "screw": "螺杆式",
                 "scroll": "涡旋式", "chord": "涡旋式(简化)"}
HEX_CN = {"circle": "圆壳之字", "rect": "矩形之字", "rect_diag": "矩形对角",
          "rect_zigzag": "蛇形盘管", "rect_zigzag7": "7点之字"}


def main():
    os.makedirs(OUT, exist_ok=True)
    use_font()

    print("[1/3] parts 模块实例图元")
    for name, obj in vars(parts).items():
        if not isinstance(obj, Part) or name.startswith("_"):
            continue
        if name == "compressor":
            continue                    # 由 compressor__centrifugal 代表
        export(obj, obj.name, f"{name}.svg")

    print("[2/3] 压缩机 7 种型式")
    for s in COMPRESSOR_STYLES:
        p = make_compressor(r=95, style=s, name=f"压缩机({s})")
        export(p, COMPRESSOR_CN[s], f"compressor__{s}.svg")

    print("[3/3] 换热器 5 种换热面")
    for sh in HEX_SHAPES:
        p = make_heat_exchanger(shape=sh, name=f"换热器({sh})")
        export(p, HEX_CN[sh], f"heat_exchanger__{sh}.svg")

    files = sorted(f for f in os.listdir(OUT) if f.endswith(".svg"))
    print(f"\n完成,共 {len(files)} 个 SVG,目录: {OUT}")


if __name__ == "__main__":
    main()
