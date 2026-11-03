"""对象列表按用户可见名称、连接和附着关系检索，不改变图纸。"""
import base64
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrplot.registry import catalog
from rrplot.scene import TEMPLATES, load_template


def search(document, query="", kind=""):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed; optional JavaScript object search check")
    raw = Path(__file__).resolve().parents[1].joinpath("web/objects.js").read_bytes()
    uri = "data:text/javascript;base64," + base64.b64encode(raw).decode()
    script = ("import fs from 'node:fs';const objects=await import("
              + json.dumps(uri) + ");const input=JSON.parse(fs.readFileSync(0,'utf8'));"
              "const before=JSON.stringify(input);"
              "const entries=objects.objectIndex(input.document,input.catalog);"
              "const found=objects.filterObjects(entries,input.query,input.kind);"
              "console.log(JSON.stringify({entries,found,"
              "unchanged:before===JSON.stringify(input)}));")
    result = subprocess.run([executable, "--input-type=module", "-e", script],
                            input=json.dumps(dict(document=document, catalog=catalog(),
                                                 query=query, kind=kind)),
                            encoding="utf-8", capture_output=True, check=True)
    output = json.loads(result.stdout)
    assert output["unchanged"]
    return output


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_every_template_object_has_stable_type_and_id(name):
    document = load_template(name)
    entries = search(document)["entries"]
    expected = [(kind, item["id"])
                for kind, collection in (("node", "nodes"), ("edge", "edges"),
                                         ("junction", "junctions"),
                                         ("label", "labels"))
                for item in document[collection]]
    assert [(entry["kind"], entry["id"]) for entry in entries] == expected
    assert all(entry["title"] and entry["detail"] for entry in entries)


@pytest.mark.parametrize("query", ["eev1", "ＥＥＶ１", "膨胀阀 eev1",
                                   "  EEV1 \n expansion_valve  "])
def test_name_id_type_and_unicode_search_with_all_words(query):
    document = load_template("evi_ftvi")
    result = search(document, query, "node")["found"]
    assert [entry["id"] for entry in result] == ["eev1"]


def test_pipe_search_accepts_device_title_id_and_port():
    document = load_template("evi_ftvi")
    document["nodes"][-1]["title"] = "支路电子阀"
    for query in ("过冷器 压缩机", "subcooler comp", "right left"):
        result = search(document, query, "edge")["found"]
        assert "injection" in [entry["id"] for entry in result]
    result = search(document, "支路电子阀", "edge")["found"]
    assert any("支路电子阀" in entry["title"] for entry in result)


def test_attached_labels_are_searchable_by_parent_or_pipe_endpoints():
    document = load_template("evi_ftvi")
    document["labels"].extend([
        dict(id="state", edgeId="injection", text="T=30℃", x=0, y=0),
        dict(id="device-note", nodeId="comp", text="A", x=0, y=0),
        dict(id="free", text="A", x=0, y=0),
    ])
    found = search(document, "T=30℃ 压缩机", "label")["found"]
    assert [entry["id"] for entry in found] == ["state"]
    assert found[0]["detail"] == "附着管路：injection"
    found = search(document, "comp device-note", "label")["found"]
    assert [entry["id"] for entry in found] == ["device-note"]
    assert "压缩机" in found[0]["detail"]
    assert search(document, "free", "label")["found"][0]["detail"] == "独立文字"


def test_filters_distinguish_same_id_in_different_collections():
    document = load_template("evi_ftvi")
    document["junctions"].append(dict(id="comp", x=0, y=0))
    found = search(document, "comp", "junction")["found"]
    assert [(entry["kind"], entry["id"]) for entry in found] == [("junction", "comp")]
    assert search(document, "missing", "node")["found"] == []
    assert search(document, "", "invalid")["found"] == []


def test_empty_document_and_changes_do_not_reuse_old_search_entries():
    empty = dict(nodes=[], edges=[], junctions=[], labels=[])
    assert search(empty)["entries"] == []
    document = load_template("evi_ftvi")
    changed = copy.deepcopy(document)
    changed["nodes"][0]["title"] = "重命名设备"
    changed["labels"] = []
    entries = search(changed)["entries"]
    assert not any(entry["kind"] == "label" for entry in entries)
    assert search(changed, "重命名设备", "node")["found"]
    assert search(document, "重命名设备")["found"] == []


def test_many_objects_remain_searchable_beyond_display_limit():
    document = dict(nodes=[], edges=[], junctions=[], labels=[
        dict(id=f"text-{i}", text=f"文字 {i}", x=0, y=0) for i in range(300)
    ])
    found = search(document, "text-299")["found"]
    assert [entry["id"] for entry in found] == ["text-299"]
