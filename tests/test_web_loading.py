"""图纸载入的实际事件、取消和异步结果顺序保护。"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, validate_scene
from rrplot.scene_renderer import export_scene


def loading_scenario(code, name="evi_ftvi", **options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript loading check")
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8')),o=input.options;
const elements=new Map(),listeners=new Map(),storage=new Map(),calls=[],pending=[];
const messages=[],statuses=[],results=[];let id=0;
function element(key){if(!elements.has(key))elements.set(key,{
  open:false,hidden:false,textContent:'',value:'',events:new Map(),
  addEventListener(name,fn){this.events.set(name,fn);},showModal(){this.open=true;},
  close(value){this.open=false;this.returnValue=value;
    const fn=this.events.get('close');this.events.delete('close');fn?.();},
  classList:{remove(){}},click(){results.push('picker');}});return elements.get(key);}
const context=vm.createContext({input,structuredClone,messages,statuses,results,
  crypto:{randomUUID:()=>String(++id)},
  document:{getElementById:element,body:element('body'),
    querySelector:()=>[...elements.values()].find(e=>e.open)||null,
    addEventListener:(n,f)=>listeners.set('document:'+n,f)},
  window:{addEventListener:(n,f)=>listeners.set('window:'+n,f)},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),
    removeItem:k=>storage.delete(k)},ResizeObserver:class{observe(){}},
  send:async(path,body)=>{calls.push({path,body:structuredClone(body)});
    if(o.fail===path)throw Error('服务失败');
    if(o.wait===path)await new Promise((resolve,reject)=>{
      pending.push({resolve,reject});});
    if(path.startsWith('templates/'))return structuredClone(input.target);
    return{document:structuredClone(body.document),nodes:[],fontFamily:'serif',
      features:body.document.title==='过期' ? [] : ['edgeLabels']};},
  element,listeners,storage,pending,calls,options:o,
  tick:async()=>{for(let i=0;i<12;i++)await Promise.resolve();}});
const source=(await import('node:module')).createRequire(input.path)
  ('../tests/web_editor_harness.cjs').loadEditorSource(input.path);
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.original);api=send;
  message=m=>messages.push(m);status=m=>statuses.push(m);
  render=renderSaveState;fit=()=>{};edgeLabelsSupported=true;
  dirty=!!options.dirty;if(dirty)saveDraft();
  globalThis.snapshot=()=>structuredClone({doc,dirty,revision,undo,redo,
    edgeLabelsSupported,documentLoad,ownedDraft,stored:Object.fromEntries(storage),
    bannerHidden:$('load-banner').hidden,banner:$('load-description').textContent});
  globalThis.click=action=>listeners.get('document:click')({target:{
    closest:s=>s==='[data-action]'?{dataset:{action}}:null}});`,context);
await vm.runInContext('(async()=>{'+input.code+'})()',context);
console.log(JSON.stringify({results,messages,statuses,calls,
  final:vm.runInContext('snapshot()',context)}));
"""
    path = Path(__file__).resolve().parents[1] / "web/app.js"
    completed = subprocess.run(
        [executable, "--input-type=module", "-e", script],
        input=json.dumps(
            dict(
                code=code,
                original=load_template("evi_ftvi"),
                target=load_template(name),
                options=options,
                path=str(path),
            )
        ),
        encoding="utf-8",
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_template_load_validates_then_applies_complete_document(name):
    output = loading_scenario(
        "await loadTemplate({id:'target',title:'系统模板'});", name
    )
    state = output["final"]
    assert state["doc"] == validate_scene(load_template(name))
    assert export_scene(state["doc"], "svg").startswith(b"<?xml")
    assert [c["path"] for c in output["calls"]] == ["templates/target", "resolve"]
    assert state["bannerHidden"] and not state["dirty"]
    assert state["documentLoad"] is None and state["undo"] == state["redo"] == []


@pytest.mark.parametrize("stage", ["templates/target", "resolve"])
def test_edit_during_template_download_or_resolve_keeps_new_work(stage):
    output = loading_scenario(
        """
      const operation=loadTemplate({id:'target',title:'系统模板'});await tick();
      results.push(snapshot());doc.title='后续修改';revision++;dirty=true;saveDraft();
      pending[0].resolve();await operation;
    """,
        wait=stage,
    )
    assert not output["results"][0]["bannerHidden"]
    assert output["final"]["doc"]["title"] == "后续修改"
    assert output["final"]["dirty"] and output["final"]["ownedDraft"]
    assert output["final"]["revision"] == 1
    assert output["final"]["edgeLabelsSupported"]
    if stage.startswith("templates"):
        assert len(output["calls"]) == 1


@pytest.mark.parametrize("stage", ["templates/target", "resolve"])
def test_cancel_button_discards_pending_result_and_keeps_current_draft(stage):
    output = loading_scenario(
        """
      saveDraft();results.push(snapshot());
      const operation=loadTemplate({id:'target',title:'模板'});await tick();
      await click('cancel-load');pending[0].resolve();await operation;
    """,
        wait=stage,
    )
    assert output["final"]["doc"] == output["results"][0]["doc"]
    assert output["final"]["stored"] == output["results"][0]["stored"]
    assert output["final"]["revision"] == 0 and output["final"]["bannerHidden"]
    assert output["statuses"][-1] == "载入已取消 · 当前图纸保留"


@pytest.mark.parametrize("stage", ["templates/target", "resolve"])
def test_later_load_wins_even_if_first_download_or_resolve_finishes_last(stage):
    output = loading_scenario(
        """
      const first=loadTemplate({id:'target',title:'旧模板'});await tick();
      options.wait=null;
      await loadDocument(()=>({...doc,title:'新模板'}),'新模板','later');
      const before=snapshot();results.push(before);pending[0].resolve();await first;
    """,
        wait=stage,
    )
    assert output["final"] == output["results"][0]
    assert output["final"]["doc"]["title"] == "新模板"
    assert output["statuses"][-1] == "已载入：新模板"


def test_duplicate_template_load_is_ignored_during_request():
    output = loading_scenario(
        """
      const first=loadTemplate({id:'target',title:'模板'});await tick();
      await loadTemplate({id:'target',title:'模板'});
      pending[0].resolve();await first;
    """,
        wait="templates/target",
    )
    assert len(output["calls"]) == 2
    assert output["final"]["revision"] == 1


@pytest.mark.parametrize("answer", ["cancel", "replace"])
def test_dirty_confirmation_runs_before_download_and_preserves_cancel(answer):
    output = loading_scenario(
        """
      results.push(snapshot());const operation=loadTemplate({id:'target',title:'模板'});
      results.push(calls.length);$('replace-dialog').close(options.answer);
      await operation;
    """,
        dirty=True,
        answer=answer,
    )
    assert output["results"][1] == 0
    assert output["final"]["dirty"] == (answer == "cancel")
    if answer == "cancel":
        assert output["final"]["stored"] == output["results"][0]["stored"]
        assert not output["calls"]


@pytest.mark.parametrize("stage", ["templates/target", "resolve"])
def test_download_and_validation_failure_preserve_current_document_and_history(stage):
    output = loading_scenario(
        """
      results.push(snapshot());const operation=loadTemplate({id:'target',title:'模板'});
      $('replace-dialog').close('replace');await operation;
    """,
        dirty=True,
        fail=stage,
    )
    before, after = output["results"][0], output["final"]
    assert before["doc"] == after["doc"] and before["stored"] == after["stored"]
    assert after["dirty"] and after["bannerHidden"]
    assert output["messages"] == ["无法载入图纸：服务失败"]


@pytest.mark.parametrize("failure", [True, False])
def test_obsolete_request_cannot_clear_later_load_banner_or_report_old_error(failure):
    output = loading_scenario(
        """
      const first=loadTemplate({id:'target',title:'旧模板'});await tick();
      const later=loadTemplate({id:'other',title:'新模板'});await tick();
      results.push(snapshot());
      if(options.failure)pending[0].reject(Error('过期错误'));else pending[0].resolve();
      await first;results.push(snapshot());pending[1].resolve();await later;
    """,
        wait="resolve",
        failure=failure,
    )
    assert output["results"][0] == output["results"][1]
    assert not output["results"][1]["bannerHidden"]
    assert not any(output["messages"])


@pytest.mark.parametrize(
    "busy",
    ["drag", "placement", "pendingPort", "reconnect", "pageLayoutBusy", "spaceDown"],
)
def test_load_does_not_interrupt_active_editor_operation(busy):
    output = loading_scenario(busy + "=true;await click('new');")
    assert not output["calls"] and output["messages"]
    assert output["final"]["revision"] == 0


def test_new_button_uses_valid_empty_document():
    output = loading_scenario("await click('new');")
    document = validate_scene(output["final"]["doc"])
    assert document["title"] == "未命名图纸"
    assert all(document[key] == [] for key in ["nodes", "edges", "labels", "junctions"])


@pytest.mark.parametrize("change", [False, True])
def test_actual_json_file_event_guards_changes_during_file_read(change):
    output = loading_scenario(
        """
      let releaseFile;const file={name:'图纸.json',size:100,
        text:()=>new Promise(resolve=>releaseFile=resolve)};
      const target={files:[file],value:'chosen'};
      const operation=$('file-input').events.get('change')({target});await tick();
      results.push(target.value);
      if(options.change){doc.title='文件读取期间修改';dirty=true;revision++;saveDraft();}
      releaseFile(JSON.stringify(input.target));await operation;
    """,
        change=change,
    )
    assert output["results"][0] == ""
    assert output["final"]["dirty"] == change
    assert output["final"]["doc"]["title"] == (
        "文件读取期间修改" if change else load_template("evi_ftvi")["title"]
    )
    assert len(output["calls"]) == (0 if change else 1)


@pytest.mark.parametrize("problem", ["oversized", "malformed", "readFailure"])
def test_json_file_errors_do_not_replace_document_or_draft(problem):
    output = loading_scenario(
        """
      saveDraft();results.push(snapshot());
      await $('file-input').events.get('change')({target:{value:'chosen',files:[{
        name:'错误.json',size:options.problem==='oversized'?5000001:100,
        text:async()=>{if(options.problem==='readFailure')throw Error('读取失败');
          return '{bad json';}}]}});
    """,
        problem=problem,
    )
    assert output["final"]["doc"] == output["results"][0]["doc"]
    assert output["final"]["stored"] == output["results"][0]["stored"]
    assert output["messages"] and not output["calls"]


def test_stale_resolve_cannot_change_supported_features():
    output = loading_scenario(
        """
      const operation=loadDocument(()=>({...doc,title:'过期'}),'旧图','old');
      await tick();
      revision++;pending[0].resolve();await operation;
    """,
        wait="resolve",
    )
    assert output["final"]["edgeLabelsSupported"]
    assert output["final"]["doc"]["title"] != "过期"


@pytest.mark.parametrize("stage", ["templates/target", "resolve"])
@pytest.mark.parametrize("busy", ["drag", "pendingPort", "pageLayoutBusy"])
def test_started_interaction_prevents_pending_load_from_replacing_document(stage, busy):
    output = loading_scenario(
        """
      const operation=loadTemplate({id:'target',title:'模板'});await tick();
    """
        + busy
        + "=true;pending[0].resolve();await operation;",
        wait=stage,
    )
    assert output["final"]["doc"] == load_template("evi_ftvi")
    assert output["final"]["revision"] == 0


def test_edit_immediately_cancels_pending_load_banner_and_preserves_undo():
    output = loading_scenario(
        """
      const operation=loadTemplate({id:'target',title:'模板'});await tick();
      refresh=async()=>{};edit(()=>{doc.title='继续编辑';});results.push(snapshot());
      pending[0].resolve();await operation;
    """,
        wait="templates/target",
    )
    assert output["results"][0]["bannerHidden"]
    assert output["final"]["dirty"] and len(output["final"]["undo"]) == 1
    assert output["final"]["doc"]["title"] == "继续编辑"


def test_active_modal_blocks_new_load_without_canceling_pending_session():
    output = loading_scenario(
        """
      const operation=loadTemplate({id:'target',title:'模板'});await tick();
      $('checks-dialog').showModal();await click('new');results.push(snapshot());
      pending[0].resolve();await operation;
    """,
        wait="templates/target",
    )
    assert output["results"][0]["documentLoad"]["key"] == "template:target"
    assert output["final"]["revision"] == 0


def test_revision_change_while_confirmation_is_open_does_not_start_download():
    output = loading_scenario(
        """
      const operation=loadTemplate({id:'target',title:'模板'});
      doc.title='等待确认时的新图纸';revision++;saveDraft();
      $('replace-dialog').close('replace');await operation;
    """,
        dirty=True,
    )
    assert not output["calls"]
    assert output["final"]["dirty"]
    assert output["final"]["doc"]["title"] == "等待确认时的新图纸"


@pytest.mark.parametrize("field", ["title", "inspector", "search"])
def test_typing_in_document_fields_cancels_load_before_change_is_committed(field):
    output = loading_scenario(
        """
      const operation=loadTemplate({id:'target',title:'模板'});await tick();
      const target=options.field==='title' ? $('title') : {
        closest:selector=>options.field==='inspector' && selector==='#inspector'};
      listeners.get('document:input')({target});results.push(snapshot());
      pending[0].resolve();await operation;
    """,
        field=field,
        wait="templates/target",
    )
    canceled = field != "search"
    assert output["results"][0]["bannerHidden"] == canceled
    assert output["final"]["revision"] == (0 if canceled else 1)
