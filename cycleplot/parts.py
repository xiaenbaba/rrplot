# -*- coding: utf-8 -*-
"""部件库:每个部件是一个绘制函数(以中心为锚点)+ 端口定义。

端口 ports: 名称 -> (dx, dy),相对部件锚点的偏移。dx/dy 同时隐含接管方向
(单轴端口取该轴符号;双轴非零的端口需要显式方向,见 Part.port_dir)。

命名约定:贯通式两口元件(阀、过滤器、毛细管等)用 in/out;
多口/换热类部件用 left/right/top/bottom 表示边中点。
"""
from dataclasses import dataclass, field

import math

import numpy as np
from matplotlib.patches import (Circle, Ellipse, FancyBboxPatch, Polygon,
                                Rectangle, Wedge)

from ._primitives import line, txt
from .style import (COIL, FILL, GRID, LINE, LW_FINE, LW_OUTLINE, LW_PART,
                    LW_STRONG)

_PORT_DIR = {"n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0)}


@dataclass
class Part:
    name: str
    draw: object                       # f(ax, x, y, label=None, **kw)
    ports: dict = field(default_factory=dict)
    _dirs: dict = field(default_factory=dict)

    def port(self, key):
        try:
            return self.ports[key]
        except KeyError:
            raise KeyError(f"部件 {self.name!r} 没有端口 {key!r},"
                           f"可用端口:{', '.join(sorted(self.ports)) or '(无)'}"
                           ) from None

    def direction(self, key):
        """端口外法向单位向量,优先取显式声明。"""
        if key in self._dirs:
            return _PORT_DIR[self._dirs[key]]
        dx, dy = self.port(key)
        if dx == 0 and dy == 0:
            return (0, 0)
        if abs(dx) >= abs(dy):
            return (1 if dx > 0 else -1, 0)
        return (0, 1 if dy > 0 else -1)


def _part(name, ports, draw, dirs=None):
    return Part(name, draw, ports, dirs or {})


# =========================
# 绘制函数(中心锚点)
# =========================
def _evaporator(ax, x, y, label="蒸发器", **kw):
    ax.add_patch(Rectangle((x - 24, y - 48), 48, 96,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    for yy in np.linspace(y - 38, y + 38, 5):
        line(ax, [(x - 20, yy), (x + 20, yy)], lw=LW_FINE)
    for xx in [-12, 0, 12]:
        line(ax, [(x + xx, y - 46), (x + xx, y + 46)], lw=LW_FINE)
    line(ax, [(x - 62, y), (x - 38, y)], lw=LW_STRONG)
    ax.add_patch(Ellipse((x - 70, y), 11, 44, angle=20,
                         facecolor=FILL, edgecolor=LINE, lw=LW_FINE))
    ax.add_patch(Ellipse((x - 70, y), 11, 44, angle=-20,
                         facecolor=FILL, edgecolor=LINE, lw=LW_FINE))
    if label:
        txt(ax, x, y + 72, label, size=18)


def _separator(ax, x, y, label="气液分离器", **kw):
    ax.add_patch(FancyBboxPatch((x - 17, y - 32), 34, 64,
                                boxstyle="round,pad=0.02,rounding_size=8",
                                facecolor=FILL, edgecolor=LINE,
                                lw=LW_PART))
    for yy in np.linspace(y - 24, y + 24, 4):
        line(ax, [(x - 13, yy), (x + 13, yy)], lw=LW_FINE)
    if label:
        txt(ax, x - 30, y + 62, label, size=17, ha="right")


def _receiver(ax, x, y, label="储液器", **kw):
    ax.add_patch(FancyBboxPatch((x - 17, y - 35), 34, 70,
                                boxstyle="round,pad=0.02,rounding_size=8",
                                facecolor=FILL, edgecolor=LINE,
                                lw=LW_PART))
    for yy in np.linspace(y - 25, y + 25, 5):
        line(ax, [(x - 13, yy), (x + 13, yy)], lw=LW_FINE)
    if label:
        txt(ax, x, y - 54, label, size=17)


def _condenser(ax, x, y, label="冷凝器", **kw):
    ax.add_patch(Rectangle((x - 32, y - 80), 64, 160,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    for xx in [-20, -7, 7, 20]:
        line(ax, [(x + xx, y - 67), (x + xx, y + 67)], lw=LW_STRONG, color=COIL)
    line(ax, [(x - 32, y - 80), (x + 32, y - 80)], lw=LW_STRONG)
    line(ax, [(x - 32, y + 80), (x + 32, y + 80)], lw=LW_STRONG)
    if label:
        txt(ax, x, y + 105, label, size=18)


def _four_way_valve(ax, x, y, label="四通阀", **kw):
    ax.add_patch(Rectangle((x - 20, y - 14), 40, 28,
                           facecolor=FILL, edgecolor=LINE,
                           lw=LW_PART))
    for xx in [x - 12, x, x + 12]:
        line(ax, [(xx, y - 14), (xx, y - 25)], lw=LW_PART)
    if label:
        txt(ax, x + 36, y - 2, label, size=17, ha="left")


def _four_way_round_valve(ax, x, y, label="四通阀", r=40, mark=True, **kw):
    """四通换向阀(圆体 + 内菱形):菱形四角即四个接管口。

    top=排气(D) right=冷凝(C) bottom=蒸发(E) left=回气(S)。
    mark=True 在四端点外侧标注 D/S/C/E 口别字母。
    """
    ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=LINE,
                        lw=LW_PART))
    ax.add_patch(Polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)],
                         closed=True, facecolor=FILL, edgecolor=LINE,
                         lw=LW_OUTLINE))
    if mark:
        m = r + 14
        for letter, (px, py) in (("D", (x, y - m)), ("C", (x + m, y)),
                                 ("E", (x, y + m)), ("S", (x - m, y))):
            txt(ax, px, py, letter, size=15)
    if label:
        txt(ax, x, y + r + 34, label, size=17)


def _expansion_valve(ax, x, y, label="电子膨胀阀", **kw):
    ax.add_patch(Polygon([[x - 16, y - 10], [x, y + 10], [x + 16, y - 10]],
                         closed=True, facecolor=FILL, edgecolor=LINE,
                         lw=LW_PART))
    ax.add_patch(Rectangle((x - 7, y - 25), 14, 15,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    if label:
        txt(ax, x, y + 38, label, size=17)


def _filter_drier(ax, x, y, label="干燥过滤器", **kw):
    ax.add_patch(Rectangle((x - 35, y - 18), 70, 36,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    ax.add_patch(Circle((x, y), 17, facecolor=FILL, edgecolor=LINE,
                        lw=LW_PART))
    if label:
        txt(ax, x, y + 48, label, size=17)


def _plate_hex(ax, x, y, label="板式换热器", **kw):
    ax.add_patch(Rectangle((x - 55, y - 28), 110, 56,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    for xx in np.linspace(x - 45, x + 45, 9):
        line(ax, [(xx, y - 25), (xx, y + 25)], lw=LW_PART, color=GRID)
    if label:
        txt(ax, x, y + 58, label, size=17)


def _water_tank(ax, x, y, label="水箱", **kw):
    ax.add_patch(Rectangle((x - 90, y - 125), 180, 250,
                           facecolor=FILL, edgecolor=LINE, lw=LW_STRONG))
    for yy in [y - 40, y - 20, y, y + 20, y + 40, y + 60]:
        line(ax, [(x - 87, yy), (x + 87, yy)], lw=LW_FINE, color="#888888")
    if label:
        txt(ax, x, y - 155, label, size=18)


def _flow_meter(ax, x, y, label="流量计", **kw):
    ax.add_patch(Rectangle((x - 28, y - 18), 56, 36,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    ax.add_patch(Circle((x - 10, y), 8, facecolor=FILL, edgecolor=LINE,
                        lw=LW_FINE))
    ax.add_patch(Circle((x + 10, y), 8, facecolor=FILL, edgecolor=LINE,
                        lw=LW_FINE))
    if label:
        txt(ax, x, y + 48, label, size=17)


def _valve(ax, x, y, label=None, w=64, h=48, **kw):
    """蝶形阀(两个对顶三角形)+ 顶部圆冠。"""
    ax.add_patch(Polygon([(x - w / 2, y - h / 2), (x + w / 2, y - h / 2),
                          (x, y)], closed=True, facecolor=FILL,
                         edgecolor=LINE, lw=LW_OUTLINE))
    ax.add_patch(Polygon([(x - w / 2, y + h / 2), (x + w / 2, y + h / 2),
                          (x, y)], closed=True, facecolor=FILL,
                         edgecolor=LINE, lw=LW_OUTLINE))
    line(ax, [(x, y - h / 2), (x, y - h / 2 - 12)], lw=LW_PART)
    ax.add_patch(Wedge((x, y - h / 2 - 12), 12, 0, 180,
                       facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    if label:
        txt(ax, x, y + h / 2 + 24, label)


def _globe_valve(ax, x, y, label=None, w=64, h=48, stem=26, handle=44, **kw):
    """截止阀(globe valve):左右对顶三角(沙漏) + 贯穿阀杆 + 顶部手轮横杆。

    左右竖边中点外侧各引一段接管,端口沿水平方向(in/out)。
    """
    ax.add_patch(Polygon([(x - w / 2, y - h / 2), (x - w / 2, y + h / 2),
                          (x, y)], closed=True, facecolor=FILL,
                         edgecolor=LINE, lw=LW_OUTLINE))
    ax.add_patch(Polygon([(x + w / 2, y - h / 2), (x + w / 2, y + h / 2),
                          (x, y)], closed=True, facecolor=FILL,
                         edgecolor=LINE, lw=LW_OUTLINE))
    top = y - h / 2 - stem
    line(ax, [(x, y + h / 2), (x, top)], lw=LW_PART)      # 贯穿阀杆
    line(ax, [(x - handle / 2, top), (x + handle / 2, top)],
         lw=LW_STRONG)                                     # 手轮横杆
    line(ax, [(x - w / 2, y), (x - w / 2 - 12, y)], lw=LW_STRONG)
    line(ax, [(x + w / 2, y), (x + w / 2 + 12, y)], lw=LW_STRONG)
    if label:
        txt(ax, x, y + h / 2 + 24, label)


def _solenoid_valve(ax, x, y, label=None, r=34, stem=20, handle=40, **kw):
    """电磁阀(solenoid valve):圆体 + 圆内 X(阀芯) + 顶部电磁引线与横杠。

    X 为圆内接正方形对角线,两端落在圆周上;竖引线自圆心向上出圆,
    顶端接水平横杠表示电磁线圈。端口在圆左右水平方向(in/out)。
    """
    ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=LINE,
                        lw=LW_OUTLINE))
    c = r / math.sqrt(2)
    line(ax, [(x - c, y - c), (x + c, y + c)], lw=LW_PART)
    line(ax, [(x + c, y - c), (x - c, y + c)], lw=LW_PART)
    top = y - r - stem
    line(ax, [(x, y), (x, top)], lw=LW_PART)                  # 电磁引线
    line(ax, [(x - handle / 2, top), (x + handle / 2, top)],
         lw=LW_STRONG)                                        # 线圈横杠
    line(ax, [(x - r, y), (x - r - 12, y)], lw=LW_STRONG)
    line(ax, [(x + r, y), (x + r + 12, y)], lw=LW_STRONG)
    if label:
        txt(ax, x, y + r + 26, label)


def _bowtie_valve(ax, x, y, label=None, w=76, h=44, actuator="none",
                  stem=14, dome_r=21, sol_len=62, **kw):
    """对顶三角阀(参考图画法):两竖边三角相对,阀杆自中心引出。

    actuator: "none"     裸阀(通用截断阀符号)
              "dome"     顶部闭合半圆穹顶(热力膨胀阀 / 经济器膨胀器)
              "solenoid" 电磁线圈(横杆 + Σ 折线)
    """
    for s in (-1, 1):
        ax.add_patch(Polygon(
            [(x + s * w / 2, y - h / 2), (x + s * w / 2, y + h / 2),
             (x, y)], closed=True, facecolor=FILL, edgecolor=LINE,
            lw=LW_OUTLINE))
    if actuator == "dome":
        base = y - h / 2 - stem
        line(ax, [(x, y), (x, base)], lw=LW_PART)
        pts = [(x + dome_r * math.cos(math.radians(a)),
                base - dome_r * math.sin(math.radians(a)))
               for a in range(0, 181, 6)]
        line(ax, pts + [(x + dome_r, base)], lw=LW_PART)      # 闭合平底
    elif actuator == "solenoid":
        line(ax, [(x, y), (x, y - sol_len)], lw=LW_PART)           # 阀杆
        bar = y - 26
        line(ax, [(x - 26, bar), (x + 22, bar)], lw=LW_PART)       # 线圈横杆
        line(ax, [(x - 26, bar), (x - 7, bar - 20), (x + 8, bar - 20)],
             lw=LW_PART)                                           # Σ 折线
    if label:
        txt(ax, x, y + h / 2 + 26, label)


# =========================
# 标准 PFD 符号(ISA-5.1 / ISO 10628 风格)
# 由 references/pfd_symbols.py 移植,坐标系统一为 y 向下
# =========================
COMPRESSOR_STYLES = ("centrifugal", "rotor", "axial", "recip", "screw",
                     "scroll", "chord")


def _compressor(ax, x, y, label="压缩机", r=95, style="centrifugal",
                n_blades=3, label_offset=None, label_ha="center", **kw):
    """压缩机:圆形壳体 + 内部型式标记。

    style ∈ COMPRESSOR_STYLES:
      centrifugal 离心式:两条对称弦线,上端靠内、下端外张,端点精确落在圆周上
      rotor       通用旋转式:n_blades 条转子辐线
      axial       轴流式:环形分布斜叶片
      recip       往复式:活塞矩形 + 连杆 + 曲柄销
      screw       螺杆式:两个相切内圆(8 字形啮合转子)
      scroll      涡旋式:阿基米德螺线
      chord       涡旋式(参考图简化):两条左张右收的收敛弦线
    """
    if style not in COMPRESSOR_STYLES:
        raise ValueError(f"未知压缩机 style={style!r},可用:"
                         f"{', '.join(COMPRESSOR_STYLES)}")
    ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=LINE, lw=LW_OUTLINE))

    if style == "centrifugal":
        # 用 x²+y²=r² 反解 y,保证弦的上下两端都落在圆周上
        for s in (-1.0, 1.0):
            ux = 0.40 * r
            uy = math.sqrt(r * r - ux * ux)
            lx = 0.66 * r
            ly = math.sqrt(r * r - lx * lx)
            line(ax, [(x + s * ux, y - uy), (x + s * lx, y + ly)], lw=LW_PART)
    elif style == "rotor":
        for k in range(n_blades):
            a = math.radians(90.0 + 360.0 * k / n_blades)
            ca, sa = math.cos(a), math.sin(a)
            line(ax, [(x + 0.34 * r * ca, y - 0.34 * r * sa),
                      (x + 0.96 * r * ca, y - 0.96 * r * sa)], lw=LW_PART)
    elif style == "axial":
        for k in range(5):
            a0 = math.radians(18.0 + 72.0 * k)
            a1 = a0 + math.radians(46.0)
            line(ax, [(x + 0.30 * r * math.cos(a0), y - 0.30 * r * math.sin(a0)),
                      (x + 0.90 * r * math.cos(a1), y - 0.90 * r * math.sin(a1))],
                 lw=LW_PART)
    elif style == "recip":
        pw, ph = 0.64 * r, 0.30 * r
        ax.add_patch(Rectangle((x - pw / 2, y - 0.06 * r - ph), pw, ph,
                               facecolor=FILL, edgecolor=LINE, lw=LW_PART))
        line(ax, [(x, y - 0.06 * r), (x, y + 0.66 * r)], lw=LW_PART)
        ax.add_patch(Circle((x, y + 0.80 * r), 0.14 * r, facecolor=FILL,
                            edgecolor=LINE, lw=LW_PART))
    elif style == "screw":
        cr = 0.42 * r
        for s in (-1, 1):
            ax.add_patch(Circle((x + s * cr, y), cr, facecolor=FILL,
                                edgecolor=LINE, lw=LW_PART))
    elif style == "chord":
        # 收敛双弦(参考图涡旋简化):左端张开、右端收拢,弦端落在圆周上
        for au, bu in (((-0.84, -0.57), (0.91, -0.24)),
                       ((-0.80, 0.61), (0.89, 0.27))):
            pa = (au[0] / math.hypot(*au) * r, au[1] / math.hypot(*au) * r)
            pb = (bu[0] / math.hypot(*bu) * r, bu[1] / math.hypot(*bu) * r)
            line(ax, [(x + pa[0], y + pa[1]), (x + pb[0], y + pb[1])],
                 lw=LW_PART)
    else:  # scroll
        pts = []
        n = 240
        for i in range(n + 1):
            th = 2.4 * math.pi * i / n
            rr = r * 0.16 + r * 0.66 * (th / (2.4 * math.pi))
            pts.append((x + rr * math.cos(th), y - rr * math.sin(th)))
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=LINE, lw=LW_PART, solid_capstyle="round")

    if label:
        dx, dy = label_offset if label_offset is not None else (0, r + 28)
        txt(ax, x + dx, y + dy, label, ha=label_ha)


def _dome(ax, cx, cy, rx, up=True, lw=LW_PART):
    """半圆穹顶弧(折线近似)。up=True 向上鼓(y 减小),False 向下鼓。"""
    rng = range(0, 181, 6) if up else range(180, 361, 6)
    pts = [(cx + rx * math.cos(math.radians(a)),
            cy - rx * math.sin(math.radians(a))) for a in rng]
    line(ax, pts, lw=lw)


def _vessel(ax, x, y, w=66, h=150, label="容器", liquid=0.42,
            label_offset=None, label_ha="left", **kw):
    """立式容器 / 闪发罐:矩形体 + 上下半圆穹顶(胶囊形) + 液位线。

    liquid ∈ [0,1] 控制液位相对高度(0=底, 1=顶)。
    """
    rx = w / 2
    body_top = y - h / 2 + rx
    body_bot = y + h / 2 - rx
    line(ax, [(x - rx, body_bot), (x - rx, body_top)], lw=LW_PART)
    line(ax, [(x + rx, body_bot), (x + rx, body_top)], lw=LW_PART)
    _dome(ax, x, body_top, rx, up=True)
    _dome(ax, x, body_bot, rx, up=False)
    y_liq = body_bot + liquid * (body_top - body_bot)
    line(ax, [(x - rx, y_liq), (x + rx, y_liq)], lw=LW_FINE)
    if label:
        dx, dy = label_offset if label_offset is not None else (rx + 20, 30)
        txt(ax, x + dx, y + dy, label, ha=label_ha)


def _low_pressure_tank(ax, x, y, w=66, h=150, label="低压罐", liquid=0.3,
                       label_offset=None, label_ha="left", sight=8, **kw):
    """立式低压罐:平顶封头 + 向下凸的半圆底 + 液位线 + 液位计/视镜。

    liquid ∈ [0,1] 控制液位线在筒体部分相对高度(0=圆底圆心处, 1=顶部)。
    sight 为液位计/视镜小圆半径,画在液位线中点。
    """
    rx = w / 2
    top = y - h / 2
    cy_bot = y + h / 2 - rx               # 底部半圆圆心
    line(ax, [(x - rx, top), (x - rx, cy_bot)], lw=LW_PART)
    line(ax, [(x + rx, top), (x + rx, cy_bot)], lw=LW_PART)
    line(ax, [(x - rx, top), (x + rx, top)], lw=LW_PART)   # 平顶封头
    _dome(ax, x, cy_bot, rx, up=False)                      # 向下凸的半圆底
    y_liq = cy_bot - liquid * (cy_bot - top)
    line(ax, [(x - rx, y_liq), (x + rx, y_liq)], lw=LW_FINE)
    ax.add_patch(Circle((x, y_liq), sight, facecolor=FILL,
                        edgecolor=LINE, lw=LW_FINE))
    if label:
        dx, dy = label_offset if label_offset is not None else (rx + 20, 20)
        txt(ax, x + dx, y + dy, label, ha=label_ha)


def _pump(ax, x, y, r=40, label="泵", **kw):
    """泵:圆 + 内部三角形(离心泵符号,三角指向排液方向)。"""
    ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=LINE,
                        lw=LW_PART))
    line(ax, [(x - 0.5 * r, y + 0.45 * r), (x + 0.55 * r, y),
              (x - 0.5 * r, y - 0.45 * r), (x - 0.5 * r, y + 0.45 * r)],
         lw=LW_PART)
    if label:
        txt(ax, x, y + r + 26, label)


def _square_wave(ax, x, y, w=224, amp=25, n=6, label=None, **kw):
    """方波,表示过冷器内部换热面。x,y 为左上角。"""
    seg = w / n
    xs, ys, cx = [x], [y], x
    for i in range(n):
        yv = y - amp if i % 2 == 0 else y + amp
        xs += [cx, cx + seg]
        ys += [yv, yv]
        cx += seg
    xs.append(cx)
    ys.append(y)
    ax.plot(xs, ys, color=LINE, lw=LW_PART)


ECONOMIZER_STYLES = ("diag", "plate")


def _economizer(ax, x, y, w=40, h=90, label="经济器", style="diag",
                n_plates=8, **kw):
    """经济器(板式换热器)符号。

    style="diag"  矩形 + 对角线换热面(默认)
    style="plate" 矩形 + 水平板片堆(n_plates 条板片)
    """
    if style not in ECONOMIZER_STYLES:
        raise ValueError(f"未知经济器 style={style!r},可用:"
                         f"{', '.join(ECONOMIZER_STYLES)}")
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, facecolor=FILL,
                           edgecolor=LINE, lw=LW_PART))
    if style == "plate":
        for i in range(1, n_plates):
            yy = y - h / 2 + h * i / n_plates
            line(ax, [(x - w / 2, yy), (x + w / 2, yy)], lw=LW_PART)
    else:
        line(ax, [(x - w / 2, y - h / 2), (x + w / 2, y + h / 2)], lw=LW_PART)
    if label:
        txt(ax, x + w / 2 + 18, y + 30, label, ha="left", boxed=True)


def _capillary(ax, x, y, label="毛细管", w=18, h=80, n=5, **kw):
    """毛细管:竖直弹簧形小螺旋管(半圆弧交替左/右),表示细长节流管。"""
    seg = h / n
    pts = []
    for i in range(n):
        cy = y - h / 2 + seg * (i + 0.5)
        r = seg / 2
        s = -1 if i % 2 == 0 else 1
        for j in range(25):
            theta = np.pi * j / 24
            px = x + s * (w / 2) * np.sin(theta)
            py = cy - r * np.cos(theta)
            pts.append((px, py))
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=LINE, lw=LW_OUTLINE, solid_capstyle="round",
            solid_joinstyle="round")
    if label:
        txt(ax, x + w / 2 + 18, y, label, ha="left", boxed=True)


def _box(ax, x, y, w, h, label=None, **kw):
    """通用矩形部件(冷凝器/蒸发器的简化抽象,供示意用)。"""
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, facecolor=FILL,
                           edgecolor=LINE, lw=LW_PART))
    if label:
        txt(ax, x, y, label)


def make_rect(w, h, name="换热器"):
    """按给定尺寸生成一个矩形部件,端口落在四边中点。"""
    def draw(ax, x, y, label=None, **kw):
        _box(ax, x, y, w, h, label=label)

    return Part(name, draw, {"left": (-w / 2, 0), "right": (w / 2, 0),
                             "top": (0, -h / 2), "bottom": (0, h / 2)},
                {"top": "n", "bottom": "s"})


HEX_SHAPES = ("circle", "rect", "rect_diag", "rect_zigzag", "rect_zigzag7")


# =========================
# 按尺寸生成端口的部件工厂
# =========================
def make_heat_exchanger(w=80, h=80, r=None, shape="rect", name="冷凝器",
                        n_pts=5):
    """标准 PFD 换热器(由 references/pfd_symbols.heat_exchanger 移植)。

    :param shape: 取值 ``HEX_SHAPES`` 之一:

      - ``circle`` 圆外壳 + 之字盘管(冷凝器/蒸发器通用)
      - ``rect`` 矩形外壳 + 之字盘管(参考版冷凝/蒸发器画法)
      - ``rect_zigzag`` 矩形外壳 + 蛇形盘管(n_pts 段交替圆弧 S 弯,默认 5)
      - ``rect_zigzag7`` 矩形外壳 + 7 点之字盘管
      - ``rect_diag`` 矩形外壳 + 左上→右下对角线(简化符号)

    端口落在四边中点。
    """
    if shape not in HEX_SHAPES:
        raise ValueError(f"未知换热器 shape={shape!r},可用:"
                         f"{', '.join(HEX_SHAPES)}")
    rx, ry = w / 2, h / 2
    ports = {"left": (-rx, 0), "right": (rx, 0),
             "top": (0, -ry), "bottom": (0, ry)}
    dirs = {"top": "n", "bottom": "s"}

    def draw(ax, x, y, label=None, **kw):
        R = r if r is not None else min(rx, ry)
        if shape == "circle":
            ax.add_patch(Circle((x, y), R, facecolor=FILL,
                                edgecolor=LINE, lw=LW_PART))
        else:
            ax.add_patch(Rectangle((x - rx, y - ry), w, h, facecolor=FILL,
                                   edgecolor=LINE, lw=LW_PART))
        if shape == "rect_diag":
            line(ax, [(x - rx, y - ry), (x + rx, y + ry)], lw=LW_OUTLINE)
        elif shape == "rect_zigzag":
            # 蛇形盘管:n 段交替圆弧 S 弯,左口中点起笔,右口中点收笔
            n = n_pts
            xs = rx
            seg = 2 * xs / n
            amp = ry * 0.42
            pts = []
            for i in range(n):
                cx = x - xs + seg * (i + 0.5)
                s = -1 if i % 2 == 0 else 1   # y 向下:负=向上鼓
                for j in range(25):
                    th = math.pi * (1 - j / 24)   # π→0,左→右
                    pts.append((cx + seg / 2 * math.cos(th),
                                y + s * amp * math.sin(th)))
            line(ax, pts, lw=LW_OUTLINE)
        else:
            # 之字盘管:左口中点起笔,右口中点收笔,中间 n 个折点上下交替
            n = 7 if shape == "rect_zigzag7" else 5
            xs = (R * 0.78 if shape == "circle" else rx)
            amp = (R * 0.42 if shape == "circle" else ry * 0.42)
            pts = [(x - xs, y)]
            for i in range(n):
                xi = x - xs + 2 * xs * (i + 0.5) / n
                pts.append((xi, y - amp if i % 2 == 0 else y + amp))
            pts.append((x + xs, y))
            line(ax, pts, lw=LW_OUTLINE)
        if label:
            txt(ax, x, y + ry + 26, label, boxed=True)

    return Part(name, draw, ports, dirs)


# =========================
# 部件实例(端口表)
# =========================
evaporator = _part("蒸发器", {"in": (0, 48), "out": (0, -48)},
                   _evaporator, dirs={"in": "s", "out": "n"})
compressor = _part("压缩机", {"suction": (0, -95), "discharge": (0, 95),
                              "vapor_inj": (95, 0)},
                   _compressor)
separator = _part("气液分离器", {"left": (-17, 0), "right": (17, 0),
                                 "top": (0, -32)},
                  _separator, dirs={"top": "n"})
receiver = _part("储液器", {"left": (-17, 0), "right": (17, 0),
                            "top": (0, -35)}, _receiver, dirs={"top": "n"})
condenser = _part("冷凝器", {"left": (-32, 0), "right": (32, 0),
                             "top": (0, -80), "bottom": (0, 80)},
                  _condenser, dirs={"top": "n", "bottom": "s"})
four_way_valve = _part("四通阀", {"left": (-20, 0), "right": (20, 0),
                                  "top": (0, -14), "bottom": (0, 14)},
                       _four_way_valve, dirs={"top": "n", "bottom": "s"})
four_way_round = _part("四通阀(圆菱形)",
                       {"exhaust": (0, -40), "condenser": (40, 0),
                        "evaporator": (0, 40), "suction": (-40, 0)},
                       _four_way_round_valve,
                       dirs={"exhaust": "n", "condenser": "e",
                             "evaporator": "s", "suction": "w"})
expansion_valve = _part("电子膨胀阀", {"in": (16, 0), "out": (-16, 0)},
                        _expansion_valve)
filter_drier = _part("干燥过滤器", {"in": (35, 0), "out": (-35, 0)},
                     _filter_drier)
plate_hex = _part("板式换热器", {"in": (55, 0), "out": (-55, 0)}, _plate_hex)
water_tank = _part("水箱", {"left_up": (-90, -65), "left_down": (-90, 65)},
                   _water_tank, dirs={"left_up": "w", "left_down": "w"})
flow_meter = _part("流量计", {"left": (-28, 0), "right": (28, 0)}, _flow_meter)
valve = _part("阀", {"left": (-32, 0), "right": (32, 0), "top": (0, -36),
                     "bottom": (0, 24)}, _valve, dirs={"top": "n",
                                                       "bottom": "s"})
square_wave = _part("过冷器换热面", {"left": (0, 55), "right": (224, 55)},
                    _square_wave, dirs={"left": "w", "right": "e"})
economizer = _part("经济器", {"top": (0, -45), "bottom": (0, 45),
                              "left": (-20, 0), "right": (20, 0)},
                   _economizer)
pump = _part("泵", {"left": (-40, 0), "right": (40, 0), "top": (0, -40),
                    "bottom": (0, 40)}, _pump)
capillary = _part("毛细管", {"in": (0, -40), "out": (0, 40)}, _capillary,
                  dirs={"in": "n", "out": "s"})


# =========================
# 按尺寸生成端口的部件工厂
# =========================
def make_compressor(r=95, style="centrifugal", name="压缩机", n_blades=3):
    """压缩机部件,style 见 COMPRESSOR_STYLES。"""
    def draw(ax, x, y, label="压缩机", label_offset=None, label_ha="center",
             **kw):
        _compressor(ax, x, y, label=label, r=r, style=style,
                    n_blades=n_blades, label_offset=label_offset,
                    label_ha=label_ha)

    return Part(name, draw,
                {"left": (-r, 0), "right": (r, 0),
                 "top": (0, -r), "bottom": (0, r)},
                {"top": "n", "bottom": "s"})


def make_scroll_chord(r=85, name="涡旋压缩机"):
    """涡旋压缩机(参考图画法):圆 + 收敛双弦,即 style="chord"。

    与 make_compressor 的差别在端口语义:suction/discharge 落在圆左右
    中点(两弦之间的接管高度),补气口 inj 在圆底部略偏左 —— 与循环
    图中补气管(如状态点 9)自下方接入的画法一致。
    """
    def draw(ax, x, y, label=None, label_offset=None, label_ha="center",
             **kw):
        _compressor(ax, x, y, label=label, r=r, style="chord",
                    label_offset=label_offset, label_ha=label_ha)

    return Part(name, draw,
                {"suction": (-r, 0), "discharge": (r, 0),
                 "inj": (-0.08 * r, r)},
                {"suction": "w", "discharge": "e", "inj": "s"})


scroll_chord = make_scroll_chord()


def make_vessel(w=66, h=150, liquid=0.42, name="闪发罐"):
    """立式容器/闪发罐部件。vapor 口在筒体上端右侧(闪发气出口)。"""
    rx = w / 2
    body_top = -(h / 2 - rx)

    def draw(ax, x, y, label="闪发罐", label_offset=None, label_ha="left",
             **kw):
        _vessel(ax, x, y, w=w, h=h, label=label, liquid=liquid,
                label_offset=label_offset, label_ha=label_ha)

    return Part(name, draw,
                {"top": (0, -h / 2), "bottom": (0, h / 2),
                 "left": (-rx, 0), "right": (rx, 0),
                 "vapor": (rx, body_top + 4)},
                {"top": "n", "bottom": "s"})


def make_low_pressure_tank(w=66, h=150, liquid=0.3, name="低压罐"):
    """立式低压罐部件:顶平底圆筒体。端口 top/bottom/left/right/vapor。

    top 为平封头中点上接口(进液/气相),bottom 为圆底最低点液相出口,
    vapor 为筒体上端右侧的闪发气出口。
    """
    rx = w / 2

    def draw(ax, x, y, label="低压罐", label_offset=None, label_ha="left",
             **kw):
        _low_pressure_tank(ax, x, y, w=w, h=h, label=label, liquid=liquid,
                           label_offset=label_offset, label_ha=label_ha)

    return Part(name, draw,
                {"top": (0, -h / 2), "bottom": (0, h / 2),
                 "left": (-rx, 0), "right": (rx, 0),
                 "vapor": (rx, -h / 2 + 10)},
                {"top": "n", "bottom": "s"})


# 默认尺寸实例(尺寸不合适时用上面的工厂函数按需生成)
vessel = make_vessel()
low_pressure_tank = make_low_pressure_tank()


def make_globe_valve(w=64, h=48, stem=26, handle=44, name="截止阀"):
    """截止阀部件:左右对顶三角沙漏 + 贯穿阀杆 + 手轮横杆。端口 in/out。

    端口落在左右接管外端,沿水平方向(in=w, out=e)。
    """
    def draw(ax, x, y, label=None, **kw):
        _globe_valve(ax, x, y, label=label, w=w, h=h, stem=stem,
                     handle=handle)

    return Part(name, draw,
                {"in": (-w / 2 - 12, 0), "out": (w / 2 + 12, 0)},
                {"in": "w", "out": "e"})


globe_valve = make_globe_valve()


def make_solenoid_valve(r=34, stem=20, handle=40, name="电磁阀"):
    """电磁阀部件:圆体 + 圆内 X + 顶部电磁引线与横杠。端口 in/out。

    端口落在圆左右接管外端,沿水平方向(in=w, out=e)。
    """
    def draw(ax, x, y, label=None, **kw):
        _solenoid_valve(ax, x, y, label=label, r=r, stem=stem, handle=handle)

    return Part(name, draw,
                {"in": (-r - 12, 0), "out": (r + 12, 0)},
                {"in": "w", "out": "e"})


solenoid_valve = make_solenoid_valve()


def make_bowtie_valve(w=76, h=44, actuator="none", stem=14, dome_r=21,
                      sol_len=62, name="对顶三角阀"):
    """对顶三角阀部件(论文/参考图风格),actuator 见 _bowtie_valve。

    端口按库内两端口件惯例 in=东口 / out=西口(图内流向东->西);
    actuator/stem 等也可在 add() 时以同名词覆盖,如
    d.add(parts.bowtie_valve, "电磁阀", loc=..., actuator="solenoid")。
    """
    def draw(ax, x, y, label=None, **kw):
        _bowtie_valve(ax, x, y, label=label, w=w, h=h, actuator=actuator,
                      stem=stem, dome_r=dome_r, sol_len=sol_len)

    return Part(name, draw, {"in": (w / 2, 0), "out": (-w / 2, 0)},
                {"in": "e", "out": "w"})


bowtie_valve = make_bowtie_valve()
bowtie_valve_dome = make_bowtie_valve(actuator="dome", name="膨胀阀(穹顶)")
bowtie_valve_solenoid = make_bowtie_valve(actuator="solenoid",
                                          name="电磁阀(对顶三角)")


def make_economizer(w=40, h=90, style="diag", n_plates=8, name="经济器"):
    """经济器部件。style ∈ ECONOMIZER_STYLES,n_plates 为 plate 样式板片数。"""
    def draw(ax, x, y, label="经济器", **kw):
        _economizer(ax, x, y, w=w, h=h, label=label, style=style,
                    n_plates=n_plates)

    return Part(name, draw,
                {"top": (0, -h / 2), "bottom": (0, h / 2),
                 "left": (-w / 2, 0), "right": (w / 2, 0)},
                {"top": "n", "bottom": "s"})


economizer_plate = make_economizer(style="plate")

# 语义上属于部件库的派生工具,core 保留导出以维持既有 import 路径
from .core import make_partial            # noqa: E402,F401
