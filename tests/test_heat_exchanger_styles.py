"""风机盘管合并为换热器样式，以及旧图纸和 Python 端口兼容。"""
import copy
import json

import matplotlib.pyplot as plt
import pytest

from rrplot import Diagram, parts
from rrplot.registry import catalog, describe, make_registered
from rrplot.scene import endpoint, resolve_scene, rotate, validate_scene
from rrplot.scene_renderer import export_scene


def legacy_document(angle=0):
    return dict(schemaVersion=1, title="旧风机盘管图纸",
                page=dict(width=800, height=700),
                nodes=[dict(id="coil", type="fan_coil", title="室内机",
                            x=400, y=350, rotation=angle,
                            params=dict(w=180, h=90, stub=20))],
                junctions=[dict(id="gas", x=80, y=100),
                           dict(id="liquid", x=700, y=600)],
                edges=[dict(id="gas-pipe", source=dict(junctionId="gas"),
                            target=dict(nodeId="coil", portId="in"),
                            vertices=[[80, 250]]),
                       dict(id="liquid-pipe",
                            source=dict(nodeId="coil", portId="out"),
                            target=dict(junctionId="liquid"))],
                labels=[dict(id="name", nodeId="coil", x=5, y=60, text="室内机"),
                        dict(id="state", edgeId="gas-pipe", at=.4,
                             x=2, y=-12, text="P")])


def test_catalog_offers_fan_coil_under_heat_exchanger_only():
    entries = {entry["type"]: entry for entry in catalog()}
    assert "fan_coil" not in entries
    fields = entries["heat_exchanger"]["fields"]
    assert "fan_coil" in fields["shape"]["options"]
    assert fields["shape"]["optionLabels"]["fan_coil"] == "风机盘管"
    assert fields["stub"]["default"] == 0


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_legacy_migration_preserves_geometry_routes_labels_and_roundtrip(angle):
    original = legacy_document(angle)
    before = copy.deepcopy(original)
    doc = validate_scene(original)
    assert original == before
    assert doc["nodes"][0]["type"] == "heat_exchanger"
    assert doc["nodes"][0]["params"] == dict(
        w=180, h=90, shape="fan_coil", orient="h", stub=20)
    assert doc["nodes"][0]["title"] == "室内机"
    assert doc["edges"][0]["target"] == dict(nodeId="coil", portId="left")
    assert doc["edges"][1]["source"] == dict(nodeId="coil", portId="right")
    assert doc["edges"][0]["vertices"] == original["edges"][0]["vertices"]
    scene = resolve_scene(doc)
    node = scene["nodes"][0]
    old = parts.make_fan_coil(w=180, h=90, stub=20)
    old_box = describe("fan_coil", original["nodes"][0]["params"])["box"]
    assert old_box == node["geometry"]["box"]
    for old_port, new_port in (("in", "left"), ("out", "right")):
        expected = rotate(old.port(old_port), angle)
        actual = endpoint(dict(nodeId="coil", portId=new_port), {"coil": node}, {})
        assert actual["point"] == [400 + expected[0], 350 + expected[1]]
        assert actual["direction"] == rotate(old.direction(old_port), angle)
    label = next(label for label in scene["labels"] if label["id"] == "name")
    offset = rotate([5, 60], angle)
    assert label["position"] == [400 + offset[0], 350 + offset[1]]
    assert resolve_scene(json.loads(json.dumps(doc))) == scene
    assert validate_scene(doc) == doc


def test_legacy_defaults_and_current_heat_exchanger_remain_distinct():
    doc = legacy_document()
    doc["nodes"][0]["params"] = {}
    migrated = validate_scene(doc)["nodes"][0]
    assert migrated["params"] == dict(
        w=120, h=64, stub=12, shape="fan_coil", orient="h")
    current = describe("heat_exchanger", {})
    assert current["ports"]["left"]["point"] == [-80, 0]
    assert current["ports"]["top"]["point"] == [0, -28]
    assert current["box"] == [-83, -31, 166, 62]


@pytest.mark.parametrize("shape", parts.HEX_SHAPES)
def test_changing_heat_exchanger_style_keeps_all_ports_and_stub(shape):
    base = describe("heat_exchanger", dict(w=120, h=60, stub=12))
    changed = describe("heat_exchanger", dict(w=120, h=60, stub=12, shape=shape))
    assert changed == base


@pytest.mark.parametrize("w,h,stub", [(16, 700, 100), (700, 16, 100),
                                        (16, 16, 0), (120, 60, 12)])
def test_fan_style_artists_fit_bounds_at_extreme_dimensions(w, h, stub):
    params = dict(w=w, h=h, stub=stub, shape="fan_coil")
    x, y, width, height = describe("heat_exchanger", params)["box"]
    with Diagram(width=width, height=height) as diagram:
        diagram.add(make_registered("heat_exchanger", params), None, loc=(-x, -y))
        diagram.render()
        diagram.fig.canvas.draw()
        renderer = diagram.fig.canvas.get_renderer()
        canvas = diagram.ax.get_window_extent(renderer)
        for artist in [*diagram.ax.lines, *diagram.ax.patches]:
            bounds = artist.get_window_extent(renderer)
            assert canvas.x0 <= bounds.x0 <= bounds.x1 <= canvas.x1
            assert canvas.y0 <= bounds.y0 <= bounds.y1 <= canvas.y1


@pytest.mark.parametrize("fmt,signature", [("svg", b"<?xml"),
                                          ("png", b"\x89PNG"), ("pdf", b"%PDF")])
def test_legacy_document_exports_using_new_heat_exchanger(fmt, signature):
    before = plt.get_fignums()
    assert export_scene(legacy_document(90), fmt).startswith(signature)
    assert plt.get_fignums() == before
