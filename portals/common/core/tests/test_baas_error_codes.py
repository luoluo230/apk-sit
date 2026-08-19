# -*- coding: utf-8 -*-
"""Tests for BaaS unified error envelope."""

from __future__ import annotations

import json
import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from services.baas.errors import (
    baas_error,
    baas_error_from_message,
    code_meta,
    list_error_codes,
    resolve_code,
)


class BaasErrorCodeTests(unittest.TestCase):
    def test_catalog_loaded(self):
        codes = list_error_codes()
        self.assertGreater(len(codes), 50)
        self.assertIn("BAAS_ROOM_NOT_FOUND", codes)

    def test_message_alias_resolves(self):
        self.assertEqual(resolve_code("房间不存在"), "BAAS_ROOM_NOT_FOUND")
        self.assertEqual(resolve_code("BAAS_AUTH_MISSING_KEY"), "BAAS_AUTH_MISSING_KEY")

    def test_error_body_shape(self):
        err = baas_error("BAAS_AUTH_MISSING_KEY")
        body = err.to_body()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error_code"], "BAAS_AUTH_MISSING_KEY")
        self.assertIn("error", body)

    def test_unknown_message_maps_to_unknown(self):
        err = baas_error_from_message("some novel message")
        self.assertEqual(err.code, "BAAS_UNKNOWN")

    def test_http_status_from_catalog(self):
        meta = code_meta("BAAS_ROOM_NOT_FOUND")
        self.assertEqual(int(meta["http_status"]), 404)


if __name__ == "__main__":
    unittest.main()
