"""项目级构建配置：Git、App 名、Unity 路径等（原 Jenkins 实例 build_defaults 中的项目字段）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from repositories.admin import projects_repo

PROJECT_BUILD_SCALAR_KEYS = (
    "app_name",
    "git_url",
    "git_workspace",
    "git_ssh_key_path",
    "default_git_branch",
    "unity_project_path",
    "output_base_dir",
)


def normalize_build_config(data: Optional[dict]) -> dict:
    """从请求体或存储记录解析项目 build_config。"""
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in PROJECT_BUILD_SCALAR_KEYS:
        v = data.get(k)
        if v is not None and str(v).strip():
            out[k] = str(v).strip()
    gb = data.get("git_branches")
    if isinstance(gb, list) and gb:
        out["git_branches"] = [str(b).strip() for b in gb if str(b).strip()]
    elif isinstance(gb, str) and gb.strip():
        out["git_branches"] = [s.strip() for s in gb.splitlines() if s.strip()]
    return out


def _legacy_git_from_project(proj: dict) -> dict:
    """兼容项目顶层 git_url / git_ssh_key_path。"""
    if not isinstance(proj, dict):
        return {}
    out = {}
    if str(proj.get("git_url") or "").strip():
        out["git_url"] = str(proj.get("git_url") or "").strip()
    if str(proj.get("git_ssh_key_path") or "").strip():
        out["git_ssh_key_path"] = str(proj.get("git_ssh_key_path") or "").strip()
    return out


def get_project_build_config(project_id: str) -> dict:
    """读取项目构建配置；build_config 优先，顶层 git 字段作回退。"""
    proj = projects_repo.get_project(project_id)
    if not proj:
        return {}
    stored = proj.get("build_config") if isinstance(proj.get("build_config"), dict) else {}
    merged = normalize_build_config({**_legacy_git_from_project(proj), **stored})
    return merged


def apply_build_config_to_project_payload(payload: dict, data: dict) -> None:
    """把请求中的构建配置写入 payload['build_config']，并同步顶层 git 字段（兼容旧调用）。"""
    raw = {}
    if isinstance(data.get("build_config"), dict):
        raw.update(data["build_config"])
    for k in PROJECT_BUILD_SCALAR_KEYS:
        if k in data:
            raw[k] = data.get(k)
    if "git_branches" in data:
        raw["git_branches"] = data.get("git_branches")
    bc = normalize_build_config(raw)
    payload["build_config"] = bc
    payload["git_url"] = bc.get("git_url", "")
    payload["git_ssh_key_path"] = bc.get("git_ssh_key_path", "")


def build_config_for_api(proj: dict) -> dict:
    """供 API / 前端使用的扁平 build_config。"""
    if not isinstance(proj, dict):
        return {}
    project_id = str(proj.get("id") or "").strip()
    if project_id:
        return get_project_build_config(project_id)
    stored = proj.get("build_config") if isinstance(proj.get("build_config"), dict) else {}
    return normalize_build_config({**_legacy_git_from_project(proj), **stored})


def resolve_effective_build_defaults(project_id: str, instance_id: Optional[str] = None) -> dict:
    """读取项目构建默认值（实例侧 build_defaults 已废弃）。"""
    _ = instance_id
    return get_project_build_config(project_id) if project_id else {}


def merge_git_branch_into_defaults(build_defaults: dict, git_branch: str) -> dict:
    """把本次构建分支并入 git_branches / default_git_branch。"""
    bd = dict(build_defaults or {})
    branch = str(git_branch or "").strip()
    if not branch:
        return bd
    branches: List[str] = bd.get("git_branches") or []
    if isinstance(branches, str):
        branches = [b.strip() for b in branches.splitlines() if b.strip()]
    if not isinstance(branches, list):
        branches = []
    if branch not in branches:
        branches = [branch] + branches
    bd["default_git_branch"] = branch
    bd["git_branches"] = branches or [branch]
    return bd
