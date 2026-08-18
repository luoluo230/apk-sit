# -*- coding: utf-8 -*-
"""Cross-environment artifact promotion — clone published bundles to higher env scopes."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from models.data import get_channel_by_id, project_versions_db, projects_db
from models.db import get_cursor, init_db
from services.release.env_registry import get_project_env_defs, normalize_release_env_key, project_env_label
from services.release.order_helpers import _artifact_rows, _decode, _event, _find_version, _json, _now_iso, _order_id
from services.release.scope_resolver import resolve_scope, resolve_topology_binding_for_scope

_ENV_RANK = {
    "development": 10,
    "testing": 20,
    "staging": 30,
    "production": 40,
}


def _env_rank(env_key: str) -> int:
    return int(_ENV_RANK.get(normalize_release_env_key(env_key), 0))


def _next_env_keys(project_id: str, source_env: str) -> List[str]:
    src_rank = _env_rank(source_env)
    out: List[str] = []
    for row in get_project_env_defs(project_id):
        ek = str(row.get("env_key") or "").strip()
        if _env_rank(ek) > src_rank:
            out.append(ek)
    return sorted(out, key=_env_rank)


def _bundle_row(bundle_id: str) -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            """
            SELECT bundle_id, release_order_id, project_id, scope_id, env_key, channel_id,
                   platform, version_name, version_code, publish_status, payload, published_at
            FROM release_bundles WHERE bundle_id=?
            """,
            (bundle_id,),
        ).fetchone()
    if not row:
        return {}
    payload = _decode(row["payload"], {}) or {}
    return {
        "bundle_id": str(row["bundle_id"] or ""),
        "release_order_id": str(row["release_order_id"] or ""),
        "project_id": str(row["project_id"] or ""),
        "scope_id": str(row["scope_id"] or ""),
        "env_key": normalize_release_env_key(str(row["env_key"] or "")),
        "channel_id": str(row["channel_id"] or ""),
        "platform": str(row["platform"] or "android").lower(),
        "version_name": str(row["version_name"] or ""),
        "version_code": str(row["version_code"] or ""),
        "publish_status": str(row["publish_status"] or ""),
        "published_at": str(row["published_at"] or ""),
        "client": dict(payload.get("client") or payload),
        "payload": payload,
    }


def _find_target_version(
    project_id: str,
    *,
    env_key: str,
    channel_id: str,
    platform: str,
    version_code: str,
    version_name: str,
) -> Dict[str, Any]:
    ek = normalize_release_env_key(env_key, project_id=project_id)
    plat = str(platform or "android").lower()
    code = str(version_code or "").strip()
    for row in project_versions_db.get(project_id) or []:
        if not isinstance(row, dict):
            continue
        row_env = normalize_release_env_key(
            row.get("env_key") or row.get("stage") or row.get("env") or "",
            project_id=project_id,
        )
        row_channel = str(row.get("channel_id") or row.get("channel") or "").strip()
        row_plat = str(row.get("platform") or "android").lower()
        row_code = str(row.get("version_code") or "").strip()
        if row_env == ek and row_channel == channel_id and row_plat == plat and row_code == code:
            return row
    if version_name:
        for row in project_versions_db.get(project_id) or []:
            if not isinstance(row, dict):
                continue
            row_env = normalize_release_env_key(
                row.get("env_key") or row.get("stage") or row.get("env") or "",
                project_id=project_id,
            )
            row_channel = str(row.get("channel_id") or row.get("channel") or "").strip()
            row_plat = str(row.get("platform") or "android").lower()
            row_name = str(row.get("version_name") or "").strip()
            if row_env == ek and row_channel == channel_id and row_plat == plat and row_name == version_name:
                return row
    return {}


def list_promotion_candidates(project_id: str) -> List[Dict[str, Any]]:
    """Published bundles that can advance to a higher environment."""
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT bundle_id, project_id, env_key, channel_id, platform, version_name, version_code,
                   publish_status, published_at, scope_id
            FROM release_bundles
            WHERE project_id=? AND publish_status='published'
            ORDER BY published_at DESC
            LIMIT 200
            """,
            (project_id,),
        ).fetchall()
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        ek = normalize_release_env_key(str(row["env_key"] or ""), project_id=project_id)
        cid = str(row["channel_id"] or "")
        plat = str(row["platform"] or "android").lower()
        key = f"{ek}:{cid}:{plat}:{row['version_code']}"
        if key in seen:
            continue
        seen.add(key)
        targets = _next_env_keys(project_id, ek)
        if not targets:
            continue
        ch = get_channel_by_id(cid) or {}
        target_rows = []
        for target_env in targets:
            version = _find_target_version(
                project_id,
                env_key=target_env,
                channel_id=cid,
                platform=plat,
                version_code=str(row["version_code"] or ""),
                version_name=str(row["version_name"] or ""),
            )
            target_rows.append(
                {
                    "env_key": target_env,
                    "env_label": project_env_label(project_id, target_env),
                    "version_ready": bool(version),
                    "version_id": str(version.get("id") or "") if version else "",
                }
            )
        out.append(
            {
                "bundle_id": str(row["bundle_id"] or ""),
                "source_env_key": ek,
                "source_env_label": project_env_label(project_id, ek),
                "channel_id": cid,
                "channel_name": str(ch.get("name") or cid),
                "platform": plat,
                "version_name": str(row["version_name"] or ""),
                "version_code": str(row["version_code"] or ""),
                "published_at": str(row["published_at"] or ""),
                "scope_id": str(row["scope_id"] or ""),
                "target_envs": target_rows,
            }
        )
    return out


def promote_bundle_to_env(
    project_id: str,
    source_bundle_id: str,
    target_env_key: str,
    actor: str,
    *,
    note: str = "",
) -> Dict[str, Any]:
    """Promote a published bundle's artifacts into a higher environment release order."""
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    source = _bundle_row(str(source_bundle_id or "").strip())
    if not source:
        raise ValueError("源 Bundle 不存在")
    if source["project_id"] != project_id:
        raise ValueError("Bundle 不属于该项目")
    if source["publish_status"] != "published":
        raise ValueError("仅已发布 Bundle 可晋级")
    target_env = normalize_release_env_key(target_env_key, project_id=project_id)
    if _env_rank(target_env) <= _env_rank(source["env_key"]):
        raise ValueError("目标环境必须高于源环境")
    channel_id = source["channel_id"]
    platform = source["platform"]
    version = _find_target_version(
        project_id,
        env_key=target_env,
        channel_id=channel_id,
        platform=platform,
        version_code=source["version_code"],
        version_name=source["version_name"],
    )
    if not version:
        raise ValueError(
            f"目标环境 {project_env_label(project_id, target_env)} 缺少匹配的 VersionCode "
            f"({source['version_name']} / {source['version_code']})，请先在版本管理中创建"
        )
    client = dict(source.get("client") or {})
    for field in ("apk_url", "resource_url", "config_url", "apk_version", "resource_version", "config_version"):
        if client.get(field) and not version.get(field):
            version[field] = client.get(field)
    scope = resolve_scope(project_id, target_env, channel_id, platform=platform, auto_create=True)
    binding = resolve_topology_binding_for_scope(scope, str(version.get("version_name") or ""))
    order_id = _order_id()
    now = _now_iso()
    promotion_meta = {
        "promoted_from_bundle_id": source["bundle_id"],
        "promoted_from_env_key": source["env_key"],
        "promoted_from_order_id": source["release_order_id"],
        "promotion_note": str(note or "").strip(),
        "promoted_at": now,
        "promoted_by": actor,
    }
    record_payload = {
        "reason": note or f"制品晋级 — 自 {project_env_label(project_id, source['env_key'])} 晋级",
        "version_snapshot": version,
        "topology_binding_snapshot": binding,
        "promotion": promotion_meta,
    }
    artifacts = _artifact_rows(version)
    has_artifacts = all(url or path for _, url, path in artifacts[:3])
    if not has_artifacts and client:
        artifacts = [
            ("apk", str(client.get("apk_url") or ""), ""),
            ("resource", str(client.get("resource_url") or ""), ""),
            ("config", str(client.get("config_url") or ""), ""),
        ]
        has_artifacts = all(url for _, url, _ in artifacts)
    if not has_artifacts:
        raise ValueError("源 Bundle 缺少可晋级的产物 URL")
    status = "artifacts_ready"
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO release_orders (
                release_order_id, project_id, env_key, channel_id, platform, version_id,
                version_name, version_code, scope_id, topology_id, topology_binding_source,
                runtime_run_id, bundle_id, status, reason, payload, created_by, approved_by,
                created_at, updated_at, published_at, batch_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                order_id,
                project_id,
                target_env,
                channel_id,
                platform,
                str(version.get("id") or ""),
                str(version.get("version_name") or source["version_name"]),
                str(version.get("version_code") or source["version_code"]),
                str(scope.get("scope_id") or ""),
                str(binding.get("topology_id") or ""),
                str(binding.get("binding_source") or ""),
                "",
                "",
                status,
                record_payload["reason"],
                _json(record_payload),
                actor,
                "",
                now,
                now,
                "",
                "",
            ),
        )
        for artifact_type, url, path in artifacts:
            cur.execute(
                """
                INSERT INTO release_order_artifacts (
                    release_order_id, artifact_type, artifact_url, artifact_path, status, payload, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (order_id, artifact_type, url, path, "registered" if url or path else "missing", "{}", now, now),
            )
        _event(
            cur,
            order_id,
            "promoted",
            actor,
            "",
            status,
            {"source_bundle_id": source["bundle_id"], "target_env_key": target_env},
        )
    from services.release.order_crud import get_release_order

    order = get_release_order(project_id, order_id)
    return {
        "release_order_id": order_id,
        "order": order,
        "promotion": promotion_meta,
        "next_action": "precheck",
        "edit_href": f"/admin/projects/{project_id}/release-orders/{order_id}/edit?env_key={target_env}",
    }
