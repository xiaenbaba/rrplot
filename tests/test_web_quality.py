"""排版检查仅作提示，区别合法接管、挂接与边界相切。"""
from test_web_requests import run_module


def test_visual_hints_are_read_only_and_include_locatable_objects():
    result = run_module(
        "checks.js",
        """
      const document={nodes:[],edges:[{id:'pipe',source:{junctionId:'a'},
        target:{junctionId:'b'}}],labels:[],junctions:[]};
      const nodes=[{id:'device',title:'换热器'},{id:'overlap',title:'阀'}];
      const bounds=[{kind:'node',id:'device',box:[40,40,20,20]},
        {kind:'node',id:'overlap',box:[45,45,20,20]},
        {kind:'label',id:'text',box:[20,45,10,10]},
        {kind:'label',id:'text2',box:[23,46,10,10]}];
      const routes=new Map([['pipe',[[0,50],[100,50]]]]);
      const before=JSON.stringify({document,nodes,bounds});
      const issues=module.inspectVisualQuality(document,{nodes,routes,bounds});
      console.log(JSON.stringify({issues,
        unchanged:before===JSON.stringify({document,nodes,bounds})}));
    """,
    )
    assert result["unchanged"]
    codes = {issue["code"] for issue in result["issues"]}
    assert codes == {"device-overlap", "label-overlap",
                     "pipe-through-device", "label-on-pipe"}
    assert all(issue["severity"] == "hint" and issue["ref"]["id"]
               for issue in result["issues"])


def test_connected_and_mounted_devices_and_tangent_lines_are_exempt():
    assert run_module(
        "checks.js",
        """
      const document={edges:[{id:'p',source:{nodeId:'a'},target:{nodeId:'b'}}]};
      const nodes=[{id:'a'},{id:'b'},{id:'v',mount:{edgeId:'p'}},{id:'c'}];
      const bounds=[{kind:'node',id:'a',box:[0,0,20,20]},
        {kind:'node',id:'b',box:[80,0,20,20]},
        {kind:'node',id:'v',box:[40,0,20,20]},
        {kind:'node',id:'c',box:[25,10,10,10]}];
      console.log(JSON.stringify(module.inspectVisualQuality(document,
        {nodes,bounds,routes:new Map([['p',[[0,10],[100,10]]]])})));
    """,
    ) == []


def test_diagonal_segments_crossing_device_interior_are_reported():
    result = run_module(
        "checks.js",
        """
      const document={edges:[{id:'p',source:{},target:{}}]};
      console.log(JSON.stringify(module.inspectVisualQuality(document,{
        nodes:[{id:'n'}],bounds:[{kind:'node',id:'n',box:[30,30,40,40]}],
        routes:new Map([['p',[[0,0],[100,100]]]])})));
    """,
    )
    assert [issue["code"] for issue in result] == ["pipe-through-device"]
