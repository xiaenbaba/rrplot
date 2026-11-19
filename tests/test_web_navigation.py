"""画布定位只改变视图，包含标签和完整走线，并拒绝过期响应。"""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene


def navigation_scenario(code, document=None, **options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript navigation check")
    root = Path(__file__).resolve().parents[1]
    document = document or load_template("evi_ftvi")
    modules = {
        name: "data:text/javascript;base64,"
        + base64.b64encode(root.joinpath("web", name + ".js").read_bytes()).decode()
        for name in ["geometry", "styles"]
    }
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8')),o=input.options;
const geometry=await import(input.modules.geometry);
const styles=await import(input.modules.styles);
const elements=new Map(),listeners=new Map(),storage=new Map(),calls=[],pending=[];
const messages=[],statuses=[],results=[];let measurements=0,removed=0;
function element(id){if(!elements.has(id))elements.set(id,{
  clientWidth:o.width||800,clientHeight:o.height||600,open:false,events:new Map(),
  addEventListener:(n,f)=>listeners.set(id+':'+n,f),
  setAttribute(){},append(){},remove(){removed++;},
  querySelectorAll:()=>[],showModal(){this.open=true;}});return elements.get(id);}
const labelElements=input.resolved.labels.map(l=>({dataset:{id:l.id},
  querySelector:()=>({cloneNode:()=>({setAttribute(){},querySelectorAll:()=>[],
    getBBox:()=>({x:-35,y:-12,width:70,height:24})})})}));
element('diagram').querySelectorAll=()=>labelElements;
const context=vm.createContext({...geometry,...styles,input,structuredClone,
  messages,statuses,results,pending,calls,storage,listeners,options:o,
  window:{addEventListener:(n,f)=>listeners.set('window:'+n,f)},
  document:{getElementById:element,body:element('body'),
    createElementNS:()=>{measurements++;return element(Symbol());},
    querySelector:()=>[...elements.values()].find(e=>e.open)||null,
    addEventListener:(n,f)=>listeners.set('document:'+n,f)},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),
    removeItem:k=>storage.delete(k)},ResizeObserver:class{observe(){}},
  send:async(path,body)=>{calls.push({path,body:structuredClone(body)});
    if(o.wait)await new Promise((resolve,reject)=>pending.push({resolve,reject}));
    if(o.fail)throw Error('定位服务失败');return structuredClone(input.resolved);},
  tick:async()=>{for(let i=0;i<10;i++)await Promise.resolve();}});
const source=(await import('node:module')).createRequire(input.path)
  ('../tests/web_editor_harness.cjs').loadEditorSource(input.path);
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.resolved.document);api=send;
  message=m=>messages.push(m);status=m=>statuses.push(m);
  dirty=true;undo=[{old:true}];redo=[{new:true}];pendingDownload={version:revision};
  multiSelection=structuredClone(options.selection||[]);selection=multiSelection.at(-1);
  saveDraft();globalThis.snapshot=()=>structuredClone({doc,dirty,undo,redo,selection,
    multiSelection,revision,request,pendingDownload,ownedDraft,
    stored:Object.fromEntries(storage),view,viewRevision,navigationSession});
  globalThis.click=action=>listeners.get('document:click')({target:{
    closest:s=>s==='[data-action]'?{dataset:{action}}:null}});`,context);
const before=vm.runInContext('snapshot()',context);
await vm.runInContext('(async()=>{'+input.code+'})()',context);
console.log(JSON.stringify({before,final:vm.runInContext('snapshot()',context),
  results,messages,statuses,calls,measurements,removed}));
"""
    completed = subprocess.run(
        [executable, "--input-type=module", "-e", script],
        input=json.dumps(
            dict(
                code=code,
                resolved=resolve_scene(document),
                modules=modules,
                options=options,
                path=str(root / "web/app.js"),
            )
        ),
        encoding="utf-8",
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def assert_only_view_changed(output):
    before, after = output["before"], output["final"]
    assert {
        k: v
        for k, v in after.items()
        if k in before and k not in {"view", "viewRevision"}
    } == {k: v for k, v in before.items() if k not in {"view", "viewRevision"}}
    assert output["measurements"] == output["removed"]


def assert_visible(box, view, size=(800, 600)):
    x, y, width, height = box
    pad_x, pad_y = view["w"] * 32 / size[0], view["h"] * 32 / size[1]
    assert view["x"] + pad_x <= x + 1e-7
    assert view["y"] + pad_y <= y + 1e-7
    assert x + width <= view["x"] + view["w"] - pad_x + 1e-7
    assert y + height <= view["y"] + view["h"] - pad_y + 1e-7


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("scope", ["fit-content", "fit-selection"])
def test_templates_fit_without_changing_document_draft_or_selection(name, scope):
    document = load_template(name)
    selection = [
        {"kind": kind, "id": item["id"]}
        for kind, key in [("node", "nodes"), ("junction", "junctions")]
        for item in document[key]
    ]
    output = navigation_scenario(
        """
      await click(options.scope);
      results.push(pageContentBoxes(input.resolved));
    """,
        document,
        scope=scope,
        selection=selection,
    )
    assert_only_view_changed(output)
    assert output["calls"][0]["body"]["document"] == output["before"]["doc"]
    # All template labels attach to devices or pipes except a free branch note.
    if scope == "fit-content":
        for box in output["results"][0]:
            assert_visible(box, output["final"]["view"])
    assert output["final"]["view"]["w"] / output["final"]["view"]["h"] == (
        pytest.approx(800 / 600)
    )
    assert len(output["calls"]) == 1


def test_selected_group_includes_labels_internal_pipes_and_state_points_only():
    document = load_template("evi_ftvi")
    edge = document["edges"][0]
    document["labels"].extend(
        [
            dict(id="state", edgeId=edge["id"], at=0.5, x=20, y=-150, text="状态"),
            dict(id="far", x=5000, y=6000, text="远处文字"),
        ]
    )
    selection = [
        {"kind": "node", "id": edge[k]["nodeId"]} for k in ["source", "target"]
    ]
    output = navigation_scenario(
        """
      await click('fit-selection');
      const targets=styleTargets(doc,multiSelection);
      results.push(targets);results.push(pageContentBoxes(input.resolved,new Set([
        ...multiSelection.map(r=>r.kind+':'+r.id),
        ...targets.edges.map(id=>'edge:'+id),...targets.labels.map(id=>'label:'+id)])));
    """,
        document,
        selection=selection,
    )
    assert_only_view_changed(output)
    assert edge["id"] in output["results"][0]["edges"]
    assert "state" in output["results"][0]["labels"]
    assert "far" not in output["results"][0]["labels"]
    for box in output["results"][1]:
        assert_visible(box, output["final"]["view"])
    assert output["final"]["view"]["w"] < 5000


@pytest.mark.parametrize(
    "kind,key", [("edge", "edges"), ("label", "labels"), ("junction", "junctions")]
)
def test_individual_pipe_label_or_junction_can_be_focused(kind, key):
    document = load_template("evi_ftvi")
    ref = dict(kind=kind, id=document[key][0]["id"])
    output = navigation_scenario(
        "await click('fit-selection');", document, selection=[ref]
    )
    assert_only_view_changed(output)
    assert output["final"]["view"] != output["before"]["view"]
    assert not any(output["messages"])


def test_off_page_text_and_wide_complete_pipe_are_not_clipped():
    document = load_template("evi_ftvi")
    document["labels"].append(dict(id="far", x=-7000, y=-6000, text="页面外文字"))
    document["edges"][0]["vertices"] = [[12000, 10000]]
    output = navigation_scenario(
        """
      await click('fit-content');results.push(pageContentBoxes(input.resolved));
    """,
        document,
    )
    assert_only_view_changed(output)
    for box in output["results"][0]:
        assert_visible(box, output["final"]["view"])
    assert output["final"]["view"]["w"] > 19000


def test_empty_document_fits_page_without_request():
    document = load_template("evi_ftvi")
    for key in ["nodes", "edges", "labels", "junctions"]:
        document[key] = []
    output = navigation_scenario("await click('fit-content');", document)
    assert_only_view_changed(output)
    assert output["calls"] == [] and "图纸为空" in output["statuses"][-1]


def test_selection_required_and_missing_object_does_not_move_view():
    output = navigation_scenario("await click('fit-selection');")
    assert output["calls"] == [] and "请先选择" in output["messages"][-1]
    output = navigation_scenario(
        "await click('fit-selection');", selection=[dict(kind="node", id="missing")]
    )
    assert output["before"] == output["final"]
    assert any(output["messages"])


@pytest.mark.parametrize(
    "interruption",
    [
        "revision++;",
        "zoom(.85);",
        "fit();",
        "view.x+=30;updateView();",
        "svg.clientWidth=500;",
        "drag={};",
        "$('preview-dialog').showModal();",
        "multiSelection=[];selection=null;",
    ],
)
def test_pending_focus_does_not_override_edits_navigation_or_selection(interruption):
    output = navigation_scenario(
        """
      const operation=click('fit-selection');await tick();
    """
        + interruption
        + "results.push(snapshot());pending[0].resolve();await operation;",
        wait=True,
        selection=[dict(kind="node", id="compressor")],
    )
    assert output["final"]["view"] == output["results"][0]["view"]
    assert output["measurements"] == 0
    assert not any(output["messages"])


def test_duplicate_request_is_ignored_and_later_scope_wins():
    output = navigation_scenario(
        """
      const first=click('fit-content');await tick();await click('fit-content');
      const later=click('fit-selection');await tick();
      pending[1].resolve();await later;results.push(snapshot());
      pending[0].resolve();await first;
    """,
        wait=True,
        selection=[dict(kind="edge", id="pipe-1")],
    )
    assert len(output["calls"]) == 2
    assert output["final"] == output["results"][0]


def test_failure_keeps_view_and_all_document_state():
    output = navigation_scenario("await click('fit-content');", fail=True)
    assert output["final"] == output["before"]
    assert output["messages"][-1] == "定位服务失败"


@pytest.mark.parametrize(
    "busy",
    ["drag", "placement", "pendingPort", "reconnect", "pageLayoutBusy", "spaceDown"],
)
def test_focus_does_not_interrupt_other_editor_operations(busy):
    output = navigation_scenario(busy + "=true;await click('fit-content');")
    assert not output["calls"] and output["final"]["view"] == output["before"]["view"]


@pytest.mark.parametrize(
    "boxes,width,height",
    [
        ([], 800, 600),
        ([[0, 0, -1, 2]], 800, 600),
        ([[None, 0, 1, 2]], 800, 600),
        ([[0, 0, 1, 2]], 60, 600),
        ([[0, 0, 1, 2]], 800, 0),
    ],
)
def test_invalid_bounds_and_too_small_canvas_reject_without_changing_view(
    boxes, width, height
):
    output = navigation_scenario(
        """
      try{fitViewport(options.boxes,options.width,options.height);}
      catch(error){results.push(error.message);}
    """,
        boxes=boxes,
        width=width,
        height=height,
    )
    assert output["results"] and output["final"] == output["before"]


@pytest.mark.parametrize("width,height", [(800, 600), (300, 900), (1200, 120)])
def test_point_focus_has_finite_centered_view_and_screen_margin(width, height):
    output = navigation_scenario(
        """
      results.push(fitViewport([[123,-456,0,0]],options.width,options.height));
    """,
        width=width,
        height=height,
    )
    view = output["results"][0]
    assert view["x"] + view["w"] / 2 == pytest.approx(123)
    assert view["y"] + view["h"] / 2 == pytest.approx(-456)
    assert view["w"] >= 100 and view["w"] / view["h"] == pytest.approx(width / height)
    assert_visible([123, -456, 0, 0], view, (width, height))
