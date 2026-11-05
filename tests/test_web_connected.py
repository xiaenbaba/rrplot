"""设备级连通选择：显式接管、分支、独立回路及只读界面状态。"""

import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, validate_scene
from rrplot.scene_renderer import export_scene

ROOT = Path(__file__).resolve().parents[1]
KINDS = dict(node="nodes", junction="junctions", edge="edges", label="labels")


def run_js(code, document, **options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript connectivity check")
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const edits=await import('data:text/javascript;base64,'+
  fs.readFileSync(input.module).toString('base64'));
const elements=new Map(),results=[],statuses=[],messages=[],buttons=[];
let modal=false;
function element(id){if(!elements.has(id))elements.set(id,{
  addEventListener(){},append(){},replaceChildren(){}});return elements.get(id);}
const context=vm.createContext({...edits,input,structuredClone,
  results,statuses,messages,buttons,
  document:{getElementById:element,body:element('body'),addEventListener(){},
    querySelector:()=>modal?{}:null},window:{addEventListener(){}},
  ResizeObserver:class{observe(){}},setModal:v=>{modal=v;}});
const source=fs.readFileSync(input.app,'utf8').replace(/^import .*;\r?$/gm,'')
  .replace('void init();','');
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.document);render=()=>{};
  status=m=>statuses.push(m);message=m=>messages.push(m);
  multiSelection=structuredClone(input.options.refs||[]);selection=multiSelection.at(-1);
  undo=[{before:true}];redo=[{after:true}];dirty=!!input.options.dirty;
  ownedDraft='existing-draft';pendingDownload={version:revision};
  globalThis.snapshot=()=>structuredClone({doc,selection,multiSelection,
    undo,redo,dirty,revision,request,view,ports,ownedDraft,pendingDownload});
  inspectorButton=(root,caption,click)=>{
    const b={caption,click};buttons.push(b);return b;};
  html=()=>({});`,context);
await vm.runInContext('(async()=>{'+input.code+'})()',context);
console.log(JSON.stringify({results,statuses,messages,buttons:buttons.map(b=>({
  caption:b.caption,disabled:b.disabled})),state:vm.runInContext('snapshot()',context)}));
"""
    output = subprocess.run(
        [executable, "--input-type=module", "-e", script],
        input=json.dumps(dict(code=code, document=document, options=options,
                             module=str(ROOT / "web/document.js"),
                             app=str(ROOT / "web/app.js"))),
        encoding="utf-8", capture_output=True,
    )
    assert output.returncode == 0, output.stderr
    return json.loads(output.stdout)


def refs_for(document):
    return [dict(kind=kind, id=item["id"])
            for kind, name in KINDS.items() for item in document[name]
            if kind != "label" or item.get("nodeId") or item.get("edgeId")]


def identities(refs):
    return {(ref["kind"], ref["id"]) for ref in refs}


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("seed", ["node", "edge", "node-label", "edge-label"])
def test_template_selection_contains_complete_system_and_attached_labels(name, seed):
    doc = load_template(name)
    doc["labels"].append(dict(id="connected-node-label", nodeId=doc["nodes"][0]["id"],
                              text="设备注释", x=10, y=20))
    doc["labels"].append(dict(id="connected-state", edgeId=doc["edges"][0]["id"],
                              text="状态点", at=.4, x=3, y=-10))
    doc = validate_scene(doc)
    ref = {"node": dict(kind="node", id=doc["nodes"][0]["id"]),
           "edge": dict(kind="edge", id=doc["edges"][0]["id"]),
           "node-label": dict(kind="label", id="connected-node-label"),
           "edge-label": dict(kind="label", id="connected-state")}[seed]
    output = run_js("""
      const before=JSON.stringify(doc);
      const expanded=connectedSelection(doc,input.options.refs);
      results.push(expanded,connectedSelection(doc,expanded),
        before===JSON.stringify(doc));
    """, doc, refs=[ref])
    expanded, repeated, unchanged = output["results"]
    assert identities(expanded) == identities(refs_for(doc))
    assert repeated == expanded and unchanged and expanded[0] == ref
    assert len(expanded) == len(identities(expanded))


def disconnected_document():
    doc = load_template("evi_ftvi")
    doc["labels"].append(dict(id="free-text", text="独立文字", x=15, y=15))
    # A second circuit occupies the same coordinates, with crossing/overlapping
    # paths, but all endpoint references use different IDs.
    for name in KINDS.values():
        for original in list(doc[name]):
            item = deepcopy(original)
            item["id"] = "other-" + item["id"]
            for endpoint in [item.get("source", {}), item.get("target", {}), item]:
                for key in ["nodeId", "junctionId", "edgeId"]:
                    if key in endpoint:
                        endpoint[key] = "other-" + endpoint[key]
            doc[name].append(item)
    return validate_scene(doc)


def test_crossing_pipes_do_not_join_disconnected_systems_and_multiseeds_union():
    doc = disconnected_document()
    first = dict(kind="node", id=doc["nodes"][0]["id"])
    other = dict(kind="node", id="other-" + first["id"])
    free = dict(kind="label", id="free-text")
    output = run_js("""
      results.push(connectedSelection(doc,[input.options.first]),
        connectedSelection(doc,[input.options.first,input.options.other,
          input.options.free,input.options.first,{kind:'node',id:'missing'}]));
    """, doc, first=first, other=other, free=free)
    one, both = output["results"]
    expected = refs_for(doc)
    assert identities(one) == identities([ref for ref in expected
                                         if not ref["id"].startswith("other-")])
    assert identities(both) == identities(expected + [free])
    assert len(both) == len(identities(both)) and both[:3] == [first, other, free]


def test_junction_branch_direction_independence_and_isolated_device():
    doc = load_template("evi_ftvi")
    junction = doc["junctions"][0]
    original_id = junction["id"]
    junction["id"] = "junction-seed"
    for edge in doc["edges"]:
        for ref in [edge["source"], edge["target"]]:
            if ref.get("junctionId") == original_id:
                ref["junctionId"] = "junction-seed"
    isolated = deepcopy(doc["nodes"][0])
    isolated["id"] = "isolated-node"
    doc["nodes"].append(isolated)
    doc = validate_scene(doc)
    output = run_js("""
      const refs=[{kind:'junction',id:'junction-seed'}];
      results.push(connectedSelection(doc,refs));
      for(const edge of doc.edges)[edge.source,edge.target]=[edge.target,edge.source];
      results.push(connectedSelection(doc,refs));
      results.push(connectedSelection(doc,[{kind:'node',id:'isolated-node'}]));
    """, doc)
    forward, reverse, isolated_refs = output["results"]
    assert forward == reverse
    expected = identities(refs_for(doc)) - {("node", "isolated-node")}
    assert identities(forward) == expected
    assert isolated_refs == [dict(kind="node", id="isolated-node")]


def test_standalone_label_empty_and_missing_seeds_are_safe():
    doc = validate_scene(dict(schemaVersion=1, title="空图",
                              page=dict(width=760, height=580), nodes=[], edges=[],
                              junctions=[],
                              labels=[dict(id="free", text="文字", x=0, y=0)]))
    output = run_js("""
      results.push(connectedSelection(doc,[]),
        connectedSelection(doc,[{kind:'node',id:'missing'},{kind:'unknown',id:'free'}]),
        connectedSelection(doc,[{kind:'label',id:'free'},{kind:'label',id:'free'}]));
    """, doc)
    assert output["results"] == [[], [], [dict(kind="label", id="free")]]


@pytest.mark.parametrize("dirty", [False, True])
def test_real_inspector_button_expands_without_changing_document_state(dirty):
    doc = load_template("evi_ftvi")
    ref = dict(kind="node", id=doc["nodes"][0]["id"])
    output = run_js("""
      results.push(snapshot());connectedSelectionButton({append(){}});
      buttons[0].click();results.push(snapshot());buttons[0].click();results.push(snapshot());
    """, doc, refs=[ref], dirty=dirty)
    before, expanded, repeated = output["results"]
    assert expanded == repeated
    assert expanded["selection"] == ref
    assert identities(expanded["multiSelection"]) == identities(refs_for(doc))
    for key in before:
        if key != "multiSelection":
            assert expanded[key] == before[key]
    assert not output["buttons"][0]["disabled"]
    assert "相连对象已全部选中" in output["statuses"][-1]


@pytest.mark.parametrize("guard", [
    "mode='connect'", "placement='compressor'", "pendingPort={}",
    "reconnect={}", "drag={}", "spaceDown=true",
    "pageLayoutBusy=true", "setModal(true)",
])
def test_interaction_and_dialog_guards_preserve_selection(guard):
    doc = load_template("heat_pump")
    output = run_js(guard + ";results.push(snapshot());selectConnected();"
                    "results.push(snapshot());", doc,
                    refs=[dict(kind="edge", id=doc["edges"][0]["id"])])
    assert output["results"][0] == output["results"][1]


def test_expanded_selection_copies_and_moves_only_its_system():
    doc = disconnected_document()
    output = run_js("""
      const refs=connectedSelection(doc,[{kind:'node',id:doc.nodes[0].id}]);
      const moved=moveContents(doc,refs,'selection',[25,-15]);
      let id=0;const copied=copySelection(doc,refs,kind=>kind+'-copy-'+(++id));
      results.push(moved,copied.document);
    """, doc)
    moved, copied = output["results"]
    assert validate_scene(moved) == moved and validate_scene(copied) == copied
    for before, after in zip(doc["nodes"], moved["nodes"]):
        assert after == (before if before["id"].startswith("other-")
                         else dict(before, x=before["x"] + 25, y=before["y"] - 15))
    assert len(copied["nodes"]) == len(doc["nodes"]) * 3 // 2
    assert len(copied["edges"]) == len(doc["edges"]) * 3 // 2
    assert export_scene(copied, "svg").startswith(b"<?xml")
