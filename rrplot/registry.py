"""Web/JSON 图纸可编辑部件的注册表，不影响原有 parts API。"""
import copy
import math

from . import parts

PIPE_ACCESSORIES = frozenset({"expansion_valve", "globe_valve", "solenoid_valve",
                              "check_valve", "filter", "capillary", "muffler"})
UPRIGHT_STYLES = {
    "expansion_valve": dict(field="style", value="dome",
                            offsetField="orient", offsets={"v": 90}),
    "solenoid_valve": dict(field="style", value="bowtie"),
}


def capabilities(kind):
    """图元行为声明；不写入用户图纸，保留旧 JSON 的参数与端口。"""
    result = dict(pipeMount=kind in PIPE_ACCESSORIES, rotationStep=90)
    if kind in UPRIGHT_STYLES:
        result["upright"] = copy.deepcopy(UPRIGHT_STYLES[kind])
    return result


def glyph_rotation(kind, params, rotation):
    policy = UPRIGHT_STYLES.get(kind)
    if not policy or params.get(policy["field"]) != policy["value"]:
        return 0
    offset = policy.get("offsets", {}).get(params.get(policy.get("offsetField")), 0)
    return 180 if (rotation + offset) % 360 >= 180 else 0


def number(label, default, low=1, high=1000):
    return dict(label=label, default=default, min=low, max=high, kind="number")


def choice(label, default, values):
    return dict(label=label, default=default, options=list(values), kind="select")


def boolean(label, default=False):
    return dict(label=label, default=default, kind="boolean", type="checkbox")


def integer(label, default, low, high):
    return dict(number(label, default, low, high), kind="integer", step=1)


REGISTRY = {
    "compressor": dict(label="压缩机", factory=parts.make_compressor, fields={
        "r": number("半径", 42, 8, 250),
        "style": choice("机身", "圆形", parts.COMPRESSOR_STYLES)}),
    "heat_exchanger": dict(label="换热器", factory=parts.make_heat_exchanger,
                           fields={
        "w": number("宽度", 160, 16, 700),
        "h": number("高度", 56, 16, 700),
        "shape": dict(choice("画法", "rect_x", parts.HEX_SHAPES),
                      optionLabels={"rect_diag": "单对角线",
                                    "rect_x": "对角交叉",
                                    "rect_zigzag7": "折线盘管",
                                    "fan_coil": "风机盘管"}),
        "orient": choice("折线盘管方向", "h", ["h", "v"]),
        "stub": number("左右接管长度", 0, 0, 100)}),
    "expansion_valve": dict(label="膨胀阀", factory=parts.make_expansion_valve_x,
                            fields={
        "r": number("阀体半径 / 半宽", 10, 4, 80),
        "orient": choice("连接方向", "v", ["h", "v"]),
        "style": dict(choice("阀体样式", "circle_x", ["circle_x", "dome"]),
                      optionLabels={"circle_x": "圆圈 X",
                                    "dome": "对顶三角＋半圆穹顶"})}),
    "vessel": dict(label="闪蒸罐", factory=parts.make_vessel, fields={
        "w": number("宽度", 66, 16, 300),
        "h": number("高度", 130, 20, 600),
        "liquid": number("液位比例", 0.42, 0, 1)}),
    "separator_utube": dict(label="气液分离器", factory=parts.make_separator_utube,
                             fields={
        "w": number("宽度", 120, 40, 500),
        "h": number("高度", 118, 40, 600),
        "stub": number("接管长度", 16, 4, 100),
        "flip": boolean("镜像进出管")}),
    "intermediate_hex": dict(label="中间换热器",
                             factory=parts.make_intermediate_hex, fields={
        "w": number("宽度", 80, 20, 500),
        "h": number("高度", 190, 20, 600),
        "drop": number("通道偏移", 0.275, 0.05, 0.45),
        "orient": choice("通道方向", "v", ["h", "v"])}),
    "four_way_valve": dict(label="四通换向阀",
                           factory=parts.make_four_way_round, fields={
        "r": number("半径", 28, 8, 150),
        "mark": boolean("显示 D/C/E/S 口标", True)}),
    "globe_valve": dict(label="截止阀", factory=parts.make_globe_valve, fields={
        "w": number("阀体宽度", 40, 16, 300),
        "h": number("阀体高度", 24, 12, 180),
        "stem": number("阀杆长度", 14, 4, 100),
        "handle": number("手轮宽度", 28, 8, 240)}),
    "solenoid_valve": dict(label="电磁阀",
                           factory=parts.make_solenoid_valve, fields={
        "r": number("阀体半径 / 半宽", 16, 6, 120),
        "stem": number("引线长度", 12, 4, 100),
        "handle": number("线圈横杠宽度", 26, 8, 240),
        "style": dict(choice("阀体样式", "circle_x", ["circle_x", "bowtie"]),
                      optionLabels={"circle_x": "圆圈 X＋横杆",
                                    "bowtie": "对顶三角＋横杆＋Σ 折线"})}),
    "check_valve": dict(label="单向阀", factory=parts.make_check_valve, fields={
        "w": number("阀体宽度", 40, 16, 300),
        "h": number("阀体高度", 24, 12, 180),
        "stub": number("接管长度", 10, 4, 100),
        "point": choice("流通方向（e 右 / w 左）", "e", ["e", "w"]),
        "style": dict(choice("阀体样式", "solid", ["solid", "hollow"]),
                      optionLabels={"solid": "黑色实心", "hollow": "空心黑框"})}),
    "filter": dict(label="过滤器", factory=parts.make_filter, fields={
        "w": number("宽度", 48, 16, 300),
        "h": number("高度", 26, 12, 180),
        "stub": number("接管长度", 10, 4, 100),
        "n": integer("网格线数", 7, 3, 25)}),
    "oil_separator": dict(label="油分离器", factory=parts.make_oil_separator,
                           fields={
        "w": number("宽度", 40, 16, 300),
        "h": number("高度", 100, 20, 600),
        "stub": number("接管长度", 12, 4, 100)}),
    "capillary": dict(label="毛细管", factory=parts.make_capillary, fields={
        "w": number("宽度", 18, 6, 100),
        "h": number("高度", 80, 16, 400),
        "n": integer("圈数", 5, 1, 25)}),
    "fan_coil": dict(label="室内风机盘管", factory=parts.make_fan_coil,
                     legacy=True, fields={
        "w": number("宽度", 120, 40, 600),
        "h": number("高度", 64, 24, 400),
        "stub": number("接管长度", 12, 4, 100)}),
    "muffler": dict(label="消音器", factory=parts.make_muffler, fields={
        "w": number("宽度", 36, 12, 200),
        "h": number("高度", 72, 16, 400),
        "stub": number("接管长度", 12, 4, 100)}),
    "sensor": dict(label="温度/压力传感器", factory=parts.make_sensor, fields={
        "r": number("半径", 14, 8, 80),
        "stub": number("测量接管长度", 12, 4, 100),
        "mark": choice("测量类型", "T", ["T", "P"])}),
}


def catalog():
    """仅返回 JSON 可序列化的描述。"""
    return [dict(type=key, label=item["label"],
                 fields=copy.deepcopy(item["fields"]), capabilities=capabilities(key))
            for key, item in REGISTRY.items() if not item.get("legacy")]


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
        if field["kind"] == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{key} 必须为布尔值")
        elif field["kind"] == "select":
            if value not in field["options"]:
                raise ValueError(f"{key} 必须为 {field['options']} 之一")
        elif (isinstance(value, bool) or not isinstance(value, (int, float))
              or not math.isfinite(value)
              or not field["min"] <= value <= field["max"]):
            raise ValueError(f"{key} 必须在 {field['min']}～{field['max']} 之间")
        elif field["kind"] == "integer":
            if int(value) != value:
                raise ValueError(f"{key} 必须为整数")
            value = int(value)
        result[key] = value
    if kind == "vessel" and result["h"] < result["w"]:
        raise ValueError("闪蒸罐高度不能小于宽度")
    return result


def make_registered(kind, params):
    return REGISTRY[kind]["factory"](**normalize_params(kind, params))


def describe(kind, params, *, _normalized=False):
    """返回以中心为原点的尺寸、端口和法向；SVG 由 renderer 生成。"""
    if not _normalized:
        params = normalize_params(kind, params)
    part = REGISTRY[kind]["factory"](**params)
    if kind in ("compressor", "expansion_valve", "four_way_valve",
                "solenoid_valve", "sensor"):
        w = 2 * params["r"]
        h = w
        if kind == "compressor" and params["style"] == "方形":
            w = params["r"]
    else:
        w, h = params["w"], params["h"]
    left, top, right, bottom = -w / 2, -h / 2, w / 2, h / 2
    if kind == "expansion_valve" and params["style"] == "dome":
        if params["orient"] == "h":
            top = -1.65 * params["r"]
            bottom = -top
        else:
            right = 1.65 * params["r"]
            left = -right
    elif kind == "separator_utube":
        top -= params["stub"]
    elif kind == "four_way_valve" and params["mark"]:
        left -= 30
        right += 30
        top -= 30
        bottom += 30
    elif kind == "solenoid_valve" and params["style"] == "bowtie":
        extent = max(params["r"] + 12, params["handle"] * 26/48)
        left, right = -extent, extent
        top = -params["r"] - params["stem"]
        bottom = -top
    elif kind in ("globe_valve", "solenoid_valve"):
        left = min(left - 12, -params["handle"] / 2)
        right = max(right + 12, params["handle"] / 2)
        top -= params["stem"]
    elif kind in ("check_valve", "filter"):
        left -= params["stub"]
        right += params["stub"]
    elif kind == "oil_separator":
        left -= params["stub"]
        top -= params["stub"]
        bottom += params["stub"]
    elif kind in ("fan_coil", "heat_exchanger"):
        left -= params["stub"]
        right += params["stub"]
    elif kind == "muffler":
        top -= params["stub"]
        bottom += params["stub"]
    elif kind == "sensor":
        bottom += params["stub"]
    return dict(width=w, height=h, capabilities=capabilities(kind),
                box=[left - 3, top - 3, right - left + 6, bottom - top + 6],
                ports={key: dict(point=list(point),
                                 direction=list(part.direction(key)))
                       for key, point in part.ports.items()})
