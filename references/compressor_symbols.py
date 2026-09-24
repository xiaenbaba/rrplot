# -*- coding: utf-8 -*-
"""
压缩机型式符号对照图（PFD 简化画法）
================================================
把 pfd_symbols.compressor() 的 6 种 style 排成 2×3 对照，用于选型画图时挑符号。

依赖：schemdraw>=0.23, matplotlib, pfd_symbols.py（同目录）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import schemdraw
from pfd_symbols import *

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

R = 1.00
DX = 3.40          # 列间距
DY = 3.30          # 行间距


def build(outfile="compressor_symbols"):
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=FS_LABEL)

        cols = (2.0, 2.0 + DX, 2.0 + 2 * DX)
        rows = (0.0, -DY)

        items = [
            (cols[0], rows[0], "centrifugal", "离心式"),
            (cols[1], rows[0], "rotor",       "通用旋转式"),
            (cols[2], rows[0], "axial",       "轴流式"),
            (cols[0], rows[1], "recip",       "往复式"),
            (cols[1], rows[1], "screw",       "螺杆式"),
            (cols[2], rows[1], "scroll",      "涡旋式"),
        ]

        for (cx, cy, style, tag) in items:
            compressor(d, cx, cy, R, tag=tag, style=style,
                       tag_xy=(cx, cy - R - 0.55))

        d.save(outfile + ".png", dpi=220)
        d.save(outfile + ".svg")
    print("saved:", outfile + ".png", outfile + ".svg")


if __name__ == "__main__":
    build()
