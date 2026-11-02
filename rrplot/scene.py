"""版本化图纸模型和纯几何解析；不改动原有 Port 快照语义。"""
import copy
import json
import math
from importlib.resources import files

from matplotlib.colors import is_color_like

from .core import _orthogonalize
from .registry import describe, normalize_params

SCHEMA_VERSION = 1
TEMPLATES = {"evi_ftvi": "EVI 过冷器喷气增焓", "ftvi": "FTVI 闪蒸罐喷气增焓"}


def load_template(name):
    if name not in TEMPLATES:
        raise ValueError(f"未知模板: {name}")
    raw = files("rrplot").joinpath("templates").joinpath(name + ".json").read_text(
        encoding="utf-8")
    return validate_scene(json.loads(raw))


def finite(value, label, low=-100000, high=100000):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{label} 必须为 {low}～{high} 的有限数字")
    return value


def color(value, label):
    if not isinstance(value, str) or not is_color_like(value):
        raise ValueError(f"{label} 必须是有效颜色，如 #111111")


def validate_scene(document):
    """复制并规范图纸；无效引用明确报错，不静默丢弃数据。"""
    if not isinstance(document, dict) or document.get("schemaVersion") != 1:
        raise ValueError("仅支持 schemaVersion=1 的图纸")
    d = copy.deepcopy(document)
    if not isinstance(d.get("title", ""), str):
        raise ValueError("图纸名称必须是文字")
    d.setdefault("title", "未命名图纸")
    page = d.setdefault("page", {})
    if not isinstance(page, dict):
        raise ValueError("page 必须为对象")
    for key, default in (("width", 760), ("height", 580)):
        finite(page.setdefault(key, default), "页面 " + key, 100, 4000)
    ids = set()
    for collection in ("nodes", "edges", "junctions", "labels"):
        items = d.setdefault(collection, [])
        if not isinstance(items, list) or len(items) > 2000:
            raise ValueError(f"{collection} 必须为数组且不超过 2000 项")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{collection} 各项必须为对象")
            key = item.get("id")
            if not isinstance(key, str) or not key or key in ids:
                raise ValueError("对象 ID 必须为非空、不重复的字符串")
            ids.add(key)
    nodes = {n["id"]: n for n in d["nodes"]}
    junctions = {j["id"]: j for j in d["junctions"]}
    descriptions = {}
    for node in d["nodes"]:
        node["params"] = normalize_params(node.get("type"), node.get("params", {}))
        descriptions[node["id"]] = describe(node["type"], node["params"])
        if not isinstance(node.setdefault("title", node["type"]), str):
            raise ValueError("设备名称必须是文字")
        for axis in ("x", "y"):
            finite(node.get(axis), "设备 " + axis)
        angle = node.setdefault("rotation", 0)
        if angle not in (0, 90, 180, 270):
            raise ValueError("旋转角必须为 0、90、180、270")
    for junction in d["junctions"]:
        for axis in ("x", "y"):
            finite(junction.get(axis), "三通 " + axis)
    for edge in d["edges"]:
        for side in ("source", "target"):
            ref = edge.get(side)
            if not isinstance(ref, dict):
                raise ValueError("管路必须引用设备端口或三通")
            if "junctionId" in ref and set(ref) == {"junctionId"}:
                if ref["junctionId"] not in junctions:
                    raise ValueError("管路引用了不存在的三通")
            elif set(ref) == {"nodeId", "portId"} and ref["nodeId"] in nodes:
                if ref["portId"] not in descriptions[ref["nodeId"]]["ports"]:
                    raise ValueError("管路引用了不存在的端口")
            else:
                raise ValueError("管路引用了不存在的设备或端口")
        vertices = edge.setdefault("vertices", [])
        if not isinstance(vertices, list) or len(vertices) > 100:
            raise ValueError("每条管路顶点必须为数组，最多 100 项")
        for point in vertices:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("顶点必须为 [x,y]")
            for val in point:
                finite(val, "顶点")
        finite(edge.setdefault("width", 1.8), "线宽", 0.2, 8)
        color(edge.setdefault("color", "#111111"), "管路颜色")
        if edge.setdefault("linestyle", "solid") not in ("solid", "dashed"):
            raise ValueError("线型必须为 solid 或 dashed")
        if not isinstance(edge.setdefault("head", True), bool):
            raise ValueError("箭头选项必须为布尔值")
        heads = edge.setdefault("headAt", [0.55])
        if not isinstance(heads, list) or len(heads) > 10:
            raise ValueError("箭头位置必须为数组，最多 10 项")
        for head in heads:
            finite(head, "箭头位置", 0, 1)
    for label in d["labels"]:
        if not isinstance(label.get("text"), str) or len(label["text"]) > 1000:
            raise ValueError("标签内容必须为不超过 1000 字的文字")
        for axis in ("x", "y"):
            finite(label.setdefault(axis, 0), "标签 " + axis)
        finite(label.setdefault("size", 15), "字号", 6, 72)
        if label.setdefault("ha", "center") not in ("left", "center", "right"):
            raise ValueError("标签对齐方式无效")
        if not isinstance(label.setdefault("boxed", False), bool):
            raise ValueError("标签背景必须为布尔值")
        color(label.setdefault("color", "#111111"), "标签颜色")
        if "nodeId" in label and label["nodeId"] not in nodes:
            raise ValueError("标签引用了不存在的设备")
    return d


def rotate(point, angle):
    c = round(math.cos(math.radians(angle)), 12)
    s = round(math.sin(math.radians(angle)), 12)
    x, y = point
    return [round(c * x - s * y, 8), round(s * x + c * y, 8)]


def endpoint(ref, nodes, junctions):
    if "junctionId" in ref:
        j = junctions[ref["junctionId"]]
        return dict(point=[j["x"], j["y"]], direction=[0, 0])
    node = nodes[ref["nodeId"]]
    port = node["geometry"]["ports"][ref["portId"]]
    offset = rotate(port["point"], node["rotation"])
    return dict(point=[node["x"] + offset[0], node["y"] + offset[1]],
                direction=rotate(port["direction"], node["rotation"]))


def route(source, target, vertices):
    """带法向引管的正交路径；正式输出和浏览器临时几何共用规则。"""
    a, b = source["point"], target["point"]
    ad, bd = source["direction"], target["direction"]
    delta = [b[0] - a[0], b[1] - a[1]]
    if not vertices and (a[0] == b[0] or a[1] == b[1]):
        if (sum(x * y for x, y in zip(ad, delta)) >= 0
                and sum(x * y for x, y in zip(bd, delta)) <= 0):
            return [a, b]
    pts = [a]
    if any(ad):
        pts.append([a[i] + ad[i] * 20 for i in (0, 1)])
    pts.extend(vertices)
    if any(bd):
        pts.append([b[i] + bd[i] * 20 for i in (0, 1)])
    pts.append(b)
    result = []
    for point in _orthogonalize(pts):
        point = list(point)
        if not result or point != result[-1]:
            result.append(point)
    return result if len(result) > 1 else [a, b]


def resolve_scene(document):
    d = validate_scene(document)
    nodes = {n["id"]: dict(n, geometry=describe(n["type"], n["params"]))
             for n in d["nodes"]}
    junctions = {j["id"]: j for j in d["junctions"]}
    edges = []
    for edge in d["edges"]:
        a = endpoint(edge["source"], nodes, junctions)
        b = endpoint(edge["target"], nodes, junctions)
        edges.append(dict(edge, points=route(a, b, edge["vertices"])))
    labels = []
    for label in d["labels"]:
        x, y = label["x"], label["y"]
        if "nodeId" in label:
            node = nodes[label["nodeId"]]
            x, y = rotate([x, y], node["rotation"])
            x, y = x + node["x"], y + node["y"]
        labels.append(dict(label, position=[x, y]))
    return dict(document=d, nodes=list(nodes.values()), edges=edges, labels=labels)
