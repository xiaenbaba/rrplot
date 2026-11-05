"""真实快捷键监听器的工具分发、编辑保护和帮助窗口。"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import load_template


def shortcut_scenario(code, **options):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional editor shortcut check")
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const elements=new Map(),listeners=new Map(),results=[],messages=[],calls=[];
const storage=new Map(Object.entries(input.options.storage||{}));
let failRead=!!input.options.failRead,failWrite=!!input.options.failWrite;
function element(id){if(!elements.has(id))elements.set(id,{
  open:false,addEventListener:(n,f)=>listeners.set(id+':'+n,f),
  showModal(){this.open=true;},
  close(){this.open=false;},contains:t=>!!t?.inCanvas,
  matches:()=>false,classList:{remove(){}}});return elements.get(id);}
const context=vm.createContext({input,structuredClone,results,messages,calls,
  document:{body:element('body'),getElementById:element,
    querySelector:()=>[...elements.values()].find(e=>e.open)||null,
    addEventListener:(n,f)=>listeners.set('document:'+n,f)},
  window:{addEventListener:(n,f)=>listeners.set('window:'+n,f)},
  localStorage:{getItem:k=>{if(failRead)throw Error('blocked');return storage.get(k);},
    setItem:(k,v)=>{if(failWrite)throw Error('full');storage.set(k,v);}},
  failStorage:(read,write)=>{failRead=read;failWrite=write;},storage,
  ResizeObserver:class{observe(){}},element,listeners});
const source=fs.readFileSync(input.path,'utf8').replace(/^import .*;\r?$/gm,'')
  .replace('void init();','');
vm.runInContext(source,context);
vm.runInContext(`doc=structuredClone(input.document);render=()=>{};
  status=()=>{};message=m=>messages.push(m);
  undo=[{before:true}];redo=[{after:true}];dirty=true;ownedDraft='draft';
  multiSelection=[{kind:'node',id:doc.nodes[0].id}];selection=multiSelection[0];
  copyToClipboard=()=>calls.push('copy');pasteClipboard=()=>calls.push('paste');
  globalThis.snapshot=()=>structuredClone({doc,mode,selection,multiSelection,
    dirty,undo,redo,revision,request,view,ownedDraft,placement,pendingPort,reconnect,
    helpOpen:$('help-dialog').open});
  globalThis.key=async(key,options={})=>{
    const targets={body:document.body,canvas:svg,
      child:{inCanvas:true,matches:()=>false},
      input:{matches:()=>true},toolbar:{matches:()=>false},
      editable:{matches:()=>false,isContentEditable:true}};
    let prevented=false;
    await listeners.get('window:keydown')({key,ctrlKey:false,metaKey:false,
      altKey:false,shiftKey:false,repeat:false,isComposing:false,...options,
      target:targets[options.target||'canvas'],preventDefault(){prevented=true;}});
    return prevented;};
  globalThis.click=action=>listeners.get('document:click')({target:{
    closest:s=>s==='[data-action]'?{dataset:{action}}:null}});`,context);
await vm.runInContext('(async()=>{'+input.code+'})()',context);
console.log(JSON.stringify({results,messages,calls,stored:Object.fromEntries(storage),
  enabled:vm.runInContext('singleKeyShortcuts',context),
  checked:element('single-key-shortcuts').checked,
  note:element('shortcut-preference-status').textContent,
  state:vm.runInContext('snapshot()',context)}));
"""
    output = subprocess.run(
        [executable, "--input-type=module", "-e", script],
        input=json.dumps(dict(code=code, document=load_template("evi_ftvi"),
                             options=options,
                             path=str(Path(__file__).resolve().parents[1]
                                      / "web/app.js"))),
        encoding="utf-8", capture_output=True,
    )
    assert output.returncode == 0, output.stderr
    return json.loads(output.stdout)


@pytest.mark.parametrize("key,mode", [
    ("v", "select"), ("b", "box-select"), ("m", "move-all"),
    ("c", "connect"), ("j", "junction"), ("t", "text"),
])
def test_tool_shortcuts_change_mode_without_changing_document(key, mode):
    output = shortcut_scenario(
        f"results.push(snapshot(),await key('{key}'),snapshot());")
    before, prevented, after = output["results"]
    assert prevented and after["mode"] == mode
    for name in before:
        if name not in {"mode", "selection", "multiSelection"}:
            assert after[name] == before[name]
    if mode == "move-all":
        assert after["selection"] is None and after["multiSelection"] == []
    else:
        assert after["selection"] == before["selection"]
        assert after["multiSelection"] == before["multiSelection"]


@pytest.mark.parametrize("option", [
    "{target:'input'}", "{target:'editable'}", "{target:'toolbar'}",
    "{isComposing:true}", "{repeat:true}", "{shiftKey:true}",
    "{altKey:true}", "{defaultPrevented:true}",
])
def test_tool_keys_preserve_text_and_native_interactions(option):
    output = shortcut_scenario(
        "results.push(snapshot(),await key('t'," + option + "),snapshot());")
    assert output["results"][0] == output["results"][2]
    assert not output["results"][1]


@pytest.mark.parametrize("guard", [
    "placement='compressor'", "pendingPort={}", "reconnect={}", "drag={}",
    "spaceDown=true", "pageLayoutBusy=true", "$('export-dialog').showModal()",
])
def test_busy_operations_are_not_canceled_by_tool_or_help_keys(guard):
    output = shortcut_scenario(guard + ";results.push(snapshot());"
                              "results.push(await key('v'),await key('?'));"
                              "results.push(snapshot());")
    before, tool, help_key, after = output["results"]
    assert before == after and not tool and not help_key


@pytest.mark.parametrize("target", ["canvas", "body", "child"])
def test_capslock_letter_and_canvas_children_support_shortcuts(target):
    output = shortcut_scenario(
        f"results.push(await key('C',{{target:'{target}'}}));")
    assert output["results"] == [True] and output["state"]["mode"] == "connect"


@pytest.mark.parametrize("modifier", ["ctrlKey", "metaKey"])
def test_copy_paste_modifiers_keep_existing_shortcuts(modifier):
    output = shortcut_scenario(
        f"results.push(snapshot(),await key('c',{{{modifier}:true}}),"
        f"await key('v',{{{modifier}:true}}),snapshot());")
    assert output["calls"] == ["copy", "paste"]
    assert output["results"][0] == output["results"][-1]
    assert output["results"][1:3] == [True, True]


def test_question_opens_help_and_close_action_preserves_editor_state():
    output = shortcut_scenario("""
      const before=snapshot();results.push(before);
      results.push(await key('?',{shiftKey:true}));results.push(snapshot());
      results.push(await key('t'));await click('close-help');results.push(snapshot());
    """)
    before, opened, during, blocked, after = output["results"]
    assert opened and during["helpOpen"] and not blocked
    assert during == dict(before, helpOpen=True) and after == before


def test_help_header_works_without_loaded_document_and_tools_require_document():
    output = shortcut_scenario("""
      doc=null;results.push(await key('c'));await click('help');
      results.push(snapshot());
      await click('close-help');results.push(snapshot());
    """)
    assert not output["results"][0]
    assert output["results"][1]["helpOpen"] and not output["results"][2]["helpOpen"]
    assert output["state"]["doc"] is None and output["state"]["mode"] == "select"


def test_repeated_help_and_busy_header_do_not_interrupt_work():
    output = shortcut_scenario("""
      results.push(await key('?',{repeat:true}));placement='compressor';
      const before=snapshot();await click('help');results.push(before,snapshot());
    """)
    assert not output["results"][0]
    assert output["results"][1] == output["results"][2]
    assert "先完成当前操作" in output["messages"][-1]


def test_disable_single_keys_keeps_header_help_and_modifier_shortcuts():
    output = shortcut_scenario("""
      results.push(snapshot());await click('help');
      $('single-key-shortcuts').checked=false;
      listeners.get('single-key-shortcuts:change')();await click('close-help');
      for(const k of ['v','b','m','c','j','t','?'])results.push(await key(k));
      results.push(snapshot());await key('c',{ctrlKey:true});
      await key('v',{ctrlKey:true});await click('help');results.push(snapshot());
    """)
    assert output["results"][1:8] == [False] * 7
    assert output["results"][0] == output["results"][8]
    assert output["results"][9]["helpOpen"]
    assert output["calls"] == ["copy", "paste"]
    assert not output["enabled"] and not output["checked"]
    assert output["stored"]["rrplot-web-v1-single-key-shortcuts"] == "false"


@pytest.mark.parametrize("stored,enabled", [
    ("false", False), ("true", True), ("invalid", True), (None, True),
])
def test_preference_restores_on_page_load(stored, enabled):
    storage = {} if stored is None else {"rrplot-web-v1-single-key-shortcuts": stored}
    output = shortcut_scenario("results.push(await key('c'));", storage=storage)
    assert output["enabled"] is enabled
    assert output["results"] == [enabled]
    assert output["state"]["mode"] == ("connect" if enabled else "select")


def test_reenable_and_cross_tab_changes_preserve_document_and_history():
    output = shortcut_scenario("""
      results.push(snapshot());await click('help');
      $('single-key-shortcuts').checked=true;
      listeners.get('single-key-shortcuts:change')();await click('close-help');
      results.push(await key('c'));mode='select';
      storage.set(SHORTCUTS,'false');listeners.get('window:storage')({key:SHORTCUTS});
      results.push(await key('t'));storage.delete(SHORTCUTS);
      listeners.get('window:storage')({key:SHORTCUTS});results.push(await key('j'));
      mode='select';results.push(snapshot());
    """, storage={"rrplot-web-v1-single-key-shortcuts": "false"})
    assert output["results"][1:4] == [True, False, True]
    assert output["results"][0] == output["results"][4]
    assert output["enabled"] and output["checked"]


def test_storage_failures_keep_preference_working_for_current_page():
    output = shortcut_scenario("""
      results.push(await key('c'));mode='select';await click('help');
      $('single-key-shortcuts').checked=false;
      listeners.get('single-key-shortcuts:change')();await click('close-help');
      results.push(await key('t'));results.push(snapshot());await click('help');
    """, failRead=True, failWrite=True)
    assert output["results"][:2] == [True, False]
    assert not output["enabled"] and output["stored"] == {}
    assert "当前页面生效" in output["note"]


def test_unrelated_storage_change_does_not_change_shortcuts():
    output = shortcut_scenario("""
      storage.set(SHORTCUTS,'false');
      listeners.get('window:storage')({key:'unrelated'});
      results.push(await key('c'));
    """)
    assert output["enabled"] and output["results"] == [True]
