"""服务管理仅停止同一项目的已核验实例，临时端口不影响用户服务。"""

import http.client
import json
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from server import manage, service
from server.run import make_server


def test_health_has_identity_without_shutdown_secret():
    with make_server(0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            data = manage.health(server.server_port)
            assert data["app"] == "rrplot"
            assert data["projectId"] == service.PROJECT_ID
            assert data["instanceId"] == server.identity["instanceId"]
            assert data["build"] == data["diskBuild"]
            assert data["codeChanged"] is False
            assert "token" not in data
            assert server.shutdown_token not in json.dumps(data)
        finally:
            server.shutdown()
            worker.join(5)


@pytest.mark.parametrize("origin,valid", [(None, False), ("http://localhost", True)])
def test_shutdown_rejects_wrong_secret_and_browser_origin(origin, valid):
    with make_server(0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        try:
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            connection.request(
                "POST",
                "/api/shutdown",
                json.dumps(dict(token=server.shutdown_token if valid else "bad")),
                headers,
            )
            response = connection.getresponse()
            assert response.status == 403
            assert json.loads(response.read())["error"]
            assert manage.health(server.server_port)["ok"]
        finally:
            connection.close()
            server.shutdown()
            worker.join(5)


@pytest.mark.parametrize(
    "state,info",
    [
        ("legacy", dict(ok=True, version="old")),
        ("foreign", dict(app="other")),
        ("foreign", dict(app="rrplot", projectId="other-project")),
    ],
)
def test_legacy_and_foreign_services_are_never_stopped(monkeypatch, state, info):
    monkeypatch.setattr(manage, "health", lambda port: info)
    assert manage.inspect(12345)[0] == state
    assert manage.stop(12345) == 1


def test_stale_instance_record_cannot_stop_server(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "STATE", tmp_path)
    with make_server(0) as server:
        service.save_instance(server)
        path = service.state_path(server.server_port)
        saved = json.loads(path.read_text())
        saved["instanceId"] = "stale-instance"
        path.write_text(json.dumps(saved))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            assert manage.stop(server.server_port) == 1
            assert manage.health(server.server_port)["ok"]
            service.remove_instance(server)
            assert path.exists()
        finally:
            server.shutdown()
            worker.join(5)


def test_code_fingerprint_changes_when_source_changes(tmp_path, monkeypatch):
    for folder in ("rrplot", "server", "web"):
        (tmp_path / folder).mkdir()
    source = tmp_path / "web/app.js"
    source.write_text("first")
    monkeypatch.setattr(service, "ROOT", tmp_path)
    first = service.code_fingerprint()
    source.write_text("second")
    assert service.code_fingerprint() != first
    assert service.code_fingerprint() == service.code_fingerprint()


def test_real_service_start_status_restart_and_stop():
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    def command(action):
        result = subprocess.run(
            [
                sys.executable,
                str(root / "server/manage.py"),
                action,
                "--port",
                str(port),
                "--background",
            ],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=40,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    try:
        command("start")
        original = manage.health(port)
        assert original and original["ok"]
        command("start")
        assert manage.health(port)["instanceId"] == original["instanceId"]
        command("status")
        command("restart")
        assert manage.health(port)["instanceId"] != original["instanceId"]
        command("stop")
        assert not manage.listening(port)
        assert not service.state_path(port).exists()
        command("stop")
    finally:
        if manage.health(port):
            manage.stop(port)
