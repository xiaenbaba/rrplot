# -*- coding: utf-8 -*-
"""经济器 rect_diag 符号几何自检。

做法：把 pfd_symbols.polyline 换成记录器，直接抓取 heat_exchanger 实际
下发的折线点，再与期望的「矩形四角 + 左上→右下对角线」比对。
（schemdraw 0.23 的 Element 不暴露 abspos，故走调用记录而非元素内省。）
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import schemdraw
import pfd_symbols as P

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]

captured = []
_real = P.polyline


def recorder(d, pts, lw=P.LW, color="black"):
    captured.append([(round(x, 3), round(y, 3)) for (x, y) in pts])
    return _real(d, pts, lw=lw, color=color)


P.polyline = recorder

cx, cy, w, h = 1.35, 3.70, 1.30, 2.20
rx, ry = w / 2.0, h / 2.0
exp_rect = [(cx - rx, cy - ry), (cx + rx, cy - ry), (cx + rx, cy + ry),
            (cx - rx, cy + ry), (cx - rx, cy - ry)]
exp_diag = [(cx - rx, cy + ry), (cx + rx, cy - ry)]

with schemdraw.Drawing(show=False) as d:
    d.config(fontsize=15)
    P.heat_exchanger(d, cx, cy, w, "经济器", shape="rect_diag", w=w, h=h)

P.polyline = _real

print("期望矩形角点:", [(round(a, 3), round(b, 3)) for a, b in exp_rect])
print("期望对角线  :", [(round(a, 3), round(b, 3)) for a, b in exp_diag])
print("实际折线：")
for p in captured:
    print("   ", p)

n_int = sum(1 for p in captured if len(p) > 2)
print("线段数(应为2: 1矩形框 + 1对角线) =", len(captured), "| 含盘管的折线数(应为0) =", n_int)
print("矩形框 OK:", any(len(p) == 5 and p == [(round(a, 3), round(b, 3)) for a, b in exp_rect] for p in captured))
print("对角线 OK:", any(len(p) == 2 and p == [(round(a, 3), round(b, 3)) for a, b in exp_diag] for p in captured))
print("对角线方向 左上->右下 OK:", any(len(p) == 2 and p[0][1] > p[1][1] and p[0][0] < p[1][0] for p in captured))
