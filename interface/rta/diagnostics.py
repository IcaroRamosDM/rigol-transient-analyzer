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
    for channel, probe in zip(state["channels"], (cfg["probe_v"],cfg["probe_i"])):
        n=channel["channel"]
        if not channel["display"]:
            add("hidden_channel","error",channel=n)
        if channel["probe"]!=probe:
            add("probe_setting","error",channel=n)
        if channel["coupling"]!="DC":
            add("coupling","error",channel=n)
        lo, hi = measurements.get("min"+str(n)),measurements.get("max"+str(n))
        if lo is None or hi is None:
            add("unavailable","warning",channel=n)
        elif lo <= -channel["offset_v"]-4*channel["scale_v"] or hi >= -channel["offset_v"]+4*channel["scale_v"]:
            add("clipping","warning",channel=n)
    lo,hi,freq=(measurements.get(k) for k in ("base2","top2","frequency2"))
    if lo is None or hi is None or freq is None:
        add("switching_unconfirmed","warning")
    elif freq<=0 or hi-lo < max(cfg["resistor"]*(cfg["high_a"]-cfg["low_a"]),1e-6):
        add("no_switching","error")
    else:
        if lo/cfg["resistor"]>cfg["low_a"] or hi/cfg["resistor"]<cfg["high_a"]:
            add("thresholds","error")
        else:
            add("switching","ok",frequency=freq,low_a=lo/cfg["resistor"],high_a=hi/cfg["resistor"])
        duty=measurements.get("duty2")
        if duty is None or not 0<duty<1:
            add("duty_unknown","warning")
        elif min(duty,1-duty)/freq <= (cfg["horizon_us"]+cfg["guard_us"]+cfg["window_us"])*1e-6:
            add("short_plateau","warning")
    average=measurements.get("average1")
    if average is not None and abs(average-cfg["nominal"])>max(cfg["nominal"]*.1,cfg["tolerance_v"]):
        add("nominal_voltage","warning",measured=average,expected=cfg["nominal"])
    add("physical_probes","info")
    return dict(checked_at=now(),state=state,measurements=measurements,checks=checks,
                ready=not any(row["level"] in {"error","warning"} for row in checks))


def diagnose(cfg):
    state=read_scope(cfg["ip"],cfg["port"],model=cfg["model"])
    values={}
    with Session(cfg["ip"],cfg["port"],timeout=12) as session:
        session.identity(cfg["model"])
        for key,item,ch in [("min1","VMIN",1),("max1","VMAX",1),("average1","VAVG",1),
                            ("min2","VMIN",2),("max2","VMAX",2),("base2","VBASE",2),
                            ("top2","VTOP",2),("frequency2","FREQ",2),("duty2","PDUT",2)]:
            try:
                value=float(session.query(":MEAS:ITEM? "+item+",CHAN"+str(ch)))
                values[key]=value if math.isfinite(value) and abs(value)<1e30 else None
            except ValueError:
                values[key]=None
    return evaluate(state,values,cfg)
