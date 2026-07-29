#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare HotUpdateConfig.asset fields with Portal project manifest (P2-02 Step 3)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import load_dotenv

load_dotenv()

TRACKED_FIELDS = (
    "Profile",
    "Channel",
    "ProjectId",
    "CurrentClientVersion",
    "RuntimeBootstrapUrl",
    "VersionResolveUrl",
    "ResourceServerUrl",
    "RuntimeChannel",
    "ExpectedUploadEnvironment",
    "PreferWebVersionResolve",
    "AllowOssMetadataFallback",
    "PreferUnifiedBootstrap",
)


def _read_yaml_scalars(path: str) -> Dict[str, str]:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    text = open(path, encoding="utf-8").read()
    out: Dict[str, str] = {}
    for field in TRACKED_FIELDS:
        m = re.search(rf"(?m)^\s*{re.escape(field)}:\s*(.*?)\s*$", text)
        if m:
            out[field] = m.group(1).strip()
    return out


def _normalize_manifest(raw: Dict[str, Any]) -> Dict[str, str]:
    portal = str(raw.get("portal_base_url") or raw.get("runtime_bootstrap_url") or "").strip().rstrip("/")
    return {
        "Profile": str(raw.get("profile") or raw.get("release_environment") or "Development"),
        "Channel": str(raw.get("channel") or raw.get("release_channel") or "common"),
        "ProjectId": str(raw.get("project_id") or ""),
        "CurrentClientVersion": str(raw.get("version_name") or raw.get("current_client_version") or ""),
        "RuntimeBootstrapUrl": portal,
        "VersionResolveUrl": portal,
        "ResourceServerUrl": str(raw.get("resource_server_url") or "").strip().rstrip("/"),
        "RuntimeChannel": str(raw.get("runtime_channel") or "development"),
        "ExpectedUploadEnvironment": str(raw.get("expected_upload_environment") or raw.get("profile") or "Development"),
        "PreferWebVersionResolve": "0",
        "AllowOssMetadataFallback": "0",
        "PreferUnifiedBootstrap": "1",
    }


def _checksum(fields: Dict[str, str]) -> str:
    ordered = {k: fields.get(k, "") for k in TRACKED_FIELDS}
    blob = json.dumps(ordered, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def compare(asset_path: str, expected: Dict[str, Any]) -> Tuple[bool, List[str], str, str]:
    actual_raw = _read_yaml_scalars(asset_path)
    expected_raw = _normalize_manifest(expected)
    mismatches: List[str] = []
    for key in TRACKED_FIELDS:
        act = str(actual_raw.get(key) or "").strip()
        exp = str(expected_raw.get(key) or "").strip()
        if act != exp:
            mismatches.append(f"{key}: asset={act!r} expected={exp!r}")
    return len(mismatches) == 0, mismatches, _checksum(actual_raw), _checksum(expected_raw)


def load_portal_manifest(project_id: str) -> Dict[str, Any]:
    from models.data import projects_db

    project = projects_db.get(project_id) if isinstance(projects_db, dict) else {}
    if not isinstance(project, dict):
        project = {}
    base = os.environ.get("PORTAL_BASE_URL", "http://127.0.0.1:5003").strip().rstrip("/")
    return {
        "project_id": project_id,
        "portal_base_url": base,
        "profile": project.get("default_env") or "Development",
        "channel": project.get("default_channel") or "wechat",
        "version_name": project.get("default_version") or "",
        "resource_server_url": project.get("resource_server_url") or "",
        "runtime_channel": "development" if str(project.get("default_env") or "").lower().startswith("dev") else "production",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify HotUpdateConfig.asset matches Portal manifest checksum")
    parser.add_argument("--asset", default=os.environ.get("HOTUPDATE_CONFIG_ASSET", ""))
    parser.add_argument("--manifest", default="", help="JSON file with expected fields")
    parser.add_argument("--project-id", default=os.environ.get("PROJECT_ID", "GomeKu"))
    parser.add_argument("--maclient-root", default=os.environ.get("MACLIENT_ROOT", "E:/maclient"))
    args = parser.parse_args()

    asset = args.asset.strip() or os.path.join(
        args.maclient_root,
        "Assets",
        "Content",
        "Resources",
        "HotUpdateConfig.asset",
    )
    if args.manifest.strip():
        expected = json.load(open(args.manifest.strip(), encoding="utf-8"))
    else:
        expected = load_portal_manifest(args.project_id)

    ok, mismatches, asset_sum, expected_sum = compare(asset, expected)
    print(json.dumps({"ok": ok, "asset": asset, "asset_checksum": asset_sum, "expected_checksum": expected_sum}, ensure_ascii=False, indent=2))
    if mismatches:
        for line in mismatches:
            print("MISMATCH:", line)
        return 1
    if asset_sum != expected_sum:
        print("FAIL: checksum mismatch")
        return 1
    print("PASS: HotUpdateConfig.asset aligned with Portal manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
