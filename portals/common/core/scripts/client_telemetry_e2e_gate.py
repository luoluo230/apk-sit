# -*- coding: utf-8 -*-
"""CI gate: client telemetry ingest + recent + metrics (T-E11/E12 apk-site)."""

from __future__ import annotations

import json
import os
import sys
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    from app_new import app
    from repositories.admin import users_repo

    username = next(iter(users_repo.list_users().keys()), "admin")
    sample_id = f"gate-{uuid.uuid4().hex[:8]}"
    errors: list[str] = []

    with app.test_client() as client:
        post = client.post(
            "/api/public/client-telemetry",
            json={
                "event_type": "performance",
                "sample_id": sample_id,
                "fps": 58.5,
                "rtt_ms": 42,
                "client_version": "1.0.0-gate",
            },
        )
        if post.status_code != 200:
            errors.append(f"ingest status {post.status_code}")

        with client.session_transaction() as sess:
            sess["user"] = username
        recent = client.get(f"/api/public/client-telemetry/recent?limit=20")
        if recent.status_code != 200:
            errors.append(f"recent status {recent.status_code}")
        else:
            events = (recent.get_json() or {}).get("events") or []
            if not any(str(e.get("sample_id") or "") == sample_id for e in events if isinstance(e, dict)):
                errors.append("ingested sample not found in recent")

        metrics = client.get("/metrics")
        if metrics.status_code != 200:
            errors.append(f"metrics status {metrics.status_code}")
        elif "apk_site_telemetry_ingest_total" not in metrics.get_data(as_text=True):
            errors.append("telemetry metric missing from /metrics")

    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "sample_id": sample_id}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
