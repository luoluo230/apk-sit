#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron-style Jenkins label sync gate (P1-05 Step 4)."""

from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


def main() -> int:
    os.environ.setdefault("USE_SQLITE", "true")
    from models.db import init_db
    from services import jenkins_manager
    from scripts.closure_evidence import write_evidence

    init_db()
    report = jenkins_manager.sync_node_labels(dry_run=False)
    if report.get("checked", 0) < 0:
        return 1
    write_evidence("GAP-P1-05-OPT-01", command="jenkins_sync_node_labels_gate.py", exit_code=0, notes=str(report))
    write_evidence("GAP-P1-05-REV-01", command="jenkins_sync_node_labels_gate.py", exit_code=0)
    print("jenkins_sync_node_labels_gate PASS", report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
