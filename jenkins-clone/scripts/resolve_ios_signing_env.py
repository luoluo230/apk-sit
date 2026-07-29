#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resolve ios_signing from version group metadata → shell export lines (P2-02 Step 5)."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "portals", "common", "core"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.build.platform_signing_service import normalize_ios_signing


def main() -> int:
    raw = os.environ.get("IOS_SIGNING_JSON", "").strip()
    if raw:
        signing = normalize_ios_signing(json.loads(raw))
    else:
        signing = normalize_ios_signing(
            {
                "team_id": os.environ.get("IOS_TEAM_ID", ""),
                "bundle_id": os.environ.get("IOS_SIGNING_BUNDLE_ID", os.environ.get("BUNDLE_ID", "")),
                "asc_api_key_id": os.environ.get("ASC_API_KEY_ID", ""),
                "asc_api_issuer": os.environ.get("ASC_API_ISSUER", ""),
                "asc_api_key_path": os.environ.get("ASC_API_KEY_PATH", ""),
            }
        )

    export_method = os.environ.get("IOS_EXPORT_METHOD", "").strip().lower()
    if not export_method:
        export_method = "app-store" if signing.get("asc_api_key_id") else "development"

    lines = [
        f'export IOS_EXPORT_METHOD="{export_method}"',
        f'export IOS_TEAM_ID="{signing.get("team_id") or ""}"',
        f'export IOS_SIGNING_BUNDLE_ID="{signing.get("bundle_id") or ""}"',
        f'export ASC_API_KEY_ID="{signing.get("asc_api_key_id") or ""}"',
        f'export ASC_API_ISSUER="{signing.get("asc_api_issuer") or ""}"',
        f'export ASC_API_KEY_PATH="{signing.get("asc_api_key_path") or ""}"',
    ]
    if signing.get("provisioning_profile_path"):
        lines.append(f'export IOS_PROVISIONING_PROFILE_PATH="{signing["provisioning_profile_path"]}"')
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
