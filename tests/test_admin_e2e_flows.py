# -*- coding: utf-8 -*-
"""Admin full-chain E2E style tests."""

import copy
import os
import secrets
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()


class TestAdminE2EFlows(unittest.TestCase):
    def setUp(self):
        from app_new import app

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.app = app
        self.client = app.test_client()
        self.pid = f"e2e_proj_{secrets.token_hex(4)}"
        self.uname = f"e2e_user_{secrets.token_hex(3)}"
        self.uname2 = f"e2e_user2_{secrets.token_hex(3)}"

    def _login(self, username="admin"):
        with self.client.session_transaction() as sess:
            sess["user"] = username

    def _ensure_user(self, username):
        from models.data import users_db, save_users

        if username not in users_db:
            users_db[username] = {
                "password": "x",
                "role": "user",
                "allowed_modules": ["*"],
                "allowed_scopes": [],
            }
            save_users()

    def test_full_chains(self):
        from models.data import projects_db, project_versions_db, project_tasks_db, approvals_db, save_projects, save_project_versions, save_project_tasks

        original_project = copy.deepcopy(projects_db.get(self.pid))
        original_versions = copy.deepcopy(project_versions_db.get(self.pid))
        original_tasks = copy.deepcopy(project_tasks_db.get(self.pid))
        original_approvals_len = len(approvals_db)

        self._login("admin")

        # 1) 登录与管理员首页
        r_home = self.client.get("/admin")
        self.assertEqual(r_home.status_code, 200)

        # 2) 用户创建-编辑-重置密码-删除
        r_create_user = self.client.post("/admin/users/create", json={"username": self.uname, "password": "123456", "role": "user"})
        self.assertEqual(r_create_user.status_code, 200)
        self.assertTrue((r_create_user.get_json() or {}).get("ok"))
        r_update_user = self.client.post("/admin/users/update", json={"username": self.uname, "allowed_modules": ["projects"], "disabled": False})
        self.assertEqual(r_update_user.status_code, 200)
        r_reset_user = self.client.post("/admin/users/reset-password", json={"username": self.uname, "new_password": "abcdef"})
        self.assertEqual(r_reset_user.status_code, 200)

        # 3) 项目创建-编辑-渠道管理
        game_id = f"gid_{self.pid}"
        game_key = f"gkey_{self.pid}_{secrets.token_hex(4)}"
        r_create_proj = self.client.post(
            "/admin/projects/create",
            json={
                "id": self.pid,
                "name": "E2E Project",
                "game_id": game_id,
                "game_key": game_key,
                "editors": ["admin", self.uname],
                "viewers": [self.uname],
                "channels": [],
            },
        )
        self.assertEqual(r_create_proj.status_code, 200)
        r_update_proj = self.client.post(
            "/admin/projects/update",
            json={
                "id": self.pid,
                "name": "E2E Project Updated",
                "editors": ["admin", self.uname],
                "viewers": [self.uname],
            },
        )
        self.assertEqual(r_update_proj.status_code, 200)
        # 渠道可能不存在默认值，先尝试 dev，不存在则忽略
        r_add_ch = self.client.post(f"/admin/projects/{self.pid}/channels/add", json={"channel_id": "dev"})
        self.assertIn(r_add_ch.status_code, (200, 404))
        if r_add_ch.status_code == 200:
            r_rm_ch = self.client.post(f"/admin/projects/{self.pid}/channels/remove", json={"channel_id": "dev"})
            self.assertEqual(r_rm_ch.status_code, 200)

        # 4) 版本创建-更新-删除
        r_ver_create = self.client.post(
            f"/admin/projects/{self.pid}/versions/create",
            json={
                "channel": "dev",
                "stage": "dev",
                "platform": "android",
                "version_name": "1.0.0",
                "version_code": "100",
                "apk_path": f"android/{self.pid}_1.0.0.apk",
            },
        )
        self.assertEqual(r_ver_create.status_code, 200)
        ver = (r_ver_create.get_json() or {}).get("version") or {}
        vid = ver.get("id")
        self.assertTrue(vid)
        r_ver_update = self.client.post(
            f"/admin/projects/{self.pid}/versions/update",
            json={
                "id": vid,
                "channel": "dev",
                "stage": "test",
                "platform": "android",
                "version_name": "1.0.1",
                "version_code": "101",
                "apk_path": f"android/{self.pid}_1.0.1.apk",
            },
        )
        self.assertEqual(r_ver_update.status_code, 200)
        r_ver_delete = self.client.delete(f"/admin/projects/{self.pid}/versions/delete/{vid}")
        self.assertEqual(r_ver_delete.status_code, 200)

        # 5) 任务创建-流转-评论-状态
        r_task_create = self.client.post(
            f"/admin/projects/{self.pid}/tasks/create",
            json={"title": "E2E Task", "assign_to_user": "admin", "content": "smoke"},
        )
        self.assertEqual(r_task_create.status_code, 200)
        tid = (r_task_create.get_json() or {}).get("task_id")
        self.assertTrue(tid)
        r_comment = self.client.post(f"/admin/projects/{self.pid}/tasks/{tid}/comment", json={"content": "first comment"})
        self.assertEqual(r_comment.status_code, 200)
        r_status = self.client.post(f"/admin/projects/{self.pid}/tasks/{tid}/update-status", json={"status": "in_progress"})
        self.assertEqual(r_status.status_code, 200)
        r_handoff = self.client.post(f"/admin/projects/{self.pid}/tasks/{tid}/handoff", json={"passed_to_user": self.uname})
        self.assertEqual(r_handoff.status_code, 200)

        self._login(self.uname)
        r_status_2 = self.client.post(f"/admin/projects/{self.pid}/tasks/{tid}/update-status", json={"status": "pending_review"})
        self.assertEqual(r_status_2.status_code, 200)

        # 6) 审批创建-通过
        self._login("admin")
        r_appr_create = self.client.post(
            "/admin/approval/create",
            json={
                "type": "delete_project",
                "target_type": "delete_project",
                "target_id": self.pid,
                "reason": "e2e delete project check",
                "project_id": self.pid,
            },
        )
        self.assertEqual(r_appr_create.status_code, 200)
        aid = (r_appr_create.get_json() or {}).get("id") or ((r_appr_create.get_json() or {}).get("data") or {}).get("id")
        self.assertTrue(aid)
        r_appr_do = self.client.post(f"/admin/approval/{aid}/approve", json={"comment": "ok"})
        self.assertEqual(r_appr_do.status_code, 200)

        # cleanup
        r_delete_user = self.client.delete(f"/admin/users/delete/{self.uname}")
        self.assertIn(r_delete_user.status_code, (200, 404))
        if original_project is None:
            projects_db.pop(self.pid, None)
        else:
            projects_db[self.pid] = original_project
        if original_versions is None:
            project_versions_db.pop(self.pid, None)
        else:
            project_versions_db[self.pid] = original_versions
        if original_tasks is None:
            project_tasks_db.pop(self.pid, None)
        else:
            project_tasks_db[self.pid] = original_tasks
        while len(approvals_db) > original_approvals_len:
            approvals_db.pop()
        save_projects()
        save_project_versions()
        save_project_tasks()


if __name__ == "__main__":
    unittest.main()
