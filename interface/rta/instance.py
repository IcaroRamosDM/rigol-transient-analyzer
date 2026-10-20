"""Process-owned lock and validated loopback instance discovery."""
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import os
import time

from .runtime import state_dir


class InstanceLock:
    def __init__(self, directory=None):
        self.directory = Path(directory or state_dir())
        self.directory.mkdir(parents=True, exist_ok=True)
        self.stream = None
        self.metadata = self.directory / "instance.json"

    def acquire(self):
        self.stream = (self.directory / "interface.lock").open("a+b")
        if os.name == "nt":
            import msvcrt
            self.stream.seek(0, 2)
            if not self.stream.tell():
                self.stream.write(b"\0"); self.stream.flush()
            self.stream.seek(0)
            try:
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.stream.close(); self.stream = None
                return False
        else:
            import fcntl
            try:
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.stream.close(); self.stream = None
                return False
        return True

    def publish(self, url, identifier):
        temporary = self.metadata.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(dict(url=url, instance=identifier, pid=os.getpid())), encoding="utf-8")
        deadline = time.monotonic() + 2
        try:
            while True:
                try:
                    temporary.replace(self.metadata)
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.05)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def discover(self, attempts=1):
        for attempt in range(attempts):
            try:
                meta = json.loads(self.metadata.read_text(encoding="utf-8"))
                if not isinstance(meta, dict) or not isinstance(meta.get("url"), str):
                    raise ValueError("Invalid instance metadata")
                url = urlsplit(meta["url"])
                if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"} or not url.port or url.path:
                    raise ValueError("Invalid instance URL")
                with urlopen(meta["url"] + "/api/bootstrap", timeout=1) as response:
                    data = json.load(response)
                if not isinstance(data, dict):
                    raise ValueError("Invalid instance response")
                if data.get("app") == "Rigol Transient Analyzer" and not data.get("closed") and data.get("instance") == meta["instance"]:
                    return meta["url"], data
            except (OSError, ValueError, KeyError, URLError):
                pass
            if attempt + 1 < attempts:
                time.sleep(.1)
        return None

    def close(self):
        if self.stream:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close(); self.stream = None


def stop_running():
    instance = InstanceLock()
    deadline = time.monotonic() + 10
    while True:
        current = instance.discover()
        if current:
            break
        if instance.acquire():
            instance.close()
            return 0
        if time.monotonic() >= deadline:
            return 2
        time.sleep(.1)
    url, data = current
    request = Request(url + "/api/shutdown", data=b"{}", method="POST",
                      headers={"Content-Type":"application/json", "X-RTA-Token":data["token"]})
    try:
        with urlopen(request, timeout=3) as response:
            if not json.load(response).get("closed"):
                return 2
    except (URLError, HTTPError, ValueError):
        return 2
    for _ in range(50):
        if instance.acquire():
            instance.close()
            return 0
        time.sleep(.1)
    return 2
