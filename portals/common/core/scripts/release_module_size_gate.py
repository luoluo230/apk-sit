# -*- coding: utf-8 -*-
"""CI gate: release order modules must stay under line budgets."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIMITS = {
    "services/release/release_order_service.py": 50,
    "services/release/order_crud.py": 400,
    "services/release/order_build_sync.py": 720,
    "services/release/order_publish_flow.py": 520,
    "services/release/channel_journey_bff.py": 650,
    "services/release/order_diagnostics.py": 450,
    "routes/commercial_release_routes.py": 150,
    "routes/project_delivery.py": 980,
    "routes/delivery/helpers.py": 160,
    "static/project_delivery.js": 2450,
    "static/delivery_common.js": 120,
}


def main() -> int:
    failures = []
    report = {}
    for rel, ceiling in LIMITS.items():
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            failures.append(f"missing: {rel}")
            continue
        with open(path, encoding="utf-8") as handle:
            count = sum(1 for _ in handle)
        ok = count <= ceiling
        report[rel] = {"lines": count, "ceiling": ceiling, "ok": ok}
        if not ok:
            failures.append(f"{rel}: {count} lines (ceiling {ceiling})")
    payload = {"ok": not failures, "files": report, "failures": failures}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
