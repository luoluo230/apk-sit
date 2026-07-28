# -*- coding: utf-8 -*-
"""Fix shared bootstrap and dedupe imports on split ops modules."""

from __future__ import annotations

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OPS = os.path.join(ROOT, "services", "ops")
BOOT = os.path.join(OPS, "shared_bootstrap.py")
MODULES = (
    "diagnostics",
    "topology_contracts",
    "cluster_importer",
    "topology_registry",
    "agent_registry",
    "runtime_orchestrator",
)


def fix_bootstrap() -> None:
    with open(BOOT, encoding="utf-8") as fp:
        body = fp.read()
    body = re.sub(r"from __future__ import annotations\s*\n\s*from __future__ import annotations", "from __future__ import annotations", body)
    if "from services.ops.encoding import" not in body:
        body = body.replace(
            "from services.legacy_gm_bridge_client import LegacyGmBridgeClient\n",
            "from services.legacy_gm_bridge_client import LegacyGmBridgeClient\n"
            "from services.ops.encoding import repair_legacy_node_text, text_has_mojibake\n"
            "from concurrent.futures import ThreadPoolExecutor, as_completed\n"
            "import time as _time_mod\n",
        )
    body = re.sub(
        r"\nCLUSTER_JSON_PATH = os\.path\.join\(_resolve_game_server_repo\(\), \"config\", \"cluster\.json\"\)\n",
        "\n",
        body,
    )
    with open(BOOT, "w", encoding="utf-8") as fp:
        fp.write(body)


def strip_module(path: str) -> None:
    with open(path, encoding="utf-8") as fp:
        lines = fp.readlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i == 0 or (i < 8 and (line.startswith('"""') or line.startswith("#") or line.strip() == "" or "from __future__" in line or "shared_bootstrap" in line)):
            if "from __future__" in line and any("from __future__" in x for x in out):
                i += 1
                continue
            out.append(line)
            i += 1
            continue
        if line.startswith("def ") or line.startswith("@") or line.startswith("class "):
            out.extend(lines[i:])
            break
        i += 1
    with open(path, "w", encoding="utf-8") as fp:
        fp.writelines(out)


def fix_cluster_path() -> None:
    path = os.path.join(OPS, "cluster_importer.py")
    with open(path, encoding="utf-8") as fp:
        body = fp.read()
    marker = "    return env or ordered[0]\n\n\ndef _load_cluster_json"
    insert = (
        "    return env or ordered[0]\n\n\n"
        "CLUSTER_JSON_PATH = os.path.join(_resolve_game_server_repo(), \"config\", \"cluster.json\")\n\n\n"
        "def _load_cluster_json"
    )
    if "CLUSTER_JSON_PATH =" not in body:
        body = body.replace(marker, insert)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(body)


BOOT_IMPORT = (
    "from services.ops import shared_bootstrap as _boot\n\n"
    "globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith('__')})\n"
)


def fix_private_bootstrap_imports() -> None:
    paths = [os.path.join(OPS, f"{n}.py") for n in MODULES] + [os.path.join(OPS, "helpers.py")]
    for path in paths:
        with open(path, encoding="utf-8") as fp:
            body = fp.read()
        body = body.replace("from services.ops.shared_bootstrap import *  # noqa: F403\n", BOOT_IMPORT)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(body)


def fix_helpers_facade() -> None:
    path = os.path.join(OPS, "helpers.py")
    helpers_body = '''# -*- coding: utf-8 -*-
"""Ops platform thin facade — re-exports domain modules. Plan P1-01."""

from __future__ import annotations

import os

from flask import has_request_context, render_template, render_template_string, request, session

from models.data import projects_db

from services.authz import can_access_module, has_scope, is_admin
from services.ops.agent_service import _default_agent_policy, _load_agent_policy, _save_agent_policy
from services.ops.runtime_service import _runtime_active_for_scope
from services.ops import shared_bootstrap as _boot

globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})
from services.ops.topology_service import (
    _env_label,
    _load_topology_contents,
    _load_topology_registry,
    _normalize_env_key,
    _save_topology_contents,
    _save_topology_registry,
    _scope_binding_key,
    _topology_content_counts,
)

from services.ops.diagnostics import *  # noqa: F403
from services.ops.topology_contracts import *  # noqa: F403
from services.ops.cluster_importer import *  # noqa: F403
from services.ops.topology_registry import *  # noqa: F403
from services.ops.agent_registry import *  # noqa: F403
from services.ops.runtime_orchestrator import *  # noqa: F403


def _session_username(default: str = "system") -> str:
    try:
        if has_request_context():
            return str(session.get("user") or default)
    except Exception:
        pass
    return default


def _allow_ops_view() -> bool:
    return bool(
        is_admin()
        or can_access_module("gm_ops")
        or has_scope("ops.platform.view")
        or has_scope("gm.ops.execute")
        or has_scope("gm.audit.view")
    )


def _allow_ops_execute() -> bool:
    return bool(
        is_admin()
        or can_access_module("gm_ops")
        or has_scope("ops.platform.execute")
        or has_scope("gm.ops.execute")
    )


def _allow_gm_execute() -> bool:
    return bool(
        can_access_module("gm_ops")
        or has_scope("gm.classic.execute")
        or has_scope("gm.liveops.execute")
        or has_scope("gm.ops.execute")
    )


def _ops_csrf_token() -> str:
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except Exception:
        return ""


def _render_ops_page(
    content: str,
    title: str,
    active_page: str = "",
    project_id: str = "",
    env_key: str = "",
    topology_id: str = "",
    breadcrumb_module: str = "",
    extra_css: str = "",
    extra_js: str = "",
):
    """Unified page wrapper — all ops pages use the shared sidebar shell."""
    if not project_id:
        project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
    if project_id:
        session["ops_last_project"] = project_id
    if not env_key:
        env_key = _resolve_ops_env_key(request.args.get("env_key") or "")
    if env_key:
        session["ops_last_env"] = env_key
    if not topology_id:
        topology_id = str(request.args.get("topology_id", ""))
    project_name = project_id
    try:
        row = (projects_db or {}).get(project_id) or {}
        project_name = str(row.get("name") or project_id or "未选择项目").strip() or project_id or "未选择项目"
    except Exception:
        project_name = project_id or "未选择项目"
    env_label = _env_label(env_key) if env_key else ""
    user_name = str(session.get("user") or "").strip() or "运维管理员"
    unread_notification_count = 0
    try:
        from data.notifications import get_notifications_for_user

        unread_notification_count = sum(
            1 for n in get_notifications_for_user(user_name, limit=200) if not n.get("read_at")
        )
    except Exception:
        unread_notification_count = 0
    return render_template(
        "ops_shell.html",
        content=content,
        title=title,
        active_page=active_page,
        project_id=project_id,
        project_name=project_name,
        project_label=project_name or "未选择项目",
        env_key=env_key,
        env_label=env_label,
        topology_id=topology_id,
        avatar_text=(user_name[:1] or "A").upper(),
        user_name=user_name,
        unread_notification_count=unread_notification_count,
        breadcrumb_module=breadcrumb_module or "项目工作区",
        extra_css=PM_UI_CSS + OPS_COMPACT_CSS + extra_css,
        extra_js=extra_js,
        csrf_token=_ops_csrf_token(),
        ops_shell_asset_ver=OPS_SHELL_ASSET_VER,
    )


def _render_page(content: str, title: str):
    """Legacy compat — delegates to _render_ops_page."""
    return _render_ops_page(content, title)


def _render_local_template(template_name: str, **kwargs):
    core_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    path = os.path.join(core_dir, "templates", template_name)
    with open(path, "r", encoding="utf-8") as f:
        return render_template_string(f.read(), **kwargs)


def _render_standalone_page(content: str, title: str):
    """Legacy compat — delegates to _render_ops_page."""
    return _render_ops_page(content, title)


__all__ = []
'''
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(helpers_body)


def main() -> int:
    fix_bootstrap()
    for name in MODULES:
        strip_module(os.path.join(OPS, f"{name}.py"))
    fix_cluster_path()
    fix_helpers_facade()
    fix_private_bootstrap_imports()
    print("cleanup done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
