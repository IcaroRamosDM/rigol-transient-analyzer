"""Execute production UI state/render code with controlled API and DOM fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class JobInterface(unittest.TestCase):
    def test_failed_acquisition_recovers_without_locking_ui(self):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for UI behavior checks")
        sources = {name: (ROOT / "interface/static/modules" / (name + ".js")).read_text(encoding="utf-8")
                   for name in ("core", "jobs")}
        script = "const sources = " + json.dumps(sources) + ";\n"
        script += (ROOT / "testes/ui_jobs.mjs").read_text(encoding="utf-8")
        result = subprocess.run([node, "--experimental-vm-modules", "--input-type=module"],
                                input=script.encode(), capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertIn("UI recovery checks passed", result.stdout.decode())


if __name__ == "__main__":
    unittest.main()
