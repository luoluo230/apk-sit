#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UTF-8 encoding gate for release platform modules."""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
REPO_DOCS = os.path.abspath(os.path.join(ROOT, "..", "..", "docs"))

SCAN_PATHS = [
    os.path.join(ROOT, "routes", "delivery"),
    os.path.join(ROOT, "routes", "internal_jenkins.py"),
    os.path.join(ROOT, "routes", "approval_webhooks.py"),
    os.path.join(ROOT, "routes", "gm_ops_release.py"),
    os.path.join(ROOT, "routes", "project_delivery.py"),
    os.path.join(ROOT, "services", "release"),
    os.path.join(ROOT, "services", "ops", "runtime_service.py"),
    os.path.join(ROOT, "services", "ops", "topology_service.py"),
    os.path.join(ROOT, "services", "ops", "agent_service.py"),
    os.path.join(ROOT, "services", "release", "client_health_service.py"),
    os.path.join(ROOT, "static", "delivery_order_detail.js"),
    os.path.join(ROOT, "static", "delivery_common.js"),
    os.path.join(ROOT, "static", "project_delivery.js"),
    os.path.join(ROOT, "static", "project_channel_build_journey.js"),
    os.path.join(ROOT, "static", "project_channel_release_journey.js"),
    os.path.join(ROOT, "static", "project_test_devices.js"),
    os.path.join(ROOT, "static", "project_environment_runtime.js"),
    os.path.join(ROOT, "templates", "release_order_form.html"),
    os.path.join(ROOT, "templates", "release_order_detail.html"),
    os.path.join(ROOT, "templates", "project_test_devices.html"),
    os.path.join(ROOT, "templates", "project_docs_embed.html"),
    os.path.join(ROOT, "templates", "project_environment_runtime.html"),
    os.path.join(ROOT, "scripts", "encoding_gate.py"),
    os.path.join(ROOT, "scripts", "bootstrap_gate_e2e.py"),
    os.path.join(ROOT, "scripts", "seed_release_gate_fixture.py"),
    os.path.join(ROOT, "scripts", "commercial_startup_sequence_gate.py"),
    os.path.join(REPO_DOCS, "architecture"),
    os.path.join(REPO_DOCS, "runbooks"),
    os.path.join(REPO_DOCS, "client_bootstrap_contract.md"),
    os.path.join(REPO_DOCS, "full_release_chain_architecture.md"),
    os.path.join(REPO_DOCS, "design_specs", "release_pipeline_audit.md"),
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
        for dirpath, _, filenames in os.walk(entry):
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
