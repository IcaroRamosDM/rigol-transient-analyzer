"""UI contract: visible validation, unique IDs and workflow assets."""
from html.parser import HTMLParser
from pathlib import Path
import json, os, re, shutil, subprocess, unittest
ROOT=Path(__file__).resolve().parents[1]
class WorkflowTests(unittest.TestCase):
    def test_html_controls_are_unique_and_scripts_reference_existing_controls(self):
        ids=[]
        class Parser(HTMLParser):
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if "id" in attrs:ids.append(attrs["id"])
        Parser().feed((ROOT/"interface/static/index.html").read_text())
        self.assertEqual(len(ids),len(set(ids)))
        referenced=set()
        for f in (ROOT/"interface/static").rglob("*.js"):
            referenced.update(re.findall(r'\$\("([A-Za-z][A-Za-z0-9]+)"\)',f.read_text()))
        self.assertEqual(referenced-set(ids),set())

    def test_invalid_hidden_step_is_revealed_and_demo_does_not_require_network(self):
        node=os.environ.get("NODE") or shutil.which("node")
        if not node:self.skipTest("Node.js required")
        src=(ROOT/"interface/static/modules/workflow.js").read_text()
        test=(ROOT/"testes/ui_workflow.mjs").read_text()
        script="const source="+json.dumps(src)+";\n"+test
        r=subprocess.run([node,"--experimental-vm-modules","--input-type=module"],input=script.encode(),capture_output=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr.decode(errors="replace"))
        self.assertIn(b"checks passed",r.stdout)

    def test_chart_pointer_does_not_throw_in_either_measurement_mode(self):
        node=os.environ.get("NODE") or shutil.which("node")
        if not node:self.skipTest("Node.js required")
        src=(ROOT/"interface/static/modules/chart.js").read_text()
        script="const source="+json.dumps(src)+";\n"+(ROOT/"testes/ui_chart.mjs").read_text()
        result=subprocess.run([node,"--experimental-vm-modules","--input-type=module"],input=script.encode(),capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
        self.assertIn(b"checks passed",result.stdout)
