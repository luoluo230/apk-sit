# -*- coding: utf-8 -*-
"""Bootstrap hot-update regression tests."""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from services.release.bootstrap_contract import contract_fixture_path
from services.release.bootstrap_hotupdate_regression import (
    assemble_bootstrap_view_from_bundle,
    compare_bootstrap_views,
    run_hotupdate_regression_for_order,
    validate_fixture_regression,
)


class BootstrapHotupdateRegressionTests(unittest.TestCase):
    def test_fixture_passes_offline_regression(self):
        errors = validate_fixture_regression(contract_fixture_path())
        self.assertEqual([], errors, msg="; ".join(errors))

    def test_assemble_view_matches_fixture(self):
        fixture_path = contract_fixture_path()
        with open(fixture_path, encoding="utf-8") as fh:
            fixture = json.load(fh)
        bundle = {
            "bundle_id": fixture["active_bundle_id"],
            "scope_id": fixture["scope_id"],
            "project_id": fixture["project_id"],
            "client": dict(fixture.get("bootstrap") or {}),
            "server": {"network_profile_snapshot": dict(fixture.get("network_profile") or {})},
        }
        view = assemble_bootstrap_view_from_bundle(bundle)
        self.assertEqual(view["active_bundle_id"], fixture["active_bundle_id"])
        self.assertEqual(view["bootstrap"]["catalog_url"], fixture["bootstrap"]["catalog_url"])
        self.assertEqual(view["network_profile"]["gateway_ws"], fixture["network_profile"]["gateway_ws"])

    def test_detect_catalog_drift(self):
        base = {
            "ok": True,
            "active_bundle_id": "b1",
            "bootstrap": {"catalog_url": "https://a.example/catalog.bin"},
            "network_profile": {"gateway_ws": "ws://127.0.0.1:15050/ws"},
        }
        drift = dict(base)
        drift["bootstrap"] = {"catalog_url": "https://b.example/other.bin"}
        errors = compare_bootstrap_views(drift, base)
        self.assertTrue(any("catalog_url" in e for e in errors))

    @mock.patch("services.release.order_publish_lifecycle.run_bootstrap_smoke_for_order")
    @mock.patch("services.release.scope_resolver.resolve_network_profile")
    @mock.patch("services.release.scope_resolver.resolve_scope")
    @mock.patch("services.release.bundle_service.find_active_bundle")
    @mock.patch("services.release.order_crud.get_release_order")
    def test_run_regression_for_order_ok(
        self,
        get_order,
        find_bundle,
        resolve_scope,
        resolve_np,
        smoke_fn,
    ):
        order = {
            "release_order_id": "ro-reg-1",
            "scope_id": "scope-reg",
            "bundle_id": "bundle-reg",
            "platform": "android",
            "env_key": "development",
            "channel_id": "wechat",
            "version_name": "1.0.0",
        }
        bundle = {
            "bundle_id": "bundle-reg",
            "scope_id": "scope-reg",
            "client": {
                "catalog_url": "https://example/catalog.bin",
                "catalog_file_name": "catalog_1.0.0.bin",
                "resource_relative_path": "development/wechat/android/Version_1.0.0/12",
                "min_client_version": "1.0.0",
                "max_client_version": "9.9.9",
                "rollout_percentage": 100,
                "force_update": False,
                "is_revoked": False,
                "resource_server_url": "https://example.oss.aliyuncs.com/bucket",
            },
            "server": {
                "network_profile_snapshot": {
                    "gateway_ws": "ws://127.0.0.1:15050/ws",
                    "login_http": "http://127.0.0.1:15051",
                }
            },
        }
        get_order.return_value = order
        find_bundle.return_value = bundle
        resolve_scope.return_value = {"scope_id": "scope-reg", "project_id": "GomeKu"}
        resolve_np.return_value = (bundle["server"]["network_profile_snapshot"], "topology")
        smoke_fn.return_value = {"ok": True, "checks": []}

        out = run_hotupdate_regression_for_order("GomeKu", "ro-reg-1")
        self.assertTrue(out.get("ok"))


if __name__ == "__main__":
    unittest.main()
