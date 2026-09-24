# -*- coding: utf-8 -*-
"""把 hvacsvg 式的 SVG 符号加载成 cycleplot 部件(路线一)。

只解析本仓库 symbols/ 用到的 SVG 子集:
  path 指令 M/m/L/l/H/h/V/v/C/c/Z/z + 标签 circle / ellipse / rect / g。
连接点读根属性 data-connection-points,转成相对锚点的 (dx, dy) 偏移。
class="connection-point" 的圆是元数据标记,默认跳过(show_ports=True 可见)。
"""
import json
import re
import xml.etree.ElementTree as ET

from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, PathPatch, Rectangle
from matplotlib.path import Path

from ._primitives import line, txt
from .parts import Part
from .style import LINE, LW_PIPE

_NS = "{http://www.w3.org/2000/svg}"
_TOKEN = re.compile(r"[MmLlHhVvCcZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Z": 0}
# SVG 默认 fill=black,但 hvacsvg 里的纯描边 path 常不写 fill —— 落成 none 更符合画意
_DEFAULT_STYLE = {"fill": "none", "stroke": "black", "stroke-width": "1"}


def _tag(el):
    return el.tag.replace(_NS, "") if isinstance(el.tag, str) else ""


def _style(el, inherited):
    st = dict(inherited)
    for item in el.get("style", "").split(";"):
        if ":" in item:
            k, v = item.split(":", 1)
            st[k.strip()] = v.strip()
    for k in ("fill", "stroke", "stroke-width"):
        if el.get(k) is not None:
            st[k] = el.get(k)
    return st


def _path_verts(d):
    """path 的 d 串编译成 (verts, codes)。相对指令在 y 向下画布上无需翻转。"""
    toks = _TOKEN.findall(d)
    verts, codes = [], []
    x = y = sx = sy = 0.0
    i = 0
    cmd = None
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                verts.append((0.0, 0.0))
                codes.append(Path.CLOSEPOLY)
                x, y = sx, sy
            continue
        if cmd is None:
            i += 1
            continue
        rel = cmd.islower()
        op = cmd.upper()
        n = _ARITY[op]
        nums = [float(v) for v in toks[i:i + n]]
        if len(nums) < n:
            break
        i += n
        if op == "M":
            nx, ny = nums
            if rel:
                nx, ny = x + nx, y + ny
            x, y = sx, sy = nx, ny
            verts.append((x, y))
            codes.append(Path.MOVETO)
            cmd = "l" if rel else "L"     # M 后的裸坐标对是隐式 L
        elif op == "L":
            nx, ny = nums
            if rel:
                nx, ny = x + nx, y + ny
            x, y = nx, ny
            verts.append((x, y))
            codes.append(Path.LINETO)
        elif op == "H":
            x = nums[0] + (x if rel else 0)
            verts.append((x, y))
            codes.append(Path.LINETO)
        elif op == "V":
            y = nums[0] + (y if rel else 0)
            verts.append((x, y))
            codes.append(Path.LINETO)
        elif op == "C":
            x1, y1, x2, y2, nx, ny = nums
            if rel:
                x1, y1, x2, y2, nx, ny = (x + x1, y + y1, x + x2, y + y2,
                                          x + nx, y + ny)
            verts += [(x1, y1), (x2, y2), (nx, ny)]
            codes += [Path.CURVE4, Path.CURVE4, Path.CURVE4]
            x, y = nx, ny
        else:
            break
    return verts, codes


def _draw(ax, el, inherited, dx, dy, s):
    """递归画一个 SVG 元素,(dx,dy) 为平移、s 为缩放(y 向下同向,不翻转)。"""
    tag = _tag(el)
    if "connection-point" in (el.get("class") or "").split():
        return
    st = _style(el, inherited)
    face = st.get("fill", "none") or "none"
    edge = st.get("stroke", "none") or "none"
    face = "none" if face == "transparent" else face
    edge = "none" if edge == "transparent" else edge
    lw = float(st.get("stroke-width", 1) or 1) * max(s, 0.5)
    if tag == "path":
        verts, codes = _path_verts(el.get("d", ""))
        if verts:
            verts = [(vx * s + dx, vy * s + dy) for vx, vy in verts]
            ax.add_patch(PathPatch(Path(verts, codes), facecolor=face,
                                   edgecolor=edge, linewidth=lw,
                                   joinstyle="round", capstyle="round",
                                   zorder=1))
    elif tag == "circle":
        cx, cy, r = (float(el.get("cx", 0)), float(el.get("cy", 0)),
                     float(el.get("r", 0)))
        ax.add_patch(Circle((cx * s + dx, cy * s + dy), r * s,
                            facecolor=face, edgecolor=edge, linewidth=lw,
                            zorder=1))
    elif tag == "ellipse":
        cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
        rx, ry = float(el.get("rx", 0)), float(el.get("ry", 0))
        ax.add_patch(Ellipse((cx * s + dx, cy * s + dy), 2 * rx * s, 2 * ry * s,
                             facecolor=face, edgecolor=edge, linewidth=lw,
                             zorder=1))
    elif tag == "rect":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("width", 0)), float(el.get("height", 0))
        rx = el.get("rx")
        if rx:
            r = float(rx) * s
            ax.add_patch(FancyBboxPatch(
                (x * s + dx + r, y * s + dy + r), w * s - 2 * r, h * s - 2 * r,
                boxstyle=f"round,pad={r}", facecolor=face, edgecolor=edge,
                linewidth=lw, zorder=1))
        else:
            ax.add_patch(Rectangle((x * s + dx, y * s + dy), w * s, h * s,
                                   facecolor=face, edgecolor=edge,
                                   linewidth=lw, zorder=1))
    for child in el:
        _draw(ax, child, st, dx, dy, s)


def load_svg_part(file, ports=None, name=None, scale=1.0, bridge=0, moves=None,
                  label_dy=None):
    """读一个 hvacsvg 风格 SVG,返回可 d.add 的 Part。

    ports: {连接点 id: 端口名},省略时原名收进端口表。
    moves: {连接点 id: (x, y)} 覆盖连接点在 viewBox 里的坐标(改接管位置)。
        端口偏移与 bridge 引管都按覆盖后的坐标算,适合把口挪到别的边。
    label_dy: 标签相对锚点的竖直偏移;None 画在符号下方(默认),
        传 0 表示画在符号中心(如风机盘管、水箱把字压在图元上)。
    锚点取 viewBox 中心,端口偏移 = (x-w/2, y-h/2) * scale。
    bridge: hvacsvg 的连接点落在 viewBox 边缘、符号图形并不画到边,
        给一个正数就从每个连接点沿边缘法向朝内补一段引管(符号单位),
        让 cycleplot 的管路与符号图形接上。
    标签按 Part 惯例画制;传 label=None/"" 时不画。
    """
    root = ET.parse(file).getroot()
    vb = root.get("viewBox", "0 0 160 100").split()
    w, h = float(vb[2]), float(vb[3])
    cx, cy = w / 2.0, h / 2.0

    raw = root.get("data-connection-points", "").strip() or "[]"
    pts = []
    for p in json.loads(raw):          # ElementTree 已把 &quot; 反转义
        pid, px, py = p["id"], float(p["x"]), float(p["y"])
        if moves and pid in moves:
            px, py = moves[pid]
        pts.append((pid, px, py))
    want = ports or {pid: pid for pid, _, _ in pts}

    port_off = {want[pid]: ((px - cx) * scale, (py - cy) * scale)
                for pid, px, py in pts if pid in want}
    label = root.get("data-title", "") if name is None else name
    default_dy = cy * scale + 24 if label_dy is None else label_dy

    def draw(ax, x, y, label=None, **style):
        ox, oy = x - cx * scale, y - cy * scale
        for el in root:
            _draw(ax, el, _DEFAULT_STYLE, ox, oy, scale)
        if bridge:
            for pid, px, py in pts:
                if pid not in want:
                    continue
                if px <= 0:
                    seg = ((px, py), (px + bridge, py))
                elif px >= w:
                    seg = ((px, py), (px - bridge, py))
                elif py <= 0:
                    seg = ((px, py), (px, py + bridge))
                else:
                    seg = ((px, py), (px, py - bridge))
                line(ax, [(vx * scale + ox, vy * scale + oy) for vx, vy in seg],
                     lw=LW_PIPE, color=LINE)
        if label:
            txt(ax, x, y + default_dy, label, size=17)

    return Part(label, draw, port_off, {})
