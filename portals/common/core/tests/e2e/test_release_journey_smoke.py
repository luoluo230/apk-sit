# -*- coding: utf-8 -*-
"""Optional smoke test hook for release journey chain (bootstrap gate script)."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest


@unittest.skipUnless(
    os.environ.get("RUN_RELEASE_JOURNEY_SMOKE") in ("1", "true", "yes"),
    "set RUN_RELEASE_JOURNEY_SMOKE=1 to run live smoke",
)
class ReleaseJourneySmokeTests(unittest.TestCase):
    def test_bootstrap_gate_e2e_script(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        script = os.path.join(root, "scripts", "bootstrap_gate_e2e.py")
        proc = subprocess.run([sys.executable, script], cwd=root, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
