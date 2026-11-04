"""导出设置、输出尺寸、快照和失败重试的实际前端事件回归。"""
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, validate_scene
from rrplot.scene_renderer import export_scene


def export_scenario(**options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript export check")
    document = options.pop("document", load_template("evi_ftvi"))
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8')),o=input.options;
const elements=new Map(),listeners=new Map(),calls=[],files=[],messages=[],statuses=[];
const storage=new Map();let release,arrive;
const gate=new Promise(resolve=>release=resolve);
const reached=new Promise(resolve=>arrive=resolve);
const element=id=>{if(!elements.has(id))elements.set(id,{
  value:'',open:false,hidden:false,disabled:false,textContent:'',
  addEventListener:(name,handler)=>listeners.set(id+':'+name,handler),
  showModal(){this.open=true;},close(){this.open=false;}});return elements.get(id);};
const context=vm.createContext({input,structuredClone,Blob,
  document:{getElementById:element,body:{},querySelector:()=>o.otherModal?{}:
    [...elements.values()].find(e=>e.open)||null,
    addEventListener:(name,handler)=>listeners.set('document:'+name,handler)},
  window:{addEventListener:(name,handler)=>listeners.set('window:'+name,handler)},
  localStorage:{setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),
    removeItem:k=>storage.delete(k)},ResizeObserver:class{observe(){}},
  send:async(path,body)=>{
    calls.push({path,body:structuredClone(body)});
    if(o.wait&&calls.length===1){arrive();await gate;}
    if(o.fail){throw new Error('测试导出失败');}
    return new Blob(['export-file']);},
  downloadFile:(blob,name)=>files.push(name),
  showMessage:text=>messages.push(text),setStatus:text=>statuses.push(text)});
const source=fs.readFileSync(input.path,'utf8').replace(/^import .*;\r?$/gm,'')
  .replace('void init();','');
vm.runInContext(source,context);
element('export-format').value=o.format||'svg';
element('export-dpi').value=String(o.dpi??140);
vm.runInContext(`doc=structuredClone(input.document);dirty=input.options.clean!==true;
  api=send;download=downloadFile;message=showMessage;status=setStatus;
  saveDraft();`,context);
if(o.busy)vm.runInContext(o.busy+'={};',context);
const state=()=>JSON.parse(vm.runInContext(
  'JSON.stringify({doc,revision,dirty,undo,redo,saving,exporting,pendingDownload})',context));
const before=state(),draftBefore=[...storage];
await listeners.get('document:click')({target:{closest:selector=>
  selector==='[data-action]'?{dataset:{action:'export'}}:null}});
const settings={open:element('export-dialog').open,
  summary:element('export-summary').textContent,error:element('export-error').textContent,
  disabled:element('export-submit').disabled,pngHidden:element('export-png').hidden};
if(o.cancel)vm.runInContext('actions["close-export"]()',context);
let prevented=false,during=null;
if(!o.settingsOnly){
  const operation=listeners.get('export-form:submit')({
    preventDefault(){prevented=true;}});
  if(o.wait){
    await reached;
    during={...state(),openDisabled:element('export-open').disabled,
      formatDisabled:element('export-format').disabled,dpiDisabled:element('export-dpi').disabled,
      submitDisabled:element('export-submit').disabled};
    await listeners.get('export-form:submit')({preventDefault(){}});
    vm.runInContext('actions.export()',context);
    if(o.closeWhileWaiting)vm.runInContext('actions["close-export"]()',context);
    if(o.edit)vm.runInContext(`doc.title='后续修改';doc.nodes[0].x+=10;
      revision++;dirty=true;saveDraft();renderExportState();`,context);
    release();
  }
  await operation;
}
const afterFirst={...state(),error:element('export-error').textContent};
if(o.retry){o.fail=false;
  await listeners.get('export-form:submit')({preventDefault(){}});}
let unload=false;listeners.get('window:beforeunload')({preventDefault(){unload=true;}});
console.log(JSON.stringify({before,after:state(),afterFirst,settings,during,calls,files,
  messages,statuses,prevented,unload,draftBefore,draftAfter:[...storage],
  open:element('export-dialog').open,error:element('export-error').textContent,
  buttonDisabled:element('export-open').disabled,
  formatDisabled:element('export-format').disabled}));
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
@pytest.mark.parametrize("fmt", ["svg", "png", "pdf"])
def test_export_settings_send_valid_snapshot_and_expected_output_dimensions(name, fmt):
    document = load_template(name)
    output = export_scenario(document=document, format=fmt, dpi=200)
    call, = output["calls"]
    assert call["path"] == "export/" + fmt
    assert call["body"]["document"] == document
    assert call["body"]["dpi"] == (200 if fmt == "png" else 140)
    assert validate_scene(call["body"]["document"]) == document
    data = export_scene(call["body"]["document"], fmt, call["body"]["dpi"])
    if fmt == "png":
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == (document["page"]["width"] * 2,
                                   document["page"]["height"] * 2)
        assert f"{width} × {height}" in output["settings"]["summary"]
    else:
        assert data.startswith(b"<?xml" if fmt == "svg" else b"%PDF")
        assert output["settings"]["pngHidden"]
    assert output["files"] == [document["title"] + "." + fmt]
    assert output["before"] == output["after"]
    assert output["draftBefore"] == output["draftAfter"]
    assert output["unload"] and output["prevented"]
    assert not output["open"] and not output["buttonDisabled"]


@pytest.mark.parametrize("dpi", ["", "abc", "Infinity", 71, 601, 140.5])
def test_invalid_png_resolution_never_starts_request(dpi):
    output = export_scenario(format="png", dpi=dpi)
    assert output["settings"]["disabled"] and output["settings"]["error"]
    assert output["calls"] == [] and output["files"] == []
    assert output["before"] == output["after"] and output["open"]
    assert output["draftBefore"] == output["draftAfter"]


@pytest.mark.parametrize("dpi", [72, 140, 300, 600])
def test_supported_png_resolutions_have_matching_estimated_size(dpi):
    document = load_template("evi_ftvi")
    output = export_scenario(format="png", dpi=dpi)
    width = int(document["page"]["width"] * dpi / 100)
    height = int(document["page"]["height"] * dpi / 100)
    assert f"{width} × {height}" in output["settings"]["summary"]
    assert output["calls"][0]["body"]["dpi"] == dpi


def test_png_pixel_limit_can_be_resolved_by_lowering_resolution_or_using_vector():
    document = load_template("evi_ftvi")
    document["page"] = dict(width=4000, height=400)
    allowed = export_scenario(document=document, format="png", dpi=500)
    assert len(allowed["calls"]) == 1
    rejected = export_scenario(document=document, format="png", dpi=501)
    assert "4000 万" in rejected["settings"]["error"]
    assert rejected["calls"] == []
    for fmt in ("svg", "pdf"):
        output = export_scenario(document=document, format=fmt, dpi="invalid")
        assert len(output["calls"]) == 1 and not output["settings"]["error"]


@pytest.mark.parametrize("format", ["png", "svg", "pdf"])
def test_canceling_export_settings_does_not_change_document_or_draft(format):
    output = export_scenario(format=format, cancel=True)
    assert output["calls"] == [] and output["files"] == []
    assert output["before"] == output["after"]
    assert output["draftBefore"] == output["draftAfter"]
    assert not output["open"]


def test_export_failure_keeps_settings_for_retry_and_preserves_unsaved_work():
    output = export_scenario(format="png", dpi=300, fail=True, retry=True)
    assert output["afterFirst"]["error"] == "测试导出失败"
    assert output["before"] == output["after"]
    assert len(output["calls"]) == 2 and len(output["files"]) == 1
    assert output["calls"][0] == output["calls"][1]
    assert output["draftBefore"] == output["draftAfter"]
    assert not output["open"] and not output["buttonDisabled"]


@pytest.mark.parametrize("fail", [False, True])
def test_pending_export_is_single_and_snapshot_name_matches_original_document(fail):
    output = export_scenario(format="png", dpi=300, wait=True,
                             closeWhileWaiting=True, edit=True, fail=fail)
    assert all(output["during"][key] for key in (
        "exporting", "openDisabled", "formatDisabled", "dpiDisabled", "submitDisabled"))
    call, = output["calls"]
    assert call["body"]["document"] == output["before"]["doc"]
    assert output["after"]["doc"]["title"] == "后续修改"
    assert output["after"]["dirty"] and output["unload"]
    assert json.loads(output["draftAfter"][0][1])["document"] == output["after"]["doc"]
    assert not output["after"]["exporting"] and not output["buttonDisabled"]
    assert not output["formatDisabled"]
    if fail:
        assert output["files"] == [] and "测试导出失败" in output["messages"][-1]
    else:
        assert output["files"] == [output["before"]["doc"]["title"] + ".png"]
        assert "后续修改请重新导出" in output["statuses"][-1]


@pytest.mark.parametrize("busy", ["drag", "placement", "pendingPort", "reconnect",
                                  "pageLayoutBusy"])
def test_unfinished_interaction_blocks_export_settings(busy):
    output = export_scenario(busy=busy, settingsOnly=True)
    assert not output["settings"]["open"] and output["messages"]
    assert output["before"] == output["after"]


def test_other_modal_blocks_export_and_clean_document_stays_clean():
    blocked = export_scenario(otherModal=True, settingsOnly=True)
    assert not blocked["settings"]["open"]
    clean = export_scenario(clean=True)
    assert not clean["after"]["dirty"] and not clean["unload"]
    assert clean["draftBefore"] == clean["draftAfter"]
