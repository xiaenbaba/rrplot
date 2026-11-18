# -*- coding: utf-8 -*-
"""部件库:每个部件是一个绘制函数(以中心为锚点)+ 端口定义。

端口 ports: 名称 -> (dx, dy),相对部件锚点的偏移。dx/dy 同时隐含接管方向
(单轴端口取该轴符号;双轴非零的端口需要显式方向,见 Part.port_dir)。

命名约定:贯通式两口元件(阀、过滤器、毛细管等)用 in/out;
多口/换热类部件用 left/right/top/bottom 表示边中点。
"""
import math

import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

from ._primitives import line, txt
from .core import make_partial  # noqa: F401  重新导出,维持 from parts import 路径
from .part import Part, make_part
from .style import FILL, LINE, LW_FINE, LW_OUTLINE, LW_PART, LW_STRONG

_part = make_part


# =========================
# 绘制函数(中心锚点)
# =========================
def _oil_separator(ax, x, y, label="油分离器", w=64, h=176, stub=16,
                   **kw):
    """油分离器:瘦长矩形壳 + 顶/底/侧三根接管(参考图画法,内部无构件)。

    进气自上部侧管(接压缩机排气),干燥气自顶管出(接四通阀 D 口),
    回油自底管出(经毛细管接回吸气管)。
    """
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    y_side = y - h / 4                        # 侧管:壳顶下 1/4(参考图比例)
    line(ax, [(x, y - h / 2 - stub), (x, y - h / 2)], lw=LW_PART)
    line(ax, [(x, y + h / 2), (x, y + h / 2 + stub)], lw=LW_PART)
    line(ax, [(x - w / 2 - stub, y_side), (x - w / 2, y_side)], lw=LW_PART)
    if label:
        txt(ax, x + w / 2 + 18, y - 8, label, size=17, ha="left")


def _separator_utube(ax, x, y, label=None, w=120, h=118, stub=16,
                     flip=False, **kw):
    """气液分离器(U 形管液封):方壳 + 内置 U 形管 + 弯底放油点。

    进气短管自壳顶伸入、悬于壳内上部;出气管即 U 形管右腿,穿壳顶引出;
    U 形管兼作液封(液体积于弯底),弯底小圆点为放油/排液口标记。
    flip=True 镜像:进气短管在东侧、出气管为 U 形管左腿(进口在右、出口在左)。
    """
    s = -1.0 if flip else 1.0
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    y_top = y - h / 2
    lx = 0.435 * w                  # U 形管两腿半距(约壳宽 87%)
    y_leg = y_top + 0.116 * h       # 开口腿上口(壳内开管)
    y_arc = y_top + 0.61 * h        # 弯头起点(竖段下端)
    y_bot = y_top + 0.963 * h       # 弯底(壳底上方)
    x_in = x - s * 0.365 * w        # 进气短管:默认偏西,镜像后偏东
    b = y_bot - y_arc               # 弯头竖半轴
    arc = [(x + s * lx * math.cos(math.radians(t)),
            y_arc + b * math.sin(math.radians(t)))
           for t in range(180, -1, -6)]        # 开口腿 -> 弯底 -> 出气腿
    line(ax, [(x - s * lx, y_leg)] + arc + [(x + s * lx, y_top - stub)],
         lw=LW_PART)                            # U 形管 + 出气管
    line(ax, [(x_in, y_top - stub), (x_in, y_top + 0.2 * h)],
         lw=LW_PART)                            # 进气短管(悬于壳内上部)
    ax.add_patch(Circle((x, y_bot), max(2.0, 0.022 * w),
                        facecolor=LINE, edgecolor=LINE, lw=LW_FINE))
    if label:
        # 标签放壳体外侧(默认右侧,镜像后左侧):底部中央留给 drain 放油管
        txt(ax, x + s * (w / 2 + 18), y - 8, label,
            ha="left" if s > 0 else "right")


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


def _filter(ax, x, y, label=None, w=72, h=36, n=7, stub=12, **kw):
    """过滤器:矩形 + 菱形网格(双向45° 交叉线),左右接管。

    网格为两族斜率 ±1 的平行线,按 k 均匀取值后裁剪到矩形内;
    端口在接管两端,沿水平方向(in/w, out/e)。
    """
    x1, x2 = x - w / 2, x + w / 2
    y1, y2 = y - h / 2, y + h / 2
    ax.add_patch(Rectangle((x1, y1), w, h,
                           facecolor=FILL, edgecolor=LINE, lw=LW_PART))
    for k in np.linspace(y1 - x2, y2 - x1, n):        # 斜率 +1:y = x + k
        xs, xe = max(x1, y1 - k), min(x2, y2 - k)
        if xs < xe:
            line(ax, [(xs, xs + k), (xe, xe + k)], lw=LW_FINE)
    for k in np.linspace(y1 + x1, y2 + x2, n):        # 斜率 -1:y = k - x
        xs, xe = max(x1, k - y2), min(x2, k - y1)
        if xs < xe:
            line(ax, [(xs, k - xs), (xe, k - xe)], lw=LW_FINE)
    line(ax, [(x1 - stub, y), (x1, y)], lw=LW_STRONG)
    line(ax, [(x2, y), (x2 + stub, y)], lw=LW_STRONG)
    if label:
        txt(ax, x, y + h / 2 + 26, label)


def _globe_valve(ax, x, y, label=None, w=64, h=48, stem=26, handle=44, **kw):
    """截止阀(globe valve):左右对顶三角(沙漏) + 阀杆 + 顶部手轮横杆。

    阀杆自两三角交汇的中点向上引出(不贯穿阀体),顶端接手轮横杆;
    左右竖边中点外侧各引一段接管,端口沿水平方向(in/out)。
    """
    ax.add_patch(Polygon([(x - w / 2, y - h / 2), (x - w / 2, y + h / 2),
                          (x, y)], closed=True, facecolor=FILL,
                         edgecolor=LINE, lw=LW_OUTLINE))
    ax.add_patch(Polygon([(x + w / 2, y - h / 2), (x + w / 2, y + h / 2),
                          (x, y)], closed=True, facecolor=FILL,
                         edgecolor=LINE, lw=LW_OUTLINE))
    top = y - h / 2 - stem
    line(ax, [(x, y), (x, top)], lw=LW_PART)              # 阀杆(止于中点)
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


def _expansion_valve_eng(ax, x, y, label=None, r=34, **kw):
    """电子膨胀阀(工程画法):圆体 + 圆内 X,无顶部电磁引线与横杠。

    即电磁阀去掉电磁执行机构后的阀体画法,常见于工程制冷流程图;
    端口在圆左右水平方向(in/out)。
    """
    ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=LINE,
                        lw=LW_OUTLINE))
    c = r / math.sqrt(2)
    line(ax, [(x - c, y - c), (x + c, y + c)], lw=LW_PART)
    line(ax, [(x + c, y - c), (x - c, y + c)], lw=LW_PART)
    line(ax, [(x - r, y), (x - r - 12, y)], lw=LW_STRONG)
    line(ax, [(x + r, y), (x + r + 12, y)], lw=LW_STRONG)
    if label:
        txt(ax, x, y + r + 26, label)


def _check_valve(ax, x, y, label=None, w=56, h=32, stub=12, point="e",
                 **kw):
    """单向阀(止回阀):实心三角指向流通方向 + 尖端挡条 + 贯穿接管。

    point: "e" 三角指向东(默认,流西→东);"w" 三角指向西(流东→西)。
    三角实心填充,挡条为竖直短棒,横管贯穿整个符号。
    """
    if point not in ("e", "w"):
        raise ValueError(f"未知 point={point!r},可用:'e' / 'w'")
    s = 1 if point == "e" else -1
    ax.add_patch(Polygon([(x - s * w / 2, y - h / 2),
                          (x - s * w / 2, y + h / 2),
                          (x + s * w / 2, y)], closed=True,
                         facecolor=LINE, edgecolor=LINE, lw=LW_PART))
    line(ax, [(x - s * (w / 2 + stub), y), (x + s * (w / 2 + stub), y)],
         lw=LW_STRONG)                                   # 贯穿接管
    line(ax, [(x + s * w / 2, y - 0.275 * h), (x + s * w / 2, y + 0.275 * h)],
         lw=LW_STRONG)                                   # 尖端挡条
    if label:
        txt(ax, x, y + h / 2 + 26, label)


# =========================
# 标准 PFD 符号(ISA-5.1 / ISO 10628 风格)
# 由 references/pfd_symbols.py 移植,坐标系统一为 y 向下
# =========================
COMPRESSOR_STYLES = ("圆形", "方形")


def _compressor_circle(ax, x, y, r=95, label="压缩机", **kw):
    """圆形压缩机:圆体 + 两条对称弦线(原离心式画法),
    弦的上下端点精确落在圆周上。"""
    ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=LINE,
                        lw=LW_OUTLINE))
    for s in (-1.0, 1.0):
        ux = 0.40 * r
        uy = math.sqrt(r * r - ux * ux)
        lx = 0.66 * r
        ly = math.sqrt(r * r - lx * lx)
        line(ax, [(x + s * ux, y - uy), (x + s * lx, y + ly)], lw=LW_PART)
    if label:
        txt(ax, x, y + r + 28, label, ha="center")


def _compressor_capsule(ax, x, y, r=95, label="压缩机", **kw):
    """方形压缩机:胶囊壳体(圆角竖矩形,宽 r、高 2r,与圆形等高)。"""
    rx = r / 2
    ax.add_patch(FancyBboxPatch((x - rx, y - r), r, 2 * r,
                                boxstyle=f"round,pad=0.02,rounding_size={rx}",
                                facecolor=FILL, edgecolor=LINE,
                                lw=LW_STRONG))
    if label:
        txt(ax, x, y + r + 28, label, ha="center")


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


HEX_SHAPES = ("rect_diag", "rect_x", "rect_zigzag7", "fan_coil")


# =========================
# 按尺寸生成端口的部件工厂
# =========================
def make_heat_exchanger(w=80, h=80, shape="rect_zigzag7", orient="h",
                        name="冷凝器", stub=0):
    """换热器部件(蒸发器/冷凝器通用):矩形外壳 + 4 种换热面画法。

    :param shape: 取值 ``HEX_SHAPES`` 之一:

      - ``rect_diag`` 矩形外壳 + 左上→右下对角线(简化符号)
      - ``rect_x`` 矩形外壳 + 两条对角线交叉(X 形换热面)
      - ``rect_zigzag7`` 矩形外壳 + 7 点之字盘管
      - ``fan_coil`` 矩形外壳 + 风机和盘管(室内机)

    :param orient: 之字盘管走向,"h" 左口→右口水平(默认),
        "v" 顶口→底口竖直(对角线与 X 旋转对称,不受影响)。

    左右端口可通过 stub 增加接管，顶部/底部端口落在边中点。
    """
    if shape not in HEX_SHAPES:
        raise ValueError(f"未知换热器 shape={shape!r},可用:"
                         f"{', '.join(HEX_SHAPES)}")
    if orient not in ("h", "v"):
        raise ValueError(f"未知 orient={orient!r},可用:'h' / 'v'")
    rx, ry = w / 2, h / 2
    ports = {"left": (-rx - stub, 0), "right": (rx + stub, 0),
             "top": (0, -ry), "bottom": (0, ry)}
    dirs = {"top": "n", "bottom": "s"}

    def draw(ax, x, y, label=None, **kw):
        ax.add_patch(Rectangle((x - rx, y - ry), w, h, facecolor=FILL,
                               edgecolor=LINE, lw=LW_PART))
        if shape == "rect_diag":
            line(ax, [(x - rx, y - ry), (x + rx, y + ry)], lw=LW_OUTLINE)
        elif shape == "rect_x":
            for s in (-1, 1):
                line(ax, [(x - rx, y - s * ry), (x + rx, y + s * ry)],
                     lw=LW_OUTLINE)
        elif shape == "fan_coil":
            cx = x - w * 0.32
            radius = min(w * 0.13, h * 0.28)
            ax.add_patch(Circle((cx, y), radius, facecolor=FILL,
                                edgecolor=LINE, lw=LW_FINE))
            for angle in (0, 120, 240):
                points = [(cx, y)] + [
                    (cx + radius * 0.85 * math.cos(math.radians(angle + a)),
                     y + radius * 0.85 * math.sin(math.radians(angle + a)))
                    for a in (0, 55)]
                ax.add_patch(Polygon(points, facecolor=FILL, edgecolor=LINE,
                                     lw=LW_FINE))
            for dy in (-0.28 * h, 0, 0.28 * h):
                line(ax, [(x - 0.08 * w, y + dy), (x + 0.40 * w, y + dy)],
                     lw=LW_PART)
        elif orient == "v":
            # 之字盘管(竖):顶口中点起笔,底口中点收笔,折点左右交替
            amp = rx * 0.42
            pts = [(x, y - ry)]
            for i in range(7):
                yi = y - ry + 2 * ry * (i + 0.5) / 7
                pts.append((x - amp if i % 2 == 0 else x + amp, yi))
            pts.append((x, y + ry))
            line(ax, pts, lw=LW_OUTLINE)
        else:
            # 之字盘管(横):左口中点起笔,右口中点收笔,折点上下交替
            amp = ry * 0.42
            pts = [(x - rx, y)]
            for i in range(7):
                xi = x - rx + 2 * rx * (i + 0.5) / 7
                pts.append((xi, y - amp if i % 2 == 0 else y + amp))
            pts.append((x + rx, y))
            line(ax, pts, lw=LW_OUTLINE)
        if stub:
            line(ax, [(x - rx - stub, y), (x - rx, y)], lw=LW_PART)
            line(ax, [(x + rx, y), (x + rx + stub, y)], lw=LW_PART)
        if label:
            txt(ax, x, y + ry + 26, label, boxed=True)

    return Part(name, draw, ports, dirs)


# =========================
# 部件实例(端口表)
# =========================
capillary = _part("毛细管", {"in": (0, -40), "out": (0, 40)}, _capillary,
                  dirs={"in": "n", "out": "s"})


def make_compressor(r=95, style="圆形", name="压缩机"):
    """压缩机部件,style 见 COMPRESSOR_STYLES。

    两种机身同一套端口:几何口 left/right/top/bottom,制冷口
    suction=top、discharge=bottom、vapor_inj=right。机身画法:圆形 =
    圆体 + 双弦;方形 = 胶囊壳体,宽 r、高 2r,与圆形等高。历史型式
    (离心/转子/轴流/往复/螺杆/涡旋)已移除,原型见
    references/compressor_symbols.py。

    r / style 在工厂里锁定,``add(..., r=..., style=...)`` 不会改外形或端口;
    改尺寸请重新调用本工厂。
    """
    if style not in COMPRESSOR_STYLES:
        raise ValueError(f"未知压缩机 style={style!r},可用:"
                         f"{', '.join(COMPRESSOR_STYLES)}")
    rx = r if style == "圆形" else r / 2

    def draw(ax, x, y, label=None, **kw):
        if style == "圆形":
            _compressor_circle(ax, x, y, r=r, label=label)
        else:
            _compressor_capsule(ax, x, y, r=r, label=label)

    ports = {"left": (-rx, 0), "right": (rx, 0),
             "top": (0, -r), "bottom": (0, r),
             "suction": (0, -r), "discharge": (0, r),
             "vapor_inj": (rx, 0)}
    dirs = {"top": "n", "bottom": "s", "suction": "n", "discharge": "s"}
    return Part(name, draw, ports, dirs)


compressor = make_compressor()


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


def make_four_way_round(r=40, mark=True, name="四通阀(圆菱形)"):
    """四通换向阀部件(圆体 + 内菱形),r 为圆体半径,端口随 r 缩放。

    端口落在菱形四角:exhaust 顶(D)/ condenser 右(C)/
    evaporator 底(E)/ suction 左(S);mark=True 在四端点外侧
    标注 D/S/C/E 口别字母。r 在工厂锁定;mark 可在 add() 时用同名词覆盖。
    """
    def draw(ax, x, y, label=None, mark=mark, **kw):
        # r 锁定在工厂;mark 等外观项可在 add() 时用同名词覆盖
        _four_way_round_valve(ax, x, y, label=label, r=r, mark=mark)

    return Part(name, draw,
                {"exhaust": (0, -r), "condenser": (r, 0),
                 "evaporator": (0, r), "suction": (-r, 0)},
                {"exhaust": "n", "condenser": "e",
                 "evaporator": "s", "suction": "w"})


four_way_round = make_four_way_round()


def make_globe_valve(w=64, h=48, stem=26, handle=44, name="截止阀"):
    """截止阀部件:左右对顶三角沙漏 + 阀杆(止于中点,不贯穿阀体) + 手轮横杆。

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


def make_expansion_valve_eng(r=34, name="电子膨胀阀"):
    """电子膨胀阀部件(工程画法:圆体 + 圆内 X,无执行机构)。端口 in/out。

    端口落在圆左右接管外端,沿水平方向(in=w, out=e),与电磁阀一致。
    """
    def draw(ax, x, y, label=None, **kw):
        _expansion_valve_eng(ax, x, y, label=label, r=r)

    return Part(name, draw,
                {"in": (-r - 12, 0), "out": (r + 12, 0)},
                {"in": "w", "out": "e"})


expansion_valve_eng = make_expansion_valve_eng()


def make_expansion_valve_x(r=10, orient="h", name="膨胀阀(圆X)"):
    """膨胀阀部件(圆 + 内接 X,参考图叠画法,圆周上无接管短管)。

    圆体与内接 X 旋转对称,水平/竖直管路通用;端口落在圆周上,
    管线分两段接入。orient="h" 时 in 西口/out 东口(流向西→东),
    orient="v" 时 in 顶口/out 底口(流向自上而下)。
    """
    if orient not in ("h", "v"):
        raise ValueError(f"未知 orient={orient!r},可用:'h' / 'v'")

    def draw(ax, x, y, label=None, **kw):
        ax.add_patch(Circle((x, y), r, facecolor=FILL, edgecolor=LINE,
                            lw=LW_OUTLINE))
        c = 0.72 * r
        for s in (-1, 1):
            line(ax, [(x - c, y - s * c), (x + c, y + s * c)],
                 lw=LW_PART)
        if label:
            txt(ax, x, y + r + 24, label)

    if orient == "h":
        ports = {"in": (-r, 0), "out": (r, 0)}
        dirs = {"in": "w", "out": "e"}
    else:
        ports = {"in": (0, -r), "out": (0, r)}
        dirs = {"in": "n", "out": "s"}
    return Part(name, draw, ports, dirs)


expansion_valve_x = make_expansion_valve_x()


def make_check_valve(w=56, h=32, stub=12, point="e", name="单向阀"):
    """单向阀部件:实心三角 + 尖端挡条,point 见 _check_valve。

    端口在贯穿接管两端:point="e" 时 in=西口 / out=东口,
    point="w" 时反向;也可 add() 后用法不变。
    """
    if point not in ("e", "w"):
        raise ValueError(f"未知 point={point!r},可用:'e' / 'w'")
    s = 1 if point == "e" else -1
    xin = -s * (w / 2 + stub)

    def draw(ax, x, y, label=None, **kw):
        _check_valve(ax, x, y, label=label, w=w, h=h, stub=stub, point=point)

    return Part(name, draw,
                {"in": (xin, 0), "out": (-xin, 0)},
                {"in": "w" if s > 0 else "e",
                 "out": "e" if s > 0 else "w"})


check_valve = make_check_valve()
check_valve_w = make_check_valve(point="w", name="单向阀(反向)")


def make_filter(w=72, h=36, n=7, stub=12, name="过滤器"):
    """过滤器部件:矩形 + 菱形网格。端口 in(西口)/ out(东口)。

    n 为每个方向的网格线数(含角点触线),默认 7;尺寸不合用工厂改。
    """
    def draw(ax, x, y, label=None, **kw):
        _filter(ax, x, y, label=label, w=w, h=h, n=n, stub=stub)

    return Part(name, draw,
                {"in": (-w / 2 - stub, 0), "out": (w / 2 + stub, 0)},
                {"in": "w", "out": "e"})


line_filter = make_filter()
filter = line_filter  # 兼容名,会覆盖内置 filter;新代码优先用 line_filter

BOWTIE_ACTUATORS = ("none", "dome", "solenoid", "tee")


def _bowtie_valve(ax, x, y, label=None, w=76, h=44, actuator="none",
                  stem=14, dome_r=21, sol_len=62, handle=30, **kw):
    """对顶三角阀(参考图画法):两竖边三角相对,阀杆自中心引出。

    actuator: "none"     裸阀(通用截断阀符号)
              "dome"     顶部闭合半圆穹顶(热力膨胀阀 / 经济器膨胀器)
              "solenoid" 电磁线圈(横杆 + Σ 折线)
              "tee"      T 形阀杆 + 手轮横杆(截止阀画法,不贯穿阀体)
    """
    if actuator not in BOWTIE_ACTUATORS:
        raise ValueError(f"未知 actuator={actuator!r},可用:"
                         f"{', '.join(BOWTIE_ACTUATORS)}")
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
    elif actuator == "tee":
        top = y - h / 2 - stem
        line(ax, [(x, y), (x, top)], lw=LW_PART)                   # 阀杆
        line(ax, [(x - handle / 2, top), (x + handle / 2, top)],
             lw=LW_STRONG)                                         # 手轮横杆
    if label:
        txt(ax, x, y + h / 2 + 26, label)


def make_bowtie_valve(w=76, h=44, actuator="none", stem=14, dome_r=21,
                      sol_len=62, handle=30, name="对顶三角阀"):
    """对顶三角阀部件(论文/参考图风格),actuator 见 _bowtie_valve。

    端口与 globe/solenoid/filter 等两口阀相反:in=东口 / out=西口
    (图内流向东→西)。w/h 在工厂锁定;actuator/stem 等外观项可在
    add() 时以同名词覆盖,如
    d.add(parts.bowtie_valve, "电磁阀", loc=..., actuator="solenoid")。
    """
    if actuator not in BOWTIE_ACTUATORS:
        raise ValueError(f"未知 actuator={actuator!r},可用:"
                         f"{', '.join(BOWTIE_ACTUATORS)}")

    def draw(ax, x, y, label=None, actuator=actuator, stem=stem,
             dome_r=dome_r, sol_len=sol_len, handle=handle, **kw):
        _bowtie_valve(ax, x, y, label=label, w=w, h=h, actuator=actuator,
                      stem=stem, dome_r=dome_r, sol_len=sol_len,
                      handle=handle)

    return Part(name, draw, {"in": (w / 2, 0), "out": (-w / 2, 0)},
                {"in": "e", "out": "w"})


bowtie_valve = make_bowtie_valve()
bowtie_valve_dome = make_bowtie_valve(actuator="dome", name="膨胀阀(穹顶)")
bowtie_valve_solenoid = make_bowtie_valve(actuator="solenoid",
                                          name="电磁阀(对顶三角)")
bowtie_valve_tee = make_bowtie_valve(actuator="tee",
                                     name="截止阀(对顶三角)")


def make_separator_utube(w=120, h=118, stub=16, flip=False,
                         name="气液分离器(U形管)"):
    """气液分离器(U 形管液封)部件,形状见 _separator_utube。

    端口:in 进气(壳顶短管)、out 出气(U 形管腿,穿壳顶引出)、
    drain 放油/排液(U 形弯底,向南引出)。
    flip=True 镜像:in 在东侧、out 为 U 形管左腿(进口在右、出口在左)。
    """
    y_port = -h / 2 - stub
    s = -1.0 if flip else 1.0

    def draw(ax, x, y, label=None, **kw):
        _separator_utube(ax, x, y, label=label, w=w, h=h, stub=stub,
                         flip=flip)

    return Part(name, draw,
                {"in": (s * -0.365 * w, y_port),
                 "out": (s * 0.435 * w, y_port),
                 "drain": (0, 0.463 * h)},
                {"in": "n", "out": "n", "drain": "s"})


separator_utube = make_separator_utube()


def make_oil_separator(w=64, h=176, stub=16, name="油分离器"):
    """油分离器部件:瘦长矩形壳 + 顶/底/侧三接管(参考图画法)。

    端口:left 进气(壳顶下 1/4,接压缩机排气)、top 出气(接四通阀 D 口)、
    bottom 回油口(经毛细管接回吸气管)。
    """
    y_port = -h / 2 - stub

    def draw(ax, x, y, label=None, **kw):
        _oil_separator(ax, x, y, label=label, w=w, h=h, stub=stub)

    return Part(name, draw,
                {"top": (0, y_port), "left": (-w / 2 - stub, -h / 4),
                 "bottom": (0, -y_port)},
                {"top": "n", "left": "w", "bottom": "s"})


oil_separator = make_oil_separator()


def make_capillary(w=18, h=80, n=5, name="毛细管"):
    """可调尺寸毛细管，in 顶部、out 底部；端口随高度变化。"""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("毛细管圈数必须为正整数")

    def draw(ax, x, y, label=None, **kw):
        _capillary(ax, x, y, label=label, w=w, h=h, n=n)

    return Part(name, draw, {"in": (0, -h / 2), "out": (0, h / 2)},
                {"in": "n", "out": "s"})


def make_fan_coil(w=120, h=64, stub=12, name="室内风机盘管"):
    """旧 Python 接口：复用换热器 fan_coil 样式，保留 in/out 端口。"""
    part = make_heat_exchanger(w=w, h=h, shape="fan_coil", stub=stub, name=name)

    def draw(ax, x, y, label=None, **kw):
        part.draw(ax, x, y, label=None)
        if label:
            txt(ax, x, y + h / 2 + 24, label)

    return Part(name, draw,
                {"in": part.port("left"), "out": part.port("right")},
                {"in": "w", "out": "e"})


def make_muffler(w=36, h=72, stub=12, name="消音器"):
    """消音器：矩形壳体，in 顶部、out 底部。"""
    def draw(ax, x, y, label=None, **kw):
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h,
                               facecolor=FILL, edgecolor=LINE, lw=LW_PART))
        line(ax, [(x, y - h / 2 - stub), (x, y - h / 2)], lw=LW_PART)
        line(ax, [(x, y + h / 2), (x, y + h / 2 + stub)], lw=LW_PART)
        if label:
            txt(ax, x + w / 2 + 18, y, label, ha="left")

    return Part(name, draw,
                {"in": (0, -h / 2 - stub), "out": (0, h / 2 + stub)},
                {"in": "n", "out": "s"})


def make_sensor(r=14, stub=12, mark="T", name="温度/压力传感器"):
    """圆圈 T/P 测点，单个底部 tap 口接测量支路，不表示贯通流道。"""
    if mark not in ("T", "P"):
        raise ValueError("传感器标记仅支持 T 或 P")

    def draw(ax, x, y, label=None, **kw):
        ax.add_patch(Circle((x, y), r, facecolor=FILL,
                            edgecolor=LINE, lw=LW_PART))
        txt(ax, x, y, mark, size=0.65 * r)
        line(ax, [(x, y + r), (x, y + r + stub)], lw=LW_PART)
        if label:
            txt(ax, x + r + 18, y, label, ha="left")

    return Part(name, draw, {"tap": (0, r + stub)}, {"tap": "s"})


def make_intermediate_hex(w=190, h=80, drop=0.275, name="中间换热器",
                          orient="h"):
    """中间换热器部件(过冷器/经济器为同一图元,角色由 label 区分)。

    矩形 + 上下两条水平通道线:主路沿下侧贯通(main_in 西口进 /
    main_out 东口出),副路沿上侧贯通(sub_in 东口进 / sub_out 西口出),
    两路逆流。orient="v" 时通道竖直:主路右侧上进下出、副路左侧
    下进上出。w/h 始终为外壳宽/高,drop 为通道距中心的偏移比例
    (水平时相对 h,竖直时相对 w,取值 0~0.5)。
    """
    if orient not in ("h", "v"):
        raise ValueError(f"未知 orient={orient!r},可用:'h' / 'v'")
    if orient == "h":
        offset = drop * h
        ports = {"main_in": (-w / 2, offset), "main_out": (w / 2, offset),
                 "sub_in": (w / 2, -offset), "sub_out": (-w / 2, -offset)}
        dirs = {"main_in": "w", "main_out": "e",
                "sub_in": "e", "sub_out": "w"}
    else:
        offset = drop * w
        ports = {"main_in": (offset, -h / 2), "main_out": (offset, h / 2),
                 "sub_in": (-offset, h / 2), "sub_out": (-offset, -h / 2)}
        dirs = {"main_in": "n", "main_out": "s",
                "sub_in": "s", "sub_out": "n"}

    def draw(ax, x, y, label=None, **kw):
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h,
                               facecolor=FILL, edgecolor=LINE,
                               lw=LW_STRONG))
        for inlet, outlet in (("main_in", "main_out"), ("sub_in", "sub_out")):
            line(ax, [(x + ports[key][0], y + ports[key][1])
                      for key in (inlet, outlet)], lw=LW_OUTLINE)
        if label:
            txt(ax, x, y, label, boxed=True)

    return Part(name, draw, ports, dirs)


intermediate_hex = make_intermediate_hex()
