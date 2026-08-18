# -*- coding: utf-8 -*-
"""Artifact promotion approval tests (P3-3)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")

from services.release.promotion_approval_service import is_promoted_release_order
from services.release.release_policy_service import (
    get_promotion_approval_tiers,
    requires_promotion_approval,
)


class PromotionApprovalPolicyTests(unittest.TestCase):
    def test_staging_requires_promotion_approval(self):
        self.assertTrue(requires_promotion_approval("__any__", "staging"))

    def test_development_skips_promotion_approval(self):
        self.assertFalse(requires_promotion_approval("__any__", "development"))

    def test_promotion_tiers_include_qa(self):
        tiers = get_promotion_approval_tiers("__any__", "staging")
        self.assertIn("qa", tiers)

    def test_production_tiers_include_qa_and_release_manager(self):
        tiers = get_promotion_approval_tiers("__any__", "production")
        self.assertEqual(tiers[0], "qa")
        self.assertIn("release_manager", tiers)

    def test_is_promoted_release_order(self):
        self.assertTrue(
            is_promoted_release_order({"payload": {"promotion": {"promoted_from_bundle_id": "rb-1"}}})
        )
        self.assertFalse(is_promoted_release_order({"payload": {}}))


class PromotionApprovalFlowTests(unittest.TestCase):
    @mock.patch("services.release.bundle_promotion_service.notify_promotion_approval_pending")
    @mock.patch("services.release.bundle_promotion_service.seed_release_order_promotion_approvals")
    @mock.patch("services.release.bundle_promotion_service.get_cursor")
    @mock.patch("services.release.bundle_promotion_service._bundle_row")
    @mock.patch("services.release.bundle_promotion_service._find_target_version")
    @mock.patch("services.release.bundle_promotion_service.resolve_topology_binding_for_scope")
    @mock.patch("services.release.bundle_promotion_service.resolve_scope")
    def test_promote_to_staging_enters_awaiting_approval(
        self,
        resolve_scope,
        resolve_binding,
        find_version,
        bundle_row,
        cursor_cm,
        seed_fn,
        notify_fn,
    ):
        from models.data import projects_db
        from services.release.bundle_promotion_service import promote_bundle_to_env

        pid = "__test_promo_approval__"
        projects_db[pid] = {"name": "Promo Approval"}
        bundle_row.return_value = {
            "bundle_id": "rb-src",
            "project_id": pid,
            "env_key": "testing",
            "channel_id": "wechat",
            "platform": "android",
            "version_name": "1.0.0",
            "version_code": "100",
            "publish_status": "published",
            "release_order_id": "ro-src",
            "client": {
                "apk_url": "https://example/apk.apk",
                "resource_url": "https://example/res.zip",
                "config_url": "https://example/cfg.zip",
            },
        }
        find_version.return_value = {
            "id": "v-staging",
            "version_name": "1.0.0",
            "version_code": "100",
            "apk_url": "https://example/apk.apk",
            "resource_url": "https://example/res.zip",
            "config_url": "https://example/cfg.zip",
        }
        resolve_scope.return_value = {"scope_id": "scope-staging"}
        resolve_binding.return_value = {"topology_id": "topo-1", "binding_source": "auto"}
        cur = mock.MagicMock()
        cursor_cm.return_value.__enter__.return_value = cur
        cursor_cm.return_value.__exit__.return_value = False

        with mock.patch("services.release.order_crud.get_release_order") as get_order:
            get_order.return_value = {
                "release_order_id": "ro-new",
                "status": "awaiting_approval",
                "payload": {"promotion": {"promoted_from_bundle_id": "rb-src"}},
            }
            result = promote_bundle_to_env(pid, "rb-src", "staging", "tester")

        self.assertTrue(result["requires_promotion_approval"])
        self.assertEqual(result["next_action"], "approval")
        order_insert = cur.execute.call_args_list[0]
        self.assertEqual(order_insert.args[1][13], "awaiting_approval")
        seed_fn.assert_called_once()
        notify_fn.assert_called_once()
        projects_db.pop(pid, None)

    @mock.patch("services.release.server_release_service.transition_server_release")
    @mock.patch("services.release.server_release_service.update_server_release")
    @mock.patch("services.release.server_release_service.get_server_release")
    def test_approve_server_promotion_moves_to_ready(self, get_fn, update_fn, transition_fn):
        from services.release.server_artifact_promotion_service import approve_server_promotion

        get_fn.return_value = {
            "server_release_id": "sro-promo-1",
            "status": "awaiting_approval",
            "payload": {"promotion": {"promoted_from_server_release_id": "sro-src"}},
        }
        update_fn.return_value = get_fn.return_value
        transition_fn.return_value = {"server_release_id": "sro-promo-1", "status": "ready"}

        out = approve_server_promotion("p1", "sro-promo-1", "qa-user", note="ok")
        self.assertEqual(out["status"], "ready")
        transition_fn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
