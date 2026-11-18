"""常用阀件的 Web 图元边界、端口、旋转口标及导出契约。"""
import json

import matplotlib.pyplot as plt
import pytest
from matplotlib.colors import to_rgba
from matplotlib.patches import Polygon
from test_web_geometry import run_geometry_script

from rrplot import Diagram, parts
from rrplot.registry import catalog, describe, make_registered, normalize_params
from rrplot.scene import endpoint, resolve_scene, rotate, validate_scene
from rrplot.scene_renderer import build_scene, export_scene, resolve_for_editor
from rrplot.style import FILL, LINE

KINDS = ("four_way_valve", "globe_valve", "solenoid_valve", "check_valve",
         "filter")


def valve_document(kind, params=None, rotation=0):
    ports = describe(kind, params or {})["ports"]
    return validate_scene(dict(schemaVersion=1, page=dict(width=600, height=500),
                               nodes=[dict(id="valve", type=kind,
                                           params=params or {}, x=300, y=250,
                                           rotation=rotation)],
                               junctions=[dict(id="end", x=70, y=60)],
                               edges=[dict(id=f"pipe-{i}",
                                           source=dict(nodeId="valve", portId=p),
                                           target=dict(junctionId="end"))
                                      for i, p in enumerate(ports)],
                               labels=[dict(id="tag", nodeId="valve", text=kind,
                                            x=0, y=60)]))


@pytest.mark.parametrize("kind,params", [
    *((kind, {}) for kind in KINDS),
    ("four_way_valve", dict(r=8, mark=True)),
    ("four_way_valve", dict(r=150, mark=False)),
    ("globe_valve", dict(w=16, h=12, stem=100, handle=240)),
    ("solenoid_valve", dict(r=6, stem=100, handle=240)),
    ("check_valve", dict(w=300, h=180, stub=100, point="w")),
    ("filter", dict(w=16, h=180, stub=100, n=25)),
])
def test_valve_bounds_contain_ports_actuators_and_port_letters(kind, params):
    geometry = describe(kind, params)
    x, y, width, height = geometry["box"]
    for port in geometry["ports"].values():
        px, py = port["point"]
        assert x < px < x + width and y < py < y + height
    before = plt.get_fignums()
    with Diagram(width=width, height=height) as diagram:
        diagram.add(make_registered(kind, params), None, loc=(-x, -y))
        diagram.render()
        diagram.fig.canvas.draw()
        renderer = diagram.fig.canvas.get_renderer()
        canvas = diagram.ax.get_window_extent(renderer)
        for artist in [*diagram.ax.lines, *diagram.ax.patches, *diagram.ax.texts]:
            bounds = artist.get_window_extent(renderer)
            assert canvas.x0 <= bounds.x0 <= bounds.x1 <= canvas.x1
            assert canvas.y0 <= bounds.y0 <= bounds.y1 <= canvas.y1
    assert plt.get_fignums() == before


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_valve_ports_rotate_with_geometry_and_keep_connections(kind, rotation):
    document = valve_document(kind, rotation=rotation)
    scene = resolve_scene(document)
    nodes = {node["id"]: node for node in scene["nodes"]}
    part = make_registered(kind, {})
    for edge in scene["edges"]:
        name = edge["source"]["portId"]
        expected = rotate(part.port(name), rotation)
        result = endpoint(edge["source"], nodes, {})
        assert result["point"] == [300 + expected[0], 250 + expected[1]]
        assert result["direction"] == rotate(part.direction(name), rotation)
        assert edge["points"][0] == result["point"]
        assert all(a[0] == b[0] or a[1] == b[1]
                   for a, b in zip(edge["points"], edge["points"][1:]))
    assert resolve_scene(json.loads(json.dumps(document)))["edges"] == scene["edges"]


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_four_way_export_letters_follow_the_same_rotated_ports_as_browser(angle):
    document = valve_document("four_way_valve", rotation=angle)
    mapping = dict(D="exhaust", C="condenser", E="evaporator", S="suction")
    offsets = dict(D=(0, -42), C=(42, 0), E=(0, 42), S=(-42, 0))
    with build_scene(document) as diagram:
        texts = {text.get_text(): text for text in diagram.ax.texts
                 if text.get_text() in mapping}
        assert set(texts) == set(mapping)
        for letter, text in texts.items():
            rendered = diagram.ax.transData.inverted().transform(
                text.get_transform().transform(text.get_position()))
            offset = rotate(offsets[letter], angle)
            assert rendered == pytest.approx([300 + offset[0], 250 + offset[1]])
            assert text.get_rotation() == (-angle) % 360
    document["nodes"][0]["params"]["mark"] = False
    with build_scene(document) as diagram:
        assert not any(text.get_text() in mapping for text in diagram.ax.texts)


def test_check_valve_reverse_direction_exchanges_port_positions_and_normals():
    right = describe("check_valve", dict(point="e", w=70, stub=20))["ports"]
    left = describe("check_valve", dict(point="w", w=70, stub=20))["ports"]
    assert left["in"] == right["out"] and left["out"] == right["in"]
    assert right["in"]["point"] == [-55, 0]


@pytest.mark.parametrize("point", ["e", "w"])
@pytest.mark.parametrize("style", ["solid", "hollow"])
def test_check_valve_styles_preserve_ports_and_hollow_body_has_no_through_line(
        point, style):
    part = parts.make_check_valve(70, 40, 20, point, "兼容名称", style=style)
    assert part.name == "兼容名称"
    assert part.ports == parts.make_check_valve(70, 40, 20, point).ports
    assert describe("check_valve", dict(point=point, style=style)) == describe(
        "check_valve", dict(point=point))
    with Diagram(width=200, height=140) as diagram:
        diagram.add(part, None, loc=(100, 70))
        diagram.render()
        body = next(p for p in diagram.ax.patches if isinstance(p, Polygon))
        assert body.get_facecolor() == to_rgba(LINE if style == "solid" else FILL)
        assert body.get_edgecolor() == to_rgba(LINE)
        horizontal = [line for line in diagram.ax.lines
                      if list(line.get_ydata()) == [70, 70]]
        if style == "hollow":
            assert len(horizontal) == 2
            assert all(max(line.get_xdata()) <= 65
                       or min(line.get_xdata()) >= 135 for line in horizontal)
        else:
            assert len(horizontal) == 1
            assert sorted(horizontal[0].get_xdata()) == [45, 155]


def test_check_valve_style_defaults_catalog_and_invalid_values():
    assert normalize_params("check_valve", {})["style"] == "solid"
    entry = next(item for item in catalog() if item["type"] == "check_valve")
    assert entry["fields"]["style"]["optionLabels"]["hollow"] == "空心黑框"
    for value in ("outline", "", None, True):
        with pytest.raises(ValueError, match="style"):
            normalize_params("check_valve", dict(style=value))
        with pytest.raises(ValueError, match="style"):
            parts.make_check_valve(style=value)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("mounted", [False, True])
def test_hollow_check_valve_roundtrip_rotated_connections_and_export(rotation, mounted):
    document = valve_document("check_valve", dict(point="w"), rotation)
    if mounted:
        document["edges"] = [dict(id="parent", source=dict(junctionId="a"),
                                  target=dict(junctionId="end"))]
        document["junctions"].append(dict(id="a", x=450, y=60))
        document["nodes"][0]["mount"] = dict(edgeId="parent", at=.5)
    solid = resolve_for_editor(document)
    document["nodes"][0]["params"]["style"] = "hollow"
    hollow = resolve_for_editor(document)
    assert hollow["edges"] == solid["edges"]
    hollow_geometry = hollow["nodes"][0]["geometry"]
    solid_geometry = solid["nodes"][0]["geometry"]
    assert hollow_geometry["ports"] == solid_geometry["ports"]
    assert hollow_geometry["image"] != solid_geometry["image"]
    saved = hollow["document"]
    assert validate_scene(json.loads(json.dumps(saved))) == saved
    for fmt, signature in (("svg", b"<?xml"), ("png", b"\x89PNG"),
                           ("pdf", b"%PDF")):
        assert export_scene(saved, fmt).startswith(signature)


@pytest.mark.parametrize("params", [dict(n=3.5), dict(n=True), dict(n=26),
                                    dict(n=2), dict(n="7")])
def test_filter_grid_count_rejects_invalid_numbers(params):
    with pytest.raises(ValueError):
        normalize_params("filter", params)


def test_filter_grid_count_normalizes_whole_number_and_ui_step():
    assert normalize_params("filter", dict(n=7.0))["n"] == 7
    assert isinstance(normalize_params("filter", dict(n=7.0))["n"], int)
    fields = next(item["fields"] for item in catalog() if item["type"] == "filter")
    assert fields["n"]["step"] == 1


@pytest.mark.parametrize("orient", ["h", "v"])
@pytest.mark.parametrize("style", ["circle_x", "dome"])
@pytest.mark.parametrize("r", [4, 10, 80])
def test_expansion_valve_style_drawing_bounds_ports_and_closed_dome(orient, style, r):
    params = dict(r=r, orient=orient, style=style)
    geometry = describe("expansion_valve", params)
    x, y, width, height = geometry["box"]
    part = parts.make_expansion_valve_x(r, orient, "兼容名称", style=style)
    assert part.name == "兼容名称"
    assert part.ports == parts.make_expansion_valve_x(r, orient).ports
    with Diagram(width=width, height=height) as diagram:
        diagram.add(part, None, loc=(-x, -y))
        diagram.render()
        diagram.fig.canvas.draw()
        renderer = diagram.fig.canvas.get_renderer()
        canvas = diagram.ax.get_window_extent(renderer)
        for artist in [*diagram.ax.lines, *diagram.ax.patches]:
            bounds = artist.get_window_extent(renderer)
            assert canvas.x0 <= bounds.x0 <= bounds.x1 <= canvas.x1
            assert canvas.y0 <= bounds.y0 <= bounds.y1 <= canvas.y1
        triangles = [p for p in diagram.ax.patches if isinstance(p, Polygon)]
        assert len(triangles) == (2 if style == "dome" else 0)
        if style == "dome":
            assert all(p.get_facecolor() == to_rgba(FILL) for p in triangles)
            for px, py in part.ports.values():
                assert any(abs((p.get_xy()[0][0] + p.get_xy()[1][0]) / 2
                               - (px-x)) < 1e-9
                           and abs((p.get_xy()[0][1] + p.get_xy()[1][1]) / 2
                                   - (py-y)) < 1e-9 for p in triangles)
            dome = next(line for line in diagram.ax.lines if len(line.get_xdata()) > 3)
            assert dome.get_xdata()[0] == pytest.approx(dome.get_xdata()[-1])
            assert dome.get_ydata()[0] == pytest.approx(dome.get_ydata()[-1])
            assert len(diagram.ax.lines) == 2  # 阀杆及闭合穹顶,无贯穿阀体的管线


def test_expansion_valve_style_default_labels_and_rejection():
    assert normalize_params("expansion_valve", {})["style"] == "circle_x"
    entry = next(item for item in catalog() if item["type"] == "expansion_valve")
    assert entry["fields"]["style"]["optionLabels"]["dome"] == "对顶三角＋半圆穹顶"
    for value in ("bowtie", "", None, True):
        with pytest.raises(ValueError, match="style"):
            normalize_params("expansion_valve", dict(style=value))
        with pytest.raises(ValueError, match="style"):
            parts.make_expansion_valve_x(style=value)


@pytest.mark.parametrize("orient", ["h", "v"])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("mounted", [False, True])
def test_expansion_dome_switch_preserves_connections_mounts_and_exports(
        orient, rotation, mounted):
    document = valve_document("expansion_valve", dict(orient=orient), rotation)
    if mounted:
        document["edges"] = [dict(id="parent", source=dict(junctionId="a"),
                                  target=dict(junctionId="end"))]
        document["junctions"].append(dict(id="a", x=450, y=60))
        document["nodes"][0]["mount"] = dict(edgeId="parent", at=.5, reverse=True)
    circle = resolve_for_editor(document)
    document["nodes"][0]["params"]["style"] = "dome"
    dome = resolve_for_editor(document)
    assert dome["edges"] == circle["edges"]
    old, new = circle["nodes"][0], dome["nodes"][0]
    assert [old[k] for k in ("x", "y", "rotation")] == [
        new[k] for k in ("x", "y", "rotation")]
    assert old.get("mount") == new.get("mount")
    assert old["geometry"]["ports"] == new["geometry"]["ports"]
    assert old["geometry"]["image"] != new["geometry"]["image"]
    saved = dome["document"]
    assert validate_scene(json.loads(json.dumps(saved))) == saved
    for fmt, signature in (("svg", b"<?xml"), ("png", b"\x89PNG"), ("pdf", b"%PDF")):
        assert export_scene(saved, fmt).startswith(signature)


@pytest.mark.parametrize("orient", ["h", "v"])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_expansion_dome_stays_above_or_right_after_manual_rotation(orient, rotation):
    document = valve_document("expansion_valve", dict(orient=orient, style="dome"),
                              rotation)
    assert_upright_dome(document)


def assert_upright_dome(document):
    scene = resolve_scene(document)
    node = scene["nodes"][0]
    adjustment = run_geometry_script(
        "console.log(JSON.stringify(geometry.glyphRotation(cases)));", node)
    native = 90 if node["params"]["orient"] == "v" else 0
    angle = (node["rotation"] + native + adjustment) % 360
    assert angle in (0, 90)
    with build_scene(document) as diagram:
        dome = next(line for line in diagram.ax.lines if len(line.get_xdata()) > 3)
        display = dome.get_transform().transform(
            list(zip(dome.get_xdata(), dome.get_ydata())))
        points = diagram.ax.transData.inverted().transform(display)
        xs, ys = points[:, 0], points[:, 1]
        if angle == 0:
            assert max(ys) < node["y"] - node["params"]["r"]
        else:
            assert min(xs) > node["x"] + node["params"]["r"]
        x, y, w, h = node["geometry"]["box"]
        corners = [rotate(point, node["rotation"]) for point in (
            [x, y], [x+w, y], [x, y+h], [x+w, y+h])]
        assert min(xs) >= node["x"] + min(p[0] for p in corners)
        assert max(xs) <= node["x"] + max(p[0] for p in corners)
        assert min(ys) >= node["y"] + min(p[1] for p in corners)
        assert max(ys) <= node["y"] + max(p[1] for p in corners)
    assert validate_scene(json.loads(json.dumps(document))) == document


@pytest.mark.parametrize("orient", ["h", "v"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("points", [
    [[100, 200], [500, 200]], [[500, 200], [100, 200]],
    [[300, 60], [300, 400]], [[300, 400], [300, 60]]])
def test_mounted_expansion_dome_stays_upright_for_both_pipe_directions(
        orient, reverse, points):
    document = valve_document("expansion_valve", dict(orient=orient, style="dome"))
    document["junctions"] = [dict(id=key, x=p[0], y=p[1])
                             for key, p in zip(("a", "b"), points)]
    document["edges"] = [dict(id="parent", source=dict(junctionId="a"),
                              target=dict(junctionId="b"))]
    document["nodes"][0]["mount"] = dict(edgeId="parent", at=.5, reverse=reverse)
    document = validate_scene(document)
    before = resolve_scene(document)
    assert_upright_dome(document)
    document["nodes"][0]["params"]["style"] = "circle_x"
    circle = resolve_scene(document)
    assert before["edges"] == circle["edges"]
    old_ports = before["nodes"][0]["geometry"]["ports"]
    assert old_ports == circle["nodes"][0]["geometry"]["ports"]
    assert before["nodes"][0]["rotation"] == circle["nodes"][0]["rotation"]


@pytest.mark.parametrize("kind", KINDS)
def test_valve_svg_and_all_export_formats_after_resizing(kind):
    params = {"r": 38} if kind in ("four_way_valve", "solenoid_valve") else {
        "w": 72, "h": 40}
    document = valve_document(kind, params=params, rotation=90)
    scene = resolve_for_editor(document)
    assert scene["nodes"][0]["geometry"]["image"].startswith(
        "data:image/svg+xml;base64,")
    for fmt, signature in (("svg", b"<?xml"), ("png", b"\x89PNG"),
                           ("pdf", b"%PDF")):
        assert export_scene(document, fmt).startswith(signature)


@pytest.mark.parametrize("params", [
    {}, dict(r=6, stem=4, handle=8), dict(r=120, stem=100, handle=240),
    dict(r=6, stem=100, handle=240), dict(r=120, stem=4, handle=8),
    dict(r=6, stem=4, handle=240)])
def test_solenoid_bowtie_sigma_drawing_bounds_ports_and_adjustable_coil(params):
    params = normalize_params("solenoid_valve", dict(params, style="bowtie"))
    geometry = describe("solenoid_valve", params)
    x, y, width, height = geometry["box"]
    r, stem, handle = (params[key] for key in ("r", "stem", "handle"))
    part = parts.make_solenoid_valve(r, stem, handle, "兼容名称", style="bowtie")
    assert part.name == "兼容名称"
    assert part.ports == parts.make_solenoid_valve(r, stem, handle).ports
    assert geometry["ports"] == describe("solenoid_valve", dict(
        params, style="circle_x"))["ports"]
    with Diagram(width=width, height=height) as diagram:
        diagram.add(part, None, loc=(-x, -y))
        diagram.render()
        diagram.fig.canvas.draw()
        renderer = diagram.fig.canvas.get_renderer()
        canvas = diagram.ax.get_window_extent(renderer)
        for artist in [*diagram.ax.lines, *diagram.ax.patches]:
            bounds = artist.get_window_extent(renderer)
            assert canvas.x0 <= bounds.x0 <= bounds.x1 <= canvas.x1
            assert canvas.y0 <= bounds.y0 <= bounds.y1 <= canvas.y1
        triangles = [p for p in diagram.ax.patches if isinstance(p, Polygon)]
        assert len(triangles) == 2
        assert all(p.get_facecolor() == to_rgba(FILL) for p in triangles)
        assert all(p.get_edgecolor() == to_rgba(LINE) for p in triangles)
        sigma = next(line for line in diagram.ax.lines if len(line.get_xdata()) == 3)
        assert list(sigma.get_xdata()) == pytest.approx(
            [-x-handle*26/48, -x-handle*7/48, -x+handle*8/48])
        assert list(sigma.get_ydata()) == pytest.approx(
            [-y-r, -y-r-0.65*stem, -y-r-0.65*stem])
        assert len(diagram.ax.lines) == 5  # 阀杆、横杆、Σ、两侧短接管
        horizontal = [line for line in diagram.ax.lines
                      if list(line.get_ydata()) == [-y, -y]]
        assert len(horizontal) == 2
        assert all(max(line.get_xdata()) <= -x-r
                   or min(line.get_xdata()) >= -x+r for line in horizontal)


def test_solenoid_style_defaults_labels_and_invalid_values():
    assert normalize_params("solenoid_valve", {})["style"] == "circle_x"
    entry = next(item for item in catalog() if item["type"] == "solenoid_valve")
    labels = entry["fields"]["style"]["optionLabels"]
    assert labels["bowtie"] == "对顶三角＋横杆＋Σ 折线"
    for value in ("sigma", "", None, True):
        with pytest.raises(ValueError, match="style"):
            normalize_params("solenoid_valve", dict(style=value))
        with pytest.raises(ValueError, match="style"):
            parts.make_solenoid_valve(style=value)


def assert_solenoid_sigma_upright(document):
    node = resolve_scene(document)["nodes"][0]
    adjustment = run_geometry_script(
        "console.log(JSON.stringify(geometry.glyphRotation(cases)));", node)
    angle = (node["rotation"] + adjustment) % 360
    assert angle in (0, 90)
    with build_scene(document) as diagram:
        sigma = next(line for line in diagram.ax.lines if len(line.get_xdata()) == 3
                     and line.get_ydata()[0] != line.get_ydata()[1]
                     and line.get_ydata()[1] == line.get_ydata()[2])
        display = sigma.get_transform().transform(
            list(zip(sigma.get_xdata(), sigma.get_ydata())))
        points = diagram.ax.transData.inverted().transform(display)
        xs, ys = points[:, 0], points[:, 1]
        if angle == 0:
            assert max(ys) < node["y"]
        else:
            assert min(xs) > node["x"]
        x, y, w, h = node["geometry"]["box"]
        corners = [rotate(p, node["rotation"]) for p in (
            [x, y], [x+w, y], [x, y+h], [x+w, y+h])]
        assert min(xs) >= node["x"] + min(p[0] for p in corners)
        assert max(xs) <= node["x"] + max(p[0] for p in corners)
        assert min(ys) >= node["y"] + min(p[1] for p in corners)
        assert max(ys) <= node["y"] + max(p[1] for p in corners)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("mounted", [False, True])
def test_solenoid_style_switch_preserves_ports_pipes_mounts_and_export(
        rotation, mounted):
    document = valve_document("solenoid_valve", rotation=rotation)
    if mounted:
        document["junctions"] = [dict(id="a", x=450, y=80),
                                 dict(id="end", x=70, y=80)]
        document["edges"] = [dict(id="parent", source=dict(junctionId="a"),
                                  target=dict(junctionId="end"))]
        document["nodes"][0]["mount"] = dict(edgeId="parent", at=.5,
                                             reverse=rotation >= 180)
    old = resolve_for_editor(document)
    document["nodes"][0]["params"]["style"] = "bowtie"
    new = resolve_for_editor(document)
    assert old["edges"] == new["edges"]
    a, b = old["nodes"][0], new["nodes"][0]
    for key in ("x", "y", "rotation", "mount"):
        assert a.get(key) == b.get(key)
    assert a["geometry"]["ports"] == b["geometry"]["ports"]
    assert a["geometry"]["image"] != b["geometry"]["image"]
    saved = new["document"]
    assert validate_scene(json.loads(json.dumps(saved))) == saved
    assert_solenoid_sigma_upright(saved)
    for fmt, signature in (("svg", b"<?xml"), ("png", b"\x89PNG"), ("pdf", b"%PDF")):
        assert export_scene(saved, fmt).startswith(signature)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("points", [
    [[100, 200], [500, 200]], [[500, 200], [100, 200]],
    [[300, 60], [300, 400]], [[300, 400], [300, 60]]])
def test_solenoid_bowtie_mount_frontend_backend_upright(points, reverse):
    document = valve_document("solenoid_valve", dict(style="bowtie"))
    document["junctions"] = [dict(id=key, x=p[0], y=p[1])
                             for key, p in zip(("a", "b"), points)]
    document["edges"] = [dict(id="parent", source=dict(junctionId="a"),
                              target=dict(junctionId="b"))]
    document["nodes"][0]["mount"] = dict(edgeId="parent", at=.5, reverse=reverse)
    document = validate_scene(document)
    scene = resolve_scene(document)
    actual = run_geometry_script(
        "console.log(JSON.stringify(geometry.mountedNodes(cases.document,cases.nodes)[0]));",
        scene)
    node = scene["nodes"][0]
    assert [actual[k] for k in ("x", "y", "rotation")] == [
        node[k] for k in ("x", "y", "rotation")]
    assert_solenoid_sigma_upright(document)
