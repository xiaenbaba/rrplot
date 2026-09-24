# -*- coding: utf-8 -*-
"""
制冷循环系统原理图（流程图）生成器 —— 标准 PFD 符号版
================================================
闪发罐（Flash Tank）双级压缩循环，全部设备采用 ISA-5.1 / ISO 10628
标准 PFD 符号（符号定义见 pfd_symbols.py）：

    冷凝器 -> EEV1 -> 闪发罐(气液分离)
        闪发罐顶部闪发气体  -> 高/低压级之间(高压级吸气)
        闪发罐底部液体      -> EEV2 -> 蒸发器
    蒸发器 -> 低压级压缩机 -> 高压级压缩机 -> 冷凝器

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


def build(outfile="refcycle_flashtank", cycle_label="闪发罐双级压缩循环"):
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=FS_LABEL)

        # ---- 关键坐标 ----
        ev_x, ev_y = 4.10, 0.00          # 蒸发器中心
        cd_x, cd_y = 4.10, 8.10          # 冷凝器中心
        cp_x, cp_r = 8.90, 1.05          # 两台压缩机共用的 x / 半径
        cp1_y, cp2_y = 2.95, 6.50        # 低压级 / 高压级中心高度
        ft_x, ft_y = 1.35, 3.75          # 闪发罐中心
        ft_w, ft_h = 1.10, 2.40
        v1_y, v2_y = 6.50, 1.70          # 两个 EEV 中心高度
        T_y = 4.30                       # 闪发气体接入两级之间的高度（须落在罐体壁面段）

        hx_r = 1.20                      # 换热器（冷凝/蒸发）圆半径
        v_half = 0.46

        ft_rx = ft_w / 2
        ft_top = ft_y + ft_h / 2
        ft_bot = ft_y - ft_h / 2

        # ---- 设备（标准 PFD 符号，冷凝/蒸发器用矩形）----
        heat_exchanger(d, cd_x, cd_y, hx_r, "冷凝器", shape="rect",
                       w=2 * hx_r, h=2 * hx_r)
        heat_exchanger(d, ev_x, ev_y, hx_r, "蒸发器", label_above=True,
                       shape="rect", w=2 * hx_r, h=2 * hx_r)
        vessel(d, ft_x, ft_y, ft_w, ft_h, "闪发罐",
               tag_xy=(ft_x + ft_w / 2 + 0.95, ft_y - 0.40))   # 避开顶部补气管
        valve(d, ft_x, v1_y)
        valve(d, ft_x, v2_y)
        compressor(d, cp_x, cp1_y, cp_r, "低压级压缩机",
                   tag_xy=(cp_x - 2.55, cp1_y), style="centrifugal")
        compressor(d, cp_x, cp2_y, cp_r, "高压级压缩机",
                   tag_xy=(cp_x - 2.55, cp2_y), style="centrifugal")

        text(d, ft_x + 1.05, v1_y, r"EEV$_1$", fs=FS_LABEL)
        text(d, ft_x + 1.05, v2_y, r"EEV$_2$", fs=FS_LABEL)

        # ---- 管路 ----
        # 1) 冷凝器 -> 左行 -> 下行 -> EEV1（接入点改到阀中心，消除悬空断点）
        flow(d, [(cd_x - hx_r, cd_y), (ft_x, cd_y), (ft_x, v1_y)])
        # 2) EEV1 -> 闪发罐（顶部进液）
        flow(d, [(ft_x, v1_y), (ft_x, ft_top)])
        # 3) 闪发罐顶部闪发气体 -> 两级压缩机之间的吸气混合点
        flow(d, [(ft_x + ft_rx, T_y), (cp_x, T_y)])
        # 4) 闪发罐底部出液 -> EEV2（接入点改到阀中心）
        flow(d, [(ft_x, ft_bot), (ft_x, v2_y)])
        # 5) EEV2 -> 下行 -> 右行 -> 蒸发器
        flow(d, [(ft_x, v2_y), (ft_x, ev_y), (ev_x - hx_r, ev_y)])
        # 6) 蒸发器 -> 右行 -> 上行 -> 低压级压缩机吸气
        flow(d, [(ev_x + hx_r, ev_y), (cp_x, ev_y), (cp_x, cp1_y - cp_r)])
        # 7) 低压级排气 -> 高压级吸气（两级之间的中间管路，闪发气体在此汇入）
        flow(d, [(cp_x, cp1_y + cp_r), (cp_x, cp2_y - cp_r)])
        # 8) 高压级排气 -> 上行 -> 左行 -> 冷凝器
        flow(d, [(cp_x, cp2_y + cp_r), (cp_x, cd_y), (cd_x + hx_r, cd_y)])

        # ---- 状态点编号（可选，与 rrprop / CoolProp 状态点对应）----
        # 1: 蒸发器出口(低压级吸气)  2: 低压级排气(中间压力)
        # 3: 混合点(高压级吸气)      4: 高压级排气
        # 5: 冷凝器出口(高压液体)    6: EEV1后(进闪发罐,两相)
        # 7: 闪发罐出液(EEV2前)      8: EEV2后(进蒸发器,两相)
        # for tag, (px, py) in {"1": (ev_x + hx_r + 0.35, ev_y),
        #                       "2": (cp_x + 0.35, cp1_y + cp_r),
        #                       "3": (cp_x + 0.35, T_y),
        #                       "4": (cp_x + 0.35, cp2_y + cp_r),
        #                       "5": (cd_x - hx_r - 0.35, cd_y),
        #                       "6": (ft_x - 0.35, ft_top + 0.20),
        #                       "7": (ft_x - 0.35, ft_bot - 0.20),
        #                       "8": (ft_x + ft_rx + 0.30, T_y)}.items():
        #     text(d, px, py, tag, fs=FS_TAG, color="#c0392b")

        d.save(outfile + ".png", dpi=220)
        d.save(outfile + ".svg")
    print("saved:", outfile + ".png", outfile + ".svg")


if __name__ == "__main__":
    build()
