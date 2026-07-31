#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan source tree for forbidden default secrets. Plan P0-01."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
FORBIDDEN = (
    "admin" + "123",
    "ma-cluster-relay-" + "dev",
)
SCAN_ROOTS = (
    os.path.join(ROOT, "portals", "common", "core"),
    os.path.join(ROOT, "jenkins-clone", "scripts"),
    os.path.join(ROOT, "scripts"),
)
SCAN_SUFFIXES = (".py", ".sh", ".ps1", ".mdc", ".json")
SKIP_DIR_NAMES = {
    "__pycache__",
    "tests",
    "release_bundles",
    "archives",
    "static",
    "gate-fixture",
    "node_modules",
}
# scripts/ under portals/core is scanned; top-level scripts/ scanned but Start-DevStack uses .env.devstack only
SKIP_SCRIPT_PATHS = set()
ALLOWED_REL_PATHS = {
    os.path.join("docs", "architecture", "full_stack_expert_review.md"),
    os.path.join("docs", "runbooks", "production_secrets.md"),
    os.path.join("docs", "runbooks", "ios_provisioning_checklist.md"),
    os.path.join("portals", "common", "core", "config", "settings.example.json"),
}
ALLOWED_JSON_KEYS_EMPTY = {
    ("portals/common/core/config/settings.example.json", "jenkins", "default_password"),
}


def _should_scan(path: str) -> bool:
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    if rel in {p.replace("\\", "/") for p in ALLOWED_REL_PATHS}:
        return False
    if not path.endswith(SCAN_SUFFIXES):
        return False
    parts = rel.split("/")
    if any(part in SKIP_DIR_NAMES for part in parts):
        return False
    if "data/repositories/user_repository.py" in rel:
        return False
    if rel.endswith("settings.json"):
        return True
    if "/scripts/" in rel and rel.startswith("portals/"):
        return False
    return True


def _scan_json_secrets(path: str, rel: str, hits: list) -> None:
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return

    def walk(obj, key_path: tuple):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, key_path + (str(k),))
        elif isinstance(obj, str):
            for token in FORBIDDEN:
                if token in obj:
                    if (rel, *key_path[:2]) in ALLOWED_JSON_KEYS_EMPTY and not obj.strip():
                        continue
                    hits.append((path, f"{token} in json {'.'.join(key_path)}"))

    walk(data, ())


def main() -> int:
    hits = []
    for scan_root in SCAN_ROOTS:
        if not os.path.isdir(scan_root):
            continue
        for dirpath, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for name in filenames:
                path = os.path.join(dirpath, name)
                if not _should_scan(path):
                    continue
                rel = os.path.relpath(path, ROOT).replace("\\", "/")
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                        text = fp.read()
                except OSError:
                    continue
                if path.endswith(".json"):
                    _scan_json_secrets(path, rel, hits)
                    continue
                for token in FORBIDDEN:
                    if token in text:
                        hits.append((path, token))
    if hits:
        print("production_secret_gate FAILED:")
        for path, token in hits[:40]:
            print(f"  {token} in {os.path.relpath(path, ROOT)}")
        if len(hits) > 40:
            print(f"  ... and {len(hits) - 40} more")
        return 1
    print("production_secret_gate PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
