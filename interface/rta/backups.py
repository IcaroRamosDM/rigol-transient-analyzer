"""Device-bound setup backups with checksums and restore readback."""
from pathlib import Path
import hashlib
import json
import math
import re
import uuid
from .common import Problem, now, read_json
from .instrument import Session, read_scope


def same_settings(expected, actual):
    keys=("time_div","memory_points","trigger_source","trigger_slope","trigger_level","trigger_sweep")
    def equal(a,b):
        return math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-10) if isinstance(a,(int,float)) and not isinstance(a,bool) else a==b
    return len(expected["channels"]) == len(actual["channels"]) and all(equal(expected[k],actual[k]) for k in keys) and all(
        all(equal(a[k],b[k]) for k in ("channel","probe","scale_v","offset_v","coupling","bandwidth","display"))
        for a,b in zip(expected["channels"],actual["channels"]))


def valid_metadata(row, identifier):
    if not isinstance(row, dict) or row.get("id") != identifier:
        return False
    if any(not isinstance(row.get(k),str) or not row[k] for k in ("date","model","serial","firmware","sha256","label")):
        return False
    if not re.fullmatch(r"[a-f0-9]{64}",row["sha256"]):
        return False
    state=row.get("state")
    if not isinstance(state,dict) or any(state.get(k)!=row[k] for k in ("model","serial","firmware")):
        return False
    if state.get("state") not in {"RUN","WAIT","TD","AUTO","STOP"}:
        return False
    if state.get("trigger_source") not in {"CHAN1","CHAN2","CHAN3","CHAN4"} or state.get("trigger_slope") not in {"POS","NEG"} or state.get("trigger_sweep") not in {"AUTO","NORM","SING"}:
        return False
    def finite(v):
        return not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v)
    if not finite(state.get("time_div")) or state["time_div"]<=0 or not finite(state.get("trigger_level")):
        return False
    depth=state.get("memory_points")
    if depth is not None and (not isinstance(depth,int) or isinstance(depth,bool) or depth<1):
        return False
    channels=state.get("channels")
    if not isinstance(channels,list) or not 1<=len(channels)<=4:
        return False
    seen=set()
    for channel in channels:
        if not isinstance(channel,dict) or not isinstance(channel.get("channel"),int) or channel["channel"] not in (1,2,3,4) or channel["channel"] in seen:
            return False
        seen.add(channel["channel"])
        if any(not finite(channel.get(k)) for k in ("probe","scale_v","offset_v")) or channel["probe"]<=0 or channel["scale_v"]<=0:
            return False
        if channel.get("coupling") not in {"AC","DC","GND"} or channel.get("bandwidth") not in {"OFF","20M"} or not isinstance(channel.get("display"),bool):
            return False
    return True


class BackupStore:
    def __init__(self, directory):
        self.directory=Path(directory).resolve()
        self.directory.mkdir(parents=True,exist_ok=True)

    def path(self, identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r"[a-f0-9]{32}",identifier):
            raise Problem("Backup inválido.")
        path=self.directory/identifier
        if path.is_symlink():
            raise Problem("Backup inválido.")
        return path

    def list(self):
        rows=[]
        for path in self.directory.iterdir():
            try:
                row=read_json(self.path(path.name)/"metadata.json")
                if not valid_metadata(row,path.name):
                    continue
                rows.append({k:row[k] for k in ("id","date","model","serial","firmware","sha256","label")})
            except (OSError,ValueError,TypeError,AttributeError,KeyError,Problem):
                continue
        return sorted(rows,key=lambda row:row["date"],reverse=True)

    def create(self, cfg, label="Manual"):
        state=read_scope(cfg["ip"],cfg["port"],model=cfg["model"], expected_identity=cfg.get("_identity"))
        with Session(cfg["ip"],cfg["port"],timeout=15) as session:
            identity=session.identity(cfg["model"], cfg.get("_identity"))
            data=session.block(":SYST:SET?")
        if any(identity[k]!=state[k] for k in ("model","serial","firmware")):
            raise Problem("A identidade do instrumento mudou durante o backup.",409)
        identifier=uuid.uuid4().hex
        path=self.path(identifier);path.mkdir()
        (path/"setup.bin").write_bytes(data)
        row=dict(id=identifier,date=now(),label=label,sha256=hashlib.sha256(data).hexdigest(),
                 state=state,**{k:identity[k] for k in ("model","serial","firmware")})
        (path/"metadata.json").write_text(json.dumps(row,ensure_ascii=False,allow_nan=False),encoding="utf-8")
        return {k:v for k,v in row.items() if k!="state"}

    def restore(self, identifier, cfg):
        path=self.path(identifier)
        try:
            row=read_json(path/"metadata.json")
            if not valid_metadata(row,identifier):
                raise Problem("Backup inválido.")
            binary=path/"setup.bin"
            if binary.is_symlink() or binary.stat().st_size>2*1024*1024:
                raise Problem("Backup inválido.")
            data=binary.read_bytes()
        except (OSError,ValueError):
            raise Problem("Backup não encontrado ou ilegível.",404) from None
        if not data or hashlib.sha256(data).hexdigest()!=row["sha256"]:
            raise Problem("A integridade do backup falhou.",409)
        # Identity check precedes every write, including on a reused address.
        with Session(cfg["ip"],cfg["port"],timeout=5) as session:
            device=session.identity(cfg["model"], cfg.get("_identity"))
        if any(row[k]!=device[k] for k in ("model","serial","firmware")):
            raise Problem("O backup pertence a outro instrumento ou firmware.",409)
        recovery=self.create(cfg,"Before restore")
        try:
            with Session(cfg["ip"],cfg["port"],timeout=20) as session:
                device=session.identity(cfg["model"], cfg.get("_identity"))
                if any(row[k]!=device[k] for k in ("model","serial","firmware")):
                    raise Problem("O instrumento mudou antes da restauração.",409)
                session.send_block(":SYST:SET",data)
                if session.query("*OPC;*OPC?")!="1":
                    raise Problem("O Rigol não confirmou a restauração.",502)
                session.send(":STOP" if row["state"]["state"]=="STOP" else ":RUN")
            actual=read_scope(cfg["ip"],cfg["port"],model=cfg["model"], expected_identity=cfg.get("_identity"))
            if not same_settings(row["state"],actual):
                raise Problem("A leitura não confirmou os ajustes restaurados.",502)
            return dict(restored=True,backup_id=identifier,recovery_id=recovery["id"],snapshot=actual)
        except (OSError,Problem) as error:
            raise Problem(str(error)+" Recovery backup: "+recovery["id"],502) from None
