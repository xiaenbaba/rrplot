"""实际画布控制器与缓存组合：图元引用、端口局部更新及文字布局。"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_scene_reuses_glyphs_auxiliaries_and_unaffected_ports_with_attached_labels():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node not installed")
    script = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=JSON.parse(fs.readFileSync(0,'utf8'));
const load=name=>import(pathToFileURL(path.join(root,'web',name)));
const {createCanvasController}=await load('editor/canvas.js');
const {createViewportController}=await load('editor/viewport.js');
const {createEditorState}=await load('editor/state.js');
const operations=[];
let owner;
class Element {
  constructor(tag){this.tag=tag;this.childNodes=[];this.attrs={};
    this.ownerDocument=owner;this.namespaceURI='svg';
    this.classList={toggle(){}};}
  get firstChild(){return this.childNodes[0]||null;}
  get nextSibling(){const nodes=this.parentNode?.childNodes||[];
    return nodes[nodes.indexOf(this)+1]||null;}
  getAttribute(k){return this.attrs[k]??null;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  replaceChildren(){for(const n of this.childNodes)n.parentNode=null;
    this.childNodes=[];}
  remove(){if(this.parentNode){const p=this.parentNode;
    p.childNodes.splice(p.childNodes.indexOf(this),1);this.parentNode=null;}}
  insertBefore(n,next){
    if(n.tag==='fragment')for(const c of [...n.childNodes])this.insertBefore(c,next);
    else{n.remove();const i=next?this.childNodes.indexOf(next):this.childNodes.length;
      assert.ok(i>=0);this.childNodes.splice(i,0,n);n.parentNode=this;}
  }
  append(n){if(this.attrs['data-kind']==='label'&&n.tag==='rect')operations.push('write');
    this.insertBefore(n,null);}
  querySelector(){return null;}
  querySelectorAll(){return [];}
  getBBox(){let parent=this;while(parent.parentNode)parent=parent.parentNode;
    assert.equal(parent.tag,'svg','bounds must be read after fragment attachment');
    operations.push('read');return{x:10,y:20,width:30,height:15};}
  cloneNode(deep){const node=new Element(this.tag);node.attrs={...this.attrs};
    node.textContent=this.textContent;
    if(deep)for(const child of this.childNodes)node.append(child.cloneNode(true));
    return node;}
}
owner={createElementNS:(_,tag)=>new Element(tag),
  createDocumentFragment:()=>new Element('fragment')};
const svg=new Element('svg');
globalThis.document={getElementById:()=>svg};
const state=createEditorState();
const geometry={glyphId:'shared',image:'data:image/svg+xml;base64,PHN2Zy8+',
  box:[-10,-10,20,20],ports:{left:{point:[-10,0],direction:[-1,0]},
    right:{point:[10,0],direction:[1,0]}}};
const nodes=['a','b'].map((id,i)=>({id,title:'same glyph',type:'heat_exchanger',
  x:100+i*200,y:100,rotation:0,params:{},geometry}));
state.doc={page:{width:500,height:300},nodes,edges:[{id:'p',source:{nodeId:'a',portId:'right'},
  target:{nodeId:'b',portId:'left'},vertices:[],color:'#111',width:1,head:false}],
  junctions:[],labels:[{id:'l1',nodeId:'a',text:'boxed',x:0,y:20,size:10,ha:'center',boxed:true},
    {id:'l2',edgeId:'p',at:.5,text:'pipe',x:0,y:10,size:10,ha:'center',boxed:true}]};
let nodeReads=0;
const commands={$:()=>({checked:true}),renderHint(){},renderConnectionFeedback:()=>null,
  renderJunctionFeedback:()=>null,renderVertices(){},updateView(){},
  currentNodes:()=>{nodeReads++;return nodes;},selected:()=>false};
commands.shape=(tag,attrs={},parent=svg)=>{
  const e=new Element(tag);
  for(const[k,v]of Object.entries(attrs))if(v!==undefined)e.setAttribute(k,v);
  if(state.canvasPass&&parent===svg)state.canvasRenderer.place(e);else parent.append(e);
  return e;
};
Object.assign(commands,createViewportController(state,commands),createCanvasController(state,commands));
commands.updateView=()=>{};commands.renderHint=()=>{};commands.renderVertices=()=>{};
commands.renderCanvas();
assert.equal(nodeReads,1,'attached labels must reuse the current scene indexes');
assert.deepEqual(operations,['read','read','write','write']);
const byId=id=>svg.childNodes.find(n=>n.attrs['data-id']===id);
const a=byId('a'),b=byId('b'),bImage=b.childNodes.find(n=>n.tag==='use');
const defs=()=>svg.childNodes.filter(n=>n.tag==='defs'&&n.firstChild?.tag==='image');
assert.equal(defs().length,1,'same glyph must have one image definition');
const page=svg.childNodes.find(n=>n.attrs.class==='page');
const grid=svg.childNodes.find(n=>n.attrs.fill==='url(#grid-pattern)');
const bPort=b.childNodes.find(n=>n.attrs.class==='port');
assert.equal(JSON.parse(bPort.attrs['data-ref']).nodeId,'b',
  'cloned port hit targets must refer to their own device');
const useTarget=bImage.attrs.href.slice(1);
assert.equal(defs()[0].firstChild.attrs.id,useTarget);
operations.length=0;state.pendingPort={nodeId:'a',portId:'left'};
commands.renderCanvas();
assert.equal(byId('b'),b);assert.ok(b.childNodes.includes(bImage));
assert.ok(b.childNodes.includes(bPort),'choosing port A must retain B port DOM');
assert.ok(a.childNodes.some(n=>n.attrs.class==='port chosen'));
assert.ok(svg.childNodes.includes(page));assert.ok(svg.childNodes.includes(grid));
assert.deepEqual(operations,[],
  'unchanged label backgrounds must not be measured again');
// Same declared glyph with different bounds needs a distinct definition.
nodes[0].geometry={...geometry,box:[-20,-10,40,20]};
commands.renderCanvas();assert.equal(defs().length,2);
nodes[0].geometry={...geometry,glyphId:undefined};
commands.renderCanvas();assert.equal(defs().length,2,'legacy images remain supported');
nodes.shift();state.doc.edges=[];state.doc.labels=[];
commands.renderCanvas();assert.equal(defs().length,1,'unused glyphs must be released');
assert.equal(byId('a'),undefined);assert.equal(byId('b'),b);
// Ordinary redraws use the measured viewport; resize/zoom measure it again.
let widthReads=0;
Object.defineProperty(svg,'clientWidth',{get(){widthReads++;return 1000;}});
state.viewportWidth=800;
const view=createViewportController(state,commands);
view.updateView({measure:false});assert.equal(widthReads,0);
view.updateView();assert.equal(widthReads,1);assert.equal(state.viewportWidth,1000);
"""
    result = subprocess.run(
        [node, "--experimental-default-type=module", "--input-type=module",
         "-e", script],
        input=json.dumps(str(Path(__file__).resolve().parents[1])),
        encoding="utf-8", capture_output=True,
    )
    assert result.returncode == 0, result.stderr
