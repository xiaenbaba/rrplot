"""精确平移的几何保持、校验、单次历史与真实表单事件。"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, validate_scene
from rrplot.scene_renderer import export_scene

ROOT = Path(__file__).resolve().parents[1]


def run_js(code, document, **options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript precise move check")
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const edits=await import('data:text/javascript;base64,'+
  fs.readFileSync(input.module).toString('base64'));
const elements=new Map(),listeners=new Map(),results=[],messages=[],statuses=[];
let draftCalls=0,saved=null;
function element(id){if(!elements.has(id))elements.set(id,{
  value:'',open:false,disabled:false,textContent:'',
  addEventListener:(n,f)=>listeners.set(id+':'+n,f),
  showModal(){this.open=true;},close(){this.open=false;listeners.get(id+':close')?.();}
});return elements.get(id);}
const context=vm.createContext({...edits,input,structuredClone,
  results,messages,statuses,
  element,listeners,document:{getElementById:element,body:element('body'),
    querySelector:()=>[...elements.values()].find(e=>e.open)||null,
    addEventListener:(n,f)=>listeners.set('document:'+n,f)},
  window:{addEventListener(){}},ResizeObserver:class{observe(){}},
  save:doc=>{draftCalls++;saved=structuredClone(doc);}});
const source=(await import('node:module')).createRequire(input.app)
  ('../tests/web_editor_harness.cjs').loadEditorSource(input.app);
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.document);render=()=>{};
  refresh=async()=>{};saveDraft=()=>save(doc);
  status=m=>statuses.push(m);message=m=>messages.push(m);
  multiSelection=structuredClone(input.options.refs||[]);selection=multiSelection.at(-1);
  globalThis.snapshot=()=>structuredClone({doc,dirty,revision,request,undo,redo,
    multiSelection,selection,mode,view,ports,moveSession,
    open:$('move-dialog').open,disabled:$('move-apply').disabled,
    error:$('move-error').textContent});
  globalThis.submit=()=>listeners.get('move-form:submit')({preventDefault(){}});
  globalThis.offset=(x,y)=>{ $('move-x').value=String(x);$('move-y').value=String(y);
    listeners.get('move-x:input')();};
  globalThis.click=action=>listeners.get('document:click')({target:{
    closest:s=>s==='[data-action]'?{dataset:{action}}:null}});`,context);
await vm.runInContext('(async()=>{'+input.code+'})()',context);
console.log(JSON.stringify({results,messages,statuses,draftCalls,saved,
  state:vm.runInContext('snapshot()',context)}));
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


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("scope", ["all", "selection"])
def test_move_templates_preserves_geometry_and_attached_labels(name, scope):
    doc = load_template(name)
    doc["nodes"][0]["rotation"] = 90
    doc["edges"][0]["vertices"] = [[145.5, 125.25], [250, 125.25]]
    doc["labels"].append(dict(id="move-state", edgeId=doc["edges"][0]["id"],
                              at=.4, x=4, y=-7, text="状态点"))
    doc = validate_scene(doc)
    edge = doc["edges"][0]
    refs = [dict(kind="node", id=ref["nodeId"]) if "nodeId" in ref
            else dict(kind="junction", id=ref["junctionId"])
            for ref in [edge["source"], edge["target"]]]
    # Explicit attached labels must not move twice; duplicate refs are harmless.
    refs += [dict(kind="edge", id=edge["id"]),
             dict(kind="label", id="move-state"), refs[0]]
    output = run_js("""
      const original=JSON.stringify(doc);
      const result=moveContents(doc,input.options.refs,
        input.options.scope,[12.5,-7.25]);
      results.push(result,original===JSON.stringify(doc));
    """, doc, refs=refs, scope=scope)
    moved, unchanged = output["results"]
    assert unchanged
    assert validate_scene(json.loads(json.dumps(moved))) == moved
    assert moved["page"] == doc["page"] and moved["title"] == doc["title"]
    before, after = resolve_scene(doc), resolve_scene(moved)
    moving_nodes = {r["id"] for r in refs if r["kind"] == "node"}
    moving_junctions = {r["id"] for r in refs if r["kind"] == "junction"}
    def inside(ref):
        return (ref.get("nodeId") in moving_nodes
                or ref.get("junctionId") in moving_junctions)
    internal = {e["id"] for e in doc["edges"]
                if inside(e["source"]) and inside(e["target"])}
    for old, new in zip(doc["nodes"], moved["nodes"]):
        moving = scope == "all" or old["id"] in moving_nodes
        assert new == dict(old, x=old["x"] + (12.5 if moving else 0),
                           y=old["y"] - (7.25 if moving else 0))
    for old, new in zip(doc["edges"], moved["edges"]):
        moving = scope == "all" or old["id"] in internal
        vertices = [[x + 12.5, y - 7.25] for x, y in old["vertices"]]
        assert new == dict(old, vertices=vertices if moving else old["vertices"])
    for label, old, new in zip(doc["labels"], before["labels"], after["labels"]):
        if (scope == "all" or label.get("nodeId") in moving_nodes
                or label.get("edgeId") in internal):
            assert new["position"] == pytest.approx([old["position"][0] + 12.5,
                                                     old["position"][1] - 7.25])
    assert export_scene(moved, "svg").startswith(b"<?xml")


@pytest.mark.parametrize("offset", [
    [None, 0], ["5", 0], [True, 0], [100001, 0], [1], [],
])
def test_invalid_offset_does_not_change_input(offset):
    doc = load_template("heat_pump")
    output = run_js("""
      const before=JSON.stringify(doc);let error;
      try{moveContents(doc,[],'all',input.options.offset);}catch(e){error=e.message;}
      results.push(error,before===JSON.stringify(doc));
    """, doc, offset=offset)
    assert output["results"][0] and output["results"][1]


def test_selected_rotated_label_moves_in_page_direction_without_parent():
    doc = load_template("heat_pump")
    node = doc["nodes"][0]
    node["rotation"] = 90
    doc["labels"].append(dict(id="rotated", nodeId=node["id"], x=11, y=13, text="文字"))
    doc = validate_scene(doc)
    output = run_js("""
      results.push(moveContents(doc,[{kind:'label',id:'rotated'}],'selection',[2.5,-4]));
    """, doc)
    moved = output["results"][0]
    assert moved["nodes"] == doc["nodes"] and moved["edges"] == doc["edges"]
    old, new = resolve_scene(doc)["labels"][-1], resolve_scene(moved)["labels"][-1]
    assert new["position"] == pytest.approx([old["position"][0] + 2.5,
                                             old["position"][1] - 4])


@pytest.mark.parametrize("failure", ["node", "vertex", "scope", "pipe-only"])
def test_failure_is_atomic(failure):
    doc = load_template("heat_pump")
    if failure == "node":
        doc["nodes"][-1]["x"] = 99999
    elif failure == "vertex":
        doc["edges"][-1]["vertices"] = [[99999, 0]]
    output = run_js("""
      const before=JSON.stringify(doc);let error;
      try{moveContents(doc,[{kind:'edge',id:doc.edges[0].id}],
        input.options.failure==='scope'?'invalid':input.options.failure==='pipe-only'?'selection':'all',[2,0]);}
      catch(e){error=e.message;}results.push(error,before===JSON.stringify(doc));
    """, doc, failure=failure)
    assert output["results"][0] and output["results"][1]


def test_form_apply_is_single_edit_and_preserves_view_selection_and_history():
    doc = load_template("heat_pump")
    refs = [dict(kind="node", id=doc["nodes"][0]["id"])]
    output = run_js("""
      const before=snapshot();showMoveDialog('selection');
      results.push(snapshot());offset(2.5,-3.25);submit();results.push(snapshot());
      submit();results.push(snapshot());history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());results.push(before);
    """, doc, refs=refs)
    opened, applied, repeated, undone, redone, before = output["results"]
    assert opened["open"] and opened["disabled"]
    assert applied["dirty"] and not applied["open"] and applied["moveSession"] is None
    assert len(applied["undo"]) == 1 and applied["revision"] == 1
    assert applied == repeated
    assert applied["multiSelection"] == refs
    for key in ["view", "ports", "mode"]:
        assert applied[key] == before[key]
    assert applied["doc"]["nodes"][0]["x"] == doc["nodes"][0]["x"] + 2.5
    assert applied["doc"]["nodes"][0]["y"] == doc["nodes"][0]["y"] - 3.25
    assert undone["doc"] == doc and redone["doc"] == applied["doc"]
    assert output["saved"] == redone["doc"] and output["draftCalls"] == 3


def test_cancel_empty_zero_invalid_and_changed_document_do_not_write_history():
    doc = load_template("heat_pump")
    output = run_js("""
      showMoveDialog('all');offset(5,5);await click('close-move');
      results.push(snapshot());
      showMoveDialog('all');submit();results.push(snapshot());
      offset('',0);submit();results.push(snapshot());
      offset(100001,0);submit();results.push(snapshot());
      $('move-scope').value='selection';listeners.get('move-scope:change')();
      offset(5,0);submit();results.push(snapshot());
      $('move-scope').value='all';listeners.get('move-scope:change')();
      revision++;submit();results.push(snapshot());
    """, doc)
    assert output["draftCalls"] == 0
    for state in output["results"]:
        assert state["doc"] == doc and state["undo"] == state["redo"] == []
        assert not state["dirty"]
    assert not output["results"][0]["open"]
    assert all(state["disabled"] for state in output["results"][1:])
    assert "图纸已变化" in output["state"]["error"]


@pytest.mark.parametrize("guard", [
    "mode='connect'", "placement='compressor'", "pendingPort={}",
    "reconnect={}", "drag={}", "spaceDown=true", "pageLayoutBusy=true",
])
def test_interaction_guards_block_open_and_submission(guard):
    output = run_js("""
      showMoveDialog('all');offset(5,5);
    """ + guard + ";submit();results.push(snapshot());$('move-dialog').close();"
      "showMoveDialog('all');results.push(snapshot());", load_template("heat_pump"))
    assert output["draftCalls"] == 0 and output["state"]["undo"] == []
    assert output["results"][0]["disabled"] and not output["results"][1]["open"]


def test_other_dialog_blocks_open_and_empty_graph_disables_apply():
    doc = validate_scene(dict(schemaVersion=1, title="空图",
                              page=dict(width=760, height=580),
                              nodes=[], edges=[], junctions=[], labels=[]))
    output = run_js("""
      $('export-dialog').showModal();showMoveDialog('all');results.push(snapshot());
      $('export-dialog').close();showMoveDialog('all');offset(5,5);submit();results.push(snapshot());
    """, doc)
    assert not output["results"][0]["open"] and output["results"][1]["disabled"]
    assert output["draftCalls"] == 0
