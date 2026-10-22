import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

MAX_BODY = 3 * 1024 * 1024


def serve(root, get_api, post_api, port):
    root = Path(root).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            expected = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            if self.headers.get("Host") not in expected:
                self.respond(403, {"error": "Недопустимый адрес сервера."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{host}" for host in expected}:
                self.respond(403, {"error": "Запрос с другого сайта запрещён."})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            route = urlsplit(self.path)
            try:
                if route.path.startswith("/api/"):
                    result = get_api(route.path, route.query)
                    if result is None:
                        self.respond(404, {"error": "Не найдено."})
                    else:
                        self.respond(200, result)
                    return
                name = unquote(route.path).lstrip("/") or "index.html"
                target = (root / name).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    self.respond(404, {"error": "Не найдено."})
                    return
                kind = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if kind.startswith("text/") or kind in (
                    "application/javascript",
                    "application/json",
                ):
                    kind += "; charset=utf-8"
                self.respond(200, target.read_bytes(), kind)
            except ValueError as exc:
                self.respond(400, {"error": str(exc)})
            except Exception as exc:
                print(f"GET failed: {type(exc).__name__}", file=sys.stderr)
                self.respond(500, {"error": "Ошибка сервера. Повторите попытку."})

        def do_POST(self):
            if not self.allowed():
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 1 or size > MAX_BODY:
                    self.respond(413, {"error": "Допустимый размер запроса: до 3 МБ."})
                    return
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    self.respond(415, {"error": "Ожидается JSON."})
                    return
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Ожидается объект с полями.")
                result = post_api(urlsplit(self.path).path, payload)
                self.respond(404 if result is None else 200, result or {"error": "Не найдено."})
            except (ValueError, UnicodeError) as exc:
                self.respond(
                    400,
                    {
                        "error": (
                            str(exc)
                            if not isinstance(exc, json.JSONDecodeError)
                            else "Некорректный JSON."
                        )
                    },
                )
            except Exception as exc:
                print(f"POST failed: {type(exc).__name__}", file=sys.stderr)
                self.respond(500, {"error": "Не удалось сохранить данные. Повторите попытку."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Local: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
