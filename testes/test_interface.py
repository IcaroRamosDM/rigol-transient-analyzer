import importlib.util
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rta_ui", ROOT / "interface/servidor.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
BIN = Path(os.environ.get("CT_BIN", ROOT / "build/carac_transientes"))


class InterfaceHarness:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.app = ui.App(results=self.path / "results", executable=BIN)
        self.http = ui.server(self.app, 0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.http.server_port)

    def tearDown(self):
        if self.app.job and self.app.job["state"] in ui.ACTIVE:
            self.app.cancel()
            self.wait()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def request(self, path, data=None, token=True, headers=None):
        h = headers or {}
        if data is not None:
            h = {"Content-Type": "application/json", **h}
            if token:
                h["X-RTA-Token"] = self.app.token
        body = None if data is None else json.dumps(data).encode()
        try:
            with urlopen(Request(self.base + path, data=body, headers=h), timeout=10) as response:
                return response.status, response.read()
        except HTTPError as error:
            error.close()
            raise

    def wait(self, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.app.snapshot()["job"]
            if job and job["state"] not in ui.ACTIVE:
                return job
            time.sleep(.02)
        self.fail("Job did not finish")

    def demo(self, captures=1):
        self.app.start(dict(mode="demo", settings=dict(plots=False, captures=captures)))
        job = self.wait()
        self.assertEqual(job["state"], "done", job)
        return job


class InterfaceTests(InterfaceHarness, unittest.TestCase):
    def test_idle_shutdown_actually_stops_server(self):
        code, body = self.request("/api/shutdown", {})
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["closed"])
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
        self.assertTrue(self.app.closed)
        self.assertTrue(self.app.snapshot()["closed"])

    def test_bootstrap_has_reference_defaults(self):
        code, body = self.request("/api/bootstrap")
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(data["timebase"]["min_ps"], 5000)
        self.assertEqual(data["defaults"]["probe_v"], 10)
        self.assertEqual(data["defaults"]["probe_i"], 1)
        self.assertFalse(data["connection"]["connected"])

    def test_static_assets_and_missing_route(self):
        for path, marker in [("/", b"Rigol Transient Analyzer"),
                             ("/app.js", b"selectEvent"), ("/style.css", b"workspace-grid")]:
            with self.subTest(path=path):
                self.assertIn(marker, self.request(path)[1])
        with self.assertRaises(HTTPError) as caught:
            self.request("/missing")
        self.assertEqual(caught.exception.code, 404)

    def test_all_javascript_imports_are_served(self):
        pending = ["/app.js"]
        checked = set()
        while pending:
            path = pending.pop()
            if path in checked:
                continue
            code, body = self.request(path)
            self.assertEqual(code, 200, path)
            checked.add(path)
            for relative in re.findall(r'(?:from\s+|import\s*)["\']([^"\']+)["\']', body.decode()):
                self.assertTrue(relative.startswith("."), relative)
                pending.append(urljoin(path, relative))
        self.assertIn("/modules/jobs.js", checked)
        self.assertGreater(len(checked), 8)

    def test_cross_origin_and_token_are_rejected(self):
        for token, headers in [(False, {}), (True, {"Origin": "https://example.org"})]:
            with self.subTest(token=token, headers=headers), self.assertRaises(HTTPError) as caught:
                self.request("/api/run", dict(mode="demo"), token, headers)
            self.assertEqual(caught.exception.code, 403)
        self.assertIsNone(self.app.job)

    def test_untrusted_host_is_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/status", headers={"Host": "example.org:" + str(self.http.server_port)})
        self.assertEqual(caught.exception.code, 403)

    def test_real_run_requires_matching_connection(self):
        with self.assertRaises(ui.Problem):
            self.app.start(dict(mode="real"))
        self.app.connection = dict(connected=True, ip="127.0.0.1", port=5555)
        with self.assertRaises(ui.Problem):
            self.app.start(dict(mode="real", settings=dict(ip="127.0.0.2")))

    def test_connection_sends_only_identification(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0)); listener.listen(1)
        port = listener.getsockname()[1]
        commands = []
        def instrument():
            try:
                connection, _ = listener.accept()
                with connection:
                    command = connection.makefile("rb").readline()
                    commands.append(command)
                    connection.sendall(b"RIGOL TECHNOLOGIES,DHO802,CONNECTION_TEST,00.01.05\n")
            finally:
                listener.close()
        thread = threading.Thread(target=instrument)
        thread.start()
        result = self.app.connect(dict(ip="127.0.0.1", port=port))
        thread.join(2)
        self.assertTrue(result["connected"])
        self.assertEqual(commands, [b"*IDN?\n"])
        self.assertIsNone(self.app.job)

    def test_other_instrument_is_not_accepted(self):
        with mock.patch("interface.rta.service.scope_query", return_value="OTHER,MODEL,SERIAL,1"):
            with self.assertRaises(ui.Problem):
                self.app.connect(dict(ip="127.0.0.1", port=5555))
        self.assertFalse(self.app.connection["connected"])

    def test_demo_uses_c_and_exports_independent_captures(self):
        with mock.patch("interface.rta.service.scope_query", side_effect=AssertionError("Demo contacted instrument")):
            job = self.demo(2)
        self.assertEqual(job["phase"], "finalizando")
        detail = self.app.detail(job["id"])
        self.assertEqual(len(detail["captures"]), 2)
        self.assertTrue(detail["execution"]["simulacao"])
        self.assertTrue(all(c["metadata"]["origem"] == "SIMULACAO" for c in detail["captures"]))
        self.assertTrue(all(c["metadata"]["pontos"] == 10000 for c in detail["captures"]))
        self.assertEqual(len(self.app.history()), 1)
        self.assertGreater(detail["execution"]["eventos_validos"], 0)

    def test_downloads_match_exported_files(self):
        job = self.demo()
        query = "/download?run=" + job["id"] + "&capture=captura_001&file=eventos.csv"
        code, body = self.request(query)
        self.assertEqual(code, 200)
        self.assertEqual(body, (self.app.results / job["id"] / "captura_001/eventos.csv").read_bytes())
        code, body = self.request("/api/run?id=" + job["id"])
        self.assertEqual(json.loads(body)["captures"][0]["metadata"]["origem"], "SIMULACAO")

    def test_envelope_preserves_extrema_from_both_channels(self):
        folder = self.app.results / "spikes/captura_001"
        folder.mkdir(parents=True)
        with (folder / "amostras.csv").open("w") as file:
            file.write("tempo_s,tensao_v,corrente_a\n")
            for i in range(10000):
                v = 9 if i == 245 else (-3 if i == 248 else 5)
                current = 4 if i == 246 else (-2 if i == 247 else 0)
                file.write(str(i * 1e-6) + "," + str(v) + "," + str(current) + "\n")
        data = self.app.waveform("spikes", "captura_001", limit=100)
        self.assertLessEqual(len(data["points"]), 100)
        self.assertEqual(max(point[1] for point in data["points"]), 9)
        self.assertEqual(min(point[1] for point in data["points"]), -3)
        self.assertEqual(max(point[2] for point in data["points"]), 4)
        self.assertEqual(min(point[2] for point in data["points"]), -2)
        zoom = self.app.waveform("spikes", "captura_001", .00024, .00025, 100)
        self.assertLess(zoom["selected"], data["selected"])

    def test_path_traversal_and_symlinks_are_rejected(self):
        job = self.demo()
        for run, capture, name in [("../outside", "captura_001", "amostras.csv"),
                                   (job["id"], "../", "amostras.csv"),
                                   (job["id"], "captura_001", "../../README.md")]:
            with self.subTest(run=run, capture=capture), self.assertRaises(ui.Problem):
                self.app.download(run, capture, name)
    def test_symlinks_are_rejected(self):
        outside = self.path / "outside"; outside.mkdir()
        try:
            (self.app.results / "escape").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name == "nt" and getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is unavailable.")
            raise
        with self.assertRaises(ui.Problem):
            self.app.run_path("escape")

    def test_invalid_config_is_rejected_before_spawn(self):
        for data in [dict(resistor=0), dict(captures=True), dict(points=999),
                     dict(low_a=.2, high_a=.1), dict(horizon_us=2),
                     dict(nominal=float("nan")), dict(extra="--simular")]:
            with self.subTest(data=data), self.assertRaises(ui.Problem):
                self.app.start(dict(mode="demo", settings=data))
        self.assertIsNone(self.app.job)

    @unittest.skipIf(os.name == "nt", "POSIX script fixture; native cancellation is tested against the protocol fixture.")
    def test_cancellation_and_exclusive_job(self):
        script = self.path / "slow_engine"
        script.write_text("#!/usr/bin/env python3\nimport time\nprint('@RTA aguardando_disparo 1 1',flush=True)\ntime.sleep(30)\n")
        script.chmod(0o755)
        self.app.executable = script
        self.app.start(dict(mode="demo", settings=dict(plots=False)))
        deadline = time.monotonic()+3
        while self.app.snapshot()["job"]["phase"] != "aguardando_disparo" and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertEqual(self.app.snapshot()["job"]["phase"], "aguardando_disparo")
        with self.assertRaises(ui.Problem):
            self.app.start(dict(mode="demo"))
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/shutdown", {})
        self.assertEqual(caught.exception.code, 409)
        self.app.cancel()
        self.assertEqual(self.wait()["state"], "cancelled")
        self.assertIsNone(self.app.process)

    def test_real_acquisition_integration_uses_protocol_fixture(self):
        from test_integracao import Instrumento
        inst = Instrumento()
        try:
            with mock.patch("interface.rta.service.scope_query", return_value="RIGOL TECHNOLOGIES,DHO802,FIXTURE,TEST"):
                self.app.connect(dict(ip="127.0.0.1", port=inst.porta))
            self.app.start(dict(mode="real", settings=dict(ip="127.0.0.1", port=inst.porta,
                           points=1000, plots=False, timeout=1)))
            job = self.wait()
            self.assertEqual(job["state"], "done", job)
            self.assertEqual(inst.armadas, 1)
            self.assertFalse(self.app.detail(job["id"])["execution"]["simulacao"])
        finally:
            inst.fechar()


if __name__ == "__main__":
    unittest.main()
