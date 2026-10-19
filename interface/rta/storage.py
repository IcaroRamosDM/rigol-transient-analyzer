"""Saved runs, validated exports, and bounded waveform caching."""
from array import array
from collections import OrderedDict
from pathlib import Path
import bisect
import csv
import math
import re
import threading

from .common import Problem, read_json


class ResultStore:
    def __init__(self, results):
        self.results = Path(results).resolve()
        self.results.mkdir(exist_ok=True, parents=True)
        self.cache_lock = threading.Lock()
        self.cache = OrderedDict()

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
        try:
            provenance=read_json(self.inside(path,"proveniencia.json"))
        except (OSError,ValueError,Problem):
            provenance=None
        return dict(id=run, captures=captures, execution=execution,provenance=provenance)

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
        if re.fullmatch(r"reports/report_[a-f0-9]{32}\.pdf",name):
            return self.inside(root,name)
        if name not in {"execucao.json", "estatisticas.csv","proveniencia.json"}:
            raise Problem("Exportação desconhecida.", 404)
        return self.inside(root, name)
