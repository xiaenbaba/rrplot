"""VRF 模板的三支路流向、回油、测量支路及 EVI 接管。"""
from collections import Counter

import pytest

from rrplot.scene import load_template, resolve_scene
from rrplot.scene_renderer import export_scene

NAMES = ("vrf_multisplit_cooling", "vrf_multisplit_evi_heating")


def port(node, name):
    return dict(nodeId=node, portId=name)


def junction(name):
    return dict(junctionId=name)


def assert_pipe(document, source, target):
    matches = [e for e in document["edges"]
               if e["source"] == source and e["target"] == target]
    assert len(matches) == 1, (source, target)
    return matches[0]


@pytest.mark.parametrize("name", NAMES)
def test_vrf_three_parallel_indoor_branches_follow_declared_mode(name):
    document = load_template(name)
    heating = name.endswith("heating")
    nodes = {n["id"]: n for n in document["nodes"]}
    for i in (1, 2, 3):
        coil, eev = f"indoor-{i}", f"eev-{i}"
        assert nodes[coil]["type"] == "heat_exchanger"
        assert nodes[coil]["params"]["shape"] == "fan_coil"
        assert nodes[eev]["type"] == "expansion_valve"
        if heating:
            path = [junction(f"gas-{i}"), port(coil, "left"),
                    port(coil, "right"), port(eev, "in"),
                    port(eev, "out"), junction(f"liquid-{i}")]
        else:
            path = [junction(f"liquid-{i}"), port(eev, "in"),
                    port(eev, "out"), port(coil, "right"),
                    port(coil, "left"), junction(f"gas-{i}")]
        for a, b in zip(path, path[1:]):
            if a.get("nodeId") is not None and a.get("nodeId") == b.get("nodeId"):
                continue
            assert assert_pipe(document, a, b)["head"]
    gas_in = (port("reversing", "evaporator"), port("gas-stop", "in"))
    outdoor = (port("reversing", "condenser"), port("outdoor", "top"))
    assert_pipe(document, *(gas_in if heating else gas_in[::-1]))
    assert_pipe(document, *(outdoor[::-1] if heating else outdoor))
    for i in (1, 2):
        gas = (junction(f"gas-{i}"), junction(f"gas-{i+1}"))
        liquid = (junction(f"liquid-{i+1}"), junction(f"liquid-{i}"))
        assert_pipe(document, *(gas if heating else gas[::-1]))
        assert_pipe(document, *(liquid[::-1] if heating else liquid))


@pytest.mark.parametrize("name", NAMES)
def test_vrf_oil_return_and_suction_use_separate_connected_branches(name):
    document = load_template(name)
    for source, target in [
        (port("comp", "top"), port("oil", "left")),
        (port("oil", "top"), junction("discharge-tap")),
        (junction("discharge-tap"), port("reversing", "exhaust")),
        (port("oil", "bottom"), port("capillary", "in")),
        (port("capillary", "out"), junction("oil-return")),
        (port("reversing", "suction"), junction("suction-tap")),
        (junction("suction-tap"), port("separator", "in")),
        (port("separator", "out"), junction("oil-return")),
        (junction("oil-return"), port("comp", "bottom")),
    ]:
        assert_pipe(document, source, target)
    for sensor, tap in (("pressure-high", "discharge-tap"),
                        ("pressure-low", "suction-tap")):
        assert not assert_pipe(document, junction(tap), port(sensor, "tap"))["head"]
        assert sum(ref.get("nodeId") == sensor for e in document["edges"]
                   for ref in (e["source"], e["target"])) == 1


def test_vrf_evi_upper_takeoff_splits_before_main_passage_and_injects_left():
    document = load_template(NAMES[1])
    path = [port("liquid-stop", "in"), junction("injection-split"),
            port("injection-eev", "in"), port("injection-eev", "out"),
            port("economizer", "sub_in"), port("economizer", "sub_out"),
            port("comp", "left")]
    for a, b in zip(path, path[1:]):
        if a.get("nodeId") is not None and a.get("nodeId") == b.get("nodeId"):
            continue
        assert_pipe(document, a, b)
    # The main pass flows right to left through the lower channel;
    # the two geometric main port IDs stay stable when reversing flow.
    assert_pipe(document, junction("injection-split"),
                port("economizer", "main_out"))
    assert_pipe(document, port("economizer", "main_in"),
                port("outdoor-eev", "in"))
    assert_pipe(document, port("outdoor-eev", "out"), port("outdoor", "bottom"))
    cooling = load_template(NAMES[0])
    assert not any(n["type"] == "intermediate_hex" for n in cooling["nodes"])


def test_vrf_evi_upper_takeoff_runs_above_main_and_returns_without_bottom_loop():
    scene = resolve_scene(load_template(NAMES[1]))
    nodes = {node["id"]: node for node in scene["nodes"]}
    edges = {edge["id"]: edge for edge in scene["edges"]}
    hx, eev, comp = (nodes[name] for name in
                     ("economizer", "injection-eev", "comp"))
    split = next(j for j in scene["document"]["junctions"]
                 if j["id"] == "injection-split")
    main_y = edges["pipe-economizer-split"]["points"][-1][1]
    upper_y = edges["pipe-injection-hex"]["points"][-1][1]
    assert split["x"] > eev["x"] > hx["x"] + hx["params"]["w"]/2
    assert split["y"] == main_y > upper_y == eev["y"]
    assert all(point[1] == upper_y
               for point in edges["pipe-injection-hex"]["points"])
    injection = edges["pipe-injection"]["points"]
    assert max(point[1] for point in injection) == upper_y
    assert injection[-1] == [comp["x"]-comp["params"]["r"], comp["y"]]


@pytest.mark.parametrize("name", NAMES)
def test_vrf_routes_avoid_bodies_and_keep_all_junctions_connected(name):
    scene = resolve_scene(load_template(name))
    degrees = Counter(ref["junctionId"] for e in scene["edges"]
                      for ref in (e["source"], e["target"]) if "junctionId" in ref)
    assert all(degrees[j["id"]] >= 2 for j in scene["document"]["junctions"])
    for edge in scene["edges"]:
        for a, b in zip(edge["points"], edge["points"][1:]):
            assert a != b
            assert a[0] == b[0] or a[1] == b[1]
            for n in scene["nodes"]:
                p = n["params"]
                w, h = (2*p["r"], 2*p["r"]) if "r" in p else (p["w"], p["h"])
                if n["rotation"] in (90, 270):
                    w, h = h, w
                left, right = n["x"]-w/2, n["x"]+w/2
                top, bottom = n["y"]-h/2, n["y"]+h/2
                crosses = (left < a[0] < right and max(a[1], b[1]) > top
                           and min(a[1], b[1]) < bottom) if a[0] == b[0] else (
                    top < a[1] < bottom and max(a[0], b[0]) > left
                    and min(a[0], b[0]) < right)
                assert not crosses, (edge["id"], n["id"])


@pytest.mark.parametrize("name", NAMES)
def test_vrf_device_labels_follow_moves_and_all_formats_export(name):
    document = load_template(name)
    before = resolve_scene(document)
    next(n for n in document["nodes"] if n["id"] == "indoor-2")["x"] += 30
    after = resolve_scene(document)
    original = next(label for label in before["labels"]
                    if label.get("nodeId") == "indoor-2")
    moved = next(label for label in after["labels"]
                 if label.get("nodeId") == "indoor-2")
    assert moved["position"] == [original["position"][0]+30, original["position"][1]]
    for fmt, signature in (("svg", b"<?xml"), ("png", b"\x89PNG"),
                           ("pdf", b"%PDF")):
        assert export_scene(document, fmt).startswith(signature)
