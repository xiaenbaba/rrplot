"""本机服务身份、代码指纹与实例文件；不依赖进程号终止服务。"""

import hashlib
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rrplot-web"
PROJECT_ID = hashlib.sha256(str(ROOT).casefold().encode()).hexdigest()[:20]
_cached = (None, None)
_cache_lock = threading.Lock()


def safe_console():
    """让 CLI 中文输出在旧控制台（如英文 Windows 的 cp1252）降级而非崩溃。

    无法编码的字符原位替换，不再抛 UnicodeEncodeError；
    中文 Windows（cp936/UTF-8）下的显示不受影响。
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def code_fingerprint():
    global _cached
    with _cache_lock:
        files = sorted(
            [
                p
                for folder in ("rrplot", "server", "web")
                for p in (ROOT / folder).rglob("*")
                if p.is_file()
                and p.suffix in (".py", ".js", ".css", ".html", ".json")
            ]
        )
        entries = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((path, str(path.relative_to(ROOT)),
                            stat.st_mtime_ns, stat.st_size))
        signature = tuple((rel, mtime, size) for _, rel, mtime, size in entries)
        if signature != _cached[0]:
            digest = hashlib.sha256()
            for path, rel, _, _ in entries:
                try:
                    content = path.read_bytes()
                except OSError:
                    continue
                digest.update(rel.encode())
                digest.update(content)
            _cached = (signature, digest.hexdigest()[:12])
        return _cached[1]


def identity():
    return dict(
        app="rrplot",
        pid=os.getpid(),
        projectId=PROJECT_ID,
        instanceId=os.environ.pop("RRPLOT_LAUNCH_ID", None) or secrets.token_hex(16),
        build=code_fingerprint(),
        startedAt=datetime.now(timezone.utc).isoformat(),
    )


def state_path(port):
    return STATE / f"service-{port}.json"


def save_instance(server):
    STATE.mkdir(exist_ok=True)
    path = state_path(server.server_port)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            dict(server.identity, port=server.server_port, token=server.shutdown_token)
        ),
        encoding="utf-8",
    )
    if os.name != "nt":
        os.chmod(temporary, 0o600)
    temporary.replace(path)


def remove_instance(server):
    path = state_path(server.server_port)
    try:
        if (
            json.loads(path.read_text(encoding="utf-8"))["instanceId"]
            == server.identity["instanceId"]
        ):
            path.unlink()
    except (OSError, ValueError, KeyError):
        pass


def wait_until(check, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.1)
    return None
