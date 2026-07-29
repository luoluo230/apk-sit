#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate legacy data/build_nodes.json into infra_nodes SQLite table."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "portals", "common", "core"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("APK_DEBUG", "false")

from config import load_dotenv

load_dotenv()

from models.db import init_db
from services.infra.infra_node_registry import register_or_heartbeat


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate build_nodes.json to infra_nodes DB")
    parser.add_argument(
        "--json",
        default=os.path.join(ROOT, "data", "build_nodes.json"),
        help="Path to legacy build_nodes.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    path = os.path.abspath(args.json)
    if not os.path.isfile(path):
        print(f"skip: file not found {path}")
        return 0
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    nodes = data.get("nodes") if isinstance(data, dict) else []
    if not isinstance(nodes, list):
        print("invalid json shape")
        return 1
    migrated = 0
    for row in nodes:
        if not isinstance(row, dict):
            continue
        payload = {
            "node_id": row.get("id") or row.get("node_id"),
            "role": row.get("role"),
            "hostname": row.get("hostname") or row.get("host"),
            "agent_name": row.get("agent_name"),
            "os": row.get("os"),
            "unity_version": row.get("unity_version"),
            "unity_editor_path": row.get("unity_editor_path"),
            "jenkins_master_url": row.get("jenkins_master_url"),
            "labels": row.get("labels"),
            "capabilities": row.get("capabilities"),
        }
        if args.dry_run:
            print("would migrate", payload.get("node_id"), payload.get("role"))
        else:
            register_or_heartbeat(payload)
        migrated += 1
    print(f"done: migrated={migrated} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
