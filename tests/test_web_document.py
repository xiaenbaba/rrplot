"""浏览器批量复制、删除后，图纸仍可被正式解析。"""
import base64
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import (
    TEMPLATES,
    endpoint,
    load_template,
    resolve_scene,
    validate_scene,
)
from rrplot.scene_renderer import export_scene


def edit_document(document, selection, operation="copy", **options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript document check")
    raw = Path(__file__).resolve().parents[1].joinpath("web/document.js").read_bytes()
    module = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    script = ("import fs from 'node:fs';const edits=await import("
              + json.dumps(module) + ");"
              "const input=JSON.parse(fs.readFileSync(0,'utf8'));let index=0;"
              "try {const result=input.operation==='copy' ? "
              "edits.copySelection(input.document,input.selection,kind=>"
              "input.collision || 'copy-'+kind+'-'+(++index),input.offset) : "
              "input.operation==='move' ? "
              "edits.translateSelection(input.document,input.selection,input.offset) : "
              "input.operation==='nudge' ? "
              "edits.nudgeSelection(input.document,input.selection,"
              "input.direction,input.accelerated) : "
              "input.operation==='reconnect' ? "
              "edits.reconnectEdge(input.document,input.edgeId,input.side,input.ref) : "
              "edits.deleteSelection(input.document,input.selection);"
              "console.log(JSON.stringify({result,original:input.document}));"
              "}catch(error){console.log(JSON.stringify({error:error.message,"
              "original:input.document}));}")
    completed = subprocess.run([executable, "--input-type=module", "-e", script],
                               input=json.dumps(dict(document=document,
                                                     selection=selection,
                                                     operation=operation,
                                                     **options)),
                               encoding="utf-8", capture_output=True, check=True)
    result = json.loads(completed.stdout)
    assert result["original"] == document
    return result


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_copy_complete_template_preserves_graph_labels_and_routed_layout(name):
    document = load_template(name)
    refs = [dict(kind=kind, id=item["id"])
            for kind, collection in (("node", "nodes"), ("junction", "junctions"),
                                     ("label", "labels"))
            for item in document[collection]]
    result = edit_document(document, [*refs, refs[0]])["result"]
    copied = result["document"]
    remap = {ref["id"]: new["id"]
             for ref, new in zip(refs, result["selection"])}
    assert len(result["selection"]) == len(refs)
    scene = resolve_scene(copied)
    for collection in ("nodes", "junctions", "labels", "edges"):
        assert len(copied[collection]) == len(document[collection]) * 2
        assert copied[collection][:len(document[collection])] == document[collection]
    for original, new in zip(document["edges"],
                             copied["edges"][len(document["edges"]):]):
        for side in ("source", "target"):
            assert new[side] == {key: remap[value] if key != "portId" else value
                                 for key, value in original[side].items()}
        assert new["vertices"] == [[x + 20, y + 20]
                                    for x, y in original["vertices"]]
        for key in ("width", "color", "linestyle", "head", "headAt"):
            assert new[key] == original[key]
    for original, new in zip(scene["edges"][:len(document["edges"])],
                             scene["edges"][len(document["edges"]):]):
        assert new["points"] == [[x + 20, y + 20] for x, y in original["points"]]
    labels = {label["id"]: label for label in scene["labels"]}
    for original in document["labels"]:
        new = labels[remap[original["id"]]]
        assert new["position"] == [v + 20 for v in labels[original["id"]]["position"]]
        if "nodeId" in original:
            assert new["nodeId"] == remap[original["nodeId"]]
            assert [new["x"], new["y"]] == [original["x"], original["y"]]


def test_partial_copy_omits_external_pipes_and_offsets_rotated_attached_label():
    document = load_template("evi_ftvi")
    next(n for n in document["nodes"] if n["id"] == "comp")["rotation"] = 90
    refs = [dict(kind=kind, id=identity) for kind, identity in [
        ("node", "subcooler"), ("node", "eev1"), ("junction", "split"),
        ("label", "label-subcooler"), ("label", "label-comp"),
        ("label", "label-branch"), ("node", "missing"),
        ("edge", document["edges"][0]["id"])]]
    result = edit_document(document, refs)["result"]
    copied = result["document"]
    assert len(copied["nodes"]) == len(document["nodes"]) + 2
    assert len(copied["labels"]) == len(document["labels"]) + 4
    assert len(result["selection"]) == 6
    originals = {"subcooler", "eev1", "split"}
    internal = [edge for edge in document["edges"]
                if all(ref.get("nodeId", ref.get("junctionId")) in originals
                       for ref in (edge["source"], edge["target"]))]
    new_edges = copied["edges"][len(document["edges"]):]
    assert len(new_edges) == len(internal) > 0
    original_ids = {item["id"] for name in ("nodes", "junctions")
                    for item in document[name]}
    assert all(ref.get("nodeId", ref.get("junctionId")) not in original_ids
               for edge in new_edges for ref in (edge["source"], edge["target"]))
    scene = resolve_scene(copied)
    old_label = next(label for label in scene["labels"]
                     if label["id"] == "label-comp")
    new_id = result["selection"][4]["id"]
    new_label = next(label for label in scene["labels"] if label["id"] == new_id)
    assert new_label["nodeId"] == "comp"
    assert new_label["position"] == [v + 20 for v in old_label["position"]]


def chain_document():
    document = load_template("heat_pump")
    source, target = document["edges"][0]["source"], document["edges"][0]["target"]
    document["junctions"] = [dict(id="j1", x=100, y=100),
                             dict(id="j2", x=200, y=100)]
    document["edges"] = [dict(id="a", source=source, target=dict(junctionId="j1"),
                              vertices=[[90, 100], [100, 100]]),
                         dict(id="b", source=dict(junctionId="j1"),
                              target=dict(junctionId="j2"),
                              vertices=[[100, 100], [200, 100]]),
                         dict(id="c", source=dict(junctionId="j2"), target=target,
                              vertices=[[200, 100], [220, 100]])]
    return validate_scene(document)


@pytest.mark.parametrize("order", [("j1", "j2"), ("j2", "j1")])
def test_delete_junction_chain_merges_once_in_either_selection_order(order):
    document = chain_document()
    deleted = edit_document(document, [dict(kind="junction", id=i) for i in order],
                            "delete")["result"]
    resolve_scene(deleted)
    assert deleted["junctions"] == []
    assert len(deleted["edges"]) == 1
    edge = deleted["edges"][0]
    assert edge["source"] == document["edges"][0]["source"]
    assert edge["target"] == document["edges"][-1]["target"]
    assert edge["vertices"] == sum((e["vertices"] for e in document["edges"]), [])
    assert deleted["nodes"] == document["nodes"]
    assert deleted["labels"] == document["labels"]


def test_delete_mixed_selection_removes_nodes_attachments_and_incident_pipes():
    document = load_template("evi_ftvi")
    refs = [dict(kind=kind, id=identity) for kind, identity in [
        ("node", "eev1"), ("node", "subcooler"), ("junction", "split"),
        ("label", "label-eev1"), ("label", "label-branch"),
        ("node", "eev1"), ("node", "missing")]]
    deleted = edit_document(document, refs, "delete")["result"]
    resolve_scene(deleted)
    assert {n["id"] for n in deleted["nodes"]} == {"cond", "evap", "comp", "eev2"}
    assert deleted["junctions"] == []
    assert all(label.get("nodeId") not in {"eev1", "subcooler"}
               and label["id"] != "label-branch" for label in deleted["labels"])
    assert all(ref.get("nodeId", ref.get("junctionId")) not in
               {"eev1", "subcooler", "split"}
               for e in deleted["edges"] for ref in (e["source"], e["target"]))


def test_deleted_pipe_is_not_resurrected_when_its_junction_is_also_selected():
    document = chain_document()
    deleted = edit_document(document, [dict(kind="junction", id="j1"),
                                      dict(kind="edge", id="a")], "delete")["result"]
    resolve_scene(deleted)
    assert [e["id"] for e in deleted["edges"]] == ["c"]
    assert [j["id"] for j in deleted["junctions"]] == ["j2"]


def test_delete_branch_junction_does_not_join_unrelated_pipes():
    document = load_template("evi_ftvi")
    deleted = edit_document(document, [dict(kind="junction", id="split")],
                            "delete")["result"]
    resolve_scene(deleted)
    assert len(deleted["edges"]) == len(document["edges"]) - 3
    assert deleted["nodes"] == document["nodes"]


@pytest.mark.parametrize("failure", ["collision", "coordinate", "count", "merge"])
def test_failed_copy_or_delete_preserves_entire_input(failure):
    document = chain_document()
    options, operation = {}, "copy"
    refs = [dict(kind="node", id=document["nodes"][0]["id"])]
    if failure == "collision":
        options["collision"] = document["nodes"][0]["id"]
    elif failure == "coordinate":
        document["nodes"][0]["x"] = 99990
    elif failure == "count":
        seed = document["labels"][0]
        document["labels"] = [dict(copy.deepcopy(seed), id=f"l-{i}")
                               for i in range(2000)]
    else:
        document["edges"][0]["vertices"] = [[10, 20]] * 60
        document["edges"][1]["vertices"] = [[20, 30]] * 60
        refs, operation = [dict(kind="junction", id="j1")], "delete"
    result = edit_document(document, refs, operation, **options)
    assert result.get("error")
    assert "result" not in result


def test_empty_or_stale_selection_does_not_change_document():
    document = load_template("evi_ftvi")
    refs = [dict(kind="node", id="missing")]
    assert edit_document(document, refs)["result"] == dict(document=document,
                                                          selection=[])
    assert edit_document(document, refs, "delete")["result"] == document


def test_multi_move_translates_internal_vertices_and_each_label_once():
    document = chain_document()
    source_id = document["edges"][0]["source"]["nodeId"]
    target_id = document["edges"][-1]["target"]["nodeId"]
    next(n for n in document["nodes"] if n["id"] == source_id)["rotation"] = 90
    next(n for n in document["nodes"] if n["id"] == target_id)["rotation"] = 270
    document["labels"].append(dict(id="free", text="独立", x=17, y=29,
                                    size=12, ha="center", boxed=False,
                                    color="#111111"))
    attached = [label for label in document["labels"]
                if label.get("nodeId") in {source_id, target_id}]
    refs = [dict(kind="node", id=source_id), dict(kind="junction", id="j1"),
            *[dict(kind="label", id=label["id"]) for label in attached],
            dict(kind="label", id="free")]
    moved = edit_document(document, refs, "move", offset=[30, -40])["result"]
    before, after = resolve_scene(document), resolve_scene(moved)
    for old, new in zip(document["nodes"], moved["nodes"]):
        assert [new["x"], new["y"]] == ([old["x"] + 30, old["y"] - 40]
                                       if old["id"] == source_id else
                                       [old["x"], old["y"]])
    assert moved["edges"][0]["vertices"] == [[x + 30, y - 40] for x, y in
                                              document["edges"][0]["vertices"]]
    assert moved["edges"][1:] == document["edges"][1:]
    assert after["edges"][0]["points"] == [[x + 30, y - 40] for x, y in
                                           before["edges"][0]["points"]]
    selected_labels = {ref["id"] for ref in refs if ref["kind"] == "label"}
    for old, new in zip(before["labels"], after["labels"]):
        if old.get("nodeId") == source_id or old["id"] in selected_labels:
            assert new["position"] == [old["position"][0] + 30,
                                       old["position"][1] - 40]
        else:
            assert new == old
    assert edit_document(document, refs, "move", offset=[0, 0])["result"] == document


@pytest.mark.parametrize("identity", ["undefined", "__proto__"])
def test_valid_unusual_ids_do_not_match_missing_node_references(identity):
    document = chain_document()
    old_id = document["edges"][0]["source"]["nodeId"]
    next(n for n in document["nodes"] if n["id"] == old_id)["id"] = identity
    for label in document["labels"]:
        if label.get("nodeId") == old_id:
            label["nodeId"] = identity
    for edge in document["edges"]:
        for ref in (edge["source"], edge["target"]):
            if ref.get("nodeId") == old_id:
                ref["nodeId"] = identity
    document["labels"].append(dict(id="free", text="独立", x=10, y=20))
    document = validate_scene(document)
    refs = [dict(kind="node", id=identity)]
    copied = edit_document(document, refs)["result"]["document"]
    expected = sum(label.get("nodeId") == identity for label in document["labels"])
    assert len(copied["labels"]) == len(document["labels"]) + expected
    resolve_scene(copied)
    deleted = edit_document(document, refs, "delete")["result"]
    assert [edge["id"] for edge in deleted["edges"]] == ["b", "c"]
    assert any(label["id"] == "free" for label in deleted["labels"])
    resolve_scene(deleted)


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("side", ["source", "target"])
def test_reconnect_preserves_pipe_identity_bends_labels_and_resolves(name, side):
    document = load_template(name)
    edge = document["edges"][0]
    edge.update(vertices=[[210, 170], [240, 170]], color="#663399",
                width=2.4, linestyle="dashed", headAt=[.25, .75])
    document["junctions"].append(dict(id="new-junction", x=180, y=260))
    document["labels"].append(dict(id="state", edgeId=edge["id"], at=.4,
                                    x=6, y=-14, text="T1"))
    document = validate_scene(document)
    scene = resolve_scene(document)
    nodes = {node["id"]: node for node in scene["nodes"]}
    junctions = {j["id"]: j for j in document["junctions"]}
    # Reconnect first to a different device port, then to a branch junction.
    candidate = next(dict(nodeId=node["id"], portId=port)
                     for node in scene["nodes"]
                     for port in node["geometry"]["ports"]
                     if dict(nodeId=node["id"], portId=port)
                     not in [edge["source"], edge["target"]])
    previous = document
    for ref in (candidate, dict(junctionId="new-junction")):
        result = edit_document(previous, [], "reconnect", edgeId=edge["id"],
                               side=side, ref=ref)["result"]
        resolved = resolve_scene(json.loads(json.dumps(result)))
        expected = endpoint(ref, nodes, junctions)["point"]
        assert resolved["edges"][0]["points"][0 if side == "source" else -1] == expected
        points = resolved["edges"][0]["points"]
        assert all(a[0] == b[0] or a[1] == b[1] for a, b in zip(points, points[1:]))
        assert result["labels"] == document["labels"]
        assert result["edges"][0] == dict(edge, **{side: ref})
        assert result["edges"][1:] == document["edges"][1:]
        assert result["nodes"] == document["nodes"]
        assert result["junctions"] == document["junctions"]
        previous = result
    assert export_scene(previous, "svg").startswith(b"<?xml")


@pytest.mark.parametrize("change", [
    dict(edgeId="missing"), dict(side="invalid"), dict(ref=None),
    dict(ref={}), dict(ref=dict(nodeId="missing", portId="top")),
    dict(ref=dict(nodeId="comp", portId="")),
    dict(ref=dict(junctionId="missing")),
    dict(ref=dict(nodeId="comp", portId="top", junctionId="split")),
])
def test_reconnect_invalid_reference_leaves_original_document_intact(change):
    document = load_template("evi_ftvi")
    options = dict(edgeId=document["edges"][0]["id"], side="target",
                   ref=dict(nodeId="comp", portId="left"))
    options.update(change)
    assert "error" in edit_document(document, [], "reconnect", **options)


def test_reconnect_same_endpoint_is_noop_and_opposite_endpoint_is_rejected():
    document = load_template("evi_ftvi")
    edge = document["edges"][0]
    edge["source"] = dict(reversed(list(edge["source"].items())))
    unchanged = edit_document(document, [], "reconnect", edgeId=edge["id"],
                              side="source", ref=edge["source"])["result"]
    assert json.dumps(unchanged) == json.dumps(document)
    assert "error" in edit_document(document, [], "reconnect", edgeId=edge["id"],
                                    side="source", ref=edge["target"])


@pytest.mark.parametrize("direction,offset", [
    ("ArrowLeft", [-1, 0]), ("ArrowRight", [1, 0]),
    ("ArrowUp", [0, -1]), ("ArrowDown", [0, 1]),
])
@pytest.mark.parametrize("accelerated", [False, True])
def test_nudge_moves_device_and_its_selected_label_once(direction, offset, accelerated):
    document = load_template("evi_ftvi")
    selection = [dict(kind="node", id="comp"), dict(kind="label", id="label-comp")]
    moved = edit_document(document, selection, "nudge", direction=direction,
                          accelerated=accelerated)["result"]
    before, after = resolve_scene(document), resolve_scene(moved)
    delta = [v * (10 if accelerated else 1) for v in offset]
    for old, new in zip(before["labels"], after["labels"]):
        expected = [v + d for v, d in zip(old["position"], delta)]
        assert new["position"] == (expected if old["id"] == "label-comp"
                                   else old["position"])
    old = next(n for n in document["nodes"] if n["id"] == "comp")
    new = next(n for n in moved["nodes"] if n["id"] == "comp")
    assert [new["x"], new["y"]] == [old["x"] + delta[0], old["y"] + delta[1]]
    assert moved["edges"] == document["edges"]


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("accelerated", [False, True])
def test_nudged_group_keeps_internal_routes_and_state_labels(name, accelerated):
    document = load_template(name)
    document["nodes"][0]["x"] += .25
    document["edges"][0]["vertices"] = [[120.5, 90.25], [150.5, 90.25]]
    document["labels"].append(dict(id="follow", edgeId=document["edges"][0]["id"],
                                    at=.37, text="T1", x=7, y=-13))
    document = validate_scene(document)
    selection = [dict(kind=kind, id=item["id"])
                 for kind, collection in (("node", "nodes"),
                                          ("junction", "junctions"),
                                          ("label", "labels"))
                 for item in document[collection]]
    moved = edit_document(document, selection, "nudge", direction="ArrowUp",
                          accelerated=accelerated)["result"]
    before = resolve_scene(document)
    after = resolve_scene(json.loads(json.dumps(moved)))
    dy = -10 if accelerated else -1
    for old, new in zip(before["labels"], after["labels"]):
        assert new["position"] == pytest.approx([old["position"][0],
                                                  old["position"][1] + dy])
    for old, new in zip(before["edges"], after["edges"]):
        assert new["points"] == [[x, y + dy] for x, y in old["points"]]
        assert new["source"] == old["source"] and new["target"] == old["target"]
    assert moved["page"] == document["page"]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_nudge_rotated_attached_label_follows_page_direction(rotation):
    document = load_template("evi_ftvi")
    next(n for n in document["nodes"] if n["id"] == "comp")["rotation"] = rotation
    moved = edit_document(document, [dict(kind="label", id="label-comp")],
                          "nudge", direction="ArrowRight")["result"]
    before = next(label for label in resolve_scene(document)["labels"]
                  if label["id"] == "label-comp")
    after = next(label for label in resolve_scene(moved)["labels"]
                 if label["id"] == "label-comp")
    assert after["position"] == [before["position"][0] + 1, before["position"][1]]
    assert moved["nodes"] == document["nodes"]
    assert moved["edges"] == document["edges"]


def test_nudge_state_label_only_changes_offset_and_ignores_selected_pipe():
    document = load_template("evi_ftvi")
    document["labels"].append(dict(id="state", edgeId="injection", at=.4,
                                    text="s", x=3, y=-13))
    document = validate_scene(document)
    refs = [dict(kind="label", id="state"), dict(kind="edge", id="injection")]
    moved = edit_document(document, refs, "nudge", direction="ArrowDown",
                          accelerated=True)["result"]
    assert moved["labels"][-1] == dict(document["labels"][-1], y=-3)
    assert moved["nodes"] == document["nodes"]
    assert moved["edges"] == document["edges"]


@pytest.mark.parametrize("x,direction", [(99999.5, "ArrowRight"),
                                        (-99999.5, "ArrowLeft")])
def test_nudge_out_of_range_is_atomic_for_group(x, direction):
    document = load_template("evi_ftvi")
    next(n for n in document["nodes"] if n["id"] == "comp")["x"] = x
    refs = [dict(kind="node", id="comp"), dict(kind="node", id="subcooler")]
    assert "error" in edit_document(document, refs, "nudge", direction=direction)


def test_nudge_cannot_move_a_whole_pipe_away_from_its_ports():
    document = load_template("evi_ftvi")
    refs = [dict(kind="edge", id="injection"), dict(kind="node", id="missing")]
    result = edit_document(document, refs, "nudge", direction="ArrowLeft")["result"]
    assert result == document
