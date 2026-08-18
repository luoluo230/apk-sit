#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Register gameserver build zip with Portal (local import or internal webhook)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import base64
from pathlib import Path


def _repo_core() -> Path:
    script = Path(__file__).resolve()
    candidates = [
        script.parents[4] / "portals" / "common" / "core",
        Path(os.environ.get("APK_SITE_CORE", "")),
    ]
    for p in candidates:
        if p.is_dir():
            return p
    raise SystemExit(f"找不到 apk-site core: {candidates}")


def _checksum_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _register_local(project_id: str, body: dict, source_path: str) -> dict:
    core = _repo_core()
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    from services.release.server_artifact_service import register_artifact  # noqa: WPS433

    return register_artifact(project_id, body, source_path=source_path)


def _register_http(project_id: str, body: dict, source_path: str) -> dict:
    portal = os.environ.get("APKSITE_BASE_URL", "http://127.0.0.1:5003").strip().rstrip("/")
    secret = os.environ.get("JENKINS_BUILD_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise SystemExit("JENKINS_BUILD_WEBHOOK_SECRET required for HTTP registration")
    payload = dict(body)
    payload["project_id"] = project_id
    if source_path and Path(source_path).is_file():
        with open(source_path, "rb") as fh:
            payload["artifact_b64"] = base64.b64encode(fh.read()).decode("ascii")
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    import hmac

    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        f"{portal}/api/internal/jenkins/server-artifact",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Jenkins-Signature": f"sha256={sig}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Portal server-artifact HTTP {exc.code}: {detail}") from exc
    if not out.get("ok"):
        raise SystemExit(f"Portal server-artifact failed: {out}")
    return out.get("artifact") or out


def main() -> int:
    artifact_file = (
        os.environ.get("GAMESERVER_ARTIFACT")
        or os.environ.get("ARTIFACT_FILE")
        or ""
    ).strip()
    if not artifact_file or not Path(artifact_file).is_file():
        print(f"ERROR: gameserver artifact missing: {artifact_file}", file=sys.stderr)
        return 1

    project_id = os.environ.get("PROJECT_ID", "GomeKu").strip()
    version_label = os.environ.get("SERVER_VERSION_LABEL", os.environ.get("VERSION_NAME", "")).strip()
    protocol_version = os.environ.get("SERVER_PROTOCOL_VERSION", "v1").strip()
    artifact_id = os.environ.get("SERVER_ARTIFACT_ID", "").strip()
    checksum = os.environ.get("SERVER_ARTIFACT_CHECKSUM", "").strip() or _checksum_file(artifact_file)

    body = {
        "artifact_id": artifact_id,
        "version_label": version_label,
        "protocol_version": protocol_version,
        "checksum": checksum,
        "build_number": os.environ.get("BUILD_NUMBER", ""),
        "jenkins_instance_id": os.environ.get("JENKINS_INSTANCE_ID", ""),
    }
    mode = os.environ.get("SERVER_ARTIFACT_REGISTER_MODE", "local").strip().lower()
    if mode == "http":
        row = _register_http(project_id, body, artifact_file)
    else:
        try:
            row = _register_local(project_id, body, artifact_file)
        except Exception as exc:
            if os.environ.get("JENKINS_BUILD_WEBHOOK_SECRET"):
                print(f"WARN: local register failed ({exc}), falling back to HTTP", file=sys.stderr)
                row = _register_http(project_id, body, artifact_file)
            else:
                raise

    manifest = {"ok": True, "project_id": project_id, "artifact": row, "local_path": artifact_file}
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
