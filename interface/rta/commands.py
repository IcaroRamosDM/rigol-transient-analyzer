"""Argument construction shared by acquisition and configuration-only mode."""

def build_command(executable, results, run, mode, cfg, configuration_only=False):
    command = [str(executable)]
    if configuration_only:
        command.append("--configurar-apenas")
        cfg = {**cfg, "plots": False, "captures": 1}
    else:
        command.extend(["--saida", str(results / run)])
    options = dict(resistor="resistor", capturas="captures", pontos="points",
                   porta="port", **{"sonda-v": "probe_v", "sonda-i": "probe_i",
                   "nominal-v": "nominal", "escala-v": "scale_v", "escala-shunt": "scale_i",
                   "tempo-div": "time_div", "banda": "bandwidth", "baixo-a": "low_a",
                   "alto-a": "high_a", "janela-us": "window_us", "guarda-us": "guard_us",
                   "horizonte-us": "horizon_us", "tolerancia-v": "tolerance_v",
                   "permanencia-us": "hold_us", "timeout": "timeout"})
    for flag, key in options.items():
        command.extend(["--" + flag, str(cfg[key])])
    if cfg["plots"]:
        command.append("--graficos")
    command.extend(["--simular"] if mode == "demo" else [cfg["ip"]])
    return command
