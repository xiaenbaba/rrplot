# -*- coding: utf-8 -*-
"""底层绘制原语:文本、折线、箭头。parts 与 core 共用。"""
from .style import FONT_STACK, LINE


def txt(ax, x, y, s, size=18, ha="center", va="center", weight="normal",
        rot=0, color=LINE, boxed=False):
    """写一段文本;boxed=True 时垫一层白底,压在管线上也可读。"""
    kw = {}
    if boxed:
        kw["bbox"] = dict(facecolor="white", edgecolor="none", pad=1.5)
    ax.text(x, y, s, fontsize=size, fontfamily=FONT_STACK, ha=ha, va=va,
            color=color, fontweight=weight, rotation=rot, **kw)


def line(ax, pts, lw=1.0, color=LINE):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=color, lw=lw, solid_capstyle="round",
            solid_joinstyle="round")


def arrow(ax, x1, y1, x2, y2, size=8, lw=0.9, color=LINE):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", lw=lw, color=color,
                                mutation_scale=size))
