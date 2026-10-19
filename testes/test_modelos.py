"""Profile contracts and simulated protocol tests; no physical instrument is used."""
import json
import subprocess
import unittest
from urllib.error import HTTPError

import test_interface as harness
from test_controle_rigol import MultiSessionScope
from interface.rta.common import Problem, settings
from interface.rta.models import MODELS, identify
from interface.rta.timebase import next_time, valid_time


class ModelCatalogTests(unittest.TestCase):
    def test_c_and_python_share_the_same_catalog(self):
        result = subprocess.run([str(harness.BIN), "--listar-modelos"], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.splitlines(), list(MODELS))
        self.assertEqual([m["model"] for m in MODELS.values() if m["bench_validated"]], ["DHO802"])

    def test_identification_is_exact_and_explicit_selection_is_checked(self):
        for model in MODELS:
            with self.subTest(model=model):
                self.assertEqual(identify("RIGOL TECHNOLOGIES," + model + ",SERIAL,FW")["model"], model)
                self.assertEqual(identify(" RIGOL , " + model + " , SERIAL , FW ", model)["model"], model)
        for identity, expected in [("OTHER RIGOL,DHO914,S,F", "auto"),
                ("RIGOL TECHNOLOGIES,DHO914,S,F,EXTRA", "auto"),
                ("RIGOL TECHNOLOGIES,DS1054Z,S,F", "auto"),
                ("RIGOL TECHNOLOGIES,DHO802,S,F", "DHO914"),
                ("RIGOL TECHNOLOGIES,DHO914,,F", "auto")]:
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                identify(identity, expected)

    def test_per_model_time_and_vertical_limits(self):
        for model, profile in MODELS.items():
            cfg = settings(dict(model=model, probe_v=1, probe_i=10,
                                scale_v=profile["min_scale"], scale_i=10*profile["min_scale"],
                                time_div=profile["min_time"]))
            self.assertEqual(cfg["model"], model)
            for change in [{"time_div":profile["min_time"]*.9}, {"time_div":501},
                           {"scale_v":profile["min_scale"]*.9}, {"scale_i":101}]:
                with self.subTest(model=model, change=change), self.assertRaises(Problem):
                    settings(cfg | change)
        self.assertEqual(settings(dict(time_div=2e-9), detected="DHO914")["model"], "auto")
        grid = MODELS["DHO914"]["timebase"]
        self.assertEqual(next_time(2e-9, grid), 2.1e-9)
        self.assertFalse(valid_time(2.05e-9, grid))
        self.assertTrue(valid_time(5.1e-9, grid))

    def test_unknown_model_and_invalid_types_are_rejected(self):
        for model in ["DHO999", "914", "DHO914;:RUN", None, [], 914]:
            with self.subTest(model=model), self.assertRaises(Problem):
                settings(dict(model=model))

    def test_each_catalog_model_uses_the_shared_c_configuration_driver(self):
        for model in MODELS:
            instrument = MultiSessionScope(model=model)
            try:
                result = subprocess.run([str(harness.BIN), "--configurar-apenas", "--modelo", model,
                    "--pontos", "1000", "--porta", str(instrument.porta), "127.0.0.1"],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, (model, result.stderr))
                self.assertEqual(instrument.armadas, 0)
            finally:
                instrument.fechar()

    def test_c_rejects_mismatch_unknown_identity_and_model_limits_without_writes(self):
        for actual, selected, extra in [("DHO802", "DHO914", []), ("DS1054Z", "auto", []),
                ("DHO802", "auto", ["--tempo-div", "2e-9"]),
                ("DHO914", "DHO914", ["--escala-shunt", ".0001"])]:
            instrument = MultiSessionScope(model=actual)
            try:
                result = subprocess.run([str(harness.BIN), "--configurar-apenas", "--modelo", selected,
                    "--porta", str(instrument.porta), *extra, "127.0.0.1"],
                    capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0, (actual, selected))
                self.assertEqual(instrument.commands, ["*IDN?"], result.stderr)
            finally:
                instrument.fechar()


class Dho900InterfaceTests(harness.InterfaceHarness, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.instrument = MultiSessionScope(model="DHO914")
        self.cfg = dict(ip="127.0.0.1", port=self.instrument.porta, plots=False, points=1000)
        self.app.connect(self.cfg)

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            self.instrument.fechar()

    def test_auto_detection_configuration_and_readback(self):
        self.assertEqual(self.app.connection["model"], "DHO914")
        self.assertFalse(self.app.connection["profile"]["bench_validated"])
        state = self.app.scope_action(dict(action="apply", settings=self.cfg | {"time_div":2e-9, "scale_i":.0002}))
        self.assertEqual(state["model"], "DHO914")
        self.assertEqual(state["time_div"], 2e-9)
        self.assertEqual(state["channels"][1]["scale_v"], .0002)
        self.assertNotEqual(state["state"], "STOP")

    def test_capturing_dho914_preserves_real_identity_and_uses_word_data(self):
        self.app.start(dict(mode="real", settings=self.cfg))
        job = self.wait()
        self.assertEqual(job["state"], "done", job)
        self.assertEqual(job["settings"]["model"], "DHO914")
        self.assertEqual(self.instrument.armadas, 1)
        metadata = list((self.app.results / job["id"]).rglob("metadados.json"))
        self.assertEqual(len(metadata), 1)
        self.assertIn(",DHO914,", json.loads(metadata[0].read_text())["instrumento"])
        self.assertIn(":WAV:FORM WORD", self.instrument.commands)

    def test_wrong_selection_cannot_run_or_configure(self):
        before = len(self.instrument.commands)
        for endpoint, payload in [("/api/connect", self.cfg | {"model":"DHO802"}),
                ("/api/scope", dict(action="apply", settings=self.cfg | {"model":"DHO802"})),
                ("/api/run", dict(mode="real", settings=self.cfg | {"model":"DHO802"}))]:
            with self.subTest(endpoint=endpoint), self.assertRaises(HTTPError):
                self.request(endpoint, payload)
        self.assertEqual(self.instrument.commands[before:], ["*IDN?"])

    def test_device_swap_after_identification_is_blocked_before_any_write(self):
        self.instrument.model = "DHO802"
        for action in ["run", "stop", "apply"]:
            before = len(self.instrument.commands)
            with self.subTest(action=action), self.assertRaises(Problem):
                self.app.scope_action(dict(action=action, settings=self.cfg))
            self.assertEqual(self.instrument.commands[before:], ["*IDN?"])

    def test_bootstrap_and_model_module_expose_profiles(self):
        data = json.loads(self.request("/api/bootstrap")[1])
        self.assertEqual(data["defaults"]["model"], "auto")
        self.assertEqual([m["model"] for m in data["models"]], list(MODELS))
        self.assertIn(b"configureModels", self.request("/modules/models.js")[1])
