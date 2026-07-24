# -*- coding: utf-8 -*-
"""Tests for completed portal feature backlog."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


class TestGrayRolloutScheduler(unittest.TestCase):
    def test_should_auto_expand_after_duration(self):
        from services.release import gray_rollout_scheduler as sched

        published = (datetime.now() - timedelta(minutes=45)).isoformat()
        order = {
            "status": "published",
            "published_at": published,
            "payload": {
                "release_strategy": "gray",
                "gray_success_action": "automatic",
                "gray_duration": "30",
                "gray_ratio": "10",
            },
        }
        bundle = {"client": {"rollout_percentage": 10}, "rollout_percentage": 10}
        self.assertTrue(sched._should_auto_expand(order, bundle))

    def test_hold_skipped_in_tick(self):
        from services.release import gray_rollout_scheduler as sched

        fake_row = MagicMock()
        fake_row.__getitem__ = lambda self, key: {
            "project_id": "Demo",
            "release_order_id": "ro-hold",
            "status": "published",
            "payload": '{"gray_success_action":"hold","release_strategy":"gray"}',
            "published_at": datetime.now().isoformat(),
            "bundle_id": "bundle-hold",
        }[key]
        cursor = MagicMock()
        cursor.execute.return_value.fetchall.return_value = [fake_row]
        with patch("models.db.get_cursor") as mock_get_cursor, patch("models.db.init_db"):
            mock_get_cursor.return_value.__enter__.return_value = cursor
            stat = sched.run_gray_rollout_tick()
        self.assertEqual(stat.get("expanded_count"), 0)
        self.assertGreaterEqual(stat.get("skipped_hold", 0), 1)


class TestExpandGrayHold(unittest.TestCase):
    def test_manual_expand_rejected_on_hold(self):
        from services.release.order_publish_flow import expand_gray_rollout

        order = {
            "status": "published",
            "bundle_id": "bundle-1",
            "payload": {"gray_success_action": "hold"},
        }
        with patch("services.release.order_publish_flow._order_crud") as mock_crud:
            mock_crud.return_value.get_release_order.return_value = order
            with self.assertRaises(ValueError) as ctx:
                expand_gray_rollout("Demo", "ro-1", "tester")
        self.assertIn("保持当前比例", str(ctx.exception))


class TestGrayJourneyHold(unittest.TestCase):
    def test_can_expand_gray_false_when_hold(self):
        from services.release.channel_journey_bff import _gray_rollout_view

        view = _gray_rollout_view(
            {
                "release_order_id": "ro-1",
                "status": "published",
                "payload": {"release_strategy": "gray", "gray_ratio": "10", "gray_success_action": "hold"},
            },
            {"client": {"rollout_percentage": 10}, "gray_status": "active"},
        )
        self.assertFalse(view["can_expand_gray"])


class TestAdminSearchExtended(unittest.TestCase):
    def test_search_finds_version_and_doc(self):
        ql = "9999"
        fake_versions = {
            "GomeKu": [
                {"id": "v-search-1", "version_name": "9.9.9", "version_code": "9999", "platform": "android"},
            ]
        }
        version_hits = []
        for pid, versions in fake_versions.items():
            for ver in versions:
                hay = " ".join([
                    str(ver.get("id") or ""),
                    str(ver.get("version_name") or ""),
                    str(ver.get("version_code") or ""),
                ]).lower()
                if ql in hay:
                    version_hits.append(ver["version_code"])
        self.assertIn("9999", version_hits)

        docs = [{"id": "doc-search", "title": "发版指南"}]
        doc_hits = [doc for doc in docs if ql in str(doc.get("title") or "").lower() or ql in str(doc.get("id") or "").lower()]
        self.assertEqual(doc_hits, [])
        doc_hits2 = [doc for doc in docs if "发版" in str(doc.get("title") or "")]
        self.assertEqual(len(doc_hits2), 1)


class TestProjectMemberUpdate(unittest.TestCase):
    def test_update_project_accepts_project_id_and_members(self):
        from services.admin import project_service

        saved = {}

        class FakeRepo:
            def get_project(self, pid):
                return {
                    "name": "Demo",
                    "viewers": ["viewer1"],
                    "editors": ["editor1"],
                    "member_roles": {},
                    "phase": "kickoff",
                }

            def list_users(self):
                return {"viewer1": {}, "editor1": {}, "newbie": {}}

            def save_projects_repo(self):
                saved["ok"] = True

            def audit(self, *args, **kwargs):
                pass

        with patch.object(project_service, "projects_repo", FakeRepo()):
            payload, status = project_service.update_project(
                {
                    "project_id": "Demo",
                    "name": "Demo",
                    "viewers": ["viewer1"],
                    "editors": ["editor1", "newbie"],
                    "member_roles": {"newbie": "编辑者"},
                }
            )
        self.assertEqual(status, 200)
        self.assertTrue(saved.get("ok"))


class TestValidationPlanRunner(unittest.TestCase):
    def test_skips_when_no_items(self):
        from services.release.validation_plan_runner import run_validation_plan

        result = run_validation_plan({"payload": {}}, phase="precheck")
        self.assertTrue(result.get("skipped"))
        self.assertTrue(result.get("ok"))

    def test_parses_comma_items(self):
        from services.release.validation_plan_runner import parse_validation_items

        items = parse_validation_items({"validation_items": "订单创建, 支付跳转"})
        self.assertEqual(items, ["订单创建", "支付跳转"])


class TestBundleGrayStrategies(unittest.TestCase):
    def test_canary_whitelist(self):
        from services.release.bundle_service import resolve_gray_rollout_bundle

        bundle = {
            "bundle_id": "b1",
            "scope_id": "s1",
            "gray_strategy": "canary",
            "gray_canary_list": ["user-a", "device-b"],
            "client": {"rollout_percentage": 5},
        }
        hit = resolve_gray_rollout_bundle(bundle, user_id="user-a")
        miss = resolve_gray_rollout_bundle(bundle, user_id="other")
        self.assertTrue(hit.get("in_rollout"))
        self.assertFalse(miss.get("in_rollout"))

    def test_region_strategy(self):
        from services.release.bundle_service import resolve_gray_rollout_bundle

        bundle = {
            "bundle_id": "b2",
            "scope_id": "s1",
            "gray_strategy": "region",
            "gray_regions": ["cn-east", "cn-north"],
            "client": {"rollout_percentage": 50},
        }
        hit = resolve_gray_rollout_bundle(bundle, region="cn-east")
        miss = resolve_gray_rollout_bundle(bundle, region="us-west")
        self.assertTrue(hit.get("in_rollout"))
        self.assertFalse(miss.get("in_rollout"))


class TestActivitiesArchive(unittest.TestCase):
    def test_kind_filter(self):
        from services.release.overview_feed_service import build_overview_activities

        with patch("services.release.overview_feed_service._release_order_activities") as rel, patch(
            "services.release.overview_feed_service._task_activities"
        ) as task, patch("services.release.overview_feed_service._alert_activities") as alert, patch(
            "services.release.overview_feed_service._doc_activities"
        ) as doc:
            rel.return_value = [{"kind": "release", "time": "2026-07-24T10:00:00", "title": "a"}]
            task.return_value = [{"kind": "task", "time": "2026-07-24T09:00:00", "title": "b"}]
            alert.return_value = []
            doc.return_value = []
            all_rows = build_overview_activities("Demo", limit=10)
            release_rows = build_overview_activities("Demo", limit=10, kind="release")
        self.assertEqual(len(all_rows), 2)
        self.assertEqual(len(release_rows), 1)
        self.assertEqual(release_rows[0]["kind"], "release")

    def test_activities_api_route(self):
        from app_new import app

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = client.get("/api/projects/GomeKu/activities?limit=5")
        payload = resp.get_json() or {}
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(payload.get("ok"))
        self.assertIn("activities", payload.get("data") or {})


if __name__ == "__main__":
    unittest.main()
