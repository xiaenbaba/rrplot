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
const observers=[];
let uuid=0,saves=0,refreshes=0;
function element(id){if(!elements.has(id))elements.set(id,{
  addEventListener:(name,handler)=>listeners.set(id+':'+name,handler),
  focus(){},setPointerCapture(){},classes:{},classList:{remove(){},add(){},
    toggle(name,on){element(id).classes[name]=on;}},hasPointerCapture:()=>false});
  return elements.get(id);}
const context=vm.createContext({...geometry,...edits,...checks,input,
  structuredClone,results,messages,listeners,
  crypto:{randomUUID:()=>String(++uuid).padStart(8,'0')},
  document:{getElementById:element,querySelector:s=>s==='.canvas-hint'
      ?element('canvas-hint'):null,
    addEventListener:(name,handler)=>listeners.set('document:'+name,handler)},
  window:{addEventListener:(name,handler)=>listeners.set('window:'+name,handler)},
  ResizeObserver:class{constructor(callback){this.callback=callback;}
    observe(target){observers.push({target,callback:this.callback});}},observers,
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
    assert "点击后选择新端口或三通" in handle["title"]
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
