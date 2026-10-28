# -*- coding: utf-8 -*-
"""Production startup must refuse missing secrets and SQLite. Plan P0-01 / P0-02."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from config import Config, require_production_database, require_production_secrets


class ProductionStartupGateTests(unittest.TestCase):
    def test_development_skips_secret_and_database_gates(self):
        with mock.patch.object(Config, "is_production", return_value=False):
            require_production_secrets()
            require_production_database()

    def test_production_missing_secrets_exits(self):
        env = {
            "APK_SECRET": "",
            "FLASK_SECRET_KEY": "",
            "JENKINS_BUILD_WEBHOOK_SECRET": "",
            "APPROVAL_WEBHOOK_SECRET": "",
            "BUILD_NODE_WEBHOOK_SECRET": "",
            "BUILD_NODE_SHARED_SECRET": "",
            "CLUSTER_RELAY_TOKEN": "",
        }
        with mock.patch.object(Config, "is_production", return_value=True), mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                require_production_secrets()
        self.assertIn("APK_SECRET", str(ctx.exception))

    def test_production_sqlite_url_is_rejected(self):
        with mock.patch.object(Config, "is_production", return_value=True), mock.patch.dict(
            os.environ, {"DATABASE_URL": ""}, clear=False
        ):
            with self.assertRaises(RuntimeError) as ctx:
                require_production_database()
        self.assertIn("PostgreSQL", str(ctx.exception))

    def test_production_postgres_url_passes_database_gate(self):
        with mock.patch.object(Config, "is_production", return_value=True), mock.patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://portal:secret@db/portal"}, clear=False
        ):
            require_production_database()


if __name__ == "__main__":
    unittest.main()
