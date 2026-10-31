# -*- coding: utf-8 -*-
"""VRF (多联机) 制冷剂系统图元库 + VRF 系统图生成。

参考 draw_gmv.py 的纯 SVG 手绘风格:所有坐标手工排布,图元以函数
形式追加 SVG 片段,最终 join 成一张矢量图。

本文件是 references/ 下的原型脚本,不是 rrplot 库的一部分:
它不依赖 matplotlib,只做 SVG 字符串拼装。用法(在本目录下)::

    from vrfpart import render_vrf_system, render_gmv
    render_vrf_system()            # -> references/VRF多联机系统图.svg
    render_gmv()                   # -> references/GMV制冷剂系统原理图.svg
    render_vrf_system("my.svg")    # 自定义路径

图元清单:
    compressor / scroll_compressor   压缩机(圆+双弦涡旋符号)
    four_way_valve                   四通阀(圆+四叶)
    oil_separator                    油分离器(竖筒+三管)
    receiver                         气液分离器(矩形+斜线)
    heat_exchanger_rect              板翅换热器(矩形+斜线)
    fan_coil                         室内风机盘管(矩形+盘管+双弧风机)
    eev                              电子膨胀阀(圆+X)
    capillary                        毛细管(之字线)
    solenoid_valve / check_valve    电磁阀 / 单向阀
    filter_drier                     过滤器(网格矩形)
    service_valve                    服务阀(T 形)
    muffer                           消音器
    sensor_circle                    T/P 传感器(圆圈)
    flow_arrow                       流向箭头(实线=制冷, 虚线=制热)

风格:白底 + 深灰线 + 双色调箭头,与 GMV 系统原理图一致。
"""
import math
from html import escape
from pathlib import Path
from typing import List, Optional

# ------------------------------------------------------------------
# 颜色常量
# ------------------------------------------------------------------
INK = "#172e3e"          # 文字
PIPE = "#344b58"         # 管路
COMP = "#263b48"         # 部件轮廓
FLOW = "#101820"         # 流向箭头
FILL = "white"
MESH = "#70838b"

DASH = "10 7"


# ------------------------------------------------------------------
# SVG Builder
# ------------------------------------------------------------------
class Builder:
    """收集 SVG 片段,最终 join。每次生成一张图用一个 Builder。"""

    def __init__(self, width: int, height: int, title: str, desc: str):
        self.w, self.h = width, height
        self.title = title
        self.desc = desc
        self.parts: List[str] = []

    # ---- 基础图元 ----
    def path(self, d: str, cls: str = "pipe"):
        self.parts.append(f'<path class="{cls}" d="{d}"/>')

    def line(self, x1, y1, x2, y2, cls: str = "pipe"):
        d = f"M{x1},{y1} H{x2}" if y1 == y2 else f"M{x1},{y1} L{x2},{y2}"
        self.path(d, cls)

    def rect(self, x, y, w, h, cls: str = "component", rx: float = 0):
        self.parts.append(
            f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'
        )

    def circle(self, cx, cy, r, cls: str = "component"):
        self.parts.append(
            f'<circle class="{cls}" cx="{cx}" cy="{cy}" r="{r}"/>'
        )

    def ellipse(self, cx, cy, rx, ry, cls: str = "component"):
        self.parts.append(
            f'<ellipse class="{cls}" cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}"/>'
        )

    def text(self, x, y, s: str, size: int = 16, anchor: str = "start",
             vertical: bool = False):
        if vertical:
            spans = "".join(
                f'<tspan x="{x}" y="{y + size + i * size}">{escape(c)}</tspan>'
                for i, c in enumerate(s)
            )
            self.parts.append(
                f'<text font-size="{size}" text-anchor="middle">{spans}</text>'
            )
        else:
            self.parts.append(
                f'<text x="{x}" y="{y}" font-size="{size}" '
                f'text-anchor="{anchor}">{escape(s)}</text>'
            )

    def arrow(self, x1, y1, x2, y2, dashed: bool = False):
        cls = "flow dashed" if dashed else "flow"
        self.parts.append(
            f'<path class="{cls}" d="M{x1},{y1} L{x2},{y2}" '
            f'marker-end="url(#arrow)"/>'
        )

    # ---- VRF 图元 ----
    def compressor(self, x, y, label="压缩机", r: int = 48, style: str = "circle"):
        """压缩机:圆或椭圆 + 双弦涡旋符号。

        style: "circle"(圆+上下双弦) / "ellipse"(椭圆+左右双弦)
        """
        if style == "circle":
            self.circle(x, y, r, "component")
            # 上下双弦
            y_top = y - r * 0.45
            y_bot = y + r * 0.45
            cx_top = math.sqrt(r ** 2 - (r * 0.45) ** 2)
            cx_bot = cx_top
            self.parts.append(
                f'<path d="M{x - cx_top:.1f} {y_top:.1f} '
                f'Q{x} {y - r * 0.1:.1f} {x + cx_top:.1f} {y_top:.1f}" '
                f'fill="none" stroke="{COMP}" stroke-width="1.2"/>'
            )
            self.parts.append(
                f'<path d="M{x - cx_bot:.1f} {y_bot:.1f} '
                f'Q{x} {y + r * 0.1:.1f} {x + cx_bot:.1f} {y_bot:.1f}" '
                f'fill="none" stroke="{COMP}" stroke-width="1.2"/>'
            )
        else:  # ellipse
            rx, ry = r * 0.75, r
            self.ellipse(x, y, rx, ry, "component")
            # 左右双弦(涡旋)
            y_c1 = y - ry * 0.45
            y_c2 = y + ry * 0.45
            self.parts.append(
                f'<path d="M{x - rx * 0.6:.1f} {y_c1:.1f} '
                f'Q{x} {y_c1 - ry * 0.15:.1f} {x + rx * 0.6:.1f} {y_c1:.1f}" '
                f'fill="none" stroke="{COMP}" stroke-width="1.2"/>'
            )
            self.parts.append(
                f'<path d="M{x - rx * 0.6:.1f} {y_c2:.1f} '
                f'Q{x} {y_c2 + ry * 0.15:.1f} {x + rx * 0.6:.1f} {y_c2:.1f}" '
                f'fill="none" stroke="{COMP}" stroke-width="1.2"/>'
            )
        if label:
            self.text(x, y + r + 14, label, 15, "middle")

    def four_way_valve(self, x, y, label="四通阀", r: int = 18):
        """四通阀:圆 + 四叶(花瓣)曲线。"""
        self.circle(x, y, r, "component")
        mid = r * 0.72
        self.parts.append(
            f'<path d="M{x} {y - r} '
            f'Q{x} {y - mid} {x - mid} {y} '
            f'Q{x} {y + mid} {x} {y + r} '
            f'Q{x} {y + mid} {x + mid} {y} '
            f'Q{x} {y - mid} {x} {y - r}" '
            f'fill="white" stroke="{COMP}" stroke-width="1.4"/>'
        )
        if label:
            self.text(x + r + 4, y - 2, label, 14, "start")

    def oil_separator(self, x, y, label="油分离器", w: int = 22, h: int = 56):
        """油分离器:竖筒 + 顶/底/侧三管。"""
        self.rect(x - w / 2, y - h / 2, w, h, "component")
        # 顶部管
        self.line(x, y - h / 2 - 8, x, y - h / 2)
        # 底部管
        self.line(x, y + h / 2, x, y + h / 2 + 8)
        # 侧管
        y_side = y - h * 0.25
        self.line(x - w / 2 - 8, y_side, x - w / 2, y_side)
        if label:
            self.text(x + w / 2 + 4, y - 4, label, 13, "start")

    def receiver(self, x, y, label="气液分离器", w: int = 52, h: int = 100):
        """气液分离器:矩形 + 内部斜线。"""
        self.rect(x, y - h / 2, w, h, "component")
        cx = x + w / 2
        # 两条对角线
        self.parts.append(
            f'<path d="M{cx - 6} {y - h / 2 + 6} '
            f'L{cx + w - 6} {y + h / 2 - 6}" '
            f'fill="none" stroke="{COMP}" stroke-width="1.0"/>'
        )
        # 内部液面线
        self.line(cx, y + h * 0.2, cx + w, y + h * 0.2, "pipe")
        if label:
            self.text(cx + 4, y, label, 13, "middle")

    def heat_exchanger(self, x, y, label="换热器", w: int = 100, h: int = 40,
                       n_slats: int = 5):
        """板翅换热器:矩形 + 内部斜线(翅片)。"""
        self.rect(x, y, w, h, "component")
        for i in range(n_slats):
            xx = x + 10 + i * (w - 20) / max(n_slats - 1, 1)
            self.parts.append(
                f'<path d="M{xx:.1f} {y} L{xx - 8:.1f} {y + h}" '
                f'fill="none" stroke="{COMP}" stroke-width="1.0"/>'
            )
        if label:
            self.text(x + w / 2, y - 10, label, 13, "middle")

    def fan_coil(self, x, y, label="室内机", w: int = 90, h: int = 48):
        """风机盘管:矩形 + 盘管 + 风机(双弧)。"""
        self.rect(x, y - h / 2, w, h, "component")
        # 盘管:水平线
        for i in range(3):
            yy = y - h / 2 + 8 + i * (h - 16) / 2
            self.line(x + 22, yy, x + w - 6, yy, "pipe")
        # 风机:双弧
        cx_f = x + 12
        self.parts.append(
            f'<path d="M{cx_f - 9} {y - 12} A13 13 0 0 1 {cx_f + 9} {y - 12} '
            f'M{cx_f - 9} {y + 12} A13 13 0 0 0 {cx_f + 9} {y + 12}" '
            f'fill="none" stroke="{COMP}" stroke-width="1.2"/>'
        )
        self.circle(cx_f, y, 2, "component")
        if label:
            self.text(x + w / 2, y - h / 2 - 8, label, 13, "middle")

    def eev(self, x, y, label="电子膨胀阀", r: int = 10):
        """电子膨胀阀:圆 + X。"""
        self.circle(x, y, r, "component")
        d = r * 0.7071
        self.parts.append(
            f'<path d="M{x - d:.1f},{y - d:.1f} L{x + d:.1f},{y + d:.1f} '
            f'M{x - d:.1f},{y + d:.1f} L{x + d:.1f},{y - d:.1f}" '
            f'fill="none" stroke="{COMP}" stroke-width="1.4"/>'
        )
        if label:
            self.text(x, y + r + 14, label, 12, "middle")

    def capillary(self, x, y_top, y_bot, label="毛细管"):
        """毛细管:白色遮罩 + 之字线。"""
        h = y_bot - y_top
        self.rect(x - 7, y_top, 14, h, "component")
        offsets = [0, -5, 5, -5, 5, -5, 5, 0]
        pts = " ".join(
            f"{x + dx},{y_top + h * i / (len(offsets) - 1):.1f}"
            for i, dx in enumerate(offsets)
        )
        self.parts.append(
            f'<polyline points="{pts}" fill="none" '
            f'stroke="{COMP}" stroke-width="1.4"/>'
        )
        if label:
            self.text(x + 10, (y_top + y_bot) / 2 + 4, label, 11, "start")

    def solenoid_valve(self, x, y, label="电磁阀", vertical: bool = True):
        """电磁阀:对顶三角形 + 顶部线圈。"""
        if vertical:
            # 对顶三角
            self.parts.append(
                f'<path d="M{x - 8} {y - 10} L{x + 8} {y + 10} '
                f'M{x + 8} {y - 10} L{x - 8} {y + 10} '
                f'L{x - 8} {y - 10} Z" '
                f'fill="white" stroke="{COMP}" stroke-width="1.4"/>'
            )
            # 线圈(顶部小矩形)
            self.rect(x - 5, y - 20, 10, 10, "component")
            self.line(x, y - 20, x, y - 28)
        else:
            self.parts.append(
                f'<path d="M{x - 10} {y - 8} L{x + 10} {y + 8} '
                f'M{x + 10} {y - 8} L{x - 10} {y + 8} '
                f'L{x - 10} {y - 8} Z" '
                f'fill="white" stroke="{COMP}" stroke-width="1.4"/>'
            )
            self.rect(x - 20, y - 5, 10, 10, "component")
        if label:
            self.text(x + (14 if not vertical else 10), y + 4, label, 12, "start")

    def check_valve(self, x, y, label="单向阀", direction: str = "up"):
        """单向阀:三角形(流向由方向决定)。"""
        if direction == "up":
            tri = f"M{x} {y - 8} L{x + 7} {y + 6} L{x - 7} {y + 6} Z"
        else:
            tri = f"M{x} {y + 8} L{x + 7} {y - 6} L{x - 7} {y - 6} Z"
        self.parts.append(
            f'<path d="{tri}" fill="white" stroke="{COMP}" stroke-width="1.4"/>'
        )
        if label:
            self.text(x + 10, y, label, 11, "start")

    def filter_drier(self, x, y, label="过滤器", vertical: bool = True):
        """过滤器:网格填充矩形。"""
        if vertical:
            w, h = 16, 30
        else:
            w, h = 30, 16
        self.parts.append(
            f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" '
            f'fill="url(#mesh)" stroke="{COMP}" stroke-width="1.2"/>'
        )
        if label:
            dx = 10 if not vertical else 12
            self.text(x + dx, y + 4, label, 11, "start")

    def service_valve(self, x, y, label="服务阀"):
        """服务阀:Z 形 + 顶部短管。"""
        self.parts.append(
            f'<path d="M{x - 12} {y - 8} V{y + 8} '
            f'L{x + 12} {y - 8} V{y + 8} '
            f'M{x} {y - 1} V{y - 16} M{x - 8} {y - 16} H{x + 8}" '
            f'fill="none" stroke="{COMP}" stroke-width="1.4"/>'
        )
        if label:
            self.text(x, y - 20, label, 12, "middle")

    def muffer(self, x, y, label="消音器"):
        """消音器:小矩形。"""
        self.rect(x - 5, y - 8, 10, 16, "component")
        if label:
            self.text(x + 10, y + 4, label, 11, "start")

    def sensor(self, x, y, text="T", r: int = 9, size: int = 11,
               label=None, label_dx: int = 14):
        """T/P 传感器:圆圈 + 字母 + 可选标签。"""
        self.circle(x, y, r, "component")
        self.text(x, y + 1, text, size, "middle")
        if label:
            self.text(x + label_dx, y + r + 10, label, 11, "start")

    def legend(self, x, y, w: int = 220, h: int = 52):
        """图例框:制冷实线 + 制热虚线。"""
        self.rect(x, y, w, h, "component", rx=4)
        self.arrow(x + 12, y + 18, x + 68, y + 18, dashed=False)
        self.text(x + 78, y + 22, "制冷时制冷剂流向", 13, "start")
        self.arrow(x + 12, y + 40, x + 68, y + 40, dashed=True)
        self.text(x + 78, y + 44, "制热时制冷剂流向", 13, "start")

    def mullion_border(self, x, y, w, h, label="室外机", rx: int = 4,
                       dashed: bool = False):
        """室外机边框。"""
        style = ' stroke-dasharray="6 4"' if dashed else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="none" stroke="{PIPE}" stroke-width="2.0"{style}/>'
        )
        if label:
            self.text(x + w / 2, y + 16, label, 15, "middle")

    # ---- 输出 ----
    def to_svg(self) -> str:
        styles = (
            "<style>"
            f'text{{font-family:"Noto Sans CJK SC","Microsoft YaHei",'
            f'sans-serif;fill:{INK}}}'
            f'.pipe{{fill:none;stroke:{PIPE};stroke-width:1.45;'
            f'stroke-linejoin:round;stroke-linecap:round}}'
            f'.component{{fill:{FILL};stroke:{COMP};stroke-width:1.6}}'
            f'.symbol{{fill:{FILL};stroke:{COMP};stroke-width:1.6;'
            f'stroke-linejoin:round}}'
            f'.flow{{fill:none;stroke:{FLOW};stroke-width:3.3}}'
            f'.dashed{{stroke-dasharray:{DASH}}}'
            "</style>"
        )
        defs = (
            "<defs>"
            '<pattern id="mesh" width="8" height="8" patternUnits="userSpaceOnUse">'
            f'<rect width="8" height="8" fill="{FILL}"/>'
            f'<path d="M0 0L8 8M8 0L0 8" stroke="{MESH}" stroke-width=".55"/>'
            "</pattern>"
            '<marker id="arrow" viewBox="0 0 12 10" refX="10" refY="5" '
            'markerWidth="7" markerHeight="6" orient="auto">'
            f'<path d="M0 0L12 5L0 10Z" fill="{FLOW}"/>'
            "</marker>"
            f"{styles}"
            "</defs>"
        )
        header = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" '
            f'aria-labelledby="title desc">'
            f'<title id="title">{escape(self.title)}</title>'
            f'<desc id="desc">{escape(self.desc)}</desc>'
            f"{defs}"
            f'<rect width="{self.w}" height="{self.h}" fill="{FILL}"/>'
        )
        body = "\n".join(self.parts)
        return f"{header}\n<g>\n{body}\n</g>\n</svg>"


# ------------------------------------------------------------------
# VRF 系统图:与 GMV 风格一致(双系统,制冷/制热箭头)
# ------------------------------------------------------------------

OUT = Path(__file__).resolve().parent      # 原型脚本:产物落在 references/ 自身


def render_vrf_system(out_path: Optional[str] = None) -> Path:
    """生成 VRF 多联机系统图 SVG。

    布局(与 GMV 一致):
        上部:室外机外壳,含 2 台变频压缩机(涡旋符号)、
              油分离器、气液分离器、四通阀、板翅换热器、
              毛细管、电子膨胀阀、过滤器、服务阀、T/P 传感器
        下部:室内机外壳(虚线框),3 台风机盘管,
              各带 EEV + 毛细管,分歧管分配
        箭头:实线=制冷流向,虚线=制热流向
    """
    if out_path is None:
        out_path = str(OUT / "VRF多联机系统图.svg")
    out = Path(out_path)

    W, H = 1100, 880
    b = Builder(
        W, H,
        "VRF 多联机制冷剂系统原理图",
        "变频多联机(VRF)系统:2台变频涡旋压缩机 + 3台室内风机盘管。"
        "实线箭头=制冷流向,虚线箭头=制热流向。仅作原理示意,未作工程校核。",
    )

    # ===================== 室外机区域 =====================
    # 外壳
    ox, oy, ow, oh = 50, 30, 1000, 330
    b.mullion_border(ox, oy, ow, oh, "室外机(变频主机)", rx=5)

    # --- 管路(先画管路,部件叠加) ---
    # 主管路:压缩机1 → 四通阀 → 换热器
    c1x, c1y = 170, 195
    c2x, c2y = 480, 195
    fwv_x, fwv_y = 340, 230

    # 压缩机1 排气 → 四通阀
    b.path(f"M{c1x + 48} {c1y} H{fwv_x - 18}")
    # 四通阀 → 换热器
    b.path(f"M{fwv_x + 18} {fwv_y} H{640}")
    # 换热器 → 分歧管(向下)
    b.path(f"M{640 + 100} {120} V{fwv_y} H{fwv_x + 18}")

    # 压缩机2 → 油分离器 → 四通阀
    b.path(f"M{c2x + 42} {c2y} V{c2y - 60} H{570}")
    b.path(f"M{570} {195 - 60 + 50} V{fwv_y}")

    # 分歧管(向下到室内机)
    b.path(f"M{640 + 100} {120 + 40} V{370}")

    # 回气管(虚线,从室内机回到压缩机吸气)
    b.path(f"M{640 + 100 + 20} {370} V{oy + oh}")

    # --- 部件 ---
    # 压缩机1(涡旋)
    b.compressor(c1x, c1y, "变频压缩机1", r=48)
    # 压缩机2(涡旋)
    b.compressor(c2x, c2y, "变频压缩机2", r=44)

    # 油分离器
    b.oil_separator(570, 135, "油分离器", w=20, h=52)

    # 四通阀
    b.four_way_valve(fwv_x, fwv_y, "四通阀", r=17)

    # 气液分离器
    b.receiver(570, 300, "气液分离器", w=50, h=88)

    # 板翅换热器
    b.heat_exchanger(640, 100, "室外换热器", w=100, h=40)

    # 毛细管
    b.capillary(680, 170, 210, "毛细管")

    # 电子膨胀阀
    b.eev(730, 190, "电子膨胀阀", r=10)

    # 过滤器
    b.filter_drier(620, 220, "过滤器", vertical=True)

    # 服务阀(左侧)
    b.service_valve(90, 290, "液管服务阀")
    b.service_valve(90, 345, "气管服务阀")

    # 传感器
    b.sensor(380, 295, "T", r=8, label="低压传感器")
    b.sensor(620, 295, "P", r=8, label="高压传感器")

    # 单向阀
    b.check_valve(600, 265, "单向阀", direction="up")

    # 消音器
    b.muffer(760, 250, "消音器")

    # ===================== 室内机区域 =====================
    iy = 400
    ih = 380
    b.mullion_border(50, iy, 1000, ih, "", rx=5, dashed=True)
    b.text(550, iy + 18, "室内机(风机盘管 ×3)", 15, "middle")

    # 分歧管(从室外机下来)
    main_x = 380
    b.path(f"M{main_x} {iy} V{iy + 260}")
    # 回气总管
    b.path(f"M{main_x + 20} {iy} V{iy + 260}")

    # 三台室内机
    fc_w, fc_h = 100, 48
    fc_ys = [iy + 65, iy + 150, iy + 235]
    for idx, fy in enumerate(fc_ys, 1):
        fx = 120
        b.fan_coil(fx, fy, f"室内机{idx}", w=fc_w, h=fc_h)
        # 各支路 EEV
        b.eev(300, fy, f"EEV{idx}", r=9)
        # 毛细管
        b.capillary(340, fy - 18, fy + 18, f"毛细管{idx}")
        # 分歧管:液路
        b.path(f"M{main_x} {fy} H309")
        # 回气:虚线
        b.path(f"M{main_x + 20} {fy} H220", "pipe")

    # ===================== 流向箭头 =====================
    # 制冷(实线)
    b.arrow(c1x + 50, c1y, fwv_x - 20, fwv_y)       # 压缩机1 → 四通阀
    b.arrow(fwv_x + 20, fwv_y, 638, 120)             # 四通阀 → 换热器
    b.arrow(740, 120, main_x, iy - 20)               # 换热器 → 分歧管
    for fy in fc_ys:
        b.arrow(main_x - 8, fy, 310, fy)             # 分歧管 → 各EEV
    b.arrow(main_x + 20, iy + 100, main_x + 20, oy + oh + 10,
            dashed=True)  # 回气(制热虚线)

    # ===================== 图例 =====================
    b.legend(60, iy + 300, w=230, h=56)

    # 底部注释
    b.text(W / 2, H - 14,
           "依据参考图手工重绘 · 管路连接及元件参数须以厂家技术资料为准",
           12, "middle")

    svg = b.to_svg()
    out.write_text(svg, encoding="utf-8")
    print(f"[OK] wrote {out}  ({len(svg)} bytes)")
    return out


# ------------------------------------------------------------------
# GMV 制冷剂系统原理图:用 Builder 复刻 draw_gmv.py 的手绘矢量图
# 坐标与 draw_gmv.py 完全一致(整组经 <g transform="translate(55 95)"> 平移),
# 输出与参考图同款风格(同 defs / CSS / mesh / 箭头)。
# ------------------------------------------------------------------
_GMV_PIPES = [
    "M12 654 H151 V35 H282 V179 H308 V35 H445",
    "M423 12 V29 C431 29 431 41 423 41 V288 C431 288 431 304 423 304 V531",
    "M12 729 H183 V296 H842",
    "M12 798 H226 V495 H423",
    "M151 253 H246 V263 H423",
    "M423 251 H911 V241 H1001 V111 H947",
    "M181 35 V188 H335 V50 H423",
    "M445 35 V88 H484 V57 A15.5 17 0 0 1 515 57 V88 H619 M641 88 H840",
    "M882 296 H1001 V241 M862 251 V276",
    "M423 12 H1058 V866",
    "M581 251 V140 H841",
    "M953 149 H727 V243 C735 243 735 259 727 259 V288 C735 288 735 304 "
    "727 304 V414 H862",
    "M862 315 V441 M862 517 V600 H710 V732 H654",
    "M862 461 H654 V630",
    "M654 715 V753 H329 V503 C337 503 337 487 329 487 V391 H395 V487 "
    "C403 487 403 503 395 503 V531",
    "M403 676 V753",
    "M497 753 V579 H646 Q654 571 662 579 H862",
    "M666 715 V726 C674 726 674 738 666 738 V789 M666 809 V866 H1058",
]

# (x1, y1, x2, y2, dashed):实线=制冷流向,虚线=制热流向
_GMV_ARROWS = [
    (168, 6, 257, 6, True), (262, 23, 169, 23, False),
    (116, 109, 116, 192, False), (132, 193, 132, 111, True),
    (610, 29, 692, 29, True), (694, 45, 611, 45, False),
    (1017, 250, 1017, 175, False), (1034, 173, 1034, 250, True),
    (616, 264, 533, 264, True), (616, 281, 533, 281, False),
    (664, 307, 581, 307, True), (576, 324, 659, 324, False),
    (203, 398, 203, 320, False), (219, 320, 219, 398, True),
    (443, 359, 443, 442, False), (461, 359, 461, 442, True),
    (822, 407, 822, 323, False), (840, 407, 840, 323, True),
    (671, 566, 671, 481, False), (687, 566, 687, 481, True),
    (114, 464, 114, 546, False), (132, 547, 132, 465, True),
    (342, 567, 342, 649, False), (358, 567, 358, 649, True),
    (364, 728, 445, 728, True), (364, 744, 445, 744, False),
]


def render_gmv(out_path: Optional[str] = None) -> Path:
    """用 Builder 复刻 GMV 制冷剂系统原理图(与 draw_gmv.py 同坐标、同风格)。

    等价于 ``python draw_gmv.py`` 的产物,但走本文件的 Builder API:
    实线箭头=制冷流向,虚线箭头=制热流向。
    """
    if out_path is None:
        out_path = str(OUT / "GMV制冷剂系统原理图.svg")
    out = Path(out_path)

    b = Builder(
        1200, 1010,
        "GMV 制冷剂系统原理图",
        "根据用户提供的 GMV 参考图片手工矢量重绘。实线箭头表示制冷流向，"
        "虚线箭头表示制热流向。仅作原图复绘，未作工程校核。",
    )
    append = b.parts.append

    def sym(d):                                   # class="symbol" 图元
        b.path(d, "symbol")

    def mesh(x, y, w, h):                         # 菱形网格过滤器矩形
        append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
               f'fill="url(#mesh)" stroke="{COMP}" stroke-width="1.4"/>')

    def outline(x, y, w, h):                      # 透明外框(不遮管线)
        append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" '
               f'stroke="{COMP}" stroke-width="1.6"/>')

    def zigzag(x, top, bottom):                   # 毛细管:白遮罩 + 之字线
        append(f'<rect x="{x - 8}" y="{top}" width="16" '
               f'height="{bottom - top}" fill="white"/>')
        offsets = [0, -6, 6, -6, 6, -6, 6, -6, 6, 0]
        pts = " ".join(f"{x + dx},{top + (bottom - top) * i / 9:.3f}"
                       for i, dx in enumerate(offsets))
        append(f'<polyline points="{pts}" fill="none" stroke="{COMP}" '
               f'stroke-width="1.6" stroke-linejoin="miter" '
               f'stroke-linecap="butt"/>')

    def service(x, y):                            # 服务阀(Z 形 + 阀杆 + 双横杠)
        sym(f"M{x - 14},{y - 9} V{y + 9} L{x + 14},{y - 9} V{y + 9} Z "
            f"M{x},{y - 1} V{y - 19} M{x - 9},{y - 19} H{x + 9} "
            f"M{x - 7},{y - 23} H{x + 7}")

    # ---- 标题 + 图组(整组平移,与参考图一致) ----
    append('<g id="heading"><text x="600" y="43" font-size="29" '
           'font-weight="600" text-anchor="middle">'
           'GMV 制冷剂系统原理图</text></g>')
    append('<g id="schematic" transform="translate(55 95)">')

    append('<g id="piping">')
    for d in _GMV_PIPES:
        b.path(d)
    append('</g><g id="components">')

    # 板式热交换器(透明外框 + 竖排文字)
    outline(294, 60, 56, 109)
    b.text(321.5, 66, "板式热交换器", 14, vertical=True)
    # 电子膨胀阀3
    b.circle(181, 143, 11)
    sym("M173.3,135.3 L188.7,150.7 M173.3,150.7 L188.7,135.3")
    b.text(204, 135, "电子", 15)
    b.text(204, 156, "膨胀阀3", 15)
    # IPM 散热片
    outline(474, 40, 52, 32)
    b.text(500, 32, "IPM散热片", 16, "middle")
    # 电子膨胀阀2
    b.circle(630, 88, 11)
    sym("M622.3,80.3 L637.7,95.7 M622.3,95.7 L637.7,80.3")
    b.text(630, 69, "电子膨胀阀2", 15, "middle")
    # 过滤器(水平网格)
    mesh(726, 77, 32, 20)
    b.text(742, 65, "过滤器", 15, "middle")
    # 室外换热器 + 两台轴流风机
    b.rect(841, 67, 107, 44)
    sym("M841 67 L948 111 M841 111 L948 67 M841 72 L801 88 L841 106")
    for yy in (77, 83, 89, 95, 101):
        b.line(826, yy, 841, yy)
    for fx in (865, 928):
        b.path(f"M{fx} 67 V43")
        b.ellipse(fx - 12, 46, 13, 4)
        b.ellipse(fx + 12, 46, 13, 4)
        b.text(fx, 34, "风机", 15, "middle")
    b.rect(841, 137, 111, 9)
    for xx in range(845, 950, 8):
        b.line(xx, 145, xx + 6, 138)
    b.text(896, 130, "室外换热器", 15, "middle")
    # 过滤器
    mesh(663, 128, 32, 20)
    b.text(679, 120, "过滤器", 15, "middle")
    # 毛细管 + 电磁阀
    zigzag(581, 161, 195)
    b.text(595, 184, "毛细管", 15)
    sym("M574,201 H588 L574,219 H588 Z")
    b.text(595, 215, "电磁阀", 15)
    sym("M416,176 H430 L416,194 H430 Z")
    b.text(438, 191, "电磁阀", 15)
    # 卸荷阀 ×2
    b.rect(243, 233, 6, 20)
    b.text(259, 246, "卸荷阀", 15)
    b.rect(908, 220, 6, 21)
    b.text(926, 232, "卸荷阀", 15)
    # 四通阀(圆 + 四叶)
    b.circle(862, 296, 20)
    sym("M862 276 Q862 291 842 296 Q862 301 862 316 "
        "Q862 301 882 296 Q862 291 862 276")
    b.text(888, 282, "四通阀", 16)
    # 高/低压传感器
    b.rect(435, 336, 17, 6)
    b.line(423, 339, 435, 339)
    b.text(461, 345, "低压传感器", 15)
    b.rect(876, 336, 17, 6)
    b.line(862, 339, 876, 339)
    b.text(902, 345, "高压传感器", 15)
    # 单向阀
    sym("M855,377 H869 L855,395 H869 Z")
    b.text(879, 392, "单向阀", 15)
    # 注油口
    b.rect(879, 425, 17, 6)
    b.line(862, 428, 879, 428)
    b.text(905, 434, "注油口", 15)
    # 油分离器 + 过滤器
    b.rect(849, 442, 26, 75)
    b.text(862, 449, "油分离器", 14, vertical=True)
    mesh(852, 526, 20, 32)
    b.text(882, 549, "过滤器", 15)
    # 高压开关
    b.rect(624, 494, 17, 6)
    b.line(641, 497, 654, 497)
    b.text(614, 503, "高压开关", 15, "end")
    # 气液分离器
    b.rect(383, 531, 62, 145)
    b.path("M395 531 V659 H432 V531 M423 531 L408 565")
    b.text(414, 572, "气液分离器", 15, vertical=True)
    # 压缩机
    b.rect(626, 630, 49, 85, rx=24)
    b.text(651, 648, "压缩机", 16, vertical=True)
    # 毛细管 / 电磁阀 ×2
    zigzag(226, 586, 625)
    b.text(241, 611, "毛细管", 15)
    zigzag(497, 655, 689)
    b.text(512, 678, "毛细管", 15)
    sym("M490,695 H504 L490,713 H504 Z")
    b.text(512, 710, "电磁阀", 15)
    zigzag(710, 647, 681)
    b.text(725, 670, "毛细管", 15)
    sym("M703,687 H717 L703,705 H717 Z")
    b.text(725, 702, "电磁阀", 15)
    # 过滤器 ×3
    mesh(141, 409, 20, 32)
    b.text(130, 431, "过滤器", 15, "end")
    mesh(173, 409, 20, 32)
    b.text(201, 431, "过滤器", 15)
    mesh(216, 625, 20, 32)
    b.text(244, 648, "过滤器", 15)
    # 服务阀 ×3
    service(99, 654)
    b.text(99, 622, "液管阀门", 16, "middle")
    service(99, 729)
    b.text(99, 697, "气管阀门", 16, "middle")
    service(99, 798)
    b.text(99, 766, "低压检测阀", 16, "middle")
    # 消音器 + 电子膨胀阀1
    b.rect(663, 759, 6, 12)
    b.text(682, 770, "消音器", 15)
    b.circle(666, 799, 11)
    sym("M658.3,791.3 L673.7,806.7 M658.3,806.7 L673.7,791.3")
    b.text(683, 806, "电子膨胀阀1", 15)

    append('</g><g id="flow-arrows">')
    for x1, y1, x2, y2, dashed in _GMV_ARROWS:
        b.arrow(x1, y1, x2, y2, dashed=dashed)
    append('</g><g id="legend">')
    b.rect(335, 758, 270, 59, rx=4)
    b.arrow(349, 775, 428, 775)
    b.text(443, 781, "制冷时制冷剂流向", 15)
    b.arrow(349, 800, 428, 800, dashed=True)
    b.text(443, 806, "制热时制冷剂流向", 15)
    append('</g></g>')

    b.text(600, 980,
           "依据参考图手工重绘 · 管路连接及元件参数须以厂家技术资料为准",
           13, "middle")

    svg = b.to_svg()
    out.write_text(svg, encoding="utf-8")
    print(f"[OK] wrote {out}  ({len(svg)} bytes)")
    return out


if __name__ == "__main__":
    render_vrf_system()
    render_gmv()
