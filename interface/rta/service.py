"""Exclusive acquisition jobs and application state."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import secrets
import signal
import subprocess
import threading
import time
import uuid

from .common import ROOT, ACTIVE, PHASES, Problem, address, settings, now, read_json
from .instrument import scope_query, read_scope, verify_profile
from .storage import ResultStore
from .commands import build_command
from .models import MODELS, identify, selected_model
from .runtime import FROZEN, results_dir, core_executable, hidden_process, process_environment
from .process import KILL, signal_process, session_options

class App:
    def __init__(self, root=ROOT, results=None, executable=None):
        self.root = Path(root).resolve()
        self.results = Path(results if results is not None else results_dir()).resolve()
        self.results.mkdir(exist_ok=True, parents=True)
        self.executable = Path(executable or core_executable())
        self.instance_id = uuid.uuid4().hex
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.store = ResultStore(self.results)
        self.scope = dict(busy=False, snapshot=None, error="")
        self.connection = dict(connected=False, checking=False)
        self.job = None
        self.process = None
        self.closed = False

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(dict(instance=self.instance_id, connection=self.connection, job=self.job, scope=self.scope, closed=self.closed)))

    def connect(self, data):
        ip, port = address(data)
        try:
            model = selected_model(data.get("model", "auto"))
        except ValueError as error:
            raise Problem(str(error)) from None
        with self.lock:
            if self.closed or self.scope["busy"] or self.connection.get("checking") or (
                    self.job and self.job["state"] in ACTIVE):
                raise Problem("Aguarde ou cancele o ensaio em andamento.", 409)
            self.connection = dict(connected=False, checking=True, ip=ip, port=port)
        try:
            identity = scope_query(ip, port)
            try:
                device = identify(identity, model)
            except ValueError as error:
                raise Problem(str(error)) from None
            connection = dict(connected=True, checking=False, ip=ip, port=port,
                              **device, checked_at=now())
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
        cfg = settings(payload.get("settings", {}), self.connection.get("model"))
        # The demonstration is explicitly advertised as a quick 10k-sample run.
        if mode == "demo":
            cfg["points"] = 10000
        with self.lock:
            if self.closed or self.scope["busy"] or self.connection.get("checking") or (
                    self.job and self.job["state"] in ACTIVE):
                raise Problem("Já existe uma operação em andamento.", 409)
            if mode == "real" and not (
                    self.connection.get("connected") and
                    self.connection.get("ip") == cfg["ip"] and
                    self.connection.get("port") == cfg["port"] and
                    self.connection.get("model") in MODELS and
                    cfg["model"] in {"auto", self.connection["model"]}):
                raise Problem("Conecte e identifique o Rigol neste endereço antes de medir.", 409)
            if mode == "real":
                cfg = settings(cfg | {"model": self.connection["model"]})
            if not self.executable.is_file():
                raise Problem("Componente de medição ausente. Reinstale o Rigol Transient Analyzer." if FROZEN else
                              "O programa de medição não foi compilado. Execute make.", 503)
            run = "ui_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
            self.job = dict(id=run, mode=mode, state="running", phase="preparando",
                            message="Preparando o ensaio", capture=0, total=cfg["captures"],
                            started_at=now(), settings=cfg, logs=[], cancel_requested=False)
            threading.Thread(target=self._work, args=(run, mode, cfg), daemon=True).start()
            return self.snapshot()["job"]

    def _command(self, run, mode, cfg, configuration_only=False):
        return build_command(self.executable, self.results, run, mode, cfg, configuration_only)
    def _work(self, run, mode, cfg):
        process = None
        error = ""
        code = -1
        cancel_file = self.results / (".cancel-" + run)
        try:
            with self.lock:
                cancelled = self.job["cancel_requested"]
            if not cancelled:
                env = process_environment()
                env["RTA_PROGRESS"] = "1"
                if os.name == "nt":
                    env["RTA_CANCEL_FILE"] = str(cancel_file)
                process = subprocess.Popen(self._command(run, mode, cfg), cwd=self.root,
                                           env=env, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True,
                                           encoding="utf-8", errors="replace", bufsize=1,
                                           **hidden_process(), **session_options())
                process.rta_cancel_file = cancel_file
                with self.lock:
                    self.process = process
                    if self.job["cancel_requested"]:
                        self._signal(process, signal.SIGINT)
                        threading.Thread(target=self._cancel_watchdog, args=(process,), daemon=True).start()
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
                self._signal(process, KILL)
                process.wait()
            cancel_file.unlink(missing_ok=True)
            with self.lock:
                cancelled = self.job["cancel_requested"]
            stop_warning = ""
            if cancelled and mode == "real":
                try:
                    if read_scope(cfg["ip"], cfg["port"], "stop", cfg["model"], timeout=2)["state"] != "STOP":
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
                if mode == "real":
                    self.scope["snapshot"] = None
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
        signal_process(process, number)

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
        for number in (signal.SIGTERM, KILL):
            time.sleep(3)
            if process.poll() is not None:
                return
            self._signal(process, number)


    def scope_action(self, payload):
        action = payload.get("action")
        if action not in {"read", "apply", "run", "stop"}:
            raise Problem("Ação do Rigol desconhecida.")
        cfg = settings(payload.get("settings", {}), self.connection.get("model"))
        with self.lock:
            if self.closed or self.scope["busy"] or self.connection.get("checking") or (
                    self.job and self.job["state"] in ACTIVE):
                raise Problem("Aguarde a operação em andamento.", 409)
            if not (self.connection.get("connected") and
                    (self.connection["ip"], self.connection["port"]) == (cfg["ip"], cfg["port"]) and
                    self.connection.get("model") in MODELS and
                    cfg["model"] in {"auto", self.connection["model"]}):
                raise Problem("Conecte o Rigol neste endereço antes de configurar.", 409)
            cfg = settings(cfg | {"model": self.connection["model"]})
            self.scope.update(busy=True, error="", snapshot=None)
        try:
            if action == "apply":
                # Reuse the C profile and its readback checks; never start a capture here.
                command = self._command(None, "real", cfg, configuration_only=True)
                result = subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=25, **hidden_process())
                if result.returncode:
                    raise Problem((result.stderr or result.stdout).strip()[-1000:] or
                                  "O Rigol não confirmou a configuração.", 502)
            state = read_scope(cfg["ip"], cfg["port"], action if action in {"run", "stop"} else "read", cfg["model"])
            if action == "apply":
                verify_profile(state, cfg)
                state = read_scope(cfg["ip"], cfg["port"], "run", cfg["model"])
            with self.lock:
                self.scope["snapshot"] = state
            return state
        except subprocess.TimeoutExpired:
            with self.lock:
                self.scope["error"] = "O Rigol não confirmou o perfil no prazo. Leia os ajustes antes de tentar novamente."
            raise Problem(self.scope["error"], 504) from None
        except (OSError, Problem) as error:
            with self.lock:
                self.scope["error"] = str(error)
                if isinstance(error, OSError):
                    self.connection["connected"] = False
            if isinstance(error, Problem):
                raise
            raise Problem("Não foi possível comunicar com o Rigol. Verifique o cabo e tente conectar novamente.", 502) from None
        finally:
            with self.lock:
                self.scope["busy"] = False

    def run_path(self, run):
        return self.store.run_path(run)

    def detail(self, run):
        return self.store.detail(run)

    def history(self):
        return self.store.history()

    def waveform(self, *args, **kwargs):
        return self.store.waveform(*args, **kwargs)

    def download(self, *args, **kwargs):
        return self.store.download(*args, **kwargs)
