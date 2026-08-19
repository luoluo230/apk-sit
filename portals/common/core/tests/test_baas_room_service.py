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


    @mock.patch("services.baas.room_service.feature_enabled", return_value=True)
    @mock.patch("services.baas.room_service.get_feature_config", return_value={"max_players": 2, "max_spectators": 4})
    def test_poll_frames_fanout_excludes_self(self, _cfg, _enabled):
        import threading
        from services.baas import room_service

        host = room_service.create_room("svc1", "host", visibility="public", battle_mode="pvp_1v1")
        guest = room_service.join_room("svc1", "guest", room_id=host["room_id"])
        self.assertEqual(guest["status"], "ready")
        room_service.start_battle("svc1", host["room_id"], "host")
        result: dict = {}

        def poll_guest():
            result["payload"] = room_service.poll_frames(
                "svc1",
                host["room_id"],
                since_seq=0,
                wait_ms=3000,
                exclude_player_id="guest",
            )

        worker = threading.Thread(target=poll_guest)
        worker.start()
        threading.Event().wait(0.05)
        room_service.push_frame("svc1", host["room_id"], "host", {"action": "attack"})
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        payload = result.get("payload") or {}
        self.assertTrue(payload.get("polled"))
        frames = payload.get("frames") or []
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].get("player_id"), "host")

    @mock.patch("services.baas.room_service.feature_enabled", return_value=True)
    @mock.patch("services.baas.room_service.get_feature_config", return_value={"max_players": 2, "max_spectators": 4})
    def test_admin_room_ops(self, _cfg, _enabled):
        from services.baas import room_service

        host = room_service.create_room("svc1", "host", visibility="public")
        room_service.join_room("svc1", "guest", room_id=host["room_id"])
        room_service.start_battle("svc1", host["room_id"], "host")
        room_service.push_frame("svc1", host["room_id"], "host", {"move": 1})
        stats = room_service.room_stats("svc1")
        self.assertGreaterEqual(stats["total"], 1)
        rows = room_service.list_all_rooms("svc1", status="active")
        self.assertTrue(any(r["room_id"] == host["room_id"] for r in rows))
        detail = room_service.get_room_detail("svc1", host["room_id"])
        self.assertEqual(detail["frame_count"], 1)
        room_service.admin_kick_player("svc1", host["room_id"], "guest")
        after_kick = room_service.get_room_detail("svc1", host["room_id"])
        self.assertNotIn("guest", after_kick.get("players") or [])
        finished = room_service.admin_finish_battle("svc1", host["room_id"], result={"winner": "host"})
        self.assertEqual(finished["status"], "finished")
        self.assertTrue(finished.get("replay_id"))
        replays = room_service.list_replays("svc1")
        self.assertTrue(any(r["replay_id"] == finished["replay_id"] for r in replays))
        room_service.admin_force_close("svc1", host["room_id"], reason="cleanup")
        closed = room_service.get_room_detail("svc1", host["room_id"])
        self.assertEqual(closed["status"], "closed")


    @mock.patch("services.baas.room_service.feature_enabled", return_value=True)
    @mock.patch("services.baas.room_service.get_feature_config", return_value={"max_players": 2, "max_spectators": 4})
    def test_room_persistence_reload(self, _cfg, _enabled):
        from services.baas import room_service, room_store

        room_service._rooms.clear()
        room_service._replays.clear()
        host = room_service.create_room("svc1", "host", visibility="public")
        room_service.join_room("svc1", "guest", room_id=host["room_id"])
        room_service.start_battle("svc1", host["room_id"], "host")
        room_service.push_frame("svc1", host["room_id"], "host", {"action": "move"})
        room_id = host["room_id"]
        room_service._rooms.clear()
        reloaded = room_service.get_room("svc1", room_id)
        self.assertEqual(reloaded["status"], "active")
        self.assertGreaterEqual(int(reloaded.get("frame_seq") or 0), 1)
        stored = room_store.load_room(room_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.get("room_id"), room_id)


if __name__ == "__main__":
    unittest.main()
