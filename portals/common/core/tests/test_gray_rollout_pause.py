# -*- coding: utf-8
"""Gray rollout auto-pause on verify failure."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


class GrayPauseTests(unittest.TestCase):
    def test_scheduler_skips_paused_gray_order(self):
        from services.release import gray_rollout_scheduler as sched

        order = {
            "project_id": "Demo",
            "release_order_id": "ro-gray",
            "status": "published",
            "payload": {
                "release_strategy": "gray",
                "gray_success_action": "automatic",
                "gray_paused_at": "2026-08-19T10:00:00",
            },
            "published_at": "2026-08-19T09:00:00",
            "bundle_id": "rb-gray",
        }
        bundle = {
            "release_strategy": "gray",
            "gray_success_action": "hold",
            "client": {"rollout_percentage": 20},
        }
        self.assertFalse(sched._should_auto_expand(order, bundle))


if __name__ == "__main__":
    unittest.main()
