#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate that runtime data documents are present in SQLite."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import DATA_DIR, load_dotenv  # noqa: E402
from models.db import has_json_document, init_db, list_json_documents  # noqa: E402


REQUIRED_DATA_DOCS = [
    "users.json",
    "projects.json",
    "project_tasks.json",
    "products.json",
    "project_versions.json",
    "player_news.json",
    "player_welfare.json",
    "forum_posts.json",
    "player_moderation.json",
    "developer_portal_content.json",
    "player_portal_content.json",
    "company_profile.json",
]


def main():
    load_dotenv()
    init_db()
    docs = list_json_documents()
    print("[INFO] sqlite json_documents: %d" % len(docs))

    missing = []
    for filename in REQUIRED_DATA_DOCS:
        key = f"data/{filename}"
        if not has_json_document(key):
            missing.append(key)

    if missing:
        print("[FAIL] missing required SQLite docs:")
        for key in missing:
            print("  -", key)
    else:
        print("[OK] all required data docs are present in SQLite")

    on_disk = []
    if os.path.isdir(DATA_DIR):
        for name in sorted(os.listdir(DATA_DIR)):
            if name.endswith(".json"):
                if name.startswith("._"):
                    continue
                on_disk.append(os.path.join(DATA_DIR, name))
    if on_disk:
        print("[WARN] JSON files still exist on disk:")
        for path in on_disk:
            print("  -", path)
    else:
        print("[OK] no JSON files left in data/")

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
