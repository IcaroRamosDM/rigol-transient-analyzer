"""Regression checks for independent workflows and malformed saved records."""
import json
import unittest
from interface.rta.common import settings, address, Problem
from interface.rta.diagnostics import evaluate
from test_interface import InterfaceHarness
from test_controle_rigol import MultiSessionScope

class AuditContracts(unittest.TestCase):
    def test_signal_defaults_do_not_load_a_supply_profile(self):
        cfg=settings(dict(measurement="signals"))
        self.assertEqual(len(cfg["channels"]),1)
        self.assertEqual(cfg["channels"][0]["center"],0)
        self.assertEqual(cfg["channels"][0]["number"],1)
        self.assertEqual(settings(cfg),cfg)

    def test_address_contract_matches_the_ipv4_acquisition_core(self):
        with self.assertRaises(Problem):address(dict(ip="::1",port=5555))
        self.assertEqual(address(dict(ip="169.254.112.67",port=5555)),("169.254.112.67",5555))

    def test_preservation_diagnostic_uses_instrument_settings(self):
        cfg=settings(dict(measurement="signals",configuration="preserve"))
        state=dict(state="RUN",channels=[dict(channel=1,probe=100,coupling="AC",display=True,scale_v=1,offset_v=0)])
        result=evaluate(state,dict(min1=-.1,max1=.1),cfg)
        self.assertTrue(result["ready"],result)
        guided=evaluate(state,dict(min1=-.1,max1=.1),settings(dict(measurement="signals")))
        self.assertFalse(guided["ready"])

class AuditWorkflows(InterfaceHarness,unittest.TestCase):
    def test_read_and_run_ignore_inactive_analysis_drafts(self):
        scope=MultiSessionScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta,resistor=None,channels=[],time_div=None)
        try:
            self.app.connect(cfg)
            before=len(scope.commands)
            state=self.app.scope_action(dict(action="read",settings=cfg))
            self.assertEqual(state["state"],"STOP")
            self.assertTrue(all("?" in cmd for cmd in scope.commands[before:]))
            self.assertNotEqual(self.app.scope_action(dict(action="run",settings=cfg))["state"],"STOP")
            with self.assertRaises(Problem):
                self.app.scope_action(dict(action="apply",settings=cfg))
            self.assertFalse(self.app.snapshot()["scope"]["busy"])
        finally:scope.fechar()

    def test_autoset_is_explicit_bounded_and_does_not_create_a_capture(self):
        scope=MultiSessionScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta)
        try:
            self.app.connect(cfg)
            state=self.app.scope_action(dict(action="autoset",settings=cfg))
            self.assertIn(":AUToset",scope.commands)
            self.assertEqual(state["memory_points"],1000000)
            self.assertEqual(state["trigger_sweep"],"AUTO")
            self.assertEqual(scope.armadas,0)
            self.assertEqual(self.app.history(),[])
            self.assertFalse(self.app.scope["busy"])
        finally:scope.fechar()

    def test_malformed_record_does_not_hide_other_history(self):
        job=self.demo()
        bad=self.app.results/"malformed"/"captura_001"
        bad.mkdir(parents=True)
        for value in ([],None,{"origem":"SIMULACAO","instante_utc":"invalid","pontos":"invalid","dt_s":1,"t0_s":0}):
            (bad/"metadados.json").write_text(json.dumps(value))
            self.assertEqual([row["id"] for row in self.app.history()],[job["id"]])
        root=self.app.results/job["id"]
        (root/"execucao.json").write_text("[]")
        self.assertFalse(self.app.history()[0]["complete"])

    def test_empty_memory_has_specific_recovery_and_can_retry(self):
        class EmptyMemory(MultiSessionScope):
            empty=True
            def consulta(self,command):
                if self.empty and command==":WAV:DATA?":return b"#10\x0a"
                return super().consulta(command)
        scope=EmptyMemory()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False,measurement="signals",configuration="memory")
        try:
            self.app.connect(cfg)
            self.app.start(dict(mode="real",settings=cfg))
            job=self.wait()
            self.assertEqual(job["state"],"error")
            self.assertEqual(job["failure"]["kind"],"empty_memory")
            self.assertTrue(self.app.connection["connected"])
            scope.empty=False
            self.app.start(dict(mode="real",settings=cfg|dict(configuration="preserve")))
            self.assertEqual(self.wait()["state"],"done")
        finally:scope.fechar()

    def test_capture_refuses_unconfirmed_trigger_and_can_retry(self):
        class WrongTrigger(MultiSessionScope):
            wrong=True
            def consulta(self,command):
                if self.wrong and command==":TRIG:EDGE:LEV?":return "9"
                return super().consulta(command)
        scope=WrongTrigger()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False)
        try:
            self.app.connect(cfg)
            self.app.start(dict(mode="real",settings=cfg))
            job=self.wait()
            self.assertEqual(job["state"],"error")
            self.assertIn("Configuracao nao confirmada",job["message"])
            self.assertTrue(self.app.connection["connected"])
            self.assertEqual(scope.armadas,0)
            scope.wrong=False
            self.app.start(dict(mode="real",settings=cfg))
            self.assertEqual(self.wait()["state"],"done")
        finally:scope.fechar()
