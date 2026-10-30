# -*- coding: utf-8 -*-
"""Build signed config/code manifests for gate-fixture static hosting.

Always emits non-empty files[] so HTTP greening cannot hide empty patch trees.
"""

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


def _md5_bytes(blob: bytes) -> str:
    return hashlib.md5(blob).hexdigest()


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


def _ensure_payload_files() -> tuple[dict, dict]:
    config_rel = "gate_fixture_config.json"
    code_rel = "hotupdate/HotUpdate.dll"
    config_path = FIXTURE / "config" / config_rel
    code_path = FIXTURE / "code" / code_rel
    config_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.parent.mkdir(parents=True, exist_ok=True)
    config_blob = b'{"gate_fixture":true,"domain":"config"}\n'
    # Tiny non-empty placeholder so download/md5 probes have a real object.
    code_blob = b"GATE_FIXTURE_HOTUPDATE_DLL_PLACEHOLDER_V1\n"
    config_path.write_bytes(config_blob)
    code_path.write_bytes(code_blob)

    # Mirror under Version tree for bootstrap relative layouts.
    ver_config = FIXTURE / "Version_1.0.0" / "12" / "config" / config_rel
    ver_code = FIXTURE / "Version_1.0.0" / "12" / "code" / code_rel
    ver_config.parent.mkdir(parents=True, exist_ok=True)
    ver_code.parent.mkdir(parents=True, exist_ok=True)
    ver_config.write_bytes(config_blob)
    ver_code.write_bytes(code_blob)

    config_file = {
        "relativePath": config_rel,
        "md5": _md5_bytes(config_blob),
        "size": len(config_blob),
        "role": "config",
        "downloadUrl": "http://127.0.0.1:5003/static/gate-fixture/config/" + config_rel,
    }
    code_file = {
        "relativePath": code_rel,
        "md5": _md5_bytes(code_blob),
        "size": len(code_blob),
        "role": "hotupdate",
        "downloadUrl": "http://127.0.0.1:5003/static/gate-fixture/code/" + code_rel,
    }
    return config_file, code_file


def build() -> dict:
    FIXTURE.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    config_file, code_file = _ensure_payload_files()
    config_manifest = {
        "schemaProject": "GomeKu",
        "environment": "Development",
        "channel": "wechat",
        "platform": "android",
        "clientVersion": "1.0.0",
        "versionCode": "12",
        "versionFolder": "Version_1.0.0/12",
        "clientMajor": "1",
        "clientMinor": "0",
        "generatedAtUtc": now,
        "providerId": "gate-fixture",
        "baseRemotePrefix": "gate-fixture/config",
        "files": [config_file],
    }
    code_manifest = {
        "schemaProject": "GomeKu",
        "environment": "Development",
        "channel": "wechat",
        "platform": "android",
        "clientVersion": "1.0.0",
        "versionCode": "12",
        "versionFolder": "Version_1.0.0/12",
        "clientMajor": "1",
        "clientMinor": "0",
        "generatedAtUtc": now,
        "providerId": "gate-fixture",
        "baseRemotePrefix": "gate-fixture/code",
        "files": [code_file],
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
        "config_files": 1,
        "code_files": 1,
    }


def main() -> int:
    print(json.dumps(build(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
