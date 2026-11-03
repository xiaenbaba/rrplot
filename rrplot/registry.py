"""Web/JSON 图纸可编辑部件的注册表，不影响原有 parts API。"""
import copy
import math

from . import parts


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
        "r": number("半径", 16, 6, 120),
        "stem": number("引线长度", 12, 4, 100),
        "handle": number("线圈横杠宽度", 26, 8, 240)}),
    "check_valve": dict(label="单向阀", factory=parts.make_check_valve, fields={
        "w": number("阀体宽度", 40, 16, 300),
        "h": number("阀体高度", 24, 12, 180),
        "stub": number("接管长度", 10, 4, 100),
        "point": choice("流通方向（e 右 / w 左）", "e", ["e", "w"])}),
    "filter": dict(label="过滤器", factory=parts.make_filter, fields={
        "w": number("宽度", 48, 16, 300),
        "h": number("高度", 26, 12, 180),
        "stub": number("接管长度", 10, 4, 100),
        "n": integer("网格线数", 7, 3, 25)}),
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


def describe(kind, params):
    """返回以中心为原点的尺寸、端口和法向；SVG 由 renderer 生成。"""
    params = normalize_params(kind, params)
    part = make_registered(kind, params)
    if kind in ("compressor", "expansion_valve", "four_way_valve",
                "solenoid_valve"):
        w = 2 * params["r"]
        h = w
        if kind == "compressor" and params["style"] == "方形":
            w = params["r"]
    else:
        w, h = params["w"], params["h"]
    left, top, right, bottom = -w / 2, -h / 2, w / 2, h / 2
    if kind == "separator_utube":
        top -= params["stub"]
    elif kind == "four_way_valve" and params["mark"]:
        left -= 30
        right += 30
        top -= 30
        bottom += 30
    elif kind in ("globe_valve", "solenoid_valve"):
        left = min(left - 12, -params["handle"] / 2)
        right = max(right + 12, params["handle"] / 2)
        top -= params["stem"]
    elif kind in ("check_valve", "filter"):
        left -= params["stub"]
        right += params["stub"]
    return dict(width=w, height=h, box=[left - 3, top - 3,
                                      right - left + 6, bottom - top + 6],
                ports={key: dict(point=list(point),
                                 direction=list(part.direction(key)))
                       for key, point in part.ports.items()})
