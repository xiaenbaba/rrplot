# -*- coding: utf-8 -*-
"""
制冷循环系统原理图（流程图）生成器 —— 标准 PFD 符号版
================================================
经济器（Economizer / EVI 喷气增焓）双 EEV 循环，全部设备采用
ISA-5.1 / ISO 10628 标准 PFD 符号（符号定义见 pfd_symbols.py）：

    冷凝器 -> EEV1 -> 经济器(气液分离) -> EEV2 -> 蒸发器 -> 压缩机 -> 冷凝器
                  经济器闪发气体 -> 压缩机补气口(中间压力)

依赖：schemdraw>=0.23, matplotlib, pfd_symbols.py（同目录）
输出：PNG / SVG / PDF，矢量可进论文、PPT。
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


def build(outfile="refcycle_schematic", cycle_label="EVI 经济器双级节流循环"):
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=FS_LABEL)

        # ---- 关键坐标 ----
        ev_x, ev_y = 4.10, 0.00          # 蒸发器中心
        cd_x, cd_y = 4.10, 7.20          # 冷凝器中心
        cp_x, cp_y, cp_r = 8.70, 5.20, 1.30   # 压缩机
        ec_x, ec_y = 1.35, 3.70          # 经济器（板式换热器）中心
        v1_y, v2_y = 6.10, 1.75          # 两个 EEV 中心高度

        hx_r = 1.20                      # 冷凝/蒸发器圆半径
        econ_w, econ_h = 1.30, 2.20      # 经济器矩形（竖长，左上→右下对角线）
        v_half = 0.46

        # ---- 设备（标准 PFD 符号，换热器统一矩形）----
        heat_exchanger(d, cd_x, cd_y, hx_r, "冷凝器", shape="rect",
                       w=2 * hx_r, h=2 * hx_r)
        heat_exchanger(d, ev_x, ev_y, hx_r, "蒸发器", label_above=True,
                       shape="rect", w=2 * hx_r, h=2 * hx_r)
        heat_exchanger(d, ec_x, ec_y, econ_w, "经济器",
                       tag_xy=(ec_x + econ_w / 2 + 1.05, ec_y - 0.55),  # 避开补气管
                       shape="rect_diag", w=econ_w, h=econ_h)
        valve(d, ec_x, v1_y)
        valve(d, ec_x, v2_y)
        compressor(d, cp_x, cp_y, cp_r, tag_xy=(cp_x - 1.95, cp_y + 1.05),
                   style="centrifugal")

        text(d, ec_x + 1.05, v1_y, r"EEV$_1$", fs=FS_LABEL)
        text(d, ec_x + 1.05, v2_y, r"EEV$_2$", fs=FS_LABEL)

        ec_r = ec_x + econ_w / 2         # 经济器右壁
        ec_t = ec_y + econ_h / 2         # 经济器顶
        ec_b = ec_y - econ_h / 2         # 经济器底

        # ---- 管路 ----
        # 1) 冷凝器 -> 左行 -> 下行 -> EEV1（接入点改到阀中心，消除悬空断点）
        flow(d, [(cd_x - hx_r, cd_y), (ec_x, cd_y), (ec_x, v1_y)])
        # 2) EEV1 -> 经济器（进液）
        flow(d, [(ec_x, v1_y), (ec_x, ec_t)])
        # 3) 经济器闪发气体 -> 压缩机补气口（中间压力）
        #    经济器为竖长矩形，闪发气体从右壁定值接入；压缩机仍用弦长公式求左壁
        y_inj = ec_y + 0.50
        x_out = ec_x + econ_w / 2                              # 经济器矩形右壁
        x_hit = cp_x - (cp_r ** 2 - (y_inj - cp_y) ** 2) ** 0.5     # 压缩机圆左壁
        flow(d, [(x_out, y_inj), (x_hit - 0.02, y_inj)])
        # 4) 经济器底部出液 -> EEV2（接入点改到阀中心）
        flow(d, [(ec_x, ec_b), (ec_x, v2_y)])
        # 5) EEV2 -> 下行 -> 右行 -> 蒸发器
        flow(d, [(ec_x, v2_y), (ec_x, ev_y), (ev_x - hx_r, ev_y)])
        # 6) 蒸发器 -> 右行 -> 上行 -> 压缩机吸气
        flow(d, [(ev_x + hx_r, ev_y), (cp_x, ev_y), (cp_x, cp_y - cp_r)])
        # 7) 压缩机排气 -> 上行 -> 左行 -> 冷凝器
        flow(d, [(cp_x, cp_y + cp_r), (cp_x, cd_y), (cd_x + hx_r, cd_y)])

        # ---- 状态点编号（可选，与 rrprop / CoolProp 状态点对应）----
        # for tag, (px, py) in {"1": (ev_x + hx_r + 0.35, ev_y),
        #                       "2": (cp_x + 0.35, cp_y + cp_r),
        #                       "3": (cd_x - hx_r - 0.35, cd_y),
        #                       "4": (ec_x - 0.35, ec_t + 0.25),
        #                       "5": (ec_r + 0.30, y_inj)}.items():
        #     text(d, px, py, tag, fs=FS_TAG, color="#c0392b")

        d.save(outfile + ".png", dpi=220)
        d.save(outfile + ".svg")
    print("saved:", outfile + ".png", outfile + ".svg")


if __name__ == "__main__":
    build()
