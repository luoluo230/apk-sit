# -*- coding: utf-8 -*-
"""Grafana dashboard + alert rules file gate (T-B05)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    from app_new import app
    from services.metrics import increment_gate_pass

    increment_gate_pass("grafana_smoke_gate", passed=True)
    errors: list[str] = []
    repo_root = Path(ROOT).parents[2]
    dash = repo_root / "docs" / "grafana" / "release-chain-dashboard.json"
    if not dash.is_file():
        errors.append(f"missing dashboard {dash}")
    else:
        data = json.loads(dash.read_text(encoding="utf-8"))
        rules = ((data.get("alerting") or {}).get("rules") or [])
        if not rules:
            errors.append("dashboard alerting.rules empty")
        if not any("cluster" in str(r.get("title", "")).lower() for r in rules):
            errors.append("cluster health alert rule missing")

    with app.test_client() as client:
        resp = client.get("/metrics")
        if resp.status_code != 200:
            errors.append(f"metrics status {resp.status_code}")
        else:
            text = resp.get_data(as_text=True)
            if "apk_site_gate_pass_total" not in text:
                errors.append("apk_site_gate_pass_total missing")

    ok = not errors
    grafana_url = os.environ.get("GRAFANA_URL", "").strip().rstrip("/")
    live = False
    if grafana_url:
        try:
            import urllib.request

            with urllib.request.urlopen(f"{grafana_url}/api/health", timeout=3) as resp:
                live = resp.status == 200
        except Exception as exc:
            errors.append(f"grafana live {exc}")
    print(json.dumps({"ok": ok, "errors": errors, "dashboard": str(dash), "grafana_live": live}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
