#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normalize legacy Jenkins path references inside jenkins-clone files.

Usage:
  python scripts/update_jenkins_paths.py
  python scripts/update_jenkins_paths.py --dry-run
  python scripts/update_jenkins_paths.py --jenkins-clone E:\\custom\\jenkins-clone --apk-dir E:\\builds
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLONE = ROOT / "jenkins-clone"
DEFAULT_APK_DIR = ROOT / "data" / "apk"

TARGET_PATTERNS = [
    "jobs/Android/config.xml",
    "scripts/*.sh",
    "notify_feishu.sh",
    "start_service.sh",
]


def _collect_files(base: Path):
    files: list[Path] = []
    for rel in TARGET_PATTERNS:
        files.extend(sorted(base.glob(rel)))
    return [p for p in files if p.is_file()]


def _replace_legacy_paths(content: str, clone_path: str, apk_dir: str) -> tuple[str, int]:
    count = 0

    patterns = [
        # Unix/macOS absolute paths ending with jenkins-clone
        (r"/[^\s'\"<>]+/jenkins-clone", clone_path),
        # Windows absolute paths ending with jenkins-clone
        (r"[A-Za-z]:\\[^\r\n'\"<>]+\\jenkins-clone", clone_path),
        # Unix/macOS absolute Builds directory
        (r"/[^\s'\"<>]+/Builds", apk_dir),
        # Windows absolute Builds directory
        (r"[A-Za-z]:\\[^\r\n'\"<>]+\\Builds", apk_dir),
    ]

    updated = content
    for pattern, replacement in patterns:
        updated, n = re.subn(pattern, replacement, updated)
        count += n
    return updated, count


def main() -> int:
    parser = argparse.ArgumentParser(description="Update legacy Jenkins absolute paths")
    parser.add_argument("--jenkins-clone", default=str(DEFAULT_CLONE), help="jenkins-clone root")
    parser.add_argument("--apk-dir", default=str(DEFAULT_APK_DIR), help="APK output base dir")
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing files")
    args = parser.parse_args()

    clone_root = Path(args.jenkins_clone).expanduser().resolve()
    apk_dir = str(Path(args.apk_dir).expanduser().resolve())

    if not clone_root.is_dir():
        print(f"[ERROR] jenkins-clone not found: {clone_root}")
        return 1

    files = _collect_files(clone_root)
    if not files:
        print("[INFO] no target files found")
        return 0

    total_files = 0
    total_replacements = 0
    for file_path in files:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        updated, count = _replace_legacy_paths(text, str(clone_root), apk_dir)
        if count <= 0:
            continue
        total_files += 1
        total_replacements += count
        rel = file_path.relative_to(ROOT) if ROOT in file_path.parents else file_path
        if args.dry_run:
            print(f"[DRY-RUN] {rel} -> {count} replacements")
            continue
        file_path.write_text(updated, encoding="utf-8")
        print(f"[UPDATED] {rel} -> {count} replacements")

    if total_replacements == 0:
        print("[INFO] no legacy absolute paths detected")
        return 0

    mode = "DRY-RUN" if args.dry_run else "DONE"
    print(f"[{mode}] files={total_files}, replacements={total_replacements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
