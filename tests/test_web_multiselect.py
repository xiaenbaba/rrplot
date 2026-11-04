"""真实选择事件支持多条管路，且批量样式、删除、移动保持图结构。"""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, validate_scene
from rrplot.scene_renderer import export_scene

ROOT = Path(__file__).resolve().parents[1]


def run_script(script, value):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript multiselect check")
    modules = {name: "data:text/javascript;base64," + base64.b64encode(
        ROOT.joinpath("web", name + ".js").read_bytes()).decode()
        for name in ("styles", "document", "geometry")}
    bootstrap = ("import fs from 'node:fs';import vm from 'node:vm';"
                 "const input=JSON.parse(fs.readFileSync(0,'utf8'));"
                 "const styles=await import(input.modules.styles),"
                 "edits=await import(input.modules.document),"
                 "geometry=await import(input.modules.geometry);")
    output = subprocess.run([executable, "--input-type=module", "-e",
                             bootstrap + script],
                            input=json.dumps(dict(value=value, modules=modules,
                                                  app=str(ROOT / "web/app.js"))),
                            encoding="utf-8", capture_output=True)
    assert output.returncode == 0, output.stderr
    return json.loads(output.stdout)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_arbitrary_pipe_selection_styles_and_deletes_only_chosen_pipes(name):
    document = load_template(name)
    pipes = [document["edges"][0]["id"], document["edges"][-1]["id"]]
    for index, pipe in enumerate(pipes):
        document["labels"].append(dict(id=f"multi-state-{index}", edgeId=pipe, at=.3,
                                       x=10, y=-14, text=f"P{index}"))
    document = validate_scene(document)
    script = """
const document=input.value.document, refs=input.value.pipes.map(id=>({kind:'edge',id}));
const styled=styles.applyStyles(document,refs,'selection',{
  edges:{color:'#24768c',width:2.8},labels:{size:18}});
const removed=edits.deleteSelection(styled,refs);
const moved=edits.translateSelection(document,refs,[30,20]);
console.log(JSON.stringify({styled,removed,moved,original:document}));
"""
    output = run_script(script, dict(document=document, pipes=pipes))
    assert output["original"] == output["moved"] == document
    styled, removed = output["styled"], output["removed"]
    validate_scene(styled)
    validate_scene(removed)
    for old, new in zip(document["edges"], styled["edges"]):
        assert new == (dict(old, color="#24768c", width=2.8)
                       if old["id"] in pipes else old)
    assert [edge["points"] for edge in resolve_scene(styled)["edges"]] == [
        edge["points"] for edge in resolve_scene(document)["edges"]]
    assert styled["nodes"] == removed["nodes"] == document["nodes"]
    assert styled["junctions"] == removed["junctions"] == document["junctions"]
    assert all(label["size"] == 18 for label in styled["labels"]
               if label.get("edgeId") in pipes)
    assert {e["id"] for e in removed["edges"]} == {
        e["id"] for e in document["edges"]} - set(pipes)
    assert removed["labels"] == [label for label in styled["labels"]
                                 if label.get("edgeId") not in pipes]
    assert export_scene(styled, "svg").startswith(b"<?xml")


def test_registered_selection_events_preserve_mixed_multiselect_and_single_handles():
    """Use actual listeners to catch primary-selection and double-click regressions."""
    script = r"""
const listeners=new Map(), highlights=new Map();
const elements=new Map();
function element(id){
  if(!elements.has(id)) elements.set(id,{
    addEventListener:(name,handler)=>{if(id==='diagram')listeners.set(name,handler);},
    focus(){},setPointerCapture(){},hasPointerCapture(){return false;},
    classList:{remove(){},toggle(){}},
    querySelectorAll:selector=>selector.includes('vertex')?[]:[...highlights.values()],
    querySelector:()=>null,contains:()=>false});
  return elements.get(id);
}
const context=vm.createContext({structuredClone,...geometry,...edits,...styles,
  document:{getElementById:element,addEventListener(){},querySelector:()=>null,
    body:{classList:{remove(){},add(){}}}},
  window:{addEventListener(){}},ResizeObserver:class{observe(){}},
  input:input.value});
const source=fs.readFileSync(input.app,'utf8').replace(/^import .*;\r?$/gm,'')
  .replace('void init();','');
vm.runInContext(source,context);
vm.runInContext("doc=structuredClone(input);render=()=>{};renderInspector=()=>{};"
  +"renderVertices=()=>{};world=()=>[0,0];status=()=>{};",context);
function snapshot(){return JSON.parse(vm.runInContext(
  'JSON.stringify({selection,multiSelection,doc,drag})',context));}
function click(kind,id,shift=false){
  const key=kind+':'+id;
  if(!highlights.has(key))highlights.set(key,{dataset:{kind,id},
    classList:{toggle:(name,on)=>{highlights.get(key).selected=on;}}});
  const hit=highlights.get(key);
  listeners.get('pointerdown')({button:0,pointerId:1,shiftKey:shift,
    target:{closest:()=>hit},preventDefault(){}});
  return snapshot();
}
const states=[];
states.push(click('edge','discharge'));
states.push(click('edge','suction',true));
states.push(click('edge','discharge')); // Plain click on chosen pipe retains group.
states.push(click('edge','suction',true)); // Toggle off, leaving one pipe.
states.push(click('node','comp',true)); // Mixed selection, primary is node.
states.push(click('edge','discharge')); // Never use primary node as a pipe.
states.push(click('edge','to-evap')); // A new pipe replaces the group.
const highlighted=[...highlights.values()].filter(e=>e.selected).map(e=>e.dataset);
listeners.get('dblclick')({shiftKey:true,
  target:{closest:()=>highlights.get('edge:to-evap')}});
const shiftedDouble=snapshot();
// Real renderer must exit before accessing primary node or pipe geometry.
vm.runInContext(source.slice(source.indexOf('function renderVertices()'),
  source.indexOf('function field(')),context);
vm.runInContext("setSelection('node','comp');setSelection('edge','suction',true);"
  +"renderVertices();",context);
console.log(JSON.stringify({states,highlighted,shiftedDouble,final:snapshot()}));
"""
    original = load_template("evi_ftvi")
    output = run_script(script, original)
    states = output["states"]

    def edge(identity):
        return dict(kind="edge", id=identity)

    assert states[0]["multiSelection"] == [edge("discharge")]
    assert states[1]["multiSelection"] == [edge("discharge"), edge("suction")]
    assert states[2]["multiSelection"] == states[1]["multiSelection"]
    assert states[3]["multiSelection"] == [edge("discharge")]
    assert states[4]["multiSelection"] == [
        edge("discharge"), dict(kind="node", id="comp")]
    assert states[5]["multiSelection"] == states[4]["multiSelection"]
    assert states[6]["multiSelection"] == [edge("to-evap")]
    assert output["highlighted"] == [edge("to-evap")]
    assert all(state["doc"] == original for state in states)
    assert output["shiftedDouble"]["doc"] == output["final"]["doc"] == original
    assert all(state["drag"] is None for state in states)


@pytest.mark.parametrize("start,end", [([0, 0], [100, 100]),
                                     ([100, 100], [0, 0])])
def test_box_selection_requires_whole_pipe_and_keeps_shifted_selection(start, end):
    script = """
const {start,end}=input.value;
const candidates=[{kind:'edge',id:'whole',box:[10,10,80,80]},
  {kind:'edge',id:'crossing',box:[-20,40,150,0]},
  {kind:'edge',id:'outside',box:[110,20,10,10]},
  {kind:'edge',id:'straight',box:[20,40,70,0]},
  {kind:'node',id:'whole',box:[40,40,20,20]}];
const refs=geometry.selectInBox(candidates,start,end,[{kind:'edge',id:'outside'}]);
console.log(JSON.stringify(refs));
"""
    refs = run_script(script, dict(start=start, end=end))
    assert refs == [dict(kind="edge", id="outside"), dict(kind="edge", id="whole"),
                    dict(kind="edge", id="straight"), dict(kind="node", id="whole")]
