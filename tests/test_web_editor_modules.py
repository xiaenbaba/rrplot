"""原生 ES 模块组装、状态隔离及跨控制器命令契约。"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_native_editor_modules_compose_bind_and_edit_without_global_aliases():
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional native editor module check")
    script = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=JSON.parse(fs.readFileSync(0,'utf8')),elements=new Map(),events=[];
function element(id){
  if(!elements.has(id))elements.set(id,{
    addEventListener:(...args)=>events.push([id,...args]),checked:false,
    value:'',style:{setProperty(){}},classList:{remove(){},toggle(){}},
    setAttribute(){},hidden:false
  });
  return elements.get(id);
}
globalThis.document={getElementById:element,querySelector:()=>null,
  addEventListener:(...args)=>events.push(['document',...args])};
globalThis.window={addEventListener:(...args)=>events.push(['window',...args])};
globalThis.localStorage={getItem:()=>null};
globalThis.ResizeObserver=class{observe(){}};
const {createEditor}=await import(pathToFileURL(path.join(root,'web/editor/index.js')));
assert.equal(events.length,0,'import must not register event handlers');
const a=createEditor(),b=createEditor();
assert.equal(events.length,0,'composition must not register event handlers');
assert.notEqual(a.state,b.state);
assert.notEqual(a.commands,b.commands);
for(const key of ['undo','redo','multiSelection','connectionVertices','geometries',
  'view','catalog','ports','inspectorGroups'])assert.notEqual(a.state[key],b.state[key],key);
assert.equal(globalThis.doc,undefined,'legacy aliases are test-harness only');
// Check every cross-controller command against the actually imported factories.
for(const file of fs.readdirSync(path.join(root,'web/editor'))){
  if(!file.endsWith('.js'))continue;
  const source=fs.readFileSync(path.join(root,'web/editor',file),'utf8');
  for(const match of source.matchAll(/commands\.([\w$]+)/g)){
    if(match[1]!=='actions')assert.equal(typeof a.commands[match[1]],'function',
      `${file}: unresolved command ${match[1]}`);
  }
}
a.bindEvents();
const count=events.length;
assert.ok(count>20,'real forms and gestures must be bound');
a.bindEvents();assert.equal(events.length,count,'binding must be idempotent');
for(const [key,action] of Object.entries(a.commands.actions))
  assert.equal(typeof action,'function',`unresolved page action ${key}`);
const effects=[];
Object.assign(a.commands,{render:()=>effects.push('render'),
  refresh:()=>effects.push('refresh'),saveDraft:()=>effects.push('draft'),
  status:()=>{},message:()=>{}});
const original={schemaVersion:1,title:'original',page:{width:100,height:100},
  nodes:[],edges:[],junctions:[],labels:[]};
a.state.doc=structuredClone(original);
a.commands.edit(()=>{a.state.doc.title='changed';});
assert.equal(a.state.undo.length,1);
assert.equal(a.state.revision,1);
assert.ok(a.state.dirty);
assert.deepEqual(effects,['draft','render','refresh']);
a.commands.history('undo',{deferRefresh:true});
assert.deepEqual(a.state.doc,original);
a.commands.history('redo',{deferRefresh:true});
assert.equal(a.state.doc.title,'changed');
assert.equal(b.state.doc,null);
assert.deepEqual(b.state.undo,[]);
// File loading calls the real session/selection ports after asynchronous resolve.
a.commands.api=async(_path,body)=>({document:structuredClone(body.document),
  nodes:[],fontFamily:'serif',features:[]});
a.commands.fit=()=>{};
assert.equal(await a.commands.replaceDocument(original,true),true);
assert.deepEqual(a.state.doc,original);
assert.deepEqual(a.state.undo,[]);
assert.deepEqual(a.state.redo,[]);
assert.equal(a.state.dirty,false);
"""
    result = subprocess.run(
        [executable, "--experimental-default-type=module", "--input-type=module",
         "-e", script],
        input=json.dumps(str(ROOT)), encoding="utf-8", capture_output=True,
    )
    assert result.returncode == 0, result.stderr
