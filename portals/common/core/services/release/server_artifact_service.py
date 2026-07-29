# -*- coding: utf-8 -*-
"""Server artifact registration and storage (P2-01 Step 1)."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import DATA_DIR
from repositories import server_artifacts_repo

_ARTIFACT_ROOT = os.path.join(DATA_DIR, "server_artifacts")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _artifact_dir(project_id: str) -> str:
    path = os.path.join(_ARTIFACT_ROOT, str(project_id or "default"))
    os.makedirs(path, exist_ok=True)
    return path


def _checksum_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_artifact(project_id: str, payload: Dict[str, Any], *, source_path: str = "") -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid:
        raise ValueError("project_id 必填")
    body = dict(payload or {})
    artifact_id = str(body.get("artifact_id") or f"sart-{uuid.uuid4().hex[:12]}").strip()
    version_label = str(body.get("version_label") or body.get("version") or "").strip()
    protocol_version = str(body.get("protocol_version") or "").strip()
    bundle_path = str(body.get("bundle_path") or source_path or "").strip()

    stored_path = bundle_path
    checksum = str(body.get("checksum") or "").strip()
    if source_path and os.path.isfile(source_path):
        ext = os.path.splitext(source_path)[1] or ".zip"
        dest = os.path.join(_artifact_dir(pid), f"{artifact_id}{ext}")
        shutil.copy2(source_path, dest)
        stored_path = dest
        checksum = checksum or _checksum_file(dest)
    elif bundle_path and os.path.isfile(bundle_path):
        checksum = checksum or _checksum_file(bundle_path)
        stored_path = bundle_path
    elif bundle_path and not checksum:
        raise ValueError("bundle_path 不存在且未提供 checksum")

    extra = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    if body.get("oss_url"):
        extra["oss_url"] = str(body.get("oss_url"))

    row = server_artifacts_repo.upsert_artifact(
        {
            "artifact_id": artifact_id,
            "project_id": pid,
            "version_label": version_label,
            "bundle_path": stored_path,
            "checksum": checksum,
            "protocol_version": protocol_version,
            "payload": extra,
            "created_at": _now_iso(),
        }
    )
    return row


def get_artifact(artifact_id: str) -> Optional[Dict[str, Any]]:
    return server_artifacts_repo.get_artifact(artifact_id)


def list_artifacts(project_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    return server_artifacts_repo.list_artifacts(project_id, limit=limit)
