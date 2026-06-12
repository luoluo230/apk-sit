# -*- coding: utf-8 -*-
"""ReleaseBundle CRUD and publish state machine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from services.release.env_registry import normalize_release_env_key
from services.release.scope_ids import resolve_channel_id
from services.release.scope_resolver import resolve_network_profile, resolve_topology_binding_for_scope, resolve_topology_id
from services.release.storage import load_bundles
from services.commercial_release_plan import build_runtime_resolve_paths, normalize_release_channel, normalize_release_platform


def _now_iso() -> str:
    return datetime.now().isoformat()


def list_bundles(
    project_id: str = "",
    scope_id: str = "",
    status: str = "",
) -> List[Dict[str, Any]]:
    rows = load_bundles()
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if project_id and str(row.get("project_id") or "").strip() != project_id:
            continue
        if scope_id and str(row.get("scope_id") or "").strip() != scope_id:
            continue
        if status and str(row.get("publish_status") or "").strip() != status:
            continue
        out.append(row)
    out.sort(key=lambda x: str(x.get("published_at") or x.get("created_at") or ""), reverse=True)
    return out


def get_bundle(bundle_id: str) -> Dict[str, Any]:
    bid = str(bundle_id or "").strip()
    for row in load_bundles():
        if isinstance(row, dict) and str(row.get("bundle_id") or "").strip() == bid:
            return row
    return {}


def _check_remote_artifact(url: str, *, timeout: float = 5.0) -> Dict[str, Any]:
    text = str(url or "").strip()
    if not text:
        return {"ok": False, "status": 0, "error": "missing url"}
    scheme = (urlparse(text).scheme or "").lower()
    if scheme not in ("http", "https"):
        return {"ok": False, "status": 0, "error": f"unsupported scheme: {scheme or 'unknown'}"}
    for method in ("HEAD", "GET"):
        try:
            req = Request(text, method=method)
            with urlopen(req, timeout=timeout) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                return {"ok": 200 <= status < 400, "status": status, "method": method}
        except HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            if method == "HEAD" and status in (403, 405):
                continue
            return {"ok": False, "status": status, "method": method, "error": str(exc)}
        except URLError as exc:
            return {"ok": False, "status": 0, "method": method, "error": str(exc.reason or exc)}
        except Exception as exc:
            return {"ok": False, "status": 0, "method": method, "error": str(exc)}
    return {"ok": False, "status": 0, "error": "artifact probe failed"}


def _artifact_probe_targets(scope: Dict[str, Any], version_row: Dict[str, Any]) -> Dict[str, str]:
    release_env = {
        "development": "Development",
        "testing": "Testing",
        "staging": "Staging",
        "production": "Production",
    }.get(normalize_release_env_key(scope.get("env_key") or version_row.get("env_key") or version_row.get("stage")), "Development")
    release_channel = normalize_release_channel(str(version_row.get("channel") or scope.get("channel_id") or "common"))
    release_platform = normalize_release_platform(str(version_row.get("platform") or "android"))
    runtime_paths = build_runtime_resolve_paths(
        resource_server_url=str(version_row.get("resource_server_url") or ""),
        release_environment=release_env,
        release_channel=release_channel,
        release_platform=release_platform,
        release_version=str(version_row.get("version_name") or ""),
        version_code=str(version_row.get("version_code") or ""),
    )
    resource_relative_path = str(version_row.get("resource_path") or runtime_paths.get("resource_relative_path") or "").strip("/")
    resource_base = str(version_row.get("resource_server_url") or "").strip().rstrip("/")
    catalog_file_name = str(version_row.get("catalog_file_name") or runtime_paths.get("catalog_file_name") or "").strip().lstrip("/")
    catalog_url = ""
    if resource_base and resource_relative_path and catalog_file_name:
        catalog_url = f"{resource_base}/{resource_relative_path}/{catalog_file_name}"
    return {
        "apk_url": str(version_row.get("apk_url") or "").strip(),
        "resource_url": str(version_row.get("resource_url") or "").strip(),
        "config_url": str(version_row.get("config_url") or "").strip(),
        "catalog_url": catalog_url,
        "config_manifest_url": str(runtime_paths.get("config_manifest_path") or "").strip(),
        "code_manifest_url": str(runtime_paths.get("code_manifest_path") or "").strip(),
    }


def find_active_bundle(scope_id: str) -> Dict[str, Any]:
    sid = str(scope_id or "").strip()
    for row in list_bundles(scope_id=sid, status="published"):
        return row
    return {}


def run_scope_precheck(scope: Dict[str, Any], version_row: Dict[str, Any], *, validate_artifacts: bool = False) -> Dict[str, Any]:
    scope_id = str(scope.get("scope_id") or "")
    version_name = str(version_row.get("version_name") or "").strip()
    network_profile, profile_source = resolve_network_profile(scope, version_name=version_name)
    topology_binding = resolve_topology_binding_for_scope(scope, version_name=version_name)
    topology_id = str(topology_binding.get("topology_id") or resolve_topology_id(scope, version_name=version_name) or "")
    client_keys = [
        "version_name",
        "version_code",
        "platform",
        "apk_url",
        "resource_url",
        "config_url",
        "apk_version",
        "resource_version",
        "config_version",
    ]
    missing_client = [k for k in client_keys if not str(version_row.get(k) or "").strip()]
    profile_keys = ("gateway_ws", "login_http", "game_ws", "ops_http")
    missing_profile = [k for k in profile_keys if not str((network_profile or {}).get(k) or "").strip()]
    row_scope_id = str(version_row.get("scope_id") or "").strip()
    row_env_key = str(version_row.get("env_key") or version_row.get("stage") or version_row.get("env") or "").strip()
    row_channel_id = resolve_channel_id(str(scope.get("project_id") or ""), str(version_row.get("channel") or ""))
    scope_aligned = not row_scope_id or row_scope_id == scope_id
    env_aligned = not row_env_key or str(scope.get("env_key") or "") == normalize_release_env_key(row_env_key)
    channel_aligned = not row_channel_id or row_channel_id == str(scope.get("channel_id") or "")
    runtime_aligned = True
    runtime_topology_id = ""
    try:
        from services.ops.helpers import _resolve_topology_context

        ctx = _resolve_topology_context(str(scope.get("project_id") or ""), str(scope.get("env_key") or ""), topology_id)
        runtime_topology_id = str((ctx.get("row") or {}).get("topology_id") or ctx.get("topology_id") or "")
        if runtime_topology_id and runtime_topology_id != topology_id:
            runtime_aligned = False
    except Exception:
        runtime_aligned = True

    alignment_errors = []
    if not scope_aligned:
        alignment_errors.append("scope_id")
    if not env_aligned:
        alignment_errors.append("env_key")
    if not channel_aligned:
        alignment_errors.append("channel_id")
    artifact_checks: Dict[str, Any] = {}
    missing_artifacts: List[str] = []
    if validate_artifacts:
        artifact_urls = _artifact_probe_targets(scope, version_row)
        artifact_checks = {key: _check_remote_artifact(value) for key, value in artifact_urls.items()}
        missing_artifacts = [key for key, result in artifact_checks.items() if not bool(result.get("ok"))]
    ok = not missing_client and not missing_profile and runtime_aligned and not alignment_errors and not missing_artifacts
    return {
        "ok": ok,
        "scope_id": scope_id,
        "topology_id": topology_id,
        "runtime_topology_id": runtime_topology_id,
        "topology_runtime_aligned": runtime_aligned,
        "scope_alignment_ok": scope_aligned,
        "env_alignment_ok": env_aligned,
        "channel_alignment_ok": channel_aligned,
        "alignment_errors": alignment_errors,
        "profile_source": profile_source,
        "binding_source": str(topology_binding.get("binding_source") or ""),
        "missing_client_fields": missing_client,
        "missing_profile_fields": missing_profile,
        "missing_artifact_fields": missing_artifacts,
        "artifact_targets": artifact_urls if validate_artifacts else {},
        "artifact_checks": artifact_checks,
        "network_profile_preview": network_profile,
        "checked_at": _now_iso(),
    }
