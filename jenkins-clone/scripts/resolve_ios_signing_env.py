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


def _shell_quote(value: str) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace('"', '\\"')


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
        export_method = str(signing.get("export_method") or "").strip().lower()
    if not export_method:
        export_method = "app-store" if signing.get("secret_mode") == "jenkins" else "development"

    lines = [
        f'export IOS_EXPORT_METHOD="{_shell_quote(export_method)}"',
        f'export IOS_TEAM_ID="{_shell_quote(signing.get("team_id") or "")}"',
        f'export IOS_SIGNING_BUNDLE_ID="{_shell_quote(signing.get("bundle_id") or "")}"',
        f'export IOS_PROVISIONING_PROFILE_NAME="{_shell_quote(signing.get("provisioning_profile_name") or "")}"',
        f'export IOS_SECRET_MODE="{_shell_quote(signing.get("secret_mode") or "jenkins")}"',
        f'export EXTERNAL_UPLOAD_TESTFLIGHT="{"true" if signing.get("auto_upload_testflight") else "false"}"',
    ]

    secret_mode = signing.get("secret_mode") or "jenkins"
    if secret_mode == "jenkins":
        for env_key, field in (
            ("IOS_JENKINS_ASC_CREDENTIAL_ID", "jenkins_asc_credential_id"),
            ("IOS_JENKINS_CERT_CREDENTIAL_ID", "jenkins_cert_credential_id"),
            ("IOS_JENKINS_PROFILE_CREDENTIAL_ID", "jenkins_profile_credential_id"),
        ):
            cred = signing.get(field) or os.environ.get(env_key, "")
            if cred:
                lines.append(f'export {env_key}="{_shell_quote(cred)}"')
        # Jenkins job should bind credentials → ASC_* / cert paths; pass through if already injected
        for env_key, field in (
            ("ASC_API_KEY_ID", "asc_api_key_id"),
            ("ASC_API_ISSUER", "asc_api_issuer"),
            ("ASC_API_KEY_PATH", "asc_api_key_path"),
        ):
            val = os.environ.get(env_key, "") or signing.get(field) or ""
            if val:
                lines.append(f'export {env_key}="{_shell_quote(val)}"')
    else:
        lines.extend([
            f'export ASC_API_KEY_ID="{_shell_quote(signing.get("asc_api_key_id") or "")}"',
            f'export ASC_API_ISSUER="{_shell_quote(signing.get("asc_api_issuer") or "")}"',
            f'export ASC_API_KEY_PATH="{_shell_quote(signing.get("asc_api_key_path") or "")}"',
        ])
        if signing.get("provisioning_profile_path"):
            lines.append(
                f'export IOS_PROVISIONING_PROFILE_PATH="{_shell_quote(signing["provisioning_profile_path"])}"'
            )

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
