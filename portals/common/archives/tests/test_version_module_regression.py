# -*- coding: utf-8 -*-
"""Version 模块关键回归：组级不改 code，单号可切状态。"""

import copy
import os
import secrets
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestVersionModuleRegression(unittest.TestCase):
    def setUp(self):
        from app_new import app

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        self.pid = "ver_reg_%s" % secrets.token_hex(4)

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def test_version_group_update_does_not_change_version_code(self):
        from models.data import projects_db, project_versions_db, save_projects, save_project_versions

        original_project = copy.deepcopy(projects_db.get(self.pid))
        original_versions = copy.deepcopy(project_versions_db.get(self.pid))
        try:
            projects_db[self.pid] = {"name": "reg", "status": "active"}
            project_versions_db[self.pid] = [
                {
                    "id": "v1",
                    "channel": "1001",
                    "stage": "dev",
                    "platform": "android",
                    "version_name": "1.0.0",
                    "version_code": "100",
                    "version_status": "active",
                    "apk_path": "wechat/dev/demo.apk",
                    "updated_at": "2026-01-01T00:00:00",
                }
            ]
            save_projects()
            save_project_versions()

            self._login_admin()
            r = self.client.post(
                "/admin/projects/%s/versions/update" % self.pid,
                json={
                    "id": "v1",
                    "edit_scope": "version_group",
                    "version_name": "1.0.1",
                    "version_code": "999",
                    "version_status": "testing",
                    "channel": "1001",
                    "stage": "test",
                    "platform": "android",
                    "apk_path": "wechat/dev/demo.apk",
                },
            )
            self.assertEqual(r.status_code, 200)
            updated = (r.get_json() or {}).get("version") or {}
            self.assertEqual(updated.get("version_code"), "100")
            self.assertEqual(updated.get("version_status"), "testing")
        finally:
            if original_project is None:
                projects_db.pop(self.pid, None)
            else:
                projects_db[self.pid] = original_project
            if original_versions is None:
                project_versions_db.pop(self.pid, None)
            else:
                project_versions_db[self.pid] = original_versions
            save_projects()
            save_project_versions()

    def test_version_code_scope_can_switch_status(self):
        from models.data import projects_db, project_versions_db, save_projects, save_project_versions

        original_project = copy.deepcopy(projects_db.get(self.pid))
        original_versions = copy.deepcopy(project_versions_db.get(self.pid))
        try:
            projects_db[self.pid] = {"name": "reg2", "status": "active"}
            project_versions_db[self.pid] = [
                {
                    "id": "v2",
                    "channel": "1001",
                    "stage": "dev",
                    "platform": "android",
                    "version_name": "2.0.0",
                    "version_code": "200",
                    "version_status": "testing",
                    "apk_path": "wechat/dev/demo2.apk",
                    "updated_at": "2026-01-01T00:00:00",
                }
            ]
            save_projects()
            save_project_versions()

            self._login_admin()
            r = self.client.post(
                "/admin/projects/%s/versions/update" % self.pid,
                json={
                    "id": "v2",
                    "edit_scope": "version_code",
                    "version_code": "201",
                    "version_status": "active",
                    "changelog": "promote",
                },
            )
            self.assertEqual(r.status_code, 200)
            updated = (r.get_json() or {}).get("version") or {}
            self.assertEqual(updated.get("version_code"), "201")
            self.assertEqual(updated.get("version_status"), "active")
        finally:
            if original_project is None:
                projects_db.pop(self.pid, None)
            else:
                projects_db[self.pid] = original_project
            if original_versions is None:
                project_versions_db.pop(self.pid, None)
            else:
                project_versions_db[self.pid] = original_versions
            save_projects()
            save_project_versions()


if __name__ == "__main__":
    unittest.main()

