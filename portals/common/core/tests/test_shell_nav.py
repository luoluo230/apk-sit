# -*- coding: utf-8 -*-
"""Shell navigation groups stay stable when the sidebar is rebuilt."""

from services.ops.shell_nav import shell_groups


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
        release = _group(groups, "release")
        assert len(release["items"]) == 1
        item = release["items"][0]
        assert item["active"] is True
        assert item["href"] == "/admin/projects/GomeKu/release-hub?env_key=staging"
    assert [row["id"] for row in shell_groups("GomeKu", "staging", "release-hub")][1:] == [
        "overview",
        "release",
        "runtime",
        "operations",
        "collab",
        "settings",
    ]


def test_baas_and_gm_live_under_operations():
    groups = shell_groups("GomeKu", "development", "casual-services")
    ops = _group(groups, "operations")
    by_id = {item["id"]: item for item in ops["items"]}
    assert by_id["casual-services"]["href"].endswith("/casual-services")
    assert by_id["casual-services"]["active"] is True
    assert by_id["baas-gm"]["href"].endswith("/baas-gm")
    assert by_id["baas-gm"]["active"] is False
    assert "project_id=GomeKu" in by_id["community"]["href"]

    gm = shell_groups("GomeKu", "development", "baas-gm")
    gm_ops = {item["id"]: item for item in _group(gm, "operations")["items"]}
    assert gm_ops["baas-gm"]["active"] is True
    assert gm_ops["casual-services"]["active"] is False
