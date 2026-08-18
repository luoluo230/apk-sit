# -*- coding: utf-8
"""Server management hub tests."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")
os.environ.setdefault("PORTAL_SERVER_FRAMEWORKS", "all")

from config import load_dotenv

load_dotenv()

from models.data import projects_db
from repositories.admin import projects_repo
from services.baas.service_crud import create_service, delete_service, get_service, service_id_exists, update_service
from services.ops.topology_registry import (
    _get_topology_registry_row,
    _topology_id_exists,
    create_topology_registry_entry,
    delete_topology_registry_entry,
    update_topology_registry_entry,
)
from services.server_management.hub_service import (
    build_baas_card,
    build_topology_card,
    list_baas_cards,
    list_topology_cards,
    topology_delete_guard,
)

_TEST_PROJECT = "test_sm_hub_proj"
_TEST_TOPO_ID = "test-sm-topo-001"
_TEST_BAAS_ID = "test-sm-baas-001"


class ServerManagementHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        projects_db[_TEST_PROJECT] = {
            "name": "SM Hub Test",
            "game_id": "sm-hub-game",
            "game_key": "sm-hub-key",
            "server_mode": "topology",
            "status": "active",
            "created_by": "admin",
        }
        projects_repo.upsert_project(_TEST_PROJECT, projects_db[_TEST_PROJECT])

    def setUp(self):
        if _topology_id_exists(_TEST_TOPO_ID):
            delete_topology_registry_entry(_TEST_TOPO_ID)
        if service_id_exists(_TEST_BAAS_ID):
            try:
                delete_service(_TEST_PROJECT, _TEST_BAAS_ID)
            except ValueError:
                pass

    def tearDown(self):
        if _topology_id_exists(_TEST_TOPO_ID):
            delete_topology_registry_entry(_TEST_TOPO_ID)
        if service_id_exists(_TEST_BAAS_ID):
            try:
                delete_service(_TEST_PROJECT, _TEST_BAAS_ID)
            except ValueError:
                pass

    def test_create_topology_custom_id(self):
        row = create_topology_registry_entry(
            {
                "project_id": _TEST_PROJECT,
                "topology_id": _TEST_TOPO_ID,
                "name": "测试拓扑",
                "description": "desc",
                "env_key": "development",
            },
            actor="admin",
        )
        self.assertEqual(row["topology_id"], _TEST_TOPO_ID)
        cards = list_topology_cards(project_id=_TEST_PROJECT, query=_TEST_TOPO_ID)
        self.assertTrue(any(c["id"] == _TEST_TOPO_ID for c in cards))

    def test_topology_duplicate_id_raises(self):
        create_topology_registry_entry(
            {"project_id": _TEST_PROJECT, "topology_id": _TEST_TOPO_ID, "name": "A", "env_key": "development"},
            actor="admin",
        )
        with self.assertRaises(ValueError):
            create_topology_registry_entry(
                {"project_id": _TEST_PROJECT, "topology_id": _TEST_TOPO_ID, "name": "B", "env_key": "development"},
                actor="admin",
            )

    def test_topology_name_id_immutable_on_update(self):
        create_topology_registry_entry(
            {"project_id": _TEST_PROJECT, "topology_id": _TEST_TOPO_ID, "name": "Orig", "env_key": "development"},
            actor="admin",
        )
        with self.assertRaises(ValueError):
            update_topology_registry_entry(_TEST_TOPO_ID, {"name": "New"})
        updated = update_topology_registry_entry(_TEST_TOPO_ID, {"description": "updated desc", "disabled": True})
        self.assertEqual(updated.get("description"), "updated desc")
        self.assertTrue(updated.get("disabled"))

    def test_topology_card_shape(self):
        row = create_topology_registry_entry(
            {"project_id": _TEST_PROJECT, "topology_id": _TEST_TOPO_ID, "name": "Card Topo", "env_key": "development"},
            actor="admin",
        )
        card = build_topology_card(row, [])
        self.assertEqual(card["kind"], "topology")
        self.assertIn("runtime", card)
        self.assertIn("actions", card)
        self.assertIn("canvas_url", card["actions"])

    def test_create_baas_custom_id(self):
        svc, secret = create_service(
            {
                "project_id": _TEST_PROJECT,
                "service_id": _TEST_BAAS_ID,
                "name": "测试 BaaS",
                "description": "轻量服务",
                "env_key": "development",
            },
            actor="admin",
        )
        self.assertEqual(svc["service_id"], _TEST_BAAS_ID)
        self.assertTrue(secret)
        cards = list_baas_cards(project_id=_TEST_PROJECT, query=_TEST_BAAS_ID)
        self.assertTrue(any(c["id"] == _TEST_BAAS_ID for c in cards))

    def test_baas_name_id_immutable_on_update(self):
        create_service(
            {"project_id": _TEST_PROJECT, "service_id": _TEST_BAAS_ID, "name": "BaaS Orig", "env_key": "development"},
            actor="admin",
        )
        with self.assertRaises(ValueError):
            update_service(_TEST_PROJECT, _TEST_BAAS_ID, {"name": "Renamed"})
        updated = update_service(_TEST_PROJECT, _TEST_BAAS_ID, {"description": "new desc", "disabled": True})
        self.assertEqual(updated.get("description"), "new desc")
        self.assertTrue(updated.get("disabled"))

    def test_baas_card_shape(self):
        svc, _ = create_service(
            {"project_id": _TEST_PROJECT, "service_id": _TEST_BAAS_ID, "name": "Card BaaS", "env_key": "development"},
            actor="admin",
        )
        card = build_baas_card(svc)
        self.assertEqual(card["kind"], "baas")
        self.assertIn("config_url", card["actions"])
        self.assertIn("gm_url", card["actions"])

    def test_topology_delete_guard_missing(self):
        self.assertEqual(topology_delete_guard("nonexistent-topology-id-xyz"), "拓扑不存在")

    def test_deploy_pack_build(self):
        from services.server_management.deploy_pack_service import build_deploy_pack

        topo, topo_name = build_deploy_pack("topology")
        self.assertTrue(topo_name.endswith(".zip"))
        self.assertGreater(len(topo), 1000)
        baas, baas_name = build_deploy_pack("baas")
        self.assertIn("baas", baas_name)
        self.assertGreater(len(baas), 1000)

    def test_get_topology_registry_row(self):
        create_topology_registry_entry(
            {"project_id": _TEST_PROJECT, "topology_id": _TEST_TOPO_ID, "name": "Row", "env_key": "development"},
            actor="admin",
        )
        row = _get_topology_registry_row(_TEST_TOPO_ID)
        self.assertIsNotNone(row)
        self.assertEqual(row["topology_id"], _TEST_TOPO_ID)


if __name__ == "__main__":
    unittest.main()
