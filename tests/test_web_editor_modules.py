"""原生 ES 模块组装、状态隔离及跨控制器命令契约。"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.registry import catalog
from rrplot.scene import resolve_scene, validate_scene

ROOT = Path(__file__).resolve().parents[1]


def run_editor(code, document, selection=()):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional native editor module check")
    script = r"""
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
globalThis.document={getElementById:()=>null};
const entry=pathToFileURL(path.join(input.root,'web/editor/index.js'));
const {createEditor}=await import(entry);
const {state,commands}=createEditor(),results=[],messages=[],effects=[];
Object.assign(state,{doc:structuredClone(input.document),catalog:input.catalog,
  multiSelection:input.selection,selection:input.selection.at(-1)||null,
  geometries:new Map(input.nodes.map(n=>[n.id,n.geometry]))});
Object.assign(commands,{render:()=>effects.push('render'),
  refresh:async()=>effects.push('refresh'),saveDraft:()=>effects.push('draft'),
  message:text=>messages.push(text),snapped:value=>value});
const snapshot=()=>structuredClone({doc:state.doc,dirty:state.dirty,
  revision:state.revision,undo:state.undo,redo:state.redo,
  selection:state.selection,placement:state.placement});
"""
    script += code + "\nconsole.log(JSON.stringify({results,messages,effects}));"
    completed = subprocess.run(
        [executable, "--experimental-default-type=module", "--input-type=module",
         "-e", script],
        input=json.dumps(dict(root=str(ROOT), document=document,
                             nodes=resolve_scene(document)["nodes"],
                             catalog=catalog(), selection=list(selection))),
        encoding="utf-8", capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("node_count,label_count", [(2000, 0), (0, 2000),
                                                   (1999, 1999)])
def test_add_device_checks_both_limits_before_committing(node_count, label_count):
    document = validate_scene(dict(
        schemaVersion=1,
        nodes=[dict(id=f"node-{i}", type="compressor", x=100, y=100)
               for i in range(node_count)],
        labels=[dict(id=f"label-{i}", text="标签") for i in range(label_count)],
    ))
    output = run_editor("""
state.placement='compressor';
commands.addNode('compressor',[200,200]);results.push(snapshot());
commands.history('undo',{deferRefresh:true});results.push(snapshot());
commands.history('redo',{deferRefresh:true});results.push(snapshot());
""", document)
    added, undone, redone = output["results"]
    if max(node_count, label_count) == 2000:
        assert all(item["doc"] == document for item in output["results"])
        assert added["undo"] == added["redo"] == []
        assert added["revision"] == 0 and not added["dirty"]
        assert added["placement"] == "compressor"
        assert output["effects"] == []
        assert "2000" in output["messages"][0]
    else:
        assert len(added["doc"]["nodes"]) == len(added["doc"]["labels"]) == 2000
        assert validate_scene(added["doc"]) == added["doc"]
        assert len(added["undo"]) == 1 and added["dirty"]
        assert undone["doc"] == document and redone["doc"] == added["doc"]
        assert not output["messages"]


@pytest.mark.parametrize("action", ["align-left", "align-center-x", "align-right",
                                    "align-top", "align-center-y", "align-bottom",
                                    "distribute-x", "distribute-y"])
@pytest.mark.parametrize("labels_first", [True, False])
def test_batch_layout_places_labels_after_their_parents(action, labels_first):
    document = validate_scene(dict(
        schemaVersion=1,
        nodes=[dict(id="device", type="heat_exchanger", x=250, y=200, rotation=90,
                    params=dict(w=100, h=50))],
        junctions=[dict(id="junction", x=100, y=60)],
        edges=[dict(id="pipe", source=dict(nodeId="device", portId="right"),
                    target=dict(junctionId="junction"))],
        labels=[dict(id="device-label", nodeId="device", x=-30, y=20, text="设备"),
                dict(id="pipe-label", edgeId="pipe", at=.6, x=10, y=-15, text="状态")],
    ))
    parents = [dict(kind="node", id="device"), dict(kind="junction", id="junction")]
    labels = [dict(kind="label", id="device-label"),
              dict(kind="label", id="pipe-label")]
    selection = labels + parents if labels_first else parents + labels
    output = run_editor("""
const boxes=()=>commands.layoutRefs().map(entry=>({
  id:entry.item.id,...commands.layoutBox(entry)}));
const before=boxes();
commands.batchLayout(""" + json.dumps(action) + """);
const after=boxes();
results.push({before,after,state:snapshot()});
commands.history('undo',{deferRefresh:true});results.push(snapshot());
commands.history('redo',{deferRefresh:true});results.push(snapshot());
""", document, selection)
    result, undone, redone = output["results"]
    before, after = result["before"], result["after"]
    if action.startswith("distribute"):
        axis = action[-1]
        original = sorted(before, key=lambda box: box[axis])
        final = {box["id"]: box for box in after}
        first, last = original[0][axis], original[-1][axis]
        assert [final[box["id"]][axis] for box in original] == pytest.approx(
            [first + (last - first) * i / (len(original) - 1)
             for i in range(len(original))], abs=1e-4)
    else:
        key = {"align-left": "left", "align-center-x": "x", "align-right": "right",
               "align-top": "top", "align-center-y": "y",
               "align-bottom": "bottom"}[action]
        assert max(box[key] for box in after) - min(box[key] for box in after) < 1e-4
    changed = result["state"]["doc"]
    assert validate_scene(changed) == changed
    assert len(result["state"]["undo"]) == 1
    assert undone["doc"] == document and redone["doc"] == changed
    assert not output["messages"]


@pytest.mark.parametrize("fraction", [.5, .5 - 1e-10, .5 + 1e-10])
def test_split_at_corner_keeps_both_halves_editable(fraction):
    document = validate_scene(dict(
        schemaVersion=1,
        junctions=[dict(id="start", x=0, y=0), dict(id="end", x=100, y=100)],
        edges=[dict(id="pipe", source=dict(junctionId="start"),
                    target=dict(junctionId="end"), vertices=[[100, 0]])],
    ))
    output = run_editor("""
const edge=state.doc.edges[0],fraction=""" + json.dumps(fraction) + """;
const split=commands.junctionSplit(edge,fraction);
commands.edit(()=>commands.applyJunctionSplit(state.doc,edge.id,split,fraction,'middle','second'));
for(const half of state.doc.edges)
  commands.validateCoordinateVertices(half.vertices,half);
results.push(snapshot());
commands.history('undo',{deferRefresh:true});results.push(snapshot());
commands.history('redo',{deferRefresh:true});results.push(snapshot());
""", document)
    split, undone, redone = output["results"]
    assert all(edge["vertices"] == [] for edge in split["doc"]["edges"])
    assert validate_scene(split["doc"]) == split["doc"]
    assert undone["doc"] == document and redone["doc"] == split["doc"]
    assert not output["messages"]


def test_native_editor_modules_compose_bind_and_edit_without_global_aliases():
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional native editor module check")
    script = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=JSON.parse(fs.readFileSync(0,'utf8')),elements=new Map(),events=[];
function element(id){
  if(!elements.has(id))elements.set(id,{
    addEventListener:(...args)=>events.push([id,...args]),checked:false,
    value:'',style:{setProperty(){}},classList:{remove(){},toggle(){}},
    setAttribute(){},hidden:false
  });
  return elements.get(id);
}
globalThis.document={getElementById:element,querySelector:()=>null,
  addEventListener:(...args)=>events.push(['document',...args])};
globalThis.window={addEventListener:(...args)=>events.push(['window',...args])};
globalThis.localStorage={getItem:()=>null};
globalThis.ResizeObserver=class{observe(){}};
const {createEditor}=await import(pathToFileURL(path.join(root,'web/editor/index.js')));
assert.equal(events.length,0,'import must not register event handlers');
const a=createEditor(),b=createEditor();
assert.equal(events.length,0,'composition must not register event handlers');
assert.notEqual(a.state,b.state);
assert.notEqual(a.commands,b.commands);
for(const key of ['undo','redo','multiSelection','connectionVertices','geometries',
  'view','catalog','ports','inspectorGroups'])assert.notEqual(a.state[key],b.state[key],key);
assert.equal(globalThis.doc,undefined,'legacy aliases are test-harness only');
// Check every cross-controller command against the actually imported factories.
for(const file of fs.readdirSync(path.join(root,'web/editor'))){
  if(!file.endsWith('.js'))continue;
  const source=fs.readFileSync(path.join(root,'web/editor',file),'utf8');
  for(const match of source.matchAll(/commands\.([\w$]+)/g)){
    if(match[1]!=='actions')assert.equal(typeof a.commands[match[1]],'function',
      `${file}: unresolved command ${match[1]}`);
  }
}
a.bindEvents();
const count=events.length;
assert.ok(count>20,'real forms and gestures must be bound');
a.bindEvents();assert.equal(events.length,count,'binding must be idempotent');
for(const [key,action] of Object.entries(a.commands.actions))
  assert.equal(typeof action,'function',`unresolved page action ${key}`);
const effects=[];
Object.assign(a.commands,{render:()=>effects.push('render'),
  refresh:()=>effects.push('refresh'),saveDraft:()=>effects.push('draft'),
  status:()=>{},message:()=>{}});
const original={schemaVersion:1,title:'original',page:{width:100,height:100},
  nodes:[],edges:[],junctions:[],labels:[]};
a.state.doc=structuredClone(original);
a.commands.edit(()=>{a.state.doc.title='changed';});
assert.equal(a.state.undo.length,1);
assert.equal(a.state.revision,1);
assert.ok(a.state.dirty);
assert.deepEqual(effects,['draft','render','refresh']);
a.commands.history('undo',{deferRefresh:true});
assert.deepEqual(a.state.doc,original);
a.commands.history('redo',{deferRefresh:true});
assert.equal(a.state.doc.title,'changed');
assert.equal(b.state.doc,null);
assert.deepEqual(b.state.undo,[]);
// File loading calls the real session/selection ports after asynchronous resolve.
a.commands.api=async(_path,body)=>({document:structuredClone(body.document),
  nodes:[],fontFamily:'serif',features:[]});
a.commands.fit=()=>{};
assert.equal(await a.commands.replaceDocument(original,true),true);
assert.deepEqual(a.state.doc,original);
assert.deepEqual(a.state.undo,[]);
assert.deepEqual(a.state.redo,[]);
assert.equal(a.state.dirty,false);
// Cold start before features are known must not pre-block mounts/edge labels.
const c=createEditor();
const seenUrls=[];
globalThis.fetch=async(url,options)=>{
  seenUrls.push(url);
  return {ok:true,headers:{get:()=>'application/json'},
    json:async()=>({document:JSON.parse(options.body).document,
      nodes:[],fontFamily:'serif',features:['edgeLabels','pipeMounts']})};
};
const coldRes=await c.commands.api('resolve',{document:{schemaVersion:1,
  nodes:[{id:'v',mount:{edgeId:'e',at:0.5}}],
  labels:[{id:'l',edgeId:'e',at:0.5,text:'1'}]}});
assert.deepEqual(seenUrls,['/api/resolve']);
assert.deepEqual(coldRes.features,['edgeLabels','pipeMounts']);
// Once known to be legacy, pre-blocking still applies.
c.state.featuresKnown=true;c.state.pipeMountsSupported=false;
await assert.rejects(()=>c.commands.api('resolve',{document:{schemaVersion:1,
  nodes:[{id:'v',mount:{edgeId:'e',at:0.5}}],labels:[]}}),/阀件挂接/);
"""
    result = subprocess.run(
        [executable, "--experimental-default-type=module", "--input-type=module",
         "-e", script],
        input=json.dumps(str(ROOT)), encoding="utf-8", capture_output=True,
    )
    assert result.returncode == 0, result.stderr
