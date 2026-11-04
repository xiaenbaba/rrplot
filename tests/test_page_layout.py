"""整图排版保持连接、局部偏移及比例，失败时不改变图纸。"""
import base64
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.scene import TEMPLATES, load_template, resolve_scene, rotate, validate_scene
from rrplot.scene_renderer import export_scene


def layout(document, boxes, action, margin=40):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript page layout check")
    root = Path(__file__).resolve().parents[1]
    source = root.joinpath("web/geometry.js").read_bytes()
    module = "data:text/javascript;base64," + base64.b64encode(source).decode()
    script = ("import fs from 'node:fs';const geometry=await import("
              + json.dumps(module) + ");"
              "const input=JSON.parse(fs.readFileSync(0,'utf8'));"
              "try{const result=geometry.layoutPage(input.document,input.boxes,"
              "input.action,input.margin);console.log(JSON.stringify({result,"
              "original:input.document,boxes:input.boxes}));}catch(error){"
              "console.log(JSON.stringify({error:error.message,"
              "original:input.document,boxes:input.boxes}));}")
    process = subprocess.run([executable, "--input-type=module", "-e", script],
                             input=json.dumps(dict(document=document, boxes=boxes,
                                                   action=action, margin=margin)),
                             encoding="utf-8", capture_output=True, check=True)
    output = json.loads(process.stdout)
    assert output["original"] == document and output["boxes"] == boxes
    return output


def content_boxes(scene):
    boxes = []
    for node in scene["nodes"]:
        x, y, w, h = node["geometry"]["box"]
        corners = [rotate(point, node["rotation"]) for point in (
            [x, y], [x + w, y], [x, y + h], [x + w, y + h])]
        xs, ys = zip(*corners)
        boxes.append([node["x"] + min(xs), node["y"] + min(ys),
                      max(xs) - min(xs), max(ys) - min(ys)])
    for junction in scene["document"]["junctions"]:
        boxes.append([junction["x"] - 4, junction["y"] - 4, 8, 8])
    for edge in scene["edges"]:
        xs, ys = zip(*edge["points"])
        boxes.append([min(xs) - 4, min(ys) - 4,
                      max(xs) - min(xs) + 8, max(ys) - min(ys) + 8])
    # Explicit text extents stand in for the browser's measured SVG text boxes.
    for label in scene["labels"]:
        x, y = label["position"]
        boxes.append([x - 32, y - 12, 64, 24])
    return boxes


def union(boxes):
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return (left, top, max(b[0] + b[2] for b in boxes) - left,
            max(b[1] + b[3] for b in boxes) - top)


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("action", ["center", "fit"])
def test_all_templates_layout_preserves_geometry_and_attached_labels(name, action):
    document = load_template(name)
    document["page"] = dict(width=1800, height=1400)
    document["nodes"][0]["rotation"] = 90
    document["labels"].extend([
        dict(id="state-point", edgeId=document["edges"][0]["id"], at=.25,
             x=17.25, y=-18, text="P1"),
        dict(id="free-label", x=-60, y=-70, text="独立文字"),
    ])
    document = validate_scene(document)
    original = resolve_scene(document)
    boxes = content_boxes(original)
    result = layout(document, boxes, action)["result"]
    assert result["title"] == document["title"]
    moved = resolve_scene(result)
    dx = result["nodes"][0]["x"] - document["nodes"][0]["x"]
    dy = result["nodes"][0]["y"] - document["nodes"][0]["y"]
    for collection in ("nodes", "junctions"):
        for before, after in zip(document[collection], result[collection]):
            assert [after["x"], after["y"]] == pytest.approx(
                [before["x"] + dx, before["y"] + dy])
            assert {k: v for k, v in before.items() if k not in {"x", "y"}} == {
                k: v for k, v in after.items() if k not in {"x", "y"}}
    for before, after in zip(original["edges"], moved["edges"]):
        assert [after["source"], after["target"]] == [
            before["source"], before["target"]]
        assert len(before["points"]) == len(after["points"])
        for start, end in zip(before["points"], after["points"]):
            assert end == pytest.approx([start[0] + dx, start[1] + dy])
    for before, after in zip(original["labels"], moved["labels"]):
        assert after["position"] == pytest.approx(
            [before["position"][0] + dx, before["position"][1] + dy])
        if before.get("nodeId") or before.get("edgeId"):
            assert after["x"] == before["x"] and after["y"] == before["y"]
    left, top, width, height = union(boxes)
    assert left + dx == pytest.approx((result["page"]["width"] - width) / 2)
    assert top + dy == pytest.approx((result["page"]["height"] - height) / 2)
    if action == "center":
        assert result["page"] == document["page"]
    else:
        assert 40 <= left + dx < 40.5001
        assert 40 <= top + dy < 40.5001
    shifted = [[x + dx, y + dy, w, h] for x, y, w, h in boxes]
    assert layout(result, shifted, action)["result"] == result
    assert export_scene(result, "svg").startswith(b"<?xml")


def text_document():
    return validate_scene(dict(schemaVersion=1, page=dict(width=200, height=160),
                               nodes=[], edges=[], junctions=[], labels=[dict(
                                   id="text", text="长标签", x=-30, y=80)]))


@pytest.mark.parametrize("action", ["fit", "center"])
def test_text_only_layout_uses_measured_box_instead_of_label_anchor(action):
    document = text_document()
    result = layout(document, [[-80, 60, 120, 40]], action, 25)["result"]
    label = result["labels"][0]
    expected = [75, 50] if action == "fit" else [90, 80]
    assert [label["x"], label["y"]] == pytest.approx(expected)
    assert result["page"] == (dict(width=170, height=100) if action == "fit"
                              else document["page"])


@pytest.mark.parametrize("action", ["fit", "center"])
def test_empty_document_layout_is_no_op(action):
    document = text_document()
    document["labels"] = []
    assert layout(document, [], action)["result"] == document


def test_page_dimension_limits_and_subpixel_rounding():
    document = text_document()
    result = layout(document, [[-40, 20, 3920, 100]], "fit")["result"]
    assert result["page"] == dict(width=4000, height=180)
    # Subpixel measurement noise must not grow the paper on repeat clicks.
    noisy = layout(document, [[-40, 20, 3920.00001, 100]], "fit")["result"]
    assert noisy["page"] == result["page"]
    small = layout(document, [[-30, 80, 0, 0]], "fit", 10)["result"]
    assert small["page"] == dict(width=100, height=100)
    assert [small["labels"][0]["x"], small["labels"][0]["y"]] == [50, 50]


@pytest.mark.parametrize("boxes,action,margin", [
    ([[0, 0, 250, 20]], "center", 40),
    ([[0, 0, 20, 170]], "center", 40),
    ([[0, 0, 3920.01, 20]], "fit", 40),
    ([[0, 0, 20, 3920.01]], "fit", 40),
    ([[0, 0, 20, 20]], "fit", 9),
    ([[0, 0, 20, 20]], "fit", 501),
    ([[0, 0, 20, 20]], "fit", None),
    ([[0, 0, -1, 20]], "fit", 40),
    ([[0, 0, 20, None]], "fit", 40),
    ([], "center", 40),
    ([[0, 0, 20, 20]], "unknown", 40),
])
def test_invalid_layout_preserves_document(boxes, action, margin):
    document = text_document()
    before = copy.deepcopy(document)
    assert layout(document, boxes, action, margin)["error"]
    assert document == before
