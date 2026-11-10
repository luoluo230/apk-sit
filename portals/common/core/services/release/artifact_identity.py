# -*- coding: utf-8 -*-
"""Client artifact identity helpers for promote hardening (P3-03 Wave C)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def extract_artifact_identity(source: Dict[str, Any]) -> Dict[str, str]:
    """Pull artifact_id + sha256 from bundle/client/version-shaped dicts."""
    source = source if isinstance(source, dict) else {}
    client = source.get("client") if isinstance(source.get("client"), dict) else {}
    payload = source.get("payload") if isinstance(source.get("payload"), dict) else {}
    nested_client = payload.get("client") if isinstance(payload.get("client"), dict) else {}
    candidates = (source, client, nested_client, payload)
    artifact_id = ""
    sha256 = ""
    for row in candidates:
        if not artifact_id:
            artifact_id = str(
                row.get("artifact_id")
                or row.get("apk_artifact_id")
                or row.get("primary_artifact_id")
                or ""
            ).strip()
        if not sha256:
            sha256 = str(
                row.get("sha256")
                or row.get("apk_sha256")
                or row.get("digest")
                or row.get("artifact_sha256")
                or ""
            ).strip()
        arts = row.get("artifacts")
        if isinstance(arts, list):
            for item in arts:
                if not isinstance(item, dict):
                    continue
                if str(item.get("artifact_type") or item.get("type") or "").lower() not in ("", "apk", "ipa", "primary"):
                    continue
                if not artifact_id:
                    artifact_id = str(item.get("artifact_id") or "").strip()
                if not sha256:
                    sha256 = str(item.get("sha256") or item.get("digest") or "").strip()
        if artifact_id and sha256:
            break
    return {"artifact_id": artifact_id, "sha256": sha256}


def require_matching_artifact_identity(source: Dict[str, Any], target: Dict[str, Any] | None = None) -> Dict[str, str]:
    """Require source identity; if target given, require exact id+sha256 match."""
    src = extract_artifact_identity(source)
    if not src["artifact_id"] or not src["sha256"]:
        raise ValueError("源制品缺少 artifact_id 或 sha256，禁止跨环境晋级；请使用带摘要的完整构建产物")
    if target is None:
        return src
    dst = extract_artifact_identity(target)
    if not dst["artifact_id"] or not dst["sha256"]:
        # Target may be empty on promote into new env — identity is carried from source only.
        return src
    if dst["artifact_id"] != src["artifact_id"] or dst["sha256"] != src["sha256"]:
        raise ValueError(
            "晋级被阻止：目标环境制品与源 Bundle 的 artifact_id/sha256 不一致，禁止替换为不同构建产物"
        )
    return src


def stamp_identity_on_client(client: Dict[str, Any], identity: Dict[str, str]) -> Dict[str, Any]:
    out = dict(client or {})
    if identity.get("artifact_id"):
        out["artifact_id"] = identity["artifact_id"]
    if identity.get("sha256"):
        out["sha256"] = identity["sha256"]
        out["apk_sha256"] = identity["sha256"]
    return out


def artifact_rows_with_identity(
    version: Dict[str, Any],
    identity: Dict[str, str] | None = None,
) -> List[Tuple[str, str, str, Dict[str, Any]]]:
    """Extend classic (type, url, path) rows with identity payload for DB insert."""
    from services.release.order_helpers import _artifact_rows

    ident = identity or extract_artifact_identity(version)
    rows = []
    for artifact_type, url, path in _artifact_rows(version):
        payload: Dict[str, Any] = {}
        if artifact_type == "apk" and ident:
            if ident.get("artifact_id"):
                payload["artifact_id"] = ident["artifact_id"]
            if ident.get("sha256"):
                payload["sha256"] = ident["sha256"]
        rows.append((artifact_type, url, path, payload))
    return rows
