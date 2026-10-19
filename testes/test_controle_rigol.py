"""Protocol and lifecycle tests; these never use the physical instrument."""
import json
import math
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib.error import HTTPError
from unittest import mock

from test_integracao import Instrumento
import test_interface as harness
import unittest

BIN = harness.BIN
from interface.rta import instrument, service
from interface.rta.common import Problem, settings


class MultiSessionScope(Instrumento):
    def __init__(self, wrong_model=False, mismatch=False):
        self.stopping = threading.Event()
        self.commands = []
        self.wrong_model = wrong_model
        self.mismatch = mismatch
        super().__init__()
        self.parametros.update({":TIM:MAIN:SCAL": ".0002", ":ACQ:MDEP": "1000000",
            ":TRIG:EDGE:SOUR": "CHAN2", ":TRIG:EDGE:SLOP": "POS", ":TRIG:EDGE:LEV": ".1"})
        for channel, probe, scale, offset in [(1, 10, .5, -5), (2, 1, .1, 0)]:
            for name, value in {"PROB":probe, "SCAL":scale, "OFFS":offset,
                                "COUP":"DC", "BWL":"20M", "DISP":1}.items():
                self.parametros[f":CHAN{channel}:{name}"] = str(value)

    def consulta(self, command):
        if command == "*IDN?" and self.wrong_model:
            return "OTHER,DEVICE,SERIAL,1"
        if command == ":CHAN1:SCAL?" and self.mismatch:
            return "99"
        return super().consulta(command)

    def executar(self):
        self.servidor.settimeout(.1)
        try:
            while not self.stopping.is_set():
                try:
                    connection, _ = self.servidor.accept()
                except socket.timeout:
                    continue
                with connection:
                    connection.settimeout(2)
                    with connection.makefile("rb") as stream:
                        for line in stream:
                            for command in line.decode().strip().split(";"):
                                if not command:
                                    continue
                                self.commands.append(command)
                                if command.endswith("?"):
                                    reply = self.consulta(command)
                                    self.mandar(connection, reply if isinstance(reply, bytes) else
                                                (reply+"\n").encode())
                                else:
                                    self.configurar(command)
        except OSError:
            pass
        finally:
            self.servidor.close()

    def fechar(self):
        self.stopping.set()
        self.thread.join(3)


class RigolControls(harness.InterfaceHarness, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.instrument = MultiSessionScope()
        self.cfg = dict(ip="127.0.0.1", port=self.instrument.porta, plots=False)
        self.app.connect(self.cfg)

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            self.instrument.fechar()

    def action(self, action, **updates):
        code, data = self.request("/api/scope", dict(action=action, settings=self.cfg | updates))
        self.assertEqual(code, 200)
        return json.loads(data)

    def test_read_is_non_mutating_and_reports_actual_settings(self):
        before = len(self.instrument.commands)
        state = self.action("read")
        self.assertEqual(state["channels"][0]["probe"], 10)
        self.assertEqual(state["channels"][0]["offset_v"], -5)
        self.assertEqual(state["memory_points"], 1000000)
        self.assertEqual(state["state"], "STOP")
        self.assertTrue(all(c.endswith("?") for c in self.instrument.commands[before:]))
        self.assertFalse(self.app.snapshot()["scope"]["busy"])

    def test_apply_reuses_c_and_never_captures_or_creates_results(self):
        state = self.action("apply", points=1000, nominal=4.5, scale_v=1)
        self.assertNotEqual(state["state"], "STOP")
        self.assertEqual(state["trigger_sweep"], "AUTO")
        self.assertEqual(state["channels"][0]["offset_v"], -4.5)
        self.assertEqual(state["channels"][0]["scale_v"], 1)
        self.assertEqual(self.instrument.armadas, 0)
        self.assertFalse(any(c.startswith(":WAV:") for c in self.instrument.commands))
        self.assertEqual(list(self.app.results.iterdir()), [])

    def test_run_and_stop_have_confirmed_states(self):
        self.assertNotEqual(self.action("run")["state"], "STOP")
        self.assertEqual(self.action("stop")["state"], "STOP")

    def test_readback_failure_releases_exclusive_operation(self):
        self.instrument.mismatch = True
        with self.assertRaises(HTTPError) as caught:
            self.action("apply", points=1000)
        self.assertEqual(caught.exception.code, 502)
        state = self.app.snapshot()["scope"]
        self.assertFalse(state["busy"])
        self.assertIsNone(state["snapshot"])
        self.assertTrue(state["error"])
        self.instrument.mismatch = False
        self.assertEqual(self.action("read")["state"], "STOP")

    def test_scope_control_excludes_measurement_connect_and_shutdown(self):
        entered, release = threading.Event(), threading.Event()
        def delayed(*_):
            entered.set()
            release.wait(3)
            return {"state":"STOP"}
        errors = []
        def reader():
            try:
                self.app.scope_action(dict(action="read", settings=self.cfg))
            except Exception as error:
                errors.append(error)
        with mock.patch.object(service, "read_scope", side_effect=delayed):
            worker = threading.Thread(target=reader)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                for endpoint, body in [("/api/run", {"mode":"demo"}),
                        ("/api/scope", {"action":"stop", "settings":self.cfg}),
                        ("/api/connect", self.cfg), ("/api/shutdown", {})]:
                    with self.subTest(endpoint=endpoint), self.assertRaises(HTTPError) as caught:
                        self.request(endpoint, body)
                    self.assertEqual(caught.exception.code, 409)
            finally:
                release.set()
                worker.join(3)
        self.assertEqual(errors, [])

    def test_wrong_model_gets_no_control_commands(self):
        self.instrument.wrong_model = True
        before = len(self.instrument.commands)
        with self.assertRaises(HTTPError):
            self.action("run")
        self.assertEqual(self.instrument.commands[before:], ["*IDN?"])

    def test_unknown_action_and_nonfinite_settings_never_touch_instrument(self):
        before = len(self.instrument.commands)
        for action, updates in [(":RUN;:STOP", {}), ("read", {"points":math.nan}),
                                ("apply", {"scale_v":1e99}), ("apply", {"timeout":31}), ("apply", {"time_div":206e-6})]:
            with self.subTest(action=action, updates=updates), self.assertRaises(HTTPError):
                self.action(action, **updates)
        self.assertEqual(self.instrument.commands[before:], [])

    def test_new_static_modules_and_asset_are_available(self):
        for path, marker in [("/modules/core.js", b"export const S"), ("/modules/chart.js", b"function draw"),
                ("/modules/results.js", b"function openRun"), ("/modules/rigol.js", b"initRigol"), ("/modules/timebase.js", b"configureTimebase"),
                ("/assets/circuit.svg", b"IRFZ44N"), ("/rigol.css", b"rigol-grid")]:
            with self.subTest(path=path):
                self.assertIn(marker, self.request(path)[1])

    def test_c_configuration_only_rejects_incompatible_modes_before_io(self):
        for options in [("--simular",), ("--existente",), ("--sem-configurar",),
                        ("--saida", str(self.path/"forbidden")), ("--capturas", "2")]:
            result = subprocess.run([str(BIN), "--configurar-apenas", *options, "127.0.0.1"],
                                    capture_output=True, text=True, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--configurar-apenas", result.stderr)
        self.assertFalse((self.path/"forbidden").exists())

    def test_socket_deadline_applies_to_whole_reply(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0)); listener.listen(1)
        port = listener.getsockname()[1]
        def trickle():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.recv(128)
                    for _ in range(20):
                        connection.sendall(b"x")
                        time.sleep(.03)
            except OSError:
                pass
            finally:
                listener.close()
        worker = threading.Thread(target=trickle)
        worker.start()
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            instrument.scope_query("127.0.0.1", port, timeout=.12)
        self.assertLess(time.monotonic()-started, .5)
        worker.join(2)
