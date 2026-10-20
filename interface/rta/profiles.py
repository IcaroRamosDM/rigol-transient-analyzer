"""Named, validated bench profiles stored separately from measurements."""
from pathlib import Path
import json
import re
import threading
import uuid
from .common import Problem, settings, now, read_json


class ProfileStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise Problem("Perfil inválido.")
        path = self.directory / (identifier + ".json")
        if path.is_symlink():
            raise Problem("Perfil inválido.")
        return path

    def list(self):
        with self.lock:
            result = []
            for path in self.directory.glob("*.json"):
                try:
                    row = read_json(self.path(path.stem))
                    if not isinstance(row, dict) or row.get("id") != path.stem:
                        continue
                    name = row.get("name")
                    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c)<32 for c in name):
                        continue
                    if not isinstance(row.get("updated_at"), str):
                        continue
                    row["settings"] = settings(row["settings"])
                    result.append(row)
                except (OSError, ValueError, TypeError, AttributeError, OverflowError, KeyError, Problem):
                    continue
            return sorted(result, key=lambda row: row["name"].casefold())

    def save(self, data):
        name = data.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c)<32 for c in name):
            raise Problem("Use um nome de perfil com 1 a 80 caracteres.")
        cfg = settings(data.get("settings", {}))
        with self.lock:
            rows = self.list()
            identifier = data.get("id") or uuid.uuid4().hex
            path = self.path(identifier)
            if data.get("id") and not path.is_file():
                raise Problem("Perfil não encontrado.", 404)
            if not data.get("id") and len(rows) >= 100:
                raise Problem("Limite de 100 perfis atingido.")
            if any(row["name"].casefold()==name.strip().casefold() and row["id"]!=identifier for row in rows):
                raise Problem("Já existe um perfil com esse nome.", 409)
            row = dict(id=identifier, name=name.strip(), settings=cfg, updated_at=now())
            temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
            temporary.write_text(json.dumps(row,ensure_ascii=False,allow_nan=False),encoding="utf-8")
            temporary.replace(path)
            return row

    def delete(self, identifier):
        with self.lock:
            path = self.path(identifier)
            if not path.is_file():
                raise Problem("Perfil não encontrado.",404)
            # Keep a recoverable copy; no measurements are affected.
            path.replace(path.with_suffix("." + uuid.uuid4().hex + ".deleted"))
            return dict(deleted=True)
