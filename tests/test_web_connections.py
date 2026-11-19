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
        for name in ["geometry", "document", "checks", "requests", "glyphs"]
    }
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const geometry=await import(input.modules.geometry);
const edits=await import(input.modules.document);
const checks=await import(input.modules.checks);
const requests=await import(input.modules.requests);
const glyphs=await import(input.modules.glyphs);
// Shape-recording interaction scenarios use a stateless renderer; renderer
// identity/order/cache behavior is covered separately in test_web_canvas.py.
const createCanvasRenderer=root=>({begin:()=>root.replaceChildren(),
  group:(key,tag,attrs)=>({element:vm.runInContext('shape',context)(tag,attrs),changed:true}),
  place:element=>root.append(element),end:()=>{}});
const elements=new Map(),listeners=new Map(),messages=[],statuses=[],results=[];
const observers=[];
let uuid=0,saves=0,refreshes=0;
function element(id){if(!elements.has(id))elements.set(id,{
  attributes:{},setAttribute(key,value){this.attributes[key]=String(value);},
  addEventListener:(name,handler)=>listeners.set(id+':'+name,handler),
  focus(){},setPointerCapture(){},classes:{},classList:{remove(){},add(){},
    toggle(name,on){element(id).classes[name]=on;}},hasPointerCapture:()=>false});
  return elements.get(id);}
const context=vm.createContext({...geometry,...edits,...checks,...requests,...glyphs,
  createCanvasRenderer,input,
  structuredClone,results,messages,listeners,
  crypto:{randomUUID:()=>String(++uuid).padStart(8,'0')},
  document:{getElementById:element,querySelector:s=>s==='.canvas-hint'
      ?element('canvas-hint'):null,
    addEventListener:(name,handler)=>listeners.set('document:'+name,handler)},
  window:{addEventListener:(name,handler)=>listeners.set('window:'+name,handler)},
  ResizeObserver:class{constructor(callback){this.callback=callback;}
    observe(target){observers.push({target,callback:this.callback});}},observers,
  save:()=>saves++,recordRefresh:()=>refreshes++,recordStatus:m=>statuses.push(m)});
const source=(await import('node:module')).createRequire(input.path)
  ('../tests/web_editor_harness.cjs').loadEditorSource(input.path);
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.resolved.document);
  geometries=new Map(input.resolved.nodes.map(n=>[n.id,n.geometry]));
  globalThis.actualRenderCanvas=renderCanvas;
  globalThis.actualRefresh=refresh;
  render=()=>{};renderCanvas=()=>{renderHint();};
  world=event=>event.point||[0,0];status=recordStatus;
  message=m=>messages.push(m);saveDraft=save;refresh=recordRefresh;
  globalThis.snapshot=()=>structuredClone({doc,undo,redo,dirty,revision,request,
    selection,multiSelection,pendingPort,connectionVertices,previewTarget,reconnect,mode,view,ownedDraft});
  globalThis.click=ref=>{const hit={dataset:ref.junctionId
    ?{kind:'junction',id:ref.junctionId}
    :{kind:'port',ref:JSON.stringify(ref)}};
    listeners.get('diagram:pointerdown')({button:0,pointerId:1,
      target:{closest:()=>hit},preventDefault(){}});};
  globalThis.hover=(ref,point=[0,0])=>{const hit=!ref?null:{dataset:ref.junctionId
    ?{kind:'junction',id:ref.junctionId}
    :{kind:'port',ref:JSON.stringify(ref)}};
    listeners.get('diagram:pointermove')({point,target:{closest:()=>hit}});};
  globalThis.hoverPipe=(edge,point,kind='edge')=>{
    const hit=edge?{dataset:{kind,id:edge.id}}:null;
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


@pytest.mark.parametrize("scale", [.2, .5, 1, 3])
@pytest.mark.parametrize("kind", ["port", "junction"])
def test_screen_distance_snaps_hover_and_click_to_same_endpoint(scale, kind):
    output = connection_scenario("""
      const scale=""" + str(scale) + """,kind='""" + kind + """';
      svg.getScreenCTM=()=>({a:scale,b:0,c:0,d:scale});
      const edge=doc.edges.shift();
      const p=endpoint(edge.target,currentNodes(),doc.junctions).point;
      const far=[p[0]+1000,p[1]+1000];
      doc.junctions.push({id:'snap-source',x:far[0],y:far[1]});
      if(kind==='junction'){
        doc.nodes=[];doc.edges=[];doc.labels=[];
        doc.junctions.push({id:'snap-target',x:p[0],y:p[1]});
      }
      const target=kind==='port'?edge.target:{junctionId:'snap-target'};
      const near=[p[0]+11/scale,p[1]];
      mode='connect';click({junctionId:'snap-source'});results.push(snapshot());
      hover(null,near);results.push(feedback());
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point:near,
        target:{closest:()=>null},preventDefault(){}});
      results.push(target,snapshot());
    """)
    before, feedback, ref, after = output["results"]
    assert feedback["target"]["ref"] == ref
    assert feedback["classes"]["connection-valid-hint"]
    assert after["doc"]["edges"][-1]["target"] == ref
    assert len(after["doc"]["edges"]) == len(before["doc"]["edges"]) + 1
    assert output["saves"] == output["refreshes"] == 1
    validate_scene(after["doc"])


PIPE_END_EVENTS = """
  const pipeEvent=(edge,point,shiftKey=true,kind='edge')=>({button:0,pointerId:1,
    point,shiftKey,clientX:100,clientY:100,
    target:{closest:selector=>selector==='[data-kind]'
      ?{dataset:{kind,id:edge.id}}:null},preventDefault(){}});
  const hoverEnd=(edge,point,shift=true)=>listeners.get('diagram:pointermove')(
    pipeEvent(edge,point,shift));
  const clickEnd=(edge,point,shift=true)=>listeners.get('diagram:pointerdown')(
    pipeEvent(edge,point,shift));
"""


PIPE_SNAP_SCENE = """
  const base=doc.edges[0];doc.nodes=[];doc.labels=[];
  doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:1000,y:0},
    {id:'origin',x:500,y:300},{id:'other',x:900,y:300}];
  doc.edges=[{...base,id:'trunk',source:{junctionId:'a'},
    target:{junctionId:'b'},vertices:[]},
    {...base,id:'editing',source:{junctionId:'origin'},
      target:{junctionId:'other'},vertices:[]}];
  const blankEvent=(point,shiftKey=false)=>({point,shiftKey,button:0,
    pointerId:1,clientX:100,clientY:100,target:{closest:()=>null},preventDefault(){}});
  const moveNear=(point,shift)=>listeners.get('diagram:pointermove')(
    blankEvent(point,shift));
  const clickNear=(point,shift)=>listeners.get('diagram:pointerdown')(
    blankEvent(point,shift));
"""


JUNCTION_REUSE_SCENE = PIPE_SNAP_SCENE + """
  doc.nodes=[];doc.edges=[];doc.labels=[];
  doc.junctions=[{id:'existing',x:500,y:500},{id:'end',x:1500,y:1500}];
  const portFixture=()=>{
    doc.junctions.shift();doc.nodes=[{id:'device',x:500,y:500,rotation:0}];
    geometries.set('device',{ports:{in:{point:[0,0],direction:[1,0]}}});
  };
"""


@pytest.mark.parametrize("scale", [.2, .5, 1, 3])
@pytest.mark.parametrize("kind", ["junction", "port"])
@pytest.mark.parametrize("branch", [False, True])
def test_junction_tool_reuses_nearby_endpoint_without_document_edit(
        scale, kind, branch):
    output = connection_scenario(JUNCTION_REUSE_SCENE + """
      const scale=""" + str(scale) + """;
      svg.getScreenCTM=()=>({a:scale,b:0,c:0,d:scale});
      if('""" + kind + """'==='port')portFixture();
      mode='junction';setSelection('junction','end');
      undo=[{old:true}];redo=[{future:true}];ownedDraft='existing-draft';
      results.push(snapshot());
      moveNear([500+11/scale,500],""" + str(branch).lower() + """);
      results.push(structuredClone(junctionPreview),feedback(),snapshot());
      clickNear([500+11/scale,500],""" + str(branch).lower() + """);
      results.push(snapshot());
    """)
    before, preview, hint, hovered, after = output["results"]
    assert before == hovered
    assert preview["point"] == [500, 500]
    for key in ["doc", "undo", "redo", "dirty", "revision", "ownedDraft"]:
        assert before[key] == after[key]
    if kind == "port":
        assert "设备端口" in preview["error"]
        assert hint["classes"]["junction-invalid-hint"]
        assert before == after and output["messages"][-1] == preview["error"]
    else:
        assert not preview["error"] and "已有三通" in hint["text"]
        assert after["selection"] == dict(kind="junction", id="existing")
        assert after["mode"] == ("connect" if branch else "select")
        assert after["pendingPort"] == ({"junctionId": "existing"} if branch else None)
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("kind", ["junction", "port"])
@pytest.mark.parametrize("branch", [False, True])
def test_junction_tool_direct_endpoint_matches_hover_without_transform(kind, branch):
    output = connection_scenario(JUNCTION_REUSE_SCENE + """
      const kind='""" + kind + """';if(kind==='port')portFixture();
      mode='junction';const event=blankEvent([500,500],""" + str(branch).lower() + """);
      const hit={dataset:kind==='port'?{kind,ref:JSON.stringify(
        {nodeId:'device',portId:'in'})}:{kind,id:'existing'}};
      event.target.closest=()=>hit;results.push(snapshot());
      listeners.get('diagram:pointermove')(event);
      results.push(structuredClone(junctionPreview));
      listeners.get('diagram:pointerdown')(event);results.push(snapshot());
    """)
    before, preview, after = output["results"]
    assert preview["point"] == [500, 500]
    assert after["doc"] == before["doc"] and after["undo"] == []
    assert after["mode"] == ("junction" if kind == "port" else
                             "connect" if branch else "select")
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("kind", ["junction", "port"])
@pytest.mark.parametrize("branch", [False, True])
def test_junction_grid_landing_does_not_duplicate_endpoint(kind, branch):
    output = connection_scenario(JUNCTION_REUSE_SCENE + """
      if('""" + kind + """'==='port')portFixture();
      svg.getScreenCTM=()=>({a:4,b:0,c:0,d:4});$('snap').checked=true;
      mode='junction';results.push(snapshot());
      moveNear([504,504],""" + str(branch).lower() + """);
      results.push(structuredClone(junctionPreview));
      clickNear([504,504],""" + str(branch).lower() + """);results.push(snapshot());
    """)
    before, preview, after = output["results"]
    assert preview["point"] == [500, 500]
    assert after["doc"] == before["doc"] and not after["undo"]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("guard", ["node", "label", "middle", "space"])
def test_junction_reuse_respects_non_pipe_hits_and_pan_priority(guard):
    output = connection_scenario(JUNCTION_REUSE_SCENE + """
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});mode='junction';
      const guard='""" + guard + """',event=blankEvent([505,500],true);
      if(['node','label'].includes(guard))event.target.closest=()=>({dataset:{kind:guard}});
      if(guard==='middle')event.button=1;if(guard==='space')spaceDown=true;
      results.push(snapshot());listeners.get('diagram:pointerdown')(event);
      results.push(snapshot(),drag?.kind||null);
    """)
    before, after, drag = output["results"]
    assert before == after
    assert drag == ("pan" if guard in {"middle", "space"} else None)
    assert output["saves"] == 0


def test_branch_from_reused_junction_adds_only_connection_and_undoes_once():
    output = connection_scenario(JUNCTION_REUSE_SCENE + """
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});mode='junction';
      results.push(snapshot());clickNear([505,500],true);results.push(snapshot());
      click({junctionId:'end'});results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """)
    before, reused, after, undone, redone = output["results"]
    assert before["doc"] == reused["doc"] and reused["undo"] == []
    assert len(after["doc"]["junctions"]) == 2 and len(after["doc"]["edges"]) == 1
    assert len(after["undo"]) == 1 and undone["doc"] == before["doc"]
    assert redone["doc"] == after["doc"]
    assert output["saves"] == output["refreshes"] == 3
    validate_scene(after["doc"])


def test_junction_port_rejection_allows_retry_at_valid_pipe_interior():
    output = connection_scenario(PIPE_SNAP_SCENE + """
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});mode='junction';
      doc.nodes=[{id:'device',x:0,y:0,rotation:0}];
      geometries.set('device',{ports:{in:{point:[0,0],direction:[1,0]}}});
      doc.junctions.shift();doc.edges[0].source={nodeId:'device',portId:'in'};
      results.push(snapshot());moveNear([5,0],false);clickNear([5,0],false);
      results.push(snapshot());moveNear([500,5],false);clickNear([500,5],false);
      results.push(snapshot());
    """)
    before, rejected, inserted = output["results"]
    assert before == rejected and len(inserted["undo"]) == 1
    assert inserted["doc"]["junctions"][-1]["x"] == 500
    assert inserted["doc"]["junctions"][-1]["y"] == 0
    assert output["saves"] == output["refreshes"] == 1


@pytest.mark.parametrize("scale", [.2, .5, 1, 3])
@pytest.mark.parametrize("operation", ["junction", "branch", "connect",
                                       "source", "target"])
def test_nearby_pipe_snap_matches_preview_commit_and_atomic_undo(scale, operation):
    output = connection_scenario(PIPE_SNAP_SCENE + """
      const scale=""" + str(scale) + """,operation='""" + operation + """';
      svg.getScreenCTM=()=>({a:scale,b:0,c:0,d:scale});
      if(['junction','branch'].includes(operation))mode='junction';
      else if(operation==='connect'){mode='connect';pendingPort={junctionId:'origin'};}
      else beginReconnect(doc.edges[1],operation);
      const point=[437,11/scale],shift=operation!=='junction';
      results.push(snapshot());moveNear(point,shift);
      results.push(structuredClone(junctionPreview||previewTarget),snapshot());
      clickNear(point,shift);results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """)
    before, preview, hovered, after, undone, redone = output["results"]
    assert preview.get("pipeId", preview.get("edgeId")) == "trunk"
    assert preview["point"] == pytest.approx([437, 0]) and not preview["error"]
    assert preview["fraction"] == pytest.approx(.437)
    for key in ["doc", "undo", "redo", "dirty", "revision", "ownedDraft"]:
        assert hovered[key] == before[key]
    junction = after["doc"]["junctions"][-1]
    assert [junction["x"], junction["y"]] == pytest.approx([437, 0])
    assert len(after["doc"]["edges"]) == 2 + (2 if operation == "connect" else 1)
    assert len(after["undo"]) == 1 and undone["doc"] == before["doc"]
    assert redone["doc"] == after["doc"]
    assert after["mode"] == ("connect" if operation in {"branch", "connect"}
                             else "select")
    if operation in {"source", "target"}:
        assert after["doc"]["edges"][1][operation] == {"junctionId": junction["id"]}
    assert output["saves"] == output["refreshes"] == 3
    validate_scene(after["doc"])


@pytest.mark.parametrize("distance", [12, 12.01])
@pytest.mark.parametrize("operation", ["junction", "connect", "target"])
def test_pipe_snap_screen_distance_boundary(distance, operation):
    output = connection_scenario(PIPE_SNAP_SCENE + """
      svg.getScreenCTM=()=>({a:.25,b:0,c:0,d:.25});
      const operation='""" + operation + """';
      if(operation==='junction')mode='junction';
      else if(operation==='connect'){mode='connect';pendingPort={junctionId:'origin'};}
      else beginReconnect(doc.edges[1],'target');
      const point=[500,""" + str(distance) + """/.25];
      moveNear(point,true);results.push(junctionPreview||previewTarget);
      results.push(snapshot());clickNear(point,true);results.push(snapshot());
    """)
    preview, before, after = output["results"]
    if distance == 12:
        assert preview.get("pipeId", preview.get("edgeId")) == "trunk"
        assert after["doc"]["junctions"][-1]["y"] == 0
    elif operation == "junction":
        assert preview is None
        assert len(after["doc"]["edges"]) == len(before["doc"]["edges"])
        assert after["doc"]["junctions"][-1]["y"] == 50  # Free placement snaps to grid.
    else:
        assert not preview.get("pipeId")
        assert before["doc"] == after["doc"] and before["undo"] == after["undo"]


@pytest.mark.parametrize("hit", ["nearest", "tie", "direct", "blocked", "invalid"])
def test_pipe_snap_selects_one_pipe_and_keeps_invalid_nearest(hit):
    output = connection_scenario(PIPE_SNAP_SCENE + """
      const hit='""" + hit + """';svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});
      doc.junctions.push({id:'c',x:0,y:hit==='tie'?16:14},
        {id:'d',x:1000,y:hit==='tie'?16:14});
      doc.edges.push({...doc.edges[0],id:'nearer',source:{junctionId:'c'},
        target:{junctionId:'d'}});
      mode='junction';const point=[500,8];
      if(hit==='invalid'){mode='reconnect';reconnect={edgeId:'nearer',side:'target'};}
      const event=blankEvent(point,true);
      if(hit==='direct')event.target.closest=()=>({dataset:{kind:'edge',id:'trunk'}});
      if(hit==='blocked')event.target.closest=()=>({dataset:{kind:'label',id:'text'}});
      results.push(snapshot());listeners.get('diagram:pointermove')(event);
      results.push(junctionPreview||previewTarget);
      listeners.get('diagram:pointerdown')(event);results.push(snapshot());
    """)
    before, preview, after = output["results"]
    if hit == "blocked":
        assert preview is None and before == after
    elif hit == "invalid":
        assert preview["pipeId"] == "nearer" and "自身" in preview["error"]
        assert before["doc"] == after["doc"] and before["undo"] == after["undo"]
    else:
        expected = "nearer" if hit == "nearest" else "trunk"
        assert preview["edgeId"] == expected
        untouched = "trunk" if expected == "nearer" else "nearer"
        assert next(e for e in before["doc"]["edges"] if e["id"] == untouched) == next(
            e for e in after["doc"]["edges"] if e["id"] == untouched)
        assert len(after["doc"]["junctions"]) == len(before["doc"]["junctions"]) + 1


@pytest.mark.parametrize("matrix", [None, {"a": 0, "b": 0, "c": 0, "d": 1},
                                     {"a": 1, "b": 0, "c": 0, "d": None}])
def test_pipe_snap_requires_valid_transform_for_proximity_but_allows_direct(matrix):
    output = connection_scenario(PIPE_SNAP_SCENE + """
      svg.getScreenCTM=()=>(""" + json.dumps(matrix) + """);mode='junction';
      moveNear([500,8],true);results.push(junctionPreview);
      const event=blankEvent([500,8],true);
      event.target.closest=()=>({dataset:{kind:'edge',id:'trunk'}});
      listeners.get('diagram:pointermove')(event);results.push(junctionPreview);
    """)
    assert output["results"][0] is None
    assert output["results"][1]["point"] == [500, 0]
    assert output["saves"] == 0


def test_pipe_projection_uses_screen_metric_but_keeps_world_route_fraction():
    output = connection_scenario("""
      results.push(projectOnRoute([[0,0],[100,0]],[50,10],{a:1,b:0,c:1,d:1}),
        projectOnRoute([[0,100],[100,100],[100,0]],[95,85],{a:3,b:0,c:0,d:.5}),
        projectOnRoute([[0,100],[100,100],[100,0]],[95,85],{a:0,b:3,c:-.5,d:0}));
    """)
    shear, stretch, rotated = output["results"]
    assert shear == dict(point=[60, 0], at=.6, distance=10)
    assert stretch == rotated == dict(point=[95, 100], at=.475, distance=7.5)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_shift_connect_to_pipe_is_atomic_and_preserves_route_and_labels(name):
    document = load_template(name)
    for at in [.2, .8]:
        document["labels"].append(dict(id=f"split-label-{at}", text="state",
                                      edgeId=document["edges"][0]["id"], at=at,
                                      x=11, y=-13, size=12, ha="center",
                                      boxed=True, color="#123456"))
    output = connection_scenario(PIPE_END_EVENTS + """
      const edge=doc.edges[0],point=along(edgePoints(edge),.37).point;
      doc.junctions.push({id:'pipe-end-source',x:1500,y:1200});
      mode='connect';click({junctionId:'pipe-end-source'});results.push(snapshot());
      hoverEnd(edge,point);results.push(feedback(),snapshot());
      clickEnd(edge,point);results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """, document)
    before, feedback, hovered, connected, undone, redone = output["results"]
    assert feedback["target"]["pipeId"] == document["edges"][0]["id"]
    assert feedback["target"]["error"] == ""
    assert "Shift+点击" in feedback["text"]
    assert feedback["classes"]["connection-valid-hint"]
    assert {k: v for k, v in before.items() if k != "previewTarget"} == {
        k: v for k, v in hovered.items() if k != "previewTarget"}
    assert len(connected["doc"]["edges"]) == len(before["doc"]["edges"]) + 2
    junction = connected["doc"]["junctions"][-1]
    assert [junction["x"], junction["y"]] == pytest.approx(feedback["target"]["point"])
    branch = connected["doc"]["edges"][-1]
    assert branch["source"] == before["pendingPort"]
    assert branch["target"] == {"junctionId": junction["id"]}
    assert connected["selection"] == dict(kind="edge", id=branch["id"])
    assert connected["pendingPort"] is None and connected["previewTarget"] is None
    assert len(connected["undo"]) == 1
    assert undone["doc"] == before["doc"]
    assert redone["doc"] == connected["doc"]
    assert undone["pendingPort"] is redone["pendingPort"] is None
    assert output["saves"] == output["refreshes"] == 3
    old, new = resolve_scene(before["doc"]), resolve_scene(connected["doc"])
    positions = {label["id"]: label["position"] for label in old["labels"]}
    for label in new["labels"]:
        assert label["position"] == pytest.approx(positions[label["id"]])
    original = old["edges"][0]
    first, second = new["edges"][0], new["edges"][-2]
    def length(points):
        return sum(abs(b[0] - a[0]) + abs(b[1] - a[1])
                   for a, b in zip(points, points[1:]))
    assert length(first["points"]) == pytest.approx(length(original["points"]) * .37)
    assert length(second["points"]) == pytest.approx(length(original["points"]) * .63)
    for key in ["width", "color", "linestyle", "head", "headAt"]:
        assert first.get(key) == second.get(key) == original.get(key)
    assert export_scene(connected["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_shift_pipe_start_preserves_split_then_connects_and_undoes_separately(name):
    output = connection_scenario(PIPE_END_EVENTS + """
      const edge=doc.edges[0],point=along(edgePoints(edge),.37).point;
      doc.junctions.push({id:'finish',x:1500,y:1200});
      doc.labels.push({id:'start-state',text:'state',edgeId:edge.id,at:.8,
        x:7,y:-9,size:12,ha:'center',boxed:false,color:'#123456'});
      mode='connect';results.push(snapshot());hoverEnd(edge,point);
      results.push(feedback(),snapshot());clickEnd(edge,point);results.push(snapshot());
      click(pendingPort);results.push(snapshot());click({junctionId:'finish'});
      results.push(snapshot());history('undo');results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');history('redo');
      results.push(snapshot());
    """, load_template(name))
    before, hint, hovered, started, rejected, connected, unconnected, undone, redone = (
        output["results"])
    assert "作为连线起点" in hint["text"] and not hint["target"]["error"]
    assert before["doc"] == hovered["doc"] and hovered["undo"] == []
    junction = started["doc"]["junctions"][-1]
    assert [junction["x"], junction["y"]] == pytest.approx(hint["target"]["point"])
    assert started["pendingPort"] == {"junctionId": junction["id"]}
    assert started["mode"] == "connect" and len(started["undo"]) == 1
    assert started == rejected
    assert len(started["doc"]["edges"]) == len(before["doc"]["edges"]) + 1
    assert len(connected["doc"]["edges"]) == len(before["doc"]["edges"]) + 2
    assert connected["doc"]["edges"][-1]["source"] == started["pendingPort"]
    assert unconnected["doc"] == started["doc"] and undone["doc"] == before["doc"]
    assert redone["doc"] == connected["doc"] and redone["pendingPort"] is None
    assert output["saves"] == output["refreshes"] == 6
    old, split = resolve_scene(before["doc"]), resolve_scene(started["doc"])
    positions = {label["id"]: label["position"] for label in old["labels"]}
    for label in split["labels"]:
        assert label["position"] == pytest.approx(positions[label["id"]])
    assert export_scene(connected["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("scale", [.2, .5, 1, 3])
def test_shift_pipe_start_nearby_snap_and_second_pipe_connection(scale):
    output = connection_scenario(PIPE_SNAP_SCENE + """
      const scale=""" + str(scale) + """;
      svg.getScreenCTM=()=>({a:scale,b:0,c:0,d:scale});mode='connect';
      results.push(snapshot());moveNear([437,11/scale],true);results.push(feedback());
      clickNear([437,11/scale],true);results.push(snapshot());
      clickNear([700,300+11/scale],true);results.push(snapshot());
      history('undo');results.push(snapshot());history('undo');results.push(snapshot());
    """)
    before, hint, started, connected, unconnected, undone = output["results"]
    assert hint["target"]["point"] == [437, 0]
    assert len(started["doc"]["edges"]) == 3
    assert len(connected["doc"]["edges"]) == 5 and len(connected["undo"]) == 2
    assert unconnected["doc"] == started["doc"] and undone["doc"] == before["doc"]
    validate_scene(connected["doc"])


@pytest.mark.parametrize("action", ["shift-up", "leave", "escape", "tool", "zoom",
                                    "blur"])
def test_pipe_start_preview_is_read_only_and_clears(action):
    cleanup = {
        "shift-up": "listeners.get('window:keyup')({key:'Shift'});",
        "leave": "listeners.get('diagram:pointerleave')();",
        "escape": ("svg.matches=()=>false;await listeners.get('window:keydown')("
                   "{key:'Escape',target:svg,preventDefault(){}});"),
        "tool": "setTool('select');", "zoom": "zoom(.9);",
        "blur": "listeners.get('window:blur')();",
    }
    output = connection_scenario(PIPE_END_EVENTS + """
      mode='connect';doc.labels=[];const edge=doc.edges[0];results.push(snapshot());
      hoverEnd(edge,along(edgePoints(edge),.37).point);
      const shapes=[];shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {};};
      svg.replaceChildren=()=>{shapes.length=0;};renderVertices=()=>{};updateView=()=>{};
      actualRenderCanvas();results.push(structuredClone(shapes));
    """ + cleanup[action] + """
      actualRenderCanvas();results.push(snapshot(),structuredClone(shapes));
    """)
    before, shapes, after, cleared = output["results"]
    assert any("connection-candidate" in s.get("class", "") for s in shapes)
    assert any(s.get("class") == "connection-target" for s in shapes)
    assert not any("connection-preview" in s.get("class", "") for s in shapes)
    assert after["previewTarget"] is None and after["doc"] == before["doc"]
    assert not any("connection-candidate" in s.get("class", "") for s in cleared)
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("failure", ["endpoint", "zero", "vertices", "edges",
                                     "junctions"])
def test_pipe_start_invalid_target_keeps_document_and_allows_retry(failure):
    setup = {
        "endpoint": "point=[0,0];",
        "zero": "edgePoints=()=>[[30,30],[30,30]];point=[30,30];",
        "vertices": ("edgePoints=()=>Array.from({length:205},(_,i)=>[i,0]);"
                     "point=[102,0];"),
        "edges": ("while(doc.edges.length<2000)doc.edges.push("
                  "{...edge,id:'e'+doc.edges.length});"),
        "junctions": ("while(doc.junctions.length<2000)doc.junctions.push("
                      "{id:'j'+doc.junctions.length,x:999,y:999});"),
    }
    output = connection_scenario(PIPE_END_EVENTS + PIPE_SNAP_SCENE + """
      mode='connect';const edge=doc.edges[0];let point=[500,0];
    """ + setup[failure] + """
      results.push(snapshot());hoverEnd(edge,point);results.push(feedback());
      clickEnd(edge,point);results.push(snapshot());
      doc.edges.splice(2);doc.junctions.splice(4);click({junctionId:'origin'});
      results.push(snapshot());
    """)
    before, hint, rejected, retried = output["results"]
    assert hint["target"]["error"]
    assert rejected["doc"] == before["doc"] and rejected["undo"] == []
    assert rejected["pendingPort"] is None and retried["pendingPort"] == {
        "junctionId": "origin"}
    assert output["saves"] == output["refreshes"] == 0


def test_pipe_start_escape_keeps_inserted_junction_and_undo_removes_it():
    output = connection_scenario(PIPE_END_EVENTS + """
      mode='connect';const edge=doc.edges[0];results.push(snapshot());
      clickEnd(edge,along(edgePoints(edge),.37).point);results.push(snapshot());
      svg.matches=()=>false;await listeners.get('window:keydown')(
        {key:'Escape',target:svg,preventDefault(){}});results.push(snapshot());
      history('undo');results.push(snapshot());
    """)
    before, started, cancelled, undone = output["results"]
    assert started["doc"] == cancelled["doc"] and cancelled["pendingPort"] is None
    assert cancelled["mode"] == "select" and len(cancelled["undo"]) == 1
    assert undone["doc"] == before["doc"]


def test_pipe_start_existing_junction_priority_and_capacity_after_insertion():
    output = connection_scenario(PIPE_END_EVENTS + PIPE_SNAP_SCENE + """
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});mode='connect';
      while(doc.edges.length<1999)doc.edges.push({...doc.edges[0],id:'e'+doc.edges.length});
      doc.junctions.push({id:'near',x:500,y:0});
      clickEnd(doc.edges[0],[510,0]);results.push(snapshot());
      pendingPort=null;clickEnd(doc.edges[0],[437,0]);results.push(snapshot());
      hover({junctionId:'other'});results.push(feedback());click({junctionId:'other'});
      results.push(snapshot());history('undo');results.push(snapshot());
    """)
    reused, started, hint, rejected, undone = output["results"]
    assert reused["pendingPort"] == {"junctionId": "near"} and reused["undo"] == []
    assert len(started["doc"]["edges"]) == 2000 and len(started["undo"]) == 1
    assert "2000" in hint["target"]["error"]
    assert started["doc"] == rejected["doc"]
    assert started["pendingPort"] == rejected["pendingPort"]
    assert len(undone["doc"]["edges"]) == 1999


@pytest.mark.parametrize("kind", ["edges", "junctions"])
@pytest.mark.parametrize("entry", ["tool", "sidebar"])
def test_junction_insert_capacity_guard_preserves_history_and_geometry(kind, entry):
    output = connection_scenario(PIPE_END_EVENTS + PIPE_SNAP_SCENE + """
      const edge=doc.edges[0],kind='""" + kind + """',entry='""" + entry + """';
      while(doc[kind].length<2000)doc[kind].push(kind==='edges'
        ?{...edge,id:'e'+doc[kind].length}:{id:'j'+doc[kind].length,x:999,y:999});
      mode='junction';results.push(snapshot());
      if(entry==='tool'){hoverPipe(edge,[500,0]);results.push(junctionPreview);
        clickEnd(edge,[500,0],false);}else{splitEdge(edge);results.push(null);}
      results.push(snapshot());
    """)
    before, preview, after = output["results"]
    assert before == after and "2000" in output["messages"][-1]
    if entry == "tool":
        assert "2000" in preview["error"]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("guard", ["no-shift", "middle", "space", "busy"])
def test_pipe_start_does_not_insert_without_authorized_connection_state(guard):
    output = connection_scenario(PIPE_END_EVENTS + """
      const edge=doc.edges[0],point=along(edgePoints(edge),.37).point;
      const guard='""" + guard + """';mode='connect';
      if(guard==='space')spaceDown=true;if(guard==='busy')pageLayoutBusy=true;
      results.push(snapshot());const event=pipeEvent(edge,point,guard!=='no-shift');
      if(guard==='middle')event.button=1;listeners.get('diagram:pointerdown')(event);
      results.push(snapshot(),drag?.kind||null);
    """)
    before, after, drag = output["results"]
    assert before["doc"] == after["doc"] and before["undo"] == after["undo"]
    assert after["pendingPort"] is None
    assert drag == ("pan" if guard in {"middle", "space"} else None)
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("failure", ["same-point", "duplicate", "endpoint", "zero",
                                     "vertex-limit", "edge-limit", "junction-limit"])
def test_pipe_end_rejection_is_atomic_then_valid_endpoint_can_retry(failure):
    setup = {
        "same-point": "point=[50,0];doc.junctions[2].y=0;",
        "duplicate": "pendingPort={junctionId:'a'};",
        "endpoint": "point=[0,0];",
        "zero": "doc.junctions[1].x=0;point=[0,0];",
        "vertex-limit": ("edgePoints=()=>Array.from({length:205},(_,i)=>[i,0]);"
                         "point=[102,0];"),
        "edge-limit": ("while(doc.edges.length<1999)"
                       "doc.edges.push({...edge,id:'e'+doc.edges.length});"),
        "junction-limit": ("while(doc.junctions.length<2000)doc.junctions.push("
                           "{id:'j'+doc.junctions.length,x:999,y:999});"),
    }
    output = connection_scenario(PIPE_END_EVENTS + """
      const base=doc.edges[0];doc.nodes=[];doc.labels=[];
      doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:100,y:0},
        {id:'origin',x:50,y:100},{id:'retry',x:200,y:200}];
      doc.edges=[{...base,id:'pipe',source:{junctionId:'a'},target:{junctionId:'b'},vertices:[]}];
      const edge=doc.edges[0];let point=[50,0];
      mode='connect';pendingPort={junctionId:'origin'};
    """ + setup[failure] + """
      redo=[{future:true}];ownedDraft='saved';results.push(snapshot());
      hoverEnd(edge,point);results.push(feedback());clickEnd(edge,point);
      results.push(snapshot());
      // Remove only synthetic limit fixtures before retrying the same start.
      doc.edges.splice(1);doc.junctions=doc.junctions.slice(0,4);
      click({junctionId:'retry'});results.push(snapshot());
    """)
    before, feedback, rejected, retried = output["results"]
    assert feedback["target"]["error"]
    assert feedback["classes"]["connection-invalid-hint"]
    assert "不可接入管路" in feedback["text"]
    assert {k: v for k, v in before.items() if k != "previewTarget"} == {
        k: v for k, v in rejected.items() if k != "previewTarget"}
    assert rejected["pendingPort"] == before["pendingPort"]
    assert retried["pendingPort"] is None and len(retried["undo"]) == 1
    assert output["saves"] == output["refreshes"] == 1


@pytest.mark.parametrize("action", ["shift-up", "leave", "escape", "tool", "zoom",
                                    "blur"])
def test_pipe_end_preview_clears_without_inserting_junction(action):
    cleanup = {
        "shift-up": "listeners.get('window:keyup')({key:'Shift'});",
        "leave": "listeners.get('diagram:pointerleave')();",
        "escape": ("svg.matches=()=>false;await listeners.get('window:keydown')("
                   "{key:'Escape',target:svg,preventDefault(){}});renderHint();"),
        "tool": "setTool('select');renderHint();",
        "zoom": "zoom(.9);",
        "blur": "listeners.get('window:blur')();",
    }
    output = connection_scenario(PIPE_END_EVENTS + """
      doc.junctions.push({id:'origin',x:1500,y:1200});
      mode='connect';click({junctionId:'origin'});
      const edge=doc.edges[0],point=along(edgePoints(edge),.37).point;
      const shapes=[];shape=(tag,attrs={})=>{
        shapes.push({tag,...attrs});return {textContent:''};};
      doc.labels=[];svg.replaceChildren=()=>{shapes.length=0;};
      renderVertices=()=>{};updateView=()=>{};
      results.push(snapshot());hoverEnd(edge,point);actualRenderCanvas();
      results.push(structuredClone(shapes));
    """ + cleanup[action] + """
      actualRenderCanvas();results.push(snapshot(),structuredClone(shapes));
    """)
    before, shapes, after, cleared = output["results"]
    assert any("connection-candidate" in shape.get("class", "") for shape in shapes)
    assert any(shape.get("class") == "connection-target" for shape in shapes)
    assert after["previewTarget"] is None
    assert after["doc"] == before["doc"] and after["undo"] == before["undo"]
    assert not any("connection-candidate" in shape.get("class", "")
                   for shape in cleared)
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("context", ["no-shift", "reconnect", "middle",
                                     "space"])
def test_pipe_end_requires_shift_start_and_preserves_other_modes(context):
    output = connection_scenario(PIPE_END_EVENTS + """
      const context='""" + context + """',edge=doc.edges[0];
      const point=along(edgePoints(edge),.37).point;
      doc.junctions.push({id:'origin',x:1500,y:1200});mode='connect';
      pendingPort={junctionId:'origin'};
      if(context==='reconnect')beginReconnect(edge,'target');
      if(context==='space')spaceDown=true;
      results.push(snapshot());
      const event=pipeEvent(edge,point,context!=='no-shift');
      if(context==='middle')event.button=1;
      listeners.get('diagram:pointerdown')(event);results.push(snapshot(),drag?.kind||null);
    """)
    before, after, drag = output["results"]
    assert before["doc"] == after["doc"] and before["undo"] == after["undo"]
    assert before["pendingPort"] == after["pendingPort"]
    assert output["saves"] == output["refreshes"] == 0
    assert drag == ("pan" if context in {"middle", "space"} else None)


@pytest.mark.parametrize("scale", [.2, .5, 1, 3])
def test_shift_pipe_end_reuses_nearby_junction_before_splitting(scale):
    output = connection_scenario(PIPE_END_EVENTS + """
      const scale=""" + str(scale) + """;
      svg.getScreenCTM=()=>({a:scale,b:0,c:0,d:scale});
      doc.nodes=[];doc.labels=[];const base=doc.edges[0];
      doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:1000,y:0},
        {id:'near',x:500,y:0},{id:'origin',x:500,y:300}];
      doc.edges=[{...base,id:'pipe',source:{junctionId:'a'},
        target:{junctionId:'b'},vertices:[]}];
      const edge=doc.edges[0],point=[500+11/scale,0];
      mode='connect';click({junctionId:'origin'});results.push(snapshot());
      hoverEnd(edge,point);results.push(feedback());clickEnd(edge,point);
      results.push(snapshot());
    """)
    before, feedback, connected = output["results"]
    assert feedback["target"]["ref"] == {"junctionId": "near"}
    assert connected["doc"]["junctions"] == before["doc"]["junctions"]
    assert connected["doc"]["edges"][0] == before["doc"]["edges"][0]
    assert connected["doc"]["edges"][-1]["target"] == {"junctionId": "near"}
    assert output["saves"] == output["refreshes"] == 1


def test_pipe_end_crossing_only_splits_hit_pipe_and_click_rechecks_new_geometry():
    output = connection_scenario(PIPE_END_EVENTS + """
      const base=doc.edges[0];doc.nodes=[];doc.labels=[];
      doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:100,y:0},
        {id:'c',x:50,y:-50},{id:'d',x:50,y:50},
        {id:'origin',x:150,y:150}];
      doc.edges=[{...base,id:'pipe',source:{junctionId:'a'},
        target:{junctionId:'b'},vertices:[]},
        {...base,id:'crossing',source:{junctionId:'c'},
        target:{junctionId:'d'},vertices:[]}];
      mode='connect';click({junctionId:'origin'});results.push(snapshot());
      hoverEnd(doc.edges[0],[50,0]);results.push(feedback());
      // A changed path invalidates the old landing point even before new hover.
      doc.junctions[0].y=10;doc.junctions[1].y=10;revision++;
      clickEnd(doc.edges[0],[50,0]);results.push(snapshot());
    """)
    before, feedback, connected = output["results"]
    assert feedback["target"]["point"] == [50, 0]
    assert connected["doc"]["junctions"][-1]["y"] == 10
    assert connected["doc"]["edges"][1] == before["doc"]["edges"][1]
    assert len(connected["doc"]["edges"]) == 4
    assert output["saves"] == output["refreshes"] == 1


def test_pipe_end_preview_cache_rechecks_after_version_or_target_change():
    output = connection_scenario(PIPE_END_EVENTS + """
      doc.junctions.push({id:'origin',x:1500,y:1200});
      mode='connect';click({junctionId:'origin'});
      const edge=doc.edges[0],point=along(edgePoints(edge),.37).point;
      const check=checkConnection;let checks=0;
      checkConnection=(...args)=>{checks++;return check(...args);};
      hoverEnd(edge,point);hoverEnd(edge,point);results.push(checks);
      revision++;hoverEnd(edge,point);results.push(checks);
      const other=along(edgePoints(edge),.6).point;hoverEnd(edge,other);
      results.push(checks);clickEnd(edge,point);results.push(checks,snapshot());
    """)
    assert output["results"][:4] == [1, 2, 3, 5]
    assert len(output["results"][-1]["undo"]) == 1


def test_pipe_end_red_preview_matches_failed_commit_without_half_split():
    output = connection_scenario(PIPE_END_EVENTS + """
      const base=doc.edges[0];doc.nodes=[];doc.labels=[];
      doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:100,y:0}];
      doc.edges=[{...base,id:'pipe',source:{junctionId:'a'},
        target:{junctionId:'b'},vertices:[]}];
      mode='connect';click({junctionId:'a'});
      const shapes=[];shape=(tag,attrs={})=>{
        shapes.push({tag,...attrs});return {textContent:''};};
      svg.replaceChildren=()=>{shapes.length=0;};renderVertices=()=>{};
      updateView=()=>{};hoverEnd(doc.edges[0],[50,0]);actualRenderCanvas();
      results.push(structuredClone(shapes));clickEnd(doc.edges[0],[50,0]);
      results.push(snapshot());
    """)
    shapes, rejected = output["results"]
    assert any(s.get("class") == "edge connection-candidate invalid" for s in shapes)
    assert any(s.get("class") == "connection-preview invalid" for s in shapes)
    assert any(s.get("class") == "connection-target invalid" for s in shapes)
    assert len(rejected["doc"]["edges"]) == 1
    assert len(rejected["doc"]["junctions"]) == 2
    assert "相同走线" in output["messages"][-1]
    assert not rejected["undo"] and output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("mode", ["connect", "reconnect"])
def test_near_click_selects_start_or_reconnects_without_direct_hit(mode):
    output = connection_scenario("""
      svg.getScreenCTM=()=>({a:.5,b:0,c:0,d:.5});
      doc.junctions.push({id:'near',x:2000,y:2000});
      const edge=doc.edges[0];
    """ + ("mode='connect';" if mode == "connect" else
               "beginReconnect(edge,'target');") + """
      results.push(snapshot());
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point:[2020,2000],
        target:{closest:()=>null},preventDefault(){}});
      results.push(snapshot());
    """)
    before, after = output["results"]
    if mode == "connect":
        assert after["pendingPort"] == {"junctionId": "near"}
        assert after["doc"] == before["doc"] and not after["undo"]
        assert output["saves"] == 0
    else:
        assert after["reconnect"] is None
        assert after["doc"]["edges"][0]["target"] == {"junctionId": "near"}
        assert len(after["undo"]) == output["saves"] == 1


@pytest.mark.parametrize("matrix,point,expected", [
    (dict(a=.5, b=0, c=0, d=.5), [24, 0], True),
    (dict(a=.5, b=0, c=0, d=.5), [24.01, 0], False),
    (dict(a=0, b=2, c=-2, d=0), [0, 5], True),
    (dict(a=3, b=0, c=0, d=.5), [0, 20], True),
    (dict(a=3, b=0, c=0, d=.5), [5, 0], False),
    (dict(a=0, b=0, c=0, d=0), [0, 0], False),
])
def test_snap_uses_full_screen_transform_and_radius_boundary(matrix, point, expected):
    output = connection_scenario("""
      doc.nodes=[];doc.edges=[];doc.labels=[];doc.junctions=[{id:'j',x:0,y:0}];
      svg.getScreenCTM=()=> (""" + json.dumps(matrix) + """);
      results.push(connectionRef({target:{closest:()=>null}},
    """ + json.dumps(point) + """));
    """)
    assert output["results"] == ([dict(junctionId="j")] if expected else [None])


def test_nearest_target_ties_direct_hit_and_rotated_alias_ports():
    output = connection_scenario("""
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});
      doc.nodes=[];doc.edges=[];doc.labels=[];
      doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:10,y:0}];
      const blank={target:{closest:()=>null}};
      results.push(connectionRef(blank,[8,0]),connectionRef(blank,[5,0]));
      const direct={dataset:{kind:'junction',id:'a'}};
      results.push(connectionRef({target:{closest:()=>direct}},[9,0]));
      doc.junctions=[];doc.nodes=[{id:'rotated',x:20,y:30,rotation:90}];
      geometries.set('rotated',{ports:{first:{point:[10,0],direction:[1,0]},
        alias:{point:[10,0],direction:[1,0]}}});
      results.push(connectionRef(blank,[22,40]));
    """)
    assert output["results"] == [dict(junctionId="b"), dict(junctionId="a"),
                                    dict(junctionId="a"),
                                    dict(nodeId="rotated", portId="first")]


@pytest.mark.parametrize("middle,space", [(True, False), (False, True)])
def test_snapping_preserves_temporary_panning(middle, space):
    output = connection_scenario("""
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});
      mode='connect';spaceDown=""" + str(space).lower() + """;
      doc.junctions.push({id:'near',x:2000,y:2000});results.push(snapshot());
      listeners.get('diagram:pointerdown')({button:""" + ("1" if middle else "0")
                                 + """,pointerId:1,point:[2001,2000],
        clientX:2001,clientY:2000,target:{closest:()=>null},preventDefault(){}});
      results.push(drag.kind,snapshot());
    """)
    before, drag, after = output["results"]
    assert drag == "pan" and before == after and output["saves"] == 0


def test_nearby_target_is_not_used_in_selection_mode_or_without_screen_matrix():
    output = connection_scenario("""
      doc.junctions.push({id:'near',x:2000,y:2000});
      results.push(connectionRef({target:{closest:()=>null}},[2001,2000]));
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});mode='select';
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point:[2001,2000],
        clientX:2001,clientY:2000,target:{closest:()=>null},preventDefault(){}});
      results.push(drag.kind,snapshot());
    """)
    assert output["results"][0] is None and output["results"][1] == "pan"
    assert output["state"]["pendingPort"] is None and output["saves"] == 0


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_start_hover_names_port_without_edit_and_checks_after_first_click(name):
    output = connection_scenario("""
      const edge=doc.edges[0];edge.vertices=[];mode='connect';
      results.push(snapshot());
      let checks=0;const check=checkConnection;
      checkConnection=(...args)=>{checks++;return check(...args);};
      hover(edge.target);results.push(feedback(),snapshot(),checks);
      click(edge.target);hover(edge.target);results.push(feedback(),checks);
    """, load_template(name))
    before, start, after, initial_checks, same, checks = output["results"]
    assert start["text"].startswith("点击起点：")
    assert start["target"]["ref"] == before["doc"]["edges"][0]["target"]
    assert start["classes"]["connection-valid-hint"]
    assert not start["classes"]["connection-invalid-hint"]
    assert initial_checks == 0 and checks == 1
    assert "同一位置" in same["text"]
    assert {k: v for k, v in after.items() if k != "previewTarget"} == {
        k: v for k, v in before.items() if k != "previewTarget"}
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("scale", [.2, .5, 1, 3])
def test_start_hover_near_junction_clears_on_blank_leave_and_tool_change(scale):
    output = connection_scenario("""
      const scale=""" + str(scale) + """;
      svg.getScreenCTM=()=>({a:scale,b:0,c:0,d:scale});
      doc.junctions.push({id:'start-hover',x:2000,y:2000});
      mode='connect';let renders=0;
      renderCanvas=()=>{renders++;renderHint();};
      hover(null,[2000+11/scale,2000]);results.push(feedback());
      hover(null,[3000,3000]);results.push(feedback(),renders);
      hover(null,[3010,3000]);results.push(renders);
      hover(null,[2000,2000]);listeners.get('diagram:pointerleave')();
      results.push(feedback());
      hover(null,[2000,2000]);setTool('select');renderHint();
      hover(null,[2000,2000]);results.push(feedback());
    """)
    start, blank, renders, repeated, left, selected = output["results"]
    assert start["target"]["ref"] == {"junctionId": "start-hover"}
    assert start["text"].startswith("点击起点：三通")
    assert renders == repeated == 2
    for cleared in [blank, left, selected]:
        assert cleared["target"] is None
        assert not any(cleared["classes"].values())
    assert output["saves"] == output["refreshes"] == 0


def test_start_marker_has_no_preview_pipe_and_clears_after_tool_change():
    output = connection_scenario("""
      doc.labels=[];mode='connect';hover(doc.edges[0].source);
      const shapes=[];
      shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {textContent:'' };};
      svg.replaceChildren=()=>{shapes.length=0;};
      renderVertices=()=>{};updateView=()=>{};
      actualRenderCanvas();results.push(structuredClone(shapes));
      setTool('select');actualRenderCanvas();results.push(structuredClone(shapes));
    """)
    active, cleared = output["results"]
    assert sum(s.get("class") == "connection-target" for s in active) == 1
    assert not any(s.get("class", "").startswith("connection-preview") for s in active)
    assert not any(s.get("class", "").startswith("connection-") for s in cleared)


@pytest.mark.parametrize("kind", ["node", "label", "edge"])
@pytest.mark.parametrize("pending", [False, True])
def test_connect_miss_cannot_select_or_drag_existing_object(kind, pending):
    output = connection_scenario("""
      const kind='""" + kind + """';
      const item=doc[{node:'nodes',label:'labels',edge:'edges'}[kind]][0];
      setSelection('node',doc.nodes[1].id);mode='connect';
    """ + ("click(doc.edges[0].source);" if pending else "") + """
      ownedDraft='saved-draft';redo=[{future:true}];results.push(snapshot());
      const hit={dataset:{kind,id:item.id}};
      const target={closest:selector=>selector==='[data-kind]'?hit:null};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point:[2500,2500],
        target,preventDefault(){}});
      results.push(drag?.kind||null);
      listeners.get('diagram:pointermove')({point:[2600,2600],target});
      listeners.get('diagram:pointerup')({pointerId:1});results.push(snapshot());
    """)
    before, drag, after = output["results"]
    assert drag is None
    assert {k: v for k, v in after.items() if k != "previewTarget"} == {
        k: v for k, v in before.items() if k != "previewTarget"}
    assert output["saves"] == output["refreshes"] == 0
    assert "端口或三通" in output["statuses"][-1]


@pytest.mark.parametrize("pending", [False, True])
def test_connect_blank_pan_keeps_selection_start_and_document(pending):
    output = connection_scenario("""
      setSelection('node',doc.nodes[0].id);mode='connect';
    """ + ("click(doc.edges[0].source);" if pending else "") + """
      results.push(snapshot());
      svg.clientWidth=1000;svg.clientHeight=800;updateView=()=>{};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point:[2000,2000],
        clientX:100,clientY:100,target:{closest:()=>null},preventDefault(){}});
      results.push(drag.kind);
      listeners.get('diagram:pointermove')({clientX:150,clientY:140});
      listeners.get('diagram:pointerup')({pointerId:1});results.push(snapshot());
    """)
    before, drag, after = output["results"]
    assert drag == "pan" and before["view"] != after["view"]
    assert after["previewTarget"] is None
    assert {k: v for k, v in after.items() if k not in {"view", "previewTarget"}} == {
        k: v for k, v in before.items() if k not in {"view", "previewTarget"}}
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("pending", [False, True])
def test_connect_double_click_cannot_add_manual_vertex(pending):
    output = connection_scenario("""
      const edge=doc.edges[0];mode='connect';
    """ + ("click(edge.source);" if pending else "") + """
      results.push(snapshot());
      listeners.get('diagram:dblclick')({point:[300,300],target:{closest:selector=>
        selector==='[data-kind="edge"]'?{dataset:{id:edge.id}}:null}});
      results.push(snapshot());
    """)
    assert output["results"][0] == output["results"][1]
    assert output["saves"] == output["refreshes"] == 0


def test_selection_mode_still_allows_manual_vertex_edit():
    output = connection_scenario("""
      const edge=doc.edges[0];results.push(snapshot());
      listeners.get('diagram:dblclick')({point:[300,300],target:{closest:selector=>
        selector==='[data-kind="edge"]'?{dataset:{id:edge.id}}:null}});
      results.push(snapshot());
    """)
    before, after = output["results"]
    assert before["doc"] != after["doc"]
    assert [300, 300] in after["doc"]["edges"][0]["vertices"]
    assert len(after["undo"]) == output["saves"] == output["refreshes"] == 1


@pytest.mark.parametrize("phase", ["start", "connect", "reconnect"])
@pytest.mark.parametrize("action", ["zoom", "fit", "pan", "resize"])
def test_view_change_clears_stale_connection_preview_but_keeps_session(phase, action):
    actions = {
        "zoom": "zoom(.85);",
        "fit": "fit();",
        "pan": """startPan({pointerId:1,clientX:100,clientY:100,preventDefault(){}});
          listeners.get('diagram:pointermove')({clientX:140,clientY:120});
          listeners.get('diagram:pointerup')({pointerId:1});""",
        "resize": "observers.find(item=>item.target===svg).callback();",
    }
    setup = {
        "start": "mode='connect';",
        "connect": "mode='connect';click(edge.source);",
        "reconnect": "beginReconnect(edge,'target');",
    }
    output = connection_scenario("""
      const edge=doc.edges[0];edge.vertices=[];
      svg.clientWidth=1000;svg.clientHeight=800;updateView=()=>{};
      ownedDraft='existing-draft';redo=[{future:true}];
    """ + setup[phase] + """
      hover(edge.target);results.push(snapshot(),feedback());
    """ + actions[action] + """
      results.push(snapshot(),feedback());
      hover(edge.target);results.push(feedback());
    """)
    before, active, after, cleared, resumed = output["results"]
    assert active["target"] is not None
    assert cleared["target"] is None and not any(cleared["classes"].values())
    assert {k: v for k, v in after.items() if k not in {"view", "previewTarget"}} == {
        k: v for k, v in before.items() if k not in {"view", "previewTarget"}}
    assert resumed == active
    assert output["saves"] == output["refreshes"] == 0


def test_view_change_discards_validation_cache_before_resuming():
    output = connection_scenario("""
      const edge=doc.edges[0];edge.vertices=[];mode='connect';click(edge.source);
      let checks=0;const check=checkConnection;
      checkConnection=(...args)=>{checks++;return check(...args);};
      hover(edge.target);results.push(checks);
      updateView=()=>{};zoom(.85);
      hover(edge.target);hover(edge.target);results.push(checks,feedback());
    """)
    assert output["results"][0:2] == [1, 2]
    assert "相同走线" in output["results"][2]["text"]
    assert output["saves"] == 0


def test_view_change_without_preview_does_not_redraw_or_clear_selection():
    output = connection_scenario("""
      mode='select';setSelection('node',doc.nodes[0].id);results.push(snapshot());
      let renders=0;renderCanvas=()=>{renders++;};updateView=()=>{};
      svg.clientWidth=1000;svg.clientHeight=800;
      zoom(.85);fit();observers.find(item=>item.target===svg).callback();
      results.push(snapshot(),renders);
    """)
    before, after, renders = output["results"]
    assert renders == 0
    assert {k: v for k, v in after.items() if k != "view"} == {
        k: v for k, v in before.items() if k != "view"}


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("side", ["source", "target"])
def test_canvas_endpoint_handles_start_reconnect_at_transformed_port(name, side):
    output = connection_scenario("""
      const shapes=[];svg.querySelectorAll=()=>[];
      shape=(tag,attrs={},parent)=>{
        const item={tag,...attrs};shapes.push(item);
        if(tag==='title')return {set textContent(value){parent.title=value;}};
        return item;
      };
      const edge=doc.edges[0],side='""" + side + """';
      setSelection('edge',edge.id);results.push(snapshot());renderVertices();
      const handles=shapes.filter(item=>item['data-kind']==='endpoint');
      results.push(handles,endpoint(edge[side],currentNodes(),doc.junctions).point);
      const handle=handles.find(item=>item['data-side']===side);
      const hit={dataset:{kind:'endpoint',id:handle['data-id'],side}};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,
        target:{closest:()=>hit},preventDefault(){}});
      results.push(snapshot(),drag);
    """, load_template(name))
    before, handles, point, after, drag = output["results"]
    assert len(handles) == 2
    handle = next(item for item in handles if item["data-side"] == side)
    assert [handle["cx"], handle["cy"]] == point
    assert "点击后选择端口、三通" in handle["title"]
    assert "Shift+点击其他管路" in handle["title"]
    assert after["reconnect"] == {"edgeId": before["selection"]["id"], "side": side}
    assert after["mode"] == "reconnect" and drag is None
    for key in ["doc", "undo", "redo", "dirty", "revision", "ownedDraft",
                "selection", "multiSelection"]:
        assert after[key] == before[key]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("side", ["source", "target"])
def test_canvas_handle_reconnect_preserves_pipe_and_supports_undo_redo(side):
    output = connection_scenario("""
      const edge=doc.edges[0],side='""" + side + """';
      doc.junctions.push({id:'new-end',x:1500,y:1200});
      doc.labels.push({id:'handle-state',edgeId:edge.id,at:.4,x:4,y:8,text:'P'});
      setSelection('edge',edge.id);results.push(snapshot());
      const hit={dataset:{kind:'endpoint',id:edge.id,side}};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,
        target:{closest:()=>hit},preventDefault(){}});
      click({junctionId:'new-end'});results.push(snapshot());
      history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());
    """)
    before, after, undone, redone = output["results"]
    original = before["doc"]["edges"][0]
    expected = {**original, side: {"junctionId": "new-end"}}
    assert after["doc"]["edges"][0] == expected
    assert after["doc"]["labels"] == before["doc"]["labels"]
    assert len(after["undo"]) == 1 and after["reconnect"] is None
    assert undone["doc"] == before["doc"] and redone["doc"] == after["doc"]
    assert output["saves"] == output["refreshes"] == 3
    validate_scene(after["doc"])


def test_endpoint_handles_removed_outside_single_pipe_selection():
    output = connection_scenario("""
      const shapes=[],removed=[];let queried='';
      svg.querySelectorAll=selector=>{
        queried=selector;return [{remove(){removed.push(true);}}];};
      shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {};};
      const edge=doc.edges[0];
      const cases=[()=>clearSelection(),()=>setSelection('node',doc.nodes[0].id),
        ()=>setSelection('edge',doc.edges[1].id,true),
        ()=>{mode='connect';},()=>{mode='reconnect';},()=>{placement='compressor';}];
      for(const setup of cases){
        mode='select';placement=null;setSelection('edge',edge.id);setup();
        shapes.length=0;renderVertices();
        results.push(shapes.filter(s=>s['data-kind']==='endpoint').length);
      }
      results.push(queried,removed.length);
    """)
    assert output["results"][:6] == [0] * 6
    assert '[data-kind="endpoint"]' in output["results"][6]
    assert output["results"][7] == 6


@pytest.mark.parametrize("guard", ["middle", "space", "stale", "unselected", "multi"])
def test_endpoint_handle_keeps_pan_priority_and_ignores_stale_selection(guard):
    output = connection_scenario("""
      const edge=doc.edges[0],guard='""" + guard + """';
      setSelection('edge',edge.id);
      if(guard==='multi')setSelection('edge',doc.edges[1].id,true);
      if(guard==='unselected')setSelection('node',doc.nodes[0].id);
      spaceDown=guard==='space';results.push(snapshot());
      const hit={dataset:{kind:'endpoint',
        id:guard==='stale'?'missing':edge.id,side:'source'}};
      listeners.get('diagram:pointerdown')({button:guard==='middle'?1:0,
        pointerId:1,clientX:100,clientY:100,target:{closest:()=>hit},preventDefault(){}});
      results.push(snapshot(),drag?.kind||null);
    """)
    before, after, drag = output["results"]
    assert before == after
    assert drag == ("pan" if guard in {"middle", "space"} else None)
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("fraction", [.23, .77])
def test_click_pipe_inserts_junction_at_projection_and_preserves_labels(name, fraction):
    output = connection_scenario("""
      const edge=doc.edges[0],points=edgePoints(edge);
      edge.color='#336699';edge.linestyle='dashed';
      for(const at of [.1,.5,.9])doc.labels.push({id:'split-'+at,
        edgeId:edge.id,at,text:'P',x:7,y:-12});
      const position=along(points,""" + str(fraction) + """);
      const p=position.point.map((v,i)=>v+position.direction[1-i]*(i?-2:2));
      const projected=projectOnRoute(points,p);
      mode='junction';setSelection('node',doc.nodes[0].id);results.push(snapshot());
      const hit={dataset:{kind:'edge',id:edge.id}};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point:p,
        target:{closest:()=>hit},preventDefault(){}});
      results.push(snapshot(),projected,drag);
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """, load_template(name))
    before, after, projected, drag, undone, redone = output["results"]
    assert drag is None and after["mode"] == "select"
    junction = after["doc"]["junctions"][-1]
    assert [junction["x"], junction["y"]] == pytest.approx(projected["point"])
    assert projected["at"] == pytest.approx(fraction)
    assert len(after["doc"]["edges"]) == len(before["doc"]["edges"]) + 1
    assert len(after["undo"]) == 1
    assert after["selection"] == {"kind": "junction", "id": junction["id"]}
    first, second = after["doc"]["edges"][0], after["doc"]["edges"][-1]
    old = before["doc"]["edges"][0]
    assert first["target"] == second["source"] == {"junctionId": junction["id"]}
    assert first["source"] == old["source"] and second["target"] == old["target"]
    for key in ["color", "linestyle", "head", "headAt", "width"]:
        assert first[key] == second[key] == old[key]
    validate_scene(after["doc"])
    original_scene, split_scene = [resolve_scene(state["doc"])
                                   for state in (before, after)]
    def length(points):
        return sum(abs(a[0] - b[0]) + abs(a[1] - b[1])
                   for a, b in zip(points, points[1:]))

    original_length = length(original_scene["edges"][0]["points"])
    assert length(split_scene["edges"][0]["points"]) == pytest.approx(
        original_length * fraction)
    assert length(split_scene["edges"][-1]["points"]) == pytest.approx(
        original_length * (1 - fraction))
    positions = {label["id"]: label["position"] for label in original_scene["labels"]}
    for label in split_scene["labels"]:
        assert label["position"] == pytest.approx(positions[label["id"]])
    assert undone["doc"] == before["doc"] and redone["doc"] == after["doc"]
    assert output["saves"] == output["refreshes"] == 3


@pytest.mark.parametrize("hit_kind", ["port", "node", "junction", "label"])
def test_junction_tool_does_not_drag_or_select_existing_non_pipe(hit_kind):
    output = connection_scenario("""
      mode='junction';results.push(snapshot());
      const hit={dataset:{kind:'""" + hit_kind + """',id:doc.nodes[0].id}};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,
        point:[100,100],target:{closest:()=>hit},preventDefault(){}});
      results.push(snapshot(),drag);
    """)
    before, after, drag = output["results"]
    assert before == after and drag is None
    assert output["saves"] == 0 and "管路内部" in output["statuses"][-1]


@pytest.mark.parametrize("action", ["endpoint", "middle", "space", "zero", "limit"])
def test_invalid_junction_insertion_and_pan_leave_document_untouched(action):
    output = connection_scenario("""
      const action='""" + action + """',edge=doc.edges[0];
      if(action==='zero')edgePoints=()=>[[30,30],[30,30]];
      if(action==='limit')edgePoints=()=>Array.from({length:205},(_,i)=>[i,0]);
      const points=edgePoints(edge);
      const point=action==='endpoint'?points[0]:along(points,.01).point;
      mode='junction';spaceDown=action==='space';results.push(snapshot());
      const hit={dataset:{kind:'edge',id:edge.id}};
      listeners.get('diagram:pointerdown')({button:action==='middle'?1:0,pointerId:1,
        point,clientX:100,clientY:100,target:{closest:()=>hit},preventDefault(){}});
      results.push(snapshot(),drag?.kind||null);
    """)
    before, after, drag = output["results"]
    assert before == after
    assert drag == ("pan" if action in {"middle", "space"} else None)
    assert output["saves"] == output["refreshes"] == 0


def test_junction_tool_blank_placement_and_sidebar_midpoint_still_work():
    output = connection_scenario("""
      mode='junction';$('snap').checked=true;results.push(snapshot());
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,
        point:[53,77],target:{closest:()=>null},preventDefault(){}});
      results.push(snapshot());
      const edge=doc.edges[0],midpoint=along(edgePoints(edge),.5).point;
      splitEdge(edge);results.push(snapshot(),midpoint);
    """)
    before, placed, split, midpoint = output["results"]
    assert placed["mode"] == split["mode"] == "select"
    assert len(placed["doc"]["edges"]) == len(before["doc"]["edges"])
    assert len(placed["doc"]["junctions"]) == len(before["doc"]["junctions"]) + 1
    assert placed["doc"]["junctions"][-1] == {
        "id": placed["selection"]["id"], "x": 50, "y": 80}
    junction = split["doc"]["junctions"][-1]
    assert [junction["x"], junction["y"]] == midpoint
    assert len(split["undo"]) == output["saves"] == 2


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_junction_hover_preview_matches_inserted_point_without_edit(name):
    output = connection_scenario("""
      const edge=doc.edges[0],location=along(edgePoints(edge),.27);
      const point=location.point.map((v,i)=>v+location.direction[1-i]*(i?-2:2));
      mode='junction';setSelection('node',doc.nodes[0].id);results.push(snapshot());
      hoverPipe(edge,point);results.push(structuredClone(junctionPreview),feedback());
      results.push(snapshot());
      const hit={dataset:{kind:'edge',id:edge.id}};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point,
        target:{closest:()=>hit},preventDefault(){}});
      results.push(snapshot(),junctionPreview);
    """, load_template(name))
    before, preview, hint, hovered, after, cleared = output["results"]
    assert before == hovered and preview["error"] == ""
    assert hint["classes"]["junction-valid-hint"]
    assert "点击插入三通" in hint["text"]
    assert hint["target"] is None  # Does not activate pipe connection preview.
    junction = after["doc"]["junctions"][-1]
    assert [junction["x"], junction["y"]] == preview["point"]
    assert cleared is None
    assert len(after["undo"]) == output["saves"] == output["refreshes"] == 1


@pytest.mark.parametrize("failure", ["endpoint", "zero", "limit"])
def test_junction_hover_rejects_invalid_split_before_click(failure):
    output = connection_scenario("""
      const edge=doc.edges[0],failure='""" + failure + """';
      if(failure==='zero')edgePoints=()=>[[30,30],[30,30]];
      if(failure==='limit')edgePoints=()=>Array.from({length:205},(_,i)=>[i,0]);
      const points=edgePoints(edge);
      const point=failure==='endpoint'?points[0]:along(points,.01).point;
      mode='junction';results.push(snapshot());hoverPipe(edge,point);
      results.push(structuredClone(junctionPreview),feedback(),snapshot());
      const hit={dataset:{kind:'edge',id:edge.id}};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point,
        target:{closest:()=>hit},preventDefault(){}});
      results.push(structuredClone(junctionPreview),snapshot());
    """)
    before, preview, hint, hovered, clicked, after = output["results"]
    assert preview["error"] and clicked == preview
    assert hint["text"] == "不可插入：" + preview["error"]
    assert hint["classes"]["junction-invalid-hint"]
    assert not hint["classes"]["junction-valid-hint"]
    assert before == hovered == after
    assert output["messages"] == [preview["error"]]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("action", ["blank", "node", "leave", "tool", "zoom",
                                    "fit", "resize", "pan", "revision"])
def test_junction_preview_clears_when_target_or_view_changes(action):
    actions = {
        "blank": "hoverPipe(null,[999,999]);",
        "node": "hoverPipe(doc.nodes[0],[999,999],'node');",
        "leave": "listeners.get('diagram:pointerleave')();",
        "tool": "setTool('select');renderHint();",
        "zoom": "zoom(.85);",
        "fit": "fit();",
        "resize": "observers.find(item=>item.target===svg).callback();",
        "pan": """startPan({pointerId:1,clientX:100,clientY:100,preventDefault(){}});
          listeners.get('diagram:pointerup')({pointerId:1});""",
        "revision": "revision++;renderHint();",
    }
    output = connection_scenario("""
      const edge=doc.edges[0],point=along(edgePoints(edge),.3).point;
      mode='junction';svg.clientWidth=1000;svg.clientHeight=800;updateView=()=>{};
      results.push(snapshot());hoverPipe(edge,point);
      results.push(structuredClone(junctionPreview));
    """ + actions[action] + """
      results.push(junctionPreview,feedback(),snapshot());
    """)
    before, preview, cleared, hint, after = output["results"]
    assert preview is not None and cleared is None
    assert not any(hint["classes"].values())
    for key in ["doc", "selection", "multiSelection", "undo", "redo", "dirty",
                "ownedDraft", "pendingPort", "reconnect"]:
        assert after[key] == before[key]
    assert output["saves"] == output["refreshes"] == 0


def test_junction_hover_redraws_only_for_changed_preview_and_never_while_panning():
    output = connection_scenario("""
      const edge=doc.edges[0],point=along(edgePoints(edge),.3).point;
      mode='junction';let renders=0;
      renderCanvas=()=>{renders++;renderHint();};
      hoverPipe(null,[999,999]);hoverPipe(null,[888,888]);results.push(renders);
      hoverPipe(edge,point);hoverPipe(edge,point);results.push(renders);
      spaceDown=true;hoverPipe(edge,point);results.push(junctionPreview,renders);
      spaceDown=false;mode='select';hoverPipe(edge,point);
      results.push(junctionPreview,renders);
    """)
    assert output["results"] == [0, 1, None, 2, None, 2]
    assert output["saves"] == 0


@pytest.mark.parametrize("invalid", [False, True])
def test_junction_candidate_and_marker_render_with_matching_feedback(invalid):
    output = connection_scenario("""
      doc.labels=[];const edge=doc.edges[0],points=edgePoints(edge);
      mode='junction';hoverPipe(edge,""" + (
        "points[0]" if invalid else "along(points,.27).point") + """);
      const shapes=[];shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {};};
      svg.replaceChildren=()=>{shapes.length=0;};renderVertices=()=>{};updateView=()=>{};
      actualRenderCanvas();results.push(structuredClone(shapes),junctionPreview);
      setTool('select');actualRenderCanvas();results.push(structuredClone(shapes));
    """)
    active, preview, cleared = output["results"]
    suffix = " invalid" if invalid else ""
    candidate = next(shape for shape in active if shape.get("class") ==
                     "edge junction-candidate" + suffix)
    assert candidate["data-id"] == preview["edgeId"]
    marker = next(shape for shape in active if shape.get("class") ==
                  "junction-preview" + suffix)
    assert [marker["cx"], marker["cy"]] == preview["point"]
    assert marker["pointer-events"] == "none"
    assert not any("junction-preview" in shape.get("class", "") or
                   "junction-candidate" in shape.get("class", "") for shape in cleared)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_shift_insert_starts_branch_then_commits_and_undoes_in_two_steps(name):
    output = connection_scenario("""
      const edge=doc.edges[0],point=along(edgePoints(edge),.27).point;
      doc.junctions.push({id:'branch-target',x:1500,y:1200});
      mode='junction';results.push(snapshot());
      const hit={dataset:{kind:'edge',id:edge.id}};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,point,shiftKey:true,
        target:{closest:()=>hit},preventDefault(){}});
      results.push(snapshot());click(pendingPort);results.push(snapshot());
      click({junctionId:'branch-target'});results.push(snapshot());
      history('undo');results.push(snapshot());history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());history('redo');results.push(snapshot());
    """, load_template(name))
    before, inserted, invalid, connected, unconnected, original, resplit, redone = (
        output["results"])
    junction = inserted["doc"]["junctions"][-1]
    ref = {"junctionId": junction["id"]}
    assert inserted["mode"] == "connect" and inserted["pendingPort"] == ref
    assert inserted["previewTarget"]["point"] == [junction["x"], junction["y"]]
    assert len(inserted["undo"]) == 1 and invalid == inserted
    assert "同一位置" in output["messages"][2]
    assert connected["doc"]["edges"][-1]["source"] == ref
    assert connected["doc"]["edges"][-1]["target"] == {"junctionId": "branch-target"}
    assert connected["pendingPort"] is None and len(connected["undo"]) == 2
    assert unconnected["doc"] == resplit["doc"] == inserted["doc"]
    assert original["doc"] == before["doc"] and redone["doc"] == connected["doc"]
    for state in [original, resplit, redone]:
        assert state["pendingPort"] is None  # History never restarts a branch.
    assert output["saves"] == output["refreshes"] == 6
    validate_scene(connected["doc"])


@pytest.mark.parametrize("source", ["insert", "existing"])
def test_cancel_branch_keeps_junction_and_begin_existing_branch_does_not_edit(source):
    output = connection_scenario("""
      const source='""" + source + """';
      doc.junctions.push({id:'existing-branch',x:1000,y:1000});results.push(snapshot());
      if(source==='insert')splitEdge(doc.edges[0],.31,true);
      else beginBranch('existing-branch');
      results.push(snapshot());svg.matches=()=>false;
      await listeners.get('window:keydown')({key:'Escape',target:svg,
        preventDefault(){}});results.push(snapshot());
    """)
    before, started, cancelled = output["results"]
    assert started["pendingPort"] is not None and started["mode"] == "connect"
    assert cancelled["doc"] == started["doc"] and cancelled["mode"] == "select"
    assert cancelled["pendingPort"] is None and cancelled["previewTarget"] is None
    assert cancelled["undo"] == started["undo"]
    if source == "existing":
        assert before["doc"] == started["doc"]
    assert output["saves"] == output["refreshes"] == (1 if source == "insert" else 0)


@pytest.mark.parametrize("busy", ["connect", "reconnect", "placement", "pending",
                                  "drag", "space", "layout", "missing"])
def test_branch_entry_rejects_busy_or_missing_target_without_edit(busy):
    setup = {
        "connect": "mode='connect';",
        "reconnect": "mode='reconnect';reconnect={edgeId:doc.edges[0].id};",
        "placement": "placement='compressor';",
        "pending": "pendingPort=doc.edges[0].source;",
        "drag": "drag={kind:'pan'};",
        "space": "spaceDown=true;",
        "layout": "pageLayoutBusy=true;",
        "missing": "",
    }
    output = connection_scenario("""
      doc.junctions.push({id:'branch-start',x:1000,y:1000});
    """ + setup[busy] + """
      results.push(snapshot());
    """ + ("" if busy == "missing" else "splitEdge(doc.edges[0],.5,true);") + """
      beginBranch('""" + ("missing" if busy == "missing" else "branch-start") + """');
      results.push(snapshot());
    """)
    assert output["results"][0] == output["results"][1]
    assert output["messages"] and output["saves"] == output["refreshes"] == 0


def test_inspector_branch_buttons_start_at_midpoint_or_existing_junction():
    output = connection_scenario("""
      const buttons=[];
      renderObjectList=()=>{};html=()=>({append(){}});
      $('inspector').replaceChildren=()=>{};$('inspector').append=()=>{};
      field=()=>{};coordinateFields=()=>{};
      renderPipeActions=()=>{};connectedSelectionButton=()=>{};
      inspectorButton=(root,caption,click)=>{
        const button={caption,click};buttons.push(button);return button;};
      const edge=doc.edges[0],midpoint=along(edgePoints(edge),.5).point;
      setSelection('edge',edge.id);renderInspector();
      const insert=buttons.find(b=>b.caption==='插入三通并接出支路');
      results.push(insert.disabled);insert.click();results.push(snapshot(),midpoint);
      setTool('select');buttons.length=0;renderInspector();
      const existing=buttons.find(b=>b.caption==='从此三通接出支路');
      results.push(existing.disabled);existing.click();results.push(snapshot());
      buttons.length=0;renderInspector();
      results.push(buttons.find(b=>b.caption==='从此三通接出支路').disabled);
    """)
    disabled, inserted, midpoint, existing_disabled, resumed, active_disabled = (
        output["results"])
    assert not disabled and not existing_disabled and active_disabled
    junction = inserted["doc"]["junctions"][-1]
    assert [junction["x"], junction["y"]] == midpoint
    assert resumed["pendingPort"] == inserted["pendingPort"] == {
        "junctionId": junction["id"]}
    assert resumed["doc"] == inserted["doc"] and len(resumed["undo"]) == 1
    assert output["saves"] == output["refreshes"] == 1


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("side", ["source", "target"])
def test_shift_reconnect_to_pipe_preserves_pipe_identity_and_undoes_once(name, side):
    document = load_template(name)
    target, editing = document["edges"][:2]
    editing.update(vertices=[[1300, 1100], [1400, 1100]], color="#123456",
                   width=2.3, linestyle="dashed", headAt=[.2, .7])
    for edge in [target, editing]:
        for at in [.2, .8]:
            document["labels"].append(dict(id=f"label-{edge['id']}-{at}",
                                          text="state", edgeId=edge["id"], at=at,
                                          x=11, y=-13, size=12, ha="center",
                                          boxed=True, color="#123456"))
    output = connection_scenario(PIPE_END_EVENTS + """
      const target=doc.edges[0],editing=doc.edges[1],side='""" + side + """';
      const point=along(edgePoints(target),.37).point;
      setSelection('edge',editing.id);beginReconnect(editing,side);
      results.push(snapshot());hoverEnd(target,point);
      results.push(feedback(),snapshot());clickEnd(target,point);
      results.push(snapshot());history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());
    """, document)
    before, feedback, hovered, connected, undone, redone = output["results"]
    assert feedback["target"]["pipeId"] == target["id"]
    assert feedback["target"]["error"] == ""
    assert "重接" in feedback["text"]
    assert {k: v for k, v in before.items() if k != "previewTarget"} == {
        k: v for k, v in hovered.items() if k != "previewTarget"}
    after = connected["doc"]
    assert len(after["edges"]) == len(before["doc"]["edges"]) + 1
    assert len(after["junctions"]) == len(before["doc"]["junctions"]) + 1
    changed = next(e for e in after["edges"] if e["id"] == editing["id"])
    junction = after["junctions"][-1]
    assert changed == dict(editing, **{side: {"junctionId": junction["id"]}})
    assert [junction["x"], junction["y"]] == pytest.approx(feedback["target"]["point"])
    assert connected["mode"] == "select" and connected["reconnect"] is None
    assert connected["selection"] == dict(kind="edge", id=editing["id"])
    assert len(connected["undo"]) == 1
    assert undone["doc"] == before["doc"] and redone["doc"] == after
    assert undone["reconnect"] is redone["reconnect"] is None
    assert output["saves"] == output["refreshes"] == 3
    old_scene, new_scene = resolve_scene(before["doc"]), resolve_scene(after)
    old_positions = {label["id"]: label["position"] for label in old_scene["labels"]}
    for label in new_scene["labels"]:
        if label["id"].startswith(f"label-{target['id']}-"):
            assert label["position"] == pytest.approx(old_positions[label["id"]])
    assert [label for label in after["labels"] if label.get("edgeId") == editing["id"]
            ] == [label for label in document["labels"]
                  if label.get("edgeId") == editing["id"]]
    assert export_scene(after, "svg").startswith(b"<?xml")


RECONNECT_PIPE_SCENE = """
  const base=doc.edges[0];doc.nodes=[];doc.labels=[];
  doc.junctions=[{id:'a',x:0,y:0},{id:'b',x:100,y:0},
    {id:'c',x:50,y:100},{id:'d',x:150,y:100},{id:'retry',x:400,y:300}];
  doc.edges=[{...base,id:'pipe',source:{junctionId:'a'},
    target:{junctionId:'b'},vertices:[]},
    {...base,id:'editing',source:{junctionId:'c'},
    target:{junctionId:'d'},vertices:[]}];
  const target=doc.edges[0],editing=doc.edges[1];
"""


@pytest.mark.parametrize("side", ["source", "target"])
@pytest.mark.parametrize("failure", ["self", "same-point", "duplicate", "endpoint",
                                     "edge-limit", "junction-limit"])
def test_shift_reconnect_invalid_pipe_preserves_session_and_can_retry(side, failure):
    setup = {
        "self": "hit=editing;point=[100,100];",
        "same-point": ("const other=side==='source'?3:2;"
                       "doc.junctions[other].x=50;doc.junctions[other].y=0;"),
        "duplicate": "editing[side==='source'?'target':'source']={junctionId:'a'};",
        "endpoint": "point=[0,0];",
        "edge-limit": ("while(doc.edges.length<2000)doc.edges.push("
                       "{...target,id:'e'+doc.edges.length});"),
        "junction-limit": ("while(doc.junctions.length<2000)doc.junctions.push("
                           "{id:'j'+doc.junctions.length,x:999,y:999});"),
    }
    output = connection_scenario(PIPE_END_EVENTS + RECONNECT_PIPE_SCENE + """
      const side='""" + side + """';let hit=target,point=[50,0];
    """ + setup[failure] + """
      setSelection('edge',editing.id);beginReconnect(editing,side);
      redo=[{future:true}];ownedDraft='saved';results.push(snapshot());
      hoverEnd(hit,point);results.push(feedback());clickEnd(hit,point);
      results.push(snapshot());
      // Remove synthetic limit fixtures and retry the retained session.
      doc.edges.splice(2);doc.junctions=doc.junctions.slice(0,5);
      click({junctionId:'retry'});results.push(snapshot());
    """)
    before, feedback, rejected, retried = output["results"]
    assert feedback["target"]["error"]
    assert feedback["classes"]["connection-invalid-hint"]
    if failure == "self":
        assert "自身" in feedback["text"]
    assert {k: v for k, v in before.items() if k != "previewTarget"} == {
        k: v for k, v in rejected.items() if k != "previewTarget"}
    assert rejected["reconnect"] == before["reconnect"]
    assert retried["reconnect"] is None and len(retried["undo"]) == 1
    assert output["saves"] == output["refreshes"] == 1


@pytest.mark.parametrize("action", ["escape", "shift-up", "leave", "zoom", "pan",
                                    "blur"])
def test_reconnect_pipe_preview_cleanup_never_splits_or_changes_original(action):
    cleanup = {
        "escape": ("svg.matches=()=>false;await listeners.get('window:keydown')("
                   "{key:'Escape',target:svg,preventDefault(){}});"),
        "shift-up": "listeners.get('window:keyup')({key:'Shift'});",
        "leave": "listeners.get('diagram:pointerleave')();",
        "zoom": "updateView=()=>{};zoom(.9);",
        "pan": "startPan(pipeEvent(target,[50,0]));",
        "blur": "listeners.get('window:blur')();",
    }
    output = connection_scenario(PIPE_END_EVENTS + RECONNECT_PIPE_SCENE + """
      beginReconnect(editing,'target');results.push(snapshot());
      hoverEnd(target,[50,0]);results.push(feedback());
    """ + cleanup[action] + """
      results.push(snapshot());
    """)
    before, feedback, after = output["results"]
    assert "重接终点" in feedback["text"]
    assert after["previewTarget"] is None
    assert after["doc"] == before["doc"] and after["undo"] == before["undo"]
    assert after["reconnect"] == (None if action == "escape" else before["reconnect"])
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("side", ["source", "target"])
def test_reconnect_shift_prefers_existing_junction_and_preserves_clicked_pipe(side):
    output = connection_scenario(PIPE_END_EVENTS + RECONNECT_PIPE_SCENE + """
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});
      doc.junctions.push({id:'near',x:50,y:0});
      beginReconnect(editing,'""" + side + """');results.push(snapshot());
      hoverEnd(target,[60,0]);results.push(feedback());
      clickEnd(target,[60,0]);results.push(snapshot());
    """)
    before, feedback, after = output["results"]
    assert feedback["target"]["ref"] == {"junctionId": "near"}
    assert after["doc"]["junctions"] == before["doc"]["junctions"]
    assert after["doc"]["edges"][0] == before["doc"]["edges"][0]
    assert after["doc"]["edges"][1][side] == {"junctionId": "near"}
    assert output["saves"] == output["refreshes"] == 1


def test_reconnect_pipe_accepts_1999_edges_and_rechecks_after_hover():
    output = connection_scenario(PIPE_END_EVENTS + RECONNECT_PIPE_SCENE + """
      while(doc.edges.length<1999)doc.edges.push({...target,id:'e'+doc.edges.length});
      beginReconnect(editing,'source');hoverEnd(target,[50,0]);
      results.push(feedback());
      doc.junctions[0].y=10;doc.junctions[1].y=10;revision++;
      clickEnd(target,[50,0]);results.push(snapshot());
    """)
    feedback, after = output["results"]
    assert not feedback["target"]["error"]
    assert feedback["target"]["point"] == [50, 0]
    assert after["doc"]["junctions"][-1]["y"] == 10
    assert len(after["doc"]["edges"]) == 2000
    assert output["saves"] == output["refreshes"] == 1


WAYPOINT_EVENTS = """
  $('snap').checked=false;
  const waypoint=(point,options={})=>listeners.get('diagram:pointerdown')({
    button:0,pointerId:1,point,altKey:true,clientX:10,clientY:10,
    target:{closest:()=>null},preventDefault(){},...options});
  svg.matches=()=>false;
  const routeKey=(key,options={})=>listeners.get('window:keydown')({
    key,target:svg,preventDefault(){},...options});
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_new_connection_manual_waypoints_commit_once_and_export(name):
    output = connection_scenario(WAYPOINT_EVENTS + """
      const edge=doc.edges[0];mode='connect';click(edge.source);
      results.push(snapshot());waypoint([85,85]);waypoint([85,95]);
      results.push(snapshot());click(edge.target);results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """, load_template(name))
    before, pending, after, undone, redone = output["results"]
    assert pending["connectionVertices"] == [[85, 85], [85, 95]]
    for key in ["doc", "undo", "redo", "dirty", "revision", "ownedDraft"]:
        assert pending[key] == before[key]
    assert after["doc"]["edges"][-1]["vertices"] == [[85, 85], [85, 95]]
    assert after["connectionVertices"] == [] and after["pendingPort"] is None
    assert len(after["undo"]) == 1 and undone["doc"] == before["doc"]
    assert redone["doc"] == after["doc"]
    assert output["saves"] == output["refreshes"] == 3
    validate_scene(after["doc"])
    assert export_scene(after["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("scale", [.2, .5, 1, 3])
@pytest.mark.parametrize("snap", [False, True])
def test_waypoints_use_world_coordinates_and_grid_preference(scale, snap):
    output = connection_scenario(WAYPOINT_EVENTS + """
      svg.getScreenCTM=()=>({a:""" + str(scale) + """,b:0,c:0,d:"""
                                 + str(scale) + """});
      $('snap').checked=""" + str(snap).lower() + """;
      mode='connect';click(doc.edges[0].source);waypoint([2083,2097]);
      results.push(snapshot(),drag);
    """)
    state, drag = output["results"]
    assert state["connectionVertices"] == (
        [[2080, 2100]] if snap else [[2083, 2097]])
    assert drag is None and output["saves"] == 0


@pytest.mark.parametrize("action", ["escape", "tool", "history", "new-source",
                                    "reconnect", "clear-ports"])
def test_temporary_waypoints_clear_with_connection_session(action):
    cleanup = {
        "escape": "await routeKey('Escape');",
        "tool": "setTool('select');",
        "history": "undo=[structuredClone(doc)];history('undo');",
        "new-source": "pendingPort=null;click(doc.edges[0].target);",
        "reconnect": "beginReconnect(doc.edges[0],'target');",
        "clear-ports": "actions['clear-ports']();",
    }
    output = connection_scenario(WAYPOINT_EVENTS + """
      mode='connect';click(doc.edges[0].source);waypoint([85,85]);
      results.push(snapshot());
    """ + cleanup[action] + """results.push(snapshot());""")
    before, after = output["results"]
    assert before["connectionVertices"] == [[85, 85]]
    assert after["connectionVertices"] == []
    assert after["doc"] == before["doc"]
    assert output["saves"] == (1 if action == "history" else 0)


@pytest.mark.parametrize("action", ["leave", "zoom", "pan", "blur"])
def test_fixed_waypoints_survive_view_changes_without_saving(action):
    cleanup = {
        "leave": "listeners.get('diagram:pointerleave')();",
        "zoom": "updateView=()=>{};zoom(.9);",
        "pan": "startPan({clientX:0,clientY:0,pointerId:1,preventDefault(){}});",
        "blur": "listeners.get('window:blur')();",
    }
    output = connection_scenario(WAYPOINT_EVENTS + """
      mode='connect';click(doc.edges[0].source);waypoint([85,85]);
      results.push(snapshot());
    """ + cleanup[action] + """results.push(snapshot());""")
    before, after = output["results"]
    assert after["connectionVertices"] == before["connectionVertices"] == [[85, 85]]
    assert after["pendingPort"] == before["pendingPort"]
    assert after["doc"] == before["doc"] and output["saves"] == 0


@pytest.mark.parametrize("key", ["Backspace", "Delete"])
def test_connection_keys_do_not_delete_selected_object(key):
    output = connection_scenario(WAYPOINT_EVENTS + """
      setSelection('node',doc.nodes[0].id);mode='connect';click(doc.edges[0].source);
      results.push(snapshot());waypoint([85,85]);waypoint([95,85]);
      await routeKey('""" + key + """');results.push(snapshot());
      await routeKey('Backspace');await routeKey('Backspace');
      await routeKey('Backspace');results.push(snapshot());
    """)
    before, popped, empty = output["results"]
    assert len(popped["connectionVertices"]) == (1 if key == "Backspace" else 2)
    assert empty["connectionVertices"] == []
    assert empty["pendingPort"] == before["pendingPort"]
    assert before["doc"] == popped["doc"] == empty["doc"]
    assert output["saves"] == 0


@pytest.mark.parametrize("failure", ["duplicate", "limit", "coordinate"])
def test_invalid_waypoints_leave_session_and_history_unchanged(failure):
    bad = {
        "duplicate": "waypoint([85,85]);",
        "limit": "connectionVertices=Array.from({length:100},(_,i)=>[i,85]);",
        "coordinate": "",
    }
    target = "[100001,0]" if failure == "coordinate" else "[85,85]"
    output = connection_scenario(WAYPOINT_EVENTS + """
      mode='connect';click(doc.edges[0].source);
    """ + bad[failure] + """results.push(snapshot());
      waypoint(""" + target + """);results.push(snapshot());
    """)
    assert output["results"][0] == output["results"][1]
    assert output["messages"][-1] and output["saves"] == 0


@pytest.mark.parametrize("start_pipe", [False, True])
def test_waypoints_finish_to_pipe_atomically_and_undo_redo(start_pipe):
    output = connection_scenario(PIPE_SNAP_SCENE + WAYPOINT_EVENTS + """
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});
      mode='connect';
    """ + ("clickNear([300,0],true);" if start_pipe else
               "click({junctionId:'origin'});") + """
      results.push(snapshot());waypoint([250,150]);waypoint([700,150]);
      clickNear([800,0],true);results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """)
    before, after, undone, redone = output["results"]
    assert after["doc"]["edges"][-1]["vertices"] == [[250, 150], [700, 150]]
    assert len(after["doc"]["edges"]) == len(before["doc"]["edges"]) + 2
    assert after["connectionVertices"] == [] and undone["doc"] == before["doc"]
    assert redone["doc"] == after["doc"]
    assert output["saves"] == 3 + int(start_pipe)
    validate_scene(after["doc"])


def test_waypoints_invalidate_duplicate_hover_cache_and_keep_rejected_route():
    output = connection_scenario(WAYPOINT_EVENTS + """
      const edge=doc.edges[0];edge.vertices=[];mode='connect';click(edge.source);
      hover(edge.target);results.push(feedback());waypoint([85,85]);
      hover(edge.target);results.push(feedback());
      await routeKey('Backspace');hover(edge.target);results.push(feedback());
      waypoint([85,85]);click(edge.source);results.push(snapshot());
      click(edge.target);results.push(snapshot());
    """)
    duplicate, valid, duplicate_again, rejected, after = output["results"]
    assert duplicate["target"]["error"] and duplicate_again["target"]["error"]
    assert not valid["target"]["error"]
    assert rejected["connectionVertices"] == [[85, 85]]
    assert len(after["undo"]) == 1 and output["saves"] == 1


def test_waypoint_render_is_temporary_and_matches_committed_route():
    output = connection_scenario(WAYPOINT_EVENTS + """
      const edge=doc.edges[0];doc.labels=[];mode='connect';click(edge.source);
      waypoint([85,85]);waypoint([95,85]);hover(edge.target);
      const expected=route(endpoint(edge.source,currentNodes(),doc.junctions),
        endpoint(edge.target,currentNodes(),doc.junctions),connectionVertices);
      const shapes=[];shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {};};
      svg.replaceChildren=()=>{shapes.length=0;};renderVertices=()=>{};updateView=()=>{};
      actualRenderCanvas();results.push(structuredClone(shapes),expected);
      click(edge.target);actualRenderCanvas();results.push(structuredClone(shapes));
    """)
    active, expected, completed = output["results"]
    markers = [s for s in active if s.get("class") == "connection-waypoint"]
    assert len(markers) == 2
    assert all(s["vector-effect"] == "non-scaling-stroke" for s in markers)
    preview = next(s for s in active if s.get("class") == "connection-preview")
    assert preview["points"] == " ".join(",".join(map(str, p)) for p in expected)
    assert not any(s.get("class") == "connection-waypoint" for s in completed)


@pytest.mark.parametrize("guard", ["node", "label", "middle", "space", "no-start",
                                    "ordinary", "busy", "shift", "control"])
def test_waypoint_gesture_respects_other_targets_and_pan_priority(guard):
    output = connection_scenario(WAYPOINT_EVENTS + """
      mode='connect';click(doc.edges[0].source);const guard='""" + guard + """';
      if(guard==='no-start')pendingPort=null;
      if(guard==='space')spaceDown=true;if(guard==='busy')pageLayoutBusy=true;
      const options={};
      if(['node','label'].includes(guard))options.target={closest:()=>({dataset:{kind:guard}})};
      if(guard==='middle')options.button=1;if(guard==='ordinary')options.altKey=false;
      if(guard==='shift')options.shiftKey=true;if(guard==='control')options.ctrlKey=true;
      results.push(snapshot());waypoint([2000,2000],options);
      results.push(snapshot(),drag?.kind||null);
    """)
    before, after, drag = output["results"]
    assert before["doc"] == after["doc"] and after["connectionVertices"] == []
    assert output["saves"] == 0
    if guard in {"middle", "space", "no-start", "ordinary", "busy", "shift", "control"}:
        assert drag == "pan"


@pytest.mark.parametrize("guard", ["input", "repeat", "control", "composing"])
def test_waypoint_backspace_respects_text_input_and_key_modifiers(guard):
    output = connection_scenario(WAYPOINT_EVENTS + """
      mode='connect';click(doc.edges[0].source);waypoint([85,85]);
      const guard='""" + guard + """',options={};
      if(guard==='input')options.target={matches:()=>true};
      if(guard==='repeat')options.repeat=true;if(guard==='control')options.ctrlKey=true;
      if(guard==='composing')options.isComposing=true;
      results.push(snapshot());await routeKey('Backspace',options);
      results.push(snapshot());
    """)
    assert output["results"][0] == output["results"][1]
    assert output["saves"] == 0


WAYPOINT_DRAG_EVENTS = WAYPOINT_EVENTS + """
  const vertexEvent=(index,options={})=>{const hit={dataset:{
    kind:'connection-vertex',index:String(index),
    point:JSON.stringify(connectionVertices[index])}};return {button:0,pointerId:31,
    point:[...(connectionVertices[index]||[0,0])],
    target:{closest:()=>hit},preventDefault(){},...options};};
  const vertexDown=(index,options={})=>listeners.get('diagram:pointerdown')(
    vertexEvent(index,options));
  const vertexMove=(point,options={})=>listeners.get('diagram:pointermove')({
    point,pointerId:31,target:{closest:()=>null},...options});
  const vertexUp=(options={})=>listeners.get('diagram:pointerup')(
    {pointerId:31,...options});
  const setupVertices=()=>{mode='connect';click(doc.edges[0].source);
    waypoint([2000,2000]);waypoint([2200,2200]);waypoint([2400,2400]);};
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_pending_waypoint_drag_commit_is_one_pipe_edit_and_exports(name):
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      const edge=doc.edges[0];setupVertices();results.push(snapshot());
      vertexDown(1);vertexMove([2223,2247]);vertexUp();results.push(snapshot(),drag);
      click(edge.target);results.push(snapshot());history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());
    """, load_template(name))
    before, moved, drag, after, undone, redone = output["results"]
    assert moved["connectionVertices"] == [[2000, 2000], [2223, 2247], [2400, 2400]]
    assert moved["previewTarget"] == {"point": [2400, 2400], "direction": [0, 0]}
    for key in ["doc", "undo", "redo", "dirty", "revision", "ownedDraft"]:
        assert before[key] == moved[key]
    assert drag is None and after["connectionVertices"] == []
    assert after["doc"]["edges"][-1]["vertices"] == moved["connectionVertices"]
    assert len(after["undo"]) == 1 and undone["doc"] == before["doc"]
    assert redone["doc"] == after["doc"] and output["saves"] == 3
    validate_scene(after["doc"])
    assert export_scene(after["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("scale", [.2, .5, 1, 3])
@pytest.mark.parametrize("snap", [False, True])
def test_pending_waypoint_drag_uses_world_delta_and_grid(scale, snap):
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();$('snap').checked=""" + str(snap).lower() + """;
      svg.getScreenCTM=()=>({a:""" + str(scale) + """,b:0,c:0,d:"""
                                 + str(scale) + """});
      vertexDown(1,{point:[2203,2204]});vertexMove([2226,2251]);vertexUp();
      results.push(snapshot());
    """)
    expected = [2220, 2250] if snap else [2223, 2247]
    assert output["state"]["connectionVertices"][1] == expected
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("index", [0, 1, 2])
def test_alt_removes_arbitrary_pending_waypoint_without_saving(index):
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();results.push(snapshot());
      vertexDown(""" + str(index) + """,{altKey:true});
      results.push(snapshot(),drag);click(doc.edges[0].target);results.push(snapshot());
    """)
    before, after, drag, completed = output["results"]
    expected = before["connectionVertices"][:]
    expected.pop(index)
    assert after["connectionVertices"] == expected and drag is None
    assert after["previewTarget"] == {"point": expected[-1], "direction": [0, 0]}
    assert after["doc"] == before["doc"] and after["undo"] == before["undo"]
    assert completed["doc"]["edges"][-1]["vertices"] == expected
    assert output["saves"] == 1



@pytest.mark.parametrize("action", ["escape", "pointercancel", "lostcapture", "blur"])
def test_pending_waypoint_drag_cancel_restores_route_and_keeps_session(action):
    cancel = {
        "escape": "await routeKey('Escape');",
        "pointercancel": "listeners.get('diagram:pointercancel')({pointerId:31});",
        "lostcapture": "listeners.get('diagram:lostpointercapture')();",
        "blur": "listeners.get('window:blur')();",
    }
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();results.push(snapshot());vertexDown(1);vertexMove([2250,2270]);
    """ + cancel[action] + """results.push(snapshot(),drag);
      await routeKey('Escape');results.push(snapshot());
    """)
    before, restored, drag, canceled = output["results"]
    assert before["connectionVertices"] == restored["connectionVertices"]
    assert restored["previewTarget"] == before["previewTarget"]
    assert before["pendingPort"] == restored["pendingPort"] and drag is None
    assert restored["mode"] == "connect" and before["doc"] == restored["doc"]
    assert canceled["connectionVertices"] == [] and canceled["pendingPort"] is None
    assert output["saves"] == 0


@pytest.mark.parametrize("target", [[2000, 2000], [2400, 2400], [100001, 0]])
def test_invalid_pending_waypoint_drag_keeps_last_valid_point_and_allows_retry(target):
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();vertexDown(1);vertexMove([2250,2270]);results.push(snapshot());
      vertexMove(""" + json.dumps(target) + """);results.push(snapshot());
      vertexMove([2230,2260]);vertexUp();results.push(snapshot());
    """)
    valid, invalid, retry = output["results"]
    assert valid == invalid and output["messages"][-2]
    assert retry["connectionVertices"][1] == [2230, 2260]
    assert output["saves"] == 0


@pytest.mark.parametrize("guard", ["middle", "space", "shift", "control", "busy",
                                    "stale", "no-start", "selection"])
def test_pending_waypoint_handle_guards_and_pan_priority(guard):
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();const guard='""" + guard + """';
      const event=vertexEvent(1);if(guard==='middle')event.button=1;
      if(guard==='space')spaceDown=true;if(guard==='shift')event.shiftKey=true;
      if(guard==='control')event.ctrlKey=true;if(guard==='busy')pageLayoutBusy=true;
      if(guard==='stale')connectionVertices[1]=[2230,2230];
      if(guard==='no-start')pendingPort=null;if(guard==='selection')mode='select';
      results.push(snapshot());listeners.get('diagram:pointerdown')(event);
      results.push(snapshot(),drag?.kind||null);
    """)
    before, after, drag = output["results"]
    assert before["doc"] == after["doc"]
    assert before["connectionVertices"] == after["connectionVertices"]
    assert drag == ("pan" if guard in {"middle", "space"} else None)
    assert output["saves"] == 0


def test_pending_waypoint_ignores_foreign_pointer_and_noop_drag():
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();results.push(snapshot());vertexDown(1);
      vertexMove([2300,2300],{pointerId:32});vertexUp({pointerId:32});
      results.push(snapshot(),drag.kind);vertexUp();results.push(snapshot(),drag);
    """)
    before, foreign, kind, after, drag = output["results"]
    assert foreign["connectionVertices"] == before["connectionVertices"]
    assert kind == "connection-vertex" and drag is None
    assert after["doc"] == before["doc"] and output["saves"] == 0


def test_pending_waypoint_drag_and_remove_reset_hover_validation_cache():
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      const edge=doc.edges[0];edge.vertices=[];mode='connect';click(edge.source);
      waypoint([2000,2000]);hover(edge.target);results.push(feedback());
      vertexDown(0);vertexMove([2100,2100]);vertexUp();hover(edge.target);
      results.push(feedback());vertexDown(0,{altKey:true});hover(edge.target);
      results.push(feedback());
    """)
    initial, moved, removed = output["results"]
    assert not initial["target"]["error"] and not moved["target"]["error"]
    assert "相同走线" in removed["text"] and output["saves"] == 0


@pytest.mark.parametrize("action", ["drag-last", "noop", "remove-last", "remove-only"])
def test_pending_waypoint_edit_retains_preview_until_final_point_is_removed(action):
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();results.push(snapshot());const action='""" + action + """';
      if(action==='remove-only')connectionVertices=connectionVertices.slice(0,1);
      if(action.startsWith('remove'))vertexDown(connectionVertices.length-1,{altKey:true});
      else {vertexDown(2);if(action==='drag-last')vertexMove([2450,2470]);vertexUp();}
      results.push(snapshot());doc.labels=[];const shapes=[];
      shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {};};
      svg.replaceChildren=()=>{shapes.length=0;};renderVertices=()=>{};updateView=()=>{};
      actualRenderCanvas();results.push(shapes);
    """)
    before, after, shapes = output["results"]
    for key in ["doc", "undo", "redo", "dirty", "revision", "ownedDraft",
                "pendingPort"]:
        assert before[key] == after[key]
    previews = [shape for shape in shapes if shape.get("class") == "connection-preview"]
    if action == "remove-only":
        assert after["connectionVertices"] == [] and after["previewTarget"] is None
        assert previews == []
    else:
        assert after["previewTarget"] == {
            "point": after["connectionVertices"][-1], "direction": [0, 0]}
        assert len(previews) == 1
        assert previews[0]["points"].endswith(
            ",".join(map(str, after["connectionVertices"][-1])))
    assert output["saves"] == output["refreshes"] == 0


def test_pending_waypoint_handles_are_rendered_as_temporary_edit_targets():
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();doc.labels=[];const shapes=[];
      shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {};};
      svg.replaceChildren=()=>{shapes.length=0;};renderVertices=()=>{};updateView=()=>{};
      actualRenderCanvas();results.push(structuredClone(shapes));
      setTool('select');actualRenderCanvas();results.push(structuredClone(shapes));
    """)
    active, cleared = output["results"]
    handles = [s for s in active if s.get("data-kind") == "connection-vertex"]
    assert [h["data-index"] for h in handles] == [0, 1, 2]
    assert [json.loads(h["data-point"]) for h in handles] == [
        [2000, 2000], [2200, 2200], [2400, 2400]]
    assert not any(s.get("data-kind") == "connection-vertex" for s in cleared)


@pytest.mark.parametrize("action", ["tool", "reconnect", "clear-ports", "history"])
def test_leaving_waypoint_drag_releases_capture_and_discards_temporary_points(action):
    cleanup = {
        "tool": "setTool('select');",
        "reconnect": "beginReconnect(doc.edges[0],'target');",
        "clear-ports": "actions['clear-ports']();",
        "history": "undo=[structuredClone(doc)];history('undo');",
    }
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();let captured=false,releases=0;
      svg.setPointerCapture=()=>{captured=true;};svg.hasPointerCapture=()=>captured;
      svg.releasePointerCapture=()=>{captured=false;releases++;};
      vertexDown(1);vertexMove([2250,2270]);
    """ + cleanup[action] + """results.push(snapshot(),drag,releases);
    """)
    state, drag, releases = output["results"]
    assert state["connectionVertices"] == [] and drag is None and releases == 1
    assert output["saves"] == (1 if action == "history" else 0)


def test_pending_waypoint_cannot_be_dragged_onto_source_endpoint():
    output = connection_scenario(WAYPOINT_DRAG_EVENTS + """
      setupVertices();vertexDown(0);results.push(snapshot());
      vertexMove(endpoint(pendingPort,currentNodes(),doc.junctions).point);
      vertexUp();results.push(snapshot());
    """)
    before, after = output["results"]
    assert before["connectionVertices"] == after["connectionVertices"]
    assert output["messages"][-1] and output["saves"] == 0


def test_dragged_waypoints_finish_to_pipe_and_split_in_one_edit():
    output = connection_scenario(PIPE_SNAP_SCENE + WAYPOINT_DRAG_EVENTS + """
      svg.getScreenCTM=()=>({a:1,b:0,c:0,d:1});mode='connect';
      click({junctionId:'origin'});waypoint([250,150]);waypoint([700,150]);
      vertexDown(0);vertexMove([275,175]);vertexUp();vertexDown(1,{altKey:true});
      results.push(snapshot());clickNear([800,0],true);results.push(snapshot());
      history('undo');results.push(snapshot());
    """)
    before, after, undone = output["results"]
    assert after["doc"]["edges"][-1]["vertices"] == [[275, 175]]
    assert len(after["doc"]["edges"]) == len(before["doc"]["edges"]) + 2
    assert undone["doc"] == before["doc"] and output["saves"] == 2
    validate_scene(after["doc"])


CONNECTION_TOOLS_EVENTS = WAYPOINT_DRAG_EVENTS + """
  const toolbar=(refresh=true)=>{if(refresh)renderConnectionTools();return {
    hidden:$('connection-tools').hidden,text:$('connection-summary').textContent,
    back:$('connection-back').disabled,clear:$('connection-clear').disabled,
    cancel:$('connection-cancel').disabled};};
  const toolClick=action=>listeners.get('document:click')({target:{
    closest:selector=>selector==='[data-action]'?{dataset:{action}}:null}});
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_connection_toolbar_back_clear_and_commit_without_extra_history(name):
    output = connection_scenario(CONNECTION_TOOLS_EVENTS + """
      const edge=doc.edges[0];mode='connect';results.push(toolbar());
      click(edge.source);results.push(toolbar(),snapshot());
      waypoint([2000,2000]);waypoint([2200,2200]);results.push(toolbar());
      toolClick('connection-back');results.push(toolbar(),snapshot());
      toolClick('connection-clear');results.push(toolbar(),snapshot());
      waypoint([2300,2300]);click(edge.target);results.push(toolbar(),snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """, load_template(name))
    (inactive, active, before, two, one, popped, empty, cleared, ended, after,
     undo, redo) = output["results"]
    assert inactive["hidden"] and ended["hidden"]
    assert active == empty == dict(hidden=False, text="连线中 · 0 个临时折点",
                                   back=True, clear=True, cancel=False)
    assert two["text"] == "连线中 · 2 个临时折点" and not two["back"]
    assert one["text"] == "连线中 · 1 个临时折点" and not one["clear"]
    assert popped["connectionVertices"] == [[2000, 2000]]
    assert cleared["connectionVertices"] == [] and cleared["previewTarget"] is None
    for state in [popped, cleared]:
        for key in ["doc", "undo", "redo", "dirty", "revision", "ownedDraft",
                    "pendingPort"]:
            assert state[key] == before[key]
    assert after["doc"]["edges"][-1]["vertices"] == [[2300, 2300]]
    assert len(after["undo"]) == 1 and output["saves"] == output["refreshes"] == 3
    assert undo["doc"] == before["doc"] and redo["doc"] == after["doc"]
    validate_scene(after["doc"])


@pytest.mark.parametrize("action", ["keyboard", "connection-back", "connection-clear"])
def test_connection_toolbar_reduction_keeps_preview_and_focuses_canvas(action):
    output = connection_scenario(CONNECTION_TOOLS_EVENTS + """
      setupVertices();let focused=0;svg.focus=()=>{focused++;};
      const action='""" + action + """';
      if(action==='keyboard')await routeKey('Backspace');else toolClick(action);
      results.push(snapshot(),focused);doc.labels=[];const shapes=[];
      shape=(tag,attrs={})=>{shapes.push({tag,...attrs});return {};};
      svg.replaceChildren=()=>{shapes.length=0;};renderVertices=()=>{};updateView=()=>{};
      actualRenderCanvas();results.push(shapes);
    """)
    state, focused, shapes = output["results"]
    previews = [s for s in shapes if s.get("class") == "connection-preview"]
    assert focused == 1 and output["saves"] == output["refreshes"] == 0
    if action == "connection-clear":
        assert state["previewTarget"] is None and not previews
    else:
        assert state["connectionVertices"] == [[2000, 2000], [2200, 2200]]
        assert state["previewTarget"] == {"point": [2200, 2200], "direction": [0, 0]}
        assert len(previews) == 1 and previews[0]["points"].endswith("2200,2200")


@pytest.mark.parametrize("guard", ["drag", "placement", "reconnect", "space",
                                    "busy", "tool", "no-start"])
def test_connection_toolbar_stale_or_busy_actions_preserve_session(guard):
    output = connection_scenario(CONNECTION_TOOLS_EVENTS + """
      setupVertices();const guard='""" + guard + """';
      if(guard==='drag')vertexDown(1);if(guard==='placement')placement='compressor';
      if(guard==='reconnect')reconnect={edgeId:doc.edges[0].id,side:'target'};
      if(guard==='space')spaceDown=true;if(guard==='busy')pageLayoutBusy=true;
      if(guard==='tool')mode='select';if(guard==='no-start')pendingPort=null;
      results.push(snapshot(),toolbar());
      for(const action of ['connection-back','connection-clear','connection-cancel'])
        toolClick(action);
      results.push(snapshot(),toolbar());
    """)
    before, controls, after, final = output["results"]
    assert before == after and controls == final
    assert controls["back"] and controls["clear"] and controls["cancel"]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("action", ["connection-cancel", "escape", "tool", "reconnect",
                                    "history"])
def test_connection_toolbar_hides_on_session_exit_without_dropping_document(action):
    cleanup = {
        "connection-cancel": "toolClick('connection-cancel');",
        "escape": "await routeKey('Escape');",
        "tool": "setTool('text');",
        "reconnect": "beginReconnect(doc.edges[0],'target');",
        "history": "undo=[structuredClone(doc)];history('undo');",
    }
    output = connection_scenario(CONNECTION_TOOLS_EVENTS + """
      setupVertices();results.push(snapshot(),toolbar());
    """ + cleanup[action] + """results.push(snapshot(),toolbar());""")
    before, active, after, ended = output["results"]
    assert not active["hidden"] and ended["hidden"] and ended["text"] == ""
    assert before["doc"] == after["doc"] and after["connectionVertices"] == []
    assert after["pendingPort"] is None
    assert output["saves"] == (1 if action == "history" else 0)


def test_connection_toolbar_cancel_keeps_inserted_start_and_can_undo_it():
    output = connection_scenario(CONNECTION_TOOLS_EVENTS + """
      const edge=doc.edges[0];mode='connect';results.push(snapshot());
      const hit={dataset:{kind:'edge',id:edge.id}};
      listeners.get('diagram:pointerdown')({button:0,pointerId:1,shiftKey:true,
        point:along(edgePoints(edge),.27).point,target:{closest:()=>hit},preventDefault(){}});
      waypoint([2000,2000]);
      results.push(snapshot());toolClick('connection-cancel');results.push(snapshot(),toolbar());
      history('undo');results.push(snapshot());
    """)
    before, inserted, canceled, ended, undone = output["results"]
    assert inserted["doc"] == canceled["doc"]
    assert inserted["undo"] == canceled["undo"] and len(canceled["undo"]) == 1
    assert canceled["mode"] == "select" and canceled["connectionVertices"] == []
    assert canceled["pendingPort"] is None and ended["hidden"]
    assert undone["doc"] == before["doc"] and output["saves"] == 2


def test_connection_toolbar_updates_during_waypoint_drag_and_space_pan():
    output = connection_scenario(CONNECTION_TOOLS_EVENTS + """
      setupVertices();results.push(toolbar(false));vertexDown(1);results.push(toolbar(false));
      vertexMove([2250,2270]);vertexUp();results.push(toolbar(false));
      await routeKey(' ',{code:'Space'});results.push(toolbar(false));
      listeners.get('window:keyup')({key:' ',code:'Space'});
      results.push(toolbar(false));
      await routeKey(' ',{code:'Space'});listeners.get('window:blur')();
      results.push(toolbar(false));
    """)
    active, dragging, released, panning, restored, blurred = output["results"]
    assert active == released == restored == blurred
    assert not active["back"] and dragging["back"] and panning["back"]
    assert dragging["cancel"] and panning["cancel"] and output["saves"] == 0


COORDINATE_EVENTS = CONNECTION_TOOLS_EVENTS + """
  let focused=0;svg.focus=()=>{focused++;};
  html=(tag,text,className)=>({tag,textContent:text||'',className,children:[],
    get value(){return this._value||'';},set value(value){this._value=String(value);},
    attributes:{},handlers:new Map(),
    append(...items){this.children.push(...items);},
    setAttribute(key,value){this.attributes[key]=value;},
    addEventListener(key,fn){this.handlers.set(key,fn);},focus(){focused++;},
    scrollIntoView(){},
    checkValidity(){const n=Number(this.value);
      return this.value!==''&&Number.isFinite(n)
      &&n>=Number(this.min)&&n<=Number(this.max);},reportValidity(){}});
  $('connection-coordinate-list').replaceChildren=function(){this.children=[];};
  $('connection-coordinate-list').append=function(child){this.children.push(child);};
  $('connection-coordinate-jump').replaceChildren=function(){this.children=[];};
  $('connection-coordinate-jump').append=function(child){this.children.push(child);};
  const preview=$('connection-coordinate-preview');preview.children=[];
  preview.replaceChildren=()=>{preview.children=[];};
  preview.append=child=>preview.children.push(child);
  preview.toggleAttribute=(name,on)=>{if(name==='hidden')preview.hidden=on;};
  shape=(tag,attributes={},parent=svg)=>{
    const child={tag,attributes,children:[],handlers:new Map(),
      setAttribute(key,value){this.attributes[key]=value;},
      addEventListener(key,fn){this.handlers.set(key,fn);},
      append(item){this.children.push(item);}};
    parent.append(child);return child;};
  const dialog=$('connection-coordinates-dialog');dialog.open=false;
  dialog.showModal=()=>{dialog.open=true;};
  dialog.close=()=>{dialog.open=false;listeners.get('connection-coordinates-dialog:close')();};
  const query=document.querySelector;let otherDialog=false;
  document.querySelector=selector=>selector==='dialog[open]'
    ?(dialog.open?dialog:otherDialog?{}:null):query(selector);
  const coordinates=(index,point)=>point.forEach((v,axis)=>{
    connectionCoordinates.controls[index][axis].value=String(v);});
  const submitCoordinates=()=>listeners.get('connection-coordinate-form:submit')({
    preventDefault(){}});
  const coordinateState=()=>({open:dialog.open,session:!!connectionCoordinates,
    error:$('connection-coordinate-error').textContent,
    values:connectionCoordinates?.controls.map(row=>row.map(input=>input.value))});
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_exact_pending_coordinates_commit_once_and_export_with_grid_enabled(name):
    output = connection_scenario(COORDINATE_EVENTS + """
      const edge=doc.edges[0];setupVertices();$('snap').checked=true;
      results.push(snapshot());toolClick('connection-coordinates');
      results.push(coordinateState());coordinates(0,[2100.25,2050.75]);
      coordinates(2,[2420.125,2430.5]);results.push(snapshot());
      submitCoordinates();results.push(snapshot(),coordinateState());
      submitCoordinates();click(edge.target);results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """, load_template(name))
    (before, opened, typing, applied, closed, committed,
     undone, redone) = output["results"]
    assert opened["open"] and opened["session"] and typing == before
    assert applied["connectionVertices"] == [
        [2100.25, 2050.75], [2200, 2200], [2420.125, 2430.5]]
    for key in ["doc", "undo", "redo", "dirty", "revision", "ownedDraft",
                "pendingPort"]:
        assert applied[key] == before[key]
    assert not closed["open"] and not closed["session"]
    assert applied["previewTarget"] == {
        "point": [2420.125, 2430.5], "direction": [0, 0]}
    assert committed["doc"]["edges"][-1]["vertices"] == applied["connectionVertices"]
    assert len(committed["undo"]) == 1
    assert undone["doc"] == before["doc"] and redone["doc"] == committed["doc"]
    assert output["saves"] == output["refreshes"] == 3
    validate_scene(committed["doc"])
    assert export_scene(committed["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("invalid", ["empty", "nan", "infinity", "range",
                                      "source", "adjacent"])
def test_pending_coordinate_rejection_is_atomic_and_allows_retry(invalid):
    wrong = {
        "empty": "coordinates(1,['',2200]);",
        "nan": "coordinates(1,['wrong',2200]);",
        "infinity": "coordinates(1,['Infinity',2200]);",
        "range": "coordinates(1,[100001,2200]);",
        "source": ("coordinates(0,endpoint(pendingPort,currentNodes(),"
                   "doc.junctions).point);"),
        "adjacent": "coordinates(1,[2000,2000]);",
    }
    output = connection_scenario(COORDINATE_EVENTS + """
      setupVertices();toolClick('connection-coordinates');results.push(snapshot());
      coordinates(2,[2450.25,2470.5]);
    """ + wrong[invalid] + """
      submitCoordinates();results.push(snapshot(),coordinateState());
      coordinates(0,[2050,2070]);coordinates(1,[2250,2270]);
      submitCoordinates();results.push(snapshot(),coordinateState());
    """)
    before, rejected, error, applied, closed = output["results"]
    assert rejected == before and error["error"] and error["open"]
    assert applied["connectionVertices"] == [
        [2050, 2070], [2250, 2270], [2450.25, 2470.5]]
    assert not closed["open"] and output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("change", ["revision", "source", "vertices", "mode", "drag"])
def test_pending_coordinate_submission_does_not_overwrite_changed_session(change):
    changes = {
        "revision": "revision++;",
        "source": "pendingPort=doc.edges[0].target;",
        "vertices": "connectionVertices[1]=[2280,2290];",
        "mode": "mode='select';",
        "drag": "drag={kind:'pan'};",
    }
    output = connection_scenario(COORDINATE_EVENTS + """
      setupVertices();toolClick('connection-coordinates');coordinates(1,[2250,2270]);
    """ + changes[change] + """results.push(snapshot());submitCoordinates();
      results.push(snapshot(),coordinateState());
    """)
    before, after, dialog = output["results"]
    assert before == after and dialog["open"] and "已变化" in dialog["error"]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("action", ["cancel", "native-close", "noop"])
def test_pending_coordinates_cancel_or_unchanged_apply_keeps_original_session(action):
    output = connection_scenario(COORDINATE_EVENTS + """
      setupVertices();results.push(snapshot());toolClick('connection-coordinates');
      const action='""" + action + """';
      if(action==='noop')submitCoordinates();
      else {coordinates(1,[2250,2270]);
        if(action==='cancel')toolClick('close-connection-coordinates');
        else dialog.close();}
      results.push(snapshot(),coordinateState(),focused);
    """)
    before, after, dialog, focused = output["results"]
    assert before == after and not dialog["open"] and not dialog["session"]
    assert focused >= 2 and output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("guard", ["empty", "no-start", "drag", "space", "busy",
                                   "dialog"])
def test_pending_coordinates_open_respects_current_operation(guard):
    changes = {
        "empty": "connectionVertices=[];",
        "no-start": "pendingPort=null;",
        "drag": "drag={kind:'pan'};",
        "space": "spaceDown=true;",
        "busy": "pageLayoutBusy=true;",
        "dialog": "otherDialog=true;",
    }
    output = connection_scenario(COORDINATE_EVENTS + """
      setupVertices();
    """ + changes[guard] + """
      results.push(snapshot());toolClick('connection-coordinates');
      results.push(snapshot(),coordinateState());
    """)
    before, after, dialog = output["results"]
    assert before == after and not dialog["open"] and not dialog["session"]
    assert output["saves"] == output["refreshes"] == 0


def test_pending_coordinates_dialog_lists_all_points_and_resets_hover_cache():
    output = connection_scenario(COORDINATE_EVENTS + """
      const edge=doc.edges[0];edge.vertices=[[2100.25,2050.75]];
      mode='connect';click(edge.source);waypoint([2000,2000]);
      hover(edge.target);results.push(feedback());toolClick('connection-coordinates');
      coordinates(0,edge.vertices[0]);submitCoordinates();hover(edge.target);
      results.push(feedback());connectionVertices=Array.from({length:100},(_,i)=>[2000+i,2100]);
      toolClick('connection-coordinates');results.push(coordinateState(),
        $('connection-coordinate-list').children.length,
        connectionCoordinates.controls[99].map(input=>input.attributes['aria-label']));
      coordinates(99,[100000,-100000]);submitCoordinates();results.push(snapshot());
    """)
    initial, changed, dialog, count, labels, applied = output["results"]
    assert not initial["target"]["error"] and "相同走线" in changed["target"]["error"]
    assert dialog["open"] and count == 100 and len(dialog["values"]) == 100
    assert labels == ["折点 100 X", "折点 100 Y"]
    assert applied["connectionVertices"][-1] == [100000, -100000]
    assert output["saves"] == output["refreshes"] == 0


EDGE_COORDINATE_EVENTS = COORDINATE_EVENTS + """
  const edge=doc.edges[0];edge.vertices=[[2000,2000],[2200,2200],[2400,2400]];
  mode='select';setSelection('edge',edge.id);
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_existing_pipe_coordinates_preserve_identity_labels_and_undo_once(name):
    document = load_template(name)
    edge = document["edges"][0]
    edge.update(color="#123456", width=2.3, linestyle="dashed", headAt=[.2, .7])
    document["labels"].append(dict(id="coordinate-state", text="P", edgeId=edge["id"],
                                   at=.6, x=11, y=-13, color="#123456"))
    output = connection_scenario(EDGE_COORDINATE_EVENTS + """
      $('snap').checked=true;results.push(snapshot());showEdgeCoordinates(edge.id);
      coordinates(0,[2100.25,2050.75]);coordinates(2,[2420.125,2430.5]);
      results.push(snapshot(),coordinateState());submitCoordinates();
      results.push(snapshot(),coordinateState());history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());
    """, document)
    before, typing, opened, applied, closed, undone, redone = output["results"]
    assert typing == before and opened["open"] and not closed["session"]
    changed = applied["doc"]["edges"][0]
    assert changed == dict(before["doc"]["edges"][0], vertices=[
        [2100.25, 2050.75], [2200, 2200], [2420.125, 2430.5]])
    assert {k: v for k, v in before["doc"].items() if k != "edges"} == {
        k: v for k, v in applied["doc"].items() if k != "edges"}
    assert applied["doc"]["edges"][1:] == before["doc"]["edges"][1:]
    assert len(applied["undo"]) == 1 and applied["dirty"]
    assert applied["revision"] == before["revision"] + 1
    assert applied["multiSelection"] == before["multiSelection"]
    assert applied["view"] == before["view"]
    assert undone["doc"] == before["doc"] and redone["doc"] == applied["doc"]
    assert output["saves"] == output["refreshes"] == 3
    old_scene, new_scene = resolve_scene(before["doc"]), resolve_scene(applied["doc"])
    old_label = next(label for label in old_scene["labels"]
                     if label["id"] == "coordinate-state")
    new_label = next(label for label in new_scene["labels"]
                     if label["id"] == "coordinate-state")
    assert new_label["position"] != old_label["position"]
    validate_scene(applied["doc"])
    assert export_scene(applied["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("invalid", ["empty", "range", "source", "target",
                                      "adjacent", "duplicate"])
def test_existing_pipe_invalid_coordinates_are_atomic_and_allow_retry(invalid):
    wrong = {
        "empty": "coordinates(1,['',2200]);",
        "range": "coordinates(1,[100001,2200]);",
        "source": ("coordinates(0,endpoint(edge.source,currentNodes(),"
                   "doc.junctions).point);"),
        "target": ("coordinates(2,endpoint(edge.target,currentNodes(),"
                   "doc.junctions).point);"),
        "adjacent": "coordinates(1,[2000,2000]);",
        "duplicate": "coordinates(0,[2100.25,2050.75]);",
    }
    output = connection_scenario(EDGE_COORDINATE_EVENTS + """
      if('""" + invalid + """'==='duplicate')doc.edges.push({
        ...clone(edge),id:'parallel',
        vertices:[[2100.25,2050.75],[2200,2200],[2450.25,2470.5]]});
      showEdgeCoordinates(edge.id);results.push(snapshot());
      coordinates(2,[2450.25,2470.5]);
    """ + wrong[invalid] + """
      submitCoordinates();results.push(snapshot(),coordinateState());
      coordinates(0,[2050,2070]);coordinates(1,[2250,2270]);coordinates(2,[2450,2470]);
      submitCoordinates();results.push(snapshot(),coordinateState());
    """)
    before, rejected, error, applied, closed = output["results"]
    assert before == rejected and error["open"] and error["error"]
    assert not closed["open"] and len(applied["undo"]) == 1
    assert applied["doc"]["edges"][0]["vertices"] == [
        [2050, 2070], [2250, 2270], [2450, 2470]]
    assert output["saves"] == output["refreshes"] == 1


@pytest.mark.parametrize("change", ["revision", "selection", "deleted", "attributes",
                                     "drag"])
def test_existing_pipe_coordinates_refuse_stale_edits(change):
    changes = {
        "revision": "revision++;",
        "selection": "setSelection('edge',doc.edges[1].id);",
        "deleted": "doc.edges.shift();",
        "attributes": "edge.color='#654321';",
        "drag": "drag={kind:'pan'};",
    }
    output = connection_scenario(EDGE_COORDINATE_EVENTS + """
      showEdgeCoordinates(edge.id);coordinates(1,[2250,2270]);
    """ + changes[change] + """
      results.push(snapshot());submitCoordinates();results.push(snapshot(),coordinateState());
    """)
    before, after, dialog = output["results"]
    assert before == after and dialog["open"] and "已变化" in dialog["error"]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("action", ["cancel", "native-close", "noop"])
def test_existing_pipe_coordinates_cancel_and_noop_leave_history_untouched(action):
    output = connection_scenario(EDGE_COORDINATE_EVENTS + """
      results.push(snapshot());showEdgeCoordinates(edge.id);
      if('""" + action + """'==='noop')submitCoordinates();
      else {coordinates(1,[2250,2270]);
        if('""" + action + """'==='cancel')toolClick('close-connection-coordinates');
        else dialog.close();}
      results.push(snapshot(),coordinateState(),focused);
      setupVertices();showConnectionCoordinates();results.push(coordinateState(),
        $('connection-coordinates-heading').textContent);
    """)
    before, after, closed, focused, reopened, heading = output["results"]
    assert before == after and not closed["session"] and focused >= 2
    assert reopened["open"] and heading == "编辑临时折点坐标"
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("guard", ["missing", "multi", "mode", "drag", "dialog"])
def test_existing_pipe_coordinate_entry_respects_selection_and_operation(guard):
    changes = {
        "missing": "doc.edges.shift();",
        "multi": "setSelection('edge',doc.edges[1].id,true);",
        "mode": "mode='connect';",
        "drag": "drag={kind:'pan'};",
        "dialog": "otherDialog=true;",
    }
    output = connection_scenario(EDGE_COORDINATE_EVENTS + changes[guard] + """
      results.push(snapshot());showEdgeCoordinates(edge.id);
      results.push(snapshot(),coordinateState());
    """)
    before, after, dialog = output["results"]
    assert before == after and not dialog["session"] and not dialog["open"]
    assert output["saves"] == output["refreshes"] == 0


COORDINATE_ROWS_EVENTS = COORDINATE_EVENTS + """
  const rowAction=(index,caption)=>{
    const row=$('connection-coordinate-list').children[index];
    row.children[2].children.find(button=>button.textContent===caption)
      .handlers.get('click')();};
  const rowLabels=()=>$('connection-coordinate-list').children.map(row=>({
    legend:row.children[0].textContent,
    actions:row.children[2].children.map(button=>({
      label:button.attributes['aria-label'],type:button.type,disabled:!!button.disabled}))}));
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_empty_pipe_coordinate_form_can_insert_and_delete_before_atomic_apply(name):
    output = connection_scenario(COORDINATE_ROWS_EVENTS + """
      const edge=doc.edges[0];edge.vertices=[];mode='select';
      setSelection('edge',edge.id);results.push(snapshot());showEdgeCoordinates(edge.id);
      results.push(coordinateState());toolClick('add-coordinate-row');
      coordinates(0,[2100.25,2050.75]);rowAction(0,'在此前插入');
      coordinates(0,[2000.125,2000.5]);toolClick('add-coordinate-row');
      coordinates(2,[2300.25,2300.5]);rowAction(1,'删除此折点');
      results.push(snapshot(),coordinateState(),rowLabels());submitCoordinates();
      results.push(snapshot());history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());
    """, load_template(name))
    before, opened, editing, form, labels, applied, undone, redone = output["results"]
    assert opened["open"] and opened["values"] == []
    assert editing == before and form["values"] == [
        ["2000.125", "2000.5"], ["2300.25", "2300.5"]]
    assert [row["legend"] for row in labels] == ["折点 1", "折点 2"]
    assert labels[1]["actions"] == [
        dict(label="在折点 2 前插入", type="button", disabled=False),
        dict(label="删除折点 2", type="button", disabled=False)]
    assert applied["doc"]["edges"][0] == dict(before["doc"]["edges"][0], vertices=[
        [2000.125, 2000.5], [2300.25, 2300.5]])
    assert len(applied["undo"]) == 1
    assert undone["doc"] == before["doc"] and redone["doc"] == applied["doc"]
    assert output["saves"] == output["refreshes"] == 3
    validate_scene(applied["doc"])
    assert export_scene(applied["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("kind", ["edge", "pending"])
@pytest.mark.parametrize("action", ["cancel", "apply"])
def test_deleting_all_coordinate_rows_keeps_changes_in_form_until_applied(kind, action):
    output = connection_scenario(COORDINATE_ROWS_EVENTS + """
      const edge=doc.edges[0];
      if('""" + kind + """'==='edge'){edge.vertices=[[2000,2000]];
        mode='select';setSelection('edge',edge.id);showEdgeCoordinates(edge.id);}
      else {setupVertices();showConnectionCoordinates();}
      results.push(snapshot());while(connectionCoordinates.controls.length)
        rowAction(0,'删除此折点');results.push(snapshot(),coordinateState());
      if('""" + action + """'==='cancel')toolClick('close-connection-coordinates');
      else submitCoordinates();results.push(snapshot(),coordinateState());
    """)
    before, editing, form, after, closed = output["results"]
    assert before == editing and form["values"] == [] and not closed["open"]
    if action == "cancel":
        assert after == before and output["saves"] == 0
    elif kind == "edge":
        assert after["doc"]["edges"][0]["vertices"] == []
        assert len(after["undo"]) == output["saves"] == 1
    else:
        assert after["connectionVertices"] == [] and after["previewTarget"] is None
        assert after["doc"] == before["doc"] and after["undo"] == before["undo"]
        assert after["pendingPort"] == before["pendingPort"] and output["saves"] == 0


def test_inserted_coordinate_row_preserves_unapplied_values_and_rejects_blank():
    output = connection_scenario(COORDINATE_ROWS_EVENTS + """
      setupVertices();showConnectionCoordinates();results.push(snapshot());
      coordinates(0,[2000.125,2050.75]);coordinates(2,['',2400]);
      rowAction(1,'在此前插入');results.push(coordinateState());
      submitCoordinates();results.push(snapshot(),coordinateState());
      coordinates(1,[2100.25,2100.5]);coordinates(3,[2420.25,2420.5]);
      submitCoordinates();results.push(snapshot(),coordinateState());
    """)
    before, inserted, rejected, error, applied, closed = output["results"]
    assert inserted["values"] == [["2000.125", "2050.75"], ["", ""],
                                  ["2200", "2200"], ["", "2400"]]
    assert rejected == before and error["open"] and error["error"]
    assert applied["connectionVertices"] == [[2000.125, 2050.75], [2100.25, 2100.5],
                                              [2200, 2200], [2420.25, 2420.5]]
    assert not closed["open"] and output["saves"] == 0


def test_coordinate_row_limit_and_session_callbacks_do_not_mutate_document():
    output = connection_scenario(COORDINATE_ROWS_EVENTS + """
      setupVertices();connectionVertices=Array.from({length:100},(_,i)=>[2000+i,2100]);
      showConnectionCoordinates();results.push(snapshot());toolClick('add-coordinate-row');
      results.push(coordinateState(),$('connection-coordinate-add').disabled,rowLabels());
      rowAction(50,'删除此折点');toolClick('add-coordinate-row');coordinates(99,[3000,3100]);
      results.push(coordinateState(),snapshot());const stale=connectionCoordinates;
      dialog.close();showConnectionCoordinates();changeCoordinateRows(stale,0,true);
      results.push(coordinateState(),snapshot());
    """)
    (before, limited, disabled, labels, rebuilt, editing,
     reopened, after) = output["results"]
    assert disabled and len(limited["values"]) == 100 and "100" in limited["error"]
    assert all(row["actions"][0]["disabled"] for row in labels)
    assert len(rebuilt["values"]) == 100 and rebuilt["values"][-1] == ["3000", "3100"]
    assert reopened["values"] == [[str(2000 + i), "2100"] for i in range(100)]
    assert before == editing == after and output["saves"] == 0


def test_deleting_last_manual_point_cannot_create_duplicate_auto_route():
    output = connection_scenario(COORDINATE_ROWS_EVENTS + """
      const edge=doc.edges[0];edge.vertices=[[2000,2000]];
      doc.edges.push({...clone(edge),id:'parallel',vertices:[]});
      mode='select';setSelection('edge',edge.id);showEdgeCoordinates(edge.id);
      results.push(snapshot());rowAction(0,'删除此折点');submitCoordinates();
      results.push(snapshot(),coordinateState());toolClick('add-coordinate-row');
      coordinates(0,[2050.25,2070.5]);submitCoordinates();
      results.push(snapshot(),coordinateState());
    """)
    before, rejected, error, applied, closed = output["results"]
    assert rejected == before and error["open"] and "相同走线" in error["error"]
    assert not closed["open"] and applied["doc"]["edges"][0]["vertices"] == [
        [2050.25, 2070.5]]
    assert output["saves"] == 1


COORDINATE_PREVIEW_EVENTS = COORDINATE_ROWS_EVENTS + """
  const previewState=()=>clone({hidden:!!preview.hidden,
    caption:$('connection-coordinate-preview-status').textContent,
    shapes:preview.children.map(child=>({tag:child.tag,attributes:child.attributes}))});
  const coordinateInput=(index,point)=>{coordinates(index,point);
    connectionCoordinates.controls[index][0].handlers.get('input')();};
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_preview_matches_applied_route_without_mutating_editor(name, kind):
    output = connection_scenario(COORDINATE_PREVIEW_EVENTS + """
      const edge=doc.edges[0];
      if('""" + kind + """'==='edge'){
        edge.vertices=[[2000,2000],[2200,2200],[2400,2400]];
        mode='select';setSelection('edge',edge.id);showEdgeCoordinates(edge.id);}
      else {setupVertices();showConnectionCoordinates();}
      results.push(snapshot(),previewState());coordinateInput(1,[2250.25,2170.75]);
      results.push(snapshot(),previewState());
      const source=endpoint(edge.source,currentNodes(),doc.junctions);
      const original=connectionCoordinates.vertices;
      const target=connectionCoordinates.kind==='edge'
        ?endpoint(edge.target,currentNodes(),doc.junctions):{point:original.at(-1),direction:[0,0]};
      const old=route(source,target,original);submitCoordinates();
      const points='""" + kind + """'==='edge'?edgePoints(doc.edges[0])
        :route(source,{point:connectionVertices.at(-1),direction:[0,0]},connectionVertices);
      results.push(old,points,snapshot(),previewState());
    """, load_template(name))
    before, initial, editing, preview, old, points, after, closed = output["results"]
    assert before == editing and not initial["hidden"] and not preview["hidden"]
    all_points = old + points
    left, top = (min(point[axis] for point in all_points) for axis in [0, 1])
    width = max(point[0] for point in all_points) - left
    height = max(point[1] for point in all_points) - top
    scale = min(432 / max(width, 1), 112 / max(height, 1))
    paths = [shape for shape in preview["shapes"] if shape["tag"] == "polyline"]
    assert len(paths) == 2
    for path, raw in zip(paths, [old, points]):
        rendered = [[float(v) for v in pair.split(",")]
                    for pair in path["attributes"]["points"].split()]
        expected = [[240 + (x - left - width / 2) * scale,
                     80 + (y - top - height / 2) * scale] for x, y in raw]
        assert len(rendered) == len(expected)
        for actual, wanted in zip(rendered, expected):
            assert actual == pytest.approx(wanted)
            assert 24 - 1e-6 <= actual[0] <= 456 + 1e-6
            assert 24 - 1e-6 <= actual[1] <= 136 + 1e-6
    assert not closed["shapes"] and closed["caption"] == ""
    assert output["saves"] == (1 if kind == "edge" else 0)
    if kind == "pending":
        assert after["doc"] == before["doc"]
    else:
        assert after["dirty"]


@pytest.mark.parametrize("invalid", ["empty", "range", "source", "target",
                                      "adjacent", "duplicate", "stale"])
def test_coordinate_preview_hides_invalid_route_and_recovers_on_input(invalid):
    wrong = {
        "empty": "coordinateInput(1,['',2200]);",
        "range": "coordinateInput(1,[100001,2200]);",
        "source": ("coordinateInput(0,endpoint(edge.source,currentNodes(),"
                   "doc.junctions).point);"),
        "target": ("coordinateInput(2,endpoint(edge.target,currentNodes(),"
                   "doc.junctions).point);"),
        "adjacent": "coordinateInput(1,[2000,2000]);",
        "duplicate": "coordinateInput(1,[2250.25,2170.75]);",
        "stale": "revision++;coordinateInput(1,[2250.25,2170.75]);",
    }
    output = connection_scenario(COORDINATE_PREVIEW_EVENTS + """
      const edge=doc.edges[0];edge.vertices=[[2000,2000],[2200,2200],[2400,2400]];
      if('""" + invalid + """'==='duplicate')doc.edges.push({...clone(edge),
        id:'parallel',vertices:[[2000,2000],[2250.25,2170.75],[2400,2400]]});
      mode='select';setSelection('edge',edge.id);showEdgeCoordinates(edge.id);
    """ + wrong[invalid] + """
      results.push(snapshot(),previewState());submitCoordinates();
      results.push(snapshot(),coordinateState());
      if('""" + invalid + """'==='stale')revision--;
      coordinates(0,[2050.25,2070.5]);coordinates(2,[2450.25,2470.5]);
      coordinateInput(1,[2300.25,2300.5]);results.push(previewState());
    """)
    before, preview, after, error, recovered = output["results"]
    assert preview["hidden"] and not preview["shapes"]
    assert "暂无法预览" in preview["caption"]
    assert before == after and error["error"] and error["open"]
    assert not recovered["hidden"] and recovered["shapes"] and output["saves"] == 0


def test_coordinate_preview_updates_on_row_changes_and_ignores_closed_callbacks():
    output = connection_scenario(COORDINATE_PREVIEW_EVENTS + """
      setupVertices();showConnectionCoordinates();results.push(snapshot());
      const oldInput=connectionCoordinates.controls[0][0].handlers.get('input');
      toolClick('add-coordinate-row');results.push(previewState());
      rowAction(3,'删除此折点');results.push(previewState());
      while(connectionCoordinates.controls.length)rowAction(0,'删除此折点');
      results.push(previewState());dialog.close();oldInput();results.push(snapshot(),previewState());
    """)
    before, blank, recovered, empty, after, closed = output["results"]
    assert blank["hidden"] and not recovered["hidden"] and not empty["hidden"]
    assert "终点待选" in recovered["caption"] and "自动走线" in empty["caption"]
    assert before == after and not closed["shapes"] and closed["caption"] == ""
    assert output["saves"] == 0


def test_coordinate_preview_limits_number_labels_and_accepts_unchanged_legacy_route():
    output = connection_scenario(COORDINATE_PREVIEW_EVENTS + """
      setupVertices();connectionVertices=Array.from({length:100},(_,i)=>[2000+i,2100]);
      showConnectionCoordinates();results.push(previewState());dialog.close();
      const edge=doc.edges[0];
      edge.vertices=[endpoint(edge.source,currentNodes(),doc.junctions).point];
      mode='select';pendingPort=null;connectionVertices=[];previewTarget=null;
      setSelection('edge',edge.id);showEdgeCoordinates(edge.id);results.push(previewState(),snapshot());
      submitCoordinates();results.push(snapshot());
    """)
    many, legacy, before, after = output["results"]
    assert not many["hidden"] and not legacy["hidden"] and before == after
    assert not any(shape["tag"] == "text" for shape in many["shapes"])
    assert len([shape for shape in many["shapes"]
                if shape["attributes"].get("class") == "coordinate-waypoint"]) == 100
    assert output["saves"] == 0


def test_coordinate_preview_keeps_source_stub_for_one_close_collinear_waypoint():
    output = connection_scenario(COORDINATE_PREVIEW_EVENTS + """
      const edge=doc.edges[0];mode='connect';click(edge.source);
      const source=endpoint(pendingPort,currentNodes(),doc.junctions);
      const point=source.point.map((v,i)=>v+source.direction[i]*5);
      connectionVertices=[point];showConnectionCoordinates();
      results.push(previewState(),route(source,{point,direction:[0,0]},[point]),snapshot());
      dialog.close();results.push(snapshot());
    """)
    preview, raw, before, after = output["results"]
    assert before == after and not preview["hidden"] and len(raw) > 2
    path = next(shape for shape in preview["shapes"]
                if shape["attributes"].get("class") == "coordinate-route-proposed")
    assert len(path["attributes"]["points"].split()) == len(raw)
    assert output["saves"] == 0


COORDINATE_ORDER_EVENTS = COORDINATE_PREVIEW_EVENTS + """
  const orderButton=(index,caption)=>$('connection-coordinate-list')
    .children[index].children[3].children.find(button=>button.textContent===caption);
  const order=(index,caption)=>orderButton(index,caption).handlers.get('click')();
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_reordering_stays_transient_and_commits_once(name, kind):
    output = connection_scenario(COORDINATE_ORDER_EVENTS + """
      const edge=doc.edges[0];
      if('""" + kind + """'==='edge'){
        edge.vertices=[[2000,2000],[2200,2200],[2400,2400]];
        mode='select';setSelection('edge',edge.id);showEdgeCoordinates(edge.id);}
      else {setupVertices();showConnectionCoordinates();}
      results.push(snapshot());coordinates(1,[2250.25,2170.75]);
      order(1,'上移');order(1,'下移');
      results.push(snapshot(),coordinateState(),previewState(),rowLabels());
      submitCoordinates();if('""" + kind + """'==='pending')click(edge.target);
      results.push(snapshot());history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());
    """, load_template(name))
    before, editing, form, preview, labels, applied, undone, redone = output["results"]
    expected = [[2250.25, 2170.75], [2400, 2400], [2000, 2000]]
    assert editing == before and form["values"] == [
        ["2250.25", "2170.75"], ["2400", "2400"], ["2000", "2000"]]
    assert [row["legend"] for row in labels] == ["折点 1", "折点 2", "折点 3"]
    assert not preview["hidden"] and "预览" in preview["caption"]
    changed = applied["doc"]["edges"][0 if kind == "edge" else -1]
    assert changed["vertices"] == expected and len(applied["undo"]) == 1
    if kind == "edge":
        assert changed == dict(before["doc"]["edges"][0], vertices=expected)
        assert applied["doc"]["labels"] == before["doc"]["labels"]
    assert undone["doc"] == before["doc"] and redone["doc"] == applied["doc"]
    assert output["saves"] == output["refreshes"] == 3
    validate_scene(applied["doc"])
    assert export_scene(applied["doc"], "svg").startswith(b"<?xml")


@pytest.mark.parametrize("action", ["cancel", "native-close", "roundtrip"])
def test_coordinate_order_cancel_or_roundtrip_does_not_change_document(action):
    output = connection_scenario(COORDINATE_ORDER_EVENTS + """
      const edge=doc.edges[0];edge.vertices=[[2000,2000],[2200,2200],[2400,2400]];
      mode='select';setSelection('edge',edge.id);showEdgeCoordinates(edge.id);
      results.push(snapshot());order(1,'上移');
      if('""" + action + """'==='roundtrip'){order(0,'下移');submitCoordinates();}
      else if('""" + action + """'==='cancel')toolClick('close-connection-coordinates');
      else dialog.close();results.push(snapshot(),coordinateState());
    """)
    before, after, closed = output["results"]
    assert before == after and not closed["open"] and output["saves"] == 0


def test_coordinate_order_preserves_blank_values_and_revalidates_route():
    output = connection_scenario(COORDINATE_ORDER_EVENTS + """
      setupVertices();showConnectionCoordinates();results.push(snapshot());
      coordinates(1,['',2170.75]);order(1,'下移');
      results.push(coordinateState(),previewState());submitCoordinates();
      results.push(snapshot(),coordinateState());
      coordinateInput(2,[2250.25,2170.75]);results.push(previewState());
      submitCoordinates();results.push(snapshot());
    """)
    before, form, preview, rejected, error, recovered, applied = output["results"]
    assert form["values"] == [["2000", "2000"], ["2400", "2400"], ["", "2170.75"]]
    assert preview["hidden"] and before == rejected and error["error"]
    assert not recovered["hidden"] and output["saves"] == 0
    assert applied["connectionVertices"] == [[2000, 2000], [2400, 2400],
                                              [2250.25, 2170.75]]


@pytest.mark.parametrize("count", [0, 1, 3, 100])
def test_coordinate_order_buttons_handle_boundaries_and_point_limit(count):
    output = connection_scenario(COORDINATE_ORDER_EVENTS + """
      const edge=doc.edges[0];edge.vertices=Array.from({length:""" + str(count) + """},
        (_,i)=>[2000+i,2100+i]);mode='select';setSelection('edge',edge.id);
      showEdgeCoordinates(edge.id);results.push(snapshot(),coordinateState());
      results.push($('connection-coordinate-list').children.map((row,index)=>({
        up:!!orderButton(index,'上移').disabled,down:!!orderButton(index,'下移').disabled,
        type:orderButton(index,'上移').type,
        label:orderButton(index,'下移').attributes['aria-label']})));
      if(connectionCoordinates.controls.length){order(0,'上移');
        order(connectionCoordinates.controls.length-1,'下移');}
      results.push(snapshot(),coordinateState());
      if(connectionCoordinates.controls.length>1){order(0,'下移');
        results.push(coordinateState());}
    """)
    before, form, buttons, after, unchanged = output["results"][:5]
    assert before == after and form == unchanged and len(buttons) == count
    for index, button in enumerate(buttons):
        assert button == dict(up=index == 0, down=index == count - 1,
                              type="button", label=f"下移折点 {index + 1}")
    if count > 1:
        swapped = output["results"][5]
        assert swapped["values"][0] == form["values"][1]
        assert swapped["values"][1] == form["values"][0]
    assert output["saves"] == 0


@pytest.mark.parametrize("stale", ["rows", "closed", "session", "revision"])
def test_coordinate_order_callbacks_cannot_apply_stale_edits(stale):
    output = connection_scenario(COORDINATE_ORDER_EVENTS + """
      setupVertices();showConnectionCoordinates();
      const callback=orderButton(0,'下移').handlers.get('click');
      if('""" + stale + """'==='rows')toolClick('add-coordinate-row');
      if(['closed','session'].includes('""" + stale + """'))dialog.close();
      if('""" + stale + """'==='session')showConnectionCoordinates();
      if('""" + stale + """'==='revision')revision++;
      results.push(snapshot(),coordinateState());callback();
      if('""" + stale + """'==='revision')submitCoordinates();
      results.push(snapshot(),coordinateState());
    """)
    before, form, after, result = output["results"]
    assert before == after and output["saves"] == 0
    if stale == "revision":
        assert "已变化" in result["error"]
    else:
        assert form == result


COORDINATE_RESET_EVENTS = COORDINATE_ORDER_EVENTS + """
  const resetState=()=>({clear:$('connection-coordinate-clear').disabled,
    reset:$('connection-coordinate-reset').disabled});
  const openResetForm=kind=>{const edge=doc.edges[0];
    if(kind==='edge'){edge.vertices=[[2000,2000],[2200,2200],[2400,2400]];
      mode='select';setSelection('edge',edge.id);showEdgeCoordinates(edge.id);}
    else {setupVertices();showConnectionCoordinates();}};
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_restore_discards_unapplied_changes(name, kind):
    output = connection_scenario(COORDINATE_RESET_EVENTS + """
      openResetForm('""" + kind + """');results.push(snapshot(),resetState());
      coordinateInput(1,[2250.125,2270.75]);order(1,'上移');
      toolClick('add-coordinate-row');results.push(resetState(),previewState());
      toolClick('clear-coordinate-rows');results.push(coordinateState(),resetState());
      toolClick('reset-coordinate-rows');
      results.push(snapshot(),coordinateState(),resetState(),previewState());
      submitCoordinates();results.push(snapshot(),coordinateState());
    """, load_template(name))
    (before, initial, edited, invalid, empty, cleared, restored, form, buttons,
     preview, after, closed) = output["results"]
    assert initial == buttons == dict(clear=False, reset=True)
    assert edited == dict(clear=False, reset=False) and invalid["hidden"]
    assert empty["values"] == [] and cleared == dict(clear=True, reset=False)
    assert before == restored == after and not closed["open"]
    assert form["values"] == [["2000", "2000"], ["2200", "2200"],
                              ["2400", "2400"]]
    assert not preview["hidden"] and not form["error"]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_clear_applies_atomically_and_preserves_endpoints(name, kind):
    output = connection_scenario(COORDINATE_RESET_EVENTS + """
      openResetForm('""" + kind + """');results.push(snapshot());
      toolClick('clear-coordinate-rows');
      results.push(snapshot(),coordinateState(),previewState());submitCoordinates();
      results.push(snapshot(),coordinateState());
      if('""" + kind + """'==='edge'){history('undo');results.push(snapshot());
        history('redo');results.push(snapshot());}
    """, load_template(name))
    before, editing, form, preview, after, closed, *states = output["results"]
    assert before == editing and form["values"] == [] and not preview["hidden"]
    assert not closed["open"]
    if kind == "edge":
        assert after["doc"]["edges"][0] == dict(before["doc"]["edges"][0], vertices=[])
        assert after["doc"]["labels"] == before["doc"]["labels"]
        assert len(after["undo"]) == 1
        assert states[0]["doc"] == before["doc"]
        assert states[1]["doc"] == after["doc"]
        assert output["saves"] == output["refreshes"] == 3
        validate_scene(after["doc"])
        assert export_scene(after["doc"], "svg").startswith(b"<?xml")
    else:
        assert after["doc"] == before["doc"] and after["undo"] == before["undo"]
        assert after["connectionVertices"] == [] and after["previewTarget"] is None
        assert after["pendingPort"] == before["pendingPort"]
        assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("kind", ["edge", "pending"])
@pytest.mark.parametrize("restore", [False, True])
def test_coordinate_bulk_changes_cancel_without_modifying_session(kind, restore):
    output = connection_scenario(COORDINATE_RESET_EVENTS + """
      openResetForm('""" + kind + """');results.push(snapshot());
      coordinateInput(0,['',2100]);toolClick('clear-coordinate-rows');
      if(""" + json.dumps(restore) + """)toolClick('reset-coordinate-rows');
      dialog.close();results.push(snapshot(),coordinateState());
    """)
    before, after, closed = output["results"]
    assert before == after and not closed["open"] and not closed["session"]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("guard", ["closed", "revision", "selection"])
@pytest.mark.parametrize("action", ["clear-coordinate-rows", "reset-coordinate-rows"])
def test_coordinate_bulk_actions_protect_stale_sessions(guard, action):
    changes = {
        "closed": "dialog.close();",
        "revision": "revision++;",
        "selection": "setSelection('edge',doc.edges[1].id);",
    }
    output = connection_scenario(COORDINATE_RESET_EVENTS + """
      openResetForm('edge');coordinateInput(0,[2100,2150]);
    """ + changes[guard] + """
      results.push(snapshot(),coordinateState());toolClick('""" + action + """');
      results.push(snapshot(),coordinateState());
    """)
    before, form, after, final = output["results"]
    assert before == after and form.get("values") == final.get("values")
    if guard != "closed":
        assert "已变化" in final["error"]
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("count", [0, 100])
def test_coordinate_bulk_restore_handles_empty_and_limit(count):
    output = connection_scenario(COORDINATE_RESET_EVENTS + """
      const edge=doc.edges[0];
      edge.vertices=Array.from({length:""" + str(count) + """},(_,i)=>[2000+i,2100]);
      mode='select';setSelection('edge',edge.id);showEdgeCoordinates(edge.id);
      results.push(snapshot(),resetState());toolClick('clear-coordinate-rows');
      results.push(resetState(),$('connection-coordinate-add').disabled);
      if(!connectionCoordinates.controls.length)toolClick('add-coordinate-row');
      toolClick('reset-coordinate-rows');
      results.push(snapshot(),coordinateState(),resetState(),
        $('connection-coordinate-add').disabled);
    """)
    (before, initial, cleared, add_disabled, after, restored, buttons,
     final_add) = output["results"]
    assert before == after and initial == buttons == dict(clear=count == 0, reset=True)
    assert cleared == dict(clear=True, reset=count == 0) and not add_disabled
    assert len(restored["values"]) == count and final_add == (count == 100)
    assert output["saves"] == output["refreshes"] == 0


def test_coordinate_clear_rejects_duplicate_route_and_restore_recovers():
    output = connection_scenario(COORDINATE_RESET_EVENTS + """
      openResetForm('edge');const edge=doc.edges[0];
      doc.edges.push({...clone(edge),id:'duplicate-auto',vertices:[]});
      results.push(snapshot());toolClick('clear-coordinate-rows');submitCoordinates();
      results.push(snapshot(),coordinateState(),previewState());
      toolClick('reset-coordinate-rows');results.push(coordinateState(),previewState());
      submitCoordinates();results.push(snapshot(),coordinateState());
    """)
    before, rejected, error, preview, restored, valid, after, closed = output["results"]
    assert before == rejected == after and error["open"] and preview["hidden"]
    assert "相同走线" in error["error"] and not valid["hidden"]
    assert restored["values"] == [["2000", "2000"], ["2200", "2200"],
                                  ["2400", "2400"]]
    assert not restored["error"] and not closed["open"] and output["saves"] == 0


def test_coordinate_restore_uses_latest_opened_values_and_input_updates_buttons():
    output = connection_scenario(COORDINATE_RESET_EVENTS + """
      openResetForm('edge');coordinateInput(0,[2050.125,2070.75]);
      results.push(resetState());submitCoordinates();
      showEdgeCoordinates(doc.edges[0].id);results.push(snapshot(),resetState());
      coordinateInput(0,['',2070.75]);results.push(resetState());
      toolClick('reset-coordinate-rows');
      results.push(coordinateState(),resetState(),snapshot());submitCoordinates();
      results.push(snapshot());
    """)
    (edited, before, initial, invalid, restored, buttons, after,
     applied) = output["results"]
    assert edited == invalid == dict(clear=False, reset=False)
    assert initial == buttons == dict(clear=False, reset=True)
    assert restored["values"][0] == ["2050.125", "2070.75"]
    assert before == after == applied and len(applied["undo"]) == 1
    assert output["saves"] == output["refreshes"] == 1


COORDINATE_ERROR_EVENTS = COORDINATE_RESET_EVENTS + """
  const errorRows=()=>connectionCoordinates.controls.map((row,index)=>({
    invalid:row.map(input=>input.attributes['aria-invalid']),
    described:row.map(input=>input.attributes['aria-describedby']),
    message:connectionCoordinates.rowErrors[index].textContent,
    id:connectionCoordinates.rowErrors[index].id}));
  let errorFocus=null;
  const watchFocus=()=>connectionCoordinates.controls.forEach((row,index)=>
    row.forEach((input,axis)=>input.focus=()=>{errorFocus=[index,axis];}));
"""


@pytest.mark.parametrize("kind", ["edge", "pending"])
@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize("invalid", ["", "100001", "NaN"])
def test_coordinate_numeric_errors_mark_axis_and_focus_on_apply(kind, axis, invalid):
    output = connection_scenario(COORDINATE_ERROR_EVENTS + """
      openResetForm('""" + kind + """');watchFocus();results.push(snapshot());
      connectionCoordinates.controls[2][""" + str(axis) + """].value="""
                                 + json.dumps(invalid) + """;
      renderCoordinatePreview();results.push(errorRows(),errorFocus);
      submitCoordinates();results.push(snapshot(),coordinateState(),errorFocus);
      coordinateInput(2,[2450.125,2470.75]);
      results.push(errorRows(),coordinateState(),previewState());
      submitCoordinates();results.push(snapshot());
    """)
    (before, rows, passive_focus, rejected, form, active_focus, repaired,
     cleared, preview, applied) = output["results"]
    assert before == rejected and form["open"] and form["error"]
    assert passive_focus is None and active_focus == [2, axis]
    assert rows[2]["invalid"] == [str(i == axis).lower() for i in range(2)]
    assert rows[2]["message"] and not rows[0]["message"]
    assert rows[2]["described"] == [rows[2]["id"]] * 2
    assert all(row["invalid"] == ["false", "false"] and not row["message"]
               for row in repaired)
    assert not cleared["error"] and not preview["hidden"]
    points = (applied["doc"]["edges"][0]["vertices"] if kind == "edge"
              else applied["connectionVertices"])
    assert points[-1] == [2450.125, 2470.75]
    assert output["saves"] == (1 if kind == "edge" else 0)


@pytest.mark.parametrize("kind", ["edge", "pending"])
@pytest.mark.parametrize("invalid", ["source", "neighbor"])
def test_coordinate_geometry_error_identifies_row_without_stealing_input(kind, invalid):
    output = connection_scenario(COORDINATE_ERROR_EVENTS + """
      openResetForm('""" + kind + """');watchFocus();results.push(snapshot());
      if('""" + invalid + """'==='source')coordinates(0,
        endpoint(doc.edges[0].source,currentNodes(),doc.junctions).point);
      else coordinates(2,[2200,2200]);
      renderCoordinatePreview();results.push(errorRows(),errorFocus);
      submitCoordinates();results.push(snapshot(),coordinateState(),errorFocus);
    """)
    before, rows, passive_focus, after, form, active_focus = output["results"]
    index = 0 if invalid == "source" else 1
    assert before == after and form["open"] and "重合" in form["error"]
    assert rows[index]["invalid"] == ["true", "true"]
    assert "重合" in rows[index]["message"]
    assert passive_focus is None and active_focus == [index, 0]
    assert output["saves"] == 0


@pytest.mark.parametrize("action", ["reorder", "delete", "clear", "restore"])
def test_coordinate_error_state_rebuilds_with_current_rows(action):
    output = connection_scenario(COORDINATE_ERROR_EVENTS + """
      openResetForm('edge');coordinateInput(2,['',2400]);results.push(snapshot());
      const action='""" + action + """';
      if(action==='reorder')order(2,'上移');
      if(action==='delete')rowAction(2,'删除此折点');
      if(action==='clear')toolClick('clear-coordinate-rows');
      if(action==='restore')toolClick('reset-coordinate-rows');
      results.push(snapshot(),errorRows(),previewState());dialog.close();
      showEdgeCoordinates(doc.edges[0].id);results.push(errorRows());
    """)
    before, after, rows, preview, reopened = output["results"]
    assert before == after and output["saves"] == 0
    if action == "reorder":
        assert rows[1]["invalid"] == ["true", "false"] and preview["hidden"]
        assert not rows[2]["message"]
    else:
        assert not preview["hidden"] and all(not row["message"] for row in rows)
    assert all(not row["message"] and row["invalid"] == ["false", "false"]
               for row in reopened)


def test_coordinate_global_errors_do_not_mark_unrelated_rows_or_focus_them():
    output = connection_scenario(COORDINATE_ERROR_EVENTS + """
      openResetForm('edge');watchFocus();doc.edges.push({
        ...clone(doc.edges[0]),id:'duplicate-auto',vertices:[]});
      toolClick('clear-coordinate-rows');submitCoordinates();
      results.push(coordinateState(),errorFocus);
      toolClick('reset-coordinate-rows');watchFocus();errorFocus=null;revision++;
      results.push(snapshot());submitCoordinates();
      results.push(snapshot(),coordinateState(),errorRows(),errorFocus);
    """)
    duplicate, focused, before, after, stale, rows, stale_focus = output["results"]
    assert "相同走线" in duplicate["error"] and focused is None
    assert before == after and "已变化" in stale["error"] and stale_focus is None
    assert all(not row["message"] for row in rows) and output["saves"] == 0


@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_error_in_last_of_hundred_rows_focuses_exact_axis(kind):
    output = connection_scenario(COORDINATE_ERROR_EVENTS + """
      openResetForm('""" + kind + """');
      renderCoordinateRows(Array.from({length:100},(_,i)=>[2000+i,2100]));
      watchFocus();coordinateInput(99,[2099,'']);results.push(snapshot());
      submitCoordinates();results.push(snapshot(),errorRows(),errorFocus);
      toolClick('reset-coordinate-rows');results.push(errorRows());
    """)
    before, after, rows, focus, restored = output["results"]
    assert before == after and focus == [99, 1] and len(rows) == 100
    assert rows[-1]["invalid"] == ["false", "true"]
    assert all(not row["message"] for row in rows[:-1] + restored)
    assert output["saves"] == 0


def test_coordinate_last_point_at_target_marks_both_axes():
    output = connection_scenario(COORDINATE_ERROR_EVENTS + """
      openResetForm('edge');watchFocus();results.push(snapshot());
      coordinateInput(2,endpoint(doc.edges[0].target,currentNodes(),doc.junctions).point);
      submitCoordinates();results.push(snapshot(),errorRows(),errorFocus);
    """)
    before, after, rows, focus = output["results"]
    assert before == after and focus == [2, 0]
    assert rows[2]["invalid"] == ["true", "true"] and "终点" in rows[2]["message"]
    assert output["saves"] == 0


def test_coordinate_errors_defer_native_blur_validation_and_center_invalid_input():
    output = connection_scenario(COORDINATE_ERROR_EVENTS + """
      openResetForm('edge');watchFocus();let reports=0,scrolls=[];
      const input=connectionCoordinates.controls[2][1];
      input.reportValidity=()=>reports++;input.scrollIntoView=options=>scrolls.push(options);
      coordinateInput(2,[2400,'']);results.push(snapshot());
      input.handlers.get('change')();input.handlers.get('blur')();
      results.push(reports,errorFocus);submitCoordinates();
      results.push(snapshot(),reports,errorFocus,scrolls);
      coordinateInput(2,[2400,2470.125]);input.handlers.get('change')();
      input.handlers.get('blur')();results.push(snapshot());submitCoordinates();
      results.push(snapshot());
    """)
    (before, reports, passive, rejected, final_reports, focus, scrolls, editing,
     applied) = output["results"]
    assert before == rejected == editing and reports == final_reports == 0
    assert passive is None and focus == [2, 1]
    assert scrolls == [dict(block="center", inline="nearest")]
    assert applied["doc"]["edges"][0]["vertices"][-1] == [2400, 2470.125]
    assert output["saves"] == 1


COORDINATE_LINK_EVENTS = COORDINATE_ERROR_EVENTS + """
  const linked=()=>({rows:connectionCoordinates.rowElements.map(
    r=>r.attributes['data-active']),
    points:connectionCoordinates.previewPoints.map(p=>({active:p.attributes['data-active'],
      pressed:p.attributes['aria-pressed'],role:p.attributes.role,tabindex:p.attributes.tabindex,
      label:p.attributes['aria-label']}))});
  let linkFocus=null,linkScrolls=[];
  const watchLinkedFocus=()=>connectionCoordinates.controls.forEach((row,index)=>
    row.forEach((input,axis)=>{input.focus=()=>{linkFocus=[index,axis];
      input.handlers.get('focus')();};
      input.scrollIntoView=options=>linkScrolls.push(options);}));
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_preview_point_locates_input_and_preserves_atomic_apply(name, kind):
    output = connection_scenario(COORDINATE_LINK_EVENTS + """
      openResetForm('""" + kind + """');watchLinkedFocus();results.push(snapshot());
      connectionCoordinates.previewPoints[1].handlers.get('click')();
      results.push(snapshot(),linked(),linkFocus,linkScrolls);
      connectionCoordinates.controls[2][1].focus();results.push(linked(),linkFocus);
      coordinateInput(2,[2450.25,2470.125]);results.push(linked(),snapshot());
      submitCoordinates();results.push(snapshot());
      if('""" + kind + """'==='edge'){history('undo');results.push(snapshot());
        history('redo');results.push(snapshot());}
    """, load_template(name))
    (before, clicked, selected, focus, scrolls, typed, typed_focus, changed,
     editing, after) = output["results"][:10]
    assert before == clicked == editing
    assert focus == [1, 0] and typed_focus == [2, 1]
    assert scrolls == [dict(block="center", inline="nearest")]
    assert selected["rows"] == ["false", "true", "false"]
    assert typed["rows"] == changed["rows"] == ["false", "false", "true"]
    assert [p["pressed"] for p in changed["points"]] == changed["rows"]
    assert all(p["role"] == "button" and p["tabindex"] == 0
               for p in changed["points"])
    assert changed["points"][2]["label"] == "定位折点 3 坐标"
    if kind == "edge":
        undone, redone = output["results"][10:]
        assert after["doc"]["edges"][0]["vertices"][-1] == [2450.25, 2470.125]
        assert len(after["undo"]) == 1 and undone["doc"] == before["doc"]
        assert redone["doc"] == after["doc"]
        validate_scene(after["doc"])
        assert export_scene(after["doc"], "svg").startswith(b"<?xml")
    else:
        assert after["doc"] == before["doc"] and not after["undo"]
        assert after["connectionVertices"][-1] == [2450.25, 2470.125]
    assert output["saves"] == (3 if kind == "edge" else 0)


@pytest.mark.parametrize("key", ["Enter", " ", "Escape", "ArrowDown"])
def test_coordinate_preview_keyboard_activation_only_handles_enter_and_space(key):
    output = connection_scenario(COORDINATE_LINK_EVENTS + """
      openResetForm('edge');watchLinkedFocus();let prevented=0;results.push(snapshot());
      connectionCoordinates.previewPoints[2].handlers.get('keydown')({
        key:'""" + key + """',preventDefault(){prevented++;}});
      results.push(snapshot(),linkFocus,linkScrolls,prevented);
    """)
    before, after, focus, scrolls, prevented = output["results"]
    assert before == after and output["saves"] == 0
    active = key in ["Enter", " "]
    assert focus == ([2, 0] if active else None)
    assert len(scrolls) == prevented == int(active)


@pytest.mark.parametrize("action", ["input", "sort", "delete", "clear", "restore",
                                    "close", "reopen"])
def test_coordinate_preview_old_markers_cannot_focus_rebuilt_or_closed_rows(action):
    commands = {
        "input": "coordinateInput(1,[2300.25,2310.5]);",
        "sort": "order(1,'上移');",
        "delete": "rowAction(1,'删除此折点');",
        "clear": "toolClick('clear-coordinate-rows');",
        "restore": ("coordinateInput(1,[2300.25,2310.5]);"
                    "toolClick('reset-coordinate-rows');"),
        "close": "dialog.close();",
        "reopen": "dialog.close();showEdgeCoordinates(doc.edges[0].id);",
    }
    output = connection_scenario(COORDINATE_LINK_EVENTS + """
      openResetForm('edge');watchLinkedFocus();
      const old=connectionCoordinates.previewPoints[1];
    """ + commands[action] + """
      linkFocus=null;linkScrolls=[];results.push(snapshot());
      old.handlers.get('click')();old.handlers.get('keydown')({key:'Enter',preventDefault(){}});
      results.push(snapshot(),linkFocus,linkScrolls);
    """)
    before, after, focus, scrolls = output["results"]
    assert before == after and focus is None and scrolls == []
    assert output["saves"] == 0


@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_preview_hundredth_marker_and_invalid_repair_keep_correct_row(kind):
    output = connection_scenario(COORDINATE_LINK_EVENTS + """
      openResetForm('""" + kind + """');
      renderCoordinateRows(Array.from({length:100},(_,i)=>[2000+i*10,2100+i*5]));
      watchLinkedFocus();results.push(snapshot());
      connectionCoordinates.previewPoints[99].handlers.get('click')();
      results.push(linked(),linkFocus);
      const stale=connectionCoordinates.controls[99][0];
      coordinateInput(99,[2990,'']);results.push(previewState(),linked());
      coordinateInput(99,[2990,2595.125]);results.push(linked());
      toolClick('clear-coordinate-rows');stale.handlers.get('focus')();
      results.push(linked());toolClick('reset-coordinate-rows');
      results.push(linked(),snapshot());
    """)
    (before, selected, focus, invalid, hidden, repaired, empty, reset,
     after) = output["results"]
    assert before == after and focus == [99, 0]
    assert len(selected["points"]) == 100 and selected["rows"][-1] == "true"
    assert selected["rows"].count("true") == 1
    assert invalid["hidden"] and hidden["points"] == []
    assert repaired["points"][-1]["pressed"] == "true"
    assert empty == dict(rows=[], points=[])
    assert len(reset["rows"]) == 3 and reset["rows"][0] == "true"
    assert output["saves"] == 0


COORDINATE_NAVIGATION_EVENTS = COORDINATE_LINK_EVENTS + """
  const navigationState=()=>({previous:$('connection-coordinate-previous').disabled,
    next:$('connection-coordinate-next').disabled,
    disabled:$('connection-coordinate-jump').disabled,
    value:$('connection-coordinate-jump').value,
    options:$('connection-coordinate-jump').children.map(o=>[o.textContent,o.value])});
  const jumpTo=value=>listeners.get('connection-coordinate-jump:change')({
    target:{value:String(value)}});
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_navigation_keeps_unapplied_values_and_atomic_submission(name, kind):
    output = connection_scenario(COORDINATE_NAVIGATION_EVENTS + """
      openResetForm('""" + kind + """');watchLinkedFocus();results.push(snapshot());
      coordinateInput(1,[2250.125,2270.5]);results.push(navigationState());
      toolClick('next-coordinate-row');results.push(navigationState(),linkFocus);
      toolClick('previous-coordinate-row');jumpTo(2);
      results.push(navigationState(),linkFocus,linked(),coordinateState(),snapshot());
      submitCoordinates();results.push(snapshot());
      if('""" + kind + """'==='edge'){history('undo');results.push(snapshot());
        history('redo');results.push(snapshot());}
    """, load_template(name))
    (before, first, second, second_focus, last, last_focus, linked, form, editing,
     applied) = output["results"][:10]
    assert before == editing
    assert first["previous"] and not first["next"] and first["value"] == "0"
    assert not second["previous"] and not second["next"]
    assert second_focus == [1, 0] and second["value"] == "1"
    assert last_focus == [2, 0] and last["next"] and not last["previous"]
    assert last["value"] == "2" and not last["disabled"]
    assert last["options"] == [[f"折点 {i + 1} / 3", str(i)] for i in range(3)]
    assert linked["rows"] == ["false", "false", "true"]
    assert form["values"][1] == ["2250.125", "2270.5"]
    if kind == "edge":
        undone, redone = output["results"][10:]
        assert applied["doc"]["edges"][0]["vertices"][1] == [2250.125, 2270.5]
        assert len(applied["undo"]) == 1 and undone["doc"] == before["doc"]
        assert redone["doc"] == applied["doc"]
        validate_scene(applied["doc"])
        assert export_scene(applied["doc"], "svg").startswith(b"<?xml")
    else:
        assert applied["doc"] == before["doc"] and not applied["undo"]
        assert applied["connectionVertices"][1] == [2250.125, 2270.5]
    assert output["saves"] == (3 if kind == "edge" else 0)


@pytest.mark.parametrize("count", [0, 1, 100])
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_navigation_handles_empty_single_and_hundred_rows(count, kind):
    output = connection_scenario(COORDINATE_NAVIGATION_EVENTS + """
      openResetForm('""" + kind + """');
      renderCoordinateRows(Array.from({length:""" + str(count) + """},
        (_,i)=>[2000+i*10,2100+i*5]));watchLinkedFocus();results.push(snapshot());
      results.push(navigationState());jumpTo('""" + str(count - 1) + """');
      results.push(navigationState(),linkFocus);linkFocus=null;
      toolClick('next-coordinate-row');results.push(linkFocus);
      jumpTo(0);linkFocus=null;toolClick('previous-coordinate-row');
      for(const value of ['','NaN','0.5','-1','100'])jumpTo(value);
      results.push(navigationState(),linkFocus,snapshot());
    """)
    (before, initial, last, focus, out_of_range, final, rejected,
     after) = output["results"]
    assert before == after and out_of_range is None and rejected is None
    assert initial["previous"] and initial["disabled"] == (count == 0)
    assert initial["next"] == (count < 2)
    assert last["next"] and focus == ([count - 1, 0] if count else None)
    assert final == initial
    assert len(initial["options"]) == max(1, count)
    assert output["saves"] == 0


def test_coordinate_navigation_remains_available_when_preview_is_invalid_and_updates():
    output = connection_scenario(COORDINATE_NAVIGATION_EVENTS + """
      openResetForm('edge');watchLinkedFocus();results.push(snapshot());
      coordinateInput(1,['',2200]);jumpTo(1);results.push(previewState(),
        navigationState(),linkFocus,coordinateState());
      toolClick('next-coordinate-row');results.push(linkFocus);
      order(2,'上移');watchLinkedFocus();jumpTo(1);
      results.push(coordinateState(),navigationState());
      rowAction(0,'在此前插入');watchLinkedFocus();jumpTo(3);
      results.push(navigationState());rowAction(0,'删除此折点');
      results.push(navigationState());toolClick('clear-coordinate-rows');
      results.push(navigationState());toolClick('reset-coordinate-rows');
      results.push(navigationState(),snapshot());
    """)
    (before, invalid, navigation, focus, form, next_focus, ordered, order_nav,
     inserted, deleted, empty, reset, after) = output["results"]
    assert before == after and invalid["hidden"] and not navigation["disabled"]
    assert focus == [1, 0] and next_focus == [2, 0]
    assert form["values"][1] == ["", "2200"]
    assert ordered["values"] == [["2000", "2000"], ["2400", "2400"], ["", "2200"]]
    assert order_nav["value"] == "1" and len(inserted["options"]) == 4
    assert inserted["value"] == "3" and len(deleted["options"]) == 3
    assert empty["disabled"] and empty["previous"] and empty["next"]
    assert empty["options"] == [["无折点", ""]]
    assert reset["value"] == "0" and not reset["disabled"]
    assert output["saves"] == 0


def test_coordinate_navigation_after_close_is_noop_and_new_session_uses_current_rows():
    output = connection_scenario(COORDINATE_NAVIGATION_EVENTS + """
      openResetForm('edge');watchLinkedFocus();jumpTo(2);dialog.close();
      linkFocus=null;results.push(snapshot());jumpTo(0);toolClick('next-coordinate-row');
      results.push(snapshot(),linkFocus);showEdgeCoordinates(doc.edges[0].id);
      watchLinkedFocus();toolClick('next-coordinate-row');
      results.push(navigationState(),linkFocus,snapshot());
    """)
    before, closed, focus, reopened, new_focus, after = output["results"]
    assert before == closed == after and focus is None and new_focus == [1, 0]
    assert reopened["value"] == "1" and output["saves"] == 0


COORDINATE_HISTORY_EVENTS = COORDINATE_NAVIGATION_EVENTS + """
  const formHistory=()=>({undo:connectionCoordinates.formUndo.length,
    redo:connectionCoordinates.formRedo.length,
    undoDisabled:$('connection-coordinate-undo').disabled,
    redoDisabled:$('connection-coordinate-redo').disabled});
  const formUndo=()=>toolClick('undo-coordinate-form');
  const formRedo=()=>toolClick('redo-coordinate-form');
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_form_history_groups_input_without_mutating_document(name, kind):
    output = connection_scenario(COORDINATE_HISTORY_EVENTS + """
      openResetForm('""" + kind + """');results.push(snapshot(),formHistory());
      coordinateInput(1,[2250.125,2270.5]);coordinateInput(1,[2250.125,2280.75]);
      results.push(formHistory());formUndo();results.push(coordinateState(),formHistory());
      formRedo();results.push(coordinateState(),formHistory(),snapshot());
      submitCoordinates();results.push(snapshot());
      if('""" + kind + """'==='edge'){history('undo');results.push(snapshot());
        history('redo');results.push(snapshot());}
    """, load_template(name))
    before, initial, typed, undone, undo_state, redone, redo_state, editing, applied = (
        output["results"][:9])
    assert before == editing and initial == dict(undo=0, redo=0,
                                                undoDisabled=True, redoDisabled=True)
    assert typed["undo"] == 1 and typed["redoDisabled"]
    assert undone["values"] == [["2000", "2000"], ["2200", "2200"], ["2400", "2400"]]
    assert undo_state["undoDisabled"] and undo_state["redo"] == 1
    assert redone["values"][1] == ["2250.125", "2280.75"]
    assert redo_state["undo"] == 1 and redo_state["redoDisabled"]
    if kind == "edge":
        original, replayed = output["results"][9:]
        assert len(applied["undo"]) == 1 and original["doc"] == before["doc"]
        assert replayed["doc"] == applied["doc"]
        validate_scene(applied["doc"])
        assert export_scene(applied["doc"], "svg").startswith(b"<?xml")
    else:
        assert applied["doc"] == before["doc"] and not applied["undo"]
        assert applied["connectionVertices"][1] == [2250.125, 2280.75]
    assert output["saves"] == (3 if kind == "edge" else 0)


@pytest.mark.parametrize("action", ["add", "insert", "delete", "order",
                                    "clear", "reset"])
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_form_history_restores_structures_and_invalid_text(action, kind):
    commands = {
        "add": "toolClick('add-coordinate-row');",
        "insert": "rowAction(1,'在此前插入');",
        "delete": "rowAction(1,'删除此折点');",
        "order": "order(1,'上移');",
        "clear": "toolClick('clear-coordinate-rows');",
        "reset": "toolClick('reset-coordinate-rows');",
    }
    output = connection_scenario(COORDINATE_HISTORY_EVENTS + """
      openResetForm('""" + kind + """');results.push(snapshot());
      coordinateInput(1,['','2270.500']);results.push(coordinateState());
    """ + commands[action] + """
      results.push(coordinateState(),formHistory());formUndo();
      results.push(coordinateState(),formHistory(),previewState());formRedo();
      results.push(coordinateState(),formHistory(),snapshot());
    """)
    (before, typed, changed, change_hist, undone, undo_hist, preview, redone,
     redo_hist, after) = output["results"]
    assert before == after and undone["values"] == typed["values"]
    assert redone["values"] == changed["values"]
    assert change_hist["undo"] == 2 and undo_hist["undo"] == undo_hist["redo"] == 1
    assert redo_hist["undo"] == 2 and redo_hist["redoDisabled"]
    assert preview["hidden"] and output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("boundary", ["blur", "change", "focus", "navigate"])
def test_coordinate_form_history_separates_confirmed_edits_and_clears_redo(boundary):
    commands = {
        "blur": "connectionCoordinates.controls[1][0].handlers.get('blur')();",
        "change": "connectionCoordinates.controls[1][0].handlers.get('change')();",
        "focus": "connectionCoordinates.controls[1][1].handlers.get('focus')();",
        "navigate": "jumpTo(2);jumpTo(1);",
    }
    output = connection_scenario(COORDINATE_HISTORY_EVENTS + """
      openResetForm('edge');results.push(snapshot());
      coordinateInput(1,[2250,2270]);
    """ + commands[boundary] + """
      coordinateInput(1,[2260,2280]);results.push(formHistory());
      formUndo();results.push(coordinateState());jumpTo(0);
      results.push(formHistory());coordinateInput(0,[2050.25,2070.5]);
      results.push(formHistory(),coordinateState());formRedo();
      results.push(coordinateState(),snapshot());
    """)
    (before, two_steps, undone, navigated, branched, edited, noop,
     after) = output["results"]
    assert before == after and two_steps["undo"] == 2
    assert undone["values"][1] == ["2250", "2270"]
    assert navigated["redo"] == 1 and branched["redoDisabled"]
    assert edited["values"] == noop["values"] and output["saves"] == 0


@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_form_history_is_bounded_and_preserves_hundred_rows(kind):
    output = connection_scenario(COORDINATE_HISTORY_EVENTS + """
      openResetForm('""" + kind + """');
      renderCoordinateRows(Array.from({length:100},(_,i)=>[2000+i*10,2100+i*5]));
      results.push(snapshot());
      for(let i=0;i<105;i++){coordinateInput(99,[4000+i,2600.125]);
        connectionCoordinates.controls[99][0].handlers.get('change')();}
      results.push(formHistory(),coordinateState());
      for(let i=0;i<100;i++)formUndo();results.push(formHistory(),coordinateState());
      formUndo();for(let i=0;i<100;i++)formRedo();
      results.push(formHistory(),coordinateState(),snapshot());
    """)
    before, limited, latest, oldest_hist, oldest, restored_hist, restored, after = (
        output["results"])
    assert before == after and limited["undo"] == oldest_hist["redo"] == 100
    assert oldest_hist["undoDisabled"] and oldest["values"][-1] == ["4004", "2600.125"]
    assert restored["values"] == latest["values"] and len(restored["values"]) == 100
    assert restored_hist["undo"] == 100 and restored_hist["redoDisabled"]
    assert output["saves"] == 0


@pytest.mark.parametrize("guard", ["closed", "reopen", "revision", "selection"])
def test_coordinate_form_history_respects_session_boundaries(guard):
    commands = {
        "closed": "dialog.close();",
        "reopen": "dialog.close();showEdgeCoordinates(doc.edges[0].id);",
        "revision": "revision++;",
        "selection": "multiSelection=[];",
    }
    output = connection_scenario(COORDINATE_HISTORY_EVENTS + """
      openResetForm('edge');coordinateInput(1,[2250.25,2270.5]);
      const old=connectionCoordinates.controls[1][0];
    """ + commands[guard] + """
      results.push(snapshot(),coordinateState());formUndo();formRedo();
      const historyError=$('connection-coordinate-error').textContent;
      old.handlers.get('input')();
      results.push(snapshot(),coordinateState(),historyError);
      if(connectionCoordinates)results.push(formHistory());
    """)
    before, form, after, result = output["results"][:4]
    assert before == after and form.get("values") == result.get("values")
    if guard == "reopen":
        assert output["results"][5]["undoDisabled"]
        assert output["results"][5]["redoDisabled"]
    elif guard in ["revision", "selection"]:
        assert "已变化" in output["results"][4]
    assert output["saves"] == 0


def test_coordinate_form_noop_navigation_and_rebuilt_callbacks_do_not_add_history():
    output = connection_scenario(COORDINATE_HISTORY_EVENTS + """
      openResetForm('edge');results.push(snapshot());formUndo();formRedo();
      jumpTo(2);coordinateInput(0,[2000,2000]);results.push(formHistory());
      const old=connectionCoordinates.controls[0][0];
      toolClick('add-coordinate-row');const hist=formHistory();
      old.value='5555';old.handlers.get('input')();old.handlers.get('blur')();
      results.push(hist,formHistory());formUndo();results.push(coordinateState());
      formRedo();results.push(coordinateState());dialog.close();results.push(snapshot());
    """)
    before, noop, added, callbacks, undone, redone, after = output["results"]
    assert before == after and noop["undoDisabled"] and noop["redoDisabled"]
    assert added == callbacks and added["undo"] == 1
    assert len(undone["values"]) == 3 and redone["values"][-1] == ["", ""]
    assert output["saves"] == 0


COORDINATE_IMPORT_EVENTS = COORDINATE_HISTORY_EVENTS + r"""
  const importText=text=>{$('connection-coordinate-text').value=text;
    toolClick('import-coordinate-rows');};
  const importState=()=>({text:$('connection-coordinate-import-status').textContent,
    error:$('connection-coordinate-import-status').attributes['data-error'],
    expanded:$('connection-coordinate-import').open});
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_import_table_is_transient_undoable_and_applies_once(name, kind):
    output = connection_scenario(COORDINATE_IMPORT_EVENTS + r"""
      openResetForm('""" + kind + r"""');results.push(snapshot());
      $('connection-coordinate-import').open=true;
      importText(' 2100.125\t2150.500\r\n\r\n2300.25\t2350.750 ');
      results.push(coordinateState(),formHistory(),importState(),snapshot());
      formUndo();results.push(coordinateState(),importState());formRedo();
      results.push(coordinateState());submitCoordinates();results.push(snapshot());
      if('""" + kind + r"""'==='edge'){history('undo');results.push(snapshot());
        history('redo');results.push(snapshot());}
    """, load_template(name))
    before, form, hist, notice, editing, undone, undo_notice, redone, applied = (
        output["results"][:9])
    assert before == editing and hist["undo"] == 1 and hist["redoDisabled"]
    assert form["values"] == [["2100.125", "2150.500"], ["2300.25", "2350.750"]]
    assert redone["values"] == form["values"]
    assert undone["values"] == [["2000", "2000"], ["2200", "2200"], ["2400", "2400"]]
    assert not notice["expanded"] and notice["error"] == "false"
    assert "2 个" in notice["text"]
    assert undo_notice["text"] == ""
    if kind == "edge":
        original, replayed = output["results"][9:]
        assert len(applied["undo"]) == 1 and original["doc"] == before["doc"]
        assert replayed["doc"] == applied["doc"]
        validate_scene(applied["doc"])
        assert export_scene(applied["doc"], "svg").startswith(b"<?xml")
    else:
        assert applied["doc"] == before["doc"] and not applied["undo"]
        assert applied["connectionVertices"] == [[2100.125, 2150.5], [2300.25, 2350.75]]
    assert output["saves"] == (3 if kind == "edge" else 0)


@pytest.mark.parametrize("text", [
    "2100.125, 2150.500\n2300.25,2350.75",
    "2100.125，2150.500\n2300.25，2350.75",
    "2100.125 2150.500\n2300.25   2350.75",
    "+2100.125 2150.500\n2300.25 2350.75",
])
def test_coordinate_import_delimiters_keep_decimal_text(text):
    output = connection_scenario(COORDINATE_IMPORT_EVENTS + r"""
      openResetForm('edge');importText(""" + json.dumps(text) + r""");
      results.push(coordinateState(),importState());
    """)
    form, notice = output["results"]
    assert form["values"] == [["2100.125", "2150.500"], ["2300.25", "2350.75"]]
    assert notice["error"] == "false" and output["saves"] == 0


@pytest.mark.parametrize("text,message", [
    ("", "请先粘贴"), (" \r\n \t", "请先粘贴"),
    ("2100 2150\n\nX Y", "第 3 行"),
    ("2100,", "第 1 行"), ("2100,,2150", "第 1 行"),
    ("2100\t\t2150", "第 1 行"), ("2100 2150 2200", "第 1 行"),
    ("0x10 2150", "第 1 行"), ("NaN 2150", "第 1 行"),
    ("Infinity 2150", "第 1 行"), ("1e999 2150", "范围"),
    ("100001 2150", "范围"), ("-100000.1 2150", "范围"),
    ("1,2\n" * 101, "100 个"), ("1" * 20001, "文本过长"),
    ("2100 2150\n2100 2150", "相邻点重合"),
])
def test_coordinate_import_invalid_text_is_atomic_and_allows_retry(text, message):
    output = connection_scenario(COORDINATE_IMPORT_EVENTS + r"""
      openResetForm('edge');coordinateInput(1,['','2270.500']);
      results.push(snapshot(),coordinateState(),formHistory());
      $('connection-coordinate-import').open=true;
      importText(""" + json.dumps(text) + r""");
      results.push(snapshot(),coordinateState(),formHistory(),importState());
      importText('2100 2150\n2300 2350');results.push(importState(),coordinateState());
    """)
    (before, form, hist, after, rejected, unchanged, notice, repaired,
     result) = output["results"]
    assert before == after and rejected == form and unchanged == hist
    assert notice["expanded"] and notice["error"] == "true"
    assert message in notice["text"]
    assert repaired["error"] == "false" and len(result["values"]) == 2
    assert output["saves"] == output["refreshes"] == 0


@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_import_limit_bounds_and_scientific_notation(kind):
    output = connection_scenario(COORDINATE_IMPORT_EVENTS + r"""
      openResetForm('""" + kind + r"""');results.push(snapshot());
      importText(Array.from({length:100},(_,i)=>`${3000+i*10},${3100+i*5}`).join('\n'));
      results.push(coordinateState(),formHistory(),previewState());formUndo();
      importText('-100000 +100000\n.5 -.5\n2.1e3 2.15e3\n2300. 2350.');
      results.push(coordinateState(),importState(),snapshot());
    """)
    before, hundred, hist, preview, normalized, notice, after = output["results"]
    assert before == after and len(hundred["values"]) == 100 and hist["undo"] == 1
    assert not preview["hidden"] and notice["error"] == "false"
    assert normalized["values"] == [["-100000", "100000"], [".5", "-.5"],
                                       ["2.1e3", "2.15e3"], ["2300", "2350"]]
    assert output["saves"] == 0


@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_import_noop_and_cancel_reset_text_on_reopen(kind):
    output = connection_scenario(COORDINATE_IMPORT_EVENTS + r"""
      openResetForm('""" + kind + r"""');results.push(snapshot());
      importText('2000 2000\n2200 2200\n2400 2400');results.push(formHistory());
      importText('2100 2150\n2300 2350');dialog.close();results.push(snapshot());
      if('""" + kind + r"""'==='edge')showEdgeCoordinates(doc.edges[0].id);
      else showConnectionCoordinates();
      results.push(coordinateState(),formHistory(),$('connection-coordinate-text').value,importState());
    """)
    before, noop, after, reopened, hist, text, notice = output["results"]
    assert before == after and noop["undoDisabled"] and hist["undoDisabled"]
    assert len(reopened["values"]) == 3 and text == "" and notice["text"] == ""
    assert not notice["expanded"] and output["saves"] == 0


@pytest.mark.parametrize("guard", ["closed", "revision", "selection"])
def test_coordinate_import_stale_session_cannot_replace_form(guard):
    commands = {"closed": "dialog.close();", "revision": "revision++;",
                "selection": "multiSelection=[];"}
    output = connection_scenario(COORDINATE_IMPORT_EVENTS + r"""
      openResetForm('edge');
    """ + commands[guard] + r"""
      results.push(snapshot(),coordinateState());importText('2100 2150');
      results.push(snapshot(),coordinateState(),importState());
    """)
    before, form, after, rejected, notice = output["results"]
    assert before == after and form == rejected and output["saves"] == 0
    if guard != "closed":
        assert "已变化" in notice["text"]


@pytest.mark.parametrize("invalid", ["source", "target", "duplicate"])
def test_coordinate_import_rejects_endpoint_and_duplicate_routes(invalid):
    output = connection_scenario(COORDINATE_IMPORT_EVENTS + r"""
      openResetForm('edge');const edge=doc.edges[0];
      let vertices=[[2100,2150],[2300,2350]];
      if('""" + invalid + r"""'==='source')
        vertices[0]=endpoint(edge.source,currentNodes(),doc.junctions).point;
      if('""" + invalid + r"""'==='target')
        vertices[1]=endpoint(edge.target,currentNodes(),doc.junctions).point;
      if('""" + invalid + r"""'==='duplicate')
        doc.edges.push({...clone(edge),id:'duplicate-import',vertices});
      results.push(snapshot(),coordinateState(),formHistory());
      importText(vertices.map(p=>p.join(',')).join('\n'));
      results.push(snapshot(),coordinateState(),formHistory(),importState());
    """)
    before, form, hist, after, rejected, same_hist, notice = output["results"]
    assert before == after and form == rejected and hist == same_hist
    assert notice["error"] == "true" and output["saves"] == 0
    assert ("相同走线" if invalid == "duplicate" else "重合") in notice["text"]


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_coordinate_import_pending_commits_only_with_final_connection(name):
    output = connection_scenario(COORDINATE_IMPORT_EVENTS + r"""
      openResetForm('pending');const edge=doc.edges[0];results.push(snapshot());
      importText('2100.125 2150.5\n2300.25 2350.75');submitCoordinates();
      results.push(snapshot());click(edge.target);results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
    """, load_template(name))
    before, edited, committed, undone, redone = output["results"]
    assert edited["doc"] == before["doc"] and not edited["undo"]
    assert committed["doc"]["edges"][-1]["vertices"] == [[2100.125, 2150.5],
                                                        [2300.25, 2350.75]]
    assert undone["doc"] == before["doc"] and redone["doc"] == committed["doc"]
    assert output["saves"] == 3 and len(committed["undo"]) == 1
    validate_scene(committed["doc"])
    assert export_scene(committed["doc"], "svg").startswith(b"<?xml")


COORDINATE_COPY_EVENTS = COORDINATE_IMPORT_EVENTS + r"""
  const writes=[];let selectedOutput=0;
  globalThis.navigator={clipboard:{writeText:async text=>{writes.push(text);}}};
  $('connection-coordinate-output').select=()=>selectedOutput++;
  const copyRows=()=>copyCoordinateRows();
  const copyState=()=>({text:$('connection-coordinate-output').value,
    status:$('connection-coordinate-copy-status').textContent,
    disabled:$('connection-coordinate-copy').disabled,selected:selectedOutput,
    expanded:$('connection-coordinate-export').open,writes:[...writes]});
"""


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_copy_preserves_unapplied_text_and_roundtrips(name, kind):
    output = connection_scenario(COORDINATE_COPY_EVENTS + r"""
      openResetForm('""" + kind + r"""');coordinateInput(1,[2250.125,'2270.500']);
      results.push(snapshot(),coordinateState(),formHistory());
      await toolClick('copy-coordinate-rows');
      results.push(snapshot(),coordinateState(),formHistory(),copyState());
      const text=$('connection-coordinate-output').value;
      toolClick('clear-coordinate-rows');importText(text);
      results.push(coordinateState());submitCoordinates();results.push(snapshot());
    """, load_template(name))
    before, form, hist, after, same_form, same_hist, copied, loaded, applied = (
        output["results"])
    assert before == after and form == same_form and hist == same_hist
    assert copied["text"] == "2000\t2000\n2250.125\t2270.500\n2400\t2400"
    assert copied["writes"] == [copied["text"]] and "已复制 3 个" in copied["status"]
    assert not copied["disabled"] and copied["selected"] == 0
    assert loaded["values"] == form["values"]
    if kind == "edge":
        assert len(applied["undo"]) == 1
        validate_scene(applied["doc"])
    else:
        assert applied["doc"] == before["doc"] and not applied["undo"]
    assert output["saves"] == (1 if kind == "edge" else 0)


@pytest.mark.parametrize("fallback", ["missing", "denied"])
def test_coordinate_copy_fallback_selects_manual_text(fallback):
    setup = ("globalThis.navigator={};" if fallback == "missing" else
             "navigator.clipboard.writeText=async()=>{throw Error('denied');};")
    output = connection_scenario(COORDINATE_COPY_EVENTS + r"""
      openResetForm('edge');results.push(snapshot(),formHistory());
    """ + setup + r"""
      await copyRows();results.push(copyState(),snapshot(),formHistory());
    """)
    before, hist, copied, after, same_hist = output["results"]
    assert before == after and hist == same_hist and copied["selected"] == 1
    assert "Ctrl+C" in copied["status"] and not copied["disabled"]
    assert copied["text"] == "2000\t2000\n2200\t2200\n2400\t2400"
    assert copied["writes"] == [] and output["saves"] == 0


@pytest.mark.parametrize("invalid", ["", "bad", "NaN", "100001", "Infinity"])
@pytest.mark.parametrize("axis", [0, 1])
def test_coordinate_copy_rejects_invalid_number_without_writing(invalid, axis):
    output = connection_scenario(COORDINATE_COPY_EVENTS + r"""
      openResetForm('edge');watchLinkedFocus();await copyRows();
      coordinateInput(1,""" + json.dumps(
          [invalid, 2200] if axis == 0 else [2200, invalid]) + r""");
      results.push(snapshot(),formHistory());await copyRows();
      results.push(copyState(),linkFocus,snapshot(),formHistory());
    """)
    before, hist, rejected, focus, after, same_hist = output["results"]
    assert before == after and hist == same_hist and focus == [1, axis]
    assert rejected["text"] == "" and "折点 2" in rejected["status"]
    assert len(rejected["writes"]) == 1 and output["saves"] == 0


@pytest.mark.parametrize("count", [0, 1, 100])
@pytest.mark.parametrize("kind", ["edge", "pending"])
def test_coordinate_copy_empty_and_hundred_points(count, kind):
    output = connection_scenario(COORDINATE_COPY_EVENTS + r"""
      openResetForm('""" + kind + r"""');
      renderCoordinateRows(Array.from({length:""" + str(count) + r"""},
        (_,i)=>[String(2000+i*10),'2100.500']));
      results.push(snapshot(),copyState());await copyRows();
      results.push(copyState(),snapshot());
    """)
    before, initial, copied, after = output["results"]
    assert before == after and initial["disabled"] == (count == 0)
    assert len(copied["writes"]) == (1 if count else 0)
    if count:
        assert len(copied["text"].splitlines()) == count
        assert copied["text"].splitlines()[-1] == f"{2000 + (count - 1) * 10}\t2100.500"
    else:
        assert copied["disabled"] and "无手动折点" in copied["status"]
    assert output["saves"] == 0


@pytest.mark.parametrize("change", ["input", "undo", "closed", "reopen", "revision"])
@pytest.mark.parametrize("rejected", [False, True])
def test_coordinate_copy_async_result_cannot_touch_changed_window(change, rejected):
    commands = {
        "input": "coordinateInput(1,[2250,2270]);",
        "undo": "toolClick('clear-coordinate-rows');formUndo();",
        "closed": "dialog.close();",
        "reopen": "dialog.close();showEdgeCoordinates(doc.edges[0].id);",
        "revision": "revision++;",
    }
    output = connection_scenario(COORDINATE_COPY_EVENTS + r"""
      openResetForm('edge');let finish;
      navigator.clipboard.writeText=text=>{writes.push(text);
        return new Promise((resolve,reject)=>{finish=""" +
        ("reject" if rejected else "resolve") + r""";});};
      const copying=copyRows();await copyRows();results.push(copyState());
    """ + commands[change] + r"""
      results.push(snapshot());finish();await copying;
      results.push(snapshot(),copyState());
    """)
    pending, before, after, final = output["results"]
    assert pending["disabled"] and len(pending["writes"]) == 1
    assert before == after and final["text"] == final["status"] == ""
    assert final["selected"] == 0 and output["saves"] == 0


@pytest.mark.parametrize("guard", ["closed", "revision", "selection"])
def test_coordinate_copy_stale_session_blocks_clipboard(guard):
    commands = {"closed": "dialog.close();", "revision": "revision++;",
                "selection": "multiSelection=[];"}
    output = connection_scenario(COORDINATE_COPY_EVENTS + r"""
      openResetForm('edge');
    """ + commands[guard] + r"""
      results.push(snapshot());await copyRows();results.push(snapshot(),copyState());
    """)
    before, after, copied = output["results"]
    assert before == after and not copied["writes"] and output["saves"] == 0
    if guard != "closed":
        assert "已变化" in copied["status"]


@pytest.mark.parametrize("action", ["input", "insert", "delete", "order",
                                    "clear", "reset", "undo", "import"])
def test_coordinate_copy_output_clears_when_rows_change(action):
    commands = {
        "input": "coordinateInput(1,[2260,2280]);",
        "insert": "rowAction(1,'在此前插入');",
        "delete": "rowAction(1,'删除此折点');",
        "order": "order(1,'上移');",
        "clear": "toolClick('clear-coordinate-rows');",
        "reset": "toolClick('reset-coordinate-rows');",
        "undo": "formUndo();",
        "import": "importText('2100 2150\\n2300 2350');",
    }
    output = connection_scenario(COORDINATE_COPY_EVENTS + r"""
      openResetForm('edge');coordinateInput(1,[2250,2270]);
      results.push(snapshot());await copyRows();jumpTo(2);
      results.push(copyState());
    """ + commands[action] + r"""
      results.push(copyState(),snapshot());
    """)
    before, navigated, cleared, after = output["results"]
    assert before == after and "已复制" in navigated["status"]
    assert cleared["text"] == cleared["status"] == ""
    assert cleared["disabled"] == (action == "clear") and output["saves"] == 0
