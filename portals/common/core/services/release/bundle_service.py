# -*- coding: utf-8 -*-
"""ReleaseBundle CRUD and publish state machine."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from services.release.env_registry import normalize_release_env_key
from services.release.scope_ids import resolve_channel_id
from services.release.scope_resolver import resolve_network_profile, resolve_topology_binding_for_scope, resolve_topology_id
from services.release.storage import load_bundles
from services.commercial_release_plan import (
    DEFAULT_RESOURCE_SERVER,
    build_runtime_resolve_paths,
    normalize_release_channel,
    normalize_release_platform,
)


def _now_iso() -> str:
    return datetime.now().isoformat()


def compute_rollout_bucket(
    *,
    device_id: str = "",
    user_id: str = "",
    scope_id: str = "",
    bundle_id: str = "",
) -> int:
    """Stable 0..99 bucket from device_id or user_id (gray rollout)."""
    identity = str(device_id or user_id or "anonymous").strip()
    seed = "|".join([identity, str(scope_id or "").strip(), str(bundle_id or "").strip()])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def resolve_gray_rollout_bundle(
    bundle: Dict[str, Any],
    *,
    device_id: str = "",
    user_id: str = "",
    region: str = "",
) -> Dict[str, Any]:
    """Return effective bundle for client; on gray miss use superseded bundle or empty."""
    if not isinstance(bundle, dict) or not bundle:
        return {
            "in_rollout": False,
            "rollout_percentage": 100,
            "rollout_bucket": 0,
            "bundle": {},
            "gray_miss": False,
            "superseded_bundle_id": "",
        }
    client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
    try:
        rollout_percentage = max(0, min(100, int(client.get("rollout_percentage") if client.get("rollout_percentage") is not None else 100)))
    except (TypeError, ValueError):
        rollout_percentage = 100
    scope_id = str(bundle.get("scope_id") or "")
    bundle_id = str(bundle.get("bundle_id") or "")
    gray_strategy = str(bundle.get("gray_strategy") or client.get("gray_strategy") or "ratio").strip().lower()
    rollout_bucket = compute_rollout_bucket(
        device_id=device_id,
        user_id=user_id,
        scope_id=scope_id,
        bundle_id=bundle_id,
    )

    def _identity_in_rollout() -> bool:
        if rollout_percentage >= 100:
            return True
        if gray_strategy == "canary":
            canary_list = bundle.get("gray_canary_list") or client.get("gray_canary_list") or []
            if isinstance(canary_list, str):
                canary_list = [part.strip() for part in canary_list.split(",") if part.strip()]
            identity = str(device_id or user_id or "").strip()
            return bool(identity) and identity in {str(item).strip() for item in canary_list}
        if gray_strategy == "region":
            allowed = bundle.get("gray_regions") or client.get("gray_regions") or []
            if isinstance(allowed, str):
                allowed = [part.strip() for part in allowed.split(",") if part.strip()]
            region_norm = str(region or "").strip().lower()
            if not region_norm:
                return rollout_bucket < rollout_percentage
            return region_norm in {str(item).strip().lower() for item in allowed}
        return rollout_bucket < rollout_percentage

    base = {
        "rollout_percentage": rollout_percentage,
        "rollout_bucket": rollout_bucket,
        "gray_strategy": gray_strategy,
        "gray_miss": False,
        "superseded_bundle_id": "",
        "target_bundle_id": bundle_id,
    }
    if _identity_in_rollout():
        return {**base, "in_rollout": True, "bundle": bundle}
    superseded_id = str(bundle.get("supersedes_bundle_id") or "").strip()
    if superseded_id:
        previous = get_bundle(superseded_id)
        if previous:
            return {
                **base,
                "in_rollout": False,
                "gray_miss": True,
                "superseded_bundle_id": superseded_id,
                "bundle": previous,
            }
    return {**base, "in_rollout": False, "gray_miss": True, "bundle": {}}


def list_bundles(
    project_id: str = "",
    scope_id: str = "",
    status: str = "",
    platform: str = "",
) -> List[Dict[str, Any]]:
    rows = load_bundles()
    out = []
    plat_filter = str(platform or "").strip().lower()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if project_id and str(row.get("project_id") or "").strip() != project_id:
            continue
        if scope_id and str(row.get("scope_id") or "").strip() != scope_id:
            continue
        if status and str(row.get("publish_status") or "").strip() != status:
            continue
        if plat_filter in {"android", "ios"}:
            client = row.get("client") if isinstance(row.get("client"), dict) else {}
            row_plat = str(client.get("platform") or row.get("platform") or "").strip().lower()
            if row_plat != plat_filter:
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


_DIRECTORY_PROBE_KEYS = frozenset({"resource_url", "config_url"})
_PROBE_FALLBACKS = {
    "resource_url": "catalog_url",
    "config_url": "config_manifest_url",
}


def _unity_project_path_from_version(version_row: Dict[str, Any]) -> str:
    pipeline = version_row.get("pipeline") if isinstance(version_row.get("pipeline"), dict) else {}
    apk_build = pipeline.get("apk_build") if isinstance(pipeline.get("apk_build"), dict) else {}
    return str(apk_build.get("unity_project_path") or "").strip()


def _oss_object_exists(object_key: str, unity_project_path: str = "") -> Dict[str, Any]:
    key = str(object_key or "").strip().lstrip("/")
    if not key:
        return {"ok": False, "status": 0, "error": "missing oss key"}
    try:
        from services.oss_client_helper import get_bucket

        bucket, _ = get_bucket(unity_project_path or None)
        bucket.head_object(key)
        return {"ok": True, "status": 200, "method": "oss-head"}
    except Exception as exc:
        return {"ok": False, "status": 0, "method": "oss-head", "error": str(exc)}


def _resolve_apk_oss_key(version_row: Dict[str, Any], apk_url: str) -> str:
    apk_dl = version_row.get("apk_download") if isinstance(version_row.get("apk_download"), dict) else {}
    key = str(apk_dl.get("oss_remote_key") or "").strip().lstrip("/")
    if key:
        return key
    text = str(apk_url or "").strip()
    if ".aliyuncs.com/" in text:
        return text.split(".aliyuncs.com/", 1)[1].split("?", 1)[0].lstrip("/")
    return ""


def _evaluate_artifact_checks(
    targets: Dict[str, str],
    version_row: Dict[str, Any],
) -> tuple[Dict[str, Any], List[str]]:
    checks = {key: _check_remote_artifact(value) for key, value in targets.items()}
    for prefix_key, fallback_key in _PROBE_FALLBACKS.items():
        if prefix_key not in checks or checks[prefix_key].get("ok"):
            continue
        if fallback_key and checks.get(fallback_key, {}).get("ok"):
            checks[prefix_key] = {
                "ok": True,
                "status": checks[fallback_key].get("status", 200),
                "method": "fallback",
                "verified_via": fallback_key,
            }
    apk_url = str(targets.get("apk_url") or "")
    if apk_url and not checks.get("apk_url", {}).get("ok"):
        oss_key = _resolve_apk_oss_key(version_row, apk_url)
        if oss_key:
            oss_check = _oss_object_exists(oss_key, _unity_project_path_from_version(version_row))
            if oss_check.get("ok"):
                checks["apk_url"] = oss_check
    missing = [key for key, result in checks.items() if not bool(result.get("ok"))]
    return checks, missing


def build_client_bootstrap_snapshot(
    version_row: Dict[str, Any],
    scope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build runtime-bootstrap client payload aligned with commercial_startup_sequence_gate."""
    scope = scope if isinstance(scope, dict) else {}
    release_env = {
        "development": "Development",
        "testing": "Testing",
        "staging": "Staging",
        "production": "Production",
    }.get(
        normalize_release_env_key(scope.get("env_key") or version_row.get("env_key") or version_row.get("stage")),
        "Development",
    )
    release_channel = normalize_release_channel(
        str(version_row.get("channel_id") or version_row.get("channel") or scope.get("channel_id") or "common")
    )
    release_platform = normalize_release_platform(str(version_row.get("platform") or "android"))
    version_name = str(version_row.get("version_name") or "").strip()
    version_code = str(version_row.get("version_code") or "").strip()
    platform = str(version_row.get("platform") or "android").strip().lower()

    runtime_paths = build_runtime_resolve_paths(
        resource_server_url=str(version_row.get("resource_server_url") or ""),
        release_environment=release_env,
        release_channel=release_channel,
        release_platform=release_platform,
        release_version=version_name,
        version_code=version_code,
    )
    artifact_urls = _artifact_probe_targets(scope, version_row) if scope.get("scope_id") or scope.get("env_key") else {}
    resource_relative_path = str(runtime_paths.get("resource_relative_path") or "").strip("/")
    config_relative_path = str(runtime_paths.get("config_relative_path") or "").strip()
    code_relative_path = str(runtime_paths.get("code_relative_path") or "").strip()
    catalog_file_name = str(
        version_row.get("catalog_file_name") or runtime_paths.get("catalog_file_name") or ""
    ).strip().lstrip("/")

    min_client = str(version_row.get("min_client_version") or version_name).strip()
    max_client = str(version_row.get("max_client_version") or version_name).strip()
    rollout_raw = version_row.get("rollout_percentage")
    try:
        rollout_percentage = max(0, min(100, int(rollout_raw if rollout_raw is not None else 100)))
    except (TypeError, ValueError):
        rollout_percentage = 100

    resource_server = str(version_row.get("resource_server_url") or "").strip().rstrip("/") or DEFAULT_RESOURCE_SERVER

    return {
        "version_id": version_row.get("id"),
        "version_name": version_name,
        "version_code": version_code,
        "platform": platform,
        "apk_path": str(version_row.get("apk_path") or ""),
        "apk_url": str(version_row.get("apk_url") or ""),
        "resource_url": str(version_row.get("resource_url") or ""),
        "config_url": str(version_row.get("config_url") or ""),
        "code_url": str(version_row.get("code_url") or ""),
        "resource_path": str(version_row.get("resource_path") or resource_relative_path),
        "config_path": str(version_row.get("config_path") or config_relative_path),
        "code_path": str(version_row.get("code_path") or code_relative_path),
        "resource_relative_path": resource_relative_path,
        "config_relative_path": config_relative_path,
        "code_relative_path": code_relative_path,
        "catalog_file_name": catalog_file_name,
        "catalog_url": str(artifact_urls.get("catalog_url") or "").strip(),
        "config_manifest_url": str(
            artifact_urls.get("config_manifest_url") or runtime_paths.get("config_manifest_path") or ""
        ).strip(),
        "code_manifest_url": str(
            artifact_urls.get("code_manifest_url") or runtime_paths.get("code_manifest_path") or ""
        ).strip(),
        "min_client_version": min_client,
        "max_client_version": max_client,
        "rollout_percentage": rollout_percentage,
        "force_update": bool(version_row.get("force_update", False)),
        "is_revoked": bool(version_row.get("is_revoked", False)),
        "resource_server_url": resource_server,
    }


def _artifact_probe_targets(scope: Dict[str, Any], version_row: Dict[str, Any]) -> Dict[str, str]:
    release_env = {
        "development": "Development",
        "testing": "Testing",
        "staging": "Staging",
        "production": "Production",
    }.get(normalize_release_env_key(scope.get("env_key") or version_row.get("env_key") or version_row.get("stage")), "Development")
    release_channel = normalize_release_channel(
        str(version_row.get("channel_id") or version_row.get("channel") or scope.get("channel_id") or "common")
    )
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
    resource_base = str(version_row.get("resource_server_url") or "").strip().rstrip("/") or DEFAULT_RESOURCE_SERVER
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


def find_active_bundle(scope_id: str, *, platform: str = "") -> Dict[str, Any]:
    sid = str(scope_id or "").strip()
    plat = str(platform or "").strip().lower()
    for row in list_bundles(scope_id=sid, status="published", platform=plat if plat in {"android", "ios"} else ""):
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
    row_channel_id = resolve_channel_id(
        str(scope.get("project_id") or ""),
        str(version_row.get("channel_id") or version_row.get("channel") or ""),
    )
    scope_aligned = not row_scope_id or row_scope_id == scope_id
    env_aligned = not row_env_key or str(scope.get("env_key") or "") == normalize_release_env_key(row_env_key)
    channel_aligned = not row_channel_id or row_channel_id == str(scope.get("channel_id") or "")
    runtime_aligned = True
    runtime_topology_id = ""
    try:
        from services.ops.topology_registry import _resolve_topology_context

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
        artifact_checks, missing_artifacts = _evaluate_artifact_checks(artifact_urls, version_row)
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


def list_publishable_bundles(scope_id: str, *, platform: str = "") -> List[Dict[str, Any]]:
    """Bundles that can be activated on a scope (published history + superseded)."""
    sid = str(scope_id or "").strip()
    if not sid:
        return []
    plat = str(platform or "").strip().lower()
    active = find_active_bundle(sid, platform=plat if plat in {"android", "ios"} else "")
    active_id = str(active.get("bundle_id") or "")
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in list_bundles(scope_id=sid, platform=plat if plat in {"android", "ios"} else ""):
        bid = str(row.get("bundle_id") or "").strip()
        if not bid or bid in seen:
            continue
        seen.add(bid)
        status = str(row.get("publish_status") or "")
        if status not in {"published", "superseded", "revoked"}:
            continue
        client = row.get("client") if isinstance(row.get("client"), dict) else {}
        out.append({
            "bundle_id": bid,
            "release_order_id": str(row.get("release_order_id") or ""),
            "version_name": str(client.get("version_name") or row.get("version_name") or ""),
            "version_code": str(client.get("version_code") or row.get("version_code") or ""),
            "platform": str(client.get("platform") or row.get("platform") or plat),
            "publish_status": status,
            "published_at": str(row.get("published_at") or ""),
            "published_by": str(row.get("published_by") or ""),
            "is_active": bid == active_id,
        })
    return out
