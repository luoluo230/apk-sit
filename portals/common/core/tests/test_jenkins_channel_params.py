# -*- coding: utf-8 -*-
"""P3-03 Wave B: Jenkins channel triple contract."""

from __future__ import annotations

import unittest
from unittest import mock

from services.release.jenkins_channel_params import apply_jenkins_channel_params, resolve_jenkins_channel_params


class JenkinsChannelParamsTests(unittest.TestCase):
    def test_numeric_channel_keeps_id_and_slug(self):
        with mock.patch(
            "services.commercial_release_plan.get_channel_by_id",
            return_value={"id": "1001", "apk_subdir": "wechat", "build_param": "CHANNEL=wechat"},
        ):
            triple = resolve_jenkins_channel_params("1001")
        self.assertEqual(triple["VERSION_CHANNEL_ID"], "1001")
        self.assertEqual(triple["CHANNEL"], "1001")
        self.assertEqual(triple["RELEASE_CHANNEL"], "wechat")

    def test_apply_overwrites_params(self):
        with mock.patch(
            "services.commercial_release_plan.get_channel_by_id",
            return_value={"id": "1001", "apk_subdir": "wechat", "build_param": ""},
        ):
            params = apply_jenkins_channel_params({"RELEASE_CHANNEL": "stale", "CHANNEL": "x"}, "1001")
        self.assertEqual(params["CHANNEL"], "1001")
        self.assertEqual(params["VERSION_CHANNEL_ID"], "1001")
        self.assertEqual(params["RELEASE_CHANNEL"], "wechat")

    def test_empty_channel_rejected(self):
        with self.assertRaises(ValueError):
            resolve_jenkins_channel_params("")


if __name__ == "__main__":
    unittest.main()
