# -*- coding: utf-8 -*-
"""Core API/page smoke tests (unittest + pytest)."""

import os
import sys
import unittest
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import Config, load_dotenv  # noqa: E402

load_dotenv()


def _get_client():
    from app_new import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app.test_client()


def _expected_admin_base():
    configured = (getattr(Config, "ADMIN_PUBLIC_URL", "") or "").strip().rstrip("/")
    if configured:
        return configured
    return f"http://127.0.0.1:{getattr(Config, 'ADMIN_PORT', 5003)}"


@contextmanager
def _portal_mode(mode):
    old_mode = os.environ.get("APP_PORTAL_MODE")
    os.environ["APP_PORTAL_MODE"] = mode
    try:
        yield
    finally:
        if old_mode is None:
            os.environ.pop("APP_PORTAL_MODE", None)
        else:
            os.environ["APP_PORTAL_MODE"] = old_mode


class TestApi(unittest.TestCase):
    def setUp(self):
        self.client = _get_client()

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def test_homepage_returns_200(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("星云游戏站", body)
        self.assertIn("id=\"games\"", body)
        self.assertIn("href=\"/about/company\"", body)

    def test_player_ecosystem_pages_return_200(self):
        for path in ("/news", "/welfare", "/forum"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)

    def test_product_detail_contains_player_ecosystem_blocks(self):
        r = self.client.get("/product/54ad770a6585")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("href=\"/news\"", body)
        self.assertIn("href=\"/welfare\"", body)
        self.assertIn("玩家下载与商店入口", body)

    def test_player_portal_blocks_admin_routes(self):
        with _portal_mode("player"):
            r = self.client.get("/admin", follow_redirects=False)
            self.assertIn(r.status_code, (301, 302))
            self.assertIn(_expected_admin_base(), r.headers.get("Location", ""))

    def test_player_portal_homepage_hides_internal_links(self):
        with _portal_mode("player"):
            r = self.client.get("/")
            self.assertEqual(r.status_code, 200)
            body = r.data.decode("utf-8", errors="ignore")
            self.assertIn("公司简介", body)
            self.assertIn("href=\"#games\"", body)
            self.assertNotIn("href=\"/admin", body)
            self.assertNotIn("href=\"/workspace", body)

    def test_admin_portal_redirects_root(self):
        with _portal_mode("admin"):
            r = self.client.get("/", follow_redirects=False)
            self.assertIn(r.status_code, (301, 302))
            self.assertIn("/login", r.headers.get("Location", ""))

    def test_admin_community_page_returns_200_for_admin(self):
        self._login_admin()
        r = self.client.get("/admin/community")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("data-open-editor=\"news\"", body)
        self.assertIn("id=\"player-governance-section\"", body)

    def test_admin_product_edit_contains_store_link_fields(self):
        self._login_admin()
        r = self.client.get("/admin/products/54ad770a6585/edit")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("name=\"android_direct\"", body)
        self.assertIn("name=\"ios_store\"", body)
        self.assertIn("name=\"project_id\"", body)

    def test_api_docs_returns_200(self):
        r = self.client.get("/api/docs")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore").lower()
        self.assertIn("api", body)

    def test_404_returns_friendly_page(self):
        r = self.client.get("/nonexistent-page-404-test")
        self.assertEqual(r.status_code, 404)
        self.assertGreater(len(r.data), 100)
        self.assertIn(b"<!DOCTYPE html>", r.data)

    def test_api_status_returns_stats(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsNotNone(data)
        self.assertTrue("status" in data or "stats" in data)

    def test_health_returns_ok(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data.get("status"), "ok")

    def test_dashboard_page_returns_200_for_admin(self):
        self._login_admin()
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("/dashboard/export", body)

    def test_admin_products_page_returns_200_for_admin(self):
        self._login_admin()
        r = self.client.get("/admin/products")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("/admin/products/new", body)
        self.assertIn("/admin/products/54ad770a6585/edit", body)

    def test_admin_build_page_returns_200_for_admin(self):
        self._login_admin()
        r = self.client.get("/admin/build")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("id=\"buildFeedback\"", body)
        self.assertIn("meta name=\"csrf-token\"", body)

    def test_admin_approval_page_contains_inline_feedback(self):
        self._login_admin()
        r = self.client.get("/admin/approval")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("id=\"approvalFeedback\"", body)
        self.assertIn("meta name=\"csrf-token\"", body)

    def test_admin_versions_page_contains_csrf_meta(self):
        self._login_admin()
        r = self.client.get("/admin/versions")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("meta name=\"csrf-token\"", body)

    def test_admin_dashboard_contains_overview_sections(self):
        self._login_admin()
        r = self.client.get("/admin")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("/admin/my-tasks", body)
        self.assertIn("/admin/community", body)
        self.assertIn("/admin/versions", body)

    def test_player_portal_logout_is_available(self):
        with _portal_mode("player"):
            self._login_admin()
            r = self.client.get("/logout", follow_redirects=False)
            self.assertIn(r.status_code, (301, 302))

    def test_product_detail_uses_configured_store_links(self):
        r = self.client.get("/product/54ad770a6585")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("玩家下载与商店入口", body)
        self.assertNotIn("/pub/download/", body)

    def test_player_portal_product_detail_hides_internal_downloads(self):
        with _portal_mode("player"):
            self._login_admin()
            r = self.client.get("/product/54ad770a6585")
            self.assertEqual(r.status_code, 200)
            body = r.data.decode("utf-8", errors="ignore")
            self.assertNotIn("内部测试下载", body)

    def test_admin_dashboard_contains_community_entry(self):
        self._login_admin()
        r = self.client.get("/admin")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("/admin/community", body)
        self.assertIn("/admin/approval", body)

    def test_community_admin_contains_moderation_sections(self):
        self._login_admin()
        r = self.client.get("/admin/community")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8", errors="ignore")
        self.assertIn("data-list-tab-panel=\"forum\"", body)
        self.assertIn("data-action=\"moderate-post\"", body)
        self.assertIn("/admin/community/player/", body)

    def test_community_news_submit_endpoint_works(self):
        self._login_admin()
        payload = {
            "title": "pytest-news-submit",
            "kind": "版本公告",
            "summary": "smoke",
            "content": "smoke content",
            "product_id": "54ad770a6585",
        }
        r = self.client.post("/admin/community/news", json=payload)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("status"), "pending_approval")
        self.assertTrue(data.get("id"))
        self.assertTrue(data.get("approval_id"))

    def test_community_forum_moderation_endpoint_works(self):
        self._login_admin()
        create_payload = {
            "title": "pytest-forum-submit",
            "content": "smoke forum content",
            "category": "综合讨论",
            "product_id": "54ad770a6585",
        }
        create_resp = self.client.post("/admin/community/forum-post", json=create_payload)
        self.assertEqual(create_resp.status_code, 200)
        post_id = (create_resp.get_json() or {}).get("id")
        self.assertTrue(post_id)

        moderate_resp = self.client.post(
            f"/admin/community/forum-post/{post_id}/moderate",
            json={"action": "pin"},
        )
        self.assertEqual(moderate_resp.status_code, 200)
        moderate_data = moderate_resp.get_json() or {}
        self.assertTrue(moderate_data.get("ok"))
        self.assertTrue((moderate_data.get("post") or {}).get("pinned"))

        delete_resp = self.client.post(f"/admin/community/forum-post/{post_id}/delete", json={})
        self.assertEqual(delete_resp.status_code, 200)
        self.assertTrue((delete_resp.get_json() or {}).get("ok"))

    def test_community_player_moderation_endpoint_works(self):
        self._login_admin()
        author_key = "pytest-user-for-moderation"
        mute_resp = self.client.post(
            f"/admin/community/player/{author_key}/moderate",
            json={"action": "mute", "duration_hours": 24, "note": "smoke mute"},
        )
        self.assertEqual(mute_resp.status_code, 200)
        mute_data = mute_resp.get_json() or {}
        self.assertTrue(mute_data.get("ok"))
        self.assertEqual((mute_data.get("player") or {}).get("status"), "muted")

        unmute_resp = self.client.post(
            f"/admin/community/player/{author_key}/moderate",
            json={"action": "unmute"},
        )
        self.assertEqual(unmute_resp.status_code, 200)
        unmute_data = unmute_resp.get_json() or {}
        self.assertTrue(unmute_data.get("ok"))
        self.assertEqual((unmute_data.get("player") or {}).get("status"), "active")


if __name__ == "__main__":
    unittest.main()
