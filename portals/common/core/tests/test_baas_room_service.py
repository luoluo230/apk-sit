# -*- coding: utf-8
"""Tests for casual room/battle REST service."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


class RoomServiceTests(unittest.TestCase):
    def setUp(self):
        from services.baas import room_service

        room_service._rooms.clear()
        room_service._replays.clear()

    @mock.patch("services.baas.room_service.feature_enabled", return_value=True)
    @mock.patch("services.baas.room_service.get_feature_config", return_value={"max_players": 2, "max_spectators": 4})
    def test_public_room_lifecycle(self, _cfg, _enabled):
        from services.baas import room_service

        host = room_service.create_room("svc1", "host", visibility="public", battle_mode="pvp_1v1")
        guest = room_service.join_room("svc1", "guest", room_id=host["room_id"])
        self.assertEqual(guest["status"], "ready")
        started = room_service.start_battle("svc1", host["room_id"], "host")
        self.assertEqual(started["status"], "active")
        self.assertTrue(started.get("battle_id"))
        synced = room_service.sync_state("svc1", host["room_id"], "host", {"hp": 100})
        self.assertIn("host", synced["state"])
        frame = room_service.push_frame("svc1", host["room_id"], "host", {"action": "move"})
        self.assertGreaterEqual(frame["frame_seq"], 1)
        finished = room_service.finish_battle("svc1", host["room_id"], "host", {"winner": "host"})
        self.assertEqual(finished["status"], "finished")
        replay = room_service.get_replay("svc1", finished["replay_id"])
        self.assertEqual(replay["battle_id"], finished["battle_id"])

    @mock.patch("services.baas.room_service.feature_enabled", return_value=True)
    @mock.patch("services.baas.room_service.get_feature_config", return_value={"max_players": 4, "max_spectators": 4})
    def test_private_room_invite_and_kick(self, _cfg, _enabled):
        from services.baas import room_service

        room = room_service.create_room("svc1", "host", visibility="private", max_players=4)
        joined = room_service.join_room("svc1", "p2", invite_code=room["invite_code"])
        self.assertIn("p2", joined["players"])
        room_service.kick_player("svc1", room["room_id"], "host", "p2")
        after = room_service.get_room("svc1", room["room_id"])
        self.assertNotIn("p2", after["players"])


if __name__ == "__main__":
    unittest.main()
