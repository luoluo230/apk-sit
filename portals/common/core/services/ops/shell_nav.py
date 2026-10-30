# -*- coding: utf-8 -*-
"""Admin shell navigation. Data only: groups, links, and which page is current."""

from __future__ import annotations

from urllib.parse import quote, urlencode

_RELEASE_PAGES = frozenset({
    "release-hub",
    "release-console",
    "versions",
    "builds",
    "release-orders",
    "download-center",
})


def register_shell_nav(app) -> None:
    @app.context_processor
    def _inject_shell_nav():
        return {"shell_groups": shell_groups, "shell_breadcrumb": shell_breadcrumb}


def shell_groups(project_id: str = "", env_key: str = "", active_page: str = "", path: str = "") -> list[dict]:
    project = str(project_id or "").strip()
    env = str(env_key or "").strip() or "development"
    page = str(active_page or "").strip()
    current = str(path or "").strip()
    groups = [_studio(page, current)]
    if project:
        groups.extend(_project_groups(project, env, page, current))
    return groups


def _studio(page: str, path: str) -> dict:
    return {
        "id": "studio",
        "label": "工作室",
        "items": [
            _item("home", "工作台", "/admin", "nav_workbench", page, path, pages=("home",), exact=("/admin",)),
            _item("message-center", "消息", "/admin/notifications", "nav_message_center", page, path, pages=("message-center",), prefixes=("/admin/notifications",)),
            _item("projects", "项目列表", "/admin/projects", "nav_project_list", page, path, pages=("projects",), exact=("/admin/projects",)),
            _item("users", "成员", "/admin/users", "nav_roles_member", page, path, pages=("users",), prefixes=("/admin/users",)),
            _item("jenkins", "打包机", "/admin/jenkins", "nav_build_artifact", page, path, pages=("jenkins",), prefixes=("/admin/jenkins",)),
            _item("site-config", "站点外壳", "/admin/site-config", "nav_project_setting", page, path, pages=("site-config",), prefixes=("/admin/site-config",)),
        ],
    }


def _with_env(href: str, env: str) -> str:
    joiner = "&" if "?" in href else "?"
    return href + joiner + urlencode({"env_key": env})


def _project_groups(project: str, env: str, page: str, path: str) -> list[dict]:
    pid = quote(project, safe="")
    base = f"/admin/projects/{pid}"
    link = lambda href: _with_env(href, env)
    return [
        {
            "id": "overview",
            "label": "总览",
            "items": [
                _item("project-home", "项目总览", link(f"{base}/overview"), "nav_project_overview", page, path, pages=("project-home",)),
                _item("environment-runtime", "运行概览", link(f"{base}/overview/runtime"), "nav_environment", page, path, pages=("environment-runtime", "environment-overview")),
            ],
        },
        {
            "id": "release",
            "label": "发版",
            "items": [
                _item(
                    "release-hub",
                    "发版",
                    link(f"{base}/release-hub"),
                    "nav_release",
                    page,
                    path,
                    pages=_RELEASE_PAGES,
                ),
            ],
        },
        {
            "id": "runtime",
            "label": "游戏服",
            "items": [
                _item("server-management", "服务器管理", link(f"{base}/server-management"), "nav_agent_server", page, path, pages=("server-management",)),
                _item("agent-control", "代理服务", link(f"{base}/agents"), "nav_agent_server", page, path, pages=("agent-control",)),
                _item("actions", "动作执行", link(f"{base}/actions"), "nav_execute", page, path, pages=("actions",)),
                _item("diagnostics", "节点诊断", link(f"{base}/diagnostics"), "nav_performance", page, path, pages=("diagnostics",)),
            ],
        },
        {
            "id": "operations",
            "label": "休闲服务",
            "items": [
                _item("casual-services", "功能配置", link(f"{base}/casual-services"), "nav_project_setting", page, path, pages=("casual-services",)),
                _item("baas-gm", "GM", link(f"{base}/baas-gm"), "nav_roles_member", page, path, pages=("baas-gm",)),
                _item(
                    "community",
                    "游戏圈内容",
                    "/admin/community?" + urlencode({"project_id": project, "env_key": env}),
                    "nav_doc",
                    page,
                    path,
                    pages=("community",),
                    prefixes=("/admin/community",),
                ),
            ],
        },
        {
            "id": "collab",
            "label": "协作",
            "items": [
                _item("project-tasks", "项目任务", link(f"{base}/tasks"), "nav_task", page, path, pages=("project-tasks",)),
                _item("project-docs", "项目文档", link(f"{base}/docs"), "nav_doc", page, path, pages=("project-docs",)),
                _item("approval-center", "审批", "/admin/approval?" + urlencode({"project_id": project, "env_key": env}), "nav_approval_center", page, path, pages=("approval-center",)),
                _item("change-governance", "变更治理", link(f"{base}/change-governance"), "nav_change_governance", page, path, pages=("change-governance",)),
                _item("audit-log", "审计日志", link(f"{base}/audit-log"), "nav_audit_log", page, path, pages=("audit-log",)),
            ],
        },
        {
            "id": "settings",
            "label": "设置",
            "items": [
                _item("project-settings", "项目设置", link(f"{base}/settings"), "nav_project_setting", page, path, pages=("project-settings",)),
                _item("test-devices", "测试设备", link(f"{base}/test-devices"), "nav_binding", page, path, pages=("test-devices",)),
                _item("project-channels", "环境渠道", link(f"{base}/overview?tab=channels"), "nav_binding", page, path, pages=("project-channels", "environment-config")),
            ],
        },
    ]


def shell_breadcrumb(project_id: str = "", project_name: str = "", active_page: str = "", env_key: str = "") -> list[dict]:
    project = str(project_id or "").strip()
    env = str(env_key or "").strip() or "development"
    name = str(project_name or project).strip() or project
    groups = shell_groups(project, env, active_page, "")
    current = None
    group_label = ""
    group_href = ""
    for group in groups:
        for item in group["items"]:
            if item["active"]:
                current = item
                group_label = group["label"]
                group_href = group["items"][0]["href"]
                break
        if current:
            break
    crumbs = [{"label": "工作台", "href": "/admin"}]
    if project:
        crumbs.append({"label": name, "href": _with_env(f"/admin/projects/{quote(project, safe='')}/overview", env)})
        if group_label and group_label != "工作室":
            crumbs.append({"label": group_label, "href": group_href})
    if current and current["id"] != "home":
        crumbs.append({"label": current["label"], "href": ""})
    elif not project and current and current["id"] == "home":
        crumbs = [{"label": "工作台", "href": ""}]
    return crumbs


def _item(item_id, label, href, icon, page, path, pages=(), exact=(), prefixes=()):
    return {
        "id": item_id,
        "label": label,
        "href": href,
        "icon": icon,
        "active": _is_active(page, path, pages, exact, prefixes),
    }


def _is_active(page: str, path: str, pages, exact, prefixes) -> bool:
    if page and page in pages:
        return True
    if path in exact:
        return True
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)
