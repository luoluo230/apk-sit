# -*- coding: utf-8 -*-
"""Release policy, defaults, and pipeline/delivery readiness for release orders."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from repositories.admin import projects_repo
from services.admin.version_service import _get_group_meta
from services.release.env_registry import get_project_env_defs, normalize_release_env_key
from services.release.scope_resolver import resolve_scope, resolve_topology_binding_for_scope

FORM_DEPTH_MINIMAL = "minimal"
FORM_DEPTH_STANDARD = "standard"
FORM_DEPTH_FULL = "full"

ENV_DEFAULT_FORM_DEPTH = {
    "development": FORM_DEPTH_MINIMAL,
    "testing": FORM_DEPTH_MINIMAL,
    "staging": FORM_DEPTH_STANDARD,
    "production": FORM_DEPTH_FULL,
}

DEFAULT_RELEASE_DEFAULTS: Dict[str, str] = {
    "validation_plan": (
        "1. 客户端冷启动与登录\n"
        "2. 热更资源/配置/代码包拉取与版本校验\n"
        "3. 核心玩法与玩家数据读写"
    ),
    "rollback_plan": (
        "1. 触发条件满足时暂停灰度扩量\n"
        "2. 恢复上一已发布 Bundle 快照\n"
        "3. 复验登录、热更与核心链路"
    ),
    "release_description": "本次发布变更说明（功能、影响范围、回滚预案已对齐）。",
    "release_window": "",
}

DEFAULT_RELEASE_POLICY: Dict[str, Any] = {
    "form_depth": FORM_DEPTH_MINIMAL,
    "require_approval": False,
    "allow_gray_release": True,
}


def _env_row(project_id: str, env_key: str) -> dict:
    key = normalize_release_env_key(env_key, project_id=project_id)
    for row in get_project_env_defs(project_id):
        if str(row.get("env_key") or "").strip().lower() == key:
            return dict(row)
    return {}


def get_project_release_defaults(project_id: str) -> Dict[str, str]:
    proj = projects_repo.get_project(project_id) or {}
    raw = proj.get("release_defaults")
    if not isinstance(raw, dict):
        raw = {}
    out = dict(DEFAULT_RELEASE_DEFAULTS)
    for key in DEFAULT_RELEASE_DEFAULTS:
        val = str(raw.get(key) or "").strip()
        if val:
            out[key] = val
    return out


def normalize_release_policy(raw: Optional[dict], env_key: str, project_id: str = "") -> Dict[str, Any]:
    ek = normalize_release_env_key(env_key, project_id=project_id) if env_key else "development"
    policy = dict(DEFAULT_RELEASE_POLICY)
    policy["form_depth"] = ENV_DEFAULT_FORM_DEPTH.get(ek, FORM_DEPTH_STANDARD)
    if ek in ("production", "prod"):
        policy["require_approval"] = True
    if isinstance(raw, dict):
        depth = str(raw.get("form_depth") or "").strip().lower()
        if depth in (FORM_DEPTH_MINIMAL, FORM_DEPTH_STANDARD, FORM_DEPTH_FULL):
            policy["form_depth"] = depth
        if "require_approval" in raw:
            policy["require_approval"] = bool(raw.get("require_approval"))
        if "allow_gray_release" in raw:
            policy["allow_gray_release"] = bool(raw.get("allow_gray_release"))
        for src, dst in (
            ("default_validation_plan", "validation_plan"),
            ("default_rollback_plan", "rollback_plan"),
            ("default_release_description", "release_description"),
        ):
            if str(raw.get(src) or "").strip():
                policy[dst] = str(raw.get(src) or "").strip()
    return policy


def get_env_release_policy(project_id: str, env_key: str) -> Dict[str, Any]:
    row = _env_row(project_id, env_key)
    raw_policy = row.get("release_policy") if isinstance(row.get("release_policy"), dict) else {}
    policy = normalize_release_policy(raw_policy, env_key, project_id=project_id)
    defaults = get_project_release_defaults(project_id)
    if not str(policy.get("validation_plan") or "").strip():
        policy["validation_plan"] = defaults.get("validation_plan") or ""
    if not str(policy.get("rollback_plan") or "").strip():
        policy["rollback_plan"] = defaults.get("rollback_plan") or ""
    if not str(policy.get("release_description") or "").strip():
        policy["release_description"] = defaults.get("release_description") or ""
    policy["env_key"] = normalize_release_env_key(env_key, project_id=project_id)
    return policy


def resolve_jenkins_job(
    version: Optional[dict],
    group_meta: Optional[dict],
    channel_id: str = "",
    project_id: str = "",
) -> str:
    """Resolve effective Jenkins job for a build target.

    Resolution order (high → low):
      1. Version group `jenkins_job_overrides[channel]` — per-channel override at group level
      2. Project-level `channel_bindings[].jenkins_job` — project-wide channel binding
      3. Version group `jenkins_job_id` — group default
      4. Legacy VC `jenkins_job_id` — fallback for unmigrated data
    """
    version = version or {}
    group_meta = group_meta or {}
    cid = str(channel_id or version.get("channel") or version.get("channel_id") or "").strip()
    overrides = group_meta.get("jenkins_job_overrides")
    if isinstance(overrides, dict) and cid:
        override = str(overrides.get(cid) or "").strip()
        if override:
            return override
    if project_id and cid:
        binding_job = _project_channel_binding_job(project_id, cid)
        if binding_job:
            return binding_job
    group_job = str(group_meta.get("jenkins_job_id") or "").strip()
    if group_job:
        return group_job
    return str(version.get("jenkins_job_id") or version.get("jenkins_job") or "").strip()


def _project_channel_binding_job(project_id: str, channel_id: str) -> str:
    """Look up jenkins_job from project-level channel_bindings list."""
    if not project_id or not channel_id:
        return ""
    try:
        proj = projects_repo.get_project(project_id) or {}
    except Exception:
        return ""
    bindings = proj.get("channel_bindings")
    if not isinstance(bindings, list):
        return ""
    cid = channel_id.strip()
    for row in bindings:
        if not isinstance(row, dict):
            continue
        if str(row.get("channel_id") or "").strip() != cid:
            continue
        return str(row.get("jenkins_job") or "").strip()
    return ""


def _pipeline_has_content(pipeline: dict) -> bool:
    if not isinstance(pipeline, dict) or not pipeline:
        return False
    for step in ("config_export", "resource_build", "hot_release", "apk_build"):
        block = pipeline.get(step)
        if not isinstance(block, dict):
            continue
        if block.get("enabled"):
            return True
        if any(str(block.get(k) or "").strip() for k in block if k != "enabled"):
            return True
    return bool(str(pipeline.get("git_branch") or "").strip())


def _pipeline_step_labels() -> List[tuple]:
    return [
        ("config_export", "配置导出"),
        ("resource_build", "资源打包"),
        ("hot_release", "热更发布"),
        ("apk_build", "安装包"),
    ]


def _missing_pipeline_steps(pipeline: dict) -> List[str]:
    if not isinstance(pipeline, dict):
        return [label for _, label in _pipeline_step_labels()]
    missing: List[str] = []
    for key, label in _pipeline_step_labels():
        block = pipeline.get(key)
        if isinstance(block, dict) and block.get("enabled"):
            continue
        missing.append(label)
    return missing


def _pipeline_summary(pipeline: dict) -> str:
    if not isinstance(pipeline, dict):
        return ""
    parts: List[str] = []
    for key, label in _pipeline_step_labels():
        block = pipeline.get(key) or {}
        if isinstance(block, dict) and block.get("enabled"):
            parts.append(label)
    return " · ".join(parts)


def assess_pipeline_readiness(
    version: Optional[dict],
    group_meta: Optional[dict] = None,
    channel_id: str = "",
    project_id: str = "",
) -> Dict[str, Any]:
    version = version or {}
    group_meta = group_meta or {}
    template = group_meta.get("pipeline_template") if isinstance(group_meta.get("pipeline_template"), dict) else {}
    legacy_pipeline = version.get("pipeline") if isinstance(version.get("pipeline"), dict) else {}

    if project_id and version:
        from services.admin.version_service import resolve_effective_jenkins, resolve_effective_pipeline

        effective_pipeline = resolve_effective_pipeline(project_id, version)
        jenkins = resolve_effective_jenkins(project_id, version)
        jenkins_instance = str(jenkins.get("jenkins_instance_id") or "").strip()
        jenkins_job = str(jenkins.get("jenkins_job_id") or "").strip()
    else:
        effective_pipeline = template if _pipeline_has_content(template) else legacy_pipeline
        jenkins_instance = str(
            group_meta.get("jenkins_instance_id") or version.get("jenkins_instance_id") or ""
        ).strip()
        jenkins_job = resolve_jenkins_job(version, group_meta, channel_id, project_id=project_id)

    has_pipeline = _pipeline_has_content(effective_pipeline)
    missing_steps = _missing_pipeline_steps(effective_pipeline) if has_pipeline else []
    checks = {
        "jenkins_instance": bool(jenkins_instance),
        "jenkins_job": bool(jenkins_job),
        "pipeline": has_pipeline,
    }
    ready = all(checks.values())

    if _pipeline_has_content(template):
        source = "version_group"
    elif _pipeline_has_content(legacy_pipeline):
        source = "legacy_vc"
    elif has_pipeline:
        source = "lazy_init"
    else:
        source = "none"

    if not checks["jenkins_instance"] and not checks["jenkins_job"] and not has_pipeline:
        status = "unconfigured"
    elif ready and not missing_steps:
        status = "ready"
    else:
        status = "partial"

    missing: List[str] = []
    if not checks["jenkins_instance"]:
        missing.append("Jenkins 实例")
    if not checks["jenkins_job"]:
        missing.append("Jenkins Job")
    if not has_pipeline:
        missing.append("管线四步配置")
    elif missing_steps:
        missing.extend(missing_steps)

    return {
        "ready": ready,
        "status": status,
        "checks": checks,
        "jenkins_instance_id": jenkins_instance,
        "jenkins_job_id": jenkins_job,
        "pipeline_summary": _pipeline_summary(effective_pipeline),
        "missing": missing,
        "missing_pipeline_steps": missing_steps,
        "source": source,
    }


def assess_delivery_readiness(
    project_id: str,
    version: dict,
    env_key: str,
    channel_id: str,
    platform: str,
) -> Dict[str, Any]:
    vn = str(version.get("version_name") or "").strip()
    group_meta = _get_group_meta(project_id, vn, env_key, platform)
    pipeline_state = assess_pipeline_readiness(version, group_meta, channel_id, project_id=project_id)
    scope = resolve_scope(project_id, env_key, channel_id, platform=platform, auto_create=False)
    binding = resolve_topology_binding_for_scope(scope or {}, vn) if scope else {}
    topology_id = str(binding.get("topology_id") or "").strip()
    artifact_ready = bool(
        str(version.get("apk_path") or "").strip()
        or str(version.get("resource_path") or "").strip()
        or str(version.get("config_path") or "").strip()
        or version.get("apk_status") == "found"
    )
    checks = dict(pipeline_state.get("checks") or {})
    checks["topology"] = bool(topology_id)
    checks["artifacts"] = artifact_ready
    score_items = ["jenkins_instance", "jenkins_job", "pipeline", "topology", "artifacts"]
    passed = sum(1 for key in score_items if checks.get(key))
    return {
        "ready": pipeline_state.get("ready") and checks["topology"],
        "pipeline_ready": pipeline_state.get("ready"),
        "checks": checks,
        "percent": int(round(passed / len(score_items) * 100)),
        "topology_id": topology_id,
        "binding_source": str(binding.get("binding_source_label") or binding.get("binding_source") or ""),
        "pipeline": pipeline_state,
    }


def get_required_plan_fields(project_id: str, env_key: str) -> List[str]:
    policy = get_env_release_policy(project_id, env_key)
    depth = policy.get("form_depth") or FORM_DEPTH_STANDARD
    base = ["reason", "owner"]
    if depth == FORM_DEPTH_STANDARD:
        return base + ["release_window", "release_description"]
    if depth == FORM_DEPTH_FULL:
        return base + [
            "release_window",
            "release_description",
            "validation_plan",
            "rollback_plan",
        ]
    return base


def apply_release_defaults_to_payload(
    project_id: str,
    env_key: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(payload or {})
    policy = get_env_release_policy(project_id, env_key)
    defaults = get_project_release_defaults(project_id)
    for key in ("validation_plan", "rollback_plan", "release_description", "release_window"):
        if not str(out.get(key) or "").strip():
            src = str(policy.get(key) or defaults.get(key) or "").strip()
            if src:
                out[key] = src
    return out


def build_config_href(
    project_id: str,
    version: dict,
    entry_from: str = "version-group",
) -> str:
    from urllib.parse import urlencode

    vid = str(version.get("id") or "").strip()
    params = {
        "from": entry_from,
        "version_name": str(version.get("version_name") or "").strip(),
        "env_key": normalize_release_env_key(
            version.get("env_key") or version.get("stage") or "development",
            project_id=project_id,
        ),
        "platform": str(version.get("platform") or "android").strip().lower(),
        "channel_id": str(version.get("channel") or version.get("channel_id") or "").strip(),
        "version_code": str(version.get("version_code") or "").strip(),
    }
    if vid:
        return f"/admin/projects/{project_id}/versions/{vid}/build-config?{urlencode({k: v for k, v in params.items() if v})}"
    return f"/admin/projects/{project_id}/version-groups/build-config?{urlencode({k: v for k, v in params.items() if v})}"


def release_order_form_context(
    project_id: str,
    version_id: str = "",
    env_key: str = "",
    channel_id: str = "",
    platform: str = "",
) -> Dict[str, Any]:
    from repositories.admin import versions_repo

    version: dict = {}
    versions = versions_repo.list_versions(project_id) if versions_repo.has_project(project_id) else []
    if version_id:
        version = next((row for row in versions if str(row.get("id") or "") == str(version_id)), {})
    if not version and env_key and channel_id and platform:
        for row in versions:
            row_ek = normalize_release_env_key(row.get("env_key") or row.get("stage") or "", project_id=project_id)
            if row_ek != normalize_release_env_key(env_key, project_id=project_id):
                continue
            if str(row.get("channel") or row.get("channel_id") or "").strip() != str(channel_id).strip():
                continue
            if str(row.get("platform") or "").strip().lower() != str(platform).strip().lower():
                continue
            version = dict(row)
            break
    ek = normalize_release_env_key(
        env_key or version.get("env_key") or version.get("stage") or "development",
        project_id=project_id,
    )
    cid = str(channel_id or version.get("channel") or version.get("channel_id") or "").strip()
    plat = str(platform or version.get("platform") or "android").strip().lower()
    policy = get_env_release_policy(project_id, ek)
    delivery = assess_delivery_readiness(project_id, version, ek, cid, plat) if version else {
        "ready": False,
        "pipeline_ready": False,
        "checks": {},
        "percent": 0,
    }
    defaults = apply_release_defaults_to_payload(project_id, ek, {})
    build_href = build_config_href(project_id, version) if version else ""
    return {
        "release_policy": policy,
        "required_fields": get_required_plan_fields(project_id, ek),
        "release_defaults": defaults,
        "delivery_readiness": delivery,
        "build_config_href": build_href,
        "form_depth": policy.get("form_depth"),
    }
