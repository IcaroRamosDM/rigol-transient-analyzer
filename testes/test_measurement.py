"""Two measurement contracts and protocol acceptance, without physical hardware."""
import csv
import json
import math
import unittest
import time
from urllib.parse import urlparse,parse_qs
from test_interface import InterfaceHarness
from test_controle_rigol import MultiSessionScope
from interface.rta.common import settings, Problem
from interface.rta.commands import build_command
from interface.rta.reports import report


def channel(n=1, probe=1, scale=1, center=0, coupling="DC"):
    return dict(number=n,probe=probe,scale=scale,center=center,coupling=coupling,bandwidth="20M")

class MeasurementContracts(unittest.TestCase):
    def test_legacy_profiles_migrate_and_modes_validate(self):
        cfg=settings(dict(nominal=12,scale_v=2,low_a=.1,high_a=.4))
        self.assertEqual(cfg["measurement"],"transients")
        self.assertEqual(cfg["channels"][0]["center"],12)
        self.assertEqual(cfg["trigger"]["level"],.25)
        self.assertEqual(settings(cfg),cfg)
        for change in [dict(measurement="unknown"),dict(channels=[]),dict(channels=[channel(),channel()]),
                       dict(measurement="signals",channels=[channel(3)]),dict(trigger=dict(source=1,level=900,slope="POS")),
                       dict(configuration="memory",captures=2),dict(channels=[channel(1,coupling="AC"),channel(2)]),
                       dict(measurement="signals",channels=[channel()],trigger=dict(source=2,level=0,slope="POS"))]:
            with self.subTest(change=change),self.assertRaises(Problem):settings(change)

    def test_preserve_ignores_invalid_unused_drafts_but_keeps_analysis_validation(self):
        cfg=settings(dict(measurement="signals",configuration="preserve",time_div=None,scale_v=None,
                          channels=[channel(1,scale=None,center=None)],trigger=dict(source=99,level=None,slope="invalid")))
        self.assertEqual(cfg["channels"][0]["number"],1)
        self.assertGreater(cfg["channels"][0]["scale"],0)
        self.assertEqual(settings(dict(measurement="signals",channels=[channel(1)],trigger=dict(source=1.0,level=0,slope="POS")))["trigger"]["source"],1)
        with self.assertRaises(Problem):settings(dict(configuration="preserve",resistor=0))
        with self.assertRaises(Problem):settings(dict(measurement="signals",channels=[channel(1,scale=None)]))

    def test_four_channel_selection_and_preservation_commands(self):
        cfg=settings(dict(model="DHO914",measurement="signals",configuration="preserve",channels=[channel(n) for n in (1,2,3,4)]))
        from pathlib import Path
        command=build_command(Path("core"),Path("results"),"run","real",cfg)
        self.assertIn("--sem-configurar",command)
        self.assertEqual(command.count("--canal"),4)
        self.assertNotIn("--existente",command)
        cfg=settings(cfg|dict(configuration="memory"))
        self.assertIn("--existente",build_command(Path("core"),Path("results"),"run","real",cfg))

class Measurements(InterfaceHarness,unittest.TestCase):
    def test_signals_demo_export_metrics_plot_and_pdf(self):
        self.app.start(dict(mode="demo",settings=dict(measurement="signals",channels=[channel(1),channel(2)],plots=True)))
        job=self.wait(30);self.assertEqual(job["state"],"done",job)
        detail=self.app.detail(job["id"]);cap=detail["captures"][0];meta=cap["metadata"]
        self.assertEqual(meta["tipo_medicao"],"sinais")
        self.assertEqual(meta["pontos"],10000)
        self.assertEqual(cap["events"],[])
        self.assertIn("visao_geral.png",cap["images"])
        wave=self.app.waveform(job["id"],cap["id"],limit=101)
        self.assertEqual(wave["columns"],["tempo_s","CH1_V","CH2_V"])
        self.assertLessEqual(len(wave["points"]),101)
        self.assertAlmostEqual(meta["canais"][0]["frequencia_hz"],1000,delta=.2)
        self.assertAlmostEqual(meta["canais"][1]["duty"],.5,delta=.002)
        metrics=self.app.download(job["id"],cap["id"],"medidas.csv")
        with metrics.open(newline="") as stream:self.assertEqual(len(list(csv.DictReader(stream))),2)
        for language in ("pt","en"):
            output=report(self.app.store,dict(run=job["id"],capture=cap["id"],language=language,notes="Signal acceptance"))
            path=self.app.download(job["id"],"",parse_qs(urlparse(output["url"]).query)["file"][0])
            self.assertTrue(path.read_bytes().startswith(b"%PDF"))
        self.assertEqual(self.app.history()[0]["measurement"],"sinais")
        with self.assertRaises(Problem):self.app.start(dict(mode="reanalysis",settings={},source=dict(run=job["id"],capture=cap["id"])))
        # Legacy history remains usable alongside new signal records.
        old=self.demo();self.assertEqual(self.app.detail(old["id"])["captures"][0]["metadata"]["versao_formato"],1)
        self.assertEqual(len(self.app.history()),2)

    def test_one_four_channels_preserve_and_memory_are_not_reconfigured(self):
        scope=MultiSessionScope(model="DHO914")
        cfg=dict(ip="127.0.0.1",port=scope.porta,model="DHO914",points=1000,plots=False,
                 measurement="signals",channels=[channel(n) for n in (1,2,3,4)],configuration="guided")
        try:
            self.app.connect(cfg)
            self.app.scope_action(dict(action="apply",settings=cfg))
            self.app.start(dict(mode="real",settings=cfg));job=self.wait()
            self.assertEqual(job["state"],"done",job)
            cap=self.app.detail(job["id"])["captures"][0]
            self.assertEqual(len(cap["metadata"]["canais"]),4)
            wave=self.app.waveform(job["id"],cap["id"],limit=105)
            self.assertEqual(len(wave["points"][0]),5);self.assertLessEqual(len(wave["points"]),105)
            scope.parametros[":TRIG:SWE"]="AUTO"
            for policy in ("preserve","memory"):
                start=len(scope.commands);armed=scope.armadas
                # Requested depth differs; preservation must accept the actual frozen record.
                self.app.start(dict(mode="real",settings=cfg|dict(configuration=policy,points=10000,channels=[channel(3)])))
                job=self.wait();self.assertEqual(job["state"],"done",job)
                writes=[c for c in scope.commands[start:] if "?" not in c]
                self.assertFalse(any(c.startswith((":CHAN",":TIM",":ACQ",":TRIG:EDGE")) for c in writes),writes)
                self.assertEqual(scope.armadas-armed,policy=="preserve")
                self.assertEqual(scope.parametros[":TRIG:SWE"],"AUTO")
                cap=self.app.detail(job["id"])["captures"][0]
                self.assertEqual(cap["metadata"]["pontos"],1000)
                self.assertEqual(cap["metadata"]["canais"][0]["numero"],3)
                self.assertFalse(cap["metadata"]["configuracao_aplicada"])
                self.assertEqual(cap["metadata"]["origem"],"MEMORIA_EXISTENTE" if policy=="memory" else "CAPTURA_NOVA")
        finally:scope.fechar()

    def test_preserved_transient_ac_coupling_fails_without_stale_lock(self):
        scope=MultiSessionScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False,configuration="preserve")
        try:
            self.app.connect(cfg);scope.parametros[":CHAN2:COUP"]="AC"
            self.app.start(dict(mode="real",settings=cfg));job=self.wait()
            self.assertEqual(job["state"],"error",job);self.assertIn("DC",job["message"])
            self.assertTrue(self.app.connection["connected"])
            scope.parametros[":CHAN2:COUP"]="DC"
            self.app.start(dict(mode="real",settings=cfg));self.assertEqual(self.wait()["state"],"done")
        finally:scope.fechar()

    def test_cancelling_preserved_capture_restores_trigger_sweep(self):
        scope=MultiSessionScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False,configuration="preserve",measurement="signals",channels=[channel(1)])
        try:
            self.app.connect(cfg);scope.falha="sem_disparo";scope.parametros[":TRIG:SWE"]="AUTO"
            self.app.start(dict(mode="real",settings=cfg))
            deadline=time.monotonic()+3
            while not scope.armadas and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(scope.armadas,1)
            self.app.cancel();job=self.wait()
            self.assertEqual(job["state"],"cancelled",job)
            self.assertEqual(scope.estado,"STOP")
            self.assertEqual(scope.parametros[":TRIG:SWE"],"AUTO")
        finally:scope.fechar()

    def test_hidden_signal_channel_is_rejected_without_reconfiguring(self):
        scope=MultiSessionScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False,configuration="memory",measurement="signals",channels=[channel(1)])
        try:
            self.app.connect(cfg);scope.parametros[":CHAN1:DISP"]="0"
            self.app.start(dict(mode="real",settings=cfg));job=self.wait()
            self.assertEqual(job["state"],"error",job);self.assertIn("oculto",job["message"])
            self.assertTrue(self.app.connection["connected"])
            self.assertEqual(scope.parametros[":CHAN1:DISP"],"0")
        finally:scope.fechar()

    def test_signal_failure_can_be_retried_and_profiles_store_mode(self):
        scope=MultiSessionScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False,measurement="signals",channels=[channel(1)])
        try:
            self.app.connect(cfg);scope.falha="saturado"
            self.app.start(dict(mode="real",settings=cfg));job=self.wait()
            self.assertEqual(job["state"],"error",job);self.assertTrue(self.app.connection["connected"])
            scope.falha=None
            self.app.start(dict(mode="real",settings=cfg));self.assertEqual(self.wait()["state"],"done")
            saved=self.app.save_profile(dict(name="Signal single channel",settings=cfg))
            self.assertEqual(saved["settings"]["measurement"],"signals")
            self.assertEqual(self.app.profiles.list()[0]["settings"]["channels"],[channel(1)])
        finally:scope.fechar()
