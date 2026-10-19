"""Bounded, model-checked DHO800/900 control with explicit readback."""
import math
import socket
import time

from .common import Problem, now
from .models import identify


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

    def exact(self, size):
        result=bytearray()
        while len(result)<size:
            self.remaining()
            part=self.connection.recv(min(65536,size-len(result)))
            if not part:
                raise Problem("Bloco incompleto do Rigol.",502)
            result.extend(part)
        return bytes(result)

    def block(self, command, maximum=2*1024*1024):
        self.send(command)
        header=self.exact(2)
        if header[:1]!=b"#" or header[1:2] not in b"123456789":
            raise Problem("Cabeçalho binário inválido.",502)
        digits=self.exact(int(header[1:]))
        if not digits.isdigit():
            raise Problem("Comprimento binário inválido.",502)
        size=int(digits)
        if not 0<size<=maximum:
            raise Problem("Bloco do Rigol excede o limite.",502)
        data=self.exact(size)
        ending=self.exact(1)
        if ending==b"\r":
            ending=self.exact(1)
        if ending!=b"\n":
            raise Problem("Terminador binário inválido.",502)
        return data

    def send_block(self, command, data):
        count=str(len(data)).encode("ascii")
        packet=command.encode("ascii")+b" #"+str(len(count)).encode("ascii")+count+data+b"\n"
        self.remaining()
        self.connection.sendall(packet)

    def number(self, command):
        try:
            value = float(self.query(command))
        except ValueError:
            raise Problem("Resposta numérica inválida: " + command, 502) from None
        if not math.isfinite(value) or abs(value) >= 1e30:
            raise Problem("Valor indisponível: " + command, 502)
        return value

    def identity(self, expected="auto"):
        reply = self.query("*IDN?")
        try:
            return identify(reply, expected)
        except ValueError as error:
            raise Problem(str(error)) from None


def scope_query(ip, port, command="*IDN?", timeout=3):
    with Session(ip, port, timeout) as connection:
        return connection.query(command)


def read_scope(ip, port, action="read", model="auto", timeout=10):
    if action not in {"read", "run", "stop"}:
        raise Problem("Ação do Rigol desconhecida.")
    with Session(ip, port, timeout) as connection:
        identity = connection.identity(model)
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
        for channel in range(1, identity["profile"]["channels"]+1):
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
        return dict(**identity, state=state, channels=channels, checked_at=now(),
                    time_div=connection.number(":TIM:MAIN:SCAL?"), memory_points=memory_points,
                    trigger_source=connection.query(":TRIG:EDGE:SOUR?"),
                    trigger_slope=connection.query(":TRIG:EDGE:SLOP?"),
                    trigger_level=connection.number(":TRIG:EDGE:LEV?"),
                    trigger_sweep=connection.query(":TRIG:SWE?"))


def verify_profile(state, cfg):
    def close(actual, expected):
        return math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-10)
    channels = cfg["channels"]
    for expected in channels:
        channel = next(c for c in state["channels"] if c["channel"] == expected["number"])
        if not (channel["display"] and close(channel["probe"], expected["probe"]) and
                close(channel["scale_v"], expected["scale"]) and close(channel["offset_v"], -expected["center"]) and
                channel["coupling"] == expected["coupling"] and channel["bandwidth"] == expected["bandwidth"]):
            raise Problem("O canal " + str(channel["channel"]) + " não confirmou o perfil solicitado.", 502)
    trigger = cfg["trigger"]
    if not (close(state["time_div"], cfg["time_div"]) and state["memory_points"] == cfg["points"] and
            state["trigger_source"] == "CHAN"+str(trigger["source"]) and state["trigger_slope"] == trigger["slope"] and
            close(state["trigger_level"], trigger["level"])):
        raise Problem("A base de tempo, memória ou disparo não confirmou o perfil.", 502)
