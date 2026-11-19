"""图元去重传输对旧客户端、样式与几何保持兼容。"""
import copy
import json

import pytest
from test_web_requests import run_module
from test_web_server import post, service  # noqa: F401

from rrplot.registry import catalog, describe, glyph_rotation, normalize_params
from rrplot.scene_renderer import resolve_for_editor
from tools.benchmark_web import sample_document


def test_shared_images_preserve_exact_geometry_and_reduce_payload():
    document = sample_document(50)
    before = copy.deepcopy(document)
    legacy = resolve_for_editor(document)
    shared = resolve_for_editor(document, shared_glyphs=True)
    assert document == before
    assert len(shared["glyphs"]) == 1
    for old, new in zip(legacy["nodes"], shared["nodes"]):
        geometry = dict(new["geometry"])
        geometry["image"] = shared["glyphs"][geometry.pop("glyphId")]
        assert geometry == old["geometry"]
    assert len(json.dumps(shared)) < len(json.dumps(legacy)) * .6
    changed = copy.deepcopy(document)
    changed["nodes"][0]["params"] = dict(shape="rect_diag")
    assert len(resolve_for_editor(changed, shared_glyphs=True)["glyphs"]) == 2


def test_shared_http_protocol_is_explicit_and_stateless(service):  # noqa: F811
    document = sample_document(2)
    status, _, data = post(service, "/api/resolve",
                           dict(document=document, sharedGlyphs=True))
    assert status == 200
    shared = json.loads(data)
    assert len(shared["glyphs"]) == 1
    assert "image" not in shared["nodes"][0]["geometry"]
    assert "sharedGlyphs" in shared["features"]
    status, _, data = post(service, "/api/resolve", dict(document=document))
    assert status == 200 and "image" in json.loads(data)["nodes"][0]["geometry"]


def test_client_cache_hydrates_legacy_shared_and_evicted_entries():
    result = run_module(
        "glyphs.js",
        """
      const hydrate=module.createGlyphCache(1);
      const scene=(id,glyphs)=>({glyphs,nodes:[{geometry:{glyphId:id}}]});
      const shared=hydrate(scene('a',{a:'SVG-A'}));
      const same=hydrate(scene('a',{}));
      const legacy=hydrate({nodes:[{geometry:{image:'OLD'}}]});
      hydrate(scene('b',{b:'SVG-B'}));let missing=false;
      try{hydrate(scene('a',{}));}catch{missing=true;}
      console.log(JSON.stringify({values:[shared.nodes[0].geometry.image,
        same.nodes[0].geometry.image,legacy.nodes[0].geometry.image],missing}));
    """,
    )
    assert result == dict(values=["SVG-A", "SVG-A", "OLD"], missing=True)


@pytest.mark.parametrize("kind,style", [("expansion_valve", "dome"),
                                       ("solenoid_valve", "bowtie")])
def test_capability_policy_matches_browser_upright_rotation(kind, style):
    params = normalize_params(kind, dict(style=style))
    nodes = [dict(type=kind, params=params, rotation=rotation,
                  geometry=describe(kind, params))
             for rotation in (0, 90, 180, 270)]
    script = ("console.log(JSON.stringify(" + json.dumps(nodes)
              + ".map(module.glyphRotation)));")
    assert run_module("geometry.js", script) == [glyph_rotation(kind, params, r)
                                                for r in (0, 90, 180, 270)]


def test_catalog_capabilities_and_geometry_agree_without_mutable_shared_state():
    for item in catalog():
        assert item["capabilities"] == describe(item["type"], {})["capabilities"]
    first = catalog()
    first[0]["capabilities"]["rotationStep"] = 1
    assert catalog()[0]["capabilities"]["rotationStep"] == 90
