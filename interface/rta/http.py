"""Loopback-only HTTP API and local static assets."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import json
import mimetypes
import secrets
import shutil
import threading

from .common import DEFAULTS, ACTIVE, Problem
from .timebase import TIMEBASE
from .models import MODELS
from .runtime import VERSION, FROZEN

class Handler(BaseHTTPRequestHandler):
    server_version = "RigolTransientAnalyzer/1"
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass

    def guard(self, write=False):
        host = urlsplit("http://" + self.headers.get("Host", ""))
        if host.hostname not in ("localhost", "127.0.0.1") or host.port != self.server.server_port:
            raise Problem("Acesso disponível somente pelo endereço local do aplicativo.", 403)
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host"):
            raise Problem("Origem não autorizada.", 403)
        if write and not secrets.compare_digest(self.headers.get("X-RTA-Token", ""), self.server.app.token):
            raise Problem("Reabra a interface para atualizar a sessão.", 403)

    def respond_headers(self, code, mime, length, attachment=None):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if attachment:
            self.send_header("Content-Disposition", 'attachment; filename="' + attachment + '"')
        self.end_headers()

    def json(self, data, code=200):
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.respond_headers(code, "application/json; charset=utf-8", len(encoded))
        self.wfile.write(encoded)

    def do_GET(self):
        try:
            self.guard()
            url = urlsplit(self.path)
            query = {key: values[-1] for key, values in parse_qs(url.query).items()}
            app = self.server.app
            if url.path == "/api/bootstrap":
                self.json(dict(app="Rigol Transient Analyzer", token=app.token,
                               version=VERSION, packaged=FROZEN, defaults=DEFAULTS, models=list(MODELS.values()), timebase=TIMEBASE, **app.snapshot()))
            elif url.path == "/api/status":
                self.json(app.snapshot())
            elif url.path == "/api/profiles":
                self.json(app.profiles.list())
            elif url.path == "/api/backups":
                self.json(app.backups.list())
            elif url.path == "/api/history":
                self.json(app.history())
            elif url.path == "/api/run":
                self.json(app.detail(query.get("id", "")))
            elif url.path == "/api/waveform":
                self.json(app.waveform(query.get("run", ""), query.get("capture", ""),
                                       query.get("start"), query.get("end"), query.get("limit", 2400)))
            elif url.path == "/download":
                file = app.download(query.get("run", ""), query.get("capture", ""), query.get("file", ""))
                self.respond_headers(200, mimetypes.guess_type(file.name)[0] or "application/octet-stream",
                             file.stat().st_size, file.name)
                with file.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile, 65536)
            elif url.path in ("/", "/app.js", "/style.css", "/modules/core.js",
                              "/modules/chart.js", "/modules/results.js", "/modules/rigol.js", "/modules/timebase.js", "/modules/models.js",
                              "/assets/circuit.svg", "/assets/circuit-en.svg", "/rigol.css", "/modules/workbench.js", "/modules/i18n.js", "/workbench.css"):
                file = app.root / "interface/static" / ("index.html" if url.path == "/" else url.path[1:])
                data = file.read_bytes()
                mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}[file.suffix]
                self.respond_headers(200, mime + "; charset=utf-8", len(data))
                self.wfile.write(data)
            else:
                raise Problem("Página não encontrada.", 404)
        except Problem as error:
            self.json(dict(error=str(error)), error.status)
        except (ValueError, KeyError, OSError) as error:
            if not isinstance(error, (BrokenPipeError, ConnectionResetError)):
                self.json(dict(error="Não foi possível ler este resultado."), 400)

    def do_POST(self):
        try:
            self.guard(write=True)
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 16384 or self.headers.get_content_type() != "application/json":
                raise Problem("Pedido inválido.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise Problem("Pedido inválido.")
            app = self.server.app
            if self.path == "/api/connect":
                self.json(app.connect(data))
            elif self.path == "/api/run":
                self.json(app.start(data), 202)
            elif self.path == "/api/profile":
                self.json(app.save_profile(data))
            elif self.path == "/api/profile/delete":
                self.json(app.profiles.delete(data.get("id")))
            elif self.path == "/api/diagnose":
                self.json(app.diagnose(data))
            elif self.path == "/api/backup":
                self.json(app.backup(data),201)
            elif self.path == "/api/restore":
                self.json(app.restore(data))
            elif self.path == "/api/compare":
                self.json(app.compare(data))
            elif self.path == "/api/report":
                self.json(app.report(data),201)
            elif self.path == "/api/scope":
                self.json(app.scope_action(data))
            elif self.path == "/api/cancel":
                self.json(app.cancel(), 202)
            elif self.path == "/api/shutdown":
                with app.lock:
                    if app.scope["busy"] or app.connection.get("checking") or (app.job and app.job["state"] in ACTIVE):
                        raise Problem("Cancele ou conclua o ensaio antes de encerrar.", 409)
                    app.closed = True
                self.json(dict(closed=True))
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                raise Problem("Operação desconhecida.", 404)
        except Problem as error:
            self.json(dict(error=str(error)), error.status)
        except (ValueError, TypeError, OverflowError, KeyError, OSError):
            self.json(dict(error="Pedido inválido."), 400)


def server(app, port=8765):
    instance = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    instance.app = app
    instance.daemon_threads = True
    return instance
