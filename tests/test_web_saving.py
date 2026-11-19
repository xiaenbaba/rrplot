"""保存失败、取消与并发编辑不能清除未保存图纸或草稿。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, validate_scene
from rrplot.scene_renderer import export_scene


def save_scenario(**options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript save check")
    document = options.pop("document", load_template("evi_ftvi"))
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const scenario=input.options,events=[],downloads=[],messages=[],statuses=[];
const elements=new Map(),listeners=new Map(),storage=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,{
  addEventListener:(name,handler)=>listeners.set(id+':'+name,handler),
  hidden:false,disabled:false,textContent:''});return elements.get(id);};
let context,release,arrive;
const gate=new Promise(resolve=>release=resolve);
const reached=new Promise(resolve=>arrive=resolve);
async function phase(name){
  events.push(name);
  if(scenario.changeAt===name)vm.runInContext(
    'doc.title="保存期间的新修改";revision++;dirty=true;saveDraft();renderSaveState();',
    context);
  if(scenario.waitAt===name){arrive();await gate;}
  if(scenario.failAt===name){
    const error=new Error('failed '+name);
    error.name=scenario.errorName||'Error';throw error;
  }
}
let contents=null,pickerOptions=null;
const writable={write:async text=>{await phase('write');contents=text;},
  close:()=>phase('close'),abort:async()=>{
    events.push('abort');if(scenario.abortFails)throw new Error('failed abort');}};
const handle={name:'测试图纸.json',createWritable:async()=>{
  await phase('create');return writable;}};
const browser={addEventListener:(name,handler)=>listeners.set('window:'+name,handler)};
if(!scenario.fallback)browser.showSaveFilePicker=async options=>{
  pickerOptions=options;await phase('picker');return handle;};
context=vm.createContext({structuredClone,Blob,input,events,messages,statuses,
  window:browser,document:{getElementById:element,
    addEventListener:(name,handler)=>listeners.set('document:'+name,handler),
    querySelector:()=>scenario.modal?{}:null,body:{}},
  localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),
    removeItem:key=>{events.push('clear-draft');storage.delete(key);}},
  ResizeObserver:class{observe(){}},
  resolveAPI:async(path,body)=>{await phase('resolve');return{document:body.document};},
  downloadFile:(blob,name)=>{events.push('download');downloads.push({blob,name});}});
const source=(await import('node:module')).createRequire(input.path)
  ('../tests/web_editor_harness.cjs').loadEditorSource(input.path);
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.document);dirty=input.options.clean!==true;
  api=resolveAPI;download=downloadFile;status=text=>statuses.push(text);
  message=text=>messages.push(text);render=renderSaveState;saveDraft();
  renderSaveState();`,context);
const state=()=>JSON.parse(vm.runInContext(
  'JSON.stringify({doc,dirty,saving,pendingDownload,revision,undo,redo})',context));
function unloadBlocked(){let blocked=false;listeners.get('window:beforeunload')({
  preventDefault(){blocked=true;}});return blocked;}
const before=state(),storedBefore=[...storage],unloadBefore=unloadBlocked();
let operation;
if(scenario.via==='keyboard')operation=listeners.get('window:keydown')({
  key:'s',ctrlKey:true,target:{matches:()=>false},preventDefault(){events.push('prevent');}});
else if(scenario.via==='click')operation=listeners.get('document:click')({
  target:{closest:selector=>selector==='[data-action]'?{dataset:{action:'save'}}:null}});
else operation=vm.runInContext('actions.save()',context);
let during=null,afterDuplicate=null;
if(scenario.waitAt){
  await reached;during={...state(),buttonDisabled:element('save-json').disabled,
    stored:[...storage],unload:unloadBlocked()};
  await vm.runInContext('actions.save();actions["confirm-download"]();',context);
  afterDuplicate={...state(),events:[...events]};release();
}
await operation;
const saved=state(),storedSaved=[...storage];
const bannerVisible=!element('download-banner').hidden;
const unloadSaved=unloadBlocked();
if(scenario.after==='confirm')vm.runInContext('actions["confirm-download"]()',context);
if(scenario.after==='dismiss')vm.runInContext('actions["dismiss-download"]()',context);
if(scenario.after==='edit-confirm')vm.runInContext(
  'doc.title="下载后的新修改";revision++;dirty=true;saveDraft();'
  +'actions["confirm-download"]()',context);
if(scenario.after==='drag-confirm')vm.runInContext(
  'drag={};actions["confirm-download"]()',context);
const files=[];
for(const file of downloads)files.push({name:file.name,text:await file.blob.text()});
console.log(JSON.stringify({before,saved,after:state(),storedBefore,storedSaved,
  storedAfter:[...storage],unloadBefore,unloadSaved,unloadAfter:unloadBlocked(),
  during,afterDuplicate,events,messages,statuses,files,contents,pickerOptions,bannerVisible,
  finalBannerVisible:!element('download-banner').hidden,
  buttonDisabled:element('save-json').disabled}));
"""
    path = Path(__file__).resolve().parents[1] / "web/app.js"
    completed = subprocess.run([executable, "--input-type=module", "-e", script],
                               input=json.dumps(dict(document=document,
                                                     options=options, path=str(path))),
                               encoding="utf-8", capture_output=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("fallback", [False, True])
def test_save_round_trip_requires_write_or_download_confirmation(name, fallback):
    document = load_template(name)
    output = save_scenario(document=document, fallback=fallback, after="confirm")
    assert output["before"]["doc"] == output["saved"]["doc"] == document
    contents = output["files"][0]["text"] if fallback else output["contents"]
    assert validate_scene(json.loads(contents)) == document
    assert export_scene(json.loads(contents), "svg").startswith(b"<?xml")
    assert output["saved"]["dirty"] == fallback
    assert output["bannerVisible"] == fallback
    assert not output["after"]["dirty"] and not output["unloadAfter"]
    assert output["storedAfter"] == [] and not output["buttonDisabled"]
    assert output["before"]["undo"] == output["after"]["undo"] == []
    if fallback:
        assert output["storedSaved"] == output["storedBefore"]
        assert output["unloadSaved"]
    else:
        assert output["events"] == ["picker", "resolve", "create", "write", "close",
                                    "clear-draft"]
        assert output["pickerOptions"]["suggestedName"] == document["title"] + ".json"


@pytest.mark.parametrize("stage", ["picker", "resolve", "create", "write", "close"])
def test_save_failures_keep_document_draft_and_close_warning(stage):
    output = save_scenario(failAt=stage)
    assert output["saved"] == output["before"]
    assert output["storedSaved"] == output["storedBefore"]
    assert output["unloadSaved"] and not output["buttonDisabled"]
    assert output["files"] == [] and output["messages"] == [
        "保存 JSON 失败：failed " + stage]
    assert ("abort" in output["events"]) == (stage in ["write", "close"])


def test_canceling_picker_keeps_unsaved_state_without_starting_validation_or_download():
    output = save_scenario(failAt="picker", errorName="AbortError")
    assert output["events"] == ["picker"]
    assert output["messages"] == [] and output["files"] == []
    assert output["saved"] == output["before"]
    assert output["storedSaved"] == output["storedBefore"]
    assert output["unloadSaved"] and not output["buttonDisabled"]


@pytest.mark.parametrize("error", ["SecurityError", "NotSupportedError"])
def test_unavailable_native_picker_falls_back_without_claiming_saved(error):
    output = save_scenario(failAt="picker", errorName=error)
    assert output["events"] == ["picker", "resolve", "download"]
    assert output["saved"]["dirty"] and output["unloadSaved"]
    assert output["storedSaved"] == output["storedBefore"]
    assert output["bannerVisible"] and not output["messages"]


@pytest.mark.parametrize("stage", ["picker", "resolve", "write", "close"])
def test_edits_during_save_are_never_marked_saved_by_older_snapshot(stage):
    output = save_scenario(changeAt=stage)
    assert json.loads(output["contents"]) == output["before"]["doc"]
    assert output["saved"]["doc"]["title"] == "保存期间的新修改"
    assert output["saved"]["dirty"] and output["unloadSaved"]
    assert "clear-draft" not in output["events"]
    draft = json.loads(output["storedSaved"][0][1])["document"]
    assert draft == output["saved"]["doc"]


@pytest.mark.parametrize("stage", ["picker", "resolve", "write", "close"])
def test_pending_save_disables_button_and_rejects_duplicate_saves(stage):
    output = save_scenario(waitAt=stage)
    assert output["during"]["saving"] and output["during"]["buttonDisabled"]
    assert output["during"]["dirty"] and output["during"]["unload"]
    assert output["during"]["stored"] == output["storedBefore"]
    assert output["afterDuplicate"]["dirty"] and output["events"].count("picker") == 1
    assert output["events"].count("close") == 1
    assert not output["saved"]["dirty"] and not output["buttonDisabled"]


@pytest.mark.parametrize("after", ["dismiss", "edit-confirm", "drag-confirm"])
def test_download_dismissal_and_stale_confirmation_keep_new_unsaved_data(after):
    output = save_scenario(fallback=True, after=after)
    assert output["after"]["dirty"] and output["unloadAfter"]
    assert "clear-draft" not in output["events"]
    assert json.loads(output["storedAfter"][0][1])["document"] == output["after"]["doc"]
    if after == "edit-confirm":
        assert output["after"]["doc"]["title"] == "下载后的新修改"
        assert not output["finalBannerVisible"]


def test_fallback_snapshot_started_before_edit_cannot_confirm_new_document():
    output = save_scenario(fallback=True, changeAt="resolve", after="confirm")
    assert output["saved"]["dirty"] and not output["bannerVisible"]
    assert json.loads(output["files"][0]["text"]) == output["before"]["doc"]
    assert output["saved"] == output["after"]
    assert "clear-draft" not in output["events"]


def test_stream_abort_failure_does_not_hide_original_write_failure():
    output = save_scenario(failAt="write", abortFails=True)
    assert output["messages"] == ["保存 JSON 失败：failed write"]
    assert output["saved"] == output["before"]
    assert output["storedSaved"] == output["storedBefore"]


def test_saving_clean_template_preserves_an_older_recoverable_draft():
    output = save_scenario(clean=True)
    assert not output["saved"]["dirty"] and not output["unloadSaved"]
    assert output["storedSaved"] == output["storedBefore"]
    assert "clear-draft" not in output["events"]


@pytest.mark.parametrize("via", ["keyboard", "click"])
def test_registered_save_shortcut_and_button_open_picker_before_async_validation(via):
    output = save_scenario(via=via)
    assert output["events"].index("picker") < output["events"].index("resolve")
    assert not output["saved"]["dirty"]
    assert output["events"].count("picker") == 1
