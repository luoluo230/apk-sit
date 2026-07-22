# -*- coding: utf-8 -*-
"""Build status sync: Jenkins SUCCESS/FAILURE → release order transitions."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from services.release import order_build_sync as obs
from services.release import order_crud as oc
from services.release import release_order_service as ros


def _building_row(order_id: str = "ro-b1", project_id: str = "p1") -> dict:
    return {
        "release_order_id": order_id,
        "project_id": project_id,
        "version_id": "v1",
        "version_code": "100",
        "status": "building",
        "payload": '{"build_job_id":"117","jenkins_instance_id":"8082"}',
    }


class JenkinsProgressPctTests(unittest.TestCase):
    def test_building_returns_mid_progress(self):
        self.assertEqual(ros._jenkins_progress_pct({"building": True, "status": "BUILDING"}), 55)

    def test_success_returns_100(self):
        self.assertEqual(ros._jenkins_progress_pct({"building": False, "result": "SUCCESS"}), 100)

    def test_failure_returns_100_bar_complete(self):
        self.assertEqual(ros._jenkins_progress_pct({"building": False, "result": "FAILURE"}), 100)


class SyncReleaseOrderBuildStatusTests(unittest.TestCase):
    def test_jenkins_failure_transitions_to_build_failed(self):
        row = _building_row()
        order = {
            "release_order_id": "ro-b1",
            "project_id": "p1",
            "version_id": "v1",
            "version_code": "100",
            "status": "building",
            "payload": {"build_job_id": "117", "jenkins_instance_id": "8082"},
        }
        updated = {**order, "status": "build_failed"}
        with mock.patch.object(obs, "init_db"), \
             mock.patch.object(obs, "_db_lock"), \
             mock.patch.object(obs, "_get_conn") as conn, \
             mock.patch("services.jenkins.get_build_status", return_value={"building": False, "status": "FAILURE", "error": "compile error"}), \
             mock.patch("services.jenkins_manager.get_jenkins_url_for_instance", return_value="http://j"), \
             mock.patch("services.jenkins_manager.get_builds_dir_for_instance", return_value="/tmp/builds"), \
             mock.patch.object(oc, "_order_from_row", side_effect=[order, updated]), \
             mock.patch.object(oc, "get_release_order", return_value=updated), \
             mock.patch.object(obs, "get_cursor") as cursor_cm, \
             mock.patch.object(obs, "_event"):
            conn.return_value.execute.return_value.fetchone.return_value = row
            cursor_cm.return_value.__enter__.return_value = mock.MagicMock()
            cursor_cm.return_value.__exit__.return_value = False
            out = ros.sync_release_order_build_status("p1", "ro-b1", actor="tester")
        self.assertEqual(out["status"], "build_failed")

    def test_jenkins_success_transitions_to_artifacts_ready(self):
        row = _building_row()
        order = {
            "release_order_id": "ro-b1",
            "project_id": "p1",
            "version_id": "v1",
            "version_code": "100",
            "status": "building",
            "payload": {"build_job_id": "118", "jenkins_instance_id": "8082"},
        }
        version = {
            "id": "v1",
            "version_code": "100",
            "apk_url": "https://cdn/a.apk",
            "resource_url": "https://cdn/r",
            "config_url": "https://cdn/c",
        }
        updated = {**order, "status": "artifacts_ready"}
        with mock.patch.object(obs, "init_db"), \
             mock.patch.object(obs, "_db_lock"), \
             mock.patch.object(obs, "_get_conn") as conn, \
             mock.patch("services.jenkins.get_build_status", return_value={"building": False, "status": "SUCCESS"}), \
             mock.patch("services.jenkins_manager.get_jenkins_url_for_instance", return_value="http://j"), \
             mock.patch("services.jenkins_manager.get_builds_dir_for_instance", return_value="/tmp/builds"), \
             mock.patch("services.apk_artifact_service.finalize_apk_from_jenkins_build"), \
             mock.patch.object(obs, "_find_version", return_value=version), \
             mock.patch.object(obs, "_artifact_rows", return_value=[("apk", "u1", "p1"), ("resource", "u2", "p2"), ("config", "u3", "p3")]), \
             mock.patch.object(oc, "_order_from_row", side_effect=[order, updated]), \
             mock.patch.object(oc, "get_release_order", return_value=updated), \
             mock.patch.object(obs, "get_cursor") as cursor_cm, \
             mock.patch.object(obs, "_event"):
            conn.return_value.execute.return_value.fetchone.return_value = row
            cursor_cm.return_value.__enter__.return_value = mock.MagicMock()
            cursor_cm.return_value.__exit__.return_value = False
            out = ros.sync_release_order_build_status("p1", "ro-b1", actor="system")
        self.assertEqual(out["status"], "artifacts_ready")

    def test_sync_building_release_orders_polls_each_row(self):
        with mock.patch.object(obs, "init_db"), \
             mock.patch.object(obs, "_db_lock"), \
             mock.patch.object(obs, "_get_conn") as conn, \
             mock.patch.object(obs, "sync_release_order_build_status", side_effect=[{"status": "artifacts_ready"}, {"status": "build_failed"}]) as sync:
            conn.return_value.execute.return_value.fetchall.return_value = [
                {"project_id": "p1", "release_order_id": "ro-1"},
                {"project_id": "p1", "release_order_id": "ro-2"},
            ]
            rows = ros.sync_building_release_orders("p1")
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
