# -*- coding: utf-8 -*-
"""In-process E2E: Server Management Hub + server release deploy callback."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")
os.environ.setdefault("PORTAL_SERVER_FRAMEWORKS", "all")

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: E402
from models.db import init_db  # noqa: E402

_TEST_PROJECT = "demo-sm-hub-e2e"
_TEST_PROJECT_ROW = {
    "name": "SM Hub E2E Demo",
    "game_id": "sm-hub-e2e-gid",
    "game_key": "sm-hub-e2e-key",
    "server_mode": "topology",
    "status": "active",
}


class ServerManagementHubE2ETests(unittest.TestCase):
    def setUp(self):
        init_db()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        self._projects_patch = mock.patch.dict(
            "routes.admin_routes.projects_db",
            {_TEST_PROJECT: dict(_TEST_PROJECT_ROW)},
            clear=False,
        )
        self._projects_patch.start()
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def tearDown(self):
        self._projects_patch.stop()

    def test_server_management_hub_page(self):
        resp = self.client.get(f"/admin/projects/{_TEST_PROJECT}/server-management")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("server_management_hub.js", html)

    def test_server_management_projects_api(self):
        resp = self.client.get("/api/server-management/projects")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertTrue(body.get("ok"))

    def test_server_release_deploy_to_deployed_flow(self):
        from services.release import server_artifact_service as sas
        from services.release import server_release_service as srs

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("game-cn-1/README.txt", "e2e")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as fh:
            fh.write(buf.getvalue())
            path = fh.name
        try:
            art = sas.register_artifact(
                _TEST_PROJECT,
                {"version_label": "1.0.0-e2e", "protocol_version": "v1"},
                source_path=path,
            )
        finally:
            os.remove(path)

        rel = srs.create_server_release(
            _TEST_PROJECT,
            {
                "artifact_id": art["artifact_id"],
                "topology_id": "topo-sm-e2e",
                "env_key": "development",
                "target_services": ["game-cn-1"],
            },
            "admin",
        )
        rid = rel["server_release_id"]

        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-sm-e2e", "status": "PENDING", "target": "game-cn-1"}]
            deploy_resp = self.client.post(
                f"/api/admin/projects/{_TEST_PROJECT}/server-releases/{rid}/deploy",
            )
        self.assertEqual(deploy_resp.status_code, 200)

        complete_resp = self.client.post(
            f"/api/admin/projects/{_TEST_PROJECT}/server-releases/{rid}/complete-deploy",
            json={"ok": True, "service_id": "game-cn-1"},
        )
        self.assertEqual(complete_resp.status_code, 200)
        body = complete_resp.get_json() or {}
        self.assertTrue(body.get("ok"))
        self.assertEqual((body.get("data") or {}).get("status"), "deployed")

        detail = self.client.get(f"/api/admin/projects/{_TEST_PROJECT}/server-releases/{rid}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual((detail.get_json().get("data") or {}).get("status"), "deployed")


if __name__ == "__main__":
    unittest.main()
