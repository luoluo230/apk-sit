# -*- coding: utf-8 -*-
"""CI gate: bootstrap hot-update regression (fixture + unit)."""

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
            "tests/test_bootstrap_hotupdate_regression.py",
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
    )
    if proc.returncode == 0:
        print("bootstrap_hotupdate_regression_gate PASS")
    else:
        print("bootstrap_hotupdate_regression_gate FAILED")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
