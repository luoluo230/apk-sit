#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan source tree for forbidden default secrets. Plan P0-01."""

from __future__ import annotations

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
)
SCAN_SUFFIXES = (".py", ".sh", ".ps1", ".mdc")
SKIP_DIR_NAMES = {
    "__pycache__",
    "tests",
    "scripts",
    "release_bundles",
    "archives",
    "static",
    "gate-fixture",
}
ALLOWED_REL_PATHS = {
    os.path.join("docs", "architecture", "full_stack_expert_review.md"),
    os.path.join("docs", "runbooks", "production_secrets.md"),
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
    if "data/repositories/user_repository.py" in rel.replace("\\", "/"):
        return False
    return True


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
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                        text = fp.read()
                except OSError:
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
