"""Read-only preflight checks. Unavailable measurements remain inconclusive."""
import math
from .common import now, Problem
from .instrument import Session, read_scope


def evaluate(state, measurements, cfg):
    checks = []
    def add(code, level, **values):
        checks.append(dict(code=code, level=level, **values))
    if state["state"]=="STOP":
        add("frozen", "warning")
    expected = cfg.get("channels") or [dict(number=1,probe=cfg["probe_v"],coupling="DC"),dict(number=2,probe=cfg["probe_i"],coupling="DC")]
    for wanted in expected:
        channel = next(c for c in state["channels"] if c["channel"] == wanted["number"])
        probe = wanted["probe"]
        n=channel["channel"]
        if not channel["display"]:
            add("hidden_channel","error",channel=n)
        if cfg.get("configuration", "guided") == "guided" and channel["probe"]!=probe:
            add("probe_setting","error",channel=n)
        if (cfg.get("measurement", "transients") == "transients" and channel["coupling"] != "DC") or (
                cfg.get("configuration", "guided") == "guided" and channel["coupling"] != wanted["coupling"]):
            add("coupling","error",channel=n)
        lo, hi = measurements.get("min"+str(n)),measurements.get("max"+str(n))
        if lo is None or hi is None:
            add("unavailable","warning",channel=n)
        elif lo <= -channel["offset_v"]-4*channel["scale_v"] or hi >= -channel["offset_v"]+4*channel["scale_v"]:
            add("clipping","warning",channel=n)
    if cfg.get("measurement", "transients") == "transients":
        lo,hi,freq=(measurements.get(k) for k in ("base"+str(cfg.get("current_channel",2)),"top"+str(cfg.get("current_channel",2)),"frequency"+str(cfg.get("current_channel",2))))
        if lo is None or hi is None or freq is None:
            add("switching_unconfirmed","warning")
        elif freq<=0 or hi-lo < max(cfg["resistor"]*(cfg["high_a"]-cfg["low_a"]),1e-6):
            add("no_switching","error")
        else:
            if lo/cfg["resistor"]>cfg["low_a"] or hi/cfg["resistor"]<cfg["high_a"]:
                add("thresholds","error")
            else:
                add("switching","ok",frequency=freq,low_a=lo/cfg["resistor"],high_a=hi/cfg["resistor"])
            duty=measurements.get("duty"+str(cfg.get("current_channel",2)))
            if duty is None or not 0<duty<1:
                add("duty_unknown","warning")
            elif min(duty,1-duty)/freq <= (cfg["horizon_us"]+cfg["guard_us"]+cfg["window_us"])*1e-6:
                add("short_plateau","warning")
        average=measurements.get("average"+str(cfg.get("voltage_channel",1)))
        if average is not None and abs(average-cfg["nominal"])>max(cfg["nominal"]*.1,cfg["tolerance_v"]):
            add("nominal_voltage","warning",measured=average,expected=cfg["nominal"])
    add("physical_probes","info")
    return dict(checked_at=now(),state=state,measurements=measurements,checks=checks,
                ready=not any(row["level"] in {"error","warning"} for row in checks))


def diagnose(cfg):
    state=read_scope(cfg["ip"],cfg["port"],model=cfg["model"], expected_identity=cfg.get("_identity"))
    values={}
    with Session(cfg["ip"],cfg["port"],timeout=12) as session:
        session.identity(cfg["model"], cfg.get("_identity"))
        queries=[]
        for channel in cfg["channels"]:
            ch=channel["number"]
            queries.extend((key+str(ch),item,ch) for key,item in (("min","VMIN"),("max","VMAX"),("average","VAVG")))
        if cfg["measurement"]=="transients":
            ch=cfg["current_channel"]
            queries.extend((key+str(ch),item,ch) for key,item in (("base","VBASE"),("top","VTOP"),("frequency","FREQ"),("duty","PDUT")))
        for key,item,ch in queries:
            try:
                value=float(session.query(":MEAS:ITEM? "+item+",CHAN"+str(ch)))
                values[key]=value if math.isfinite(value) and abs(value)<1e30 else None
            except ValueError:
                values[key]=None
    return evaluate(state,values,cfg)
