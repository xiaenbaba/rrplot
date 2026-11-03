"""浏览器管路线段拖动与正式输出的一致性。"""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, endpoint, load_template, resolve_scene, route


def run_geometry(cases):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript geometry check")
    raw = Path(__file__).resolve().parents[1].joinpath("web/geometry.js").read_bytes()
    module = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    script = ("import fs from 'node:fs';"
              "const {route,editableSegments,moveSegment}=await import("
              + json.dumps(module) + ");"
              "const cases=JSON.parse(fs.readFileSync(0,'utf8'));"
              "console.log(JSON.stringify(cases.map(([a,b,vertices])=>({"
              "original:vertices, moves:editableSegments(a,b,vertices).map(s=>({"
              "segment:s, results:[0,-35,26.5].map(offset=>{"
              "const v=moveSegment(a,b,vertices,s.index,offset);"
              "return {offset,vertices:v,points:route(a,b,v)};})}))}))));")
    result = subprocess.run([executable, "--input-type=module", "-e", script],
                            input=json.dumps(cases), encoding="utf-8",
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def check_moves(cases, results):
    for (source, target, vertices), result in zip(cases, results):
        assert result["original"] == vertices
        for move in result["moves"]:
            segment = move["segment"]
            axis = segment["axis"]
            for moved in move["results"]:
                points = moved["points"]
                assert points[0] == source["point"]
                assert points[-1] == target["point"]
                assert all(a[0] == b[0] or a[1] == b[1]
                           for a, b in zip(points, points[1:]))
                assert points == route(source, target, moved["vertices"])
                if not moved["offset"]:
                    assert moved["vertices"] == vertices
                    continue
                coordinate = segment["point"][axis] + moved["offset"]
                midpoint = segment["point"][1 - axis]
                assert any(a[axis] == b[axis] == coordinate
                           and min(a[1 - axis], b[1 - axis]) < midpoint
                           < max(a[1 - axis], b[1 - axis])
                           for a, b in zip(points, points[1:]))
                for ref, adjacent in ((source, points[1]), (target, points[-2])):
                    if any(ref["direction"]):
                        assert adjacent == [p + n * 20 for p, n in
                                            zip(ref["point"], ref["direction"])]


def test_segment_moves_preserve_ports_junctions_and_export_routes():
    cases = []
    for name in TEMPLATES:
        scene = resolve_scene(load_template(name))
        nodes = {n["id"]: n for n in scene["nodes"]}
        junctions = {j["id"]: j for j in scene["document"]["junctions"]}
        for edge in scene["edges"]:
            cases.append([endpoint(edge["source"], nodes, junctions),
                          endpoint(edge["target"], nodes, junctions),
                          edge["vertices"]])
    results = run_geometry(cases)
    assert sum(len(result["moves"]) for result in results) > 20
    check_moves(cases, results)


@pytest.mark.parametrize("axis", [0, 1])
def test_straight_pipe_drag_adds_elbows_and_preserves_end_lead_ins(axis):
    start = dict(point=[0, 0], direction=[1 - axis, axis])
    end = dict(point=[200 * (1 - axis), 200 * axis],
               direction=[axis - 1, -axis])
    cases = [[start, end, []]]
    result = run_geometry(cases)
    assert len(result[0]["moves"]) == 1
    check_moves(cases, result)


def test_short_pipe_and_port_lead_ins_do_not_offer_drag_handles():
    cases = [[dict(point=[0, 0], direction=[1, 0]),
              dict(point=[40, 0], direction=[-1, 0]), []],
             [dict(point=[0, 0], direction=[1, 0]),
              dict(point=[200, 100], direction=[-1, 0]), [[100, 0]]]]
    results = run_geometry(cases)
    assert results[0]["moves"] == []
    last_segment = len(route(*cases[1])) - 2
    assert all(move["segment"]["index"] not in (0, last_segment)
               for move in results[1]["moves"])
