"""Validated application settings and shared errors."""
from datetime import datetime, timezone
from pathlib import Path
import ipaddress
import json
import math

from .models import MODELS, selected_model
from .timebase import valid_time, floor_time, next_time, format_time

from .runtime import ROOT
DEFAULTS = dict(measurement="transients", configuration="guided", channels=None,
                voltage_channel=1, current_channel=2, trigger=None, model="auto", ip="169.254.112.67", port=5555, probe_v=10, probe_i=1,
                resistor=1, captures=1, points=1000000, nominal=5,
                scale_v=.5, scale_i=.1, time_div=.0002, bandwidth="20M",
                low_a=.05, high_a=.15, window_us=50, guard_us=20,
                horizon_us=300, tolerance_v=.05, hold_us=20,
                timeout=5, plots=True, require_edge=False)
ACTIVE = {"running", "cancelling"}
PHASES = {
    "conectando": "Identificando o osciloscópio",
    "configurando": "Configurando os canais",
    "aguardando_disparo": "Aguardando o disparo",
    "transferindo": "Recebendo os canais selecionados",
    "simulando": "Gerando sinal de demonstração",
    "analisando": "Analisando os dados",
    "exportando": "Salvando os resultados",
    "graficos": "Gerando imagens para exportação",
    "finalizando": "Finalizando o ensaio",
}


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))
def address(data):
    try:
        ip = str(ipaddress.IPv4Address(str(data["ip"]).strip()))
        port = int(data["port"])
        if isinstance(data["port"], bool) or str(port) != str(data["port"]):
            raise ValueError()
        if not 1 <= port <= 65535:
            raise ValueError()
        return ip, port
    except (KeyError, ValueError, TypeError):
        raise Problem("Informe um endereço IP válido e uma porta de 1 a 65535.") from None


def settings(data, detected=None):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise Problem("Configuração desconhecida.")
    cfg = DEFAULTS | data
    try:
        selected_model(cfg["model"])
    except ValueError as error:
        raise Problem(str(error)) from None
    profile = MODELS[cfg["model"] if cfg["model"] != "auto" else detected if detected in MODELS else "DHO802"]
    grid = profile["timebase"]
    cfg["ip"], cfg["port"] = address(cfg)
    if cfg["measurement"] not in ("transients", "signals") or cfg["configuration"] not in ("guided", "preserve", "memory"):
        raise Problem("Modo de medição ou configuração inválido.")
    if cfg["configuration"] == "memory" and cfg["captures"] != 1:
        raise Problem("A memória congelada permite apenas uma captura.")
    if cfg["configuration"] != "guided":
        # Inactive hardware fields are drafts, not commands to the instrument.
        for key in ("scale_v", "scale_i", "time_div", "nominal"):
            value = cfg[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                cfg[key] = DEFAULTS[key]
        for key in ("probe_v", "probe_i"):
            if isinstance(cfg[key], bool) or cfg[key] not in (1, 10): cfg[key] = DEFAULTS[key]
        if cfg["points"] not in (1000, 10000, 100000, 1000000): cfg["points"] = DEFAULTS["points"]
        if cfg["bandwidth"] not in ("20M", "OFF"): cfg["bandwidth"] = DEFAULTS["bandwidth"]
    if cfg["measurement"] == "signals":
        for key in ("voltage_channel", "current_channel", "probe_v", "probe_i", "resistor", "nominal", "scale_v", "scale_i", "low_a", "high_a", "window_us", "guard_us", "horizon_us", "tolerance_v", "hold_us"):
            cfg[key] = DEFAULTS[key]
    integers = {"voltage_channel": (1, profile["channels"]), "current_channel": (1, profile["channels"]),"captures": (1, 100), "points": (1000, 1000000),
                "probe_v": (1, 10), "probe_i": (1, 10)}
    for key, bounds in integers.items():
        value = cfg[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value:
            raise Problem("Valor inteiro inválido: " + key)
        cfg[key] = int(value)
        if not bounds[0] <= value <= bounds[1]:
            raise Problem("Valor fora da faixa: " + key)
    if cfg["points"] not in (1000, 10000, 100000, 1000000):
        raise Problem("Selecione uma profundidade de memória disponível.")
    if cfg["probe_v"] not in (1, 10) or cfg["probe_i"] not in (1, 10):
        raise Problem("As pontas devem estar em 1× ou 10×.")
    if not isinstance(cfg["require_edge"], bool):
        raise Problem("A opção de aguardar borda deve ser verdadeira ou falsa.")
    numeric = set(DEFAULTS) - set(integers) - {"ip", "port", "bandwidth", "plots", "model", "measurement", "configuration", "channels", "trigger", "require_edge"}
    for key in numeric:
        value = cfg[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise Problem("Valor numérico inválido: " + key)
        if (key not in {"low_a", "high_a", "guard_us"} and value <= 0) or (
                key == "guard_us" and value < 0):
            raise Problem("Use um valor positivo: " + key)
    if cfg["measurement"] == "transients" and cfg["low_a"] >= cfg["high_a"]:
        raise Problem("O limiar baixo deve ser menor que o limiar alto.")
    if cfg["horizon_us"] < cfg["window_us"] + cfg["guard_us"]:
        raise Problem("O horizonte deve comportar a janela e a guarda.")
    if cfg["hold_us"] > cfg["horizon_us"]:
        raise Problem("A permanência não pode superar o horizonte.")
    if cfg["bandwidth"] not in ("20M", "OFF") or not isinstance(cfg["plots"], bool):
        raise Problem("Configuração de banda ou gráficos inválida.")
    if not .1 <= cfg["timeout"] <= 30:
        raise Problem("Use um prazo de 0,1 a 30 segundos.")
    for key, probe in (() if cfg["configuration"] != "guided" else (("scale_v", "probe_v"), ("scale_i", "probe_i"))):
        if not profile["min_scale"] * cfg[probe] <= cfg[key] <= profile["max_scale"] * cfg[probe]:
            raise Problem("Escala fora da faixa da ponta: " + key)
    if cfg["configuration"] == "guided" and not profile["min_time"] <= cfg["time_div"] <= profile["max_time"]:
        raise Problem("Tempo por divisão fora da faixa do " + profile["model"] + ": " +
                      format_time(profile["min_time"]) + " a " + format_time(profile["max_time"]) + ".")
    if cfg["configuration"] == "guided" and not valid_time(cfg["time_div"], grid):
        value = cfg["time_div"]
        raise Problem("Tempo por divisão fora do passo do Rigol. Use " +
                      format_time(floor_time(value, grid)) + " ou " + format_time(next_time(value, grid)) + ".")
    from .measurement import validate_measurement
    return validate_measurement(cfg, profile)
