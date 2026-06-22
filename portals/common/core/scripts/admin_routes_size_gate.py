# -*- coding: utf-8 -*-
"""CI gate: admin_routes.py must stay under a shrinking line budget (T-C02)."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ADMIN_ROUTES = os.path.join(ROOT, "routes", "admin_routes.py")
# Target per plan: 800. Staged ceiling via env until extraction completes.
DEFAULT_MAX = int(os.environ.get("ADMIN_ROUTES_TARGET_LINES", "800"))
STAGE_MAX = int(os.environ.get("ADMIN_ROUTES_MAX_LINES", "800"))


def main() -> int:
    if not os.path.isfile(ADMIN_ROUTES):
        print(json.dumps({"ok": False, "error": "admin_routes.py missing"}))
        return 1
    with open(ADMIN_ROUTES, encoding="utf-8") as handle:
        line_count = sum(1 for _ in handle)
    ceiling = STAGE_MAX if STAGE_MAX > 0 else DEFAULT_MAX
    ok = line_count <= ceiling
    payload = {
        "ok": ok,
        "line_count": line_count,
        "ceiling": ceiling,
        "target": DEFAULT_MAX,
        "file": ADMIN_ROUTES,
    }
    print(json.dumps(payload, ensure_ascii=False))
    if not ok:
        print(
            f"FAIL: admin_routes.py has {line_count} lines (ceiling {ceiling})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
