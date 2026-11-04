"""正式预览的缩放、资源释放、并发和真实事件分发。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, validate_scene
from rrplot.scene_renderer import export_scene


def preview_scenario(**options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript preview check")
    document = options.pop("document", load_template("evi_ftvi"))
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8')),o=input.options;
const elements=new Map(),listeners=new Map(),observers=new Map(),storage=new Map();
const calls=[],urls=[],revoked=[],messages=[],statuses=[];let release,arrive;
const gate=new Promise(resolve=>release=resolve);
const reached=new Promise(resolve=>arrive=resolve);
const element=id=>{if(!elements.has(id))elements.set(id,{
  id,style:{},open:false,hidden:false,disabled:false,textContent:'',
  clientWidth:800,clientHeight:600,scrollLeft:0,scrollTop:0,
  addEventListener:(name,handler)=>listeners.set(id+':'+name,handler),
  removeAttribute(name){delete this[name];},showModal(){this.open=true;},
  close(){this.open=false;},getBoundingClientRect(){return{left:10,top:20};}});
  return elements.get(id);};
const viewport=element('preview-viewport'),image=element('preview-image');
image.naturalWidth=o.zeroSize?0:Math.floor(input.document.page.width*.96);
image.naturalHeight=Math.floor(input.document.page.height*.96);
image.getBoundingClientRect=()=>{
  const width=parseFloat(image.style.width)||image.naturalWidth;
  const height=parseFloat(image.style.height)||image.naturalHeight;
  return {width,height,left:30+Math.max(0,(viewport.clientWidth-40-width)/2)
    -viewport.scrollLeft,top:40+Math.max(0,(viewport.clientHeight-40-height)/2)
    -viewport.scrollTop};};
for(const [key,axis] of [['scrollLeft','width'],['scrollTop','height']]){
  let offset=0;Object.defineProperty(viewport,key,{get:()=>offset,set:value=>{
    const size=parseFloat(image.style[axis])||0;
    const client=axis==='width'?viewport.clientWidth:viewport.clientHeight;
    offset=Math.min(Math.max(0,size+40-client),Math.max(0,value));}});
}
async function phase(stage){
  if(o.waitAt===stage&&calls.length===1){arrive();await gate;}
  if(o.failAt===stage)throw new Error('测试 '+stage+' 失败');
}
image.decode=()=>phase('decode');
const context=vm.createContext({input,structuredClone,Blob,
  document:{getElementById:element,body:{},querySelector:()=>o.otherModal?{}:
    [...elements.values()].find(e=>e.open)||null,
    addEventListener:(name,handler)=>listeners.set('document:'+name,handler)},
  window:{addEventListener:(name,handler)=>listeners.set('window:'+name,handler)},
  localStorage:{setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),
    removeItem:k=>storage.delete(k)},ResizeObserver:class{
      constructor(callback){this.callback=callback;}
      observe(target){observers.set(target.id,this.callback);}},
  URL:{createObjectURL:()=>{const url='blob:'+urls.length;urls.push(url);return url;},
    revokeObjectURL:url=>revoked.push(url)},
  send:async(path,body)=>{calls.push({path,body:structuredClone(body)});
    await phase('api');return new Blob(['svg-preview']);},
  showMessage:text=>messages.push(text),setStatus:text=>statuses.push(text)});
const source=fs.readFileSync(input.path,'utf8').replace(/^import .*;\r?$/gm,'')
  .replace('void init();','');
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.document);dirty=input.options.clean!==true;
  api=send;message=showMessage;status=setStatus;saveDraft();`,context);
if(o.busy)vm.runInContext(o.busy+'={};',context);
const state=()=>JSON.parse(vm.runInContext(
  'JSON.stringify({doc,revision,dirty,undo,redo,view,previewSession})',context));
const ui=()=>({open:element('preview-dialog').open,src:image.src||null,
  hidden:image.hidden,style:{...image.style},label:element('preview-scale').textContent,
  disabled:element('preview-open').disabled,plus:element('preview-plus').disabled,
  minus:element('preview-minus').disabled,error:element('preview-message').textContent,
  retryHidden:element('preview-retry').hidden,rect:image.getBoundingClientRect(),
  scroll:[viewport.scrollLeft,viewport.scrollTop]});
const click=action=>listeners.get('document:click')({target:{closest:selector=>
  selector==='[data-action]'?{dataset:{action}}:null}});
const before=state(),draftBefore=[...storage];
const operation=click('preview');let during=null;
if(o.waitAt){
  await reached;during={state:state(),ui:ui()};
  await click('preview');
  if(o.close){await click('close-preview');
    listeners.get('preview-dialog:close')();}
  if(o.edit)vm.runInContext(`doc.title='后续修改';doc.nodes[0].x+=10;
    revision++;dirty=true;saveDraft();`,context);
  if(o.reopen){await click('preview');
    // A queued close event from the previous opening cannot close this one.
    listeners.get('preview-dialog:close')();}
  release();
}
await operation;
const first={state:state(),ui:ui(),urls:[...urls],revoked:[...revoked]};
if(o.retry){o.failAt=null;await click('retry-preview');}
const steps=[];
for(const command of o.commands||[]){
  if(command==='resize'){
    viewport.clientWidth=400;viewport.clientHeight=300;
    observers.get('preview-viewport')();
  }else if(command==='wheel'||command==='scroll'||command==='zero-wheel'){
    let prevented=false;
    listeners.get('preview-viewport:wheel')({ctrlKey:command!=='scroll',
      deltaY:command==='zero-wheel'?0:-100,clientX:410,clientY:320,
      preventDefault(){prevented=true;}});
    steps.push({command,prevented,state:state(),ui:ui()});continue;
  }else if(command==='escape'){
    element('preview-dialog').close();listeners.get('preview-dialog:close')();
  }else await click(command);
  steps.push({command,state:state(),ui:ui()});
}
console.log(JSON.stringify({before,after:state(),during,first,steps,ui:ui(),calls,
  urls,revoked,messages,statuses,draftBefore,draftAfter:[...storage]}));
"""
    completed = subprocess.run(
        [executable, "--input-type=module", "-e", script],
        input=json.dumps(dict(document=document, options=options,
                              path=str(Path(__file__).resolve().parents[1]
                                       / "web/app.js"))),
        encoding="utf-8", capture_output=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_preview_all_templates_use_snapshot_and_keep_document_and_draft(name):
    document = load_template(name)
    output = preview_scenario(document=document)
    call, = output["calls"]
    assert call["path"] == "preview" and call["body"]["document"] == document
    assert validate_scene(call["body"]["document"]) == document
    assert export_scene(call["body"]["document"]).startswith(b"<?xml")
    session = output["after"].pop("previewSession")
    output["before"].pop("previewSession")
    assert output["after"] == output["before"]
    assert output["draftAfter"] == output["draftBefore"]
    assert session["ready"] and not session["loading"] and session["fit"]
    assert float(output["ui"]["style"]["width"][:-2]) <= 760
    assert float(output["ui"]["style"]["height"][:-2]) <= 560


def test_zoom_actual_size_fit_and_resize_keep_canvas_view_separate():
    output = preview_scenario(commands=["preview-actual", "preview-plus",
                                        "preview-minus", "resize", "preview-fit"])
    actual, larger, smaller, resized, fitted = output["steps"]
    assert actual["ui"]["label"] == smaller["ui"]["label"] == "100%"
    assert larger["ui"]["label"] == "125%"
    assert resized["ui"]["label"] == "100%"
    assert fitted["state"]["previewSession"]["fit"]
    assert float(fitted["ui"]["style"]["width"][:-2]) <= 360
    assert float(fitted["ui"]["style"]["height"][:-2]) <= 260
    assert all(step["state"]["view"] == output["before"]["view"]
               for step in output["steps"])
    assert output["draftBefore"] == output["draftAfter"]


def test_fit_recomputes_on_window_resize_and_manual_zoom_has_limits():
    fitted = preview_scenario(commands=["resize"])
    assert float(fitted["ui"]["style"]["height"][:-2]) <= 260
    enlarged = preview_scenario(commands=["preview-plus"] * 30)
    assert enlarged["ui"]["label"] == "800%" and enlarged["ui"]["plus"]
    reduced = preview_scenario(commands=["preview-minus"] * 30)
    assert reduced["ui"]["label"] == "10%" and reduced["ui"]["minus"]


def test_ctrl_wheel_zooms_around_cursor_and_ordinary_wheel_keeps_scale():
    output = preview_scenario(commands=["preview-actual", "preview-plus",
                                        "wheel", "scroll", "zero-wheel"])
    before = output["steps"][1]["ui"]["rect"]
    wheel, scroll, zero = output["steps"][2:]
    after = wheel["ui"]["rect"]
    for axis, point, length in (("left", 410, "width"), ("top", 320, "height")):
        assert (point - before[axis]) / before[length] == pytest.approx(
            (point - after[axis]) / after[length])
    assert wheel["prevented"] and not scroll["prevented"] and not zero["prevented"]
    assert wheel["ui"]["label"] == scroll["ui"]["label"] == zero["ui"]["label"]


@pytest.mark.parametrize("stage", ["api", "decode"])
def test_pending_preview_is_single_and_close_discards_late_response(stage):
    output = preview_scenario(waitAt=stage, close=True)
    assert output["during"]["ui"]["disabled"]
    assert output["during"]["state"]["previewSession"]["loading"]
    assert len(output["calls"]) == 1
    assert output["after"]["previewSession"] is None and not output["ui"]["open"]
    assert output["urls"] == output["revoked"]
    assert not output["ui"]["disabled"]


@pytest.mark.parametrize("stage", ["api", "decode"])
def test_old_response_cannot_replace_new_preview_after_close_edit_and_reopen(stage):
    output = preview_scenario(waitAt=stage, close=True, edit=True, reopen=True)
    assert len(output["calls"]) == 2
    assert output["calls"][0]["body"]["document"] == output["before"]["doc"]
    assert output["calls"][1]["body"]["document"] == output["after"]["doc"]
    session = output["after"]["previewSession"]
    assert session["ready"] and session["version"] == output["after"]["revision"]
    assert output["ui"]["src"] == session["url"]
    assert session["url"] not in output["revoked"]


@pytest.mark.parametrize("stage", ["api", "decode"])
def test_failed_preview_keeps_work_and_can_retry(stage):
    output = preview_scenario(failAt=stage, retry=True)
    assert output["first"]["state"]["previewSession"]["error"]
    assert "失败" in output["first"]["ui"]["error"]
    assert not output["first"]["ui"]["retryHidden"]
    assert output["after"]["previewSession"]["ready"] and output["ui"]["open"]
    assert output["after"]["doc"] == output["before"]["doc"]
    assert output["draftAfter"] == output["draftBefore"]
    assert len(output["calls"]) == 2


@pytest.mark.parametrize("stage", ["api", "decode"])
def test_changed_document_never_displays_stale_preview(stage):
    output = preview_scenario(waitAt=stage, edit=True)
    assert not output["after"]["previewSession"]["ready"]
    assert "图纸已变化" in output["ui"]["error"]
    assert output["urls"] == output["revoked"]
    assert output["ui"]["hidden"]


@pytest.mark.parametrize("close", ["close-preview", "escape"])
def test_closing_ready_preview_releases_image_and_preserves_clean_state(close):
    output = preview_scenario(clean=True, commands=[close])
    assert output["after"] == output["before"]
    assert output["urls"] == output["revoked"]
    assert output["ui"]["hidden"] and output["ui"]["src"] is None


@pytest.mark.parametrize("busy", ["drag", "placement", "pendingPort", "reconnect",
                                  "pageLayoutBusy"])
def test_unfinished_interaction_blocks_preview(busy):
    output = preview_scenario(busy=busy)
    assert output["calls"] == [] and output["messages"]
    assert not output["ui"]["open"]


def test_other_modal_and_broken_image_cannot_open_a_ready_preview():
    blocked = preview_scenario(otherModal=True)
    assert not blocked["ui"]["open"] and blocked["calls"] == []
    broken = preview_scenario(zeroSize=True)
    assert broken["after"]["previewSession"]["error"]
    assert not broken["after"]["previewSession"]["ready"]
    assert broken["urls"] == broken["revoked"]
