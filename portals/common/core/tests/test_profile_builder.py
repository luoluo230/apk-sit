# -*- coding: utf-8 -*-

import unittest

from services.release.profile_builder import build_network_profile_from_topology, merge_network_profiles


class ProfileBuilderTests(unittest.TestCase):
    def test_build_from_topology_gateway_port(self):
        topo = {
            "nodes": [
                {
                    "id": "gateway-cn-1",
                    "role": "gateway",
                    "port": 15050,
                    "ui": {"remote": {"host": "127.0.0.1", "port": 15050}},
                },
                {
                    "id": "auth-cn-1",
                    "role": "auth",
                    "ui": {"remote": {"host": "127.0.0.1", "port": 5501}},
                },
                {
                    "id": "ops-cn-1",
                    "role": "ops",
                    "ui": {"remote": {"host": "127.0.0.1", "port": 5504}},
                },
            ]
        }
        profile = build_network_profile_from_topology(topo)
        self.assertIn(":15050", profile.get("gateway_ws", ""))

    def test_merge_manual_over_auto(self):
        auto = {"gateway_ws": "ws://127.0.0.1:15050/ws/", "ops_http": "http://127.0.0.1:5504"}
        manual = {"gateway_ws": "wss://custom.example/ws/"}
        merged = merge_network_profiles(auto, manual)
        self.assertEqual(merged["gateway_ws"], "wss://custom.example/ws/")
        self.assertEqual(merged["ops_http"], "http://127.0.0.1:5504")


if __name__ == "__main__":
    unittest.main()
