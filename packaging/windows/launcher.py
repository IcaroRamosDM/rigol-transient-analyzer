"""Native Windows entry point, diagnostics, plotting, and installer integration."""
from pathlib import Path
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from interface.rta.runtime import (ROOT, VERSION, FROZEN, state_dir, results_dir,
                                   core_executable, hidden_process, process_environment)


def message(text):
    ctypes.windll.user32.MessageBoxW(None, text, "Rigol Transient Analyzer", 0x10)


def self_test(destination):
    """Exercise the shipped C binary and plotting runtime, including Unicode paths."""
    with tempfile.TemporaryDirectory(prefix="RTA teste ação ") as folder:
        base = Path(folder)
        env = process_environment()
        env["RTA_STATE_DIR"] = str(base / "estado")
        env["MPLCONFIGDIR"] = str(base / "cache")
        command = [str(core_executable()), "--simular", "--pontos", "1000", "--graficos",
                   "--saida", str(base / "resultados ação/ensaio_001")]
        run = subprocess.run(command, env=env, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=90, **hidden_process())
        if run.returncode:
            raise RuntimeError("Core self-test failed: " + (run.stderr or run.stdout)[-1200:])
        capture = base / "resultados ação/ensaio_001/captura_001"
        meta = json.loads((capture / "metadados.json").read_text(encoding="utf-8"))
        pngs = list((capture / "graficos").glob("*.png"))
        models = subprocess.run([str(core_executable()), "--listar-modelos"], check=True,
                                 capture_output=True, text=True, timeout=5, **hidden_process()).stdout.splitlines()
        if meta["origem"] != "SIMULACAO" or meta["pontos"] != 1000 or not pngs or len(models) != 8:
            raise RuntimeError("The bundled resources did not pass validation.")
        from interface.rta.storage import ResultStore
        from interface.rta.reports import report
        store=ResultStore(base/"resultados ação")
        pdf=report(store,dict(run=capture.parent.name,capture="captura_001",language="en",notes="Unicode check: ação"))
        file=store.download(capture.parent.name,"","reports/"+pdf["file"])
        if not file.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError("Bundled PDF generator failed.")
        signal_run=base/"resultados ação/sinais_001"
        signal_command=[str(core_executable()),"--tipo","sinais","--canal","1:10:1:0:DC:20M",
                        "--canal","2:1:1:0:DC:20M","--simular","--pontos","1000","--graficos","--saida",str(signal_run)]
        result=subprocess.run(signal_command,env=env,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=90,**hidden_process())
        if result.returncode:raise RuntimeError("Signal core self-test failed: "+(result.stderr or result.stdout)[-1200:])
        signal_meta=store.detail(signal_run.name)["captures"][0]["metadata"]
        signal_pdf=report(store,dict(run=signal_run.name,capture="captura_001",language="en",notes="Signals runtime check"))
        if signal_meta["tipo_medicao"]!="sinais" or len(signal_meta["canais"])!=2 or not (signal_run/"captura_001/graficos/visao_geral.png").is_file():
            raise RuntimeError("Signals bundle validation failed.")
        if not store.download(signal_run.name,"","reports/"+signal_pdf["file"]).read_bytes().startswith(b"%PDF-"):
            raise RuntimeError("Signals PDF validation failed.")
        Path(destination).write_text(json.dumps(dict(pdf=True,signals=True,signal_channels=2,version=VERSION, platform=sys.platform,
            packaged=FROZEN, core="windows-x64", samples=meta["pontos"], pngs=len(pngs),
            models=models, unicode_paths=True), indent=2) + "\n", encoding="utf-8")
    return 0


def main():
    args = sys.argv[1:]
    quiet = "--quiet" in args
    try:
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        logs = directory / "logs"; logs.mkdir(exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(directory / "matplotlib"))
        if FROZEN:
            stream = (logs / "application.log").open("a", encoding="utf-8", buffering=1)
            sys.stdout = stream; sys.stderr = stream
    except Exception as error:
        if not quiet:
            message("Não foi possível preparar os dados do aplicativo.\n\nDetalhe: " + str(error))
        return 1
    if quiet:
        sys.argv.remove("--quiet")
        args.remove("--quiet")
    if FROZEN:
        print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
              f"v{VERSION} PID={os.getpid()} mode={args[0] if args else 'open'}", flush=True)
    try:
        if args[:1] == ["--render-plots"] and len(args) == 2:
            from ferramentas.graficos import main as render
            sys.argv = [sys.argv[0], args[1]]
            render()
            return 0
        if args[:1] == ["--self-test"] and len(args) == 2:
            return self_test(args[1])
        if "--shutdown" in args:
            from interface.rta.instance import stop_running
            status = stop_running()
            if status and not quiet:
                message("Conclua ou cancele o ensaio na interface e tente encerrar novamente.")
            return status
        if args == ["--open-results"]:
            folder = results_dir(); folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
            return 0
        from interface.servidor import main as serve
        serve()
        return 0
    except (Exception, SystemExit) as error:
        if isinstance(error, SystemExit) and error.code in (None, 0):
            return 0
        traceback.print_exc()
        sys.stderr.flush()
        if not quiet and not any(flag in args for flag in ("--render-plots", "--self-test")):
            message("Não foi possível iniciar o aplicativo.\n\nDetalhe: " +
                    (str(error) or type(error).__name__) +
                    "\n\nRegistro: " + str(logs / "application.log"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
