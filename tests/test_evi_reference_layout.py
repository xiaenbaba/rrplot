"""参考图布局：主路左右穿过过冷器，补气支路底进顶出。"""

import pytest
from matplotlib.transforms import Bbox

from rrplot.scene import endpoint, load_template, resolve_scene
from rrplot.scene_renderer import build_scene


def test_evi_reference_main_and_injection_paths_use_real_ports():
    document = load_template("evi_intermediate")
    edges = {edge["id"]: edge for edge in document["edges"]}

    def port(node, name):
        return dict(nodeId=node, portId=name)

    split = dict(junctionId="split")
    expected = {
        "suction": (port("evap", "top"), port("comp", "bottom")),
        "discharge": (port("comp", "top"), port("cond", "left")),
        "cond-split": (port("cond", "right"), split),
        "main-in": (split, port("hex", "right")),
        "main-out": (port("hex", "left"), port("eev2", "in")),
        "to-evap": (port("eev2", "out"), port("evap", "bottom")),
        "branch-in": (split, port("eev1", "in")),
        "branch-expanded": (port("eev1", "out"), port("hex", "bottom")),
        "branch-solenoid": (port("hex", "top"), port("solenoid", "out")),
        "injection": (port("solenoid", "in"), port("comp", "vapor_inj")),
    }
    assert set(edges) == set(expected)
    for key, (source, target) in expected.items():
        assert edges[key]["source"] == source
        assert edges[key]["target"] == target


def test_evi_reference_geometry_matches_reference_arrangement():
    scene = resolve_scene(load_template("evi_intermediate"))
    nodes = {node["id"]: node for node in scene["nodes"]}
    junctions = {j["id"]: j for j in scene["document"]["junctions"]}
    edges = {edge["id"]: edge for edge in scene["edges"]}

    def point(node, port):
        return endpoint(dict(nodeId=node, portId=port), nodes, junctions)["point"]

    comp, cond, evap, hx = (nodes[key] for key in ("comp", "cond", "evap", "hex"))
    assert comp["rotation"] == 90
    assert point("comp", "bottom")[0] < comp["x"] < point("comp", "top")[0]
    assert comp["y"] == cond["y"] < evap["y"] < hx["y"]
    assert evap["params"]["h"] > evap["params"]["w"]
    assert cond["params"]["shape"] == evap["params"]["shape"] == "rect_x"
    assert hx["type"] == "heat_exchanger"
    assert hx["params"]["shape"] == "rect_zigzag7"
    assert nodes["eev2"]["x"] < hx["x"] < nodes["eev1"]["x"] < junctions["split"]["x"]
    assert nodes["eev2"]["y"] == hx["y"] == junctions["split"]["y"]
    assert nodes["eev1"]["y"] > point("hex", "bottom")[1]
    assert (
        point("hex", "top")[1] > nodes["solenoid"]["y"] > point("comp", "vapor_inj")[1]
    )
    assert all(p[0] == hx["x"] for p in edges["branch-expanded"]["points"][-2:])
    assert all(p[0] == comp["x"] for p in edges["injection"]["points"][-2:])


def test_evi_reference_external_pipes_do_not_cross_equipment_bodies():
    scene = resolve_scene(load_template("evi_intermediate"))
    for edge in scene["edges"]:
        for a, b in zip(edge["points"], edge["points"][1:]):
            assert a != b
            assert a[0] == b[0] or a[1] == b[1]
            for node in scene["nodes"]:
                params = node["params"]
                w, h = (
                    (2 * params["r"], 2 * params["r"])
                    if "r" in params
                    else (params["w"], params["h"])
                )
                left, right = node["x"] - w / 2, node["x"] + w / 2
                top, bottom = node["y"] - h / 2, node["y"] + h / 2
                crosses = (
                    (
                        left < a[0] < right
                        and max(a[1], b[1]) > top
                        and min(a[1], b[1]) < bottom
                    )
                    if a[0] == b[0]
                    else (
                        top < a[1] < bottom
                        and max(a[0], b[0]) > left
                        and min(a[0], b[0]) < right
                    )
                )
                assert not crosses, (edge["id"], node["id"])


def test_evi_reference_formal_labels_fit_page_and_avoid_component_bodies():
    document = load_template("evi_intermediate")
    with build_scene(document) as diagram:
        diagram.fig.canvas.draw()
        renderer = diagram.fig.canvas.get_renderer()
        canvas = diagram.ax.get_window_extent(renderer)
        bodies = []
        for node in document["nodes"]:
            p = node["params"]
            w, h = (2 * p["r"], 2 * p["r"]) if "r" in p else (p["w"], p["h"])
            corners = diagram.ax.transData.transform(
                [
                    [node["x"] - w / 2, node["y"] - h / 2],
                    [node["x"] + w / 2, node["y"] + h / 2],
                ]
            )
            xs, ys = zip(*corners)
            bodies.append(Bbox.from_extents(min(xs), min(ys), max(xs), max(ys)))
        for text in diagram.ax.texts:
            bounds = text.get_window_extent(renderer)
            assert canvas.x0 <= bounds.x0 < bounds.x1 <= canvas.x1
            assert canvas.y0 <= bounds.y0 < bounds.y1 <= canvas.y1
            assert not any(bounds.overlaps(body) for body in bodies), text.get_text()


@pytest.mark.parametrize("device,port", [("comp", "vapor_inj"), ("hex", "bottom")])
def test_evi_reference_moving_device_keeps_pipe_endpoint_attached(device, port):
    document = load_template("evi_intermediate")
    node = next(node for node in document["nodes"] if node["id"] == device)
    before = resolve_scene(document)
    node["x"] += 20
    node["y"] += 10
    after = resolve_scene(document)
    ref = dict(nodeId=device, portId=port)
    for first, moved in zip(before["edges"], after["edges"]):
        for side, index in (("source", 0), ("target", -1)):
            if first[side] == ref:
                assert moved["points"][index] == [
                    first["points"][index][0] + 20,
                    first["points"][index][1] + 10,
                ]
