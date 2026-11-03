"""本机 HTTP 边界和编辑器实际调用的接口。"""
import http.client
import json
import socket
import threading

import pytest

from server.run import make_server


@pytest.fixture(scope="module")
def service():
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def request(port, path, body=None, headers=None, timeout=20):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("POST" if body is not None else "GET", path,
                           body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def post(port, path, value):
    return request(port, path, json.dumps(value).encode(),
                   {"Content-Type": "application/json"})


def test_duplicate_server_cannot_bind_same_port(service):
    with pytest.raises(OSError):
        with make_server(service):
            pytest.fail("同一端口不应允许第二个服务启动")


def test_incomplete_connection_does_not_block_page(service):
    # 模拟浏览器预连接：连接已建立，但尚未发送 HTTP 请求。
    with socket.create_connection(("127.0.0.1", service), timeout=2):
        assert request(service, "/api/health", timeout=2)[0] == 200
        assert request(service, "/", timeout=2)[0] == 200


def test_static_and_catalog_interfaces(service):
    status, headers, body = request(service, "/")
    assert status == 200 and b'id="diagram"' in body
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert request(service, "/app.js")[1]["Content-Type"].startswith("text/javascript")
    status, headers, body = request(service, "/document.js")
    assert status == 200 and b"copySelection" in body
    assert headers["Content-Type"].startswith("text/javascript")
    status, headers, body = request(service, "/checks.js")
    assert status == 200 and b"inspectDiagram" in body
    assert headers["Content-Type"].startswith("text/javascript")
    status, headers, body = request(service, "/objects.js")
    assert status == 200 and b"objectIndex" in body
    assert headers["Content-Type"].startswith("text/javascript")
    assert json.loads(request(service, "/api/health")[2])["ok"] is True
    assert len(json.loads(request(service, "/api/catalog")[2])) == 6
    assert len(json.loads(request(service, "/api/templates")[2])) == 5
    for path in ("/../pyproject.toml", "/missing", "/api/missing"):
        assert request(service, path)[0] == 404
    assert request(service, "/api/templates/missing")[0] == 400


@pytest.mark.parametrize("name", [
    "evi_ftvi", "ftvi", "heat_pump", "heat_pump_receiver", "evi_intermediate"
])
def test_template_edit_reopen_preview_and_exports(service, name):
    document = json.loads(request(service, "/api/templates/" + name)[2])
    node = next(item for item in document["nodes"] if item["id"] in {"eev1", "eev"})
    node["x"] += 20
    status, _, data = post(service, "/api/resolve", {"document": document})
    assert status == 200
    resolved = json.loads(data)
    moved = next(item for item in resolved["nodes"] if item["id"] == node["id"])
    assert moved["x"] == node["x"]
    saved = json.loads(json.dumps(resolved["document"]))
    assert post(service, "/api/resolve", {"document": saved})[0] == 200
    status, headers, data = post(service, "/api/preview", {"document": saved})
    assert status == 200 and b"<svg" in data
    assert headers["Content-Type"] == "image/svg+xml"
    for fmt, signature in (("png", b"\x89PNG"), ("svg", b"<?xml"), ("pdf", b"%PDF")):
        status, headers, data = post(service, "/api/export/" + fmt,
                                     {"document": saved})
        assert status == 200 and data.startswith(signature)
        assert headers["Content-Disposition"] == f'attachment; filename="rrplot.{fmt}"'


@pytest.mark.parametrize("path,body,headers", [
    ("/api/resolve", b"{", {"Content-Type": "application/json"}),
    ("/api/resolve", b"{}", {}),
    ("/api/resolve", b"[]", {"Content-Type": "application/json"}),
    ("/api/resolve", b"{}", {"Content-Type": "application/json"}),
    ("/api/resolve", b"", {"Content-Type": "application/json"}),
    ("/api/resolve", b"", {"Content-Length": "5000001"}),
    ("/api/resolve", b"", {"Content-Length": "bad"}),
    ("/api/resolve", b' {"document":null}', {"Content-Type": "application/json"}),
    ("/api/export/gif", b'{"document":{}}', {"Content-Type": "application/json"}),
])
def test_invalid_requests_are_json_errors(service, path, body, headers):
    status, _, data = request(service, path, body, headers)
    assert status == 400 and json.loads(data)["error"]


def test_unknown_post_and_invalid_port(service):
    assert post(service, "/api/missing", {"document": {}})[0] == 404
    document = json.loads(request(service, "/api/templates/evi_ftvi")[2])
    document["edges"][0]["source"]["portId"] = "missing"
    status, _, data = post(service, "/api/resolve", {"document": document})
    assert status == 400 and json.loads(data)["error"]


def test_pipe_state_label_resolve_reopen_preview_and_exports(service):
    document = json.loads(request(service, "/api/templates/evi_ftvi")[2])
    document["labels"].append(dict(id="pipe-state", edgeId="injection", at=.25,
                                    x=8, y=-14, text="T1"))
    status, _, data = post(service, "/api/resolve", {"document": document})
    assert status == 200
    resolved = json.loads(data)
    assert "edgeLabels" in resolved["features"]
    state = next(label for label in resolved["labels"] if label["id"] == "pipe-state")
    assert state["position"] == [254.75, 258]
    reopened = json.loads(json.dumps(resolved["document"]))
    assert post(service, "/api/resolve", {"document": reopened})[0] == 200
    assert post(service, "/api/preview", {"document": reopened})[0] == 200
    for fmt, signature in (("svg", b"<?xml"), ("png", b"\x89PNG"), ("pdf", b"%PDF")):
        status, _, data = post(service, "/api/export/" + fmt, {"document": reopened})
        assert status == 200 and data.startswith(signature)
