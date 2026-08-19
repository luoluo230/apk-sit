# -*- coding: utf-8 -*-
"""Sync portable unity_contract_manifest.json for maclient EditMode tests."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _fetch_from_portal(base_url: str) -> dict:
    url = str(base_url or "").strip().rstrip("/") + "/api/public/unity-contract-manifest"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sync_manifest(*, dest: str, portal_base_url: str = "", local_only: bool = False) -> str:
    if local_only or not str(portal_base_url or "").strip():
        from services.release.unity_contract_bridge import build_portable_unity_contract_manifest

        manifest = build_portable_unity_contract_manifest(
            portal_base_url=str(portal_base_url or "http://127.0.0.1:5003").strip()
        )
    else:
        manifest = _fetch_from_portal(portal_base_url)
    dest_path = os.path.abspath(dest)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return dest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync unity contract manifest for maclient")
    parser.add_argument(
        "--dest",
        default=os.path.join(ROOT, "tests", "fixtures", "unity_contract_manifest.json"),
        help="Output JSON path",
    )
    parser.add_argument(
        "--portal-base-url",
        default=os.environ.get("PORTAL_BASE_URL", ""),
        help="Fetch live manifest from Portal (optional)",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Build manifest locally without HTTP fetch",
    )
    args = parser.parse_args()
    path = sync_manifest(
        dest=args.dest,
        portal_base_url=str(args.portal_base_url or ""),
        local_only=bool(args.local_only or not str(args.portal_base_url or "").strip()),
    )
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    contracts = data.get("contracts") or []
    if not contracts or not isinstance(contracts[0].get("fixture"), dict):
        print("sync_unity_contract_manifest FAILED: missing embedded fixtures")
        return 1
    print(f"sync_unity_contract_manifest PASS -> {path} ({len(contracts)} contracts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
