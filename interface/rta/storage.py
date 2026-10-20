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
                if not isinstance(meta, dict) or not all(key in meta for key in ("origem", "instante_utc", "pontos", "dt_s", "t0_s")):
                    continue
                if not isinstance(meta["pontos"], int) or not 2 <= meta["pontos"] <= 1000000:
                    continue
                if any(not isinstance(meta[k], (int, float)) or not math.isfinite(meta[k]) for k in ("dt_s", "t0_s")) or meta["dt_s"] <= 0:
                    continue
                if meta.get("tipo_medicao") == "sinais":
                    if not isinstance(meta.get("canais"), list) or not 1 <= len(meta["canais"]) <= 4:
                        continue
                    if any(not isinstance(c, dict) or c.get("numero") not in (1,2,3,4) for c in meta["canais"]):
                        continue
                page = dict(events=[], offset=0, total=0)
                if meta.get("tipo_medicao") == "sinais":
                    self.inside(path, folder.name + "/medidas.csv")
                else:
                    page = self.events(run, folder.name)
                events = page["events"]
                pngs = [file.name for file in sorted((folder / "graficos").glob("*.png"))
                        if file.is_file() and file.resolve().is_relative_to(path)]
                captures.append(dict(id=folder.name, metadata=meta, events=events, event_count=page["total"], event_offset=page["offset"], images=pngs))
            except (OSError, ValueError, TypeError, AttributeError, KeyError, Problem):
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
        if not isinstance(execution, dict):
            execution = {}
        if not isinstance(provenance, dict):
            provenance = None
        return dict(id=run, captures=captures, execution=execution,provenance=provenance)

    @staticmethod
    def _parse_event(row):
        event = {key: value if key in ("direcao", "status") else
                 (float(value) if value else None) for key, value in row.items()}
        if any(isinstance(value, float) and not math.isfinite(value) for value in event.values()):
            raise Problem("Dados de transição inválidos.")
        if not isinstance(event.get("evento"), (int,float)) or event["evento"] < 1:
            raise Problem("Dados de transição inválidos.")
        return event

    def events(self, run, capture, offset=0, limit=200, valid_only=False):
        if not isinstance(capture, str) or not re.fullmatch(r"captura_\d+", capture):
            raise Problem("Captura inválida.")
        offset, limit = int(offset), int(limit)
        if offset < 0 or not 1 <= limit <= 200:
            raise Problem("Página de transições inválida.")
        root = self.run_path(run)
        meta = read_json(self.inside(root, capture+"/metadados.json"))
        total = meta.get("eventos_validos" if valid_only else "bordas", 0)
        if isinstance(total, bool) or not isinstance(total, int) or not 0 <= total <= 1000000:
            raise Problem("Dados de transição inválidos.")
        rows = []
        with self.inside(root, capture+"/eventos.csv").open(newline="") as stream:
            index = 0
            for row in csv.DictReader(stream):
                if valid_only and row.get("status") != "valido":
                    continue
                if index >= offset:
                    rows.append(self._parse_event(row))
                    if len(rows) >= limit:
                        break
                index += 1
        return dict(events=rows, offset=offset, total=total)

    def event(self, run, capture, identifier):
        if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier < 1:
            raise Problem("Selecione uma transição válida.")
        if not isinstance(capture, str) or not re.fullmatch(r"captura_\d+", capture):
            raise Problem("Captura inválida.")
        root = self.run_path(run)
        with self.inside(root, capture+"/eventos.csv").open(newline="") as stream:
            for row in csv.DictReader(stream):
                if float(row["evento"]) == identifier:
                    return self._parse_event(row)
        raise Problem("Selecione uma transição válida.")

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
                                    valid=sum(c["metadata"].get("eventos_validos", 0) for c in captures),
                                    measurement=first.get("tipo_medicao", "transientes"),
                                    complete=detail["execution"].get("concluido") is True))
            except (OSError, ValueError, TypeError, AttributeError, KeyError, Problem):
                continue
        return sorted(history, key=lambda row: row["date"], reverse=True)

    def waveform(self, run, capture, start=None, end=None, limit=2400):
        if not re.fullmatch(r"captura_\d+", capture):
            raise Problem("Captura inválida.")
        path = self.inside(self.run_path(run), capture + "/amostras.csv")
        key = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        with self.cache_lock:
            if key in self.cache:
                headers, columns = self.cache.pop(key)
                self.cache[key] = (headers, columns)
            else:
                with path.open(newline="") as file:
                    reader = csv.reader(file)
                    headers = next(reader, None)
                    generic = headers and 2 <= len(headers) <= 5 and headers[0] == "tempo_s" and all(re.fullmatch(r"CH[1-4]_V", h) for h in headers[1:]) and len(set(headers)) == len(headers)
                    if headers != ["tempo_s", "tensao_v", "corrente_a"] and not generic:
                        raise Problem("Formato de amostras inválido.")
                    columns = [array("d") for _ in headers]
                    previous = -math.inf
                    for row in reader:
                        if len(row) != len(headers):
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
                self.cache[key] = (headers, columns)
                while len(self.cache) > 2:
                    self.cache.popitem(last=False)
        t = columns[0]
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
            buckets = max(1, (limit - 2) // (2*(len(columns)-1)))
            indices = {first, last - 1}
            for bucket in range(buckets):
                a = first + (last - first) * bucket // buckets
                b = first + (last - first) * (bucket + 1) // buckets
                for column in columns[1:]:
                    indices.add(min(range(a, b), key=column.__getitem__))
                    indices.add(max(range(a, b), key=column.__getitem__))
            indices = sorted(indices)
        return dict(points=[[column[k] for column in columns] for k in indices], columns=headers,
                    total=len(t), selected=last-first, start=t[first], end=t[last-1],
                    record_start=t[0], record_end=t[-1])

    def download(self, run, capture, name):
        root = self.run_path(run)
        if capture:
            if not re.fullmatch(r"captura_\d+", capture):
                raise Problem("Captura inválida.")
            allowed = {"amostras.csv", "eventos.csv", "medidas.csv", "metadados.json", "resumo.txt"}
            if name not in allowed and not re.fullmatch(
                    r"graficos/(?:visao_geral|evento_\d+_(?:subida|descida))\.png", name):
                raise Problem("Exportação desconhecida.", 404)
            return self.inside(root, capture + "/" + name)
        if re.fullmatch(r"reports/report_[a-f0-9]{32}\.pdf",name):
            return self.inside(root,name)
        if name not in {"execucao.json", "estatisticas.csv","proveniencia.json"}:
            raise Problem("Exportação desconhecida.", 404)
        return self.inside(root, name)
