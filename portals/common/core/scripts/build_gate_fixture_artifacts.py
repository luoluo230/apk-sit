# -*- coding: utf-8 -*-
"""Build signed config/code manifests for gate-fixture static hosting."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "static" / "gate-fixture"
SIGNING_KEY = os.environ.get(
    "GATE_FIXTURE_SIGNING_KEY",
    "full-smoke-sign-key-20260403",
)


def _sign(manifest_text: str) -> dict:
    digest = hmac.new(
        SIGNING_KEY.encode("utf-8"),
        manifest_text.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "manifestFileName": "config_patch_manifest.json",
        "algorithm": "HMACSHA256",
        "signature": digest,
        "generatedAtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
    }


def _code_sign(manifest_text: str) -> dict:
    payload = _sign(manifest_text)
    payload["manifestFileName"] = "code_patch_manifest.json"
    return payload


def _write_manifest(subdir: str, manifest_name: str, signature_name: str, body: dict, sign_fn) -> None:
    folder = FIXTURE / subdir
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    (folder / manifest_name).write_text(text, encoding="utf-8")
    sig = sign_fn(text)
    (folder / signature_name).write_text(json.dumps(sig, ensure_ascii=False, indent=2), encoding="utf-8")


def build() -> dict:
    FIXTURE.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    config_manifest = {
        "schemaProject": "GomeKu",
        "environment": "Development",
        "channel": "wechat",
        "platform": "Android",
        "clientVersion": "1.0.0",
        "versionCode": "12",
        "versionFolder": "Version_1.0.0/12",
        "clientMajor": "1",
        "clientMinor": "0",
        "generatedAtUtc": now,
        "providerId": "gate-fixture",
        "baseRemotePrefix": "static/gate-fixture/config",
        "files": [],
    }
    code_manifest = {
        "schemaProject": "GomeKu",
        "environment": "Development",
        "channel": "wechat",
        "platform": "Android",
        "clientVersion": "1.0.0",
        "versionCode": "12",
        "versionFolder": "Version_1.0.0/12",
        "clientMajor": "1",
        "clientMinor": "0",
        "generatedAtUtc": now,
        "providerId": "gate-fixture",
        "baseRemotePrefix": "static/gate-fixture/code",
        "files": [],
    }
    layouts = (
        ("config", "config_patch_manifest.json", "config_patch_manifest.signature.json", config_manifest, _sign),
        ("code", "code_patch_manifest.json", "code_patch_manifest.signature.json", code_manifest, _code_sign),
        ("Version_1.0.0/12/config", "config_patch_manifest.json", "config_patch_manifest.signature.json", config_manifest, _sign),
        ("Version_1.0.0/12/code", "code_patch_manifest.json", "code_patch_manifest.signature.json", code_manifest, _code_sign),
    )
    for subdir, manifest_name, signature_name, body, sign_fn in layouts:
        _write_manifest(subdir, manifest_name, signature_name, body, sign_fn)
    catalog = FIXTURE / "catalog_1.0.0.bin"
    if not catalog.is_file() or catalog.stat().st_size < 16:
        catalog.write_bytes(b"GATE_FIXTURE_CATALOG_V1\n")
    return {
        "ok": True,
        "fixture_root": str(FIXTURE),
        "config_manifest": str(FIXTURE / "config" / "config_patch_manifest.json"),
        "code_manifest": str(FIXTURE / "code" / "code_patch_manifest.json"),
    }


def main() -> int:
    print(json.dumps(build(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
