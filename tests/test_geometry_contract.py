"""同一 JSON 夹具在 Python 和 JavaScript 两侧解释，防止画布与导出偏离。"""

import json
from pathlib import Path

import pytest
from test_web_connections import connection_scenario
from test_web_geometry import run_geometry_script

from rrplot.registry import REGISTRY, normalize_params
from rrplot.scene import resolve_scene, route

CONTRACT = json.loads(
    Path(__file__)
    .with_name("fixtures")
    .joinpath("geometry_contract.json")
    .read_text(encoding="utf-8")
)


def test_shared_route_contract():
    cases = CONTRACT["routes"]
    result = run_geometry_script(
        "console.log(JSON.stringify(cases.map(c=>"
        "geometry.route(c.source,c.target,c.vertices))));",
        cases,
    )
    assert result == [route(c["source"], c["target"], c["vertices"]) for c in cases]


@pytest.mark.parametrize("size", ["min", "default", "max"])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize(
    "kind,style", [("expansion_valve", "dome"), ("solenoid_valve", "bowtie")]
)
def test_shared_mount_contract(kind, style, rotation, size):
    size = REGISTRY[kind]["fields"]["r"][size]
    scenes = []
    for case in CONTRACT["mounts"]:
        points = case["points"]
        scenes.append(
            resolve_scene(
                dict(
                    schemaVersion=1,
                    nodes=[
                        dict(
                            id="valve",
                            type=kind,
                            x=0,
                            y=0,
                            rotation=rotation,
                            params=normalize_params(kind, dict(r=size, style=style)),
                            mount=dict(
                                edgeId="pipe", at=case["at"], reverse=case["reverse"]
                            ),
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
                )
            )
        )
    result = run_geometry_script(
        "console.log(JSON.stringify(cases.map(s=>{"
        "const nodes=geometry.mountedNodes(s.document,s.nodes);"
        "return {pose:nodes.map(n=>[n.x,n.y,n.rotation]),"
        "routes:s.document.edges.map(e=>geometry.route("
        "geometry.endpoint(e.source,nodes,s.document.junctions),"
        "geometry.endpoint(e.target,nodes,s.document.junctions),e.vertices))};})));",
        scenes,
    )
    for scene, actual in zip(scenes, result):
        assert actual["pose"][0] == pytest.approx(
            [scene["nodes"][0][key] for key in ("x", "y", "rotation")]
        )
        assert actual["routes"] == [edge["points"] for edge in scene["edges"]]


@pytest.mark.parametrize("case", CONTRACT["mounts"], ids=lambda c: c["name"])
def test_shared_junction_split_and_merge_preserves_mount(case):
    points = case["points"]
    document = dict(
        schemaVersion=1,
        nodes=[
            dict(
                id="valve",
                type="globe_valve",
                x=0,
                y=0,
                mount=dict(edgeId="pipe", at=case["at"], reverse=case["reverse"]),
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
    )
    original = resolve_scene(document)["nodes"][0]
    output = connection_scenario(
        """
      splitEdge(doc.edges[0],.5);results.push(snapshot());
      const junction=doc.junctions.at(-1);
      setSelection('junction',junction.id);removeSelected();results.push(snapshot());
    """,
        document,
    )
    for index, state in enumerate(output["results"]):
        resolved = resolve_scene(state["doc"])
        node = resolved["nodes"][0]
        assert [node[k] for k in ("x", "y", "rotation")] == pytest.approx(
            [original[k] for k in ("x", "y", "rotation")]
        )
        assert len(resolved["edges"]) == (2 if index == 0 else 1)
