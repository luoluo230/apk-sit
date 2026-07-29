# -*- coding: utf-8 -*-
"""Project onboarding orchestration — 0 to first quick-build in one API.

Plan: P1-02 Step 1 — create project, envs, version group, scope bootstrap.
"""

from __future__ import annotations

import copy
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from data.platforms import DEFAULT_PROJECT_PLATFORMS, is_valid_platform_id
from repositories.admin import projects_repo
from services.admin.envelope import attach_legacy_error, fail, ok
from services.admin import project_service, version_service
from services.release.env_registry import CANONICAL_ENV_KEYS, get_project_env_defs
from services.release.manifest_service import bootstrap_scopes_for_project, upsert_manifest
from services.release.scope_ids import build_scope_id, project_slug
from services.release.storage import find_manifest, load_manifests, load_scopes, save_manifests, save_scopes

_CORE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULTS_PATH = os.path.join(_CORE_DIR, "data", "onboarding_defaults.json")


def load_onboarding_defaults() -> Dict[str, Any]:
    try:
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_project_id(payload: Dict[str, Any]) -> str:
    explicit = str(payload.get("id") or payload.get("project_id") or "").strip()
    if explicit:
        return explicit
    slug = str(payload.get("slug") or "").strip()
    if slug:
        return slug
    name = str(payload.get("name") or "").strip()
    if not name:
        return ""
    compact = re.sub(r"\s+", "", name)
    return compact[:48] if compact else ""


def _normalize_env_keys(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        key = str(item or "").strip().lower()
        if key in CANONICAL_ENV_KEYS and key not in out:
            out.append(key)
    return out


def _normalize_platforms(raw: Any, defaults: Dict[str, Any]) -> List[str]:
    if isinstance(raw, list) and raw:
        out = [str(p).strip().lower() for p in raw if is_valid_platform_id(p)]
        return out or list(defaults.get("default_platforms") or DEFAULT_PROJECT_PLATFORMS)
    return list(defaults.get("default_platforms") or DEFAULT_PROJECT_PLATFORMS)


def _normalize_channels(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(c).strip() for c in raw if str(c).strip()]


def _validate_catalog(channel_ids: List[str], platform_ids: List[str]) -> Optional[str]:
    valid_channels = {(c.get("id") or "").strip() for c in projects_repo.list_channels()}
    for cid in channel_ids:
        if cid not in valid_channels:
            return f"渠道 {cid} 不存在于全局目录"
    for pid in platform_ids:
        if not is_valid_platform_id(pid):
            return f"平台 {pid} 无效"
    return None


def _merge_pipeline_template(payload: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    base = copy.deepcopy(defaults.get("pipeline_template") or {})
    app_name = str(payload.get("name") or payload.get("slug") or "").strip() or "MyGame"
    git_branch = str(
        payload.get("default_git_branch")
        or (payload.get("build_config") or {}).get("default_git_branch")
        or base.get("git_branch")
        or "main"
    ).strip()
    unity_path = str(payload.get("unity_project_path") or (payload.get("build_config") or {}).get("unity_project_path") or "").strip()
    output_base = str(payload.get("output_base_dir") or (payload.get("build_config") or {}).get("output_base_dir") or "").strip()
    seed = payload.get("seed_version_group") if isinstance(payload.get("seed_version_group"), dict) else {}
    version_name = str(seed.get("version_name") or "1.0.0").strip()
    channel_id = str(seed.get("channel_id") or (payload.get("channels") or [""])[0] or "").strip()

    cfg = base.setdefault("config_export", {})
    cfg["remote_prefix"] = str(cfg.get("remote_prefix") or "{app_name}").replace("{app_name}", app_name)
    cfg["client_version"] = version_name
    hot = base.setdefault("hot_release", {})
    if channel_id:
        hot["release_channel"] = channel_id
    apk = base.setdefault("apk_build", {})
    apk["app_name"] = app_name
    apk["git_branch"] = git_branch
    if unity_path:
        apk["unity_project_path"] = unity_path
    if output_base:
        apk["output_base_dir"] = output_base
    base["git_branch"] = git_branch
    return base


def _persist_project(project_id: str, proj: Dict[str, Any]) -> None:
    projects_repo.upsert_project(project_id, proj)


def _apply_release_environments(
    project_id: str,
    env_keys: List[str],
    channel_ids: List[str],
    platform_ids: List[str],
    *,
    jenkins_instance_id: str = "",
    jenkins_job_id: str = "",
) -> None:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return
    enabled = set(env_keys)
    rows: List[Dict[str, Any]] = []
    for row in get_project_env_defs(project_id):
        key = str(row.get("env_key") or "").strip().lower()
        item = dict(row)
        item["enabled"] = key in enabled
        if key in enabled:
            item["channels"] = list(channel_ids)
            item["platforms"] = list(platform_ids)
        rows.append(item)
    proj["release_environments"] = rows
    proj["platforms"] = list(platform_ids)
    if jenkins_instance_id:
        proj["jenkins_instance_id"] = jenkins_instance_id
    if jenkins_job_id:
        proj["jenkins_job_id"] = jenkins_job_id
    _persist_project(project_id, proj)


def _purge_onboard_artifacts(project_id: str) -> None:
    pid = str(project_id or "").strip()
    if not pid:
        return
    remaining_scopes = [row for row in load_scopes() if str(row.get("project_id") or "") != pid]
    save_scopes(remaining_scopes)
    manifests = [row for row in load_manifests() if str(row.get("project_id") or "") != pid]
    save_manifests(manifests)
    if projects_repo.has_project(pid):
        projects_repo.delete_project_versions(pid)
        projects_repo.delete_project(pid)


def _collect_scope_ids(project_id: str, env_keys: List[str], channel_ids: List[str], platform_ids: List[str]) -> List[str]:
    slug = project_slug(project_id)
    out: List[str] = []
    for env_key in env_keys:
        for channel_id in channel_ids:
            for platform in platform_ids:
                out.append(build_scope_id(slug, env_key, channel_id, platform))
    return out


def _build_next_actions(
    project_id: str,
    seed: Dict[str, Any],
    version_id: str,
) -> List[Dict[str, str]]:
    env_key = str(seed.get("env_key") or "development").strip()
    channel_id = str(seed.get("channel_id") or "").strip()
    version_qs = f"?version_id={version_id}" if version_id else ""
    actions = [
        {
            "label": "配置 Jenkins 管线",
            "url": f"/admin/projects/{project_id}/versions{version_qs}",
        },
        {
            "label": "启动 Dev Runtime",
            "url": f"/admin/projects/{project_id}/ops?env_key={env_key}",
        },
    ]
    if channel_id:
        actions.append(
            {
                "label": "打开 Build Journey",
                "url": f"/admin/projects/{project_id}/environments/{env_key}/channels/{channel_id}/build",
            }
        )
    return actions


def onboard_project(payload: Dict[str, Any], actor: str, tenant_id: str = "default") -> Tuple[Dict[str, Any], int]:
    """Atomically onboard a new project through version group + scope bootstrap."""
    data = dict(payload or {})
    defaults = load_onboarding_defaults()
    project_id = _resolve_project_id(data)
    name = str(data.get("name") or "").strip()
    if not project_id or not name:
        return attach_legacy_error(fail("项目名称与 ID 不能为空", code="validation_error")), 400

    channel_ids = _normalize_channels(data.get("channels"))
    if not channel_ids:
        return attach_legacy_error(fail("至少选择一个渠道", code="validation_error")), 400
    platform_ids = _normalize_platforms(data.get("platforms"), defaults)
    env_keys = _normalize_env_keys(data.get("env_keys")) or _normalize_env_keys(defaults.get("default_env_keys"))
    if not env_keys:
        return attach_legacy_error(fail("至少选择一个环境", code="validation_error")), 400

    catalog_err = _validate_catalog(channel_ids, platform_ids)
    if catalog_err:
        return attach_legacy_error(fail(catalog_err, code="validation_error")), 400

    seed = data.get("seed_version_group") if isinstance(data.get("seed_version_group"), dict) else {}
    seed_env = str(seed.get("env_key") or env_keys[0]).strip().lower()
    seed_channel = str(seed.get("channel_id") or channel_ids[0]).strip()
    seed_platform = str(seed.get("platform") or platform_ids[0]).strip().lower()
    seed_version_name = str(seed.get("version_name") or "1.0.0").strip()
    if seed_channel not in channel_ids:
        channel_ids = channel_ids + [seed_channel]
    if seed_platform not in platform_ids:
        platform_ids.append(seed_platform)

    cred_payload, cred_status = project_service.generate_credentials(project_id)
    if cred_status != 200:
        return attach_legacy_error(cred_payload), cred_status
    cred = cred_payload.get("data") if isinstance(cred_payload.get("data"), dict) else cred_payload

    create_payload: Dict[str, Any] = {
        "id": project_id,
        "name": name,
        "game_id": str(cred.get("game_id") or "").strip(),
        "game_key": str(cred.get("game_key") or "").strip(),
        "channels": channel_ids,
        "platforms": platform_ids,
        "editors": [actor] if actor else [],
        "build_config": data.get("build_config") if isinstance(data.get("build_config"), dict) else {},
    }
    for key in ("git_url", "unity_project_path", "output_base_dir", "default_git_branch", "git_branches", "app_name"):
        if key in data and data.get(key) not in (None, ""):
            create_payload[key] = data.get(key)
    jenkins_instance_id = str(data.get("jenkins_instance_id") or "").strip()
    jenkins_job_id = str(data.get("jenkins_job_id") or "").strip()
    if jenkins_instance_id:
        create_payload["jenkins_instance_id"] = jenkins_instance_id
    if jenkins_job_id:
        create_payload["jenkins_job_id"] = jenkins_job_id

    try:
        result, status = project_service.create_project(create_payload, actor, tenant_id)
        if status != 200:
            return attach_legacy_error(result), status

        _apply_release_environments(
            project_id,
            env_keys,
            channel_ids,
            platform_ids,
            jenkins_instance_id=jenkins_instance_id,
            jenkins_job_id=jenkins_job_id,
        )

        upsert_manifest(
            {
                "project_id": project_id,
                "project_slug": project_slug(project_id),
                "topology_pattern": "topology-{project_slug}-{env_key}-default",
                "default_scopes_per_env": True,
                "status": "active",
            }
        )

        pipeline_template = _merge_pipeline_template({**data, "name": name, "channels": channel_ids}, defaults)
        group_payload = {
            "version_name": seed_version_name,
            "env_key": seed_env,
            "platform": seed_platform,
            "pipeline_template": pipeline_template,
        }
        if jenkins_instance_id:
            group_payload["jenkins_instance_id"] = jenkins_instance_id
        if jenkins_job_id:
            group_payload["jenkins_job_id"] = jenkins_job_id
        group_result, group_status = version_service.create_version_group(project_id, actor, group_payload)
        if group_status != 200:
            raise ValueError(str(group_result.get("error") or "版本组创建失败"))

        seed_defaults = defaults.get("seed_version") if isinstance(defaults.get("seed_version"), dict) else {}
        version_payload = {
            "env_key": seed_env,
            "platform": seed_platform,
            "channel_id": seed_channel,
            "version_name": seed_version_name,
            "version_code": str(seed.get("version_code") or seed_defaults.get("version_code") or "1").strip(),
            "version_mode": str(seed.get("version_mode") or seed_defaults.get("version_mode") or "general").strip(),
        }
        if jenkins_instance_id:
            version_payload["jenkins_instance_id"] = jenkins_instance_id
        if jenkins_job_id:
            version_payload["jenkins_job_id"] = jenkins_job_id
        version_result, version_status = version_service.create_version(project_id, actor, version_payload)
        if version_status != 200:
            raise ValueError(str(version_result.get("error") or "版本创建失败"))

        bootstrap_scopes_for_project(project_id)

        proj = projects_repo.get_project(project_id) or {}
        version_row = version_result.get("version") if isinstance(version_result.get("version"), dict) else {}
        version_id = str(version_row.get("id") or "").strip()
        scope_ids = _collect_scope_ids(project_id, env_keys, channel_ids, platform_ids)
        body = {
            "project_id": project_id,
            "game_id": str(proj.get("game_id") or cred.get("game_id") or ""),
            "game_key": str(proj.get("game_key") or cred.get("game_key") or ""),
            "version_group_id": seed_version_name,
            "version_id": version_id,
            "scope_ids": scope_ids,
            "next_actions": _build_next_actions(project_id, {**seed, "env_key": seed_env, "channel_id": seed_channel}, version_id),
        }
        return ok(body, legacy={"success": True, **body}), 200
    except Exception as exc:
        if projects_repo.has_project(project_id):
            _purge_onboard_artifacts(project_id)
        return attach_legacy_error(fail(str(exc) or "项目初始化失败", code="onboard_failed")), 500
