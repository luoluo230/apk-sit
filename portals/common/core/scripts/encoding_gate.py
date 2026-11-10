#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UTF-8 encoding gate for release platform modules."""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
REPO_DOCS = os.path.abspath(os.path.join(ROOT, "..", "..", "docs"))

# Generated / vendor trees — never scan (binary junk, mojibake from export, huge maps).
SKIP_DIR_NAMES = frozenset(
    {
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        ".git",
        "release_bundles",  # split-deploy output; see release_bundles/README.md — DO NOT SHIP as UTF-8 source
        "jenkins-clone",
        "archives",
    }
)

SCAN_PATHS = [
    os.path.join(ROOT, "routes"),
    os.path.join(ROOT, "services"),
    os.path.join(ROOT, "templates"),
    os.path.join(ROOT, "static"),
    os.path.join(ROOT, "scripts", "encoding_gate.py"),
    os.path.join(ROOT, "scripts", "bootstrap_gate_e2e.py"),
    os.path.join(ROOT, "scripts", "seed_release_gate_fixture.py"),
    os.path.join(ROOT, "scripts", "commercial_startup_sequence_gate.py"),
    os.path.join(REPO_DOCS, "architecture"),
    os.path.join(REPO_DOCS, "runbooks"),
    os.path.join(REPO_DOCS, "design_specs"),
    os.path.join(REPO_DOCS, "client_bootstrap_contract.md"),
    os.path.join(REPO_DOCS, "full_release_chain_architecture.md"),
]

EXTENSIONS = {".py", ".js", ".html", ".css", ".md", ".json", ".yml", ".yaml", ".sh"}

def _chars(*codepoints: int) -> str:
    return "".join(chr(c) for c in codepoints)


MOJIBAKE_PATTERNS = [
    (re.compile(r"\ufffd"), "Unicode replacement character U+FFFD"),
    (re.compile(_chars(0x951F, 0x65A4, 0x6302)), "GBK mojibake marker"),
    (re.compile("Ã[\x80-\xbf]"), "Latin-1 mojibake"),
    (re.compile(_chars(0x00EF, 0x00BC)), "UTF-8 mojibake fragment"),
]


def _walk_skip(dirpath: str, dirnames: list[str]) -> None:
    """Prune os.walk in place — quarantine release_bundles and vendor trees."""
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]


def _iter_files():
    seen: set[str] = set()
    for entry in SCAN_PATHS:
        if not os.path.exists(entry):
            continue
        if os.path.isfile(entry):
            if entry not in seen:
                seen.add(entry)
                yield entry
            continue
        for dirpath, dirnames, filenames in os.walk(entry):
            _walk_skip(dirpath, dirnames)
            for name in filenames:
                if name.startswith("._"):
                    continue
                _, ext = os.path.splitext(name)
                if ext.lower() not in EXTENSIONS:
                    continue
                path = os.path.join(dirpath, name)
                if path not in seen:
                    seen.add(path)
                    yield path


def main() -> int:
    failures: list[str] = []
    scanned = list(_iter_files())
    for path in scanned:
        rel = os.path.relpath(path, ROOT)
        try:
            raw = open(path, "rb").read()
        except OSError as exc:
            failures.append(f"{rel}: read error ({exc})")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            failures.append(f"{rel}: not valid UTF-8")
            continue
        for pat, msg in MOJIBAKE_PATTERNS:
            if pat.search(text):
                failures.append(f"{rel}: {msg}")
                break
    if failures:
        print("encoding_gate FAIL (%d issues):" % len(failures), file=sys.stderr)
        for item in failures:
            print("  -", item, file=sys.stderr)
        return 1
    print("encoding_gate PASS (%d files)" % len(scanned))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
