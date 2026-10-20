"""Offline analysis consumes saved samples and analysis criteria only."""
from .common import DEFAULTS, Problem, settings
from .models import identify

ANALYSIS_FIELDS = {"low_a", "high_a", "window_us", "guard_us", "horizon_us",
                   "tolerance_v", "hold_us", "plots"}
METADATA_FIELDS = {"low_a": ("limiar_baixo_a", 1), "high_a": ("limiar_alto_a", 1),
                   "window_us": ("janela_s", 1e6), "guard_us": ("guarda_s", 1e6),
                   "horizon_us": ("horizonte_s", 1e6), "tolerance_v": ("tolerancia_v", 1),
                   "hold_us": ("permanencia_s", 1e6)}

def reanalysis_settings(draft, metadata, original):
    if not isinstance(draft, dict) or set(draft) - set(DEFAULTS):
        raise Problem("Configuração desconhecida.")
    resistance = metadata["resistor_ohm"]
    if "resistor" in draft and draft["resistor"] != resistance:
        raise Problem("A reanálise preserva o resistor e a conversão de corrente originais.")
    roles = metadata.get("canais_solicitados", [1, 2])
    try:
        model = identify(original.get("instrumento", ""))["model"]
    except (ValueError, AttributeError):
        model = "DHO804" if max(roles) > 2 else "DHO802"
    criteria = {key: metadata[field]*factor for key, (field, factor) in METADATA_FIELDS.items()}
    criteria.update({key: draft[key] for key in ANALYSIS_FIELDS if key in draft})
    return settings(criteria | dict(measurement="transients", configuration="preserve",
                    model=model, voltage_channel=roles[0], current_channel=roles[1],
                    resistor=resistance, captures=1))
