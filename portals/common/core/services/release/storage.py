# -*- coding: utf-8 -*-
"""JSON persistence for release platform data files."""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List

from config import DATA_DIR
from utils import load_json, save_json

MANIFESTS_FILE = os.path.join(DATA_DIR, "project_release_manifests.json")
SCOPES_FILE = os.path.join(DATA_DIR, "release_scopes.json")
BUNDLES_FILE = os.path.join(DATA_DIR, "release_bundles.json")
_BUNDLES_LOCK = threading.RLock()


def load_manifests() -> List[Dict[str, Any]]:
    raw = load_json(MANIFESTS_FILE, [])
    return raw if isinstance(raw, list) else []


def save_manifests(rows: List[Dict[str, Any]]) -> None:
    save_json(MANIFESTS_FILE, rows)


def load_scopes() -> List[Dict[str, Any]]:
    raw = load_json(SCOPES_FILE, [])
    return raw if isinstance(raw, list) else []


def save_scopes(rows: List[Dict[str, Any]]) -> None:
    save_json(SCOPES_FILE, rows)


def load_bundles() -> List[Dict[str, Any]]:
    raw = load_json(BUNDLES_FILE, [])
    return raw if isinstance(raw, list) else []


def save_bundles(rows: List[Dict[str, Any]]) -> None:
    save_json(BUNDLES_FILE, rows)


def mutate_bundles(mutator):
    """Serialize bundle read/modify/write operations within this process."""
    with _BUNDLES_LOCK:
        rows = load_bundles()
        result = mutator(rows)
        save_bundles(rows)
        return result


def find_manifest(project_id: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    for row in load_manifests():
        if isinstance(row, dict) and str(row.get("project_id") or "").strip() == pid:
            return row
    return {}


def find_scope(scope_id: str) -> Dict[str, Any]:
    sid = str(scope_id or "").strip()
    for row in load_scopes():
        if isinstance(row, dict) and str(row.get("scope_id") or "").strip() == sid:
            return row
    return {}


def upsert_scope(row: Dict[str, Any]) -> Dict[str, Any]:
    sid = str(row.get("scope_id") or "").strip()
    rows = load_scopes()
    hit = -1
    for i, item in enumerate(rows):
        if isinstance(item, dict) and str(item.get("scope_id") or "").strip() == sid:
            hit = i
            break
    if hit >= 0:
        rows[hit] = row
    else:
        rows.append(row)
    save_scopes(rows)
    return row
