"""检查结果反映可编辑图纸的问题，不误报备用端口或改变图纸。"""
import base64
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene


def inspect(document, bounds=None, routes=None):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript diagram check")
    scene = resolve_scene(document)
    if routes is None:
        routes = {edge["id"]: edge["points"] for edge in scene["edges"]}
    raw = Path(__file__).resolve().parents[1].joinpath("web/checks.js").read_bytes()
    uri = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    script = ("import fs from 'node:fs';const checks=await import("
              + json.dumps(uri) + ");const input=JSON.parse(fs.readFileSync(0,'utf8'));"
              "const before=JSON.stringify(input);"
              "const issues=checks.inspectDiagram(input.document,{nodes:input.nodes,"
              "routes:new Map(Object.entries(input.routes)),bounds:input.bounds});"
              "console.log(JSON.stringify({issues,unchanged:before===JSON.stringify(input)}));")
    result = subprocess.run([executable, "--input-type=module", "-e", script],
                            input=json.dumps(dict(document=scene["document"],
                                                 nodes=scene["nodes"], routes=routes,
                                                 bounds=bounds or [])),
                            encoding="utf-8", capture_output=True, check=True)
    output = json.loads(result.stdout)
    assert output["unchanged"]
    return output["issues"]


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_templates_do_not_require_all_optional_ports_to_be_connected(name):
    assert inspect(load_template(name)) == []


def test_empty_drawing_has_no_connection_issues():
    document = dict(schemaVersion=1, nodes=[], edges=[], labels=[], junctions=[])
    assert inspect(document) == []


def test_isolated_device_and_open_junctions_are_locatable():
    document = load_template("evi_ftvi")
    device = copy.deepcopy(document["nodes"][0])
    device["id"] = "unused"
    document["nodes"].append(device)
    document["junctions"].append(dict(id="open", x=100, y=100))
    document["junctions"].append(dict(id="single", x=200, y=100))
    document["edges"].append(dict(id="branch", source=dict(junctionId="single"),
                                  target=dict(nodeId="comp", portId="right")))
    issues = inspect(document)
    assert [(i["code"], i["ref"]) for i in issues] == [
        ("isolated-node", dict(kind="node", id="unused")),
        ("open-junction", dict(kind="junction", id="open")),
        ("open-junction", dict(kind="junction", id="single")),
    ]


def test_two_pipe_junction_is_valid_during_drawing():
    document = load_template("evi_ftvi")
    document["edges"] = [e for e in document["edges"] if e["id"] != "branch-in"]
    # Removing one of three incident pipes should not warn about the junction.
    issues = inspect(document)
    assert not any(i["code"] == "open-junction" and i["ref"]["id"] == "split"
                   for i in issues)


def test_same_port_loop_is_reported_but_two_ports_of_same_device_are_allowed():
    document = load_template("evi_ftvi")
    document["edges"].extend([
        dict(id="self", source=dict(nodeId="comp", portId="left"),
             target=dict(nodeId="comp", portId="left")),
        dict(id="bypass", source=dict(nodeId="comp", portId="left"),
             target=dict(nodeId="comp", portId="right")),
    ])
    assert [(i["code"], i["ref"]["id"]) for i in inspect(document)] == [
        ("same-endpoint", "self")]


def test_reverse_duplicate_is_detected_with_redundant_bends_and_different_style():
    document = load_template("evi_ftvi")
    original = next(e for e in document["edges"] if e["id"] == "injection")
    duplicate = copy.deepcopy(original)
    duplicate.update(id="duplicate", source=original["target"],
                     target=original["source"], color="#ff0000", linestyle="dashed")
    document["edges"].append(duplicate)
    routes = {e["id"]: e["points"] for e in resolve_scene(document)["edges"]}
    routes["duplicate"] = [[558, 272], [400, 272], [400, 272], [143, 272]]
    issues = inspect(document, routes=routes)
    assert [(i["code"], i["ref"]["id"]) for i in issues] == [
        ("duplicate-edge", "duplicate")]


def test_parallel_pipes_and_backtracking_routes_are_not_called_duplicates():
    document = load_template("evi_ftvi")
    edge = next(e for e in document["edges"] if e["id"] == "injection")
    for identity in ("parallel", "backtrack"):
        document["edges"].append(dict(copy.deepcopy(edge), id=identity))
    routes = {e["id"]: e["points"] for e in resolve_scene(document)["edges"]}
    routes["parallel"] = [[143, 272], [143, 250], [558, 250], [558, 272]]
    routes["backtrack"] = [[143, 272], [560, 272], [558, 272]]
    assert inspect(document, routes=routes) == []


def test_port_aliases_are_compared_by_physical_point():
    document = load_template("evi_ftvi")
    original = next(e for e in document["edges"] if e["id"] == "discharge")
    duplicate = copy.deepcopy(original)
    duplicate.update(id="alias", source=dict(nodeId="comp", portId="suction"))
    document["edges"].extend([duplicate, dict(
        id="self-alias", source=dict(nodeId="comp", portId="top"),
        target=dict(nodeId="comp", portId="suction"))])
    assert [(i["code"], i["ref"]["id"]) for i in inspect(document)] == [
        ("duplicate-edge", "alias"), ("same-endpoint", "self-alias")]


def test_distinct_endpoints_at_same_position_have_zero_length():
    document = load_template("evi_ftvi")
    document["junctions"].extend([dict(id="a", x=80, y=80),
                                  dict(id="b", x=80, y=80)])
    document["edges"].append(dict(id="zero", source=dict(junctionId="a"),
                                  target=dict(junctionId="b")))
    issues = inspect(document)
    assert any(i["code"] == "zero-length" and i["ref"]["id"] == "zero"
               for i in issues)


@pytest.mark.parametrize("box,expected", [
    ([0, 0, 760, 580], False), ([-1, 0, 10, 10], True),
    ([750, 10, 11, 10], True), ([10, 575, 10, 6], True),
])
def test_object_bounds_report_page_overflow_once(box, expected):
    document = load_template("evi_ftvi")
    bound = dict(kind="label", id=document["labels"][0]["id"], box=box)
    issues = inspect(document, bounds=[bound, bound])
    assert len([i for i in issues if i["code"] == "outside-page"]) == int(expected)


def test_bend_outside_page_is_reported_even_when_endpoints_are_inside():
    document = load_template("evi_ftvi")
    document["edges"][0]["vertices"] = [[-20, 20], [700, 20]]
    assert any(i["code"] == "outside-page"
               and i["ref"] == dict(kind="edge", id=document["edges"][0]["id"])
               for i in inspect(document))
