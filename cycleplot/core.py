# -*- coding: utf-8 -*-
"""示意图引擎:部件放置、走线式连线、随线状态点/传感器标注。

坐标系与旧脚本一致:x 向右, y 向下(ax.set_ylim(H, 0))。
"""
import os

import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from ._primitives import arrow, line as _line, txt
from .style import (FONT_STACK, LINE, LW_PIPE, NUM_SIZE, SENSOR_SIZE,
                    use_font)

_DIR_TOKENS = {
    "e": (1, 0), "w": (-1, 0), "n": (0, -1), "s": (0, 1),
    "right": (1, 0), "left": (-1, 0), "up": (0, -1), "down": (0, 1),
    "右": (1, 0), "左": (-1, 0), "上": (0, -1), "下": (0, 1),
}


class Port:
    """节点上的一个接管口,记录绝对坐标与外法向。"""

    __slots__ = ("point", "dir", "owner")

    def __init__(self, point, direction, owner):
        self.point = point
        self.dir = direction
        self.owner = owner

    def __repr__(self):
        name = "-" if self.owner is None \
            else (self.owner.label or self.owner.part.name)
        return f"<Port {name} {self.point}>"


class Node:
    """放置在画布上的部件实例。node["port"] 取得端口。"""

    def __init__(self, part, loc, label, style=None):
        self.part = part
        self.loc = loc
        self.label = label
        self.style = style or {}

    def port(self, key):
        dx, dy = self.part.port(key)
        x, y = self.loc
        return Port((x + dx, y + dy), self.part.direction(key), self)

    def __getitem__(self, key):
        return self.port(key)


class State:
    """随线标注:状态点编号或 T/P 传感器。"""

    def __init__(self, text, at, side=-1, kind=None, size=None):
        self.text = text
        self.at = at
        self.side = side
        self.kind = kind or ("sensor" if _is_sensor(text) else "num")
        self.size = size

    @property
    def is_sensor(self):
        return self.kind == "sensor"


def _is_sensor(text):
    t = text.strip().strip("$").strip()
    return bool(t) and t[0].isalpha()


def _resolve_at(at):
    """把 at 归一为 [0,1] 的折线弧长比例。"""
    if isinstance(at, str):
        at = {"start": 0.0, "mid": 0.5, "end": 1.0}[at.lower()]
    return float(at)


def _polyline_point(pts, frac):
    """返回折线上给定弧长比例处的点与局部方向。"""
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    lens = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in segs]
    total = sum(lens) or 1.0
    target = frac * total
    acc = 0.0
    for (a, b), L in zip(segs, lens):
        if acc + L >= target or (a, b) is segs[-1]:
            t = 0.0 if L == 0 else (target - acc) / L
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            ux = (b[0] - a[0]) / L if L else 1.0
            uy = (b[1] - a[1]) / L if L else 0.0
            return (x, y), (ux, uy)
        acc += L
    return pts[-1], (1.0, 0.0)


def _orthogonalize(pts):
    """把任意折线补齐为直角走线:在方向突变处插入拐点。"""
    out = [pts[0]]
    for cur in pts[1:]:
        prev = out[-1]
        if prev[0] == cur[0] or prev[1] == cur[1]:
            out.append(cur)
            continue
        # 依据进入段的方向决定拐点位置
        if len(out) >= 2 and out[-2][1] == prev[1]:
            corner = (cur[0], prev[1])     # 进入段水平 -> 先横后竖
        else:
            corner = (prev[0], cur[1])     # 进入段竖直 -> 先竖后横
        out.extend([corner, cur])
    return out


class Pipe:
    def __init__(self, diagram, a, b, via, states, lw, head, head_at):
        self.d = diagram
        self.a = a
        self.b = b
        self.via = via
        self.states = states
        self.lw = lw
        self.head = head
        self.head_at = head_at
        self._pts = None

    def points(self):
        if self._pts is not None:
            return self._pts
        pts = [self.a.point]
        cur = self.a.point
        for token in self.via:
            if isinstance(token, (tuple, list)) and len(token) == 2 \
                    and isinstance(token[0], str):
                d = _DIR_TOKENS[token[0].lower()]
                val = token[1]
                nxt = (val, cur[1]) if d[0] else (cur[0], val)
            elif isinstance(token, str):
                d = _DIR_TOKENS[token.lower()]
                length = self.d.default_step
                nxt = (cur[0] + d[0] * length, cur[1] + d[1] * length)
            else:
                nxt = (float(token[0]), float(token[1]))
            pts.append(nxt)
            cur = nxt
        pts.append(self.b.point)
        self._pts = _orthogonalize(pts)
        return self._pts

    def draw(self):
        pts = self.points()
        _line(self.d.ax, pts, lw=self.lw, color=LINE)
        if self.head:
            for f in self.head_at:
                (x1, y1), (ux, uy) = _polyline_point(pts, f)
                arrow(self.d.ax, x1 - ux * 20, y1 - uy * 20,
                      x1 + ux * 20, y1 + uy * 20, size=8, lw=0.9)
        for st in self.states:
            self._draw_state(st, pts)

    def _draw_state(self, st, pts):
        (x, y), (ux, uy) = _polyline_point(pts, _resolve_at(st.at))
        nx, ny = -uy, ux
        off = (SENSOR_SIZE + 22) if st.is_sensor else (NUM_SIZE + 12)
        px = x + nx * off * st.side
        py = y + ny * off * st.side
        if st.is_sensor:
            size = st.size or SENSOR_SIZE
            self.d.ax.add_patch(Circle((px, py), 18, facecolor="white",
                                       edgecolor=LINE, lw=1.0, zorder=5))
            txt(self.d.ax, px, py, st.text, size=size)
            self.d.ax.texts[-1].set_zorder(6)
        else:
            self.d.ax.text(px, py, st.text, fontsize=st.size or NUM_SIZE,
                           fontfamily=FONT_STACK, ha="center", va="center",
                           color=LINE, zorder=6)


class Diagram:
    """一张示意图。add() 放部件,pipe() 连线,最后 save() 出图。"""

    def __init__(self, width=800, height=600, default_step=100):
        self.W, self.H = width, height
        self.default_step = default_step
        self.fig, self.ax = plt.subplots(figsize=(width / 100, height / 100),
                                         dpi=100)
        self.ax.set_xlim(0, width)
        self.ax.set_ylim(height, 0)
        self.ax.set_aspect("equal")
        self.ax.axis("off")
        self.fig.patch.set_facecolor("white")
        self._nodes = []
        self._pipes = []

    # ---------- 组装 ----------
    def add(self, part, label=None, loc=(0, 0), **style):
        node = Node(part, loc, label, style)
        self._nodes.append(node)
        return node

    def pipe(self, a, b, via=(), states=(), lw=LW_PIPE, head=True,
             head_at=(0.55,)):
        a, b = _as_port(a), _as_port(b)
        if isinstance(states, State):
            states = (states,)
        norm = []
        for s in states:
            if isinstance(s, State):
                norm.append(s)
            elif isinstance(s, dict):
                s = dict(s)
                norm.append(State(s.pop("text"),
                                  s.pop("at", "mid"), **s))
            else:
                norm.append(State(s[0], s[1]))
        p = Pipe(self, a, b, list(via), norm, lw, head, head_at)
        self._pipes.append(p)
        return p

    # 便捷:直接按坐标放一个 T/P 传感器圆圈
    def sensor(self, x, y, text, r=18, size=SENSOR_SIZE):
        self.ax.add_patch(Circle((x, y), r, facecolor="white",
                                 edgecolor=LINE, lw=1.0, zorder=5))
        txt(self.ax, x, y, text, size=size)
        self.ax.texts[-1].set_zorder(6)

    def text(self, x, y, s, **kw):
        txt(self.ax, x, y, s, **kw)

    # ---------- 出图 ----------
    def render(self):
        for n in self._nodes:
            kw = dict(n.style)
            # label=None/"" 一律不画,不回落到部件绘制函数的默认标签
            kw["label"] = n.label
            n.part.draw(self.ax, n.loc[0], n.loc[1], **kw)
        for p in self._pipes:
            p.draw()
        return self.fig

    def save(self, path, dpi=100, tight=True):
        self.render()
        kw = dict(dpi=dpi)
        if tight:
            kw.update(bbox_inches="tight", pad_inches=0.05)
        self.fig.savefig(path, **kw)
        return path

    def show(self):
        self.render()
        plt.show()


def _as_port(p):
    """允许把裸坐标 (x, y) 当作固定管路端点(用于画总管/分支点)。"""
    if isinstance(p, Port):
        return p
    return Port((float(p[0]), float(p[1])), (0.0, 0.0), None)


def make_partial(part, ports=None, dirs=None):
    """从已有部件派生一个只改端口定义的新部件(复用同一绘制函数)。

    覆盖某个端口位置时,其旧方向声明一并作废(回落到按偏移推断);
    需要固定方向就显式传 dirs。
    """
    from .parts import Part
    new_ports = dict(part.ports)
    new_dirs = dict(part._dirs)
    if ports:
        for k, v in ports.items():
            new_ports[k] = v
            new_dirs.pop(k, None)
    if dirs:
        new_dirs.update(dirs)
    return Part(part.name, part.draw, new_ports, new_dirs)


__all__ = ["Diagram", "Node", "Port", "State", "Pipe", "make_partial",
           "use_font", "os"]
