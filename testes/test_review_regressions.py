"""Regressions found by the complete review; protocol fixtures are not hardware."""
from pathlib import Path
from unittest import mock
import json
import tempfile
import csv
import hashlib
import math
import subprocess
import unittest
from urllib.error import HTTPError

from test_interface import InterfaceHarness
from test_workbench import SetupScope
from test_flexible_capture import NoEdgeScope
from interface.rta.common import Problem, settings
from interface.rta.models import OFFSET_LIMITS, offset_limit
from interface.rta.reports import trigger_notice
from interface.rta.profiles import ProfileStore

class ReviewContracts(unittest.TestCase):
    def test_offset_limits_match_every_probe_and_boundary(self):
        for probe in (1, 10):
            for scale, expected in ((.0002,.5),(.0005,1),(.065,1),(.06501,8),(.26,8),(.26001,20),(2.65,20),(2.6501,100),(10,100)):
                with self.subTest(probe=probe, scale=scale):
                    self.assertEqual(offset_limit(scale*probe,probe),expected*probe)
            for scale, center in ((.001,1),(.1,8),(1,20),(3,100)):
                channel=dict(number=1,probe=probe,scale=scale*probe,center=center*probe,coupling="DC",bandwidth="20M")
                settings(dict(measurement="signals",channels=[channel],trigger=dict(source=1,level=center*probe,slope="POS")))
                with self.assertRaises(Problem):
                    settings(dict(measurement="signals",channels=[channel|dict(center=(center+.01)*probe)]))
        self.assertEqual(len(OFFSET_LIMITS),5)

    def test_forced_trigger_report_warning_is_bilingual_and_conditional(self):
        self.assertIn("without a signal edge",trigger_notice(dict(disparo_forcado=True),"en"))
        self.assertIn("sem uma borda",trigger_notice(dict(disparo_forcado=True),"pt"))
        self.assertEqual(trigger_notice({},"en"),"")

    def test_malformed_profiles_do_not_hide_valid_profiles_or_destroy_files(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ProfileStore(folder)
            row=store.save(dict(name="Healthy",settings={}))
            damaged=Path(folder)/("a"*32+".json")
            for value in (None,[],1,{},dict(id="a"*32,name=None),dict(id="a"*32,name=17,updated_at="now",settings={})):
                damaged.write_text(json.dumps(value))
                self.assertEqual(store.list(),[row])
                self.assertTrue(damaged.exists())

class ReviewWorkflows(InterfaceHarness,unittest.TestCase):
    def test_same_model_swapped_serial_blocks_every_instrument_write(self):
        scope=SetupScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False)
        try:
            self.app.connect(cfg)
            previous=self.app.connection.copy()
            scope.serial="DIFFERENT_SERIAL"
            for action in ("read","run","stop","apply","autoset"):
                self.app.connection=previous.copy()
                start=len(scope.commands)
                with self.subTest(action=action),self.assertRaises(Problem) as caught:
                    self.app.scope_action(dict(action=action,settings=cfg))
                self.assertEqual(caught.exception.status,409)
                self.assertFalse(self.app.connection["connected"])
                self.assertTrue(all(command=="*IDN?" for command in scope.commands[start:]))
            for action in (self.app.diagnose,self.app.backup):
                self.app.connection=previous.copy()
                start=len(scope.commands)
                with self.assertRaises(Problem):action(dict(settings=cfg))
                self.assertEqual(scope.commands[start:],["*IDN?"])
            self.app.connection=previous.copy()
            start=len(scope.commands)
            self.app.start(dict(mode="real",settings=cfg))
            job=self.wait()
            self.assertEqual(job["state"],"error",job)
            self.assertIn("identidade",job["message"])
            self.assertTrue(all(command=="*IDN?" for command in scope.commands[start:]))
            self.assertFalse(self.app.connection["connected"])
        finally:scope.fechar()

    def test_guided_signal_failure_stops_and_retry_succeeds(self):
        scope=NoEdgeScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False,
                 measurement="signals",require_edge=True,timeout=.4)
        try:
            self.app.connect(cfg)
            self.app.start(dict(mode="real",settings=cfg))
            self.assertEqual(self.wait()["state"],"error")
            self.assertEqual(scope.estado,"STOP")
            self.assertFalse(scope.pendente)
            cfg["require_edge"]=False
            self.app.start(dict(mode="real",settings=cfg))
            self.assertEqual(self.wait()["state"],"done")
            self.assertEqual(scope.estado,"STOP")
        finally:scope.fechar()

    def test_reanalysis_ignores_hardware_drafts_and_uses_source_roles(self):
        original=self.demo()
        for change in (dict(scale_v=.00001),dict(time_div=.000206),
                       dict(measurement="signals",model="DHO914",channels=[]),
                       dict(ip="bad",trigger=dict(source=2,level=99,slope="POS"))):
            with self.subTest(change=change),mock.patch("interface.rta.service.scope_query",side_effect=AssertionError("Hardware contact")):
                self.app.start(dict(mode="reanalysis",settings=dict(plots=False,**change),
                                    source=dict(run=original["id"],capture="captura_001")))
                job=self.wait()
                self.assertEqual(job["state"],"done",job)
                self.assertEqual(self.app.detail(job["id"])["captures"][0]["metadata"]["canais_solicitados"],[1,2])

    def test_comparison_preserves_the_exported_voltage_change(self):
        job=self.demo()
        cap=self.app.detail(job["id"])["captures"][0]
        event=next(e for e in cap["events"] if e["status"]=="valido")
        item=dict(run=job["id"],capture=cap["id"],event=int(event["evento"]))
        compared=self.app.compare(dict(items=[item,item]))
        self.assertEqual(compared["rows"][0]["metrics"]["delta_v"],event["delta_v"])
        self.assertEqual(compared["rows"][1]["difference"]["delta_v"],0)

    def test_corrupt_profile_http_route_still_returns_valid_rows(self):
        row=self.app.save_profile(dict(name="Healthy",settings={}))
        (self.app.profiles.directory/("a"*32+".json")).write_text("null")
        self.assertEqual(json.loads(self.request("/api/profiles")[1]),[row])

    def test_unexpected_http_error_is_structured_and_service_stays_alive(self):
        with mock.patch.object(self.app,"history",side_effect=RuntimeError("Test failure")),self.assertLogs(level="ERROR"):
            with self.assertRaises(HTTPError) as caught:self.request("/api/history")
            self.assertEqual(caught.exception.code,500)
        self.assertEqual(self.request("/api/status")[0],200)


class LargeRecordReview(InterfaceHarness,unittest.TestCase):
    def make_record(self, noisy=False, plots=False):
        source=self.path/"input.csv"
        count=20000 if noisy else 60000
        with source.open("w") as stream:
            stream.write("tempo_s,tensao_v,corrente_a\n")
            for k in range(count):
                current=.2 if (k%2 if noisy else k%200<100) else 0
                stream.write(f"{k*(1e-8 if noisy else 5e-6):.17g},{5-current*.2:.17g},{current:.17g}\n")
        output=self.app.results/"large"
        command=[str(self.app.executable),"--entrada",str(source),"--saida",str(output)]
        if plots:command.append("--graficos")
        from interface.rta.runtime import process_environment,hidden_process
        result=subprocess.run(command,capture_output=True,text=True,encoding="utf-8",
                              env=process_environment(),timeout=90,**hidden_process())
        self.assertIn(result.returncode,(0,2),result.stderr)
        return result,output

    def test_large_noisy_record_keeps_csv_and_bounds_http_event_pages_and_logs(self):
        result,output=self.make_record(noisy=True)
        detail=self.app.detail("large")
        capture=detail["captures"][0]
        self.assertEqual(capture["event_count"],19999)
        self.assertEqual(len(capture["events"]),200)
        self.assertLess(len(result.stdout.splitlines()),230)
        _,body=self.request("/api/events?run=large&capture=captura_001&offset=200")
        page=json.loads(body)
        self.assertEqual(page["offset"],200)
        self.assertEqual(page["events"][0]["evento"],201)
        self.assertEqual(len(page["events"]),200)
        self.assertLess(len(body),160000)
        with (output/"captura_001/eventos.csv").open() as stream:
            self.assertEqual(sum(1 for _ in csv.DictReader(stream)),19999)
        self.assertEqual(self.app.store.event("large","captura_001",19999)["evento"],19999)
        for suffix in ("&offset=-1","&limit=201","&capture=../outside"):
            with self.assertRaises(HTTPError):self.request("/api/events?run=large&capture=captura_001"+suffix)

    def test_comparison_can_select_valid_events_beyond_the_first_page(self):
        self.make_record()
        event=self.app.store.event("large","captura_001",250)
        self.assertEqual(event["status"],"valido")
        item=dict(run="large",capture="captura_001",event=250)
        result=self.app.compare(dict(items=[item,item]))
        self.assertEqual(result["rows"][0]["event"],250)
        self.assertEqual(result["rows"][0]["metrics"]["delta_v"],event["delta_v"])
        page=json.loads(self.request("/api/events?run=large&capture=captura_001&valid=1&offset=200")[1])
        self.assertEqual(len(page["events"]),200)
        self.assertTrue(all(e["status"]=="valido" for e in page["events"]))

    def test_png_export_is_bounded_and_preserves_the_full_capture(self):
        _,output=self.make_record(plots=True)
        folder=output/"captura_001"
        meta=json.loads((folder/"metadados.json").read_text())
        manifest=json.loads((folder/"graficos/graficos.json").read_text())
        self.assertGreater(meta["bordas"],500)
        self.assertEqual(manifest["limite_graficos_eventos"],20)
        self.assertEqual(manifest["graficos_eventos"],20)
        self.assertEqual(len(list((folder/"graficos").glob("*.png"))),21)
        self.assertEqual(manifest["eventos_total"],meta["bordas"])
        self.assertEqual(manifest["eventos_sem_png"],meta["bordas"]-20)
        with (folder/"amostras.csv").open() as stream:
            self.assertEqual(sum(1 for _ in stream)-1,60000)

    def test_forced_capture_warning_is_present_in_the_rendered_pdf(self):
        from reportlab.platypus import Paragraph
        scope=NoEdgeScope()
        cfg=dict(ip="127.0.0.1",port=scope.porta,points=1000,plots=False,measurement="signals",configuration="preserve",timeout=.8)
        try:
            self.app.connect(cfg);self.app.start(dict(mode="real",settings=cfg))
            job=self.wait();self.assertEqual(job["state"],"done",job)
            with mock.patch("reportlab.platypus.Paragraph",wraps=Paragraph) as paragraph:
                result=self.app.report(dict(run=job["id"],capture="captura_001",language="en"))
            self.assertTrue(any("Forced trigger:" in str(call.args[0]) for call in paragraph.call_args_list))
            self.assertTrue(self.app.download(job["id"],"","reports/"+result["file"]).read_bytes().startswith(b"%PDF"))
        finally:scope.fechar()

    def test_native_core_rejects_invalid_offset_before_sending_settings(self):
        scope=SetupScope()
        try:
            result=subprocess.run([str(self.app.executable),"--tipo","sinais","--canal","1:1:.001:5:DC:20M",
                "--disparo-v","5","--porta",str(scope.porta),"127.0.0.1"],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,1)
            self.assertIn("offset",result.stderr)
            self.assertEqual(scope.commands,["*IDN?"])
        finally:scope.fechar()


class StartupAndDataReview(unittest.TestCase):
    def test_launcher_reports_state_directory_failure_and_quiet_mode(self):
        import importlib.util
        import sys
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location("review_launcher",root/"packaging/windows/launcher.py")
        launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        for quiet in (False,True):
            with mock.patch.object(launcher,"state_dir",side_effect=PermissionError("blocked")),mock.patch.object(launcher,"message") as popup, mock.patch.object(sys,"argv",["rta"]+(["--quiet"] if quiet else [])):
                self.assertEqual(launcher.main(),1)
                self.assertEqual(popup.call_count,not quiet)
                if not quiet:self.assertIn("blocked",popup.call_args.args[0])

class BackupDataReview(InterfaceHarness,unittest.TestCase):
    def test_corrupt_backup_state_is_rejected_before_any_instrument_command(self):
        scope=SetupScope();cfg=dict(ip="127.0.0.1",port=scope.porta)
        try:
            self.app.connect(cfg);backup=self.app.backup(dict(settings=cfg))
            path=self.app.backups.path(backup["id"])/"metadata.json"
            row=json.loads(path.read_text());row["state"]={};path.write_text(json.dumps(row))
            start=len(scope.commands)
            with self.assertRaises(Problem):self.app.restore(dict(settings=cfg,id=backup["id"]))
            self.assertEqual(scope.commands[start:],[])
            self.assertEqual(self.app.backups.list(),[])
            self.assertTrue(path.exists())
        finally:scope.fechar()
