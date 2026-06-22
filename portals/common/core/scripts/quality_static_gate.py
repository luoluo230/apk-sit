#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Static quality gate: legacy drift, UI/logic traps, mojibake in first-party sources."""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCAN_DIRS = [
    os.path.join(ROOT, "routes"),
    os.path.join(ROOT, "services"),
    os.path.join(ROOT, "static"),
    os.path.join(ROOT, "templates"),
    os.path.join(ROOT, "repositories"),
]

SKIP_PARTS = {
    os.path.join(ROOT, "jenkins-clone"),
    os.path.join(ROOT, "static", "gate-fixture"),
}

MOJIBAKE_PATTERNS = [
    (re.compile(r"锟斤拷"), "replacement char garbage"),
    (re.compile(r"Ã[\x80-\xbf]"), "latin1 mojibake"),
    (re.compile(r"ï¼"), "utf8 mojibake"),
]

LEGACY_PATTERNS = [
    (re.compile(r"btnValidateGit"), "removed Jenkins Git button id referenced"),
    (
        re.compile(r"inst\.get\(['\"]jenkins_home['\"]\)"),
        "raw jenkins_home; use resolve_jenkins_home(inst)",
    ),
]

ALLOWED_RAW_JENKINS_HOME = {
    os.path.join(ROOT, "services", "jenkins_manager.py"),
}


def _iter_files():
    for base in SCAN_DIRS:
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            if any(dirpath.startswith(skip) for skip in SKIP_PARTS):
                continue
            for name in filenames:
                if name.startswith("._"):
                    continue
                if not name.endswith((".py", ".js", ".html", ".css")):
                    continue
                yield os.path.join(dirpath, name)


def main() -> int:
    failures: list[str] = []
    for path in _iter_files():
        rel = os.path.relpath(path, ROOT)
        try:
            text = open(path, encoding="utf-8").read()
        except UnicodeDecodeError:
            failures.append("%s: file is not valid UTF-8" % rel)
            continue
        for pat, msg in MOJIBAKE_PATTERNS:
            if pat.search(text):
                failures.append("%s: mojibake (%s)" % (rel, msg))
                break
        for pat, msg in LEGACY_PATTERNS:
            if "raw jenkins_home" in msg and path in ALLOWED_RAW_JENKINS_HOME:
                continue
            if "raw jenkins_home" in msg and "resolve_jenkins_home" in text:
                continue
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                failures.append("%s:%d: %s" % (rel, line, msg))
    if failures:
        print("[FAIL] quality_static_gate found %d issue(s):" % len(failures))
        for item in failures[:50]:
            print(" -", item)
        if len(failures) > 50:
            print(" ... and %d more" % (len(failures) - 50))
        return 1
    print("[OK] quality_static_gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
