"""Bounded, model-checked DHO802 control with explicit readback."""
import math
import socket
import time

from .common import Problem, now


class Session:
    def __init__(self, ip, port, timeout=10):
        self.deadline = time.monotonic() + timeout
        self.connection = socket.create_connection((ip, port), timeout=timeout)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.connection.close()

    def remaining(self):
        value = self.deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("Prazo de comunicação com o Rigol esgotado.")
        self.connection.settimeout(value)

    def send(self, command):
        self.remaining()
        self.connection.sendall((command + "\n").encode("ascii"))

    def query(self, command):
        self.send(command)
        reply = bytearray()
        while not reply.endswith(b"\n"):
            self.remaining()
            part = self.connection.recv(1)
            if not part or len(reply) >= 1024:
                raise Problem("O instrumento retornou uma resposta incompleta.", 502)
            reply.extend(part)
        try:
            return reply.decode("ascii").strip()
        except UnicodeDecodeError:
            raise Problem("Resposta de texto inválida do Rigol.", 502) from None

    def number(self, command):
        try:
            value = float(self.query(command))
        except ValueError:
            raise Problem("Resposta numérica inválida: " + command, 502) from None
        if not math.isfinite(value) or abs(value) >= 1e30:
            raise Problem("Valor indisponível: " + command, 502)
        return value

    def identity(self):
        reply = self.query("*IDN?")
        fields = reply.split(",")
        if len(fields) < 4 or "RIGOL" not in fields[0] or fields[1] != "DHO802":
            raise Problem("Este perfil requer um Rigol DHO802. Resposta: " + reply)
        return reply


def scope_query(ip, port, command="*IDN?", timeout=3):
    with Session(ip, port, timeout) as connection:
        return connection.query(command)


def read_scope(ip, port, action="read"):
    if action not in {"read", "run", "stop"}:
        raise Problem("Ação do Rigol desconhecida.")
    with Session(ip, port) as connection:
        identity = connection.identity()
        if action == "run":
            connection.send(":TRIG:SWE AUTO;:RUN")
        elif action == "stop":
            connection.send(":STOP")
        state = connection.query(":TRIG:STAT?")
        if action in {"run", "stop"}:
            deadline = time.monotonic() + 1
            while (state != "STOP" if action == "stop" else state == "STOP"):
                if time.monotonic() >= deadline:
                    raise Problem("O Rigol não confirmou a mudança de estado.", 502)
                time.sleep(.02)
                state = connection.query(":TRIG:STAT?")
        if state not in {"RUN", "WAIT", "TD", "AUTO", "STOP"}:
            raise Problem("Estado de disparo desconhecido: " + state, 502)
        channels = []
        for channel in (1, 2):
            prefix = ":CHAN" + str(channel)
            channels.append(dict(channel=channel, probe=connection.number(prefix + ":PROB?"),
                                 scale_v=connection.number(prefix + ":SCAL?"),
                                 offset_v=connection.number(prefix + ":OFFS?"),
                                 coupling=connection.query(prefix + ":COUP?"),
                                 bandwidth=connection.query(prefix + ":BWL?"),
                                 display=connection.query(prefix + ":DISP?") in {"1", "ON"}))
        memory = connection.query(":ACQ:MDEP?")
        try:
            memory_points = int(float(memory))
            if memory_points < 1:
                raise ValueError()
        except (ValueError, OverflowError):
            if memory != "AUTO":
                raise Problem("Profundidade de memória inválida.", 502) from None
            memory_points = None
        return dict(identity=identity, state=state, channels=channels, checked_at=now(),
                    time_div=connection.number(":TIM:MAIN:SCAL?"), memory_points=memory_points,
                    trigger_source=connection.query(":TRIG:EDGE:SOUR?"),
                    trigger_slope=connection.query(":TRIG:EDGE:SLOP?"),
                    trigger_level=connection.number(":TRIG:EDGE:LEV?"),
                    trigger_sweep=connection.query(":TRIG:SWE?"))


def verify_profile(state, cfg):
    def close(actual, expected):
        return math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-10)
    for channel, probe, scale, offset in zip(state["channels"],
            (cfg["probe_v"], cfg["probe_i"]), (cfg["scale_v"], cfg["scale_i"]), (-cfg["nominal"], 0)):
        if not (channel["display"] and close(channel["probe"], probe) and
                close(channel["scale_v"], scale) and close(channel["offset_v"], offset) and
                channel["coupling"] == "DC" and channel["bandwidth"] == cfg["bandwidth"]):
            raise Problem("O canal " + str(channel["channel"]) + " não confirmou o perfil solicitado.", 502)
    if not (close(state["time_div"], cfg["time_div"]) and state["memory_points"] == cfg["points"] and
            state["trigger_source"] == "CHAN2" and state["trigger_slope"] == "POS" and
            close(state["trigger_level"], (cfg["low_a"] + cfg["high_a"]) * .5 * cfg["resistor"])):
        raise Problem("A base de tempo, memória ou disparo não confirmou o perfil.", 502)
