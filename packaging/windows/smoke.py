"""Install, exercise, upgrade and uninstall the Windows package without WSL/Python on its PATH."""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import winreg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "testes"))
from test_controle_rigol import MultiSessionScope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        parser.error("Use a new, empty smoke-test directory.")
    key_name = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name, access=winreg.KEY_READ|winreg.KEY_WOW64_64KEY):
            parser.error("An installation already exists; preserve it before running installer smoke tests.")
    except FileNotFoundError:
        pass
    target = work / "aplicativo ação"
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("RTA_", "WSL", "PYTHON")) or key in {"VIRTUAL_ENV", "MPLCONFIGDIR"}:
            env.pop(key, None)
    env.update(PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
               RTA_STATE_DIR=str(work/"estado ação"), RTA_RESULTS_DIR=str(work/"resultados ação"),
               MPLCONFIGDIR=str(work/"cache"))
    hidden = dict(creationflags=0x08000000)
    app = target / "RigolTransientAnalyzer.exe"
    report = {}
    process = None
    instrument = None
    url = token = None

    def run_setup():
        # NSIS /D must be last, with the directory unquoted in the raw command line.
        command = '"' + str(args.installer.resolve()) + '" /S /D=' + str(target)
        return subprocess.run(command, env=env, timeout=90, **hidden).returncode

    def api(path, data=None):
        headers = {} if data is None else {"Content-Type":"application/json", "X-RTA-Token":token}
        request = Request(url+path, data=None if data is None else json.dumps(data).encode(), headers=headers)
        with urlopen(request, timeout=20) as response:
            return response.read()

    def wait_job():
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            job = json.loads(api("/api/status"))["job"]
            if job and job["state"] not in {"running", "cancelling"}:
                return job
            time.sleep(.05)
        raise RuntimeError("The installed application did not complete its job.")

    try:
        assert run_setup()==0, "Installation failed"
        assert app.is_file(), "Application executable is missing"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name, access=winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
            assert winreg.QueryValueEx(key, "DisplayVersion")[0]=="0.1.0"
        report["installation"] = True
        with socket.socket() as listener:
            listener.bind(("127.0.0.1",0)); port=listener.getsockname()[1]
        process = subprocess.Popen([str(app),"--no-browser","--quiet","--port",str(port)],env=env,**hidden)
        deadline = time.monotonic()+20
        metadata = work/"estado ação/instance.json"
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError("Installed app exited before starting")
            try:
                meta=json.loads(metadata.read_text(encoding="utf-8"))
                url=meta["url"]
                data=json.loads(api("/api/bootstrap"))
                if data["instance"]==meta["instance"]: break
            except (OSError, ValueError, KeyError, URLError):
                pass
            time.sleep(.05)
        else:
            raise RuntimeError("Installed app did not open its interface")
        token=data["token"]
        assert data["packaged"] and data["version"]=="0.1.0"
        assert len(data["models"])==8
        report["standalone_without_python_or_wsl_on_path"] = True
        duplicate=subprocess.run([str(app),"--no-browser","--quiet"],env=env,timeout=10,**hidden)
        assert duplicate.returncode==0
        assert json.loads(api("/api/bootstrap"))["instance"]==data["instance"]
        report["single_instance"] = True
        api("/api/run",dict(mode="demo",settings=dict(plots=True)))
        job=wait_job()
        assert job["state"]=="done",job
        folder=work/"resultados ação"/job["id"]
        capture=folder/"captura_001"
        assert json.loads((capture/"metadados.json").read_text(encoding="utf-8"))["origem"]=="SIMULACAO"
        assert len(list((capture/"graficos").glob("*.png")))==8
        download=api("/download?run="+job["id"]+"&capture=captura_001&file=amostras.csv")
        assert hashlib.sha256(download).digest()==hashlib.sha256((capture/"amostras.csv").read_bytes()).digest()
        report["demo_export_png_and_download"] = True
        instrument=MultiSessionScope()
        instrument.falha="sem_disparo"
        cfg=dict(ip="127.0.0.1",port=instrument.porta,points=1000,plots=False,timeout=10)
        api("/api/connect",cfg)
        api("/api/run",dict(mode="real",settings=cfg))
        deadline=time.monotonic()+5
        while instrument.armadas<1 and time.monotonic()<deadline:time.sleep(.02)
        assert instrument.armadas>=1
        assert subprocess.run([str(app),"--shutdown","--quiet"],env=env,timeout=10,**hidden).returncode==2
        assert run_setup()==2, "Updating during capture must be refused"
        api("/api/cancel",{})
        assert wait_job()["state"]=="cancelled"
        assert instrument.estado=="STOP"
        report["cancel_and_busy_update_protection"] = True
        assert subprocess.run([str(app),"--shutdown","--quiet"],env=env,timeout=10,**hidden).returncode==0
        assert process.wait(timeout=10)==0
        process=None
        assert run_setup()==0
        assert (capture/"amostras.csv").is_file()
        report["upgrade_preserves_results"] = True
        (target/"user-note.txt").write_text("Preserve unknown files.",encoding="utf-8")
        subprocess.run([str(target/"Uninstall.exe"),"/S"],env=env,check=True,timeout=90,**hidden)
        # NSIS hands uninstall work to a temporary process; wait for both signals.
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key_name,access=winreg.KEY_READ|winreg.KEY_WOW64_64KEY):
                    registered=True
            except FileNotFoundError:
                registered=False
            if not app.exists() and not registered:
                break
            time.sleep(.05)
        assert not app.exists(), "Uninstaller left the executable"
        assert not registered, "Uninstall registration was not removed"
        assert (target/"user-note.txt").is_file()
        assert (capture/"amostras.csv").is_file()
        report["uninstall_preserves_results_and_unknown_files"] = True
        (work/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,indent=2))
    finally:
        if process and process.poll() is None:
            try:
                status=json.loads(api("/api/status"))
                if (status.get("job") or {}).get("state") in {"running","cancelling"}:
                    api("/api/cancel",{});wait_job()
                subprocess.run([str(app),"--shutdown","--quiet"],env=env,timeout=10,**hidden)
                process.wait(timeout=10)
            except Exception:
                process.kill();process.wait(timeout=5)
        if instrument:
            instrument.fechar()


if __name__ == "__main__":
    main()
