# -*- coding: utf-8 -*-
"""Human-facing release storyline mapping."""

from __future__ import annotations

import unittest


class FlowStorylineTests(unittest.TestCase):
    def test_status_maps_to_pipeline_stage(self):
        from services.release.flow_storyline_service import (
            pipeline_steps,
            stage_id_for_status,
            status_label,
        )

        self.assertEqual(stage_id_for_status("building"), "build")
        self.assertEqual(stage_id_for_status("artifacts_ready"), "artifacts")
        self.assertEqual(stage_id_for_status("awaiting_approval"), "approval")
        self.assertEqual(stage_id_for_status("verified"), "live")
        self.assertEqual(status_label("awaiting_approval"), "待审批")

        steps = pipeline_steps("precheck")
        states = {row["id"]: row["state"] for row in steps}
        self.assertEqual(states["build"], "done")
        self.assertEqual(states["precheck"], "current")
        self.assertEqual(states["publish"], "todo")
        self.assertEqual(len(steps), 7)

    def test_empty_storyline_points_to_console(self):
        from services.release.flow_storyline_service import build_storyline

        data = build_storyline("p1", "development", [], release_href="/admin/projects/p1/release")
        self.assertFalse(data["has_in_flight"])
        self.assertEqual(data["primary"]["href"], "/admin/projects/p1/release")
        self.assertEqual(data["primary"]["label"], "去发版")

    def test_in_flight_storyline_uses_next_action(self):
        from services.release.flow_storyline_service import build_storyline

        pending = [
            {
                "env_key": "production",
                "env_label": "生产",
                "channel_name": "微信",
                "platform": "android",
                "version_name": "1.2.0",
                "version_code": "12",
                "status": "awaiting_approval",
                "href": "/order/1",
                "next_action": {"label": "下一步：去审批", "href": "/approval"},
            }
        ]
        data = build_storyline("p1", "production", pending, release_href="/release")
        self.assertTrue(data["has_in_flight"])
        self.assertEqual(data["current_stage"], "approval")
        self.assertEqual(data["primary"]["href"], "/approval")
        self.assertEqual(data["status_label"], "待审批")


if __name__ == "__main__":
    unittest.main()
