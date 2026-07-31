#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI gate: version module files must stay under line budget."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "services", "admin")
MAX_LINES = int(os.environ.get("VERSION_MODULE_MAX_LINES", "460"))
FILES = [
    "version_service.py",
    "version_constants.py",
    "version_row_helpers.py",
    "version_propagation.py",
    "version_group_service.py",
    "version_download_service.py",
    "version_runtime_service.py",
    "version_crud_service.py",
    "version_group_repo.py",
    "version_pipeline_resolver.py",
    "version_domain.py",
]


def main() -> int:
    failures = []
    report = {}
    for name in FILES:
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            failures.append(f"missing {name}")
            continue
        with open(path, encoding="utf-8") as handle:
            count = sum(1 for _ in handle)
        report[name] = count
        if count > MAX_LINES:
            failures.append(f"{name}: {count} > {MAX_LINES}")
    payload = {"ok": not failures, "max_lines": MAX_LINES, "files": report, "failures": failures}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
