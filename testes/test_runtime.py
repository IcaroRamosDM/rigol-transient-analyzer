"""Cross-platform instance isolation and native C cancellation checks."""
from pathlib import Path
import json
import os
import tempfile
import time
import unittest
from unittest import mock
from urllib.error import HTTPError

import test_interface as harness
from test_controle_rigol import MultiSessionScope
from interface.rta.instance import InstanceLock
from interface.rta.runtime import state_dir, results_dir


class InstanceTests(unittest.TestCase):
    def test_lock_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = InstanceLock(folder), InstanceLock(folder)
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.publish("http://localhost:8765", "instance")
                self.assertEqual(json.loads(first.metadata.read_text())["instance"], "instance")
                first.close()
                self.assertTrue(second.acquire())
            finally:
                first.close(); second.close()

    def test_user_data_overrides_do_not_depend_on_install_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with mock.patch.dict(os.environ, RTA_STATE_DIR=str(base/"state"), RTA_RESULTS_DIR=str(base/"results")):
                self.assertEqual(state_dir(), base/"state")
                self.assertEqual(results_dir(), base/"results")


class RuntimeControls(harness.InterfaceHarness, unittest.TestCase):
    def test_instance_discovery_checks_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            lock = InstanceLock(folder)
            lock.publish(self.base, self.app.instance_id)
            self.assertEqual(lock.discover()[0], self.base)
            lock.publish(self.base, "another-process")
            self.assertIsNone(lock.discover())

    def test_cancel_native_acquisition_is_exclusive_and_stops_scope(self):
        instrument = MultiSessionScope()
        instrument.falha = "sem_disparo"
        cfg = dict(ip="127.0.0.1", port=instrument.porta, points=1000, plots=False, timeout=10)
        try:
            self.app.connect(cfg)
            self.app.start(dict(mode="real", settings=cfg))
            deadline = time.monotonic()+4
            while instrument.armadas < 1 and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertGreaterEqual(instrument.armadas, 1)
            with self.assertRaises(HTTPError) as caught:
                self.request("/api/shutdown", {})
            self.assertEqual(caught.exception.code, 409)
            with self.assertRaises(harness.ui.Problem):
                self.app.start(dict(mode="demo"))
            before = time.monotonic()
            self.app.cancel()
            job = self.wait()
            self.assertEqual(job["state"], "cancelled", job)
            self.assertLess(time.monotonic()-before, 2.5)
            self.assertEqual(instrument.estado, "STOP")
            self.assertIsNone(self.app.process)
            self.assertEqual(list(self.app.results.glob(".cancel-*")), [])
        finally:
            if self.app.job and self.app.job["state"] in harness.ui.ACTIVE:
                self.app.cancel(); self.wait()
            instrument.fechar()
