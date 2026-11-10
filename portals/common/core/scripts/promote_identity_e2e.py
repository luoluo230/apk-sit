#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""In-process promote identity gate (COMM-P1-3): identity helper + API promote block."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from scripts.closure_evidence import write_evidence  # noqa: E402


def _run_identity_cases() -> Tuple[bool, List[str]]:
    from services.release.artifact_identity import require_matching_artifact_identity

    errors: List[str] = []
    try:
        require_matching_artifact_identity({"client": {"apk_url": "http://x"}})
        errors.append("missing identity should block")
    except ValueError:
        pass
    try:
        require_matching_artifact_identity(
            {"artifact_id": "a1", "sha256": "aaa"},
            {"artifact_id": "a1", "sha256": "bbb"},
        )
        errors.append("mismatch should block")
    except ValueError:
        pass
    ident = require_matching_artifact_identity(
        {"artifact_id": "a1", "sha256": "aaa"},
        {"artifact_id": "a1", "sha256": "aaa"},
    )
    if ident.get("artifact_id") != "a1":
        errors.append("match path failed")
    return len(errors) == 0, errors


def _run_promote_api_block() -> Tuple[bool, str]:
    from app_new import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["username"] = "admin"
    pid = "GomeKu"
    resp = client.post(
        f"/api/projects/{pid}/artifact-promotions",
        json={"source_bundle_id": "rb-nonexistent", "target_env_key": "staging"},
        content_type="application/json",
    )
    payload = resp.get_json() or {}
    # Missing bundle must not succeed as promote.
    if resp.status_code == 201 and payload.get("ok"):
        return False, "unexpected promote success without bundle"
    return True, f"HTTP {resp.status_code} {json.dumps(payload, ensure_ascii=False)[:240]}"


def main() -> int:
    cmd = "py -3 portals/common/core/scripts/promote_identity_e2e.py"
    ok_id, id_errors = _run_identity_cases()
    ok_api, api_note = _run_promote_api_block()
    ok = ok_id and ok_api
    notes: Dict[str, Any] = {
        "identity_cases_ok": ok_id,
        "identity_errors": id_errors,
        "promote_api_probe": api_note,
    }
    write_evidence(
        "COMM-P1-3",
        command=cmd,
        exit_code=0 if ok else 1,
        status="DONE" if ok else "FAIL",
        notes=json.dumps(notes, ensure_ascii=False),
    )
    if not ok:
        print("FAIL", notes, file=sys.stderr)
        return 1
    print("OK", notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
