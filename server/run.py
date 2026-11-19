"""本机 rrplot 编辑器：python server/run.py [--port 8765]。"""
import argparse
import json
import mimetypes
import secrets
import socket
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from rrplot import __version__  # noqa: E402
from rrplot.registry import catalog  # noqa: E402
from rrplot.scene import TEMPLATES, load_template  # noqa: E402
from rrplot.scene_renderer import (  # noqa: E402
    export_scene,
    preview_glyph,
    resolve_for_editor,
)
from server.service import (  # noqa: E402
    code_fingerprint,
    identity,
    remove_instance,
    save_instance,
)

WEB = ROOT / "web"
MIMES = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}
RENDER_LOCK = threading.Lock()


class LocalHTTPServer(ThreadingHTTPServer):
    # Windows 的 SO_REUSEADDR 会允许多个服务抢占同一端口。
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    timeout = 10

    def send_data(self, data, content_type, status=200, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition",
                             f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, obj, status=200):
        self.send_data(json.dumps(obj, ensure_ascii=False, allow_nan=False).encode(),
                       "application/json; charset=utf-8", status)

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path == "/api/health":
                current = code_fingerprint()
                return self.json_response(dict(
                    self.server.identity, ok=True, version=__version__,
                    codeChanged=current != self.server.identity["build"],
                    diskBuild=current))
            if path == "/api/catalog":
                return self.json_response(catalog())
            if path.startswith("/api/glyph/"):
                query = parse_qs(urlsplit(self.path).query)
                params = json.loads(query.get("params", ["{}"])[0])
                if not isinstance(params, dict):
                    raise ValueError("params 必须是对象")
                with RENDER_LOCK:
                    image = preview_glyph(path.rsplit("/", 1)[-1], params)
                return self.send_data(image, MIMES["svg"])
            if path == "/api/templates":
                return self.json_response([dict(id=k, title=v)
                                           for k, v in TEMPLATES.items()])
            if path.startswith("/api/templates/"):
                return self.json_response(load_template(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/"):
                return self.json_response(dict(error="接口不存在"), 404)
            target = (WEB / (path.lstrip("/") or "index.html")).resolve()
            if not target.is_relative_to(WEB) or not target.is_file():
                return self.json_response(dict(error="文件不存在"), 404)
            mime = mimetypes.guess_type(target)[0] or "application/octet-stream"
            if target.suffix in (".js", ".html", ".css"):
                mime = {".js": "text/javascript", ".html": "text/html",
                        ".css": "text/css"}[target.suffix] + "; charset=utf-8"
            self.send_data(target.read_bytes(), mime)
        except (ValueError, OSError) as exc:
            self.json_response(dict(error=str(exc)), 400)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 5000000:
                raise ValueError("JSON 请求为空或超过 5 MB")
            raw = self.rfile.read(length)
            if self.headers.get_content_type() != "application/json":
                raise ValueError("请求必须使用 application/json")
            body = json.loads(raw)
            if path == "/api/shutdown":
                token = body.get("token") if isinstance(body, dict) else None
                if (self.headers.get("Origin") is not None
                        or not isinstance(token, str)
                        or not secrets.compare_digest(
                            token, self.server.shutdown_token)):
                    return self.json_response(dict(error="服务实例身份校验失败"), 403)
                self.json_response(dict(ok=True))
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if not isinstance(body, dict) or "document" not in body:
                raise ValueError("请求缺少 document")
            if path == "/api/resolve":
                with RENDER_LOCK:
                    result = resolve_for_editor(
                        body["document"],
                        shared_glyphs=body.get("sharedGlyphs") is True)
                return self.json_response(result)
            if path == "/api/preview":
                with RENDER_LOCK:
                    output = export_scene(body["document"])
                return self.send_data(output, MIMES["svg"])
            if path.startswith("/api/export/"):
                fmt = path.rsplit("/", 1)[-1]
                if fmt not in MIMES:
                    raise ValueError("不支持的导出格式")
                with RENDER_LOCK:
                    output = export_scene(body["document"], fmt, body.get("dpi", 140))
                return self.send_data(output, MIMES[fmt], filename="rrplot." + fmt)
            self.json_response(dict(error="接口不存在"), 404)
        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
            self.json_response(dict(error=str(exc)), 400)
        except Exception:
            traceback.print_exc()
            self.json_response(dict(error="图纸处理失败，请查看本机服务日志"), 500)


def make_server(port=8765):
    server = LocalHTTPServer(("127.0.0.1", port), Handler)
    server.identity = identity()
    server.shutdown_token = secrets.token_hex(32)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        server = make_server(args.port)
    except OSError as exc:
        parser.exit(1, f"无法启动本机服务（端口 {args.port}）：{exc}\n"
                    "如服务已启动，请直接打开网页；也可用 --port 指定其他端口。\n")
    with server:
        save_instance(server)
        print(f"rrplot Web: http://127.0.0.1:{server.server_port}", flush=True)
        print("按 Ctrl+C 停止。", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            remove_instance(server)


if __name__ == "__main__":
    main()
