#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate data/*.json documents into SQLite json_documents.

This script is intentionally file-first (not load_json) so it can run
when runtime fallback from JSON files is disabled.
"""

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import DATA_DIR, load_dotenv  # noqa: E402
from models.db import init_db, set_json_document  # noqa: E402


def _read_json(path):
    last_error = None
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return json.load(handle)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = exc
    raise last_error or ValueError(f"unable to decode {path}")


def _iter_data_json_files():
    if not os.path.isdir(DATA_DIR):
        return
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith(".json"):
            continue
        # Skip AppleDouble metadata files such as ._users.json
        if name.startswith("._"):
            continue
        path = os.path.join(DATA_DIR, name)
        if os.path.isfile(path):
            yield name, path


def _archive_source(path):
    archive_root = os.path.join(DATA_DIR, "_legacy_json")
    os.makedirs(archive_root, exist_ok=True)
    target = os.path.join(archive_root, os.path.basename(path))
    if os.path.exists(target):
        base, ext = os.path.splitext(target)
        idx = 1
        while os.path.exists(f"{base}.{idx}{ext}"):
            idx += 1
        target = f"{base}.{idx}{ext}"
    shutil.move(path, target)
    return target


def main():
    parser = argparse.ArgumentParser(description="Migrate data/*.json to SQLite")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="move source JSON files into data/_legacy_json after successful migration",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any JSON file cannot be parsed",
    )
    args = parser.parse_args()

    load_dotenv()
    init_db()

    migrated = 0
    skipped = 0
    failed = 0
    archived = 0

    for name, path in _iter_data_json_files():
        try:
            payload = _read_json(path)
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {name}: {exc}")
            if args.strict:
                return 2
            continue

        set_json_document(f"data/{name}", payload)
        migrated += 1
        print(f"[OK] migrated data/{name}")

        if args.archive:
            archived_path = _archive_source(path)
            archived += 1
            print(f"[OK] archived -> {archived_path}")

    if migrated == 0 and failed == 0:
        skipped += 1
        print("[INFO] no JSON files found under data/")

    print(
        "[DONE] migrated=%d failed=%d archived=%d skipped=%d"
        % (migrated, failed, archived, skipped)
    )
    return 1 if (failed and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
