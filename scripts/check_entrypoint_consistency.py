#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guard against legacy runtime entry usage."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCAN_GLOBS = ["*.py", "*.ps1", "*.bat", "*.md"]
EXCLUDE_DIRS = {
    ".git", "venv", "node_modules", "dist", "backups",
    "release_bundles", "release_bundles_clean", "release_bundles_final",
    "release_bundles_deploy", "release_bundles_verify", "legacy"
}
FORBIDDEN_PATTERNS = [
    re.compile(r"\bwaitress\b.*\bapp:app\b", re.I),
    re.compile(r"\bgunicorn\b.*\bapp:app\b", re.I),
    re.compile(r"from\s+app\s+import\s+app", re.I),
]


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def main() -> int:
    issues = []
    for glob in SCAN_GLOBS:
        for p in ROOT.rglob(glob):
            if should_skip(p):
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(txt.splitlines(), start=1):
                for pat in FORBIDDEN_PATTERNS:
                    if pat.search(line):
                        issues.append((p, i, line.strip()))
    if issues:
        print("[FAIL] legacy entry usage found:")
        for p, i, line in issues:
            print(f"- {p}:{i}: {line}")
        return 2
    print("[OK] entrypoint consistency passed (no legacy app.py runtime usage).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
