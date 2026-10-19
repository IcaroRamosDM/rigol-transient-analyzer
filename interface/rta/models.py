"""Instrument profiles shared with the C driver via rigol_models.def.

Primary references:
https://download.rigol.com/en/Manual/Digital%20Oscilloscope/DHO900/DHO800900_ProgrammingGuide_EN.pdf
https://www.rigol.com/dam/global/downloads/brochures/en/data-sheet/oscilloscopes/DHO800_DataSheet_EN.pdf
https://www.rigol.com/dam/global/downloads/brochures/en/data-sheet/oscilloscopes/DHO900_DataSheet.pdf
"""
import ast
from pathlib import Path
import re

from .timebase import build_timebase


def _catalog():
    result = {}
    source = Path(__file__).resolve().parents[2] / "include/rigol_models.def"
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("//"):
            continue
        match = re.fullmatch(r"RIGOL_MODEL(\(.*\))", line)
        if not match:
            raise ValueError("Invalid Rigol model catalog")
        name, series, channels, mhz, tmin, tmax, vmin, validated = ast.literal_eval(match[1])
        if name in result:
            raise ValueError("Duplicate Rigol model")
        result[name] = dict(model=name, series=series, channels=channels, bandwidth_mhz=mhz,
                            min_time=tmin, max_time=tmax, min_scale=vmin, max_scale=10,
                            bench_validated=bool(validated), driver="dho800-900",
                            timebase=build_timebase(tmin, tmax))
    return result


MODELS = _catalog()


def selected_model(value):
    if not isinstance(value, str) or value not in {"auto", *MODELS}:
        raise ValueError("Selecione detecção automática ou um modelo Rigol disponível.")
    return value


def identify(identity, expected="auto"):
    selected_model(expected)
    fields = [part.strip() for part in identity.split(",")]
    if len(fields) != 4 or not all(fields) or fields[0].upper() not in {"RIGOL", "RIGOL TECHNOLOGIES"}:
        raise ValueError("Identificação do instrumento inválida: " + identity)
    model = fields[1].upper()
    if model not in MODELS:
        raise ValueError("Modelo sem perfil disponível: " + model + ". Use um modelo das séries DHO800/DHO900 listado no seletor.")
    if expected != "auto" and expected != model:
        raise ValueError("Modelo selecionado " + expected + "; instrumento conectado " + model + ". Nenhum ajuste enviado.")
    return dict(identity=identity, model=model, serial=fields[2], firmware=fields[3],
                profile=MODELS[model])
