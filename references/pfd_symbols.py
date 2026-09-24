# -*- coding: utf-8 -*-
"""
标准 PFD 符号库（ISA-5.1 / ISO 10628 风格），基于 schemdraw 实现
================================================

所有符号都是"基础几何拼装"，与 pyflowsheet 的 draw() 哲学一致（用
svgwrite/schemdraw 基础图元手搓设备符号），但渲染走 schemdraw 的
Segment/Element。可直接 `from pfd_symbols import *` 后调用。

符号清单（均为标准 PFD 约定）：
  compressor()      压缩机：圆 + 型式标记，style ∈
                    {centrifugal 双斜线 | rotor 辐线 | axial | recip | screw | scroll}
  valve()           阀 / EEV：蝶形 bowtie（标准节流阀符号）
  heat_exchanger()  换热器：圆 / 矩形 + 内部标记，shape ∈
                    {circle 圆+盘管 | rect 矩形+盘管 | rect_diag 矩形+左上→右下对角线}
  vessel()          立式容器 / 闪发罐：胶囊形（矩形体 + 上下半圆穹顶）+ 液位线
  plate_hex()       板式换热器：矩形 + X（两介质交叉）+ 板片横线
  pump()            泵：圆 + 内部三角形（标准离心泵符号，备用）

使用前各脚本需先设置中文字体：
  plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
"""

import math

import schemdraw
import schemdraw.elements as elm
from schemdraw.segments import Segment

LW = 1.8          # 管路线宽 / 设备线宽
FS_LABEL = 15     # 部件标签字号
FS_TAG = 11       # 状态点编号字号


# ----------------------------- 基础图元 ----------------------------- #


class Poly(elm.Element):
    """自定义折线图元：pts 为首点归零后的相对坐标"""

    def __init__(self, pts, lw=LW, color="black", **kwargs):
        super().__init__(**kwargs)
        self._userparams["theta"] = 0          # 不与上一图元的方向耦合
        self.anchors["start"] = (0, 0)
        self.anchors["end"] = pts[-1]
        self.anchors["center"] = (pts[-1][0] / 2.0, pts[-1][1] / 2.0)
        self.segments.append(Segment(pts, lw=lw, color=color))


def polyline(d, pts, lw=LW, color="black"):
    """折线（一个图元，拐角处自然连接）"""
    x0, y0 = pts[0]
    rel = [(x - x0, y - y0) for (x, y) in pts]
    d += Poly(rel, lw=lw, color=color).at((x0, y0))


def rect(d, x0, y0, x1, y1, lw=LW):
    """矩形设备框"""
    polyline(d, [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], lw=lw)


def circle(d, cx, cy, r, lw=LW):
    """圆（折线逼近，避免依赖具体版本的内置图元名）"""
    pts = [(cx + r * math.cos(2 * math.pi * i / 180.0),
            cy + r * math.sin(2 * math.pi * i / 180.0)) for i in range(181)]
    polyline(d, pts, lw=lw)


def text(d, x, y, s, fs=FS_LABEL, color="black"):
    d += elm.Label().at((x, y)).label(s, fontsize=fs, color=color)


def arrow(d, a, b, lw=LW):
    d += elm.Arrow().at(a).to(b).color("black").linewidth(lw)


def flow(d, pts, lw=LW):
    """带单个流向箭头的管路：折线 + 最长管段中点方向箭头（每条线仅一个箭头）。"""
    polyline(d, pts, lw=lw)
    if len(pts) >= 2:
        segs = list(zip(pts[:-1], pts[1:]))
        (a, b) = max(segs, key=lambda ab: abs(ab[0][0] - ab[1][0]) + abs(ab[0][1] - ab[1][1]))
        m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        u = ((b[0] - a[0]) / 2.0 * 0.28, (b[1] - a[1]) / 2.0 * 0.28)
        arrow(d, (m[0] - u[0], m[1] - u[1]), (m[0] + u[0], m[1] + u[1]), lw=lw)


# ----------------------------- 标准 PFD 符号 ----------------------------- #


def _dome(d, cx, cy_dome, rx, up=True, lw=LW):
    """半圆穹顶弧（折线近似）。up=True 向上鼓，False 向下鼓。"""
    rng = range(0, 181, 6) if up else range(180, 361, 6)
    pts = [(cx + rx * math.cos(math.radians(a)),
            cy_dome + rx * math.sin(math.radians(a))) for a in rng]
    polyline(d, pts, lw=lw)


COMPRESSOR_STYLES = ("rotor", "centrifugal", "axial", "recip", "screw", "scroll")


def compressor(d, cx, cy, r=1.05, tag="压缩机", fs=FS_LABEL,
               tag_xy=None, n_blades=3, style="rotor"):
    """压缩机（标准 PFD）：圆形壳体 + 内部型式标记。返回圆心四向锚点。

    style 取值（COMPRESSOR_STYLES）：
      "centrifugal" 离心式：圆 + 两条对称内收斜线（上端靠内、下端外张）
      "rotor"       通用旋转式：圆 + n_blades 条转子辐线（型式无关）
      "axial"       轴流式：圆 + 环形分布斜叶片
      "recip"       往复式：圆 + 活塞矩形 + 连杆
      "screw"       螺杆式：圆 + 两个相切内圆（8 字形啮合转子）
      "scroll"      涡旋式：圆 + 阿基米德螺旋

    注：圆形壳体是 ISA / ISO 体系里压缩机的通用外框，内部标记用于区分型式；
    不同院所的画法略有出入，位号（如 C-101）才是最终定型的依据。
    """
    circle(d, cx, cy, r)

    if style == "centrifugal":
        # 离心式：圆 + 两条对称弦线（离心叶轮 / 扩压流道之示意）。
        # 两条弦的**两端都精确落在圆周上**（用 x²+y²=r² 反解 y），
        # 构成"上窄下宽"的内接梯形——上端靠内（±0.40r），下端外张（±0.66r）。
        for sx in (-1.0, 1.0):
            ux = 0.40 * r
            uy = math.sqrt(r * r - ux * ux)        # 上端贴圆周
            lx = 0.66 * r
            ly = -math.sqrt(r * r - lx * lx)       # 下端贴圆周
            polyline(d, [(cx + sx * ux, cy + uy), (cx + sx * lx, cy + ly)], lw=1.5)
    elif style == "rotor":
        for k in range(n_blades):
            ang = math.radians(90.0 + 360.0 * k / n_blades)
            p0 = (cx + 0.34 * r * math.cos(ang), cy + 0.34 * r * math.sin(ang))
            p1 = (cx + 0.96 * r * math.cos(ang), cy + 0.96 * r * math.sin(ang))
            polyline(d, [p0, p1], lw=1.3)
    elif style == "axial":
        for k in range(5):
            a0 = math.radians(18.0 + 72.0 * k)
            a1 = a0 + math.radians(46.0)
            polyline(d, [(cx + 0.30 * r * math.cos(a0), cy + 0.30 * r * math.sin(a0)),
                         (cx + 0.90 * r * math.cos(a1), cy + 0.90 * r * math.sin(a1))],
                     lw=1.3)
    elif style == "recip":
        # 活塞（扁矩形）+ 连杆 + 曲柄销
        pw, ph = 0.64 * r, 0.30 * r
        rect(d, cx - pw / 2, cy + 0.06 * r, cx + pw / 2, cy + 0.06 * r + ph, lw=1.3)
        rod_bot = cy - 0.66 * r
        polyline(d, [(cx, cy + 0.06 * r), (cx, rod_bot)], lw=1.3)
        circle(d, cx, rod_bot - 0.14 * r, 0.14 * r, lw=1.3)
    elif style == "screw":
        cr = 0.42 * r
        circle(d, cx - cr, cy, cr, lw=1.3)
        circle(d, cx + cr, cy, cr, lw=1.3)
    elif style == "scroll":
        pts = []
        n = 240
        for i in range(n + 1):
            th = 2.4 * math.pi * i / n
            rr = r * 0.16 + r * 0.66 * (th / (2.4 * math.pi))
            pts.append((cx + rr * math.cos(th), cy + rr * math.sin(th)))
        polyline(d, pts, lw=1.3)
    else:
        raise ValueError(
            f"未知压缩机符号 style={style!r}，可用：{', '.join(COMPRESSOR_STYLES)}")

    text(d, *(tag_xy or (cx, cy + r + 0.42)), tag, fs=fs)
    return {"left": (cx - r, cy), "right": (cx + r, cy),
            "top": (cx, cy + r), "bottom": (cx, cy - r)}


def valve(d, cx, cy, w=0.86, h=0.92):
    """阀 / EEV（标准 PFD）：蝶形 bowtie（两三角对顶）。"""
    polyline(d, [(cx - w / 2, cy + h / 2), (cx - w / 2, cy - h / 2), (cx, cy),
                 (cx - w / 2, cy + h / 2)])
    polyline(d, [(cx + w / 2, cy + h / 2), (cx + w / 2, cy - h / 2), (cx, cy),
                 (cx + w / 2, cy + h / 2)])


def heat_exchanger(d, cx, cy, r=1.20, tag="换热器", fs=FS_LABEL,
                   label_above=False, tag_xy=None, shape="circle", w=2.4, h=2.4):
    """换热器（标准 PFD）：圆 / 矩形 外壳 + 内部介质标记。

    - shape="circle"（默认）：圆 + 5 点之字盘管（冷凝器/蒸发器通用）。
    - shape="rect"：矩形外壳 + 之字盘管（波纹数与圆型一致，2 波，不加倍）。
    - shape="rect_diag"：矩形外壳 + **左上→右下对角线**（简化换热器符号，
        不画盘管）。w/h 可独立给定——经济器/过冷器常用竖长矩形（h > w）。
    标签默认在符号下方；label_above=True 改到上方；tag_xy 可强制指定位置。
    """
    rx, ry = w / 2.0, h / 2.0

    if shape == "circle":
        circle(d, cx, cy, r)
        xs, amp, half = r * 0.78, r * 0.42, r
    else:
        rect(d, cx - rx, cy - ry, cx + rx, cy + ry)
        xs, amp, half = rx * 0.78, ry * 0.42, ry

    if shape == "rect_diag":
        # 简化换热器符号：仅一条对角线（左上角 -> 右下角），无盘管
        polyline(d, [(cx - rx, cy + ry), (cx + rx, cy - ry)], lw=1.3)
    else:
        # 5 点之字盘管（与圆型同形，2 波），按比例缩放进外壳
        pts = [
            (cx - xs,       cy),
            (cx - xs * 0.5, cy - amp),
            (cx,            cy + amp),
            (cx + xs * 0.5, cy - amp),
            (cx + xs,       cy),
        ]
        polyline(d, pts, lw=1.3)

    if tag_xy is not None:
        text(d, tag_xy[0], tag_xy[1], tag, fs=fs)
    else:
        ly = (cy + half + 0.35) if label_above else (cy - half - 0.35)
        text(d, cx, ly, tag, fs=fs)


def vessel(d, cx, cy, w=1.10, h=2.40, tag="容器", fs=FS_LABEL,
           liquid=0.42, tag_xy=None):
    """立式容器 / 闪发罐（标准 PFD）：矩形体 + 上下半圆穹顶（胶囊）+ 液位线。

    liquid ∈ [0,1] 控制液位线在容器内的相对高度（0=底, 1=顶）。
    标签默认在容器右侧；tag_xy 可强制指定位置。
    """
    rx = w / 2
    body_top = cy + h / 2 - rx
    body_bot = cy - h / 2 + rx
    polyline(d, [(cx - rx, body_bot), (cx - rx, body_top)])
    polyline(d, [(cx + rx, body_bot), (cx + rx, body_top)])
    _dome(d, cx, body_top, rx, up=True)
    _dome(d, cx, body_bot, rx, up=False)
    y_liq = body_bot + liquid * (body_top - body_bot)
    polyline(d, [(cx - rx, y_liq), (cx + rx, y_liq)], lw=1.1)
    text(d, *(tag_xy or (cx + rx + 0.95, cy)), tag, fs=fs)


def plate_hex(d, cx, cy, w=1.10, h=2.00, tag="板换", fs=FS_LABEL, tag_xy=None):
    """板式换热器（标准 PFD）：矩形 + X（两介质交叉）+ 板片横线。"""
    rx = w / 2
    rect(d, cx - rx, cy - h / 2, cx + rx, cy + h / 2)
    polyline(d, [(cx - rx, cy + 0.375 * h), (cx + rx, cy - 0.375 * h)])
    polyline(d, [(cx - rx, cy - 0.375 * h), (cx + rx, cy + 0.375 * h)])
    for i in range(3):
        y = cy - 0.2 * h + (0.4 * h) / 2 * i
        polyline(d, [(cx - rx, y), (cx + rx, y)], lw=1.1)
    text(d, *(tag_xy or (cx + rx + 0.95, cy)), tag, fs=fs)


def pump(d, cx, cy, r=1.0, tag="泵", fs=FS_LABEL, tag_xy=None):
    """泵（标准 PFD）：圆 + 内部三角形（离心泵符号，三角指向排液方向）。"""
    circle(d, cx, cy, r)
    polyline(d, [(cx - r * 0.5, cy - r * 0.45),
                 (cx + r * 0.55, cy),
                 (cx - r * 0.5, cy + r * 0.45),
                 (cx - r * 0.5, cy - r * 0.45)], lw=1.3)
    text(d, *(tag_xy or (cx, cy + r + 0.42)), tag, fs=fs)
