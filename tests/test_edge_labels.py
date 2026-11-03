"""管路状态点的前后端位置、编辑生命周期与导出。"""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, validate_scene
from rrplot.scene_renderer import build_scene, export_scene, resolve_for_editor


def state_document():
    document = load_template("evi_ftvi")
    document["labels"].append(dict(id="follow", edgeId="injection", at=.25,
                                    x=8, y=-14, text="T1", size=12, ha="center",
                                    color="#111111", boxed=True))
    return validate_scene(document)


def run_js(script, payload):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript label check")
    root = Path(__file__).resolve().parents[1] / "web"
    imports = []
    for name in ("geometry", "document"):
        uri = "data:text/javascript;base64," + base64.b64encode(
            (root / (name + ".js")).read_bytes()).decode()
        imports.append(f"const {name}=await import({json.dumps(uri)});")
    source = ("import fs from 'node:fs';" + "".join(imports)
              + "const input=JSON.parse(fs.readFileSync(0,'utf8'));" + script)
    result = subprocess.run([executable, "--input-type=module", "-e", source],
                            input=json.dumps(payload), encoding="utf-8",
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def positions(document):
    return {label["id"]: label["position"]
            for label in resolve_scene(document)["labels"]}


@pytest.mark.parametrize("at", [0, .25, .5, 1])
def test_label_follows_length_fraction_and_moving_endpoint(at):
    document = state_document()
    document["labels"][-1]["at"] = at
    assert positions(document)["follow"] == [151 + 415 * at, 258]
    next(n for n in document["nodes"] if n["id"] == "comp")["x"] += 100
    assert positions(document)["follow"] == [151 + 515 * at, 258]


def test_label_follows_manual_elbows_and_editor_advertises_support():
    document = state_document()
    document["labels"][-1]["at"] = .5
    next(e for e in document["edges"] if e["id"] == "injection")["vertices"] = [
        [200, 180], [500, 180]]
    assert positions(document)["follow"] == [358.5, 166]
    assert "edgeLabels" in resolve_for_editor(document)["features"]


@pytest.mark.parametrize("change", [
    dict(edgeId="missing"), dict(edgeId=[]), dict(edgeId=3),
    dict(nodeId="comp"), dict(at=-.1), dict(at=1.1), dict(at=True),
    dict(at=".5"), dict(at=float("nan")), dict(at=float("inf")),
])
def test_invalid_state_attachment_is_rejected(change):
    document = state_document()
    document["labels"][-1].update(change)
    with pytest.raises(ValueError):
        validate_scene(document)


@pytest.mark.parametrize("fmt,signature", [("svg", b"<?xml"),
                                          ("png", b"\x89PNG"), ("pdf", b"%PDF")])
def test_json_roundtrip_and_export_use_resolved_state_position(fmt, signature):
    document = state_document()
    reopened = validate_scene(json.loads(json.dumps(document)))
    assert reopened == document
    with build_scene(reopened) as diagram:
        label = next(text for text in diagram.ax.texts if text.get_text() == "T1")
        assert list(label.get_position()) == positions(document)["follow"]
    assert export_scene(reopened, fmt).startswith(signature)


def test_browser_along_matches_backend_on_all_template_routes():
    cases = []
    expected = []
    for name in TEMPLATES:
        document = load_template(name)
        for edge in document["edges"]:
            for at in (0, .37, 1):
                document["labels"].append(dict(id=f"s-{len(expected)}",
                                                edgeId=edge["id"], at=at,
                                                x=5, y=-13, text="s"))
                expected.append(f"s-{len(expected)}")
        scene = resolve_scene(document)
        routes = {edge["id"]: edge["points"] for edge in scene["edges"]}
        for label in scene["labels"]:
            if "edgeId" in label:
                cases.append(dict(points=routes[label["edgeId"]],
                                  at=label["at"], expected=label["position"]))
    actual = run_js("console.log(JSON.stringify(input.map(c=>"
                    "geometry.along(c.points,c.at).point.map((v,i)=>v+[5,-13][i]))));",
                    cases)
    for case, point in zip(cases, actual):
        assert point == pytest.approx(case["expected"])


def test_nearest_route_projection_handles_corners_endpoints_and_zero_length():
    cases = [dict(points=[[0, 0], [100, 0], [100, 100]], point=p)
             for p in ([50, 20], [130, 70], [-10, 4], [150, 150])]
    cases.append(dict(points=[[5, 5], [5, 5]], point=[10, 10]))
    result = run_js("console.log(JSON.stringify(input.map(c=>"
                    "geometry.projectOnRoute(c.points,c.point))));", cases)
    for projection, point, at in zip(result, [[50, 0], [100, 70], [0, 0],
                                            [100, 100], [5, 5]],
                                     [.25, .85, 0, 1, 0]):
        assert projection["point"] == point
        assert projection["at"] == pytest.approx(at)


def test_reverse_split_and_merge_preserve_state_positions():
    source = state_document()
    source["labels"] = [label for label in source["labels"] if label["id"] != "follow"]
    for index, at in enumerate((.2, .5, .8)):
        source["labels"].append(dict(id=f"follow-{index}", edgeId="injection",
                                     at=at, text=str(index), x=7, y=-12))
    source = validate_scene(source)
    scene = resolve_scene(source)
    script = ("const original=input.document;"
              "const reversed=document.reverseEdge(original,'injection',"
              "input.edges.find(e=>e.id==='injection').points);"
              "const split=structuredClone(original);"
              "const edge=split.edges.find(e=>e.id==='injection');"
              "const points=input.edges.find(e=>e.id==='injection').points;"
              "const halves=geometry.splitRoute(points);"
              "split.junctions.push({id:'split-new',x:halves.point[0],y:halves.point[1]});"
              "split.edges.push({...structuredClone(edge),id:'second',source:{junctionId:'split-new'},vertices:halves.suffix});"
              "edge.target={junctionId:'split-new'};edge.vertices=halves.prefix;"
              "split.labels=document.splitEdgeLabels(split.labels,'injection','second');"
              "const routes=new Map(split.edges.map(e=>[e.id,geometry.route("
              "geometry.endpoint(e.source,input.nodes,split.junctions),"
              "geometry.endpoint(e.target,input.nodes,split.junctions),e.vertices)]));"
              "const merged=document.deleteSelection(split,"
              "[{kind:'junction',id:'split-new'}],routes);"
              "console.log(JSON.stringify({reversed,split,merged,original}));")
    result = run_js(script, scene)
    assert result["original"] == source
    before = positions(source)
    for operation in ("reversed", "split", "merged"):
        after = positions(result[operation])
        for identity, point in before.items():
            assert after[identity] == pytest.approx(point)
    assert result["split"]["labels"][-1]["edgeId"] == "second"
    assert result["merged"]["labels"][-1]["edgeId"] == "injection"


def test_state_copy_group_move_and_delete_keep_attachments_consistent():
    source = state_document()
    refs = [dict(kind="node", id="subcooler"), dict(kind="node", id="comp"),
            dict(kind="label", id="follow")]
    script = ("let index=0;const copy=document.copySelection(input.document,input.refs,"
              "kind=>'new-'+kind+'-'+(++index));"
              "const moved=document.translateSelection("
              "copy.document,copy.selection,[30,40]);"
              "const state=moved.labels.find(l=>l.id===copy.selection[2].id);"
              "const deleted=document.deleteSelection("
              "moved,[{kind:'edge',id:state.edgeId}]);"
              "const single=document.copySelection(input.document,"
              "[{kind:'label',id:'follow'}],kind=>'single');"
              "console.log(JSON.stringify({copy,moved,deleted,single}));")
    result = run_js(script, dict(document=source, refs=refs))
    new_id = result["copy"]["selection"][2]["id"]
    before = positions(source)["follow"]
    assert positions(result["copy"]["document"])[new_id] == [v + 20 for v in before]
    assert positions(result["moved"])[new_id] == [before[0] + 50, before[1] + 60]
    assert positions(result["moved"])["follow"] == before
    assert new_id not in positions(result["deleted"])
    assert positions(result["deleted"])["follow"] == before
    assert positions(result["single"]["document"])["single"] == [v + 20 for v in before]


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_reversing_routed_pipes_preserves_state_positions_in_all_templates(name):
    source = load_template(name)
    for index, edge in enumerate(source["edges"]):
        source["labels"].append(dict(id=f"follow-{index}", edgeId=edge["id"],
                                     at=.37, text="s", x=6, y=-15))
    scene = resolve_scene(source)
    script = ("let result=input.document;for(const edge of input.edges)"
              "result=document.reverseEdge(result,edge.id,edge.points);"
              "console.log(JSON.stringify(result));")
    result = run_js(script, scene)
    for identity, point in positions(source).items():
        assert positions(result)[identity] == pytest.approx(point)
