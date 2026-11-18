"""VRF 图元的绘制边界、接管语义及 Web/Python 导出一致性。"""
import json

import matplotlib.pyplot as plt
import pytest

from rrplot import Diagram, parts
from rrplot.registry import REGISTRY, describe, make_registered, normalize_params
from rrplot.scene import endpoint, resolve_scene, rotate, validate_scene
from rrplot.scene_renderer import build_scene, export_scene, resolve_for_editor

PORTS = {
    "oil_separator": {"left", "top", "bottom"},
    "capillary": {"in", "out"},
    "fan_coil": {"in", "out"},
    "muffler": {"in", "out"},
    "sensor": {"tap"},
}


def vrf_document(kind, params=None, rotation=0):
    params = params or {}
    return validate_scene(dict(
        schemaVersion=1, page=dict(width=800, height=700),
        nodes=[dict(id="device", type=kind, params=params, x=400, y=350,
                    rotation=rotation)],
        junctions=[dict(id="end", x=70, y=60)],
        edges=[dict(id=f"pipe-{i}", source=dict(nodeId="device", portId=p),
                    target=dict(junctionId="end"))
               for i, p in enumerate(sorted(PORTS[kind]))]))


@pytest.mark.parametrize("kind", PORTS)
@pytest.mark.parametrize("size", ["default", "min", "max", "narrow", "short"])
def test_vrf_glyph_bounds_contain_drawn_artists_and_ports(kind, size):
    fields = REGISTRY[kind]["fields"]
    params = {}
    for key, field in fields.items():
        if "min" not in field:
            continue
        bound = {"default": "default", "min": "min", "max": "max",
                 "narrow": "min" if key in ("w", "r") else "max",
                 "short": "min" if key == "h" else "max"}[size]
        params[key] = field[bound]
    geometry = describe(kind, params)
    assert set(geometry["ports"]) == PORTS[kind]
    x, y, width, height = geometry["box"]
    for port in geometry["ports"].values():
        px, py = port["point"]
        assert x < px < x + width and y < py < y + height
    before = plt.get_fignums()
    with Diagram(width=width, height=height) as diagram:
        diagram.add(make_registered(kind, params), None, loc=(-x, -y))
        diagram.render()
        diagram.fig.canvas.draw()
        renderer = diagram.fig.canvas.get_renderer()
        canvas = diagram.ax.get_window_extent(renderer)
        for artist in [*diagram.ax.lines, *diagram.ax.patches, *diagram.ax.texts]:
            bounds = artist.get_window_extent(renderer)
            assert canvas.x0 <= bounds.x0 <= bounds.x1 <= canvas.x1
            assert canvas.y0 <= bounds.y0 <= bounds.y1 <= canvas.y1
    assert plt.get_fignums() == before


@pytest.mark.parametrize("kind,params", [
    ("oil_separator", dict(w=64, h=176, stub=16)),
    ("capillary", dict(w=28, h=120, n=8)),
    ("fan_coil", dict(w=180, h=90, stub=20)),
    ("muffler", dict(w=48, h=100, stub=20)),
    ("sensor", dict(r=20, stub=18, mark="P")),
])
@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_vrf_resized_rotated_ports_match_rendered_connections(kind, params, angle):
    document = vrf_document(kind, params, angle)
    scene = resolve_scene(document)
    node = scene["nodes"][0]
    part = make_registered(kind, params)
    for edge in scene["edges"]:
        name = edge["source"]["portId"]
        if kind == "fan_coil":
            name = {"left": "in", "right": "out"}[name]
        result = endpoint(edge["source"], {"device": node}, {})
        offset = rotate(part.port(name), angle)
        assert result["point"] == [400 + offset[0], 350 + offset[1]]
        assert result["direction"] == rotate(part.direction(name), angle)
        assert edge["points"][0] == result["point"]
        assert all(a[0] == b[0] or a[1] == b[1]
                   for a, b in zip(edge["points"], edge["points"][1:]))
    assert resolve_scene(json.loads(json.dumps(document)))["edges"] == scene["edges"]
    editor = resolve_for_editor(document)
    assert editor["nodes"][0]["geometry"]["image"].startswith(
        "data:image/svg+xml;base64,")


def test_vrf_port_semantics_and_original_capillary_are_preserved():
    oil = describe("oil_separator", dict(w=40, h=100, stub=12))["ports"]
    assert oil["left"]["point"] == [-32, -25]
    assert oil["top"]["point"] == [0, -62]
    assert oil["bottom"]["point"] == [0, 62]
    assert describe("sensor", dict(r=20, stub=18))["ports"] == {
        "tap": dict(point=[0, 38], direction=[0, 1])}
    assert parts.capillary.port("in") == (0, -40)
    assert parts.capillary.port("out") == (0, 40)


@pytest.mark.parametrize("value", [True, 0, 26, 2.5, "5"])
def test_capillary_rejects_invalid_turn_count(value):
    with pytest.raises(ValueError):
        normalize_params("capillary", dict(n=value))


def test_capillary_integer_normalization_and_sensor_mark_validation():
    normalized = normalize_params("capillary", dict(n=7.0))
    assert type(normalized["n"]) is int
    assert normalized["n"] == 7
    with pytest.raises(ValueError):
        make_registered("sensor", dict(mark="X"))
    with pytest.raises(ValueError):
        parts.make_capillary(n=True)


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("mark", ["T", "P"])
def test_sensor_mark_follows_glyph_rotation(angle, mark):
    with build_scene(vrf_document("sensor", dict(mark=mark), angle)) as diagram:
        text = next(text for text in diagram.ax.texts if text.get_text() == mark)
        position = diagram.ax.transData.inverted().transform(
            text.get_transform().transform(text.get_position()))
        assert position == pytest.approx([400, 350])
        assert text.get_rotation() == (-angle) % 360


@pytest.mark.parametrize("kind", PORTS)
def test_vrf_all_export_formats(kind):
    document = vrf_document(kind, rotation=90)
    for fmt, signature in (("svg", b"<?xml"), ("png", b"\x89PNG"),
                           ("pdf", b"%PDF")):
        assert export_scene(document, fmt).startswith(signature)
