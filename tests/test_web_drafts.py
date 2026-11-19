"""使用实际前端函数验证本机草稿保护及恢复流程。"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, validate_scene
from rrplot.scene_renderer import export_scene

DRAFT = "rrplot-web-v1-draft"
HISTORY = DRAFT + "-history"


def saved(title, document=None):
    document = document or load_template("evi_ftvi")
    return {"time": 1700000000000, "document": {**document, "title": title}}


def draft_scenario(code, current=None, history=None, **options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript draft check")
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8')),o=input.options;
const storage=new Map(),elements=new Map(),listeners=new Map(),messages=[],results=[];
if(input.current!==null)storage.set('rrplot-web-v1-draft',JSON.stringify(input.current));
if(input.history!==null)storage.set('rrplot-web-v1-draft-history',JSON.stringify(input.history));
function element(id){if(!elements.has(id))elements.set(id,{
  open:false,hidden:false,textContent:'',children:[],events:new Map(),
  addEventListener(name,fn){this.events.set(name,fn);},
  append(...children){this.children.push(...children);},
  replaceChildren(){this.children=[];},showModal(){this.open=true;},
  close(value){this.open=false;if(value!==undefined)this.returnValue=value;
    const fn=this.events.get('close');this.events.delete('close');fn?.();}});
  return elements.get(id);}
let release,arrive;const gate=new Promise(r=>release=r);
const reached=new Promise(r=>arrive=r);
const context=vm.createContext({input,structuredClone,results,messages,
  window:{addEventListener:(n,f)=>listeners.set('window:'+n,f)},
  document:{getElementById:element,createElement:()=>element(Symbol()),body:{},
    querySelector:()=>[...elements.values()].find(e=>e.open)||null,
    addEventListener:(n,f)=>listeners.set('document:'+n,f)},
  localStorage:{getItem:k=>{if(o.readFail===k)throw Error('storage blocked');
      return storage.get(k)||null;},
    setItem:(k,v)=>{if(o.writeFail===k)throw Error('quota exceeded');storage.set(k,v);},
    removeItem:k=>storage.delete(k)},ResizeObserver:class{observe(){}},
  send:async(path,body)=>{if(o.wait){arrive();await gate;}
    if(o.apiFail)throw Error('invalid diagram');
    return{document:structuredClone(body.document),nodes:[],fontFamily:'serif'};},
  tell:m=>messages.push(m),element,listeners,storage,options:o,gate,reached,
  release:()=>release()});
const source=(await import('node:module')).createRequire(input.path)
  ('../tests/web_editor_harness.cjs').loadEditorSource(input.path);
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.document);api=send;message=tell;
  render=renderSaveState;fit=()=>{};
  globalThis.snapshot=()=>structuredClone({doc,dirty,revision,ownedDraft,draftError,
    restoringDraft,undo,redo,stored:Object.fromEntries(storage),
    bannerHidden:$('draft-banner').hidden,description:$('draft-description').textContent,
    header:$('draft-open').textContent,open:$('drafts-dialog').open,
    error:$('draft-error').textContent,summary:$('draft-summary').textContent,
    list:$('draft-list').children.map(e=>e.children.map(c=>c.textContent))});`,context);
await vm.runInContext('(async()=>{'+input.code+'})()',context);
console.log(JSON.stringify({results,messages,final:vm.runInContext('snapshot()',context)}));
"""
    path = Path(__file__).resolve().parents[1] / "web/app.js"
    completed = subprocess.run(
        [executable, "--input-type=module", "-e", script],
        input=json.dumps(
            dict(
                code=code,
                current=current,
                history=history,
                document=load_template("evi_ftvi"),
                options=options,
                path=str(path),
            )
        ),
        encoding="utf-8",
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_first_edit_archives_previous_session_but_continuous_edits_do_not():
    old = saved("上次未保存")
    output = draft_scenario(
        """
      dirty=true;saveDraft();results.push(snapshot());
      doc.title='继续修改';revision++;saveDraft();results.push(snapshot());
    """,
        current=old,
    )
    for state in output["results"]:
        assert json.loads(state["stored"][HISTORY]) == [old]
        assert json.loads(state["stored"][DRAFT])["document"] == state["doc"]
        assert state["ownedDraft"] == state["stored"][DRAFT]
    assert output["final"]["doc"]["title"] == "继续修改"


def test_history_is_deduplicated_and_capped_before_active_replacement():
    old = saved("旧草稿")
    history = [saved(str(i)) for i in range(5)]
    output = draft_scenario(
        "saveDraft();", current=old, history=[history[0], old, *history[1:]]
    )
    assert json.loads(output["final"]["stored"][HISTORY]) == [old, *history[:4]]


def test_same_document_does_not_create_redundant_history():
    output = draft_scenario(
        "saveDraft();", current=saved(load_template("evi_ftvi")["title"])
    )
    assert HISTORY not in output["final"]["stored"]


@pytest.mark.parametrize("owned", [False, True])
def test_clear_only_removes_owned_active_draft_and_preserves_history(owned):
    old, history = saved("旧草稿"), [saved("历史")]
    output = draft_scenario(
        ("saveDraft();" if owned else "") + "clearDraft();",
        current=old,
        history=history,
    )
    state = output["final"]
    assert (DRAFT not in state["stored"]) == owned
    assert json.loads(state["stored"][HISTORY]) == (
        [old, *history] if owned else history
    )


def test_clean_template_replacement_preserves_unrecovered_draft():
    old = saved("启动前草稿")
    output = draft_scenario(
        "await replaceDocument({...doc,title:'另一个模板'});", current=old
    )
    assert json.loads(output["final"]["stored"][DRAFT]) == old
    assert not output["final"]["dirty"]


@pytest.mark.parametrize(
    "key,kind",
    [(HISTORY, "write"), (DRAFT, "write"), (HISTORY, "read"), (DRAFT, "read")],
)
def test_storage_failure_preserves_old_active_and_reports_unsaved(key, kind):
    old, history = saved("不能丢失"), [saved("更早")]
    output = draft_scenario(
        "dirty=true;saveDraft();renderSaveState();",
        current=old,
        history=history,
        **{kind + "Fail": key},
    )
    assert json.loads(output["final"]["stored"][DRAFT]) == old
    assert output["final"]["draftError"] and output["final"]["dirty"]
    assert "草稿未保存" in output["messages"][0]
    if key == HISTORY:
        assert json.loads(output["final"]["stored"][HISTORY]) == history


def test_foreign_tab_draft_is_archived_before_next_edit_and_never_cleared():
    foreign = saved("其他标签页")
    output = draft_scenario(
        """
      saveDraft();storage.set(DRAFT,JSON.stringify(input.current));clearDraft();
      results.push(snapshot());saveDraft();
    """,
        current=foreign,
    )
    assert json.loads(output["results"][0]["stored"][DRAFT]) == foreign
    assert json.loads(output["final"]["stored"][HISTORY]) == [foreign]


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_list_button_restores_valid_template_and_preserves_previous_work(name):
    target, previous = saved("待恢复", load_template(name)), saved("现有图纸")
    output = draft_scenario(
        """
      doc=structuredClone(input.history[0].document);dirty=true;saveDraft();
      showDrafts();const before=snapshot();results.push(before);
      const operation=$('draft-list').children[1].children[3].events.get('click')();
      $('replace-dialog').close('replace');await operation;
    """,
        current=target,
        history=[previous],
    )
    final = output["final"]
    assert final["doc"] == target["document"]
    assert validate_scene(final["doc"]) == target["document"]
    assert export_scene(final["doc"], "svg").startswith(b"<?xml")
    assert final["dirty"] and not final["open"] and not final["restoringDraft"]
    assert previous["document"] in [
        s["document"] for s in json.loads(final["stored"][HISTORY])
    ]
    assert final["undo"] == final["redo"] == []


def test_canceling_dirty_recovery_keeps_current_work_and_drafts():
    output = draft_scenario(
        """
      dirty=true;saveDraft();showDrafts();results.push(snapshot());
      const operation=restoreDraft(input.current);
      $('replace-dialog').close('cancel');await operation;
    """,
        current=saved("旧图"),
    )
    before, after = output["results"][0], output["final"]
    assert before == after


def test_invalid_restore_retains_document_and_storage_and_shows_error():
    output = draft_scenario(
        """
      showDrafts();results.push(snapshot());await restoreDraft(input.current);
    """,
        current=saved("错误图纸"),
        apiFail=True,
    )
    before, after = output["results"][0], output["final"]
    assert after["doc"] == before["doc"] and after["stored"] == before["stored"]
    assert not after["dirty"] and after["open"] and "恢复失败" in after["error"]


@pytest.mark.parametrize(
    "interruption",
    [
        "closeDrafts();",
        "revision++;",
        "request++;",
        "$('drafts-dialog').events.get('cancel')();$('drafts-dialog').close();",
    ],
)
def test_late_restore_cannot_replace_document_after_cancel_or_new_revision(
    interruption,
):
    output = draft_scenario(
        """
      showDrafts();results.push(snapshot());const operation=restoreDraft(input.current);
      await reached;
    """
        + interruption
        + "release();await operation;",
        current=saved("晚到的图纸"),
        wait=True,
    )
    assert output["final"]["doc"] == output["results"][0]["doc"]
    assert output["final"]["stored"] == output["results"][0]["stored"]
    assert not output["final"]["dirty"] and not output["final"]["restoringDraft"]


def test_dismissed_banner_keeps_header_access_and_storage_events_refresh_list():
    output = draft_scenario(
        """
      renderDraftBanner();results.push(snapshot());actions['dismiss-draft']();
      actions.drafts();storage.set(DRAFT,JSON.stringify({...input.current,
        document:{...input.current.document,title:'另一个标签页的更新'}}));
      listeners.get('window:storage')({key:DRAFT});
    """,
        current=saved("<img onerror=alert(1)>"),
    )
    assert not output["results"][0]["bannerHidden"]
    assert output["results"][0]["header"] == "草稿 (1)"
    assert output["final"]["open"] and output["final"]["bannerHidden"]
    assert output["final"]["list"][0][0] == "另一个标签页的更新"


@pytest.mark.parametrize(
    "busy", ["drag", "placement", "pendingPort", "reconnect", "pageLayoutBusy"]
)
def test_draft_list_waits_until_active_interaction_finishes(busy):
    output = draft_scenario(busy + "={};showDrafts();", current=saved("旧图"))
    assert not output["final"]["open"] and output["messages"]


def test_malformed_entries_are_ignored_without_breaking_valid_history():
    good = saved("有效草稿")
    output = draft_scenario(
        "showDrafts();", current={"broken": True}, history=[None, {}, good]
    )
    assert len(output["final"]["list"]) == 1
    assert output["final"]["list"][0][0] == "有效草稿"


def test_duplicate_recovery_during_pending_request_is_ignored():
    output = draft_scenario(
        """
      showDrafts();const operation=restoreDraft(input.current);await reached;
      await restoreDraft(input.current);release();await operation;
    """,
        current=saved("唯一恢复"),
        wait=True,
    )
    assert output["final"]["doc"]["title"] == "唯一恢复"
    assert output["final"]["revision"] == 1
