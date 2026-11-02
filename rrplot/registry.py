"""Web/JSON 图纸可编辑部件的注册表，不影响原有 parts API。"""
import copy
import math

from . import parts


def number(label, default, low=1, high=1000):
    return dict(label=label, default=default, min=low, max=high, kind="number")


def choice(label, default, values):
    return dict(label=label, default=default, options=list(values), kind="select")


REGISTRY = {
    "compressor": dict(label="压缩机", factory=parts.make_compressor, fields={
        "r": number("半径", 42, 8, 250),
        "style": choice("机身", "圆形", parts.COMPRESSOR_STYLES)}),
    "heat_exchanger": dict(label="换热器", factory=parts.make_heat_exchanger,
                           fields={
        "w": number("宽度", 160, 16, 700),
        "h": number("高度", 56, 16, 700),
        "shape": choice("画法", "rect_x", parts.HEX_SHAPES),
        "orient": choice("盘管方向", "h", ["h", "v"])}),
    "expansion_valve": dict(label="膨胀阀", factory=parts.make_expansion_valve_x,
                            fields={
        "r": number("半径", 10, 4, 80),
        "orient": choice("连接方向", "v", ["h", "v"])}),
    "vessel": dict(label="闪蒸罐", factory=parts.make_vessel, fields={
        "w": number("宽度", 66, 16, 300),
        "h": number("高度", 130, 20, 600),
        "liquid": number("液位比例", 0.42, 0, 1)}),
    "intermediate_hex": dict(label="中间换热器",
                             factory=parts.make_intermediate_hex, fields={
        "w": number("宽度", 80, 20, 500),
        "h": number("高度", 190, 20, 600),
        "drop": number("通道偏移", 0.275, 0.05, 0.45),
        "orient": choice("通道方向", "v", ["h", "v"])}),
}


def catalog():
    """仅返回 JSON 可序列化的描述。"""
    return [dict(type=key, label=item["label"],
                 fields=copy.deepcopy(item["fields"]))
            for key, item in REGISTRY.items()]


def normalize_params(kind, params):
    if not isinstance(kind, str) or kind not in REGISTRY:
        raise ValueError(f"未知图元: {kind}")
    if not isinstance(params, dict):
        raise ValueError("params 必须是对象")
    fields = REGISTRY[kind]["fields"]
    if set(params) - set(fields):
        raise ValueError(f"未知参数: {', '.join(sorted(set(params) - set(fields)))}")
    result = {}
    for key, field in fields.items():
        value = params.get(key, field["default"])
        if field["kind"] == "select":
            if value not in field["options"]:
                raise ValueError(f"{key} 必须为 {field['options']} 之一")
        elif (isinstance(value, bool) or not isinstance(value, (int, float))
              or not math.isfinite(value)
              or not field["min"] <= value <= field["max"]):
            raise ValueError(f"{key} 必须在 {field['min']}～{field['max']} 之间")
        result[key] = value
    if kind == "vessel" and result["h"] < result["w"]:
        raise ValueError("闪蒸罐高度不能小于宽度")
    return result


def make_registered(kind, params):
    return REGISTRY[kind]["factory"](**normalize_params(kind, params))


def describe(kind, params):
    """返回以中心为原点的尺寸、端口和法向；SVG 由 renderer 生成。"""
    params = normalize_params(kind, params)
    part = make_registered(kind, params)
    if kind in ("compressor", "expansion_valve"):
        w = 2 * params["r"]
        h = w
        if kind == "compressor" and params["style"] == "方形":
            w = params["r"]
    else:
        w, h = params["w"], params["h"]
    return dict(width=w, height=h, box=[-w / 2 - 3, -h / 2 - 3, w + 6, h + 6],
                ports={key: dict(point=list(point),
                                 direction=list(part.direction(key)))
                       for key, point in part.ports.items()})
