"""浏览器批量复制、删除后，图纸仍可被正式解析。"""
import base64
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, validate_scene


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
