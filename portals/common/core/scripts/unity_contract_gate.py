# -*- coding: utf-8 -*-
"""CI gate: Unity contract bridge manifest + fixture validation."""

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
            "tests/test_unity_contract_bridge.py",
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
    )
    if proc.returncode == 0:
        manifest_path = os.path.join(ROOT, "tests", "fixtures", "unity_contract_manifest.json")
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from services.release.unity_contract_bridge import export_manifest

        export_manifest(manifest_path)
        sync_proc = subprocess.run(
            [sys.executable, "scripts/sync_unity_contract_manifest.py", "--local-only"],
            cwd=ROOT,
        )
        if sync_proc.returncode != 0:
            print("unity_contract_gate FAILED (sync)")
            return sync_proc.returncode
        print("unity_contract_gate PASS")
    else:
        print("unity_contract_gate FAILED")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
