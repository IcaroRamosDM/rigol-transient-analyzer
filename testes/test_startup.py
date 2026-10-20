"""Startup, port ownership and restart regressions; no instrument operations."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import interface.servidor as ui
from interface.rta.http import server
from interface.rta.instance import InstanceLock, stop_running

class StartupTests(unittest.TestCase):
    def fake_lock(self):
        lock=mock.Mock(spec=InstanceLock)
        lock.directory=Path(tempfile.gettempdir())
        lock.acquire.return_value=True
        return lock

    def test_http_listener_cannot_share_an_existing_port(self):
        first=server(object(),0)
        second=None
        try:
            with self.assertRaises(OSError):
                second=server(object(),first.server_port)
        finally:
            if second:second.server_close()
            first.server_close()

    def test_publishing_failure_closes_the_listener_before_showing_an_error(self):
        listener=server(object(),0)
        lock=self.fake_lock()
        lock.publish.side_effect=PermissionError("metadata blocked")
        with mock.patch.object(ui,"InstanceLock",return_value=lock), mock.patch.object(ui,"App"), \
             mock.patch.object(ui,"server",return_value=listener), mock.patch.object(sys,"argv",["rta","--no-browser"]):
            try:
                with self.assertRaises(PermissionError):ui.main()
                self.assertEqual(listener.socket.fileno(),-1,"A failed startup must not leave a listening port")
                lock.close.assert_called_once()
            finally:listener.server_close()

    def test_restart_takes_ownership_after_previous_process_exits(self):
        lock=self.fake_lock()
        lock.acquire.side_effect=[False,True]
        lock.discover.return_value=None
        listener=mock.Mock(server_port=12345)
        with mock.patch.object(ui,"InstanceLock",return_value=lock), mock.patch.object(ui,"App"), \
             mock.patch.object(ui,"server",return_value=listener), mock.patch.object(sys,"argv",["rta","--no-browser"]):
            ui.main()
        self.assertEqual(lock.acquire.call_count,2)
        listener.serve_forever.assert_called_once()
        listener.server_close.assert_called_once()
        lock.close.assert_called_once()

    def test_second_open_reuses_existing_instance(self):
        lock=self.fake_lock()
        lock.acquire.return_value=False
        lock.discover.return_value=("http://127.0.0.1:12345",{})
        with mock.patch.object(ui,"InstanceLock",return_value=lock), mock.patch.object(ui,"App") as app, \
             mock.patch.object(ui,"server") as start, mock.patch.object(ui,"open_browser") as browser, \
             mock.patch.object(sys,"argv",["rta"]):
            ui.main()
        browser.assert_called_once_with("http://127.0.0.1:12345")
        app.assert_not_called()
        start.assert_not_called()

    def test_shutdown_waits_for_previous_owner_to_release_the_lock(self):
        lock=self.fake_lock()
        lock.discover.return_value=None
        lock.acquire.side_effect=[False,True]
        with mock.patch("interface.rta.instance.InstanceLock",return_value=lock):
            self.assertEqual(stop_running(),0)
        self.assertEqual(lock.acquire.call_count,2)
        lock.close.assert_called_once()

    def test_malformed_instance_metadata_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            lock=InstanceLock(folder)
            for value in [None,[],1,{"url":None},{"url":{}},{"url":"http://localhost:99999"}]:
                with self.subTest(value=value):
                    lock.metadata.write_text(json.dumps(value),encoding="utf-8")
                    self.assertIsNone(lock.discover())

    def test_instance_lock_excludes_an_independent_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(__file__).resolve().parents[1]
            child="import sys;sys.path.insert(0,sys.argv[1]);from interface.rta.instance import InstanceLock;l=InstanceLock(sys.argv[2]);print(l.acquire());l.close()"
            lock=InstanceLock(folder)
            try:
                self.assertTrue(lock.acquire())
                result=subprocess.run([sys.executable,"-c",child,str(root),folder],capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),"False")
            finally:lock.close()
            result=subprocess.run([sys.executable,"-c",child,str(root),folder],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),"True")


    def test_publish_retries_a_transient_windows_sharing_violation(self):
        with tempfile.TemporaryDirectory() as folder:
            lock=InstanceLock(folder)
            original=Path.replace
            attempts=[]
            def replace(path,target):
                attempts.append(path)
                if len(attempts)==1:raise PermissionError("File temporarily in use")
                return original(path,target)
            with mock.patch.object(Path,"replace",replace):
                lock.publish("http://127.0.0.1:12345","ready")
            self.assertEqual(len(attempts),2)
            self.assertEqual(json.loads(lock.metadata.read_text(encoding="utf-8"))["instance"],"ready")


    def test_completed_http_requests_do_not_prevent_reusing_the_same_port(self):
        import threading
        from urllib.request import urlopen
        from interface.rta.service import App
        with tempfile.TemporaryDirectory() as folder:
            app=App(results=Path(folder)/"results")
            port=0
            for _ in range(15):
                listener=server(app,port);port=listener.server_port
                thread=threading.Thread(target=listener.serve_forever,daemon=True);thread.start()
                try:
                    with urlopen("http://127.0.0.1:"+str(port)+"/api/status",timeout=2) as response:
                        self.assertIn("instance",json.load(response))
                finally:
                    listener.shutdown();listener.server_close();thread.join(2)
