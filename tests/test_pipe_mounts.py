"""管路附件的前后端定位、编辑、保存和实际编辑器事件。"""

import copy
import io
import json

import numpy as np
import pytest
from PIL import Image
from test_web_checks import inspect
from test_web_connections import connection_scenario
from test_web_document import edit_document
from test_web_geometry import run_geometry_script

from rrplot.registry import normalize_params
from rrplot.scene import MOUNT_TYPES, resolve_scene, validate_scene
from rrplot.scene_renderer import build_scene, export_scene, resolve_for_editor


def mount_document(kind="globe_valve", at=0.3, reverse=False, points=None):
    points = points or [[100, 200], [500, 200], [500, 450]]
    return validate_scene(
        dict(
            schemaVersion=1,
            page=dict(width=800, height=600),
            nodes=[
                dict(
                    id="valve",
                    type=kind,
                    title="挂接阀",
                    x=250,
                    y=200,
                    mount=dict(edgeId="pipe", at=at, reverse=reverse),
                )
            ],
            junctions=[
                dict(id="a", x=points[0][0], y=points[0][1]),
                dict(id="b", x=points[-1][0], y=points[-1][1]),
            ],
            edges=[
                dict(
                    id="pipe",
                    source=dict(junctionId="a"),
                    target=dict(junctionId="b"),
                    vertices=points[1:-1],
                )
            ],
            labels=[dict(id="label", nodeId="valve", x=0, y=45, text="阀件")],
        )
    )


@pytest.mark.parametrize("kind", sorted(MOUNT_TYPES))
@pytest.mark.parametrize(
    "points",
    [
        [[100, 200], [600, 200]],
        [[600, 200], [100, 200]],
        [[400, 80], [400, 500]],
        [[400, 500], [400, 80]],
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_mount_frontend_backend_geometry_and_roundtrip(kind, points, reverse):
    document = mount_document(kind, reverse=reverse, points=points)
    before = copy.deepcopy(document)
    scene = resolve_scene(document)
    assert document == before
    assert validate_scene(json.loads(json.dumps(document))) == document
    node = scene["nodes"][0]
    actual = run_geometry_script(
        "const s=cases;console.log(JSON.stringify(geometry.mountedNodes("
        "s.document,s.nodes)[0]));",
        scene,
    )
    assert [actual[k] for k in ("x", "y", "rotation")] == pytest.approx(
        [node[k] for k in ("x", "y", "rotation")]
    )
    assert scene["edges"][0]["points"] == points
    assert len(document["edges"]) == 1


@pytest.mark.parametrize("at", [0, 0.2, 400 / 650, 0.8, 1])
def test_bent_pipe_position_and_labels_follow_route_changes(at):
    document = mount_document(at=at)
    before = resolve_scene(document)
    document["junctions"][1]["y"] += 50
    after = resolve_scene(document)
    for scene in (before, after):
        node, label = scene["nodes"][0], scene["labels"][0]
        assert node["mount"]["at"] == at
        assert label["position"] != [0, 45]
        assert 100 <= node["x"] <= 500
        assert 200 <= node["y"] <= 500
    assert before != after


@pytest.mark.parametrize(
    "mount",
    [
        None,
        {},
        {"edgeId": "missing"},
        {"edgeId": []},
        {"edgeId": "pipe", "at": -1},
        {"edgeId": "pipe", "at": 1.1},
        {"edgeId": "pipe", "at": True},
        {"edgeId": "pipe", "reverse": 1},
        {"edgeId": "pipe", "extra": 1},
    ],
)
def test_invalid_mount_configuration_rejected_without_mutating_input(mount):
    document = mount_document()
    document["nodes"][0]["mount"] = mount
    original = copy.deepcopy(document)
    with pytest.raises(ValueError):
        validate_scene(document)
    assert document == original


def test_connected_or_unsupported_devices_and_zero_pipe_cannot_mount():
    document = mount_document()
    document["edges"][0]["source"] = dict(nodeId="valve", portId="out")
    with pytest.raises(ValueError, match="独立管路端点"):
        validate_scene(document)
    document = mount_document()
    document["nodes"][0].update(type="compressor", params={})
    with pytest.raises(ValueError, match="挂接配置"):
        validate_scene(document)
    with pytest.raises(ValueError, match="长度为零"):
        mount_document(points=[[100, 200], [100, 200]])


@pytest.mark.parametrize(
    "fmt,signature", [("svg", b"<?xml"), ("png", b"\x89PNG"), ("pdf", b"%PDF")]
)
def test_mount_export_and_editor_feature(fmt, signature):
    document = mount_document()
    assert "pipeMounts" in resolve_for_editor(document)["features"]
    assert export_scene(document, fmt).startswith(signature)
    with build_scene(document) as diagram:
        masks = [p for p in diagram.ax.patches if p.get_zorder() == 8]
        assert len(masks) == 1
        assert any(p.get_zorder() == 9 for p in diagram.ax.patches)
    assert not any(issue["code"] == "isolated-node" for issue in inspect(document))


def test_delete_accessory_keeps_parent_and_delete_parent_detaches_accessory():
    document = mount_document()
    output = edit_document(document, [dict(kind="node", id="valve")], "delete")
    result = output["result"]
    assert result["edges"] == document["edges"] and not result["nodes"]
    output = edit_document(document, [dict(kind="edge", id="pipe")], "delete")
    result = validate_scene(output["result"])
    assert len(result["nodes"]) == 1 and "mount" not in result["nodes"][0]
    assert result["nodes"][0]["x"] == document["nodes"][0]["x"]


def test_copy_group_includes_mounted_valve_but_single_copy_is_independent():
    document = mount_document()
    result = edit_document(document, [dict(kind="junction", id=j) for j in ("a", "b")])[
        "result"
    ]["document"]
    new_pipe = next(e for e in result["edges"] if e["id"] != "pipe")
    new_node = next(n for n in result["nodes"] if n["id"] != "valve")
    assert new_node["mount"]["edgeId"] == new_pipe["id"]
    validate_scene(result)
    copied = edit_document(document, [dict(kind="node", id="valve")])["result"][
        "document"
    ]
    assert "mount" not in copied["nodes"][-1]
    assert copied["nodes"][-1]["x"] == document["nodes"][0]["x"] + 20


def test_real_editor_drag_mount_detach_cancel_and_undo_redo():
    document = mount_document(at=0.3, points=[[100, 200], [600, 200]])
    document["nodes"][0].pop("mount")
    document["nodes"][0]["y"] = 100
    output = connection_scenario(
        """
      pipeMountsSupported=true;
      const hit={dataset:{kind:'node',id:'valve'}};
      const down=point=>listeners.get('diagram:pointerdown')({
        button:0,pointerId:1,point,target:{closest:()=>hit},preventDefault(){}});
      const move=point=>listeners.get('diagram:pointermove')({point});
      const up=()=>listeners.get('diagram:pointerup')({pointerId:1});
      down([250,100]);move([350,205]);up();results.push(snapshot());
      history('undo');results.push(snapshot());history('redo');results.push(snapshot());
      down([350,200]);move([350,320]);cancelDrag();results.push(snapshot());
      down([350,200]);move([350,320]);up();results.push(snapshot());
    """,
        document,
    )
    mounted, undone, redone, cancelled, detached = output["results"]
    assert mounted["doc"]["nodes"][0]["mount"]["edgeId"] == "pipe"
    assert mounted["doc"]["nodes"][0]["y"] == 200
    assert "mount" not in undone["doc"]["nodes"][0]
    assert mounted["doc"] == redone["doc"] == cancelled["doc"]
    assert "mount" not in detached["doc"]["nodes"][0]
    assert detached["doc"]["edges"] == mounted["doc"]["edges"]


def test_real_editor_split_reverse_merge_preserves_mount_position():
    document = mount_document(at=0.75, points=[[100, 200], [600, 200]])
    output = connection_scenario(
        """
      splitEdge(doc.edges[0],.5);results.push(snapshot());
      const newId=doc.nodes[0].mount.edgeId;
      const reverse=()=>editSelectedEdges(doc,[{kind:'edge',id:newId}],
        'reverse',new Map([[newId,edgePoints(doc.edges.find(e=>e.id===newId))]]));
      doc=reverse();
      syncMounts();results.push(snapshot());
      doc=reverse();
      multiSelection=[{kind:'junction',id:doc.junctions.at(-1).id}];selection=multiSelection[0];removeSelected();results.push(snapshot());
    """,
        document,
    )
    for state in output["results"]:
        node = validate_scene(state["doc"])["nodes"][0]
        assert node["x"] == 475 and node["y"] == 200
        assert node["rotation"] == 0
    assert len(output["results"][-1]["doc"]["edges"]) == 1


@pytest.mark.parametrize("scale", [0.3, 1, 3])
def test_mount_snap_uses_screen_distance_and_preserves_pipe(scale):
    document = mount_document(points=[[100, 200], [600, 200]])
    document["nodes"][0].pop("mount")
    scene = resolve_scene(document)
    results = run_geometry_script(
        "const {document:d,nodes}=cases.scene;"
        "const matrix={a:cases.scale,b:0,c:0,d:cases.scale};"
        "console.log(JSON.stringify([17,19].map(dy=>geometry.nearestMount("
        "d,d.nodes[0],nodes,[300,200+dy/cases.scale],matrix))));",
        dict(scene=scene, scale=scale),
    )
    assert results[0]["edgeId"] == "pipe"
    assert results[1] is None


def test_mount_defaults_do_not_change_legacy_devices():
    params = normalize_params("globe_valve", {})
    document = mount_document()
    document["nodes"][0].pop("mount")
    assert validate_scene(document)["nodes"][0]["params"] == params


@pytest.mark.parametrize("kind", sorted(MOUNT_TYPES))
def test_palette_drag_preview_preserves_dom_and_internal_leave_then_drop(kind):
    document = mount_document(points=[[100, 200], [600, 200]])
    params = normalize_params(kind, {})
    setup = (
        "const kind=" + json.dumps(kind) + ";const params=" + json.dumps(params) + ";"
    )
    output = connection_scenario(
        setup
        + """
      pipeMountsSupported=true;draggingPart=kind;
      catalog=[{type:kind,label:'新附件',fields:Object.fromEntries(
        Object.entries(params).map(([k,v])=>[k,{default:v}]))}];
      let marker=null,created=0,repaints=0;
      const child={};
      svg.querySelector=()=>marker;svg.contains=target=>target===child;
      svg.getBoundingClientRect=()=>({left:0,top:0,right:800,bottom:600});
      shape=()=>{created++;
        marker={attrs:{},setAttribute(k,v){this.attrs[k]=v;}};return marker;};
      renderCanvas=()=>repaints++;
      const transfer={getData:()=>''};
      const event=point=>({point,clientX:point[0],clientY:point[1],
        dataTransfer:transfer,preventDefault(){}});
      const before=snapshot();
      for(let i=0;i<20;i++){
        listeners.get('diagram:dragover')(event([300+i,205]));
        listeners.get('diagram:dragleave')({...event([300+i,205]),relatedTarget:child});
        listeners.get('diagram:dragleave')({...event([300+i,205]),relatedTarget:null});
        if(!mountPreview||marker.attrs.visibility!=='visible')
          throw Error('预览被内部切换清除');
      }
      results.push({before,after:snapshot(),created,repaints,preview:structuredClone(mountPreview)});
      listeners.get('diagram:dragleave')({...event([850,205]),relatedTarget:null});
      results.push({preview:mountPreview,visibility:marker.attrs.visibility});
      listeners.get('diagram:dragover')(event([400,205]));
      listeners.get('diagram:drop')(event([400,205]));
      results.push(snapshot(),{draggingPart,preview:mountPreview,created,repaints});
    """,
        document,
    )
    preview, left, committed, cleaned = output["results"]
    assert preview["before"] == preview["after"]
    assert preview["created"] == 1 and preview["repaints"] == 0
    assert preview["preview"]["point"] == [319, 200]
    assert left == dict(preview=None, visibility="hidden")
    result = validate_scene(committed["doc"])
    assert result["nodes"][-1]["mount"] == dict(
        edgeId="pipe", at=0.6, reverse=False
    )
    assert result["edges"] == document["edges"]
    assert len(committed["undo"]) == 1
    assert cleaned == dict(draggingPart=None, preview=None, created=1, repaints=0)


def test_click_placement_preview_reuses_marker_without_repainting_canvas():
    output = connection_scenario(
        """
      pipeMountsSupported=true;placement='globe_valve';
      let marker=null,created=0,repaints=0;
      svg.querySelector=()=>marker;
      shape=()=>{created++;
        marker={attrs:{},setAttribute(k,v){this.attrs[k]=v;}};return marker;};
      renderCanvas=()=>repaints++;
      for(const point of [[300,205],[310,205],[310,250],[320,205]])
        listeners.get('diagram:pointermove')({point});
      results.push({created,repaints,point:mountPreview.point,visibility:marker.attrs.visibility});
      listeners.get('diagram:pointerleave')();
      results.push({preview:mountPreview,visibility:marker.attrs.visibility});
    """,
        mount_document(points=[[100, 200], [600, 200]]),
    )
    active, left = output["results"]
    assert active == dict(created=1, repaints=0, point=[320, 200], visibility="visible")
    assert left == dict(preview=None, visibility="hidden")


@pytest.mark.parametrize("end", ["drop", "outside", "cancel", "click"])
def test_pointer_palette_drag_commits_only_on_canvas_release(end):
    output = connection_scenario(
        "const action=" + json.dumps(end) + ";" + """
      pipeMountsSupported=true;
      catalog=[{type:'globe_valve',label:'新附件',fields:{w:{default:40},h:{default:24}}}];
      let captured=false,marker=null,repaints=0;
      const button={focus(){},setPointerCapture(){captured=true;},
        hasPointerCapture(){return captured;},
        releasePointerCapture(){captured=false;}};
      svg.getBoundingClientRect=()=>({left:100,top:100,right:800,bottom:600});
      svg.querySelector=()=>marker;
      shape=()=>{marker={setAttribute(){}};return marker;};
      renderCanvas=()=>repaints++;document.body={classList:{remove(){}}};
      const event=(x,y,pointerId=1)=>({button:0,pointerId,clientX:x,clientY:y,
        point:[x,y],preventDefault(){}});
      const before=snapshot();
      beginPaletteDrag(event(50,200),'globe_valve',button);
      movePaletteDrag(event(400,205,2));
      results.push({captured,moved:paletteDrag.moved,preview:mountPreview});
      if(action!=='click')movePaletteDrag(event(400,205));
      results.push({repaints,point:mountPreview?.point});
      if(action==='cancel')endPaletteDrag(event(400,205),true);
      else endPaletteDrag(['outside','click'].includes(action)
        ?event(50,200):event(400,205));
      results.push({before,after:snapshot(),captured,paletteDrag,preview:mountPreview,suppressed:suppressedPaletteClick===button});
    """,
        mount_document(points=[[100, 200], [600, 200]]),
    )
    untouched, preview, finished = output["results"]
    assert untouched == dict(captured=True, moved=False, preview=None)
    assert preview["repaints"] == 0
    assert not finished["captured"]
    assert finished["paletteDrag"] is None and finished["preview"] is None
    if end == "drop":
        committed = validate_scene(finished["after"]["doc"])
        assert committed["nodes"][-1]["mount"]["edgeId"] == "pipe"
        assert len(finished["after"]["undo"]) == 1
    else:
        assert finished["before"] == finished["after"]
    assert finished["suppressed"] is (end != "click")


MOUNT_CANVAS = """
  const shapes=[];
  shape=(tag,attrs={})=>{
    shapes.push({tag,...attrs});
    return {setAttribute(){},classList:{add(){},remove(){},toggle(){}}};
  };
  svg.replaceChildren=()=>{shapes.length=0;};
  renderVertices=()=>{};updateView=()=>{};
  render=actualRenderCanvas;renderCanvas=actualRenderCanvas;
"""


def test_delete_endpoint_undo_redo_renders_while_geometry_refresh_is_pending():
    document = mount_document(points=[[100, 200], [600, 200]])
    document["nodes"].append(dict(id="device", type="compressor", x=650, y=200))
    document["edges"][0]["target"] = dict(nodeId="device", portId="suction")
    document = validate_scene(document)
    output = connection_scenario(
        MOUNT_CANVAS + """
      pipeMountsSupported=true;refresh=actualRefresh;
      const known=new Map(geometries),pending=[];
      api=(path,body)=>new Promise(resolve=>pending.push({
        document:structuredClone(body.document),resolve}));
      const complete=async()=>{
        const job=pending.shift();
        job.resolve({nodes:job.document.nodes.map(n=>({...n,
          geometry:known.get(n.id)})),fontFamily:'serif'});
        for(let i=0;i<12;i++)await Promise.resolve();
      };
      setSelection('node','device');removeSelected();await complete();
      results.push({deleted:!geometries.has('device'),state:snapshot()});
      history('undo');
      results.push({pending:pending.length,state:snapshot()});
      await complete();
      results.push({restored:geometries.has('device'),state:snapshot(),
        drawn:shapes.filter(s=>s['data-kind']==='node').map(s=>s['data-id'])});
      history('redo');await complete();results.push(snapshot());
      history('undo');await complete();results.push(snapshot());
    """,
        document,
    )
    deleted, waiting, restored, redone, undone = output["results"]
    assert deleted["deleted"]
    assert not deleted["state"]["doc"]["edges"]
    assert waiting["pending"] == 1
    assert waiting["state"]["doc"] == document
    assert restored["restored"] and set(restored["drawn"]) == {"valve", "device"}
    assert restored["state"]["doc"] == undone["doc"] == document
    assert redone["doc"] == deleted["state"]["doc"]
    assert not output["messages"]


@pytest.mark.parametrize("operation", ["edit", "drag"])
def test_collapsing_mounted_pipe_rolls_back_without_changing_history(operation):
    output = connection_scenario(
        MOUNT_CANVAS + "const operation=" + json.dumps(operation) + ";" + """
      pipeMountsSupported=true;
      undo=[{old:true}];redo=[{future:true}];ownedDraft='existing-draft';
      if(operation==='edit'){
        results.push(snapshot());edit(()=>{doc.junctions[1].x=doc.junctions[0].x;});
      }
      else {
        const hit={dataset:{kind:'junction',id:'b'}};
        listeners.get('diagram:pointerdown')({button:0,pointerId:1,
          point:[600,200],target:{closest:()=>hit},preventDefault(){}});
        results.push(snapshot());
        listeners.get('diagram:pointermove')({point:[100,200]});
        results.push({preview:doc.junctions[1].x});
        listeners.get('diagram:pointerup')({pointerId:1});
      }
      const after=snapshot();results.push(after);
      edit(()=>{doc.junctions[1].x=550;});results.push(snapshot());
    """,
        mount_document(points=[[100, 200], [600, 200]]),
    )
    before, *others = output["results"]
    if operation == "drag":
        assert others.pop(0) == dict(preview=100)
    rejected, accepted = others
    for field in ("doc", "undo", "redo", "dirty", "revision", "request", "ownedDraft"):
        assert rejected[field] == before[field]
    assert accepted["doc"]["junctions"][1]["x"] == 550
    assert len(accepted["undo"]) == len(before["undo"]) + 1
    assert not accepted["redo"]
    assert output["saves"] == output["refreshes"] == 1
    assert any("长度为零" in message for message in output["messages"])
    validate_scene(rejected["doc"])
    validate_scene(accepted["doc"])


def test_rejected_repeated_nudge_keeps_last_valid_move_and_undo():
    document = mount_document(points=[[100, 200], [102, 200]])
    output = connection_scenario(
        MOUNT_CANVAS + """
      pipeMountsSupported=true;setSelection('junction','b');
      nudgeSelected({key:'ArrowLeft',repeat:false});results.push(snapshot());
      nudgeSelected({key:'ArrowLeft',repeat:true});results.push(snapshot());
      results.push({nudge});
      history('undo');results.push(snapshot());
      history('redo');results.push(snapshot());
    """,
        document,
    )
    accepted, rejected, session, undone, redone = output["results"]
    assert accepted["doc"] == rejected["doc"] == redone["doc"]
    assert accepted["doc"]["junctions"][1]["x"] == 101
    assert accepted["undo"] == rejected["undo"] == [document]
    assert session == dict(nudge=None)
    assert undone["doc"] == document
    assert output["saves"] == output["refreshes"] == 3
    assert any("长度为零" in message for message in output["messages"])


@pytest.mark.parametrize("boxed", [False, True])
def test_exported_labels_remain_visible_over_mounted_valve_mask(boxed):
    document = mount_document(at=0.5, points=[[100, 200], [600, 200]])
    document["nodes"][0]["params"]["h"] = 180
    document["labels"] = [dict(id="label", nodeId="valve", text="V",
                               x=0, y=70, size=10, color="red", boxed=boxed)]
    with Image.open(io.BytesIO(export_scene(document, "png", dpi=100))) as image:
        labelled = np.asarray(image).copy()
    document["labels"] = []
    with Image.open(io.BytesIO(export_scene(document, "png", dpi=100))) as image:
        unlabelled = np.asarray(image).copy()
    assert np.count_nonzero(labelled != unlabelled) > 0
    red = ((labelled[:, :, 0] > 150) & (labelled[:, :, 1] < 100)
           & (labelled[:, :, 2] < 100))
    assert np.count_nonzero(red) > 0
