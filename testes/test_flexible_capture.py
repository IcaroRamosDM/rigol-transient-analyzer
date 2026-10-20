"""Capture regressions for independently changed controls and signals without edges."""
import json
import struct
import unittest
from interface.rta.common import settings, Problem
from test_interface import InterfaceHarness
from test_controle_rigol import MultiSessionScope

class RejectSignedZero(MultiSessionScope):
    def configurar(self, command):
        parts = command.split()
        if len(parts) == 2 and parts[1].startswith("-") and float_or_none(parts[1]) == 0:
            return  # DHO802 firmware 00.01.05 reports -120, Invalid number.
        super().configurar(command)

def float_or_none(value):
    try: return float(value)
    except ValueError: return None

class NoEdgeScope(MultiSessionScope):
    forced = False
    complete_force = True
    def configurar(self, command):
        super().configurar(command)
        if command == ":SING": self.forced = False
        if command == ":TFOR": self.forced = True
    def consulta(self, command):
        if command == ":TRIG:STAT?" and self.pendente and not (self.forced and self.complete_force):
            return "WAIT"
        if command == ":WAV:DATA?":
            payload = struct.pack("<H", 40000) * (self.fim - self.inicio + 1)
            count = str(len(payload))
            return ("#" + str(len(count)) + count).encode() + payload + b"\n"
        return super().consulta(command)

class FlexibleCapture(InterfaceHarness, unittest.TestCase):
    def test_guided_zero_centers_replace_previous_offsets(self):
        scope = RejectSignedZero()
        cfg = dict(ip="127.0.0.1", port=scope.porta, plots=False, points=1000)
        try:
            self.app.connect(cfg)
            for center in (0.0, -0.0, 1.5, 0.0):
                with self.subTest(center=center):
                    self.app.scope_action(dict(action="apply", settings=cfg | dict(measurement="signals",
                        channels=[dict(number=1, probe=10, scale=1, center=center, coupling="DC", bandwidth="20M")])))
                    self.assertEqual(float(scope.parametros[":CHAN1:OFFS"]), -center)
            scope.parametros[":CHAN2:OFFS"] = "-0.2"
            self.app.scope_action(dict(action="apply", settings=cfg))
            self.assertEqual(float(scope.parametros[":CHAN2:OFFS"]), 0)
        finally: scope.fechar()

    def test_signal_dc_capture_does_not_require_an_edge(self):
        scope = NoEdgeScope()
        cfg = dict(ip="127.0.0.1", port=scope.porta, plots=False, points=1000,
                   measurement="signals", configuration="preserve", timeout=1)
        try:
            self.app.connect(cfg)
            self.app.start(dict(mode="real", settings=cfg))
            job = self.wait()
            self.assertEqual(job["state"], "done", job)
            self.assertEqual(scope.commands.count(":TFOR"), 1)
            self.assertEqual(scope.armadas, 1)
            meta = self.app.detail(job["id"])["captures"][0]["metadata"]
            self.assertTrue(meta["disparo_forcado"])
            self.assertFalse(meta["canais"][0]["frequencia_hz"])
            self.assertEqual(meta["canais"][0]["minimo_v"], meta["canais"][0]["maximo_v"])
            self.assertEqual(scope.parametros[":TRIG:SWE"], "NORM")
            self.assertTrue(self.app.connection["connected"])
        finally: scope.fechar()

    def test_strict_signal_and_transient_capture_never_force_an_edge(self):
        for measurement, require_edge in (("signals", True), ("transients", False)):
            with self.subTest(measurement=measurement):
                scope = NoEdgeScope()
                cfg = dict(ip="127.0.0.1", port=scope.porta, plots=False, points=1000,
                           measurement=measurement, require_edge=require_edge, timeout=.6)
                try:
                    self.app.connect(cfg)
                    self.app.start(dict(mode="real", settings=cfg))
                    job = self.wait()
                    self.assertEqual(job["state"], "error", job)
                    self.assertEqual(job["failure"]["kind"], "trigger_timeout")
                    self.assertNotIn(":TFOR", scope.commands)
                    self.assertTrue(self.app.connection["connected"])
                finally: scope.fechar()

    def test_force_without_completion_still_fails_and_allows_retry(self):
        scope = NoEdgeScope()
        scope.complete_force = False
        cfg = dict(ip="127.0.0.1", port=scope.porta, plots=False, points=1000,
                   measurement="signals", configuration="preserve", timeout=.6)
        try:
            self.app.connect(cfg)
            self.app.start(dict(mode="real", settings=cfg))
            job = self.wait()
            self.assertEqual(job["state"], "error", job)
            self.assertEqual(job["failure"]["kind"], "trigger_timeout")
            self.assertEqual(scope.commands.count(":TFOR"), 1)
            scope.complete_force = True
            self.app.start(dict(mode="real", settings=cfg))
            self.assertEqual(self.wait()["state"], "done")
        finally: scope.fechar()

    def test_normal_signal_edge_is_not_marked_forced(self):
        scope = MultiSessionScope()
        cfg = dict(ip="127.0.0.1", port=scope.porta, plots=False, points=1000,
                   measurement="signals", configuration="preserve")
        try:
            self.app.connect(cfg)
            self.app.start(dict(mode="real", settings=cfg))
            job = self.wait()
            self.assertEqual(job["state"], "done", job)
            self.assertNotIn(":TFOR", scope.commands)
            self.assertFalse(self.app.detail(job["id"])["captures"][0]["metadata"]["disparo_forcado"])
        finally: scope.fechar()

    def test_edge_requirement_is_a_boolean(self):
        self.assertFalse(settings(dict(measurement="signals"))["require_edge"])
        for value in (None, 0, "true", []):
            with self.subTest(value=value), self.assertRaises(Problem):
                settings(dict(require_edge=value))
