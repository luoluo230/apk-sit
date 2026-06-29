# -*- coding: utf-8 -*-
"""Version create helpers — iOS path extension and multi-channel create."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: F401 — bootstrap imports

from services.apk_artifact_service import default_version_apk_rel_path, _expected_archive_filename
from services.admin import version_service as vs
from repositories.admin import versions_repo


class VersionCreateTests(unittest.TestCase):
    def test_expected_archive_filename_ios_uses_ipa(self):
        name = _expected_archive_filename(
            {"platform": "ios", "version_name": "1.0.0", "version_code": "12"},
            "GomeKu",
        )
        self.assertTrue(name.endswith(".ipa"))

    def test_default_apk_rel_path_ios_uses_ipa(self):
        path = default_version_apk_rel_path(
            "GomeKu",
            {
                "platform": "ios",
                "version_name": "1.0.0",
                "version_code": "12",
                "channel": "1001",
                "stage": "dev",
            },
        )
        self.assertTrue(path.endswith(".ipa"))

    def test_build_new_version_row_ios_passes_validation(self):
        pid = "GomeKu"
        if not versions_repo.has_project(pid):
            self.skipTest("GomeKu project not in test data")
        data = {
            "env_key": "development",
            "platform": "ios",
            "version_name": "1.0.0",
            "version_code": "unittest_vc_ios",
            "version_status": "draft",
            "channel_id": "1001",
        }
        versions = versions_repo.list_versions(pid)
        row, err, status = vs._build_new_version_row(pid, "admin", data, versions)
        self.assertIsNone(err, err)
        self.assertEqual(status, 200)
        self.assertTrue(str((row or {}).get("apk_path") or "").endswith(".ipa"))

    def test_create_version_apply_all_channels_ios(self):
        pid = "GomeKu"
        if not versions_repo.has_project(pid):
            self.skipTest("GomeKu project not in test data")
        vc = "unittest_all_ch_ios"
        with app.test_request_context():
            from flask import session

            session["user"] = "admin"
            versions = versions_repo.list_versions(pid)
            versions[:] = [row for row in versions if str(row.get("version_code") or "") != vc]
            versions_repo.save_versions(pid, versions)

            payload = {
                "apply_all_channels": True,
                "env_key": "development",
                "platform": "ios",
                "version_name": "1.0.0",
                "version_code": vc,
                "version_status": "draft",
            }
            result, status = vs.create_version(pid, "admin", payload)
            self.assertEqual(status, 200, result)
            self.assertGreaterEqual(int(result.get("created_count") or 0), 1)

            versions = versions_repo.list_versions(pid)
            matched = [
                row
                for row in versions
                if str(row.get("version_code") or "") == vc and str(row.get("platform") or "") == "ios"
            ]
            versions[:] = [row for row in versions if str(row.get("version_code") or "") != vc]
            versions_repo.save_versions(pid, versions)
            self.assertGreaterEqual(len(matched), 1)
            for row in matched:
                self.assertTrue(str(row.get("apk_path") or "").endswith(".ipa"))


if __name__ == "__main__":
    unittest.main()
