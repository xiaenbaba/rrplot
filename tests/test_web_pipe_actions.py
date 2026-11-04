"""批量管路操作保留图结构，并作为单次编辑提交。"""
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
        pytest.skip("Node not installed; optional JavaScript pipe actions check")
    raw = ROOT.joinpath("web/document.js").read_bytes()
    module = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    bootstrap = ("import fs from 'node:fs';import vm from 'node:vm';"
                 "const input=JSON.parse(fs.readFileSync(0,'utf8'));"
                 "const edits=await import(input.module);")
    completed = subprocess.run([executable, "--input-type=module", "-e",
                                bootstrap + script],
                               input=json.dumps(dict(value=value, module=module,
                                                     app=str(ROOT / "web/app.js"))),
                               encoding="utf-8", capture_output=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("action", ["reverse", "clear-vertices"])
def test_batch_pipe_actions_preserve_connections_styles_and_state_labels(name, action):
    document = load_template(name)
    chosen = [document["edges"][0], document["edges"][-1]]
    for i, edge in enumerate(chosen):
        edge.update(vertices=[[200 + i * 50, 150], [250 + i * 50, 150]],
                    headAt=[.25, .75], linestyle="dashed", color="#336699")
        for j, at in enumerate([0, .3, 1]):
            document["labels"].append(dict(id=f"batch-{i}-{j}", edgeId=edge["id"],
                                           at=at, text="T", x=7, y=-14))
    document = validate_scene(document)
    before = resolve_scene(document)
    refs = [dict(kind="edge", id=edge["id"]) for edge in chosen]
    # Duplicate and non-pipe refs must not reverse twice or select more pipes.
    refs += [refs[0], dict(kind="node", id=document["nodes"][0]["id"]),
             dict(kind="edge", id="missing")]
    script = """
const {document,refs,action,routes}=input.value;
const result=edits.editSelectedEdges(document,refs,action,new Map(routes));
const twice=action==='clear-vertices'?edits.editSelectedEdges(result,refs,action):null;
console.log(JSON.stringify({result,twice,original:document}));
"""
    routes = [[e["id"], e["points"]] for e in before["edges"]]
    output = run_script(script, dict(document=document, refs=refs, action=action,
                                    routes=routes))
    assert output["original"] == document
    result = output["result"]
    assert validate_scene(json.loads(json.dumps(result))) == result
    after = resolve_scene(result)
    selected = {edge["id"] for edge in chosen}
    for collection in ("nodes", "junctions", "page", "title"):
        assert result[collection] == document[collection]
    for old, new, old_route, new_route in zip(document["edges"], result["edges"],
                                             before["edges"], after["edges"]):
        if old["id"] not in selected:
            assert new == old and new_route == old_route
        elif action == "reverse":
            assert new == dict(old, source=old["target"], target=old["source"],
                               vertices=list(reversed(old_route["points"][1:-1])))
            assert new_route["points"] == list(reversed(old_route["points"]))
        else:
            assert new == dict(old, vertices=[])
    for old, new, old_label, new_label in zip(document["labels"], result["labels"],
                                             before["labels"], after["labels"]):
        if action == "reverse" and old.get("edgeId") in selected:
            assert new == dict(old, at=1 - old["at"])
            assert new_label["position"] == pytest.approx(old_label["position"])
        else:
            assert new == old
    if action == "clear-vertices":
        assert output["twice"] == result
    assert export_scene(result, "svg").startswith(b"<?xml")


@pytest.mark.parametrize("failure", ["missing-route", "invalid-route",
                                     "vertex-limit", "action"])
def test_batch_failure_is_atomic_even_after_first_pipe_was_processed(failure):
    document = load_template("heat_pump")
    refs = [dict(kind="edge", id=e["id"]) for e in document["edges"][:2]]
    routes = [[ref["id"], [[0, 0], [10, 0], [10, 10]]] for ref in refs]
    action = "reverse"
    if failure == "missing-route":
        routes.pop()
    elif failure == "invalid-route":
        routes[-1][1] = [[0, 0], [100001, 0]]
    elif failure == "vertex-limit":
        routes[-1][1] = [[i, i % 2] for i in range(103)]
    else:
        action = "invalid"
    output = run_script("""
const {document,refs,action,routes}=input.value;
let error;try{edits.editSelectedEdges(document,refs,action,new Map(routes));}
catch(e){error=e.message;}
console.log(JSON.stringify({error,original:document}));
""", dict(document=document, refs=refs, action=action, routes=routes))
    assert output["error"]
    assert output["original"] == document


def test_inspector_buttons_commit_once_preserve_selection_and_support_history():
    document = load_template("heat_pump")
    scene = resolve_scene(document)
    script = r"""
const element={addEventListener(){},replaceChildren(){},append(){},dataset:{}};
const buttons=[];let modal=false;
const context=vm.createContext({structuredClone,...edits,input:input.value,buttons,
  document:{getElementById:()=>element,addEventListener(){},
    querySelector:()=>modal?{}:null,body:element},
  window:{addEventListener(){}},ResizeObserver:class{observe(){}}});
const source=fs.readFileSync(input.app,'utf8').replace(/^import .*;\r?$/gm,'')
  .replace('void init();','');
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.document);
  multiSelection=input.refs;selection=multiSelection.at(-1);
  render=()=>{};refresh=async()=>{};saveDraft=()=>{};
  status=()=>{};message=()=>{};html=()=>({append(){}});
  edgePoints=edge=>input.routes.find(([id])=>id===edge.id)[1];
  inspectorButton=(root,caption,click)=>{
    const button={caption,click,dataset:{}};buttons.push(button);return button;};
  renderPipeActions({append(){}},2);`,context);
const state=()=>JSON.parse(vm.runInContext(
  'JSON.stringify({doc,multiSelection,undo,redo,dirty,revision})',context));
const before=state();buttons[0].click();const reversed=state();
vm.runInContext("history('undo')",context);const undone=state();
vm.runInContext("history('redo')",context);const redone=state();
vm.runInContext('multiSelection=input.refs;selection=multiSelection.at(-1);',context);
buttons[1].click();const cleared=state();buttons[1].click();const noop=state();
const disabled=[];
for(const code of ['mode="connect"','mode="select";placement="compressor"',
  'placement=null;pendingPort={}','pendingPort=null;reconnect={}',
  'reconnect=null;drag={}','drag=null;spaceDown=true',
  'spaceDown=false;pageLayoutBusy=true']){
  vm.runInContext(code,context);const snapshot=state();
  const first=buttons.length;
  vm.runInContext('renderPipeActions({append(){}},2)',context);
  disabled.push(buttons.slice(first).every(b=>b.disabled));
  buttons[0].click();if(JSON.stringify(snapshot)!==JSON.stringify(state()))
    throw new Error('Busy action mutated document or history');
}
vm.runInContext('pageLayoutBusy=false',context);modal=true;
buttons[0].click();const protectedState=state();modal=false;
buttons.length=0;vm.runInContext('renderPipeActions({append(){}},2)',context);
const emptyResetDisabled=buttons[1].disabled;
vm.runInContext('multiSelection=[{kind:"node",id:"comp"}]',context);
buttons[0].click();const nodeOnly=state();
console.log(JSON.stringify({before,reversed,undone,redone,cleared,noop,
  disabled,protectedState,emptyResetDisabled,nodeOnly}));
"""
    refs = [dict(kind="edge", id=e["id"]) for e in document["edges"][:2]]
    routes = [[e["id"], e["points"]] for e in scene["edges"]]
    output = run_script(script, dict(document=document, refs=refs, routes=routes))
    assert output["before"]["undo"] == []
    assert len(output["reversed"]["undo"]) == 1
    assert output["reversed"]["multiSelection"] == refs
    assert output["undone"]["doc"] == document
    assert output["redone"]["doc"] == output["reversed"]["doc"]
    assert len(output["cleared"]["undo"]) == 2
    assert output["cleared"]["multiSelection"] == refs
    assert output["noop"] == output["cleared"] == output["protectedState"]
    assert output["nodeOnly"]["doc"] == output["cleared"]["doc"]
    assert len(output["nodeOnly"]["undo"]) == 2
    assert all(output["disabled"]) and output["emptyResetDisabled"]
