#!/usr/bin/env python3
"""Start the local Rigol Transient Analyzer application."""
from pathlib import Path
import argparse
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
from interface.rta.instance import InstanceLock
from interface.rta.process import KILL
from interface.rta.runtime import FROZEN, hidden_process

def open_browser(url):
    if os.name=="nt":
        # Default-browser activation must not retain this executable after shutdown.
        helper=os.path.join(os.environ.get("SystemRoot",r"C:\Windows"),"System32","rundll32.exe")
        subprocess.Popen([helper,"url.dll,FileProtocolHandler",url],
                         stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                         **hidden_process())
    elif os.environ.get("WSL_DISTRO_NAME") and shutil.which("powershell.exe"):
        subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", "Start-Process", url],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("Use uma porta de 1 a 65535.")
    instance = InstanceLock()
    if not instance.acquire():
        current = instance.discover(attempts=30)
        if not current:
            raise SystemExit("O aplicativo já está iniciando. Aguarde alguns segundos e abra-o novamente.")
        if not args.no_browser:
            open_browser(current[0])
        return
    try:
        app = App()
        ports = [args.port] if args.port else range(8765, 8776) if os.name == "nt" else [8765]
        http = None
        for port in ports:
            try:
                http = server(app, port)
                break
            except OSError:
                continue
        if http is None:
            raise SystemExit("Porta ocupada. Use --port com outra porta local.")
        url = "http://localhost:" + str(http.server_port)
        instance.publish(url, app.instance_id)
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
                        app._signal(process, KILL)
        finally:
            http.server_close()
    finally:
        instance.close()


if __name__ == "__main__":
    main()
