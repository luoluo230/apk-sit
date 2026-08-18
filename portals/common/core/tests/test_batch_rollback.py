# -*- coding: utf-8 -*-
"""Tests for batch coordinated rollback."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")

from models.db import init_db
from services.release.release_batch_service import batch_rollback, resolve_batch_next_action


class BatchRollbackTests(unittest.TestCase):
    def setUp(self):
        init_db()

    @mock.patch("services.release.release_batch_service._orders_for_batch")
    @mock.patch("services.release.release_batch_service.get_release_batch")
    @mock.patch("services.release.order_publish_lifecycle.rollback_release_order")
    @mock.patch("services.release.incident_loop_service.find_rollback_target_order")
    def test_batch_rollback_invokes_per_line(
        self,
        find_target,
        rollback_order,
        get_batch,
        orders_for_batch,
    ):
        find_target.side_effect = [
            {"release_order_id": "ro-prev-a"},
            {"release_order_id": "ro-prev-b"},
        ]
        rollback_order.side_effect = [
            {"status": "rolled_back"},
            {"status": "rolled_back"},
        ]
        get_batch.return_value = {"batch_id": "rbatch-1", "status": "published", "orders": []}
        orders_for_batch.return_value = [
            {"release_order_id": "ro-a", "scope_id": "scope-a", "status": "published", "channel_id": "wechat", "platform": "android"},
            {"release_order_id": "ro-b", "scope_id": "scope-b", "status": "published", "channel_id": "douyin", "platform": "android"},
            {"release_order_id": "ro-c", "scope_id": "scope-c", "status": "draft", "channel_id": "wechat", "platform": "ios"},
        ]

        with mock.patch("services.release.release_batch_service._sync_batch_status", return_value="published"):
            with mock.patch("services.release.release_batch_service._batch_event"):
                result = batch_rollback("GomeKu", "rbatch-1", "tester")

        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(all(r.get("ok") for r in result["results"]))
        self.assertEqual(rollback_order.call_count, 2)

    @mock.patch("services.release.release_batch_service.get_release_batch")
    def test_next_action_exposes_rollback_after_publish(self, get_batch):
        get_batch.return_value = {
            "batch_id": "rbatch-2",
            "status": "published",
            "orders": [{"status": "published"}],
        }
        action = resolve_batch_next_action("GomeKu", "rbatch-2")
        api_actions = [action["primary"].get("api_action")] + [
            a.get("api_action") for a in action.get("more_actions") or []
        ]
        self.assertIn("rollback", api_actions)


if __name__ == "__main__":
    unittest.main()
