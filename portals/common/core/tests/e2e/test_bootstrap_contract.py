# -*- coding: utf-8 -*-
"""Bootstrap contract tests shared with maclient (P2-02 Step 1)."""

from __future__ import annotations

import json
import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from services.release.bootstrap_contract import (  # noqa: E402
    CONTRACT_VERSION,
    assert_bootstrap_contract,
    contract_fixture_path,
    validate_bootstrap_contract,
)


class BootstrapContractFixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixture_path = contract_fixture_path()
        with open(self.fixture_path, encoding="utf-8") as fh:
            self.sample = json.load(fh)

    def test_fixture_passes_v2_contract(self):
        errors = validate_bootstrap_contract(self.sample)
        self.assertEqual([], errors, msg="; ".join(errors))

    def test_fixture_version_marker(self):
        self.assertEqual("v2", CONTRACT_VERSION)

    def test_missing_force_update_fails(self):
        broken = dict(self.sample)
        boot = dict(broken.get("bootstrap") or {})
        boot.pop("force_update", None)
        broken["bootstrap"] = boot
        errors = validate_bootstrap_contract(broken)
        self.assertTrue(any("force_update" in err for err in errors))

    def test_missing_network_profile_fails(self):
        broken = dict(self.sample)
        broken.pop("network_profile", None)
        errors = validate_bootstrap_contract(broken)
        self.assertTrue(any("network_profile" in err for err in errors))

    def test_android_case_drift_fails(self):
        broken = json.loads(json.dumps(self.sample))
        broken["bootstrap"]["resource_relative_path"] = "Development/wechat/Android/Version_1.0.0/12"
        errors = validate_bootstrap_contract(broken)
        self.assertTrue(any("android" in err.lower() for err in errors))

    def test_assert_helper_raises(self):
        with self.assertRaises(AssertionError):
            assert_bootstrap_contract({"ok": False})


if __name__ == "__main__":
    unittest.main()
