"""Argument construction shared by acquisition and configuration-only mode."""

def build_command(executable, results, run, mode, cfg, configuration_only=False, input_file=None):
    command = [str(executable)]
    if configuration_only:
        command.append("--configurar-apenas")
        cfg = {**cfg, "plots": False, "captures": 1}
    else:
        command.extend(["--saida", str(results / run)])
    options = dict(modelo="model", resistor="resistor", capturas="captures", pontos="points",
                   porta="port", **{"sonda-v": "probe_v", "sonda-i": "probe_i",
                   "nominal-v": "nominal", "escala-v": "scale_v", "escala-shunt": "scale_i",
                   "tempo-div": "time_div", "banda": "bandwidth", "baixo-a": "low_a",
                   "alto-a": "high_a", "janela-us": "window_us", "guarda-us": "guard_us",
                   "horizonte-us": "horizon_us", "tolerancia-v": "tolerance_v",
                   "permanencia-us": "hold_us", "timeout": "timeout"})
    for flag, key in options.items():
        command.extend(["--" + flag, str(cfg[key])])
    command.extend(["--tipo", "sinais" if cfg["measurement"] == "signals" else "transientes",
                    "--ch-v", str(cfg["voltage_channel"]), "--ch-i", str(cfg["current_channel"])])
    for channel in cfg["channels"]:
        command.extend(["--canal", ":".join(str(channel[k]) for k in
                        ("number", "probe", "scale", "center", "coupling", "bandwidth"))])
    trigger = cfg["trigger"]
    command.extend(["--disparo-canal", str(trigger["source"]), "--disparo-v", str(trigger["level"]),
                    "--disparo-borda", trigger["slope"]])
    if cfg["measurement"] == "signals" and not cfg["require_edge"]:
        command.append("--sem-exigir-borda")
    if mode == "real" and not configuration_only:
        if cfg["configuration"] == "preserve": command.append("--sem-configurar")
        elif cfg["configuration"] == "memory": command.append("--existente")
    if cfg["plots"]:
        command.append("--graficos")
    if mode=="reanalysis":
        if input_file is None:
            raise ValueError("Reanalysis requires saved samples.")
        command.extend(["--entrada",str(input_file)])
    else:
        command.extend(["--simular"] if mode == "demo" else [cfg["ip"]])
    return command
