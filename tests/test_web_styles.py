"""批量样式只改变指定字段，保持图形几何、连接与附着关系。"""
import base64
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, validate_scene
from rrplot.scene_renderer import export_scene


def style_edit(document, refs, patch, scope="selection"):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript style check")
    source = Path(__file__).resolve().parents[1].joinpath("web/styles.js").read_bytes()
    uri = "data:text/javascript;base64," + base64.b64encode(source).decode()
    script = ("import fs from 'node:fs';const styles=await import("
              + json.dumps(uri) + ");const input=JSON.parse(fs.readFileSync(0,'utf8'));"
              "try{const targets=styles.styleTargets(input.document,input.refs,"
              "input.scope);const result=styles.applyStyles(input.document,"
              "input.refs,input.scope,input.patch);"
              "const again=styles.applyStyles(result,input.refs,input.scope,"
              "input.patch);console.log(JSON.stringify({targets,result,again,"
              "original:input}));}catch(error){console.log(JSON.stringify({"
              "error:error.message,original:input}));}")
    args = dict(document=document, refs=refs, patch=patch, scope=scope)
    completed = subprocess.run([executable, "--input-type=module", "-e", script],
                               input=json.dumps(args), encoding="utf-8",
                               capture_output=True, check=True)
    output = json.loads(completed.stdout)
    assert output["original"] == args
    if "result" in output:
        assert output["again"] == output["result"]
    return output


PATCH = dict(edges=dict(color="#b94724", width=2.4, linestyle="dashed", head=False),
             labels=dict(color="#214578", size=18, ha="left", boxed=True))


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_all_templates_bulk_style_round_trip_retains_geometry_and_exports(name):
    original = load_template(name)
    original["nodes"][0]["rotation"] = 90
    original["edges"][0]["vertices"] = [[35, 25], [35, 90]]
    original["edges"][0]["headAt"] = [.2, .7]
    original["labels"].append(dict(id="state", edgeId=original["edges"][0]["id"],
                                   at=.35, x=9, y=-13, text="P1"))
    original = validate_scene(original)
    output = style_edit(original, [], PATCH, "all")
    result = validate_scene(json.loads(json.dumps(output["result"])))
    expected = copy.deepcopy(original)
    for group, patch in PATCH.items():
        for item in expected[group]:
            item.update(patch)
    assert result == expected
    old, new = resolve_scene(original), resolve_scene(result)
    assert [e["points"] for e in old["edges"]] == [e["points"] for e in new["edges"]]
    assert [label["position"] for label in old["labels"]] == [
        label["position"] for label in new["labels"]]
    svg = export_scene(result, "svg")
    assert b"#b94724" in svg and b"#214578" in svg


def test_partial_group_includes_internal_pipes_and_labels_only_once():
    document = load_template("evi_ftvi")
    document["labels"].extend([
        dict(id="inside", edgeId="branch-in", at=.4, x=0, y=-10, text="P1"),
        dict(id="outside", edgeId="injection", at=.4, x=0, y=-10, text="P2"),
        dict(id="free", x=10, y=20, text="自由文字"),
    ])
    document = validate_scene(document)
    refs = [dict(kind="node", id="eev1"), dict(kind="junction", id="split"),
            dict(kind="label", id="label-eev1"), dict(kind="label", id="free"),
            dict(kind="node", id="missing"), dict(kind="node", id="eev1")]
    output = style_edit(document, refs, PATCH)
    assert output["targets"]["edges"] == ["branch-in"]
    labels = {label["id"] for label in document["labels"]
              if label.get("nodeId") == "eev1"} | {"inside", "free"}
    assert set(output["targets"]["labels"]) == labels
    for group in ("edges", "labels"):
        targets = set(output["targets"][group])
        for old, new in zip(document[group], output["result"][group]):
            expected = dict(old, **PATCH[group]) if old["id"] in targets else old
            assert new == expected


def test_single_pipe_includes_its_state_labels_but_not_device_labels():
    document = load_template("evi_ftvi")
    document["labels"].append(dict(id="state", edgeId="injection", at=.5,
                                   x=0, y=-10, text="P1"))
    output = style_edit(document, [dict(kind="edge", id="injection")], PATCH)
    assert output["targets"] == dict(edges=["injection"], labels=["state"])


def test_single_attached_label_does_not_restyle_parent_or_pipe():
    document = load_template("heat_pump")
    label = document["labels"][0]
    output = style_edit(document, [dict(kind="label", id=label["id"])],
                        dict(labels=dict(size=23)))
    assert output["targets"] == dict(edges=[], labels=[label["id"]])
    assert output["result"]["edges"] == document["edges"]
    assert output["result"]["labels"][0] == dict(label, size=23)


@pytest.mark.parametrize("refs,patch", [([], PATCH),
    ([dict(kind="node", id="missing")], PATCH), ([], {}),
    ([dict(kind="edge", id="discharge")], {}),
])
def test_empty_scope_or_patch_is_a_noop(refs, patch):
    document = load_template("evi_ftvi")
    assert style_edit(document, refs, patch)["result"] == document


@pytest.mark.parametrize("patch", [
    dict(edges=dict(width=.1)), dict(edges=dict(width=8.1)),
    dict(labels=dict(size=5.9)), dict(labels=dict(size=72.1)),
    dict(labels=dict(size=True)), dict(edges=dict(head="false")),
    dict(labels=dict(boxed=1)), dict(edges=dict(color="red")),
    dict(labels=dict(color="#xyzxyz")), dict(edges=dict(linestyle="dots")),
    dict(labels=dict(ha="middle")), dict(edges=dict(vertices=[])),
    dict(labels=dict(nodeId="comp")), dict(nodes=dict(color="#111111")),
    dict(edges=[]), None,
])
def test_invalid_patch_leaves_entire_document_unchanged(patch):
    document = load_template("heat_pump")
    assert style_edit(document, [], patch, "all")["error"]


def test_scope_must_be_explicit_and_valid():
    assert style_edit(load_template("heat_pump"), [], PATCH, "unknown")["error"]


def test_minimum_maximum_and_false_values_are_valid():
    document = load_template("heat_pump")
    for width, size in ((.2, 6), (8, 72)):
        patch = dict(edges=dict(width=width, head=False),
                     labels=dict(size=size, boxed=False))
        result = style_edit(document, [], patch, "all")["result"]
        validate_scene(result)
        assert all(e["head"] is False and e["width"] == width for e in result["edges"])
        assert all(label["boxed"] is False and label["size"] == size
                   for label in result["labels"])
