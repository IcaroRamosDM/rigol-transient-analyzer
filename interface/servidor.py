#!/usr/bin/env python3
"""Start the local Rigol Transient Analyzer application."""
from pathlib import Path
import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import webbrowser

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interface.rta.common import ROOT, DEFAULTS, ACTIVE, Problem
from interface.rta.service import App
from interface.rta.http import server

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
