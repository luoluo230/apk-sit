# -*- coding: utf-8 -*-
"""CI gate: Server Management Hub in-process E2E."""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e/test_server_management_hub_e2e.py::ServerManagementHubE2ETests",
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
    )
    if proc.returncode == 0:
        print("server_management_hub_e2e_gate PASS")
    else:
        print("server_management_hub_e2e_gate FAILED")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
