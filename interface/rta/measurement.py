"""Measurement contracts shared by profiles, acquisition, and instrument controls."""
import math
from .common import Problem


def finite(value):
    return not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value)


def validate_measurement(cfg, profile):
    channels = cfg["channels"]
    if channels is None and cfg["measurement"] == "signals":
        channels = [dict(number=1, probe=1, scale=1, center=0, coupling="DC", bandwidth="20M")]
    if channels is None:
        channels = [dict(number=cfg["voltage_channel"], probe=cfg["probe_v"], scale=cfg["scale_v"],
                         center=cfg["nominal"], coupling="DC", bandwidth=cfg["bandwidth"]),
                    dict(number=cfg["current_channel"], probe=cfg["probe_i"], scale=cfg["scale_i"],
                         center=0, coupling="DC", bandwidth=cfg["bandwidth"])]
    if not isinstance(channels, list) or not 1 <= len(channels) <= profile["channels"]:
        raise Problem("Selecione de um a quatro canais disponíveis no modelo.")
    normalized = []
    for channel in channels:
        if not isinstance(channel, dict) or set(channel) != {"number", "probe", "scale", "center", "coupling", "bandwidth"}:
            raise Problem("Configuração de canal inválida.")
        c = dict(channel)
        if cfg["configuration"] != "guided":
            if not finite(c["probe"]) or c["probe"] not in (1, 10): c["probe"] = 1
            if not finite(c["scale"]) or c["scale"] <= 0: c["scale"] = 1
            if not finite(c["center"]): c["center"] = 0
            if c["coupling"] not in ("AC", "DC"): c["coupling"] = "DC"
            if c["bandwidth"] not in ("OFF", "20M"): c["bandwidth"] = "20M"
        if not finite(c["number"]) or int(c["number"]) != c["number"] or not 1 <= c["number"] <= profile["channels"] or c["number"] in [v["number"] for v in normalized]:
            raise Problem("Canal indisponível ou repetido.")
        if not finite(c["probe"]) or c["probe"] not in (1, 10) or not finite(c["scale"]) or not finite(c["center"]) or c["scale"] <= 0 or c["coupling"] not in ("AC", "DC") or c["bandwidth"] not in ("OFF", "20M"):
            raise Problem("Configuração de canal inválida.")
        if cfg["configuration"] == "guided":
            if not profile["min_scale"]*c["probe"] <= c["scale"] <= profile["max_scale"]*c["probe"] or abs(c["center"]) > 100*c["probe"]:
                raise Problem("Escala ou centro fora da faixa do canal.")
        c["number"] = int(c["number"])
        c["probe"] = int(c["probe"])
        normalized.append(c)
    if cfg["measurement"] == "transients":
        if cfg["voltage_channel"] == cfg["current_channel"] or {c["number"] for c in normalized} != {cfg["voltage_channel"], cfg["current_channel"]} or len(normalized) != 2 or any(c["coupling"] != "DC" for c in normalized):
            raise Problem("Transientes exige dois canais distintos com acoplamento DC.")
        # Role order is stable in legacy exports even when physical channels change.
        normalized.sort(key=lambda c: c["number"] != cfg["voltage_channel"])
        cfg.update(probe_v=normalized[0]["probe"], probe_i=normalized[1]["probe"],
                   scale_v=normalized[0]["scale"], scale_i=normalized[1]["scale"])
    trigger = cfg["trigger"]
    if cfg["configuration"] != "guided" and (not isinstance(trigger, dict) or set(trigger) != {"source", "level", "slope"} or not finite(trigger.get("source")) or trigger["source"] not in [c["number"] for c in normalized] or not finite(trigger.get("level")) or trigger.get("slope") not in ("POS", "NEG")):
        trigger = None
    if trigger is None:
        trigger = dict(source=normalized[-1]["number"] if cfg["measurement"] == "transients" else normalized[0]["number"],
                       level=(cfg["low_a"]+cfg["high_a"])*.5*cfg["resistor"] if cfg["measurement"] == "transients" else 0,
                       slope="POS")
    if not isinstance(trigger, dict) or set(trigger) != {"source", "level", "slope"} or not finite(trigger["source"]) or trigger["source"] not in [c["number"] for c in normalized] or not finite(trigger["level"]) or trigger["slope"] not in ("POS", "NEG"):
        raise Problem("Disparo inválido para os canais selecionados.")
    if cfg["configuration"] == "guided":
        selected = next(c for c in normalized if c["number"] == trigger["source"])
        if abs(trigger["level"] - selected["center"]) > 5*selected["scale"]:
            raise Problem("O nível de disparo deve estar dentro da faixa vertical do canal.")
    cfg["channels"] = normalized
    cfg["trigger"] = dict(trigger, source=int(trigger["source"]))
    return cfg
