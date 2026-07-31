#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for Plan Closure evidence JSON files."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
EVIDENCE_ROOT = os.path.join(ROOT, "docs", "evidence")


def _today_dir() -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(EVIDENCE_ROOT, day)
    os.makedirs(path, exist_ok=True)
    return path


def evidence_path(gap_id: str, day: Optional[str] = None) -> str:
    gid = str(gap_id or "").strip().replace("/", "_")
    if day:
        return os.path.join(EVIDENCE_ROOT, day, f"{gid}.json")
    return os.path.join(_today_dir(), f"{gid}.json")


def write_evidence(
    gap_id: str,
    *,
    command: str,
    exit_code: int,
    status: str = "DONE",
    artifact_paths: Optional[List[str]] = None,
    notes: str = "",
) -> str:
    path = evidence_path(gap_id)
    payload: Dict[str, Any] = {
        "gap_id": gap_id,
        "status": status if exit_code == 0 else "FAIL",
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "command": command,
        "exit_code": exit_code,
        "artifact_paths": artifact_paths or [os.path.relpath(path, ROOT).replace("\\", "/")],
        "notes": notes,
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    return path


def load_latest_evidence(gap_id: str) -> Optional[Dict[str, Any]]:
    gid = str(gap_id or "").strip().replace("/", "_")
    if not os.path.isdir(EVIDENCE_ROOT):
        return None
    candidates: List[str] = []
    for day in sorted(os.listdir(EVIDENCE_ROOT), reverse=True):
        p = os.path.join(EVIDENCE_ROOT, day, f"{gid}.json")
        if os.path.isfile(p):
            candidates.append(p)
    if not candidates:
        return None
    with open(candidates[0], "r", encoding="utf-8") as fp:
        return json.load(fp)


def evidence_status(gap_id: str) -> str:
    row = load_latest_evidence(gap_id)
    if not row:
        return "MISSING"
    return str(row.get("status") or "MISSING").upper()
