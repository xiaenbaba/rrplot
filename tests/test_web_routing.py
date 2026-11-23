"""Automatic routing preserves orthogonal exports, connectivity and edit history."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, route, validate_scene
from rrplot.scene_renderer import export_scene

ROOT = Path(__file__).resolve().parents[1]


def run_js(script, value):
    executable = shutil.which('node')
    if not executable:
        pytest.skip('Node not installed; optional routing check')
    bootstrap = ("import fs from 'node:fs';import assert from 'node:assert/strict';"
                 "import * as routing from './web/routing.js';"
                 "const input=JSON.parse(fs.readFileSync(0,'utf8'));")
    result = subprocess.run(
        [executable, '--experimental-default-type=module', '--input-type=module',
         '-e', bootstrap + script],
        input=json.dumps(value), encoding='utf-8', capture_output=True, cwd=ROOT,
        timeout=40,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_router_avoids_boxes_and_matches_python_export(rotation):
    output = run_js("""
import {rotate} from './web/geometry.js';
const turn=p=>rotate(p,input).map(v=>v+250);
const a={point:turn([-180,0]),direction:rotate([1,0],input)};
const b={point:turn([180,0]),direction:rotate([-1,0],input)};
const obstacles=[{id:'block',box:[210,210,80,80]}];
const result=routing.avoidObstacles(a,b,obstacles,{page:{width:500,height:500}});
assert.deepEqual(result,routing.avoidObstacles(a,b,obstacles,{page:{width:500,height:500}}));
assert.ok(result.points.some(p=>p[0]<=198||p[0]>=302));
assert.ok(result.points.some(p=>p[1]<=198||p[1]>=302));
assert.ok(result.points.every((p,i)=>!i||!routing.crossesBox(result.points[i-1],p,[198,198,302,302])));
console.log(JSON.stringify({a,b,...result}));
""", rotation)
    assert output['points'] == route(output['a'], output['b'], output['vertices'])
    assert output['points'][0] == output['a']['point']
    assert output['points'][-1] == output['b']['point']
    assert len(output['vertices']) <= 100


@pytest.mark.parametrize('name', list(TEMPLATES))
def test_templates_keep_schema_connections_and_python_route_contract(name):
    scene = resolve_scene(load_template(name))
    result = run_js("""
const doc=structuredClone(input.document),before=JSON.stringify(doc);
const ids=new Set(doc.edges.map(e=>e.id));
const result=routing.routeDiagramEdges(doc,input.nodes,ids);
assert.equal(JSON.stringify(doc),before);
const changes=new Map(result.changes.map(c=>[c.id,c.vertices]));
for(const e of doc.edges)if(changes.has(e.id))e.vertices=changes.get(e.id);
const again=routing.routeDiagramEdges(doc,input.nodes,ids);
assert.equal(again.changes.length,0,'routing must be idempotent');
console.log(JSON.stringify({document:doc,...result}));
""", scene)
    document = result['document']
    assert validate_scene(document) == document
    resolved = resolve_scene(document)
    assert len(resolved['edges']) == len(scene['edges'])
    for old, new in zip(scene['document']['edges'], document['edges']):
        assert dict(new, vertices=old['vertices']) == old
    assert document['nodes'] == scene['document']['nodes']
    assert document['labels'] == scene['document']['labels']
    assert document['junctions'] == scene['document']['junctions']


def test_route_failure_limits_and_blocked_port_are_explicit():
    output = run_js("""
const a={point:[40,100],direction:[1,0]},b={point:[260,100],direction:[-1,0]};
const errors=[];
for(const [aa,bb,boxes,options] of [
  [a,b,[{id:'wall',box:[120,0,40,200]}],{page:{width:300,height:200}}],
  [a,b,[{id:'cover',box:[35,90,40,20]}],{}],
  [a,b,[{id:'middle',box:[120,80,40,40]}],{maxStates:0}],
  [{...a,direction:[1,1]},b,[],{}],
  [a,b,[],{page:{width:100,height:100}}],
]){try{routing.avoidObstacles(aa,bb,boxes,options);errors.push(null);}catch(e){errors.push(e.message);}}
console.log(JSON.stringify(errors));
""", None)
    assert len(output) == 5 and all(output)


def test_close_facing_ports_remain_straight_and_do_not_backtrack():
    run_js("""
const a={point:[100,100],direction:[1,0],nodeId:'a'};
const b={point:[102,100],direction:[-1,0],nodeId:'b'};
const result=routing.avoidObstacles(a,b,[
 {id:'a',box:[60,80,40,40]},{id:'b',box:[102,80,40,40]}],
 {page:{width:300,height:200}});
assert.deepEqual(result.points,[[100,100],[102,100]]);
assert.deepEqual(result.vertices,[]);console.log('true');
""", None)


def test_junction_and_same_side_ports_route_around_endpoint_devices():
    run_js("""
const a={point:[120,100],direction:[1,0],nodeId:'a'};
const b={point:[240,160],direction:[1,0],nodeId:'b'};
const boxes=[{id:'a',box:[70,70,50,60]},{id:'b',box:[190,130,50,60]}];
const result=routing.avoidObstacles(a,b,boxes,{page:{width:400,height:300}});
for(let i=2;i<result.points.length-2;i++)for(const o of boxes){
 const [x,y,w,h]=o.box;
 assert.ok(!routing.crossesBox(result.points[i-1],result.points[i],
   [x-12,y-12,x+w+12,y+h+12]));
}
const j=routing.avoidObstacles({point:[30,50],direction:[0,0]},b,boxes,
  {page:{width:400,height:300}});
assert.deepEqual(j.points[0],[30,50]);
console.log('true');
""", None)


def test_controller_commits_once_undo_redo_noop_and_cancels_stale_results():
    run_js("""
import {createEditor} from './web/editor/index.js';
globalThis.document={getElementById:()=>({}),querySelector:()=>null};
const editor=createEditor(),s=editor.state,c=editor.commands,messages=[];
Object.assign(c,{render(){},saveDraft(){},refresh:async()=>{},status:m=>messages.push(m),message:m=>messages.push(m),pipeActionsBusy:()=>false});
const node=(id,x,y,ports,box=[-20,-20,40,40])=>
  ({id,x,y,rotation:0,geometry:{box,ports}});
const nodes=[node('a',60,150,{out:{point:[20,0],direction:[1,0]}}),
 node('b',400,150,{in:{point:[-20,0],direction:[-1,0]}}),node('block',230,150,{})];
const edge={id:'e',source:{nodeId:'a',portId:'out'},
  target:{nodeId:'b',portId:'in'},vertices:[],width:1,color:'#111',head:true};
s.doc={nodes:nodes.map(({geometry,...n})=>n),edges:[edge],junctions:[],labels:[],page:{width:500,height:300}};
s.geometries=new Map(nodes.map(n=>[n.id,n.geometry]));
const original=structuredClone(s.doc);s.multiSelection=[{kind:'edge',id:'e'}];
await c.autoRoute();assert.equal(s.undo.length,1);
assert.ok(s.doc.edges[0].vertices.length);
assert.deepEqual(s.multiSelection,[{kind:'edge',id:'e'}]);
const changed=structuredClone(s.doc);
await c.autoRoute();assert.equal(s.undo.length,1,'no-op does not add history');
c.history('undo');assert.deepEqual(s.doc,original);c.history('redo');assert.deepEqual(s.doc,changed);
c.history('undo');const pending=c.autoRoute();s.revision++;await pending;
assert.deepEqual(s.doc,original);
const cancel=c.autoRoute();s.routingSession=null;await cancel;
assert.deepEqual(s.doc,original);
const geometryChange=c.autoRoute();s.geometries=new Map(s.geometries);
await geometryChange;assert.deepEqual(s.doc,original);
const loading=c.autoRoute();s.documentLoad={};await loading;
assert.deepEqual(s.doc,original);s.documentLoad=null;
// Failure on the second pipe must not apply the already-computed first route.
s.doc.edges.push({...structuredClone(edge),id:'bad',target:{junctionId:'blocked'}});
s.doc.junctions.push({id:'blocked',x:230,y:150});s.multiSelection=[];
const failed=structuredClone(s.doc);await c.autoRoute('all');
assert.deepEqual(s.doc,failed);
assert.equal(s.routingSession,null);assert.ok(messages.some(m=>m.includes('未应用')));
console.log('true');
""", None)


def test_mounted_valve_follows_parent_and_rejects_new_collisions():
    run_js("""
import {mountedNodes} from './web/geometry.js';
const valve={id:'v',type:'globe_valve',x:150,y:100,rotation:0,
 mount:{edgeId:'e',at:.5,reverse:false},
 geometry:{box:[-10,-10,20,20],ports:{
 in:{point:[-10,0],direction:[-1,0]},
 out:{point:[10,0],direction:[1,0]}}}};
const doc={page:{width:400,height:300},nodes:[valve],labels:[],
 junctions:[{id:'a',x:50,y:100},{id:'b',x:250,y:100},
 {id:'c',x:150,y:150},{id:'d',x:150,y:250}],
 edges:[{id:'e',source:{junctionId:'a'},target:{junctionId:'b'},vertices:[]},
 {id:'other',source:{junctionId:'c'},target:{junctionId:'d'},vertices:[]}]};
const changes=[{id:'e',vertices:[[50,200],[250,200]]}];
assert.throws(()=>routing.validateRoutedMounts(doc,[valve],changes),
 /挡住管路/);
doc.edges.pop();routing.validateRoutedMounts(doc,[valve],changes);
const moved=mountedNodes({...doc,edges:[{...doc.edges[0],
 vertices:changes[0].vertices}]},[valve])[0];
assert.equal(moved.y,200);assert.equal(moved.x,150);
const block={id:'block',x:150,y:200,rotation:0,geometry:{box:[-15,-15,30,30]}};
assert.throws(()=>routing.validateRoutedMounts(doc,[valve,block],changes),
 /重叠/);
assert.throws(()=>routing.validateRoutedMounts({...doc,page:{width:400,height:205}},
 [valve],changes),/超出页面/);
console.log('true');
""", None)


def test_many_obstacles_remain_clear_and_export_all_formats():
    result = run_js("""
const a={point:[40,150],direction:[1,0]};
const b={point:[760,150],direction:[-1,0]};
const boxes=Array.from({length:8},(_,i)=>({id:String(i),
 box:[100+i*75,80+(i%2)*40,35,90]}));
const result=routing.avoidObstacles(a,b,boxes,{page:{width:800,height:350}});
for(let i=1;i<result.points.length;i++)for(const o of boxes){
 const [x,y,w,h]=o.box;
 assert.ok(!routing.crossesBox(result.points[i-1],result.points[i],
 [x-12,y-12,x+w+12,y+h+12]));
}
console.log(JSON.stringify(result));
""", None)
    document = validate_scene(dict(
        schemaVersion=1, page=dict(width=800, height=350),
        nodes=[], labels=[], junctions=[dict(id='a', x=40, y=150),
                                      dict(id='b', x=760, y=150)],
        edges=[dict(id='pipe', source=dict(junctionId='a'),
                    target=dict(junctionId='b'), vertices=result['vertices'])],
    ))
    assert resolve_scene(document)['edges'][0]['points'] == result['points']
    for fmt, signature in [('svg', b'<?xml'), ('png', b'\x89PNG'), ('pdf', b'%PDF')]:
        assert export_scene(document, fmt).startswith(signature)


def test_router_clamps_boundary_eps_and_ignores_unrelated_mount_collisions():
    run_js("""
// Point within EPS outside page border must clamp into grid instead of indexOf === -1.
const a={point:[-1e-10,100],direction:[0,0]};
const b={point:[300+1e-10,100],direction:[0,0]};
const res=routing.avoidObstacles(a,b,[{id:'mid',box:[130,80,40,40]}],
  {page:{width:300,height:200}});
assert.ok(res.points.length>=4 && res.points.every(p=>p.every(Number.isFinite)));
// Unrelated pre-existing edge/valve collision must not block routing a separate edge.
const valve={id:'v',type:'globe_valve',x:150,y:100,rotation:0,
  mount:{edgeId:'e1',at:.5,reverse:false},
  geometry:{box:[-10,-10,20,20],ports:{
    in:{point:[-10,0],direction:[-1,0]},out:{point:[10,0],direction:[1,0]}}}};
const doc={page:{width:400,height:400},nodes:[valve],labels:[],
  junctions:[
    {id:'a',x:50,y:100},{id:'b',x:250,y:100},
    {id:'c',x:150,y:50},{id:'d',x:150,y:150},
    {id:'p',x:50,y:320},{id:'q',x:350,y:320}],
  edges:[
    {id:'e1',source:{junctionId:'a'},target:{junctionId:'b'},vertices:[]},
    {id:'e2',source:{junctionId:'c'},target:{junctionId:'d'},vertices:[]},
    {id:'e3',source:{junctionId:'p'},target:{junctionId:'q'},vertices:[]}]};
routing.validateRoutedMounts(doc,[valve],[{id:'e3',vertices:[[200,320]]}]);
console.log('true');
""", None)
