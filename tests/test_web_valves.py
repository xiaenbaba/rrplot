"""常用阀件的 Web 图元边界、端口、旋转口标及导出契约。"""
import json

import matplotlib.pyplot as plt
import pytest

from rrplot import Diagram
from rrplot.registry import catalog, describe, make_registered, normalize_params
from rrplot.scene import endpoint, resolve_scene, rotate, validate_scene
from rrplot.scene_renderer import build_scene, export_scene, resolve_for_editor

KINDS = ("four_way_valve", "globe_valve", "solenoid_valve", "check_valve",
         "filter")


def valve_document(kind, params=None, rotation=0):
    ports = describe(kind, params or {})["ports"]
    return validate_scene(dict(schemaVersion=1, page=dict(width=600, height=500),
                               nodes=[dict(id="valve", type=kind,
                                           params=params or {}, x=300, y=250,
                                           rotation=rotation)],
                               junctions=[dict(id="end", x=70, y=60)],
                               edges=[dict(id=f"pipe-{i}",
                                           source=dict(nodeId="valve", portId=p),
                                           target=dict(junctionId="end"))
                                      for i, p in enumerate(ports)],
                               labels=[dict(id="tag", nodeId="valve", text=kind,
                                            x=0, y=60)]))


@pytest.mark.parametrize("kind,params", [
    *((kind, {}) for kind in KINDS),
    ("four_way_valve", dict(r=8, mark=True)),
    ("four_way_valve", dict(r=150, mark=False)),
    ("globe_valve", dict(w=16, h=12, stem=100, handle=240)),
    ("solenoid_valve", dict(r=6, stem=100, handle=240)),
    ("check_valve", dict(w=300, h=180, stub=100, point="w")),
    ("filter", dict(w=16, h=180, stub=100, n=25)),
])
def test_valve_bounds_contain_ports_actuators_and_port_letters(kind, params):
    geometry = describe(kind, params)
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


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_valve_ports_rotate_with_geometry_and_keep_connections(kind, rotation):
    document = valve_document(kind, rotation=rotation)
    scene = resolve_scene(document)
    nodes = {node["id"]: node for node in scene["nodes"]}
    part = make_registered(kind, {})
    for edge in scene["edges"]:
        name = edge["source"]["portId"]
        expected = rotate(part.port(name), rotation)
        result = endpoint(edge["source"], nodes, {})
        assert result["point"] == [300 + expected[0], 250 + expected[1]]
        assert result["direction"] == rotate(part.direction(name), rotation)
        assert edge["points"][0] == result["point"]
        assert all(a[0] == b[0] or a[1] == b[1]
                   for a, b in zip(edge["points"], edge["points"][1:]))
    assert resolve_scene(json.loads(json.dumps(document)))["edges"] == scene["edges"]


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_four_way_export_letters_follow_the_same_rotated_ports_as_browser(angle):
    document = valve_document("four_way_valve", rotation=angle)
    mapping = dict(D="exhaust", C="condenser", E="evaporator", S="suction")
    offsets = dict(D=(0, -42), C=(42, 0), E=(0, 42), S=(-42, 0))
    with build_scene(document) as diagram:
        texts = {text.get_text(): text for text in diagram.ax.texts
                 if text.get_text() in mapping}
        assert set(texts) == set(mapping)
        for letter, text in texts.items():
            rendered = diagram.ax.transData.inverted().transform(
                text.get_transform().transform(text.get_position()))
            offset = rotate(offsets[letter], angle)
            assert rendered == pytest.approx([300 + offset[0], 250 + offset[1]])
            assert text.get_rotation() == (-angle) % 360
    document["nodes"][0]["params"]["mark"] = False
    with build_scene(document) as diagram:
        assert not any(text.get_text() in mapping for text in diagram.ax.texts)


def test_check_valve_reverse_direction_exchanges_port_positions_and_normals():
    right = describe("check_valve", dict(point="e", w=70, stub=20))["ports"]
    left = describe("check_valve", dict(point="w", w=70, stub=20))["ports"]
    assert left["in"] == right["out"] and left["out"] == right["in"]
    assert right["in"]["point"] == [-55, 0]


@pytest.mark.parametrize("params", [dict(n=3.5), dict(n=True), dict(n=26),
                                    dict(n=2), dict(n="7")])
def test_filter_grid_count_rejects_invalid_numbers(params):
    with pytest.raises(ValueError):
        normalize_params("filter", params)


def test_filter_grid_count_normalizes_whole_number_and_ui_step():
    assert normalize_params("filter", dict(n=7.0))["n"] == 7
    assert isinstance(normalize_params("filter", dict(n=7.0))["n"], int)
    fields = next(item["fields"] for item in catalog() if item["type"] == "filter")
    assert fields["n"]["step"] == 1


@pytest.mark.parametrize("kind", KINDS)
def test_valve_svg_and_all_export_formats_after_resizing(kind):
    params = {"r": 38} if kind in ("four_way_valve", "solenoid_valve") else {
        "w": 72, "h": 40}
    document = valve_document(kind, params=params, rotation=90)
    scene = resolve_for_editor(document)
    assert scene["nodes"][0]["geometry"]["image"].startswith(
        "data:image/svg+xml;base64,")
    for fmt, signature in (("svg", b"<?xml"), ("png", b"\x89PNG"),
                           ("pdf", b"%PDF")):
        assert export_scene(document, fmt).startswith(signature)
