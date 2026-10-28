# -*- coding: utf-8 -*-
"""Completed build tasks carry a release mark and can be tied to a server release."""

from services.release.completed_task_catalog import (
    classify_release_mark,
    list_ship_choices,
    stamp_selected_build,
)
from services.release.project_download_catalog import list_download_entries


def test_published_build_is_marked_released():
    orders = [{
        "version_id": "v1",
        "status": "verified",
        "payload": {"selected_build_number": "18"},
    }]
    assert classify_release_mark("v1", 18, orders, is_newest_success=False) == "released"
    assert classify_release_mark("v1", 17, orders, is_newest_success=True) == "unreleased"


def test_rollback_is_marked_separately():
    orders = [{
        "version_id": "v1",
        "status": "rolled_back",
        "payload": {"build_job_id": "9"},
    }]
    assert classify_release_mark("v1", 9, orders, is_newest_success=True) == "rolled_back"


def test_selecting_a_server_release_requests_joint_deploy():
    payload = {"selected_build_number": "8", "server_release_id": "sro-1"}
    stamp_selected_build(payload)
    assert payload["build_job_id"] == "8"
    assert payload["deploy_server_with_client"] is True


def test_ship_choices_keep_success_tasks_for_the_scope(monkeypatch):
    version = {
        "id": "v1",
        "version_name": "1.2.0",
        "version_code": "20",
        "env_key": "development",
        "channel": "1001",
        "platform": "android",
        "description": "修复登录",
    }
    monkeypatch.setattr(
        "services.release.completed_task_catalog.project_versions_db.get",
        lambda _pid: [version],
    )
    monkeypatch.setattr(
        "services.release.completed_task_catalog._load_orders",
        lambda _pid: [{
            "version_id": "v1",
            "status": "published",
            "payload": {"selected_build_number": "3"},
        }],
    )
    monkeypatch.setattr(
        "services.release.completed_task_catalog._version_has_apk",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "services.release.completed_task_catalog._server_releases",
        lambda *_args, **_kwargs: [{
            "server_release_id": "sro-9",
            "status": "ready",
            "status_label": "可部署",
            "version_label": "gs-1.2.0",
            "artifact_id": "art-1",
            "env_key": "development",
        }],
    )
    monkeypatch.setattr(
        "services.build_history_service.list_records_for_project",
        lambda _pid: [
            {"instance_id": "jen-1", "build_number": 3, "version_id": "v1", "triggered_by": "admin"},
            {"instance_id": "jen-1", "build_number": 2, "version_id": "v1", "triggered_by": "admin"},
        ],
    )

    def _status(rec, _cache, detail_mode=False):
        result = "SUCCESS" if int(rec["build_number"]) == 3 else "FAILURE"
        return {**rec, "result": result, "ended_at": "2026-10-28T10:00:00"}

    monkeypatch.setattr("services.build_history_service._resolve_build_status", _status)
    data = list_ship_choices("GomeKu", env_key="development", channel_id="1001", platform="android")
    assert [row["build_number"] for row in data["tasks"]] == [3]
    assert data["tasks"][0]["release_label"] == "已发版"
    assert data["server_releases"][0]["version_label"] == "gs-1.2.0"
    unreleased = list_ship_choices(
        "GomeKu", env_key="development", channel_id="1001", platform="android", release_state="unreleased"
    )
    assert unreleased["tasks"] == []


def test_download_entry_uses_store_when_package_missing(monkeypatch):
    version = {
        "id": "v2",
        "version_name": "1.0.0",
        "version_code": "1",
        "env_key": "production",
        "channel": "1001",
        "platform": "ios",
        "description": "商店包",
    }
    monkeypatch.setattr(
        "services.release.project_download_catalog.project_versions_db.get",
        lambda _pid: [version],
    )
    monkeypatch.setattr("services.release.project_download_catalog._latest_builds", lambda _pid: {})
    monkeypatch.setattr("services.release.project_download_catalog._apk_entry", lambda *_a, **_k: {})
    monkeypatch.setattr(
        "services.release.project_download_catalog._store_links",
        lambda _pid: {"ios_store": "https://apps.example/gomeku"},
    )
    monkeypatch.setattr("services.release.project_download_catalog._qr", lambda text: "qr:" + text)
    monkeypatch.setattr("services.release.completed_task_catalog._load_orders", lambda _pid: [])
    rows = list_download_entries("GomeKu")
    assert rows[0]["kind"] == "store"
    assert rows[0]["store_url"] == "https://apps.example/gomeku"
    assert rows[0]["qr_dataurl"].startswith("qr:")
