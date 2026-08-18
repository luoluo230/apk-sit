# -*- coding: utf-8 -*-
"""CI gate: client/server framework alignment + deploy packs + server release."""

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
            "tests/test_framework_alignment_gate.py",
            "tests/test_server_framework_modules.py",
            "tests/test_server_management_hub.py",
            "tests/test_server_release.py",
            "tests/test_order_state_machine.py",
            "tests/test_coordinated_rollback.py",
            "tests/test_batch_rollback.py",
            "tests/test_jenkins_build_linkage.py",
            "tests/test_coordinated_publish_approval_integration.py",
            "tests/test_bootstrap_hotupdate_regression.py",
            "tests/test_server_deploy_notify.py",
            "tests/test_server_framework_gating.py",
            "tests/test_unity_contract_bridge.py",
            "tests/test_baas_public_api.py",
            "tests/test_baas_standalone.py",
            "tests/test_baas_auth.py",
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
    )
    if proc.returncode == 0:
        print("framework_alignment_gate PASS")
    else:
        print("framework_alignment_gate FAILED")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
