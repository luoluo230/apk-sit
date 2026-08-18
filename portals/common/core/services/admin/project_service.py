"""Project management service."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple

from models.data import get_approved_approval
from repositories.admin import projects_repo
from data.platforms import DEFAULT_PROJECT_PLATFORMS, is_valid_platform_id
from services.admin.envelope import ok, fail, attach_legacy_error
from services.admin.project_build_config_service import (
    apply_build_config_to_project_payload,
    build_config_for_api,
)

PROJECT_PHASES = [
    ("kickoff", "立项/预研"),
    ("prototype", "原型/白盒"),
    ("preprod", "预生产/绿光"),
    ("production", "正式开发"),
    ("alpha", "Alpha"),
    ("beta", "Beta"),
    ("polish", "调优/收尾"),
    ("launch", "上线/运营"),
    ("maintenance", "维护"),
]
PROJECT_ROLES = ["策划", "数值", "美术", "特效", "前端", "后端", "测试", "其他"]


def _normalize_public_url(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if not (s.startswith("http://") or s.startswith("https://")):
        s = "https://" + s
    return s.rstrip("/")


def _generate_unique_game_credentials(project_id: str):
    base = (project_id or "game").strip()[:24] or "game"
    game_id = f"{base}-{secrets.token_hex(8)}"
    existed_ids = {
        str((p or {}).get("game_id") or "").strip()
        for p in (projects_repo.list_projects() or {}).values()
        if isinstance(p, dict)
    }
    while game_id in existed_ids:
        game_id = f"{base}-{secrets.token_hex(8)}"
    raw = f"{project_id}:{secrets.token_hex(24)}:{datetime.now().isoformat()}:{uuid.uuid4().hex}"
    game_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return game_id, game_key


def generate_credentials(project_id: str) -> Tuple[Dict[str, Any], int]:
    game_id, game_key = _generate_unique_game_credentials(project_id or "project")
    return ok({"game_id": game_id, "game_key": game_key}, legacy={"success": True, "game_id": game_id, "game_key": game_key}), 200


def create_project(data: Dict[str, Any], created_by: str, tenant_id: str = "default") -> Tuple[Dict[str, Any], int]:
    project_id = str(data.get("id") or data.get("project_id") or "").strip()
    name = str(data.get("name") or "").strip()
    if not project_id or not name:
        return attach_legacy_error(fail("项目ID和名称不能为空", code="validation_error", legacy={"error": "项目ID和名称不能为空"})), 400
    if projects_repo.has_project(project_id):
        return attach_legacy_error(fail("项目ID已存在", code="conflict", legacy={"error": "项目ID已存在"})), 409

    users_db = projects_repo.list_users()
    viewers_raw = data.get("viewers")
    editors_raw = data.get("editors")
    if isinstance(viewers_raw, list):
        viewers = [str(u).strip() for u in viewers_raw if str(u).strip() in users_db]
    elif isinstance(viewers_raw, str):
        viewers = [u.strip() for u in viewers_raw.replace("，", ",").split(",") if u.strip() in users_db]
    else:
        viewers = []
    if isinstance(editors_raw, list):
        editors = [str(u).strip() for u in editors_raw if str(u).strip() in users_db]
    elif isinstance(editors_raw, str):
        editors = [u.strip() for u in editors_raw.replace("，", ",").split(",") if u.strip() in users_db]
    else:
        editors = []

    member_roles = data.get("member_roles")
    if not isinstance(member_roles, dict):
        member_roles = {}
    member_roles = {
        str(u): (str(r) if str(r) in PROJECT_ROLES else "其他")
        for u, r in member_roles.items()
        if str(u).strip() in users_db
    }

    phase = str(data.get("phase") or "kickoff").strip()
    allowed_phases = {p[0] for p in PROJECT_PHASES}
    if phase not in allowed_phases:
        phase = "kickoff"

    game_id = str(data.get("game_id") or "").strip()
    game_key = str(data.get("game_key") or "").strip()
    if not game_id or not game_key:
        return attach_legacy_error(fail("创建项目必须填写 gameId 和 gameKey（可点系统生成）", code="validation_error", legacy={"error": "创建项目必须填写 gameId 和 gameKey（可点系统生成）"})), 400
    existed_game_ids = {
        str((p or {}).get("game_id") or "").strip()
        for p in (projects_repo.list_projects() or {}).values()
        if isinstance(p, dict)
    }
    if game_id in existed_game_ids:
        return attach_legacy_error(fail("gameId 已存在，请重新生成", code="conflict", legacy={"error": "gameId 已存在，请重新生成"})), 409
    existed_game_keys = {
        str((p or {}).get("game_key") or "").strip()
        for p in (projects_repo.list_projects() or {}).values()
        if isinstance(p, dict)
    }
    if game_key in existed_game_keys:
        return attach_legacy_error(fail("gameKey 已存在，请重新生成", code="conflict", legacy={"error": "gameKey 已存在，请重新生成"})), 409

    payload = {
        "tenant_id": tenant_id,
        "name": name,
        "name_en": str(data.get("name_en") or "").strip(),
        "description": str(data.get("description") or "").strip(),
        "intro": str(data.get("intro") or "").strip(),
        "detail": str(data.get("detail") or "").strip(),
        "icon": str(data.get("icon") or "").strip(),
        "phase": phase,
        "network_connection": str(data.get("network_connection") or "").strip(),
        "player_public_url": _normalize_public_url(data.get("player_public_url")),
        "forum_public_url": _normalize_public_url(data.get("forum_public_url")),
        "admin_public_url": _normalize_public_url(data.get("admin_public_url")),
        "created_at": datetime.now().isoformat(),
        "created_by": created_by,
        "order": len(projects_repo.list_projects()) + 1,
        "status": "active",
        "viewers": viewers,
        "editors": editors,
        "member_roles": member_roles,
        "is_template": False,
        "channels": [str(c).strip() for c in (data.get("channels") or []) if str(c).strip()],
        "game_id": game_id,
        "game_key": game_key,
        "game_key_updated_at": datetime.now().isoformat(),
        "game_key_updated_by": created_by,
        "default_server_profile": str((data.get("default_server_profile") or "default")).strip() or "default",
        "default_env": str((data.get("default_env") or "dev")).strip() or "dev",
        "default_channel": str((data.get("default_channel") or "")).strip(),
        "server_mode": str(data.get("server_mode") or "topology").strip().lower(),
    }
    mode = payload["server_mode"]
    if mode not in ("topology", "casual_baas"):
        payload["server_mode"] = "topology"
    apply_build_config_to_project_payload(payload, data)
    projects_repo.upsert_project(project_id, payload)
    if payload["server_mode"] == "casual_baas":
        from services.baas.service_crud import ensure_service

        svc, _secret = ensure_service(project_id, str(data.get("default_env") or "development"), actor=created_by)
        payload["baas_service_id"] = svc.get("service_id") or ""
        projects_repo.upsert_project(project_id, payload)
    projects_repo.audit("create_project", project_id)
    return ok({"project_id": project_id}, legacy={"success": True}), 200


def get_project(project_id: str) -> Tuple[Dict[str, Any], int]:
    v = projects_repo.get_project(project_id)
    if not v:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    project = {
        "id": project_id,
        "name": v.get("name", project_id),
        "name_en": v.get("name_en", ""),
        "icon": v.get("icon", ""),
        "phase": v.get("phase", "kickoff"),
        "intro": v.get("intro", "") or v.get("description", ""),
        "detail": v.get("detail", ""),
        "network_connection": v.get("network_connection", ""),
        "player_public_url": _normalize_public_url(v.get("player_public_url")),
        "forum_public_url": _normalize_public_url(v.get("forum_public_url")),
        "admin_public_url": _normalize_public_url(v.get("admin_public_url")),
        "viewers": v.get("viewers") or [],
        "editors": v.get("editors") or [],
        "member_roles": v.get("member_roles") or {},
        "status": v.get("status", "active"),
        "is_template": bool(v.get("is_template")),
        "channels": v.get("channels") or [],
        "disabled_channels": v.get("disabled_channels") or [],
        "platforms": v.get("platforms") if isinstance(v.get("platforms"), list) else [],
        "disabled_platforms": v.get("disabled_platforms") if isinstance(v.get("disabled_platforms"), list) else [],
        "server_mode": str(v.get("server_mode") or "topology"),
        "baas_service_id": str(v.get("baas_service_id") or ""),
    }
    bc = build_config_for_api({**v, "id": project_id})
    project.update(bc)
    project["build_config"] = bc
    project["git_url"] = bc.get("git_url", "")
    project["git_ssh_key_path"] = bc.get("git_ssh_key_path", "")
    return ok({"project": project}, legacy={"project": project}), 200


def update_project(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    project_id = str(data.get("id") or data.get("project_id") or "").strip()
    v = projects_repo.get_project(project_id)
    if not project_id or not v:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404

    name = str(data.get("name") or "").strip()
    if not name:
        return attach_legacy_error(fail("名称不能为空", code="validation_error", legacy={"error": "名称不能为空"})), 400
    v["name"] = name
    v["name_en"] = str(data.get("name_en") or "").strip()
    v["intro"] = str(data.get("intro") or "").strip()
    v["detail"] = str(data.get("detail") or "").strip()
    v["icon"] = str(data.get("icon") or "").strip()
    ph = str(data.get("phase") or "kickoff").strip()
    allowed_phases = {p[0] for p in PROJECT_PHASES}
    v["phase"] = ph if ph in allowed_phases else v.get("phase", "kickoff")
    v["network_connection"] = str(data.get("network_connection") or "").strip()
    apply_build_config_to_project_payload(v, data)
    if "player_public_url" in data:
        v["player_public_url"] = _normalize_public_url(data.get("player_public_url"))
    if "forum_public_url" in data:
        v["forum_public_url"] = _normalize_public_url(data.get("forum_public_url"))
    if "admin_public_url" in data:
        v["admin_public_url"] = _normalize_public_url(data.get("admin_public_url"))

    users_db = projects_repo.list_users()
    viewers = data.get("viewers")
    editors = data.get("editors")
    member_roles = data.get("member_roles")
    if isinstance(viewers, list):
        v["viewers"] = [str(u).strip() for u in viewers if str(u).strip() in users_db]
    elif isinstance(viewers, str):
        v["viewers"] = [u.strip() for u in viewers.replace("，", ",").split(",") if u.strip() in users_db]
    else:
        v["viewers"] = []
    if isinstance(editors, list):
        v["editors"] = [str(u).strip() for u in editors if str(u).strip() in users_db]
    elif isinstance(editors, str):
        v["editors"] = [u.strip() for u in editors.replace("，", ",").split(",") if u.strip() in users_db]
    else:
        v["editors"] = []
    if isinstance(member_roles, dict):
        v["member_roles"] = {
            str(u): (str(r) if str(r) in PROJECT_ROLES else "其他")
            for u, r in member_roles.items()
            if str(u).strip() in users_db
        }
    else:
        v["member_roles"] = v.get("member_roles") or {}
    if "is_template" in data:
        v["is_template"] = bool(data["is_template"])
    channels = data.get("channels")
    if isinstance(channels, list):
        v["channels"] = [str(c).strip() for c in channels if str(c).strip()]
    projects_repo.save_projects_repo()
    projects_repo.audit("update_project", project_id)
    return ok({"project_id": project_id}, legacy={"success": True}), 200


def add_channel(project_id: str, channel_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    cid = str(channel_id or "").strip()
    if not cid:
        return attach_legacy_error(fail("渠道 ID 不能为空", code="validation_error", legacy={"error": "渠道 ID 不能为空"})), 400
    valid_ids = {(c.get("id") or "").strip() for c in projects_repo.list_channels()}
    if cid not in valid_ids:
        return attach_legacy_error(fail("渠道不存在", code="not_found", legacy={"error": "渠道不存在"})), 404
    channels = proj.get("channels")
    if not isinstance(channels, list):
        channels = []
    if cid in channels:
        return attach_legacy_error(fail("该渠道已在项目中", code="conflict", legacy={"error": "该渠道已在项目中"})), 409
    channels = channels + [cid]
    proj["channels"] = channels
    disabled = proj.get("disabled_channels")
    if isinstance(disabled, list):
        proj["disabled_channels"] = [x for x in disabled if str(x).strip() != cid]
    projects_repo.save_projects_repo()
    projects_repo.audit("project_add_channel", f"{project_id} {cid}")
    return ok({"channels": channels}, legacy={"success": True, "channels": channels}), 200


def remove_channel(project_id: str, channel_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    cid = str(channel_id or "").strip()
    if not cid:
        return attach_legacy_error(fail("渠道 ID 不能为空", code="validation_error", legacy={"error": "渠道 ID 不能为空"})), 400
    channels = proj.get("channels")
    if not isinstance(channels, list):
        channels = []
    if not channels:
        all_ids = [
            (c.get("id") or "").strip()
            for c in projects_repo.list_channels()
            if (c.get("id") or "").strip()
        ]
        channels = [c for c in all_ids if c != cid]
    else:
        channels = [c for c in channels if str(c).strip() != cid]
    proj["channels"] = channels
    disabled = proj.get("disabled_channels")
    if isinstance(disabled, list):
        proj["disabled_channels"] = [x for x in disabled if str(x).strip() != cid]
    projects_repo.save_projects_repo()
    projects_repo.audit("project_remove_channel", f"{project_id} {cid}")
    return ok({"channels": channels, "disabled_channels": proj.get("disabled_channels") or []}, legacy={"success": True, "channels": channels}), 200


def _project_channel_whitelist(project_id: str, proj: Dict[str, Any]) -> List[str]:
    channels = proj.get("channels")
    if isinstance(channels, list) and channels:
        return [str(c).strip() for c in channels if str(c).strip()]
    return [
        (c.get("id") or "").strip()
        for c in projects_repo.list_channels()
        if (c.get("id") or "").strip()
    ]


def disable_channel(project_id: str, channel_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    cid = str(channel_id or "").strip()
    if not cid:
        return attach_legacy_error(fail("渠道 ID 不能为空", code="validation_error", legacy={"error": "渠道 ID 不能为空"})), 400
    whitelist = _project_channel_whitelist(project_id, proj)
    if cid not in whitelist:
        return attach_legacy_error(fail("该渠道不在项目白名单中", code="not_found", legacy={"error": "该渠道不在项目白名单中"})), 404
    disabled = proj.get("disabled_channels")
    if not isinstance(disabled, list):
        disabled = []
    if cid in disabled:
        return attach_legacy_error(fail("该渠道已禁用", code="conflict", legacy={"error": "该渠道已禁用"})), 409
    disabled = disabled + [cid]
    proj["disabled_channels"] = disabled
    projects_repo.save_projects_repo()
    projects_repo.audit("project_disable_channel", f"{project_id} {cid}")
    return ok({"disabled_channels": disabled}, legacy={"success": True, "disabled_channels": disabled}), 200


def enable_channel(project_id: str, channel_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    cid = str(channel_id or "").strip()
    if not cid:
        return attach_legacy_error(fail("渠道 ID 不能为空", code="validation_error", legacy={"error": "渠道 ID 不能为空"})), 400
    disabled = proj.get("disabled_channels")
    if not isinstance(disabled, list) or cid not in disabled:
        return attach_legacy_error(fail("该渠道未处于禁用状态", code="not_found", legacy={"error": "该渠道未处于禁用状态"})), 404
    disabled = [x for x in disabled if str(x).strip() != cid]
    proj["disabled_channels"] = disabled
    projects_repo.save_projects_repo()
    projects_repo.audit("project_enable_channel", f"{project_id} {cid}")
    return ok({"disabled_channels": disabled}, legacy={"success": True, "disabled_channels": disabled}), 200


def _normalized_stored_platforms(proj: Dict[str, Any], *, default_if_empty: bool = True) -> List[str]:
    raw = proj.get("platforms")
    if not isinstance(raw, list) or not raw:
        return list(DEFAULT_PROJECT_PLATFORMS) if default_if_empty else []
    out: List[str] = []
    seen = set()
    for item in raw:
        pid = str(item).strip().lower()
        if is_valid_platform_id(pid) and pid not in seen:
            seen.add(pid)
            out.append(pid)
    if not out and default_if_empty:
        return list(DEFAULT_PROJECT_PLATFORMS)
    return out


def _project_platform_whitelist(project_id: str, proj: Dict[str, Any]) -> List[str]:
    return _normalized_stored_platforms(proj)


def add_platform(project_id: str, platform_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    pid = str(platform_id or "").strip().lower()
    if not is_valid_platform_id(pid):
        return attach_legacy_error(fail("平台不存在", code="not_found", legacy={"error": "平台不存在"})), 404
    platforms = _normalized_stored_platforms(proj)
    if pid in platforms:
        return ok(
            {"platforms": platforms, "already_exists": True},
            legacy={"success": True, "platforms": platforms, "already_exists": True},
        ), 200
    platforms = platforms + [pid]
    proj["platforms"] = platforms
    disabled = proj.get("disabled_platforms")
    if isinstance(disabled, list):
        proj["disabled_platforms"] = [x for x in disabled if str(x).strip().lower() != pid]
    projects_repo.save_projects_repo()
    projects_repo.audit("project_add_platform", f"{project_id} {pid}")
    return ok({"platforms": platforms}, legacy={"success": True, "platforms": platforms}), 200


def remove_platform(project_id: str, platform_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    pid = str(platform_id or "").strip().lower()
    if not is_valid_platform_id(pid):
        return attach_legacy_error(fail("平台 ID 不能为空", code="validation_error", legacy={"error": "平台 ID 不能为空"})), 400
    platforms = _normalized_stored_platforms(proj, default_if_empty=False)
    if not platforms:
        platforms = [p for p in DEFAULT_PROJECT_PLATFORMS if p != pid]
    else:
        platforms = [p for p in platforms if p != pid]
    proj["platforms"] = platforms
    disabled = proj.get("disabled_platforms")
    if isinstance(disabled, list):
        proj["disabled_platforms"] = [x for x in disabled if str(x).strip().lower() != pid]
    projects_repo.save_projects_repo()
    projects_repo.audit("project_remove_platform", f"{project_id} {pid}")
    return ok(
        {"platforms": platforms, "disabled_platforms": proj.get("disabled_platforms") or []},
        legacy={"success": True, "platforms": platforms},
    ), 200


def disable_platform(project_id: str, platform_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    pid = str(platform_id or "").strip().lower()
    if not pid:
        return attach_legacy_error(fail("平台 ID 不能为空", code="validation_error", legacy={"error": "平台 ID 不能为空"})), 400
    whitelist = _project_platform_whitelist(project_id, proj)
    if pid not in whitelist:
        return attach_legacy_error(fail("该平台不在项目白名单中", code="not_found", legacy={"error": "该平台不在项目白名单中"})), 404
    disabled = proj.get("disabled_platforms")
    if not isinstance(disabled, list):
        disabled = []
    if pid in disabled:
        return attach_legacy_error(fail("该平台已禁用", code="conflict", legacy={"error": "该平台已禁用"})), 409
    disabled = disabled + [pid]
    proj["disabled_platforms"] = disabled
    projects_repo.save_projects_repo()
    projects_repo.audit("project_disable_platform", f"{project_id} {pid}")
    return ok({"disabled_platforms": disabled}, legacy={"success": True, "disabled_platforms": disabled}), 200


def enable_platform(project_id: str, platform_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    pid = str(platform_id or "").strip().lower()
    if not pid:
        return attach_legacy_error(fail("平台 ID 不能为空", code="validation_error", legacy={"error": "平台 ID 不能为空"})), 400
    disabled = proj.get("disabled_platforms")
    if not isinstance(disabled, list) or pid not in disabled:
        return attach_legacy_error(fail("该平台未处于禁用状态", code="not_found", legacy={"error": "该平台未处于禁用状态"})), 404
    disabled = [x for x in disabled if str(x).strip().lower() != pid]
    proj["disabled_platforms"] = disabled
    projects_repo.save_projects_repo()
    projects_repo.audit("project_enable_platform", f"{project_id} {pid}")
    return ok({"disabled_platforms": disabled}, legacy={"success": True, "disabled_platforms": disabled}), 200


CHANNEL_BINDING_KEYS = ("jenkins_job", "package_suffix", "signing_ref", "notes")


def _normalize_channel_binding(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for key in CHANNEL_BINDING_KEYS:
        if key in raw and raw.get(key) is not None:
            out[key] = str(raw.get(key) or "").strip()
    return out


def list_channel_bindings(project_id: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    bindings = proj.get("channel_bindings") if isinstance(proj.get("channel_bindings"), list) else []
    normalized: List[Dict[str, Any]] = []
    for row in bindings:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("channel_id") or "").strip()
        if not cid:
            continue
        entry = {"channel_id": cid}
        entry.update(_normalize_channel_binding(row))
        normalized.append(entry)
    return ok({"channel_bindings": normalized}, legacy={"channel_bindings": normalized}), 200


def update_channel_binding(project_id: str, channel_id: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    cid = str(channel_id or "").strip()
    if not cid:
        return attach_legacy_error(fail("渠道 ID 不能为空", code="validation_error", legacy={"error": "渠道 ID 不能为空"})), 400
    whitelist = _project_channel_whitelist(project_id, proj)
    if cid not in whitelist:
        return attach_legacy_error(fail("该渠道不在项目白名单中", code="not_found", legacy={"error": "该渠道不在项目白名单中"})), 404
    bindings = proj.get("channel_bindings") if isinstance(proj.get("channel_bindings"), list) else []
    bindings = [row for row in bindings if isinstance(row, dict) and str(row.get("channel_id") or "").strip() != cid]
    payload = _normalize_channel_binding(data)
    if any(payload.values()):
        entry = {"channel_id": cid}
        entry.update(payload)
        bindings.append(entry)
    proj["channel_bindings"] = bindings
    projects_repo.save_projects_repo()
    projects_repo.audit("project_update_channel_binding", f"{project_id} {cid} {sorted(payload.keys())}")
    return ok({"channel_bindings": bindings}, legacy={"success": True, "channel_bindings": bindings}), 200


def delete_channel_binding(project_id: str, channel_id: str) -> Tuple[Dict[str, Any], int]:
    return update_channel_binding(project_id, channel_id, {})


def set_archive(project_id: str, archive: bool) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    proj["status"] = "archived" if archive else "active"
    projects_repo.save_projects_repo()
    projects_repo.audit("project_archive" if archive else "project_unarchive", project_id)
    return ok({"project_id": project_id, "status": proj["status"]}, legacy={"success": True}), 200


def delete_project(project_id: str, require_approval_for_delete: bool) -> Tuple[Dict[str, Any], int]:
    if not projects_repo.has_project(project_id):
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    if require_approval_for_delete:
        if not get_approved_approval("delete_project", project_id):
            msg = "删除项目需先提交审批并通过。请至 审批管理 发起「删除项目」申请，目标 ID 填写：" + project_id
            return attach_legacy_error(fail(msg, code="approval_required", legacy={"error": msg})), 403
    projects_repo.delete_project(project_id)
    projects_repo.delete_project_versions(project_id)
    projects_repo.audit("delete_project", project_id)
    return ok({"project_id": project_id}, legacy={"success": True}), 200


def import_projects_csv(csv_text: str, created_by: str, tenant_id: str = "default") -> Tuple[Dict[str, Any], int]:
    import csv
    import io

    text = str(csv_text or "").strip()
    if not text:
        return attach_legacy_error(fail("CSV 内容为空", code="validation_error", legacy={"error": "CSV 内容为空"})), 400
    reader = csv.DictReader(io.StringIO(text))
    created: List[str] = []
    errors: List[str] = []
    for idx, row in enumerate(reader, start=2):
        if not isinstance(row, dict):
            continue
        pid = str(row.get("project_id") or row.get("id") or "").strip()
        name = str(row.get("name") or pid).strip()
        if not pid:
            errors.append(f"行 {idx}: 缺少 project_id")
            continue
        if projects_repo.has_project(pid):
            errors.append(f"行 {idx}: 项目 {pid} 已存在")
            continue
        payload = {
            "project_id": pid,
            "name": name or pid,
            "intro": str(row.get("intro") or "").strip(),
            "channels": [x.strip() for x in str(row.get("channels") or "wechat").replace("，", ",").split(",") if x.strip()],
        }
        result, status = create_project(payload, created_by, tenant_id)
        if status >= 400:
            err = result.get("error") or result.get("message") or "创建失败"
            errors.append(f"行 {idx}: {err}")
            continue
        created.append(pid)
    if not created and errors:
        return attach_legacy_error(fail("导入失败", code="import_failed", legacy={"error": "; ".join(errors), "errors": errors})), 400
    return ok({"created": created, "errors": errors, "created_count": len(created)}, legacy={"success": True}), 200
