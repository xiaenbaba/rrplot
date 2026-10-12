# -*- coding: utf-8 -*-
"""HVAC 符号族:references/hvacsvg/symbols 全部 17 个 SVG 转成的代码图元。

每个符号是一个工厂,参数语义与 load_svg_part 一致::

    from cycleplot import hvac

    tank = hvac.thermal_tank(scale=1.5, bridge=44,
                            moves={"right": (160, 72)}, label_dy=-97)
    node = d.add(tank, "蓄热水箱", loc=(770, 375))

工厂参数:
    scale     整体缩放(端口偏移、线宽、标签位置一并缩放)
    moves     {连接点 id: (x, y)} 覆盖连接点在 viewBox 里的坐标
    bridge    从每个连接点沿边缘法向朝内补一段引管(符号单位)
    label_dy  标签相对锚点的竖直偏移;None 画在符号下方,0 压在符号中心

图形全部写在 160×100 的 viewBox 坐标里(中心 80,50),绘制时统一乘
scale 再平移到锚点;stroke-width 换算与 svgparts 同规则。同一个 SVG
<path> 的多条子路径画在同一个 PathPatch 里 —— Agg 对复合路径与分离
路径的描边光栅化不同,按原分组才能与 load_svg_part 逐像素一致。
SVG 原文件只作形状参考,形状以本模块为准。
"""
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, PathPatch, Rectangle
from matplotlib.path import Path

from ._primitives import line, txt
from .parts import Part
from .style import LINE, LW_PIPE

VB_W, VB_H = 160.0, 100.0

RED, GREEN, BLUE, PURPLE = "#e53935", "#2e9e58", "#1677ff", "#7b3ff2"


# =========================
# viewBox 画布辅助
# =========================
def _lw(sw, s):
    """SVG stroke-width → matplotlib linewidth(与 svgparts 同规则)。"""
    return sw * max(s, 0.5)


def _rect(ax, X, Y, s, x, y, w, h, fc, ec, sw, rx=0):
    lw = _lw(sw, s)
    x0, y0, ww, hh = X(x), Y(y), w * s, h * s
    if rx:
        r = rx * s
        ax.add_patch(FancyBboxPatch((x0 + r, y0 + r), ww - 2 * r, hh - 2 * r,
                                    boxstyle=f"round,pad={r}", facecolor=fc,
                                    edgecolor=ec, linewidth=lw, zorder=1))
    else:
        ax.add_patch(Rectangle((x0, y0), ww, hh, facecolor=fc, edgecolor=ec,
                               linewidth=lw, zorder=1))


def _circle(ax, X, Y, s, cx, cy, r, fc, ec, sw):
    ax.add_patch(Circle((X(cx), Y(cy)), r * s, facecolor=fc, edgecolor=ec,
                        linewidth=_lw(sw, s), zorder=1))


def _ellipse(ax, X, Y, s, cx, cy, rx, ry, fc, ec, sw):
    ax.add_patch(Ellipse((X(cx), Y(cy)), 2 * rx * s, 2 * ry * s,
                         facecolor=fc, edgecolor=ec,
                         linewidth=_lw(sw, s), zorder=1))


def _pathpatch(ax, X, Y, verts, codes, color, sw, s, fill="none"):
    pts = [(X(a), Y(b)) for a, b in verts]
    ax.add_patch(PathPatch(Path(pts, codes), facecolor=fill, edgecolor=color,
                           linewidth=_lw(sw, s), joinstyle="round",
                           capstyle="round", zorder=1))


def _lines(ax, X, Y, s, subs, color, sw):
    """若干条开放折线画进同一个 PathPatch(对应 SVG 一个 <path>)。"""
    verts, codes = [], []
    for pts in subs:
        verts += list(pts)
        codes += [Path.MOVETO] + [Path.LINETO] * (len(pts) - 1)
    _pathpatch(ax, X, Y, verts, codes, color, sw, s)


def _stroke(ax, X, Y, s, pts, color, sw):
    _lines(ax, X, Y, s, [pts], color, sw)


def _fillpolys(ax, X, Y, s, polys, color, sw):
    """若干闭合多边形画进同一个 PathPatch(填充 = 描边同色)。"""
    verts, codes = [], []
    for pts in polys:
        verts += list(pts) + [pts[0]]
        codes += ([Path.MOVETO] + [Path.LINETO] * (len(pts) - 1)
                  + [Path.CLOSEPOLY])
    _pathpatch(ax, X, Y, verts, codes, color, sw, s, fill=color)


# =========================
# 符号本体(viewBox 坐标)
# =========================
def _heat_pump(ax, X, Y, s):                      # 01_空气能主机
    _rect(ax, X, Y, s, 22, 12, 116, 76, "#eef2f5", "#444444", 2, rx=3)
    for cy in (34, 65):
        _rect(ax, X, Y, s, 35, cy - 12, 90, 24, "#dfe5ea", "#777777", 1)
        _circle(ax, X, Y, s, 80, cy, 16, "#c8d0d8", "#333333", 2)
        _lines(ax, X, Y, s,
               [[(80, cy - 16), (80, cy + 16)],
                [(64, cy), (96, cy)],
                [(69, cy - 11), (91, cy + 11)],
                [(91, cy - 11), (69, cy + 11)]], "#333333", 1.5)


def _water_pump(ax, X, Y, s):                     # 02_水泵
    _stroke(ax, X, Y, s, [(18, 50), (45, 50)], BLUE, 7)
    _circle(ax, X, Y, s, 65, 50, 20, BLUE, "#124f9d", 2)
    _pathpatch(ax, X, Y,
               [(54, 39), (69, 43), (71, 56), (62, 63)],
               [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4],
               "#ffffff", 3, s)
    _rect(ax, X, Y, s, 83, 37, 28, 26, "#287ee0", "#124f9d", 2, rx=3)
    _stroke(ax, X, Y, s, [(111, 50), (139, 50)], BLUE, 7)


def _stop_valve(color):
    """两段短管 + 对顶三角 + 白心圆(03 防冻阀 / 07 排水阀 / 08 补水阀)。"""
    def body(ax, X, Y, s):
        _lines(ax, X, Y, s, [[(10, 50), (55, 50)], [(105, 50), (150, 50)]],
               color, 5)
        _fillpolys(ax, X, Y, s, [[(55, 36), (80, 50), (55, 64)],
                                 [(105, 36), (80, 50), (105, 64)]], color, 1)
        _circle(ax, X, Y, s, 80, 50, 7, "#ffffff", color, 3)
    return body


def _thermal_tank(ax, X, Y, s):                   # 04_蓄热水箱
    _ellipse(ax, X, Y, s, 80, 14, 38, 9, "#f5f7f8", "#555555", 2)
    _rect(ax, X, Y, s, 42, 14, 76, 70, "#f5f7f8", "#555555", 2)
    _ellipse(ax, X, Y, s, 80, 84, 38, 9, "#edf1f3", "#555555", 2)
    _ellipse(ax, X, Y, s, 80, 14, 15, 4, "none", "#777777", 1)
    _lines(ax, X, Y, s, [[(25, 32), (42, 32)], [(118, 32), (135, 32)],
                         [(25, 70), (42, 70)], [(118, 70), (135, 70)]],
           RED, 4)
    _stroke(ax, X, Y, s, [(80, 48), (80, 68)], "#ff8c00", 4)
    _circle(ax, X, Y, s, 80, 44, 5, "#ff8c00", "black", 1)


def _electric_heater(ax, X, Y, s):                # 05_电加热
    _rect(ax, X, Y, s, 55, 16, 50, 68, "#f7f7f7", "#555555", 2, rx=8)
    verts = [(80, 27), (80, 69)]
    codes = [Path.MOVETO, Path.LINETO]
    for y0 in (40, 52, 64):
        verts += [(67, y0), (75, y0 - 7), (85, y0 - 7), (93, y0)]
        codes += [Path.MOVETO] + [Path.CURVE4] * 3
    _pathpatch(ax, X, Y, verts, codes, "#e66b00", 3, s)
    _circle(ax, X, Y, s, 80, 50, 4, "#ff9d00", "black", 1)


def _safety_valve(ax, X, Y, s):                   # 06_安全阀
    _stroke(ax, X, Y, s, [(20, 55), (140, 55)], GREEN, 5)
    _stroke(ax, X, Y, s, [(65, 55), (65, 28), (95, 28), (95, 55)], GREEN, 5)
    _lines(ax, X, Y, s, [[(58, 28), (102, 28)], [(70, 18), (90, 18)]],
           GREEN, 5)
    _stroke(ax, X, Y, s, [(80, 55), (80, 73)], GREEN, 3)


def _auto_vent(ax, X, Y, s):                      # 09_自动排气阀
    _stroke(ax, X, Y, s, [(80, 85), (80, 58)], PURPLE, 5)
    _rect(ax, X, Y, s, 61, 36, 38, 23, "#a56cff", "#5d2bc2", 2, rx=4)
    _stroke(ax, X, Y, s, [(69, 36), (69, 25), (91, 25), (91, 36)],
            "#5d2bc2", 3)
    _stroke(ax, X, Y, s, [(74, 25), (86, 25)], "#5d2bc2", 3)


def _fan_coil(ax, X, Y, s):                       # 10_风机盘管
    _rect(ax, X, Y, s, 20, 22, 120, 56, "#eef2f5", "#555555", 2, rx=4)
    _rect(ax, X, Y, s, 38, 34, 84, 32, "#e0e8ef", "#287ee0", 2, rx=2)
    _lines(ax, X, Y, s, [[(45, y0), (115, y0)] for y0 in (43, 51, 59)],
           "#287ee0", 2)
    _rect(ax, X, Y, s, 10, 39, 10, 22, "#d8dde2", "#555555", 1)
    _rect(ax, X, Y, s, 140, 39, 10, 22, "#d8dde2", "#555555", 1)


def _corrugated(ax, X, Y, s):                     # 11_不锈钢波纹管
    _stroke(ax, X, Y, s, [(12, 50), (148, 50)], "#777777", 14)
    _stroke(ax, X, Y, s, [(12, 50), (148, 50)], "#d8dde2", 9)
    _lines(ax, X, Y, s, [[(x0, 42), (x0, 58)] for x0 in range(20, 141, 8)],
           "#777777", 2)
    _rect(ax, X, Y, s, 3, 40, 10, 20, "#bbbbbb", "#555555", 1)
    _rect(ax, X, Y, s, 147, 40, 10, 20, "#bbbbbb", "#555555", 1)


_FLOOR_SPIRAL = [(18, 12), (142, 12), (142, 88), (18, 88), (18, 22),
                 (132, 22), (132, 78), (28, 78), (28, 32), (122, 32),
                 (122, 68), (38, 68), (38, 42), (112, 42), (112, 58),
                 (48, 58), (48, 52), (102, 52), (102, 48), (58, 48),
                 (58, 52)]


def _floor_heating(ax, X, Y, s):                  # 12_地暖
    _stroke(ax, X, Y, s, _FLOOR_SPIRAL, RED, 4)
    _lines(ax, X, Y, s, [[(8, 50), (18, 50)], [(142, 50), (152, 50)]],
           RED, 4)


def _manifold(color):
    """分水器:竖汇管 + 三条支管 + 端部白心圆(13 供 / 14 进)。"""
    def body(ax, X, Y, s):
        _stroke(ax, X, Y, s, [(25, 20), (25, 80)], color, 7)
        _lines(ax, X, Y, s, [[(25, y0), (140, y0)] for y0 in (30, 50, 70)],
               color, 5)
        for y0 in (30, 50, 70):
            _circle(ax, X, Y, s, 140, y0, 5, "#ffffff", color, 3)
    return body


def _supply_pipe(ax, X, Y, s):                    # 15_供水管_热水
    _stroke(ax, X, Y, s, [(10, 50), (140, 50)], RED, 5)
    _stroke(ax, X, Y, s, [(125, 42), (140, 50), (125, 58)], RED, 4)


def _return_pipe(ax, X, Y, s):                    # 16_回水管
    _stroke(ax, X, Y, s, [(10, 50), (140, 50)], BLUE, 5)
    _stroke(ax, X, Y, s, [(25, 42), (10, 50), (25, 58)], BLUE, 4)


def _ball_valve(ax, X, Y, s):                     # 17_球阀
    _lines(ax, X, Y, s, [[(10, 50), (58, 50)], [(102, 50), (150, 50)]],
           RED, 5)
    _fillpolys(ax, X, Y, s, [[(58, 34), (80, 50), (58, 66)],
                             [(102, 34), (80, 50), (102, 66)]], RED, 1)
    _circle(ax, X, Y, s, 80, 50, 9, "#ffffff", RED, 3)
    _stroke(ax, X, Y, s, [(80, 50), (94, 40)], RED, 3)


# =========================
# 工厂
# =========================
def _hvac(name, pts, body):
    """构造符号工厂;pts 为 {连接点 id: (x, y)}(viewBox 坐标)。"""
    def make(scale=1.0, moves=None, bridge=0, label_dy=None):
        cx, cy = VB_W / 2, VB_H / 2
        P = {k: tuple(moves[k]) if moves and k in moves else v
             for k, v in pts.items()}
        port_off = {k: ((px - cx) * scale, (py - cy) * scale)
                    for k, (px, py) in P.items()}
        dy = cy * scale + 24 if label_dy is None else label_dy

        def draw(ax, x, y, label=None, **kw):
            ox, oy = x - cx * scale, y - cy * scale

            def X(px):
                return px * scale + ox

            def Y(py):
                return py * scale + oy

            body(ax, X, Y, scale)
            if bridge:
                for px, py in P.values():
                    if px <= 0:
                        seg = ((px, py), (px + bridge, py))
                    elif px >= VB_W:
                        seg = ((px, py), (px - bridge, py))
                    elif py <= 0:
                        seg = ((px, py), (px, py + bridge))
                    else:
                        seg = ((px, py), (px, py - bridge))
                    line(ax, [(X(a), Y(b)) for a, b in seg],
                         lw=LW_PIPE, color=LINE)
            if label:
                txt(ax, x, y + dy, label, size=17)

        return Part(name, draw, port_off, {})
    return make


_TWO = {"in": (0, 50), "out": (160, 50)}
_MANIFOLD_PORTS = {"main": (0, 50), "loop1": (160, 30),
                   "loop2": (160, 50), "loop3": (160, 70)}

heat_pump = _hvac("空气能主机",
                  {"water_out": (160, 40), "water_in": (0, 60)}, _heat_pump)
water_pump = _hvac("水泵", _TWO, _water_pump)
anti_freeze_valve = _hvac("防冻阀", _TWO, _stop_valve(RED))
thermal_tank = _hvac("蓄热水箱",
                     {"upper": (0, 32), "lower": (0, 70), "right": (160, 50)},
                     _thermal_tank)
electric_heater = _hvac("电加热", {"center": (0, 50), "out": (160, 50)},
                        _electric_heater)
safety_valve = _hvac("安全阀",
                     {"in": (0, 55), "out": (160, 55), "drain": (80, 100)},
                     _safety_valve)
drain_valve = _hvac("排水阀", _TWO, _stop_valve(GREEN))
makeup_valve = _hvac("补水阀", _TWO, _stop_valve(GREEN))
auto_vent = _hvac("自动排气阀", {"pipe": (80, 100)}, _auto_vent)
fan_coil = _hvac("风机盘管",
                 {"water_in": (0, 42), "water_out": (160, 58), "air": (80, 0)},
                 _fan_coil)
corrugated_pipe = _hvac("不锈钢波纹管", _TWO, _corrugated)
floor_heating = _hvac("地暖", _TWO, _floor_heating)
supply_manifold = _hvac("分水器（供）", _MANIFOLD_PORTS, _manifold(RED))
return_manifold = _hvac("分水器（进）", _MANIFOLD_PORTS, _manifold(BLUE))
supply_pipe = _hvac("供水管（热水）", _TWO, _supply_pipe)
return_pipe = _hvac("回水管", _TWO, _return_pipe)
ball_valve = _hvac("球阀", _TWO, _ball_valve)
