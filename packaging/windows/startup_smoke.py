"""Exercise the frozen app lifecycle in isolated state without an instrument."""
from pathlib import Path
import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

def request(url, path, data=None, token=""):
    with urlopen(Request(url+path, data=None if data is None else json.dumps(data).encode(),
            headers={"Content-Type":"application/json","X-RTA-Token":token}), timeout=3) as response:
        return json.load(response)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    exe=args.app.resolve()
    expected_version=(exe.parent/"_internal/VERSION").read_text(encoding="utf-8").strip()
    processes=[]
    report={}
    with tempfile.TemporaryDirectory(prefix="RTA startup ação ") as temporary:
        root=Path(temporary)
        def environment(name):
            env=os.environ.copy()
            env.update(PATH=str(Path(os.environ["SystemRoot"])/"System32"),
                       RTA_STATE_DIR=str(root/name/"state"),
                       RTA_RESULTS_DIR=str(root/name/"results"))
            return env
        def launch(env,extra=()):
            proc=subprocess.Popen([str(exe),"--no-browser","--quiet",*extra],cwd=exe.parent,
                                  env=env,creationflags=0x08000000)
            processes.append(proc)
            return proc
        def ready(proc,env,previous=""):
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                assert proc.poll() is None,("Startup exited",proc.returncode)
                try:
                    meta=json.loads((Path(env["RTA_STATE_DIR"])/"instance.json").read_text(encoding="utf-8"))
                    boot=request(meta["url"],"/api/bootstrap")
                    if (meta["pid"]==proc.pid and boot["instance"]==meta["instance"]
                            and boot["instance"]!=previous and not boot["closed"]):
                        assert boot["version"]==expected_version,boot["version"]
                        return meta["url"],boot
                except (OSError,ValueError,KeyError):pass
                time.sleep(.05)
            raise AssertionError("Application did not become ready")
        def stop(url,boot,proc):
            request(url,"/api/shutdown",{},boot["token"])
            assert proc.wait(timeout=10)==0
        try:
            env=environment("main")
            first=launch(env)
            url,boot=ready(first,env)
            original=boot["instance"]
            duplicates=[launch(env) for _ in range(6)]
            assert [proc.wait(timeout=15) for proc in duplicates]==[0]*6
            assert request(url,"/api/bootstrap")["instance"]==original
            report["six_simultaneous_opens_reuse_owner"]=True
            for _ in range(3):
                previous=boot["instance"]
                request(url,"/api/shutdown",{},boot["token"])
                new=launch(env)
                new_url,new_boot=ready(new,env,previous)
                assert first.wait(timeout=10)==0
                first,url,boot=new,new_url,new_boot
            report["close_and_immediately_reopen_cycles"]=3
            # Explicitly requested busy ports must fail without stealing the listener.
            other_env=environment("other")
            port=url.rsplit(":",1)[1]
            other=launch(other_env,["--port",port])
            assert other.wait(timeout=15)==1
            assert request(url,"/api/bootstrap")["instance"]==boot["instance"]
            report["busy_port_does_not_steal_listener"]=True
            # A failed metadata publication must release its listening socket.
            probe=socket.socket()
            probe.bind(("127.0.0.1",0))
            failed_port=probe.getsockname()[1]
            probe.close()
            failed_env=environment("failed")
            state=Path(failed_env["RTA_STATE_DIR"])
            (state/"instance.json").mkdir(parents=True)
            failed=launch(failed_env,["--port",str(failed_port)])
            assert failed.wait(timeout=15)==1
            probe=socket.socket()
            try:
                probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
                probe.bind(("127.0.0.1",failed_port))
            finally:probe.close()
            report["failed_start_releases_port"]=True
            report["version"]=boot["version"]
            report["path_without_python_or_wsl"]=True
            stop(url,boot,first)
            report["clean_shutdown"]=True
        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report))

if __name__=="__main__":
    main()
