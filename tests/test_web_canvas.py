"""缓存实际保留 DOM 身份、层次顺序，删除对象后回收缓存。"""
from test_web_requests import run_module


def test_cached_groups_retain_children_update_position_and_remove_stale_nodes():
    result = run_module(
        "canvas.js",
        """
      class Element {
        constructor(tag){this.tag=tag;this.childNodes=[];this.attrs={};
          this.parentNode=null;}
        get firstChild(){return this.childNodes[0]||null;}
        get nextSibling(){const list=this.parentNode?.childNodes||[];
          return list[list.indexOf(this)+1]||null;}
        getAttribute(k){return this.attrs[k]??null;}
        setAttribute(k,v){this.attrs[k]=String(v);}
        replaceChildren(){for(const n of this.childNodes)n.parentNode=null;
          this.childNodes=[];}
        remove(){if(this.parentNode){const p=this.parentNode;
          p.childNodes.splice(p.childNodes.indexOf(this),1);this.parentNode=null;}}
        insertBefore(n,next){n.remove();
          const i=next?this.childNodes.indexOf(next):this.childNodes.length;
          if(i<0)throw Error('Missing reference');
          this.childNodes.splice(i,0,n);n.parentNode=this;}
      }
      const root=new Element('svg');root.namespaceURI='svg';
      root.ownerDocument={createElementNS:(ns,tag)=>new Element(tag)};
      const r=module.createCanvasRenderer(root);
      r.begin();const a=r.group('node:a','g',{transform:'t0',class:'node'},'one');
      const image=new Element('image');a.element.insertBefore(image,null);
      const b=r.group('node:b','g',{},'two');r.end();
      const old=a.element;
      r.begin();const defs=new Element('defs');r.place(defs);
      const a2=r.group('node:a','g',{transform:'t10',class:'node selected'},'one');
      const mark=new Element('circle');r.place(mark);
      const b2=r.group('node:b','g',{},'two');r.end();
      const reused=a2.element===old&&a2.element.firstChild===image
        &&!a2.changed&&!b2.changed;
      const order=root.childNodes.map(n=>n.tag);
      r.begin();const a3=r.group('node:a','g',{},'new-style');r.end();
      const cleared=a3.changed&&a3.element.childNodes.length===0
        &&b.element.parentNode===null;
      r.begin();r.group('node:a','g',{},'new-style');
      const b3=r.group('node:b','g',{},'two');r.end();
      console.log(JSON.stringify({reused,order,attrs:old.attrs,cleared,
        recreated:b3.element!==b.element}));
    """,
    )
    assert result == dict(reused=True, order=["defs", "g", "circle", "g"],
                          attrs=dict(transform="t10", **{"class": "node selected"}),
                          cleared=True, recreated=True)


def test_new_scene_is_built_detached_and_committed_in_one_fragment():
    result = run_module(
        "canvas.js",
        """
      let rootInsertions=0;
      class Element {
        constructor(tag){this.tag=tag;this.childNodes=[];this.attrs={};}
        get firstChild(){return this.childNodes[0]||null;}
        get nextSibling(){const list=this.parentNode?.childNodes||[];
          return list[list.indexOf(this)+1]||null;}
        getAttribute(k){return this.attrs[k]??null;}
        setAttribute(k,v){this.attrs[k]=String(v);}
        replaceChildren(){for(const n of this.childNodes)n.parentNode=null;
          this.childNodes=[];}
        remove(){if(this.parentNode){const p=this.parentNode;
          p.childNodes.splice(p.childNodes.indexOf(this),1);this.parentNode=null;}}
        append(n){this.insertBefore(n,null);}
        insertBefore(n,next){
          if(this.tag==='svg')rootInsertions++;
          if(n.tag==='fragment'){
            for(const child of [...n.childNodes])this.insert(child,next);
          }else this.insert(n,next);
        }
        insert(n,next){n.remove();
          const index=next?this.childNodes.indexOf(next):this.childNodes.length;
          if(index<0)throw Error('Missing reference');
          this.childNodes.splice(index,0,n);n.parentNode=this;}
      }
      const root=new Element('svg');root.namespaceURI='svg';
      root.ownerDocument={createElementNS:(_,tag)=>new Element(tag),
        createDocumentFragment:()=>new Element('fragment')};
      const r=module.createCanvasRenderer(root);
      const group=(id)=>r.group(id,'g',{'data-id':id},id).element;
      r.begin();const a=group('a'),b=group('b'),c=group('c');
      const detached=root.childNodes.length===0&&!a.parentNode&&!b.parentNode;
      r.end();const first=rootInsertions;
      r.begin();group('a');group('b');group('c');r.end();
      const unchanged=rootInsertions===first;
      r.begin();group('c');const d=group('d');group('a');r.end();
      const order=root.childNodes.map(n=>n.attrs['data-id']);
      console.log(JSON.stringify({detached,first,unchanged,order,
        removed:!b.parentNode,retained:root.childNodes[0]===c,
        inserted:root.childNodes[1]===d}));
    """,
    )
    assert result == dict(detached=True, first=1, unchanged=True,
                          order=["c", "d", "a"], removed=True,
                          retained=True, inserted=True)
