# -*- coding: utf-8 -*-
"""Shell navigation groups stay stable when the sidebar is rebuilt."""

from services.ops.shell_nav import shell_breadcrumb, shell_groups


def _group(groups, group_id):
    return next(row for row in groups if row["id"] == group_id)


def test_studio_only_when_no_project_is_selected():
    groups = shell_groups("", "", "admin", "/admin")
    assert [row["id"] for row in groups] == ["studio"]
    labels = [item["label"] for item in groups[0]["items"]]
    assert "发版" not in labels
    assert "服务器管理" not in labels
    assert groups[0]["items"][0]["active"] is True


def test_project_release_is_one_link_and_stays_active_for_sibling_pages():
    for page in ("release-hub", "release-console", "versions", "builds", "release-orders"):
        groups = shell_groups("GomeKu", "staging", page, f"/admin/projects/GomeKu/{page}")
        # 发版页收敛为 release-only 组（含版本/构建/发版中心等入口）
        assert [row["id"] for row in groups] == ["release"]
        release = _group(groups, "release")
        by_id = {item["id"]: item for item in release["items"]}
        assert "release-hub" in by_id
        assert by_id["release-hub"]["href"] == "/admin/projects/GomeKu/release-hub?env_key=staging"
    # active_page 属于发版页时始终 release-only
    full = shell_groups("GomeKu", "staging", "release-hub")
    assert [row["id"] for row in full] == ["release"]
    # 非发版页保留完整项目导航
    normal = shell_groups("GomeKu", "staging", "server-management")
    assert "overview" in [row["id"] for row in normal]
    assert "runtime" in [row["id"] for row in normal]


def test_studio_breadcrumb_names_the_current_page():
    crumbs = shell_breadcrumb("", "", "message-center", "")
    assert [item["label"] for item in crumbs] == ["工作台", "消息"]
    assert crumbs[0]["href"] == "/admin"
    assert crumbs[-1]["href"] == ""


def test_project_links_keep_the_selected_env():
    groups = shell_groups("GomeKu", "staging", "server-management")
    hrefs = {
        item["id"]: item["href"]
        for group in groups
        for item in group["items"]
    }
    assert hrefs["server-management"] == "/admin/projects/GomeKu/server-management?env_key=staging"
    # topology 项目不展示 BaaS GM
    assert "baas-gm" not in hrefs
    assert "agent-control" in hrefs
    assert hrefs["project-tasks"] == "/admin/projects/GomeKu/tasks?env_key=staging"
    assert "env_key=staging" in hrefs["approval-center"]


def test_server_groups_and_hidden_pages():
    groups = shell_groups("GomeKu", "development", "server-management", "/admin/projects/GomeKu/server-management")
    assert _group(groups, "runtime")["label"] == "游戏服"
    # topology：operations 仅保留社区等共享项，无 BaaS GM/功能配置
    ops = _group(groups, "operations")
    assert ops["label"] == "社区"
    ops_ids = {item["id"] for item in ops["items"]}
    assert "baas-gm" not in ops_ids
    assert "casual-services" not in ops_ids
    assert "community" in ops_ids
    settings = {item["id"]: item for item in _group(groups, "settings")["items"]}
    assert settings["test-devices"]["href"].endswith("/test-devices?env_key=development")
    crumbs = shell_breadcrumb("GomeKu", "五子棋", "server-management", "development")
    assert [item["label"] for item in crumbs] == ["工作台", "五子棋", "游戏服", "服务器管理"]
    assert crumbs[0]["href"] == "/admin"
    assert "env_key=development" in crumbs[1]["href"]
    assert crumbs[-1]["href"] == ""


def test_baas_and_gm_live_under_operations(monkeypatch):
    from services.baas import project_nav_policy as policy

    monkeypatch.setattr(policy, "project_server_mode", lambda _pid: "casual_baas")
    groups = shell_groups("GomeKu", "development", "casual-services")
    ops = _group(groups, "operations")
    assert ops["label"] == "BaaS 运维"
    by_id = {item["id"]: item for item in ops["items"]}
    assert by_id["casual-services"]["href"].endswith("/casual-services?env_key=development")
    assert by_id["casual-services"]["active"] is True
    assert by_id["baas-gm"]["href"].endswith("/baas-gm?env_key=development")
    assert by_id["baas-gm"]["active"] is False
    assert "project_id=GomeKu" in by_id["community"]["href"]
    assert "env_key=development" in by_id["community"]["href"]
    # BaaS 项目不展示 Agent
    hrefs = {item["id"] for group in groups for item in group["items"]}
    assert "agent-control" not in hrefs

    gm = shell_groups("GomeKu", "development", "baas-gm")
    gm_ops = {item["id"]: item for item in _group(gm, "operations")["items"]}
    assert gm_ops["baas-gm"]["active"] is True
    assert gm_ops["casual-services"]["active"] is False
