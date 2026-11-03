"""四通阀两工况保留外部接管，流向与声明的阀内连通一致。"""
from itertools import combinations

import pytest

from rrplot.scene import load_template, resolve_scene


def ref(node, port):
    return {"nodeId": node, "portId": port}


@pytest.mark.parametrize("mode", ["heating", "cooling"])
def test_reversible_heat_pump_flow_forms_one_cycle_with_two_valve_passages(mode):
    document = load_template("reversible_heat_pump_" + mode)
    heating = mode == "heating"
    hot, cold = ("indoor", "outdoor") if heating else ("outdoor", "indoor")
    hot_port, cold_port = (("condenser", "evaporator") if heating
                           else ("evaporator", "condenser"))
    # Follow the entire flow, including the two independent valve passages.
    path = [ref("comp", "top"), ref("reversing", "exhaust"),
            ref("reversing", hot_port), ref(hot, "left"), ref(hot, "right")]
    if heating:
        path += [ref("filter", "in"), ref("filter", "out"),
                 ref("eev", "in"), ref("eev", "out")]
    else:
        path += [ref("eev", "in"), ref("eev", "out"),
                 ref("filter", "in"), ref("filter", "out")]
    path += [ref(cold, "right"), ref(cold, "left"),
             ref("reversing", cold_port), ref("reversing", "suction"),
             ref("separator", "in"), ref("separator", "out"),
             ref("comp", "bottom"), ref("comp", "top")]
    external = [(a, b) for a, b in zip(path, path[1:])
                if a["nodeId"] != b["nodeId"]]
    assert len(external) == len(document["edges"]) == 8
    for source, target in external:
        matches = [e for e in document["edges"]
                   if (e["source"], e["target"]) == (source, target)]
        assert len(matches) == 1
        assert matches[0]["head"]
    labels = {label["id"]: label["text"] for label in document["labels"]}
    assert labels["label-" + hot] == (
        ("室内" if heating else "室外") + "换热器\n（冷凝器）")
    assert labels["label-" + cold] == (
        ("室外" if heating else "室内") + "换热器\n（蒸发器）")
    assert labels["valve-state"] == ("阀内连通：D→C，E→S" if heating
                                      else "阀内连通：D→E，C→S")
    assert labels["mode-note"] == ("室内放热 · 室外吸热" if heating
                                     else "室内吸热 · 室外放热")
    assert document["junctions"] == []


def test_reversible_modes_keep_physical_connections_and_positions():
    heating, cooling = [resolve_scene(load_template("reversible_heat_pump_" + mode))
                        for mode in ("heating", "cooling")]
    assert [(n["id"], n["x"], n["y"]) for n in heating["nodes"]] == [
        (n["id"], n["x"], n["y"]) for n in cooling["nodes"]]
    cool_edges = {edge["id"]: edge for edge in cooling["edges"]}
    for edge in heating["edges"]:
        other = cool_edges[edge["id"]]
        if edge["id"] in {"discharge", "suction-in", "suction"}:
            assert edge["source"] == other["source"]
            assert edge["target"] == other["target"]
            assert edge["points"] == other["points"]
        else:
            assert edge["points"] == list(reversed(other["points"]))
    suction = next(e for e in heating["edges"] if e["id"] == "suction")
    assert len(suction["points"]) == 2
    assert suction["points"][0][0] == suction["points"][1][0]


@pytest.mark.parametrize("mode", ["heating", "cooling"])
def test_reversible_template_routes_avoid_device_bodies_and_pipe_crossings(mode):
    scene = resolve_scene(load_template("reversible_heat_pump_" + mode))
    segments = []
    for edge in scene["edges"]:
        for a, b in zip(edge["points"], edge["points"][1:]):
            assert a != b
            assert a[0] == b[0] or a[1] == b[1]
            segments.append((edge["id"], a, b))
            for node in scene["nodes"]:
                params = node["params"]
                if node["type"] in {"compressor", "four_way_valve", "expansion_valve"}:
                    w = h = params["r"] * 2
                else:
                    w, h = params["w"], params["h"]
                if node["rotation"] in (90, 270):
                    w, h = h, w
                left, right = node["x"] - w / 2, node["x"] + w / 2
                top, bottom = node["y"] - h / 2, node["y"] + h / 2
                if a[0] == b[0]:
                    intersects = (left < a[0] < right
                                  and max(a[1], b[1]) > top
                                  and min(a[1], b[1]) < bottom)
                else:
                    intersects = (top < a[1] < bottom
                                  and max(a[0], b[0]) > left
                                  and min(a[0], b[0]) < right)
                assert not intersects, (edge["id"], node["id"])
    # These templates need neither shared pipe segments nor crossing marks.
    for (first, a, b), (second, c, d) in combinations(segments, 2):
        if first == second:
            continue
        overlap_x = min(max(a[0], b[0]), max(c[0], d[0])) >= max(
            min(a[0], b[0]), min(c[0], d[0]))
        overlap_y = min(max(a[1], b[1]), max(c[1], d[1])) >= max(
            min(a[1], b[1]), min(c[1], d[1]))
        assert not (overlap_x and overlap_y), (first, second)
