"""连线与重接在提交前校验，失败保留起点、图纸和历史。"""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, validate_scene
from rrplot.scene_renderer import export_scene


def connection_scenario(code, document=None):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional connection interaction check")
    root = Path(__file__).resolve().parents[1]
    modules = {
        name: "data:text/javascript;base64,"
        + base64.b64encode(root.joinpath("web", name + ".js").read_bytes()).decode()
        for name in ["geometry", "document", "checks"]
    }
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const geometry=await import(input.modules.geometry);
const edits=await import(input.modules.document);
const checks=await import(input.modules.checks);
const elements=new Map(),listeners=new Map(),messages=[],statuses=[],results=[];
let uuid=0,saves=0,refreshes=0;
function element(id){if(!elements.has(id))elements.set(id,{
  addEventListener:(name,handler)=>listeners.set(id+':'+name,handler),
  focus(){},classes:{},classList:{remove(){},
    toggle(name,on){element(id).classes[name]=on;}},hasPointerCapture:()=>false});
  return elements.get(id);}
const context=vm.createContext({...geometry,...edits,...checks,input,
  structuredClone,results,messages,listeners,
  crypto:{randomUUID:()=>String(++uuid).padStart(8,'0')},
  document:{getElementById:element,querySelector:s=>s==='.canvas-hint'
      ?element('canvas-hint'):null,
    addEventListener:(name,handler)=>listeners.set('document:'+name,handler)},
  window:{addEventListener:(name,handler)=>listeners.set('window:'+name,handler)},
  ResizeObserver:class{observe(){}},
  save:()=>saves++,recordRefresh:()=>refreshes++,recordStatus:m=>statuses.push(m)});
const source=fs.readFileSync(input.path,'utf8').split(String.fromCharCode(10))
  .filter(line=>!line.startsWith('import ')).join(String.fromCharCode(10))
  .replace('void init();','');
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.resolved.document);
  geometries=new Map(input.resolved.nodes.map(n=>[n.id,n.geometry]));
  globalThis.actualRenderCanvas=renderCanvas;
  render=()=>{};renderCanvas=()=>{renderHint();};
  world=event=>event.point||[0,0];status=recordStatus;
  message=m=>messages.push(m);saveDraft=save;refresh=recordRefresh;
  globalThis.snapshot=()=>structuredClone({doc,undo,redo,dirty,revision,request,
    selection,multiSelection,pendingPort,previewTarget,reconnect,mode,view,ownedDraft});
  globalThis.click=ref=>{const hit={dataset:ref.junctionId
    ?{kind:'junction',id:ref.junctionId}
    :{kind:'port',ref:JSON.stringify(ref)}};
    listeners.get('diagram:pointerdown')({button:0,pointerId:1,
      target:{closest:()=>hit},preventDefault(){}});};
  globalThis.hover=(ref,point=[0,0])=>{const hit=!ref?null:{dataset:ref.junctionId
    ?{kind:'junction',id:ref.junctionId}
    :{kind:'port',ref:JSON.stringify(ref)}};
    listeners.get('diagram:pointermove')({point,target:{closest:()=>hit}});};
  globalThis.feedback=()=>structuredClone({target:previewTarget,
    text:$('canvas-hint').textContent,classes:$('canvas-hint').classes});`,context);
await vm.runInContext('(async()=>{'+input.code+'})()',context);
console.log(JSON.stringify({results,messages,statuses,saves,refreshes,
  state:vm.runInContext('snapshot()',context)}));
"""
    completed = subprocess.run(
        [executable, "--input-type=module", "-e", script],
        input=json.dumps(dict(code=code, modules=modules,
                             resolved=resolve_scene(document or load_template(
                                 "evi_ftvi")), path=str(root / "web/app.js"))),
        encoding="utf-8", capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_auto_route_rejected_without_changing_editor(name, reverse):
    output = connection_scenario("""
      const edge=doc.edges[0];edge.vertices=[];
      const refs=[edge.source,edge.target];
    """ + ("refs.reverse();edge.vertices=route("
               "endpoint(refs[0],currentNodes(),doc.junctions),"
               "endpoint(refs[1],currentNodes(),doc.junctions))"
               ".slice(1,-1).reverse();" if reverse else "") + """
      undo=[{old:true}];redo=[{future:true}];ownedDraft='existing-draft';
      mode='connect';click(refs[0]);results.push(snapshot());
      click(refs[1]);results.push(snapshot());
    """, load_template(name))
    assert output["results"][0] == output["results"][1]
    assert output["saves"] == output["refreshes"] == 0
    assert "相同走线" in output["messages"][-1]


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_new_pipe_commits_once_and_supports_undo_redo(name):
    output = connection_scenario("""
      const edge=doc.edges.shift();edge.vertices=[];
      mode='connect';click(edge.source);results.push(snapshot());
      click(edge.target);results.push(snapshot());
      history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());
    """, load_template(name))
    before, after, undone, redone = output["results"]
    assert len(after["doc"]["edges"]) == len(before["doc"]["edges"]) + 1
    assert len(after["undo"]) == 1 and after["dirty"]
    assert after["pendingPort"] is None and after["previewTarget"] is None
    assert undone["doc"] == before["doc"]
    assert redone["doc"] == after["doc"]
    assert output["saves"] == output["refreshes"] == 3
    validate_scene(after["doc"])
    assert export_scene(after["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("target", ["same", "junction", "device", "alias"])
def test_coincident_endpoints_keep_start_and_allow_valid_retry(target):
    output = connection_scenario("""
      const ref=doc.edges[0].source;
      const first=doc.nodes.find(node=>node.id===ref.nodeId);
      const p=endpoint(ref,currentNodes(),doc.junctions).point;
      doc.junctions.push({id:'overlap',x:p[0],y:p[1]},
        {id:'valid',x:p[0]+100,y:p[1]+90});
      const other={...structuredClone(first),id:'overlap-node'};
      const port=geometries.get(first.id).ports[ref.portId];
      other.rotation=0;other.x=p[0]-port.point[0];other.y=p[1]-port.point[1];
      doc.nodes.push(other);geometries.set(other.id,geometries.get(first.id));
      geometries.get(first.id).ports.alias=structuredClone(port);
      const targets={same:ref,junction:{junctionId:'overlap'},
        device:{nodeId:other.id,portId:ref.portId},
        alias:{nodeId:first.id,portId:'alias'}};
      mode='connect';click(ref);results.push(snapshot());
      click(targets['""" + target + """']);results.push(snapshot());
      click({junctionId:'valid'});results.push(snapshot());
    """)
    before, rejected, after = output["results"]
    assert before == rejected
    assert "同一位置" in output["messages"][0]
    assert output["messages"][-1] == ""
    assert len(after["doc"]["edges"]) == len(before["doc"]["edges"]) + 1
    assert len(after["undo"]) == output["saves"] == 1


@pytest.mark.parametrize("reverse", [False, True])
def test_parallel_pipe_with_different_manual_route_is_allowed(reverse):
    output = connection_scenario("""
      const edge=doc.edges[0];
      edge.vertices=[[5,5],[5,30]];
      const refs=[edge.source,edge.target];
    """ + ("refs.reverse();" if reverse else "") + """
      mode='connect';click(refs[0]);click(refs[1]);
    """)
    assert output["saves"] == 1 and output["messages"] == [""]


@pytest.mark.parametrize("side", ["source", "target"])
@pytest.mark.parametrize("reverse", [False, True])
def test_reconnect_rejects_duplicate_but_keeps_session_for_retry(side, reverse):
    output = connection_scenario("""
      doc.nodes=[];doc.labels=[];
      doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:100,y:0},
        {id:'c',x:200,y:0},{id:'d',x:100,y:100}];
      const ref=id=>({junctionId:id}), base=doc.edges[0];
      const side='""" + side + """';
      doc.edges=[{...base,id:'existing',source:ref('a'),target:ref('b'),vertices:[]},
        {...base,id:'editing',source:ref(side==='source'?'c':'a'),
          target:ref(side==='source'?'b':'c'),vertices:[]}];
    """ + ("[doc.edges[0].source,doc.edges[0].target]="
               "[doc.edges[0].target,doc.edges[0].source];"
               if reverse else "") + """
      doc.labels=[{id:'state',edgeId:'editing',at:.3,x:5,y:7,text:'P'}];
      beginReconnect(doc.edges[1],side);results.push(snapshot());
      click(ref(side==='source'?'a':'b'));results.push(snapshot());
      click(ref('d'));results.push(snapshot());
      history('undo');results.push(snapshot());
    """)
    before, rejected, after, undone = output["results"]
    assert before == rejected and "相同走线" in output["messages"][1]
    assert after["reconnect"] is None and len(after["undo"]) == 1
    assert after["doc"]["labels"] == before["doc"]["labels"]
    assert undone["doc"] == before["doc"]


def test_original_endpoint_reconnect_is_noop_even_with_old_duplicate():
    output = connection_scenario("""
      const edge=doc.edges[0];
      doc.edges.push({...structuredClone(edge),id:'old-duplicate'});
      const before=snapshot();beginReconnect(edge,'source');
      click(Object.fromEntries(Object.entries(edge.source).reverse()));
      results.push(before,snapshot());
    """)
    before, after = output["results"]
    assert after["doc"] == before["doc"]
    assert after["undo"] == before["undo"] and not after["dirty"]
    assert after["reconnect"] is None and output["saves"] == 0


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_hover_feedback_checks_duplicates_before_click_without_edit(name):
    output = connection_scenario("""
      const edge=doc.edges[0];edge.vertices=[];
      mode='connect';click(edge.source);results.push(snapshot());
      hover(edge.target);results.push(feedback(),snapshot());
      hover(edge.source);results.push(feedback());
      hover(null,[23,47]);results.push(feedback());
    """, load_template(name))
    before, invalid, after, same, blank = output["results"]
    assert "相同走线" in invalid["text"]
    assert invalid["classes"]["connection-invalid-hint"]
    assert not invalid["classes"]["connection-valid-hint"]
    assert "同一位置" in same["text"]
    assert blank["target"]["point"] == [23, 47]
    assert "起点已选" in blank["text"]
    assert not any(blank["classes"].values())
    assert {k: v for k, v in after.items() if k != "previewTarget"} == {
        k: v for k, v in before.items() if k != "previewTarget"}
    assert output["saves"] == output["refreshes"] == 0
    assert output["messages"] == []


def test_hover_cache_invalidates_on_revision_and_distinguishes_same_position():
    output = connection_scenario("""
      const edge=doc.edges[0];edge.vertices=[];mode='connect';click(edge.source);
      let count=0;const check=checkConnection;
      checkConnection=(...args)=>{count++;return check(...args);};
      hover(edge.target);hover(edge.target);results.push(count);
      doc.edges.shift();revision++;hover(edge.target);hover(edge.target);
      results.push(count,feedback());
      const p=previewTarget.point;
      doc.junctions.push({id:'hover-junction',x:p[0],y:p[1]});
      hover({junctionId:'hover-junction'});results.push(count,feedback());
      listeners.get('diagram:pointerleave')();renderHint();
      results.push(feedback());
      hover(edge.target);results.push(count,feedback());
    """)
    count, changed_count, valid, junction_count, junction, left, reentry, _ = (
        output["results"])
    assert count == 1 and changed_count == 2 and junction_count == 3
    assert "点击连接" in valid["text"] and not valid["target"]["error"]
    assert valid["classes"]["connection-valid-hint"]
    assert junction["target"]["ref"] == {"junctionId": "hover-junction"}
    assert "三通" in junction["text"]
    assert left["target"] is None and not any(left["classes"].values())
    assert reentry == 4 and output["saves"] == 0


@pytest.mark.parametrize("side", ["source", "target"])
def test_reconnect_hover_feedback_matches_commit_checks_and_cancel(side):
    output = connection_scenario("""
      const edge=doc.edges[0],side='""" + side + """';
      beginReconnect(edge,side);results.push(snapshot());
      hover(edge[side]);results.push(feedback());
      hover(edge[side==='source'?'target':'source']);results.push(feedback());
      const other=endpoint(edge[side==='source'?'target':'source'],
        currentNodes(),doc.junctions).point;
      doc.junctions.push({id:'overlapping-target',x:other[0],y:other[1]});
      hover({junctionId:'overlapping-target'});results.push(feedback());
      cancelReconnect();renderHint();results.push(feedback());
    """)
    _, original, opposite, overlap, canceled = output["results"]
    assert original["target"]["error"] == ""
    assert original["classes"]["connection-valid-hint"]
    assert "同一位置" in opposite["text"] and "同一位置" in overlap["text"]
    assert canceled["target"] is None and not any(canceled["classes"].values())
    assert output["saves"] == 0 and output["state"]["undo"] == []


@pytest.mark.parametrize("invalid", [False, True])
def test_svg_preview_and_target_marker_show_validity_and_cleanup(invalid):
    output = connection_scenario("""
      const edge=doc.edges[0];edge.vertices=[];doc.labels=[];
    """ + ("" if invalid else "doc.edges.shift();") + """
      mode='connect';click(edge.source);hover(edge.target);
      const shapes=[];
      shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {textContent:''};};
      svg.replaceChildren=()=>{shapes.length=0;};
      renderVertices=()=>{};updateView=()=>{};
      actualRenderCanvas();results.push(structuredClone(shapes));
      cancelReconnect();actualRenderCanvas();results.push(structuredClone(shapes));
    """)
    active, canceled = output["results"]
    preview = next(s for s in active if s.get("class", "").startswith(
        "connection-preview"))
    marker = next(s for s in active if s.get("class", "").startswith(
        "connection-target"))
    assert ("invalid" in preview["class"]) is invalid
    assert ("invalid" in marker["class"]) is invalid
    assert marker["vector-effect"] == "non-scaling-stroke"
    assert not any(s.get("class", "").startswith("connection-") for s in canceled)


@pytest.mark.parametrize("side", ["source", "target"])
def test_duplicate_reconnect_hover_keeps_document_and_history(side):
    output = connection_scenario("""
      doc.nodes=[];doc.labels=[];
      doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:100,y:0},{id:'c',x:200,y:0}];
      const ref=id=>({junctionId:id}),base=doc.edges[0],side='""" + side + """';
      doc.edges=[{...base,id:'existing',source:ref('a'),target:ref('b'),vertices:[]},
        {...base,id:'editing',source:ref(side==='source'?'c':'a'),
          target:ref(side==='source'?'b':'c'),vertices:[]}];
      beginReconnect(doc.edges[1],side);results.push(snapshot());
      hover(ref(side==='source'?'a':'b'));results.push(feedback(),snapshot());
    """)
    before, feedback, after = output["results"]
    assert "相同走线" in feedback["text"]
    assert feedback["classes"]["connection-invalid-hint"]
    assert {k: v for k, v in after.items() if k != "previewTarget"} == {
        k: v for k, v in before.items() if k != "previewTarget"}
    assert output["saves"] == output["refreshes"] == 0
