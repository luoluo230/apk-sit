# -*- coding: utf-8 -*-
"""Release health dashboard summary tests (P3-1)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")

from services.monitor.release_metrics import (
    _compute_client_mttr_minutes,
    _success_rate,
    build_release_health_summary,
)


class ReleaseHealthMetricTests(unittest.TestCase):
    def test_success_rate(self):
        self.assertEqual(_success_rate(8, 2), 80.0)
        self.assertIsNone(_success_rate(0, 0))

    def test_mttr_minutes(self):
        rows = [
            {"release_order_id": "ro-1", "event_type": "verify_failed", "created_at": "2026-07-20T10:00:00"},
            {"release_order_id": "ro-1", "event_type": "rollback_restored", "created_at": "2026-07-20T10:30:00"},
        ]
        self.assertEqual(_compute_client_mttr_minutes(rows), 30.0)

    @mock.patch("services.monitor.release_metrics._server_plane_summary")
    @mock.patch("services.monitor.release_metrics._get_conn")
    @mock.patch("services.monitor.release_metrics.init_db")
    def test_build_summary_includes_client_server_planes(self, _init, conn_fn, server_summary):
        conn = mock.MagicMock()
        conn_fn.return_value = conn
        conn.execute.return_value.fetchone.return_value = {
            "verified": 4,
            "verify_failed": 1,
            "publish_failed": 0,
        }
        conn.execute.return_value.fetchall.side_effect = [
            [
                {
                    "release_order_id": "ro-f1",
                    "env_key": "development",
                    "version_name": "1.0.0",
                    "version_code": "1",
                    "platform": "android",
                    "event_type": "verify_failed",
                    "created_at": "2026-07-21T12:00:00",
                    "payload": "{}",
                }
            ],
            [],
            [{"env_key": "development", "verified": 4, "verify_failed": 1, "publish_failed": 0}],
            [{"platform": "android", "verified": 4, "verify_failed": 1, "publish_failed": 0}],
            [{"env_key": "development", "deployed": 2, "failed": 1}],
            [{"day": "2026-07-21", "verified": 3, "failed": 1}],
            [{"day": "2026-07-21", "deployed": 2, "failed": 0}],
        ]
        server_summary.return_value = {
            "deployed_count": 2,
            "failed_count": 1,
            "deploying_count": 0,
            "success_rate_pct": 66.7,
        }

        summary = build_release_health_summary("__health_test__", days=7)

        self.assertEqual(summary["verified_count"], 4)
        self.assertEqual(summary["client"]["success_rate_pct"], 80.0)
        self.assertEqual(summary["server"]["success_rate_pct"], 66.7)
        self.assertIn("by_env", summary)
        self.assertIn("by_platform", summary)
        self.assertIn("daily_trend", summary)
        self.assertEqual(len(summary["daily_trend"]), 1)
        self.assertEqual(summary["daily_trend"][0]["client_verified"], 3)
        self.assertEqual(summary["daily_trend"][0]["server_deployed"], 2)


if __name__ == "__main__":
    unittest.main()
