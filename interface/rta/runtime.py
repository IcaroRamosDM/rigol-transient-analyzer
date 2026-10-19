"""Resource locations and per-user application state."""
from pathlib import Path
import ctypes
import os
import sys

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
FROZEN = bool(getattr(sys, "frozen", False))
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def state_dir():
    if os.environ.get("RTA_STATE_DIR"):
        return Path(os.environ["RTA_STATE_DIR"])
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "RigolTransientAnalyzer"
    return ROOT / "build"


def results_dir():
    if os.environ.get("RTA_RESULTS_DIR"):
        return Path(os.environ["RTA_RESULTS_DIR"])
    if os.name != "nt":
        return ROOT / "resultados"
    folder = ctypes.create_unicode_buffer(32768)
    status = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, folder)
    if status:
        raise OSError("Não foi possível localizar a pasta Documentos do Windows.")
    return Path(folder.value) / "Rigol Transient Analyzer" / "resultados"


def core_executable():
    if FROZEN:
        return ROOT / "core/carac_transientes.exe"
    return ROOT / ("build/windows/carac_transientes.exe" if os.name == "nt" else "build/carac_transientes")


def hidden_process():
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def process_environment():
    env = os.environ.copy()
    if os.name == "nt":
        if FROZEN:
            env["RTA_PLOT_EXE"] = sys.executable
            env.pop("RTA_PLOT_SCRIPT", None)
        else:
            env["RTA_PLOT_EXE"] = sys.executable
            env["RTA_PLOT_SCRIPT"] = str(ROOT / "ferramentas/graficos.py")
    return env
