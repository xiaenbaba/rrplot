# -*- coding: utf-8 -*-
"""涡旋压缩机 + 过冷器(经济器) 制冷循环示意图

状态点编号:
  1  压缩机吸气        4  压缩机排气 -> 冷凝器
  5  冷凝器出口/过冷器进口(分流点)
  6  过冷器主路出口 -> 膨胀阀
  7  膨胀阀出口 -> 蒸发器
  8  膨胀器出口 -> 过冷器底部(补气支路)
  9  过冷器补气出口 -> 电磁阀 -> 压缩机补气口
"""
import os

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Circle, Polygon, Rectangle, Wedge

# ---------- 中文字体 ----------
FONT_CANDIDATES = [
    "Microsoft YaHei", "SimHei", "DengXian", "SimSun",
    "Microsoft JhengHei", "Noto Sans CJK SC",
    "Source Han Sans SC", "WenQuanYi Zen Hei", "Arial Unicode MS",
]
_installed = {f.name for f in fm.fontManager.ttflist}
FONT = next((c for c in FONT_CANDIDATES if c in _installed), "DejaVu Sans")
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = [FONT, "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
print("使用字体：", FONT)

# ---------- 画布 ----------
W, H = 880, 740
fig, ax = plt.subplots(figsize=(W / 100, H / 100), dpi=100)
ax.set_xlim(0, W)
ax.set_ylim(H, 0)          # y 向下, 便于按参考图坐标直接布局
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("white")

BLACK = "#000000"
LW = 2.5
NUM = 30                   # 状态点编号字号


def txt(x, y, s, size=28, ha="center", va="center", rot=0):
    ax.text(x, y, s, fontsize=size, fontfamily=FONT, ha=ha, va=va,
            color=BLACK, rotation=rot)


def num(x, y, s):
    txt(x, y, s, size=NUM)


def line(pts, lw=LW):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=BLACK, lw=lw,
            solid_capstyle="round", solid_joinstyle="round")


def arrow(x1, y1, x2, y2, size=22, lw=2.2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", lw=lw,
                                color=BLACK, mutation_scale=size))


def valve(x, y, w=64, h=48):
    """蝶形阀符号(两个对顶三角形) + 顶部圆冠"""
    ax.add_patch(Polygon([(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x, y)],
                         closed=True, facecolor="white",
                         edgecolor=BLACK, lw=LW))
    ax.add_patch(Polygon([(x - w / 2, y + h / 2), (x + w / 2, y + h / 2), (x, y)],
                         closed=True, facecolor="white",
                         edgecolor=BLACK, lw=LW))
    line([(x, y - h / 2), (x, y - h / 2 - 12)], lw=2.2)
    ax.add_patch(Wedge((x, y - h / 2 - 12), 12, 0, 180,
                       facecolor="white", edgecolor=BLACK, lw=2.2))


def square_wave(x0, x1, y, amp=25, n=6):
    """方波, 表示过冷器内部换热面"""
    seg = (x1 - x0) / n
    xs, ys, x = [x0], [y], x0
    for i in range(n):
        yv = y - amp if i % 2 == 0 else y + amp
        xs.append(x)
        ys.append(yv)
        x += seg
        xs.append(x)
        ys.append(yv)
    xs.append(x)
    ys.append(y)
    ax.plot(xs, ys, color=BLACK, lw=2.2)


# =========================
# 部件
# =========================
# --- 涡旋压缩机 ---
CC, CR = (310, 110), 95
ax.add_patch(Circle(CC, CR, facecolor="white", edgecolor=BLACK, lw=LW))
line([(219, 92), (401, 78)], lw=2.2)      # 上涡旋线
line([(219, 148), (399, 138)], lw=2.2)    # 下涡旋线
txt(402, 162, "涡旋压缩机", ha="left")
num(200, 68, "1")
num(186, 130, "2")
num(388, 120, "3")
num(398, 60, "4")
num(266, 188, "9")

# --- 冷凝器 ---
ax.add_patch(Rectangle((505, 52), 205, 86,
                       facecolor="white", edgecolor=BLACK, lw=LW))
txt(607, 95, "冷凝器")
arrow(404, 95, 500, 95)                   # 排气 -> 冷凝器

# --- 蒸发器 ---
ax.add_patch(Rectangle((65, 210), 75, 190,
                       facecolor="white", edgecolor=BLACK, lw=LW))
txt(102, 305, "蒸\n发\n器")

# --- 过冷器 ---
ax.add_patch(Rectangle((440, 450), 260, 110,
                       facecolor="white", edgecolor=BLACK, lw=LW))
square_wave(458, 682, 505, amp=25, n=6)
txt(655, 428, "过冷器")

# --- 阀件 ---
valve(288, 505)                           # 膨胀阀
txt(288, 556, "膨胀阀")
valve(505, 375)                           # 电磁阀
txt(556, 372, "电磁阀", ha="left")
valve(672, 660)                           # 膨胀器
txt(700, 585, "膨胀器")

# =========================
# 管路
# =========================
# 蒸发器 -> 压缩机吸气
line([(102, 210), (102, 95), (216, 95)])
arrow(102, 200, 102, 150)

# 冷凝器 -> 右侧下行总管
line([(710, 95), (790, 95), (790, 660)])
arrow(790, 270, 790, 320)
arrow(790, 580, 790, 630)

# 5: 总管 -> 过冷器 主路进口
line([(790, 505), (700, 505)])
arrow(742, 505, 706, 505)
num(770, 483, "5")

# 过冷器 -> 膨胀阀 -> 蒸发器
line([(440, 505), (320, 505)])
num(418, 483, "6")
line([(256, 505), (102, 505), (102, 400)])
num(228, 483, "7")
arrow(205, 505, 170, 505)

# 8: 总管 -> 膨胀器 -> 过冷器底部(补气支路)
line([(790, 660), (704, 660)])
line([(640, 660), (560, 660), (560, 560)])
num(598, 632, "8")

# 9: 过冷器补气出口 -> 电磁阀 -> 压缩机补气口
line([(505, 450), (505, 399)])
line([(473, 375), (285, 375), (285, 202)])
arrow(285, 290, 285, 240)

# =========================
# 输出
# =========================
BASE = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(BASE, "涡旋压缩机循环示意图.png")
plt.tight_layout(pad=0)
plt.savefig(PNG, dpi=100, bbox_inches="tight", pad_inches=0.05)
plt.show()
print("已生成图片：", PNG)
