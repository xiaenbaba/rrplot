"""统一入口：python server/manage.py start|status|stop|restart [--port 8765]。"""

import argparse
import http.client
import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.service import (  # noqa: E402
    PROJECT_ID,
    STATE,
    safe_console,
    state_path,
    wait_until,
)


def health(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        if response.status == 200:
            result = json.loads(response.read(65536))
            return result if isinstance(result, dict) else None
    except (OSError, ValueError, http.client.HTTPException):
        pass
    finally:
        connection.close()
    return None


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def inspect(port):
    info = health(port)
    if not info:
        return ("foreign" if listening(port) else "stopped"), {}
    if info.get("app") != "rrplot" or info.get("projectId") != PROJECT_ID:
        legacy = info.get("ok") is True and "version" in info and "app" not in info
        return ("legacy" if legacy else "foreign"), info
    return "running", info


def status(port):
    state, info = inspect(port)
    address = f"http://127.0.0.1:{port}/"
    if state == "running":
        print(
            f"运行中 {address} · v{info.get('version')} · PID {info.get('pid')}"
            f" · build {info.get('build')}"
        )
        if info.get("codeChanged"):
            print("代码已更新：请先保存 JSON，再运行 restart-web.cmd 并刷新页面。")
    elif state == "stopped":
        print(f"服务未启动：{address}")
    elif state == "legacy":
        print("检测到旧版服务，无法安全自动停止。请在原服务窗口按 Ctrl+C 后重新启动。")
    else:
        print(f"端口 {port} 已被其他程序或其他项目占用；不会停止该程序，请更换端口。")
    return state, info


def stop(port):
    state, info = status(port)
    if state == "stopped":
        return 0
    if state != "running":
        return 1
    try:
        saved = json.loads(state_path(port).read_text(encoding="utf-8"))
        if any(
            saved.get(key) != info.get(key)
            for key in ("instanceId", "projectId", "pid")
        ) or not isinstance(saved.get("token"), str):
            raise ValueError("实例信息不匹配")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"无法确认服务身份，保留现有进程：{exc}。请在原服务窗口按 Ctrl+C。")
        return 1
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(
            "POST",
            "/api/shutdown",
            json.dumps(dict(token=saved["token"])),
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response.read()
        if response.status != 200:
            raise ValueError("服务拒绝停止请求")
    except (OSError, ValueError, http.client.HTTPException) as exc:
        print(f"停止失败：{exc}")
        return 1
    finally:
        connection.close()
    if not wait_until(lambda: not listening(port), timeout=8):
        print("停止尚未完成，请稍后查询状态；未强制终止进程。")
        return 1
    print(f"已停止本项目端口 {port} 的服务。")
    return 0


def start(port, background=False):
    state, _ = status(port)
    if state == "running":
        return 0
    if state != "stopped":
        return 1
    command = [sys.executable, str(ROOT / "server/run.py"), "--port", str(port)]
    if not background:
        try:
            return subprocess.call(command, cwd=ROOT)
        except KeyboardInterrupt:
            return 0
    STATE.mkdir(exist_ok=True)
    log = STATE / f"service-{port}.log"
    options = (
        dict(creationflags=subprocess.CREATE_NO_WINDOW)
        if sys.platform == "win32"
        else dict(start_new_session=True)
    )
    with log.open("ab") as output:
        instance_id = secrets.token_hex(16)
        environment = dict(os.environ, RRPLOT_LAUNCH_ID=instance_id)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=environment,
            **options,
        )

    def ready():
        info = health(port)
        return (
            bool(
                info
                and info.get("projectId") == PROJECT_ID
                and info.get("instanceId") == instance_id
            )
            or process.poll() is not None
        )

    wait_until(ready)
    state, info = status(port)
    if state != "running" or info.get("instanceId") != instance_id:
        print(f"启动未确认，请查询状态和日志：{log}")
        return 1
    print(f"后台日志：{log}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "status", "stop", "restart"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--background", action="store_true", help="后台启动，日志写入 .rrplot-web"
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("端口必须为 1–65535")
    if args.action == "status":
        return 0 if status(args.port)[0] == "running" else 1
    if args.action in ("stop", "restart"):
        result = stop(args.port)
        if result or args.action == "stop":
            return result
    return start(args.port, args.background)


if __name__ == "__main__":
    safe_console()
    sys.exit(main())
