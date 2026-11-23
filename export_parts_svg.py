# -*- coding: utf-8 -*-
"""把 rrplot.parts 里的全部图元各自导出为一张独立 SVG 到 SVG/。

每张 SVG 按部件实际外形紧裁(bbox_inches="tight"),可直接单张拷进论文/PPT。
覆盖三类:
  1) parts 模块内所有 Part 实例(压缩机默认型除外,它由下变体组代表);
  2) make_compressor 的全部机身变体;
  3) make_heat_exchanger 的全部换热面变体。

用法:
    python export_parts_svg.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from rrplot import Diagram, parts, use_font  # noqa: E402
from rrplot.parts import (  # noqa: E402
    COMPRESSOR_STYLES,
    HEX_SHAPES,
    Part,
    make_compressor,
    make_heat_exchanger,
)

CANVAS = 600                     # 部件居中放置,紧裁后无留白
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SVG")

HEX_CN = {
    "rect_diag": "矩形对角",
    "rect_x": "矩形对角X",
    "rect_zigzag7": "7点之字",
    "fan_coil": "风机盘管",
}


def export(part, label, fname):
    with Diagram(width=CANVAS, height=CANVAS) as d:
        d.add(part, label, loc=(CANVAS / 2, CANVAS / 2))
        path = os.path.join(OUT, fname)
        d.save(path, tight=True)
    print("  已导出:", fname)
    return fname


def main():
    os.makedirs(OUT, exist_ok=True)
    use_font()
    exported = set()

    print("[1/3] parts 模块实例图元")
    for name, obj in sorted(vars(parts).items()):
        if not isinstance(obj, Part) or name.startswith("_"):
            continue
        if name == "compressor":
            continue                    # 由压缩机各 style 代表
        exported.add(export(obj, obj.name, f"{name}.svg"))

    print(f"[2/3] 压缩机 {len(COMPRESSOR_STYLES)} 种机身")
    for s in COMPRESSOR_STYLES:
        p = make_compressor(r=95, style=s, name=f"压缩机({s})")
        exported.add(export(p, s, f"compressor__{s}.svg"))

    print(f"[3/3] 换热器 {len(HEX_SHAPES)} 种换热面")
    for sh in HEX_SHAPES:
        p = make_heat_exchanger(shape=sh, name=f"换热器({sh})")
        exported.add(export(p, HEX_CN.get(sh, sh), f"heat_exchanger__{sh}.svg"))

    for stale in sorted(f for f in os.listdir(OUT) if f.endswith(".svg")):
        if stale not in exported:
            os.remove(os.path.join(OUT, stale))
            print("  已清理过期文件:", stale)

    files = sorted(f for f in os.listdir(OUT) if f.endswith(".svg"))
    print(f"\n完成,共 {len(files)} 个 SVG,目录: {OUT}")


if __name__ == "__main__":
    main()
