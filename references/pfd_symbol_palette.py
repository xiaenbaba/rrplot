# -*- coding: utf-8 -*-
"""
标准 PFD 符号总览（ISA-5.1 / ISO 10628 风格）
================================================
把 pfd_symbols.py 里的标准符号排成一行，供核对 / 挑用。

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


def build(outfile="pfd_symbol_palette"):
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=FS_LABEL)

        ly = -1.80        # 行内标签基线（相对行中心）

        # ---- 第一行：压缩机两种画法 + 阀 + 换热器 ----
        r0 = 0.0
        compressor(d, 2.40, r0, 1.00, tag="离心式压缩机",
                   tag_xy=(2.40, r0 + ly), style="centrifugal")
        compressor(d, 5.60, r0, 1.00, tag="通用旋转式",
                   tag_xy=(5.60, r0 + ly), style="rotor")
        valve(d, 8.80, r0, 1.10, 1.10)
        text(d, 8.80, r0 + ly, "阀 / EEV", fs=FS_LABEL)
        heat_exchanger(d, 12.00, r0, 1.00, "换热器·圆+盘管", tag_xy=(12.00, r0 + ly))

        # ---- 第二行：容器 + 板换 + 泵 ----
        r1 = -4.15
        vessel(d, 2.40, r1, 1.30, 2.20, "立式容器 / 闪发罐", tag_xy=(2.40, r1 + ly))
        plate_hex(d, 5.60, r1, 1.30, 2.20, "板式换热器", tag_xy=(5.60, r1 + ly))
        pump(d, 8.80, r1, 1.00, tag="泵", tag_xy=(8.80, r1 + ly))

        # ---- 第三行：换热器三种形态（shape 参数对照）----
        r2 = -8.30
        heat_exchanger(d, 2.40, r2, 1.00, "换热器·圆+盘管",
                       tag_xy=(2.40, r2 + ly), shape="circle")
        heat_exchanger(d, 5.60, r2, 1.00, "换热器·矩形+盘管",
                       tag_xy=(5.60, r2 + ly), shape="rect", w=2.2, h=2.2)
        heat_exchanger(d, 8.80, r2, 1.00, "经济器·矩形+对角线",
                       tag_xy=(8.80, r2 + ly), shape="rect_diag", w=1.30, h=2.20)

        d.save(outfile + ".png", dpi=220)
        d.save(outfile + ".svg")
    print("saved:", outfile + ".png", outfile + ".svg")


if __name__ == "__main__":
    build()
