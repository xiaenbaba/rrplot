"""图纸模型的引用、几何、工厂复用与输出契约。"""
import base64
import json
import random
import shutil
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from rrplot.registry import catalog, describe, normalize_params
from rrplot.scene import (
    TEMPLATES,
    endpoint,
    load_template,
    resolve_scene,
    rotate,
    route,
    validate_scene,
)
from rrplot.scene_renderer import build_scene, export_scene, resolve_for_editor


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_template_roundtrip_and_orthogonal_edges(name):
    d = load_template(name)
    assert validate_scene(json.loads(json.dumps(d))) == d
    scene = resolve_scene(d)
    for edge in scene["edges"]:
        assert len(edge["points"]) >= 2
        assert all(a[0] == b[0] or a[1] == b[1]
                   for a, b in zip(edge["points"], edge["points"][1:]))
    assert scene["document"] == d


def test_intermediate_evi_injection_enters_rotated_compressor_injection_port():
    document = load_template("evi_intermediate")
    injection = next(edge for edge in document["edges"] if edge["id"] == "injection")
    assert injection["target"] == {"nodeId": "comp", "portId": "vapor_inj"}
    resolved = resolve_scene(document)
    injection = next(edge for edge in resolved["edges"] if edge["id"] == "injection")
    assert injection["points"][-1] == [270, 130]


def test_heat_pump_receiver_template_uses_gas_liquid_separator_on_suction():
    document = load_template("heat_pump_receiver")
    separator = next(node for node in document["nodes"] if node["id"] == "separator")
    assert document["title"] == "带气液分离器的普通热泵"
    assert separator["title"] == "气液分离器"
    assert separator["type"] == "separator_utube"
    inlet = next(edge for edge in document["edges"] if edge["id"] == "separator-in")
    vapor = next(edge for edge in document["edges"] if edge["id"] == "separator-vapor")
    assert inlet["source"] == {"nodeId": "evap", "portId": "right"}
    assert inlet["target"] == {"nodeId": "separator", "portId": "in"}
    assert vapor["source"] == {"nodeId": "separator", "portId": "out"}
    assert vapor["target"] == {"nodeId": "comp", "portId": "bottom"}


def test_separator_template_pipes_stay_outside_body_and_exit_straight():
    scene = resolve_scene(load_template("heat_pump_receiver"))
    separator = next(node for node in scene["nodes"] if node["id"] == "separator")
    left = separator["x"] - separator["params"]["w"] / 2
    right = separator["x"] + separator["params"]["w"] / 2
    top = separator["y"] - separator["params"]["h"] / 2
    bottom = separator["y"] + separator["params"]["h"] / 2
    for edge in scene["edges"]:
        for a, b in zip(edge["points"], edge["points"][1:]):
            if a[0] == b[0]:
                assert not (left < a[0] < right
                            and max(a[1], b[1]) > top
                            and min(a[1], b[1]) < bottom)
            else:
                assert not (top < a[1] < bottom
                            and max(a[0], b[0]) > left
                            and min(a[0], b[0]) < right)
    vapor = next(edge for edge in scene["edges"] if edge["id"] == "separator-vapor")
    assert len(vapor["points"]) == 2
    assert vapor["points"][0][0] == vapor["points"][1][0]


@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("stub", [16, 100])
def test_separator_svg_bounds_include_connections_and_mirrored_ports(flip, stub):
    geometry = describe("separator_utube", {"flip": flip, "stub": stub})
    x, y, w, h = geometry["box"]
    for port in geometry["ports"].values():
        px, py = port["point"]
        assert x < px < x + w and y < py < y + h
    assert (geometry["ports"]["in"]["point"][0] > 0) is flip
    assert (geometry["ports"]["out"]["point"][0] < 0) is flip
    field = next(item for item in catalog()
                 if item["type"] == "separator_utube")["fields"]["flip"]
    assert field["type"] == "checkbox"
    assert normalize_params("separator_utube", {"flip": flip})["flip"] is flip


@pytest.mark.parametrize("value", ["true", "false", 0, 1, None])
def test_separator_rejects_non_boolean_mirror_values(value):
    with pytest.raises(ValueError, match="布尔值"):
        normalize_params("separator_utube", {"flip": value})


def test_node_move_updates_pipe_and_attached_label_without_mutating_document():
    d = load_template("evi_ftvi")
    old = resolve_scene(d)
    comp = next(n for n in d["nodes"] if n["id"] == "comp")
    comp["x"] += 60
    comp["y"] += 40
    new = resolve_scene(d)
    injection = next(e for e in new["edges"] if e["id"] == "injection")
    assert injection["points"][-1] == [618, 312]
    label = next(item for item in new["labels"] if item["id"] == "label-comp")
    assert label["position"] == [600, 338]
    assert next(n for n in old["nodes"] if n["id"] == "comp")["x"] == 600
    assert "geometry" not in comp


def test_rotation_updates_ports_normals_and_label_offsets():
    d = load_template("evi_ftvi")
    n = next(n for n in d["nodes"] if n["id"] == "eev1")
    n["rotation"] = 90
    scene = resolve_scene(d)
    nodes = {n["id"]: n for n in scene["nodes"]}
    p = endpoint({"nodeId": "eev1", "portId": "in"}, nodes, {})
    assert p == {"point": [50, 171], "direction": [1, 0]}
    label = next(item for item in scene["labels"] if item["id"] == "label-eev1")
    assert label["position"] == [40, 187]
    assert rotate([10, 20], 270) == [20, -10]
    with build_scene(d) as diagram:
        assert len(diagram.ax.lines) > 0


@pytest.mark.parametrize("kind", [entry["type"] for entry in catalog()])
def test_catalog_defaults_create_svg_and_ports(kind):
    params = normalize_params(kind, {})
    geometry = describe(kind, params)
    assert geometry["width"] > 0 and geometry["ports"]
    d = dict(schemaVersion=1, nodes=[dict(id="n", type=kind, params=params,
                                        x=200, y=200)], labels=[], edges=[])
    scene = resolve_for_editor(d)
    image = scene["nodes"][0]["geometry"]["image"]
    assert image.startswith("data:image/svg+xml;base64,")
    assert scene["fontFamily"]
    assert describe("compressor", {"style": "方形"})["width"] == 42


@pytest.mark.parametrize("fmt,signature", [("svg", b"<?xml"), ("png", b"\x89PNG"),
                                          ("pdf", b"%PDF")])
def test_export_valid_file_and_closes_figure(fmt, signature):
    before = plt.get_fignums()
    out = export_scene(load_template("evi_ftvi"), fmt)
    assert out.startswith(signature) and len(out) > 1000
    assert plt.get_fignums() == before


@pytest.mark.parametrize("change", [
    lambda d: d.update(schemaVersion=9),
    lambda d: d.update(title=3),
    lambda d: d.update(page=[]),
    lambda d: d["page"].update(width=0),
    lambda d: d.update(nodes={}),
    lambda d: d["nodes"].append("bad"),
    lambda d: d["nodes"][0].update(id=d["nodes"][1]["id"]),
    lambda d: d["nodes"][0].update(type="unknown"),
    lambda d: d["nodes"][0].update(type=[]),
    lambda d: d["nodes"][0].update(params=[]),
    lambda d: d["nodes"][0]["params"].update(w=0),
    lambda d: d["nodes"][0]["params"].update(shape="bad"),
    lambda d: d["nodes"][0]["params"].update(extra=1),
    lambda d: d["nodes"][0].update(x=float("nan")),
    lambda d: d["nodes"][0].update(rotation=45),
    lambda d: d["nodes"][0].update(rotation=False),
    lambda d: d["nodes"][0].update(title=4),
    lambda d: d["edges"][0].update(source=[0, 0]),
    lambda d: d["edges"][0].update(source={"nodeId": "missing", "portId": "left"}),
    lambda d: d["edges"][0].update(source={"nodeId": [], "portId": "left"}),
    lambda d: d["edges"][0].update(source={"nodeId": "comp", "portId": "missing"}),
    lambda d: d["edges"][0].update(source={"nodeId": "comp", "portId": []}),
    lambda d: d["edges"][0].update(source={"junctionId": "missing"}),
    lambda d: d["edges"][0].update(source={"junctionId": []}),
    lambda d: d["edges"][0].update(vertices="bad"),
    lambda d: d["edges"][0].update(vertices=[[1]]),
    lambda d: d["edges"][0].update(width=-1),
    lambda d: d["edges"][0].update(color=3),
    lambda d: d["edges"][0].update(color="not-a-color"),
    lambda d: d["edges"][0].update(linestyle="bad"),
    lambda d: d["edges"][0].update(head="bad"),
    lambda d: d["edges"][0].update(headAt="bad"),
    lambda d: d["edges"][0].update(headAt=[2]),
    lambda d: d["labels"][0].update(text=4),
    lambda d: d["labels"][0].update(ha="bad"),
    lambda d: d["labels"][0].update(color=4),
    lambda d: d["labels"][0].update(color="not-a-color"),
    lambda d: d["labels"][0].update(boxed=4),
    lambda d: d["labels"][0].update(nodeId="missing"),
    lambda d: d["labels"][0].update(nodeId=[]),
])
def test_invalid_scene_reports_error(change):
    d = load_template("evi_ftvi")
    change(d)
    with pytest.raises(ValueError):
        validate_scene(d)


@pytest.mark.parametrize(
    "path",
    sorted(
        Path(__file__).resolve().parents[1]
        .joinpath("examples/scenes")
        .glob("*.json")
    ),
    ids=lambda p: p.name,
)
def test_example_scenes_resolve_and_roundtrip(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    validated = validate_scene(raw)
    scene = resolve_scene(validated)
    assert scene["document"] == validated
    assert scene["nodes"] and scene["edges"]


def test_invalid_export_or_geometry_and_failure_closes_figure():
    with pytest.raises(ValueError):
        load_template("bad")
    with pytest.raises(ValueError):
        normalize_params("vessel", {"w": 100, "h": 80})
    d = load_template("evi_ftvi")
    for fmt, dpi in (("gif", 140), ("png", 0), ("png", "bad")):
        with pytest.raises(ValueError):
            export_scene(d, fmt, dpi)
    d["page"] = dict(width=4000, height=4000)
    with pytest.raises(ValueError, match="DPI"):
        export_scene(d, "png", 600)
    d["edges"][0]["color"] = "not-a-color"
    before = plt.get_fignums()
    with pytest.raises(ValueError):
        build_scene(d)
    assert plt.get_fignums() == before


def test_renderer_exception_closes_figure(monkeypatch):
    def fail(*args):
        raise RuntimeError("drawing failed")

    before = plt.get_fignums()
    monkeypatch.setattr("rrplot.scene_renderer.make_registered", fail)
    with pytest.raises(RuntimeError, match="drawing failed"):
        build_scene(load_template("evi_ftvi"))
    assert plt.get_fignums() == before


def test_frontend_and_backend_routes_agree():
    """Node 仅用于可选开发校验，运行编辑器本身无需 Node。"""
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript geometry check")
    randomizer = random.Random(15)
    cases = []
    for _ in range(100):
        a, b = [dict(point=[randomizer.randrange(-50, 300) for _ in range(2)],
                     direction=randomizer.choice([[1, 0], [0, -1], [0, 1],
                                                   [-1, 0], [0, 0]]))
                for _ in range(2)]
        vertices = [[randomizer.randrange(-20, 300) for _ in range(2)]
                    for _ in range(randomizer.randrange(4))]
        cases.append([a, b, vertices])
    raw = Path(__file__).resolve().parents[1].joinpath("web/geometry.js").read_bytes()
    module = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    script = ("import fs from 'node:fs'; const {route}=await import("
              + json.dumps(module)
              + "); const cases=JSON.parse(fs.readFileSync(0,'utf8'));"
              "console.log(JSON.stringify(cases.map(c=>route(...c))));")
    result = subprocess.run([executable, "--input-type=module", "-e", script],
                            input=json.dumps(cases), text=True, capture_output=True,
                            check=True)
    assert json.loads(result.stdout) == [route(*case) for case in cases]


def test_frontend_split_route_anchors_both_edges_at_junction():
    """插入三通时，前后两段保持原走线且不产生与三通重合的冗余折点。"""
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript geometry check")
    raw = Path(__file__).resolve().parents[1].joinpath("web/geometry.js").read_bytes()
    module = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    script = ("import fs from 'node:fs'; const {splitRoute,route}=await import("
              + json.dumps(module)
              + "); const points=JSON.parse(fs.readFileSync(0,'utf8'));"
              "const split=splitRoute(points);"
              "const short=splitRoute([[0,0],[40,0]],0.25);"
              "const shortRoute=route({point:[0,0],direction:[1,0]},"
              "{point:short.point,direction:[0,0]},short.prefix);"
              "console.log(JSON.stringify({split,short,shortRoute}));")
    points = [[0, 0], [100, 0], [100, 100], [200, 100]]
    result = subprocess.run([executable, "--input-type=module", "-e", script],
                            input=json.dumps(points), text=True,
                            capture_output=True, check=True)
    data = json.loads(result.stdout)
    split = data["split"]
    assert split["point"] == [100, 50]
    assert split["prefix"] == [[100, 0]]
    assert split["suffix"] == [[100, 100]]
    # 近端口（<20 单位）拆分保持直连，不产生引出段过冲折返
    assert data["short"]["prefix"] == []
    assert data["shortRoute"] == [[0, 0], [10, 0]]


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("offset", [(30, -20), (23.5, -17.25), (0, 0)])
def test_frontend_translate_preserves_entire_resolved_layout(name, offset):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript geometry check")
    original = load_template(name)
    original["nodes"][0]["rotation"] = 90
    original["nodes"][0]["x"] += 0.25
    original["edges"][0]["vertices"] = [[120.25, 87.5], [160.25, 87.5]]
    original["labels"].append(dict(id="free-label", text="独立文字", x=17.25, y=29.5))
    original["labels"].append(dict(id="pipe-label", text="状态点",
                                   edgeId=original["edges"][0]["id"],
                                   at=.4, x=5, y=-12))
    original = validate_scene(original)
    raw = Path(__file__).resolve().parents[1].joinpath("web/geometry.js").read_bytes()
    module = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    script = ("import fs from 'node:fs'; const {translateDocument}=await import("
              + json.dumps(module)
              + "); const args=JSON.parse(fs.readFileSync(0,'utf8'));"
              "const moved=translateDocument(...args);"
              "console.log(JSON.stringify({moved,original:args[0]}));")
    result = subprocess.run([executable, "--input-type=module", "-e", script],
                            input=json.dumps([original, *offset]), encoding="utf-8",
                            capture_output=True, check=True)
    data = json.loads(result.stdout)
    moved = data["moved"]
    assert data["original"] == original
    assert moved["page"] == original["page"]
    for before, after in zip(original["labels"], moved["labels"]):
        if "nodeId" in before or "edgeId" in before:
            assert after == before  # 保持附着标签的局部偏移，避免重复移动。
    for before, after in zip(original["edges"], moved["edges"]):
        assert after["source"] == before["source"]
        assert after["target"] == before["target"]
    before, after = resolve_scene(original), resolve_scene(moved)
    def shifted(point):
        return [value + offset[i] for i, value in enumerate(point)]

    for a, b in zip(before["nodes"], after["nodes"]):
        assert [b["x"], b["y"]] == shifted([a["x"], a["y"]])
    for a, b in zip(original["junctions"], moved["junctions"]):
        assert [b["x"], b["y"]] == shifted([a["x"], a["y"]])
    for a, b in zip(before["edges"], after["edges"]):
        assert b["points"] == [shifted(point) for point in a["points"]]
    for a, b in zip(before["labels"], after["labels"]):
        assert b["position"] == shifted(a["position"])
    assert export_scene(moved).startswith(b"<?xml")
