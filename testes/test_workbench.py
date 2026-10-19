"""Functional workflow and protocol tests. No physical device is used here."""
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
import hashlib
import json
import socket
import tempfile
import threading
import time
import unittest

import test_interface as harness
from test_controle_rigol import MultiSessionScope
from interface.rta.common import Problem, settings
from interface.rta.profiles import ProfileStore
from interface.rta.diagnostics import evaluate
from interface.rta.instrument import Session
from interface.rta.backups import same_settings


class SetupScope(MultiSessionScope):
    def __init__(self):
        self.serial="SETUP_TEST";self.writes=0;self.fail_restore=False
        super().__init__()
    def consulta(self,command):
        if command=="*IDN?":
            return "RIGOL TECHNOLOGIES,DHO802,"+self.serial+",SIMULATED"
        if command==":SYST:SET?":
            data=json.dumps(self.parametros,sort_keys=True).encode()
            count=str(len(data)).encode()
            return b"#"+str(len(count)).encode()+count+data+b"\n"
        if command.startswith(":MEAS:ITEM?"):
            return {"VMIN,CHAN1":"4.9","VMAX,CHAN1":"5.1","VAVG,CHAN1":"5",
                    "VMIN,CHAN2":"0","VMAX,CHAN2":".21","VAVG,CHAN2":".105","VBASE,CHAN2":"0",
                    "VTOP,CHAN2":".21","FREQ,CHAN2":"1000","PDUT,CHAN2":".5"}[command.split(" ",1)[1]]
        return super().consulta(command)
    def configurar(self,command):
        if command.startswith(":SYST:SET #"):
            self.writes+=1
            packet=command.split(" #",1)[1];digits=int(packet[0])
            size=int(packet[1:1+digits]);data=packet[1+digits:].encode()
            if not self.fail_restore:
                self.parametros=json.loads(data[:size])
        else:super().configurar(command)


class Profiles(unittest.TestCase):
    def test_named_profiles_survive_restart_and_preserve_values(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ProfileStore(folder)
            row=store.save(dict(name="Fonte 12 V ação",settings=dict(nominal=12,scale_v=2,time_div=.00021)))
            self.assertEqual(ProfileStore(folder).list()[0],row)
            updated=store.save(dict(id=row["id"],name="Fonte 5 V",settings=dict(nominal=5)))
            self.assertEqual(updated["id"],row["id"])
            self.assertEqual(len(store.list()),1)
            store.delete(row["id"])
            self.assertEqual(store.list(),[])
            self.assertEqual(len(list(Path(folder).glob("*.deleted"))),1)
    def test_invalid_names_duplicate_names_and_unknown_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ProfileStore(folder);store.save(dict(name="Bench",settings={}))
            for value in ["", "a"*81,"Bad\nname"]:
                with self.assertRaises(Problem):store.save(dict(name=value,settings={}))
            for cfg in [dict(time_div=206e-6),dict(plots="false"),dict(unknown=1),dict(low_a=.2,high_a=.1)]:
                with self.assertRaises(Problem):store.save(dict(name="Other",settings=cfg))
            with self.assertRaises(Problem):store.save(dict(name="bench",settings={}))
            with self.assertRaises(Problem):store.delete("../outside")


class Workflows(harness.InterfaceHarness,unittest.TestCase):
    def test_new_mutations_reject_cross_origin_and_invalid_bodies(self):
        for route,body in [("/api/profile",dict(name="Test",settings={})),("/api/backup",{}),
                           ("/api/restore",{}),("/api/diagnose",{}),("/api/compare",{}),("/api/report",{})]:
            with self.subTest(route=route),self.assertRaises(HTTPError) as caught:
                self.request(route,body,headers={"Origin":"https://example.org"})
            self.assertEqual(caught.exception.code,403)
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/report",dict(language={}))
        self.assertEqual(caught.exception.code,400)

    def test_profile_uses_detected_model_to_preserve_dho900_limits(self):
        self.app.connection=dict(connected=True,ip="169.254.112.67",port=5555,model="DHO914")
        _,body=self.request("/api/profile",dict(name="DHO914 profile",settings=dict(model="auto",time_div=2e-9)))
        row=json.loads(body)
        self.assertEqual(row["settings"]["model"],"DHO914")
        self.assertEqual(json.loads(self.request("/api/profiles")[1])[0]["settings"]["time_div"],2e-9)

    def test_profile_routes_require_token_and_persist(self):
        with self.assertRaises(HTTPError):
            self.request("/api/profile",dict(name="Unauthorized",settings={}),token=False)
        _,body=self.request("/api/profile",dict(name="Named profile",settings=dict(resistor=.5)))
        row=json.loads(body)
        self.assertEqual(json.loads(self.request("/api/profiles")[1])[0]["settings"]["resistor"],.5)
        self.assertEqual(json.loads(self.request("/api/profile/delete",dict(id=row["id"]))[1]),dict(deleted=True))

    def test_reanalysis_uses_original_samples_without_contacting_scope(self):
        original=self.demo()
        file=self.app.download(original["id"],"captura_001","amostras.csv")
        original_hash=hashlib.sha256(file.read_bytes()).hexdigest()
        with mock.patch("interface.rta.service.scope_query",side_effect=AssertionError("Reanalysis contacted scope")),mock.patch("interface.rta.service.read_scope",side_effect=AssertionError("Reanalysis controlled scope")):
            self.app.start(dict(mode="reanalysis",settings=dict(plots=False,tolerance_v=.02),
                                source=dict(run=original["id"],capture="captura_001")))
            derived=self.wait()
        self.assertEqual(derived["state"],"done",derived)
        self.assertNotEqual(derived["id"],original["id"])
        result=self.app.detail(derived["id"])
        self.assertEqual(result["captures"][0]["metadata"]["origem"],"ARQUIVO")
        self.assertEqual(result["captures"][0]["metadata"]["tolerancia_v"],.02)
        self.assertEqual(result["provenance"]["sha256"],original_hash)
        self.assertEqual(result["provenance"]["metadata"]["origem"],"SIMULACAO")
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),original_hash)

    def test_reanalysis_rejects_reinterpretation_of_already_converted_current(self):
        job=self.demo()
        with self.assertRaises(Problem):
            self.app.start(dict(mode="reanalysis",settings=dict(resistor=.5),
                                source=dict(run=job["id"],capture="captura_001")))

    def test_reanalysis_rejects_unknown_or_traversing_source(self):
        for source in [{},None,dict(run="../outside",capture="captura_001")]:
            with self.assertRaises(Problem):
                self.app.start(dict(mode="reanalysis",source=source))
        self.assertIsNone(self.app.job)

    def test_comparison_alignment_differences_and_direction_validation(self):
        job=self.demo(2);detail=self.app.detail(job["id"])
        items=[]
        for capture in detail["captures"]:
            event=next(e for e in capture["events"] if e["status"]=="valido" and e["direcao"]=="subida")
            items.append(dict(run=job["id"],capture=capture["id"],event=int(event["evento"])))
        data=self.app.compare(dict(items=items))
        self.assertTrue(data["criteria_match"])
        self.assertTrue(all(row["points"][0][0]<0<row["points"][-1][0] for row in data["rows"]))
        self.assertEqual(data["rows"][0]["difference"]["afundamento_v"],0)
        expected=data["rows"][1]["metrics"]["afundamento_v"]-data["rows"][0]["metrics"]["afundamento_v"]
        self.assertAlmostEqual(data["rows"][1]["difference"]["afundamento_v"],expected)
        bad=next(e for e in detail["captures"][0]["events"] if e["status"]=="valido" and e["direcao"]=="descida")
        items[0]["event"]=int(bad["evento"])
        with self.assertRaises(Problem):self.app.compare(dict(items=items))
        with self.assertRaises(Problem):self.app.compare(dict(items=items[:1]))

    def test_pdf_is_downloadable_in_both_languages_and_original_unchanged(self):
        try:import reportlab
        except ImportError:self.skipTest("PDF dependencies unavailable")
        job=self.demo();source=self.app.download(job["id"],"captura_001","amostras.csv")
        digest=hashlib.sha256(source.read_bytes()).digest()
        names=[]
        for language in ["pt","en"]:
            _,body=self.request("/api/report",dict(run=job["id"],capture="captura_001",language=language,
                notes="Observação <not markup> & next\n"+"long notes "*90))
            result=json.loads(body);names.append(result["file"])
            code,pdf=self.request(result["url"])
            self.assertEqual(code,200);self.assertTrue(pdf.startswith(b"%PDF-"));self.assertGreater(len(pdf),10000)
        self.assertNotEqual(names[0],names[1])
        self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),digest)
        for data in [dict(language="de"),dict(notes="x"*4001),dict(notes="\x00")]:
            with self.assertRaises(Problem):
                self.app.report(dict(run=job["id"],capture="captura_001",**data))

    def test_reanalysis_report_retains_origin_instrument_and_analysis_timestamp_label(self):
        from interface.rta.reports import report_context
        source=dict(origem="CAPTURA_NOVA",instrumento="RIGOL TECHNOLOGIES,DHO802,ORIGINAL,1")
        capture=dict(metadata=dict(origem="ARQUIVO",instrumento="Reanalise de CSV; nenhuma captura nova"))
        context=report_context(dict(provenance=dict(metadata=source)),capture,"en")
        self.assertEqual(context["instrument"],source["instrumento"])
        self.assertEqual(context["date_label"],"Analysis timestamp (UTC)")
        context=report_context(dict(provenance=dict(metadata=capture["metadata"],root_metadata=source)),capture,"pt")
        self.assertEqual(context["instrument"],source["instrumento"])
        self.assertEqual(context["date_label"],"Instante da análise (UTC)")

    def test_report_routes_cannot_read_arbitrary_files(self):
        job=self.demo()
        for path in ["reports/../../outside.pdf","reports/unknown.pdf"]:
            with self.assertRaises(Problem):self.app.download(job["id"],"",path)


class SetupControls(harness.InterfaceHarness,unittest.TestCase):
    def setUp(self):
        super().setUp();self.instrument=SetupScope()
        self.cfg=dict(ip="127.0.0.1",port=self.instrument.porta,plots=False)
        self.app.connect(self.cfg)
    def tearDown(self):
        try:super().tearDown()
        finally:self.instrument.fechar()
    def test_backup_restore_preserves_parameters_and_creates_recovery(self):
        backup=self.app.backup(dict(settings=self.cfg))
        original=self.app.backups.path(backup["id"])/"setup.bin"
        digest=hashlib.sha256(original.read_bytes()).hexdigest()
        self.instrument.parametros[":CHAN1:SCAL"]="2"
        result=self.app.restore(dict(settings=self.cfg,id=backup["id"]))
        self.assertEqual(result["snapshot"]["channels"][0]["scale_v"],.5)
        self.assertEqual(self.instrument.writes,1)
        self.assertEqual(len(self.app.backups.list()),2)
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),digest)
    def test_corrupted_backup_and_other_serial_are_refused_before_writes(self):
        backup=self.app.backup(dict(settings=self.cfg))
        self.instrument.serial="OTHER"
        with self.assertRaises(Problem):self.app.restore(dict(settings=self.cfg,id=backup["id"]))
        self.assertEqual(self.instrument.writes,0)
        self.instrument.serial="SETUP_TEST"
        path=self.app.backups.path(backup["id"])/"setup.bin";path.write_bytes(b"corrupted")
        with self.assertRaises(Problem):self.app.restore(dict(settings=self.cfg,id=backup["id"]))
        self.assertEqual(self.instrument.writes,0)
    def test_restore_mismatch_keeps_recovery_and_releases_lock(self):
        backup=self.app.backup(dict(settings=self.cfg))
        self.instrument.parametros[":CHAN1:SCAL"]="2";self.instrument.fail_restore=True
        with self.assertRaises(Problem) as caught:self.app.restore(dict(settings=self.cfg,id=backup["id"]))
        self.assertIn("Recovery backup:",str(caught.exception))
        self.assertEqual(len(self.app.backups.list()),2)
        self.assertFalse(self.app.scope["busy"])
    def test_diagnostics_are_read_only_and_unavailable_is_inconclusive(self):
        start=len(self.instrument.commands)
        result=self.app.diagnose(dict(settings=self.cfg))
        self.assertTrue(all("?" in cmd for cmd in self.instrument.commands[start:]))
        self.assertTrue(any(c["code"]=="switching" for c in result["checks"]))
        values={key:None for key in result["measurements"]}
        unavailable=evaluate(result["state"],values,settings(self.cfg))
        self.assertFalse(unavailable["ready"])
        self.assertTrue(any(c["code"]=="switching_unconfirmed" for c in unavailable["checks"]))
        bad=dict(result["measurements"],base2=.2,top2=.41)
        self.assertTrue(any(c["code"]=="thresholds" for c in evaluate(result["state"],bad,settings(self.cfg))["checks"]))
    def test_short_duty_plateau_and_unknown_duty_are_reported(self):
        result=self.app.diagnose(dict(settings=self.cfg))
        cfg=settings(self.cfg)
        for duty,code in [(.1,"short_plateau"),(None,"duty_unknown")]:
            evaluated=evaluate(result["state"],result["measurements"]|dict(duty2=duty),cfg)
            self.assertTrue(any(row["code"]==code for row in evaluated["checks"]))

    def test_opt_in_backup_precedes_acquisition(self):
        original=self.instrument.parametros[":CHAN1:SCAL"]
        self.app.start(dict(mode="real",settings=self.cfg|dict(points=1000),backup=True))
        job=self.wait()
        self.assertEqual(job["state"],"done",job)
        self.assertTrue(job["backup_id"])
        saved=self.app.backups.path(job["backup_id"])/"setup.bin"
        self.assertEqual(json.loads(saved.read_bytes())[":CHAN1:SCAL"],original)
        self.assertLess(self.instrument.commands.index(":SYST:SET?"),self.instrument.commands.index(":SING"))

    def test_scope_operations_exclude_restore_backup_and_diagnostics(self):
        self.app.scope["busy"]=True
        for action in [self.app.backup,self.app.diagnose,lambda data:self.app.restore(data|dict(id="a"*32))]:
            with self.assertRaises(Problem):action(dict(settings=self.cfg))
        self.assertEqual(self.instrument.writes,0)


class BinaryTransfer(unittest.TestCase):
    def exchange(self,reply,maximum=2048):
        listener=socket.socket();listener.bind(("127.0.0.1",0));listener.listen(1)
        def send():
            try:
                connection,_=listener.accept()
                with connection:
                    connection.recv(128)
                    for byte in reply:
                        connection.sendall(bytes([byte]))
            except OSError:pass
            finally:listener.close()
        thread=threading.Thread(target=send);thread.start()
        try:
            with Session("127.0.0.1",listener.getsockname()[1],2) as session:
                return session.block(":SYST:SET?",maximum)
        finally:thread.join(3)
    def test_fragmented_binary_payload_can_contain_lf(self):
        data=b"line1\nline2\r\n#123"
        length=str(len(data)).encode()
        self.assertEqual(self.exchange(b"#"+str(len(length)).encode()+length+data+b"\n"),data)
    def test_invalid_headers_lengths_payloads_and_terminators_are_rejected(self):
        for reply in [b"#0\n",b"#x\n",b"#2xx",b"#510000",b"#15abc",b"#13abcX"]:
            with self.subTest(reply=reply),self.assertRaises((Problem,OSError)):
                self.exchange(reply,100)
