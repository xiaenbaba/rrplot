"""将可编辑 JSON 图纸适配为现有 Matplotlib 绘图。"""
import base64
import io
import json
from functools import lru_cache

import matplotlib as mpl
from matplotlib.patches import Circle, Rectangle
from matplotlib.transforms import Affine2D

from .core import Diagram
from .registry import describe, make_registered, normalize_params
from .scene import resolve_scene
from .style import FONT_STACK


@lru_cache(maxsize=256)
def _glyph(kind, params_json):
    params = json.loads(params_json)
    geometry = describe(kind, params)
    x, y, w, h = geometry["box"]
    with Diagram(width=w, height=h) as diagram:
        diagram.add(make_registered(kind, params), None, loc=(-x, -y))
        diagram.render()
        out = io.BytesIO()
        with mpl.rc_context({"svg.hashsalt": "rrplot-web"}):
            diagram.fig.savefig(out, format="svg", transparent=True,
                                metadata={"Date": None})
    return "data:image/svg+xml;base64," + base64.b64encode(out.getvalue()).decode()


def preview_glyph(kind, params=None):
    """复用图元缓存提供库与属性面板缩略图，不构建临时图纸。"""
    normalized = normalize_params(kind, {} if params is None else params)
    image = _glyph(kind, json.dumps(normalized, sort_keys=True))
    return base64.b64decode(image.split(",", 1)[1])


def resolve_for_editor(document):
    result = resolve_scene(document)
    for node in result["nodes"]:
        node["geometry"]["image"] = _glyph(
            node["type"], json.dumps(node["params"], sort_keys=True))
    result["fontFamily"] = ", ".join(FONT_STACK)
    result["features"] = ["edgeLabels", "pipeMounts"]
    return result


def _rotated(part, angle):
    if angle == 0:
        return part

    def draw(ax, x, y, label=None, **kw):
        before_lines, before_patches = len(ax.lines), len(ax.patches)
        before_texts = len(ax.texts)
        part.draw(ax, x, y, label=None)
        transform = Affine2D().rotate_deg_around(x, y, angle) + ax.transData
        for artist in (list(ax.lines)[before_lines:]
                       + list(ax.patches)[before_patches:]):
            artist.set_transform(transform)
        for text in list(ax.texts)[before_texts:]:
            text.set_transform(transform)
            text.set_rotation(text.get_rotation() - angle)
            text.set_rotation_mode("anchor")

    from .part import Part
    return Part(part.name, draw, {})


def _node_part(node):
    """只校正阀顶执行机构朝向,保留场景端口、挂接及标签旋转。"""
    params = node["params"]
    angle = node["rotation"]
    if node["type"] == "expansion_valve" and params["style"] == "dome":
        if (angle + (90 if params["orient"] == "v" else 0)) % 360 >= 180:
            angle = (angle + 180) % 360
    elif node["type"] == "solenoid_valve" and params["style"] == "bowtie":
        angle %= 180
    return _rotated(make_registered(node["type"], params), angle)


def build_scene(document):
    resolved = resolve_scene(document)
    d = resolved["document"]
    diagram = Diagram(width=d["page"]["width"], height=d["page"]["height"])
    try:
        for node in resolved["nodes"]:
            if node.get("mount"):
                continue
            diagram.add(_node_part(node), None,
                        loc=(node["x"], node["y"]))
        for edge in resolved["edges"]:
            points = edge["points"]
            diagram.pipe(points[0], points[-1], via=points[1:-1],
                         head=edge["head"], head_at=edge["headAt"],
                         lw=edge["width"], color=edge["color"],
                         linestyle=edge["linestyle"])
        diagram.render()
        # Accessories sit above their parent pipe in both editor and exports.
        # An opaque body mask removes the pipe and arrow beneath the symbol.
        for node in resolved["nodes"]:
            if not node.get("mount"):
                continue
            x, y = node["x"], node["y"]
            p = node["params"]
            w, h = (2*p["r"], 2*p["r"]) if "r" in p else (p["w"], p["h"])
            transform = Affine2D().rotate_deg_around(x, y, node["rotation"])
            mask = Rectangle((x-w/2, y-h/2), w, h, facecolor="white",
                             edgecolor="none", zorder=8,
                             transform=transform + diagram.ax.transData)
            diagram.ax.add_patch(mask)
            lines, patches = len(diagram.ax.lines), len(diagram.ax.patches)
            _node_part(node).draw(diagram.ax, x, y, label=None)
            artists = (list(diagram.ax.lines)[lines:]
                       + list(diagram.ax.patches)[patches:])
            for artist in artists:
                artist.set_zorder(9)
        for junction in d["junctions"]:
            diagram.ax.add_patch(Circle((junction["x"], junction["y"]), 4,
                                        facecolor="#111111", edgecolor="none",
                                        zorder=6))
        for label in resolved["labels"]:
            diagram.text(*label["position"], label["text"], size=label["size"],
                         ha=label["ha"], color=label["color"], boxed=label["boxed"])
            diagram.ax.texts[-1].set_zorder(10)
        return diagram
    except Exception:
        diagram.close()
        raise


def export_scene(document, fmt="svg", dpi=140):
    if fmt not in ("svg", "png", "pdf"):
        raise ValueError("导出格式仅支持 SVG、PNG、PDF")
    if (isinstance(dpi, bool) or not isinstance(dpi, (int, float))
            or not 72 <= dpi <= 600):
        raise ValueError("DPI 必须在 72～600 之间")
    with build_scene(document) as diagram:
        if fmt == "png" and diagram.W * diagram.H * (dpi / 100) ** 2 > 40000000:
            raise ValueError("位图尺寸过大，请减小页面或 DPI")
        out = io.BytesIO()
        with mpl.rc_context({"svg.hashsalt": "rrplot-web"}):
            options = {"metadata": {"Date": None}} if fmt == "svg" else {}
            diagram.fig.savefig(out, format=fmt, dpi=dpi, **options)
        return out.getvalue()
