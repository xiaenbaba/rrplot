"""跨图纸粘贴保留组内连接，并隔离源图、目标图和剪贴板快照。"""
import base64
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, validate_scene
from rrplot.scene_renderer import export_scene


def clipboard_edit(source, selection, target, **options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript clipboard check")
    raw = Path(__file__).resolve().parents[1].joinpath("web/document.js").read_bytes()
    uri = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    script = ("import fs from 'node:fs';const edits=await import("
              + json.dumps(uri) + ");const input=JSON.parse(fs.readFileSync(0,'utf8'));"
              "let index=0,fragment;try{"
              "fragment=edits.captureSelection(input.source,input.selection,"
              "new Map(Object.entries(input.positions||{})));"
              "const snapshot=JSON.stringify(fragment);"
              "const result=edits.pasteFragment(input.target,"
              "input.empty?null:fragment,kind=>input.collision||'paste-'+kind+'-'+"
              "(++index),input.offset);"
              "const again=input.repeat?edits.pasteFragment(result.document,fragment,"
              "kind=>'paste-'+kind+'-'+(++index),[40,40]):null;"
              "if(input.mutate){input.source.nodes[0].x+=300;"
              "result.document.nodes.at(-1).x+=200;}"
              "console.log(JSON.stringify({result,again,fragment,"
              "snapshot:JSON.parse(snapshot),source:input.source,target:input.target}));"
              "}catch(error){console.log(JSON.stringify({error:error.message,"
              "source:input.source,target:input.target}));}")
    completed = subprocess.run([executable, "--input-type=module", "-e", script],
                               input=json.dumps(dict(source=source,
                                                     selection=selection,
                                                     target=target, **options)),
                               encoding="utf-8", capture_output=True, check=True)
    output = json.loads(completed.stdout)
    if not options.get("mutate"):
        assert output["source"] == source
    assert output["target"] == target
    return output


def all_refs(document):
    return [dict(kind=kind, id=item["id"])
            for kind, collection in (("node", "nodes"), ("junction", "junctions"),
                                     ("label", "labels"))
            for item in document[collection]]


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_cross_document_paste_retains_complete_template_graph_and_layout(name):
    source, target = load_template(name), load_template("heat_pump")
    refs = all_refs(source)
    output = clipboard_edit(source, refs + refs[:1], target)
    result, fragment = output["result"], output["fragment"]
    assert fragment == output["snapshot"]
    validate_scene(fragment)
    pasted = validate_scene(result["document"])
    assert pasted["title"] == target["title"]
    assert pasted["page"] == target["page"]
    assert "selection" not in pasted
    assert len(result["selection"]) == len(refs)
    mapping = {old["id"]: new["id"]
               for old, new in zip(refs, result["selection"])}
    for collection in ("nodes", "junctions", "edges", "labels"):
        assert pasted[collection][:len(target[collection])] == target[collection]
        assert len(pasted[collection]) == len(target[collection]) + len(
            source[collection])
    old_scene, new_scene = resolve_scene(source), resolve_scene(pasted)
    copied_edges = new_scene["edges"][len(target["edges"]):]
    for old, new in zip(old_scene["edges"], copied_edges):
        assert new["points"] == [[x + 20, y + 20] for x, y in old["points"]]
        for side in ("source", "target"):
            assert new[side] == {key: value if key == "portId" else mapping[value]
                                 for key, value in old[side].items()}
        for key in ("head", "headAt", "width", "color", "linestyle"):
            assert new[key] == old[key]
    labels = {label["id"]: label for label in new_scene["labels"]}
    for label in old_scene["labels"]:
        assert labels[mapping[label["id"]]]["position"] == [
            v + 20 for v in label["position"]]
    assert export_scene(pasted, "svg").startswith(b"<?xml")


def test_partial_clipboard_copies_internal_pipes_and_detaches_external_labels():
    source = load_template("evi_ftvi")
    next(n for n in source["nodes"] if n["id"] == "comp")["rotation"] = 90
    source["labels"].append(dict(id="state", edgeId="injection", at=.25,
                                 x=8, y=-14, text="T1"))
    source = validate_scene(source)
    positions = {label["id"]: label["position"]
                 for label in resolve_scene(source)["labels"]}
    refs = [dict(kind=kind, id=identity) for kind, identity in [
        ("node", "subcooler"), ("node", "eev1"), ("junction", "split"),
        ("label", "label-comp"), ("label", "state"), ("node", "missing"),
        ("edge", "discharge")]]
    target = load_template("heat_pump")  # Also has 'comp'; never bind to it.
    output = clipboard_edit(source, refs, target, positions=positions)
    fragment, result = output["fragment"], output["result"]
    assert len(fragment["nodes"]) == 2 and len(fragment["junctions"]) == 1
    inside = {"subcooler", "eev1", "split"}
    assert {e["id"] for e in fragment["edges"]} == {
        e["id"] for e in source["edges"] if all(
            ref.get("nodeId", ref.get("junctionId")) in inside
            for ref in (e["source"], e["target"]))}
    assert any(label.get("nodeId") == "subcooler" for label in fragment["labels"])
    fragment_labels = {label["id"]: label for label in fragment["labels"]}
    remap = {old["id"]: new["id"] for old, new in zip(
        fragment["selection"], result["selection"])}
    pasted_labels = {label["id"]: label
                     for label in resolve_scene(result["document"])["labels"]}
    for identity in ("label-comp", "state"):
        label = fragment_labels[identity]
        assert not any(key in label for key in ("nodeId", "edgeId", "at"))
        assert [label["x"], label["y"]] == positions[identity]
        assert pasted_labels[remap[identity]]["position"] == [
            v + 20 for v in positions[identity]]


def test_group_clipboard_keeps_pipe_state_attachment_and_repeated_paste_is_unique():
    source = load_template("heat_pump")
    source["labels"].append(dict(id="state", edgeId=source["edges"][0]["id"],
                                 at=.3, x=8, y=-14, text="P1"))
    source = validate_scene(source)
    target = load_template("heat_pump")
    output = clipboard_edit(source, all_refs(source), target, repeat=True)
    first, second = output["result"]["document"], output["again"]["document"]
    validate_scene(second)
    assert output["fragment"] == output["snapshot"]
    copies = second["nodes"][len(first["nodes"]):]
    assert [[n["x"], n["y"]] for n in copies] == [
        [n["x"] + 40, n["y"] + 40] for n in source["nodes"]]
    states = [label for label in second["labels"] if label["text"] == "P1"]
    assert len(states) == 2
    assert states[0]["edgeId"] != states[1]["edgeId"]
    assert states[0]["at"] == states[1]["at"] == .3
    assert all([label["x"], label["y"]] == [8, -14] for label in states)


def test_clipboard_is_a_snapshot_independent_of_later_source_and_paste_edits():
    source = load_template("heat_pump")
    output = clipboard_edit(source, all_refs(source), source, mutate=True)
    assert output["fragment"] == output["snapshot"]
    assert output["fragment"]["nodes"] == source["nodes"]


@pytest.mark.parametrize("failure", ["collision", "limit", "coordinates",
                                     "missing-position", "empty", "edge-only"])
def test_clipboard_failures_leave_both_documents_unchanged(failure):
    source, target = load_template("heat_pump"), load_template("heat_pump")
    refs = [dict(kind="node", id="comp")]
    options = {}
    if failure == "collision":
        options["collision"] = "comp"
    elif failure == "limit":
        target["labels"] = [dict(copy.deepcopy(target["labels"][0]), id=f"l-{i}")
                            for i in range(2000)]
    elif failure == "coordinates":
        options["offset"] = [100001, 0]
    elif failure == "missing-position":
        refs = [dict(kind="label", id=source["labels"][0]["id"])]
    elif failure == "empty":
        options["empty"] = True
    elif failure == "edge-only":
        refs = [dict(kind="edge", id=source["edges"][0]["id"])]
    output = clipboard_edit(source, refs, target, **options)
    assert output["error"]


def test_registered_keyboard_handler_routes_clipboard_and_preserves_text_editing():
    """Exercise the actual listener; browser automation intercepts Ctrl+C/V itself."""
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript keyboard check")
    root = Path(__file__).resolve().parents[1]
    cases = [
        dict(key="c", ctrlKey=True, expected="copy"),
        dict(key="v", ctrlKey=True, expected="paste"),
        dict(key="c", metaKey=True, expected="copy"),
        dict(key="v", metaKey=True, expected="paste"),
        dict(key="d", ctrlKey=True, expected="duplicate"),
        dict(key="c", expected=None),
        dict(key="v", ctrlKey=True, editable=True, expected=None),
        dict(key="c", ctrlKey=True, editable=True, expected=None),
        dict(key="v", ctrlKey=True, contentEditable=True, expected=None),
        dict(key="v", ctrlKey=True, isComposing=True, expected=None),
        dict(key="c", ctrlKey=True, dialog=True, expected=None),
        dict(key="v", ctrlKey=True, dialog=True, expected=None),
        dict(key="c", ctrlKey=True, shiftKey=True, expected=None),
        dict(key="v", ctrlKey=True, altKey=True, expected=None),
        dict(key="v", ctrlKey=True, dragging=True, expected=None),
    ]
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const listeners=new Map(), calls=[];
let scenario;
const element={addEventListener(){}};
const context=vm.createContext({structuredClone,
  document:{getElementById:()=>element,addEventListener(){},
    querySelector:()=>scenario?.dialog?{}:null,body:element},
  window:{addEventListener:(name,handler)=>listeners.set(name,handler)},
  ResizeObserver:class {observe(){}},calls});
const source=fs.readFileSync(input.path,'utf8')
  .replace(/^import .*;\r?$/gm,'').replace('void init();','');
vm.runInContext(source,context);
vm.runInContext("copyToClipboard=()=>calls.push('copy');"
  +"pasteClipboard=()=>calls.push('paste');"
  +"copySelected=()=>calls.push('duplicate');",context);
const output=[];
for(scenario of input.cases){
  calls.length=0;
  context.dragging=!!scenario.dragging;
  vm.runInContext('drag=dragging?{}:null;',context);
  let prevented=false;
  await listeners.get('keydown')({...scenario,
    target:{matches:()=>!!scenario.editable,
      isContentEditable:!!scenario.contentEditable},
    preventDefault(){prevented=true;}});
  output.push({calls:[...calls],prevented});
}
console.log(JSON.stringify(output));
"""
    result = subprocess.run([executable, "--input-type=module", "-e", script],
                            input=json.dumps(dict(path=str(root / "web/app.js"),
                                                  cases=cases)),
                            encoding="utf-8", capture_output=True, check=True)
    for case, actual in zip(cases, json.loads(result.stdout)):
        expected = case["expected"]
        assert actual == dict(calls=[expected] if expected else [],
                              prevented=bool(expected))
