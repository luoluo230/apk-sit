# -*- coding: utf-8 -*-
"""Server deploy webhook notification tests."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")

from models.db import init_db
from services.notify.outbound_webhook import EVENT_SERVER_DEPLOY_COMPLETED, EVENT_SERVER_DEPLOY_FAILED
from services.release.server_deploy_notify import notify_server_deploy_transition


class ServerDeployNotifyTests(unittest.TestCase):
    def setUp(self):
        init_db()

    @mock.patch("services.release.server_deploy_notify.notify_release_event")
    def test_deployed_transition_fires_completed(self, notify_fn):
        row = {
            "server_release_id": "sro-n1",
            "env_key": "development",
            "topology_id": "topo-1",
            "artifact_id": "sart-n1",
            "target_services": ["game-cn-1"],
            "status": "deployed",
            "payload": {"linked_release_order_id": "ro-1"},
        }
        notify_server_deploy_transition("GomeKu", row, "deployed", "agent")
        notify_fn.assert_called_once()
        self.assertEqual(notify_fn.call_args.args[0], EVENT_SERVER_DEPLOY_COMPLETED)

    @mock.patch("services.release.server_deploy_notify.notify_release_event")
    def test_failed_transition_fires_failed(self, notify_fn):
        row = {
            "server_release_id": "sro-n2",
            "env_key": "staging",
            "topology_id": "topo-1",
            "artifact_id": "sart-n2",
            "target_services": ["game-cn-1"],
            "status": "failed",
            "payload": {},
        }
        notify_server_deploy_transition("GomeKu", row, "failed", "agent", error="agent timeout")
        notify_fn.assert_called_once()
        self.assertEqual(notify_fn.call_args.args[0], EVENT_SERVER_DEPLOY_FAILED)

    @mock.patch("services.release.server_deploy_notify.notify_release_event")
    def test_transition_server_release_wires_notify(self, notify_fn):
        from services.release import server_artifact_service as sas
        from services.release import server_release_service as srs

        art = sas.register_artifact(
            "GomeKu",
            {"artifact_id": "sart-notify-1", "version_label": "1.0.0", "checksum": "x"},
        )
        rel = srs.create_server_release(
            "GomeKu",
            {
                "artifact_id": art["artifact_id"],
                "topology_id": "topo-notify",
                "env_key": "development",
                "target_services": ["game-cn-1"],
            },
            "tester",
        )
        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-n1"}]
            srs.deploy_server_release("GomeKu", rel["server_release_id"], "tester")
        srs.complete_deploy_server_release("GomeKu", rel["server_release_id"], ok=True, actor="agent")
        self.assertTrue(any(c.args[0] == EVENT_SERVER_DEPLOY_COMPLETED for c in notify_fn.call_args_list))


if __name__ == "__main__":
    unittest.main()
