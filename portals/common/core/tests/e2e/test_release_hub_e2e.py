# -*- coding: utf-8 -*-
"""CI gate: release hub + release console pages and APIs (in-process E2E)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: E402
from models.db import init_db  # noqa: E402

_TEST_PROJECT = "demo-release-hub-e2e"
_TEST_PROJECT_ROW = {"name": "Release Hub E2E Demo", "channels": ["wechat"]}


class ReleaseHubE2ETests(unittest.TestCase):
    """Release hub / console smoke — runs in CI via pytest without a live server."""

    def setUp(self):
        init_db()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        self._projects_patch = patch.dict(
            "routes.project_delivery.projects_db",
            {_TEST_PROJECT: dict(_TEST_PROJECT_ROW)},
            clear=False,
        )
        self._projects_patch.start()
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def tearDown(self):
        self._projects_patch.stop()

    def test_release_hub_page(self):
        resp = self.client.get(f"/admin/projects/{_TEST_PROJECT}/release-hub")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("发版中心", html)
        self.assertIn("project_release_hub.js", html)
        self.assertIn("交付发版", html)

    def test_release_console_page(self):
        resp = self.client.get(
            f"/admin/projects/{_TEST_PROJECT}/release?env_key=development"
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("发版控制台", html)
        self.assertIn("project_release_console.js", html)
        self.assertNotIn("project_versions_workspace", html)

    def test_release_hub_api(self):
        resp = self.client.get(
            f"/api/projects/{_TEST_PROJECT}/release-hub?env_key=development"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertTrue(body.get("ok"))
        data = body.get("data") or {}
        self.assertTrue(data.get("module_cards"))
        self.assertIn("release_health", data)
        self.assertIn("promotion_candidates", data)
        self.assertIn("server_promotion_candidates", data)
        self.assertIn("coordinated_deploy_feed", data)
        self.assertIn("prod_wizard_steps", data)

    def test_server_artifact_promotions_api(self):
        resp = self.client.get(f"/api/projects/{_TEST_PROJECT}/server-artifact-promotions")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertTrue(body.get("ok"))
        self.assertIsInstance(body.get("data"), list)

    def test_release_hub_page_has_server_sections(self):
        resp = self.client.get(f"/admin/projects/{_TEST_PROJECT}/release-hub")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("服务端制品晋级", html)
        self.assertIn("协同发布 / 联合回滚", html)
        self.assertIn("rhServerPromotionList", html)
        self.assertIn("rhCoordinatedList", html)

    def test_release_console_api(self):
        resp = self.client.get(
            f"/api/projects/{_TEST_PROJECT}/release-console?env_key=development"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertTrue(body.get("ok"))
        data = body.get("data") or {}
        self.assertTrue(data.get("env_defs"))

    def test_artifact_promotions_api(self):
        resp = self.client.get(f"/api/projects/{_TEST_PROJECT}/artifact-promotions")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertTrue(body.get("ok"))
        self.assertIsInstance(body.get("data"), list)

    def test_overview_links_to_release_hub(self):
        resp = self.client.get(f"/admin/projects/{_TEST_PROJECT}/overview")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn(f"/admin/projects/{_TEST_PROJECT}/release-hub", html)


@unittest.skipUnless(
    os.environ.get("RUN_RELEASE_HUB_LIVE_E2E") in ("1", "true", "yes"),
    "set RUN_RELEASE_HUB_LIVE_E2E=1 to run against a live admin server",
)
class ReleaseHubLiveServerE2ETests(unittest.TestCase):
    """Optional live-server checks (local/staging with admin on :5003)."""

    def test_live_release_hub_gate_script(self):
        import subprocess

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        script = os.path.join(root, "scripts", "release_hub_live_e2e.py")
        proc = subprocess.run(
            [sys.executable, script],
            cwd=root,
            capture_output=True,
            text=True,
            env={**os.environ, "RELEASE_GATE_BASE_URL": os.environ.get("RELEASE_GATE_BASE_URL", "http://127.0.0.1:5003")},
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
