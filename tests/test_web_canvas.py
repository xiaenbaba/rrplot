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
