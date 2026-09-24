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
        return self.ports[key]

    def direction(self, key):
        """端口外法向单位向量,优先取显式声明。"""
        if key in self._dirs:
            return _PORT_DIR[self._dirs[key]]
        dx, dy = self.ports[key]
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


def _scroll_compressor(ax, x, y, label="涡旋压缩机", r=95, **kw):
    """涡旋压缩机(原图简化画法):圆内两条对称的括号形折线。

    注:标准 PFD 的涡旋符号是阿基米德螺线,见 compressor(style="scroll")。
    """
    ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=LINE, lw=LW_OUTLINE))
    for s in (1, -1):
        top = (x + s * r * 0.12, y - r * 0.82)
        mid = (x + s * r * 0.64, y - r * 0.18)
        low = (x + s * r * 0.44, y + r * 0.80)
        line(ax, [top, mid, low], lw=LW_PART)
    if label:
        txt(ax, x + 92, y + 52, label, ha="left")


# =========================
# 标准 PFD 符号(ISA-5.1 / ISO 10628 风格)
# 由 references/pfd_symbols.py 移植,坐标系统一为 y 向下
# =========================
COMPRESSOR_STYLES = ("centrifugal", "rotor", "axial", "recip", "screw",
                     "scroll")


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


def _economizer(ax, x, y, w=40, h=90, label="经济器", **kw):
    """经济器(板式换热器)符号:矩形 + 对角线换热面。"""
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, facecolor=FILL,
                           edgecolor=LINE, lw=LW_PART))
    line(ax, [(x - w / 2, y - h / 2), (x + w / 2, y + h / 2)], lw=LW_PART)
    if label:
        txt(ax, x + w / 2 + 18, y + 30, label, ha="left", bg=True)


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
        txt(ax, x + w / 2 + 18, y, label, ha="left", bg=True)


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

    shape ∈ HEX_SHAPES:
      circle       圆外壳 + 之字盘管(冷凝器/蒸发器通用)
      rect         矩形外壳 + 之字盘管(参考版冷凝/蒸发器画法)
      rect_zigzag  矩形外壳 + 蛇形盘管(n_pts 段交替圆弧 S 弯,默认 5)
      rect_zigzag7 矩形外壳 + 7 点之字盘管
      rect_diag    矩形外壳 + 左上→右下对角线(简化符号,即原 economizer)
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
            txt(ax, x, y + ry + 26, label, bg=True)

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
scroll_compressor = _part("涡旋压缩机", {"suction": (-95, 0),
                                         "discharge": (95, 0),
                                         "vapor_inj": (0, 95)},
                          _scroll_compressor, dirs={"suction": "w",
                                                    "discharge": "e",
                                                    "vapor_inj": "s"})
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


# 默认尺寸实例(尺寸不合适时用上面的工厂函数按需生成)
vessel = make_vessel()
