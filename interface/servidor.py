#!/usr/bin/env python3
"""Local browser interface for Rigol Transient Analyzer."""
from array import array
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import argparse
import bisect
import csv
import fcntl
import ipaddress
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = dict(ip="169.254.112.67", port=5555, probe_v=10, probe_i=1,
                resistor=1, captures=1, points=1000000, nominal=5,
                scale_v=.5, scale_i=.1, time_div=.0002, bandwidth="20M",
                low_a=.05, high_a=.15, window_us=50, guard_us=20,
                horizon_us=300, tolerance_v=.05, hold_us=20,
                timeout=5, plots=True)
ACTIVE = {"running", "cancelling"}
PHASES = {
    "conectando": "Identificando o osciloscópio",
    "configurando": "Configurando os canais",
    "aguardando_disparo": "Aguardando o disparo",
    "transferindo": "Recebendo os dois canais",
    "simulando": "Gerando sinal de demonstração",
    "analisando": "Analisando as transições",
    "exportando": "Salvando os resultados",
    "graficos": "Gerando imagens para exportação",
    "finalizando": "Finalizando o ensaio",
}


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def scope_query(ip, port, command="*IDN?", timeout=3):
    with socket.create_connection((ip, port), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall((command + "\n").encode("ascii"))
        with connection.makefile("rb") as stream:
            reply = stream.readline(1025)
    if not reply.endswith(b"\n") or len(reply) > 1024:
        raise Problem("O instrumento retornou uma resposta incompleta.")
    return reply.decode("ascii", errors="replace").strip()


def address(data):
    try:
        ip = str(ipaddress.ip_address(str(data["ip"]).strip()))
        port = int(data["port"])
        if isinstance(data["port"], bool) or str(port) != str(data["port"]):
            raise ValueError()
        if not 1 <= port <= 65535:
            raise ValueError()
        return ip, port
    except (KeyError, ValueError, TypeError):
        raise Problem("Informe um endereço IP válido e uma porta de 1 a 65535.") from None


def settings(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise Problem("Configuração desconhecida.")
    cfg = DEFAULTS | data
    cfg["ip"], cfg["port"] = address(cfg)
    integers = {"captures": (1, 100), "points": (1000, 1000000),
                "probe_v": (1, 10), "probe_i": (1, 10)}
    for key, bounds in integers.items():
        value = cfg[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise Problem("Valor inteiro inválido: " + key)
        cfg[key] = int(value)
        if not bounds[0] <= value <= bounds[1]:
            raise Problem("Valor fora da faixa: " + key)
    if cfg["points"] not in (1000, 10000, 100000, 1000000):
        raise Problem("Selecione uma profundidade de memória disponível.")
    if cfg["probe_v"] not in (1, 10) or cfg["probe_i"] not in (1, 10):
        raise Problem("As pontas devem estar em 1× ou 10×.")
    numeric = set(DEFAULTS) - set(integers) - {"ip", "port", "bandwidth", "plots"}
    for key in numeric:
        value = cfg[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise Problem("Valor numérico inválido: " + key)
        if (key not in {"low_a", "high_a", "guard_us"} and value <= 0) or (
                key == "guard_us" and value < 0):
            raise Problem("Use um valor positivo: " + key)
    if cfg["low_a"] >= cfg["high_a"]:
        raise Problem("O limiar baixo deve ser menor que o limiar alto.")
    if cfg["horizon_us"] < cfg["window_us"] + cfg["guard_us"]:
        raise Problem("O horizonte deve comportar a janela e a guarda.")
    if cfg["hold_us"] > cfg["horizon_us"]:
        raise Problem("A permanência não pode superar o horizonte.")
    if cfg["bandwidth"] not in ("20M", "OFF") or not isinstance(cfg["plots"], bool):
        raise Problem("Configuração de banda ou gráficos inválida.")
    return cfg


class App:
    def __init__(self, root=ROOT, results=None, executable=None):
        self.root = Path(root).resolve()
        self.results = Path(results or self.root / "resultados").resolve()
        self.results.mkdir(exist_ok=True, parents=True)
        self.executable = Path(executable or self.root / "build/carac_transientes")
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.cache_lock = threading.Lock()
        self.cache = OrderedDict()
        self.connection = dict(connected=False, checking=False)
        self.job = None
        self.process = None
        self.closed = False

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(dict(connection=self.connection, job=self.job)))

    def connect(self, data):
        ip, port = address(data)
        with self.lock:
            if self.closed or self.connection.get("checking") or (
                    self.job and self.job["state"] in ACTIVE):
                raise Problem("Aguarde ou cancele o ensaio em andamento.", 409)
            self.connection = dict(connected=False, checking=True, ip=ip, port=port)
        try:
            identity = scope_query(ip, port)
            fields = [part.strip() for part in identity.split(",")]
            if len(fields) < 4 or "RIGOL" not in fields[0].upper() or fields[1] != "DHO802":
                raise Problem("Este perfil requer um Rigol DHO802. Resposta: " + identity)
            connection = dict(connected=True, checking=False, ip=ip, port=port,
                              identity=identity, model=fields[1], serial=fields[2],
                              firmware=fields[3], checked_at=now())
        except (OSError, Problem) as error:
            with self.lock:
                self.connection = dict(connected=False, checking=False, ip=ip,
                                       port=port, error=str(error))
            if isinstance(error, Problem):
                raise
            raise Problem("Não foi possível acessar o Rigol. Confira alimentação, cabo e IP.", 502) from None
        with self.lock:
            self.connection = connection
        return connection

    def start(self, payload):
        mode = payload.get("mode")
        if mode not in ("real", "demo"):
            raise Problem("Selecione medição real ou demonstração.")
        cfg = settings(payload.get("settings", {}))
        # The demonstration is explicitly advertised as a quick 10k-sample run.
        if mode == "demo":
            cfg["points"] = 10000
        with self.lock:
            if self.closed or self.connection.get("checking") or (
                    self.job and self.job["state"] in ACTIVE):
                raise Problem("Já existe uma operação em andamento.", 409)
            if mode == "real" and not (
                    self.connection.get("connected") and
                    self.connection.get("ip") == cfg["ip"] and
                    self.connection.get("port") == cfg["port"]):
                raise Problem("Conecte e identifique o Rigol neste endereço antes de medir.", 409)
            if not self.executable.is_file():
                raise Problem("O programa de medição não foi compilado. Execute make.", 503)
            run = "ui_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
            self.job = dict(id=run, mode=mode, state="running", phase="preparando",
                            message="Preparando o ensaio", capture=0, total=cfg["captures"],
                            started_at=now(), settings=cfg, logs=[], cancel_requested=False)
            threading.Thread(target=self._work, args=(run, mode, cfg), daemon=True).start()
            return self.snapshot()["job"]

    def _command(self, run, mode, cfg):
        command = [str(self.executable), "--saida", str(self.results / run)]
        options = dict(resistor="resistor", capturas="captures", pontos="points",
                       porta="port", **{"sonda-v": "probe_v", "sonda-i": "probe_i",
                       "nominal-v": "nominal", "escala-v": "scale_v", "escala-shunt": "scale_i",
                       "tempo-div": "time_div", "banda": "bandwidth", "baixo-a": "low_a",
                       "alto-a": "high_a", "janela-us": "window_us", "guarda-us": "guard_us",
                       "horizonte-us": "horizon_us", "tolerancia-v": "tolerance_v",
                       "permanencia-us": "hold_us", "timeout": "timeout"})
        for flag, key in options.items():
            command.extend(["--" + flag, str(cfg[key])])
        if cfg["plots"]:
            command.append("--graficos")
        command.extend(["--simular"] if mode == "demo" else [cfg["ip"]])
        return command

    def _work(self, run, mode, cfg):
        process = None
        error = ""
        code = -1
        try:
            with self.lock:
                cancelled = self.job["cancel_requested"]
            if not cancelled:
                env = os.environ.copy()
                env["RTA_PROGRESS"] = "1"
                process = subprocess.Popen(self._command(run, mode, cfg), cwd=self.root,
                                           env=env, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True,
                                           encoding="utf-8", errors="replace", bufsize=1,
                                           start_new_session=True)
                with self.lock:
                    self.process = process
                    if self.job["cancel_requested"]:
                        self._signal(process, signal.SIGINT)
                for line in process.stdout:
                    line = line.rstrip()
                    progress = re.fullmatch(r"@RTA ([a-z_]+) (\d+) (\d+)", line)
                    with self.lock:
                        if progress and not self.job["cancel_requested"]:
                            phase, capture, total = progress.groups()
                            self.job.update(phase=phase, message=PHASES.get(phase, phase),
                                            capture=int(capture), total=int(total))
                        elif line and not progress:
                            self.job["logs"] = (self.job["logs"] + [line])[-80:]
                            if line.startswith("Erro:"):
                                error = line[5:].strip()
                process.stdout.close()
                code = process.wait()
        except (OSError, ValueError) as exc:
            error = str(exc)
        finally:
            if process and process.poll() is None:
                self._signal(process, signal.SIGKILL)
                process.wait()
            with self.lock:
                cancelled = self.job["cancel_requested"]
            stop_warning = ""
            if cancelled and mode == "real":
                try:
                    if scope_query(cfg["ip"], cfg["port"], ":STOP;:TRIG:STAT?", 2) != "STOP":
                        stop_warning = " Não foi possível confirmar STOP no Rigol."
                except (OSError, Problem):
                    stop_warning = " Não foi possível confirmar STOP no Rigol."
            complete = False
            try:
                complete = read_json(self.results / run / "execucao.json").get("concluido") is True
            except (OSError, ValueError, AttributeError):
                pass
            with self.lock:
                self.process = None
                if cancelled:
                    self.job.update(state="cancelled", message="Ensaio cancelado." + stop_warning)
                elif code in (0, 2) and complete:
                    message = ("Ensaio concluído" if code == 0 else
                               "Dados salvos; nenhuma transição tem janela completa.")
                    self.job.update(state="done" if code == 0 else "attention", message=message)
                else:
                    self.job.update(state="error", message=error or "O ensaio não foi concluído. Consulte os detalhes.")
                    if mode == "real":
                        self.connection["connected"] = False
                self.job.update(finished_at=now(), exit_code=code)

    @staticmethod
    def _signal(process, number):
        try:
            os.killpg(process.pid, number)
        except ProcessLookupError:
            pass

    def cancel(self):
        with self.lock:
            if not self.job or self.job["state"] not in ACTIVE:
                raise Problem("Não há ensaio em andamento.", 409)
            self.job.update(cancel_requested=True, state="cancelling",
                            message="Cancelando e aguardando o encerramento")
            process = self.process
            if process:
                self._signal(process, signal.SIGINT)
                threading.Thread(target=self._cancel_watchdog, args=(process,), daemon=True).start()
            return self.snapshot()["job"]

    def _cancel_watchdog(self, process):
        for number in (signal.SIGTERM, signal.SIGKILL):
            time.sleep(3)
            if process.poll() is not None:
                return
            self._signal(process, number)

    def run_path(self, run):
        if not isinstance(run, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run):
            raise Problem("Identificador de ensaio inválido.")
        path = (self.results / run).resolve()
        if path.parent != self.results or not path.is_dir():
            raise Problem("Ensaio não encontrado.", 404)
        return path

    @staticmethod
    def inside(parent, child):
        path = (parent / child).resolve()
        if not path.is_relative_to(parent.resolve()) or not path.is_file():
            raise Problem("Arquivo não encontrado.", 404)
        return path

    def detail(self, run):
        path = self.run_path(run)
        captures = []
        for folder in sorted(path.glob("captura_*")):
            if not folder.is_dir() or not re.fullmatch(r"captura_\d+", folder.name):
                continue
            try:
                meta = read_json(self.inside(path, folder.name + "/metadados.json"))
                with self.inside(path, folder.name + "/eventos.csv").open(newline="") as file:
                    events = []
                    for row in csv.DictReader(file):
                        event = {key: value if key in ("direcao", "status") else
                                 (float(value) if value else None) for key, value in row.items()}
                        if any(isinstance(value, float) and not math.isfinite(value)
                               for value in event.values()):
                            raise ValueError("Non-finite event")
                        events.append(event)
                pngs = [file.name for file in sorted((folder / "graficos").glob("*.png"))
                        if file.is_file() and file.resolve().is_relative_to(path)]
                captures.append(dict(id=folder.name, metadata=meta, events=events, images=pngs))
            except (OSError, ValueError, KeyError, Problem):
                continue
        if not captures:
            raise Problem("Este ensaio ainda não possui capturas completas.", 404)
        try:
            execution = read_json(self.inside(path, "execucao.json"))
        except (OSError, ValueError, Problem):
            execution = {}
        return dict(id=run, captures=captures, execution=execution)

    def history(self):
        history = []
        for path in self.results.iterdir():
            if not path.is_dir():
                continue
            try:
                detail = self.detail(path.name)
                captures = detail["captures"]
                first = captures[0]["metadata"]
                history.append(dict(id=path.name, origin=first["origem"],
                                    date=first["instante_utc"], captures=len(captures),
                                    valid=sum(c["metadata"]["eventos_validos"] for c in captures),
                                    complete=detail["execution"].get("concluido") is True))
            except (OSError, ValueError, KeyError, Problem):
                continue
        return sorted(history, key=lambda row: row["date"], reverse=True)

    def waveform(self, run, capture, start=None, end=None, limit=2400):
        if not re.fullmatch(r"captura_\d+", capture):
            raise Problem("Captura inválida.")
        path = self.inside(self.run_path(run), capture + "/amostras.csv")
        key = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        with self.cache_lock:
            if key in self.cache:
                columns = self.cache.pop(key)
                self.cache[key] = columns
            else:
                columns = [array("d"), array("d"), array("d")]
                with path.open(newline="") as file:
                    reader = csv.reader(file)
                    if next(reader, None) != ["tempo_s", "tensao_v", "corrente_a"]:
                        raise Problem("Formato de amostras inválido.")
                    previous = -math.inf
                    for row in reader:
                        if len(row) != 3:
                            raise Problem("Amostra inválida.")
                        values = [float(value) for value in row]
                        if not all(math.isfinite(value) for value in values) or values[0] <= previous:
                            raise Problem("As amostras devem ser finitas e ordenadas no tempo.")
                        previous = values[0]
                        for column, value in zip(columns, values):
                            column.append(value)
                        if len(columns[0]) > 1000000:
                            raise Problem("O registro excede um milhão de amostras.")
                if len(columns[0]) < 2:
                    raise Problem("O registro possui poucas amostras.")
                self.cache[key] = columns
                while len(self.cache) > 2:
                    self.cache.popitem(last=False)
        t, v, current = columns
        start = t[0] if start is None else float(start)
        end = t[-1] if end is None else float(end)
        limit = int(limit)
        if not (math.isfinite(start) and math.isfinite(end) and start < end and 100 <= limit <= 5000):
            raise Problem("Janela de visualização inválida.")
        first = bisect.bisect_left(t, start)
        last = bisect.bisect_right(t, end)
        if last - first < 2:
            raise Problem("A janela precisa conter pelo menos duas amostras.")
        if last - first <= limit:
            indices = range(first, last)
        else:
            buckets = max(1, (limit - 2) // 4)
            indices = {first, last - 1}
            for bucket in range(buckets):
                a = first + (last - first) * bucket // buckets
                b = first + (last - first) * (bucket + 1) // buckets
                for column in (v, current):
                    indices.add(min(range(a, b), key=column.__getitem__))
                    indices.add(max(range(a, b), key=column.__getitem__))
            indices = sorted(indices)
        return dict(points=[[t[k], v[k], current[k]] for k in indices],
                    total=len(t), selected=last-first, start=t[first], end=t[last-1],
                    record_start=t[0], record_end=t[-1])

    def download(self, run, capture, name):
        root = self.run_path(run)
        if capture:
            if not re.fullmatch(r"captura_\d+", capture):
                raise Problem("Captura inválida.")
            allowed = {"amostras.csv", "eventos.csv", "metadados.json", "resumo.txt"}
            if name not in allowed and not re.fullmatch(
                    r"graficos/(?:visao_geral|evento_\d+_(?:subida|descida))\.png", name):
                raise Problem("Exportação desconhecida.", 404)
            return self.inside(root, capture + "/" + name)
        if name not in {"execucao.json", "estatisticas.csv"}:
            raise Problem("Exportação desconhecida.", 404)
        return self.inside(root, name)


class Handler(BaseHTTPRequestHandler):
    server_version = "RigolTransientAnalyzer/1"
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
                               defaults=DEFAULTS, **app.snapshot()))
            elif url.path == "/api/status":
                self.json(app.snapshot())
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
            elif url.path in ("/", "/app.js", "/style.css"):
                file = app.root / "interface/static" / ("index.html" if url.path == "/" else url.path[1:])
                data = file.read_bytes()
                mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[file.suffix]
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
            elif self.path == "/api/cancel":
                self.json(app.cancel(), 202)
            elif self.path == "/api/shutdown":
                with app.lock:
                    if app.connection.get("checking") or (app.job and app.job["state"] in ACTIVE):
                        raise Problem("Cancele ou conclua o ensaio antes de encerrar.", 409)
                    app.closed = True
                self.json(dict(closed=True))
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                raise Problem("Operação desconhecida.", 404)
        except Problem as error:
            self.json(dict(error=str(error)), error.status)
        except (ValueError, KeyError, OSError):
            self.json(dict(error="Pedido inválido."), 400)


def server(app, port=8765):
    instance = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    instance.app = app
    instance.daemon_threads = True
    return instance


def open_browser(url):
    if os.environ.get("WSL_DISTRO_NAME") and shutil.which("powershell.exe"):
        subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", "Start-Process", url],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Use uma porta de 1 a 65535.")
    (ROOT / "build").mkdir(exist_ok=True)
    with (ROOT / "build/interface.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            try:
                url = json.load(lock)["url"]
            except (ValueError, KeyError):
                raise SystemExit("A interface já está iniciando. Aguarde alguns segundos.") from None
            print("Interface já aberta: " + url)
            if not args.no_browser:
                open_browser(url)
            return
        app = App()
        try:
            http = server(app, args.port)
        except OSError:
            raise SystemExit("Porta ocupada. Use --port com outra porta local.") from None
        url = "http://localhost:" + str(http.server_port)
        lock.seek(0); lock.truncate()
        json.dump(dict(url=url, pid=os.getpid()), lock); lock.flush()
        print("Rigol Transient Analyzer: " + url, flush=True)
        if not args.no_browser:
            threading.Timer(.4, open_browser, args=(url,)).start()
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            if app.job and app.job["state"] in ACTIVE:
                app.cancel()
                process = app.process
                if process:
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        app._signal(process, signal.SIGKILL)
        finally:
            http.server_close()


if __name__ == "__main__":
    main()
