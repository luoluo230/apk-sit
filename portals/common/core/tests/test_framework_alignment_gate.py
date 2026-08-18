# -*- coding: utf-8 -*-
"""Full alignment gate: client bootstrap, server frameworks, deploy packs, server release."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
import zipfile
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: E402
from models.db import init_db  # noqa: E402


class FrameworkAlignmentGateTests(unittest.TestCase):
    TOPO_PROJECT = "align_topo_proj"
    BAAS_PROJECT = "align_baas_proj"
    GAME_TOPO = "align-topo-gid"
    GAME_BAAS = "align-baas-gid"

    @classmethod
    def setUpClass(cls):
        from repositories.admin import projects_repo
        from services.baas.service_crud import ensure_service

        init_db()
        projects_repo.upsert_project(cls.TOPO_PROJECT, {
            "name": "Align Topo",
            "game_id": cls.GAME_TOPO,
            "game_key": "align-topo-key",
            "server_mode": "topology",
            "status": "active",
        })
        projects_repo.upsert_project(cls.BAAS_PROJECT, {
            "name": "Align BaaS",
            "game_id": cls.GAME_BAAS,
            "game_key": "align-baas-key",
            "server_mode": "casual_baas",
            "status": "active",
        })
        ensure_service(cls.BAAS_PROJECT, "development", actor="admin")

    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_topology_client_network_module(self):
        resp = self.client.get(
            "/api/public/client-network-module",
            query_string={"game_id": self.GAME_TOPO, "game_key": "align-topo-key"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertEqual(body.get("server_module", {}).get("key"), "topology_server")
        self.assertEqual(body.get("client_module", {}).get("key"), "topology_client")

    def test_baas_client_network_module(self):
        resp = self.client.get(
            "/api/public/client-network-module",
            query_string={"game_id": self.GAME_BAAS, "game_key": "align-baas-key"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertEqual(body.get("server_module", {}).get("key"), "casual_baas_server")
        self.assertEqual(body.get("client_module", {}).get("key"), "baas_client")

    def test_baas_unified_client_bootstrap(self):
        resp = self.client.get(
            "/api/public/client-bootstrap",
            query_string={
                "game_id": self.GAME_BAAS,
                "game_key": "align-baas-key",
                "env": "development",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertEqual(body.get("framework"), "casual_baas")
        self.assertIn("public_api_base", body)
        self.assertIn("endpoints", body)

    def test_baas_legacy_bootstrap_path(self):
        resp = self.client.get(
            "/api/public/baas-bootstrap",
            query_string={
                "game_id": self.GAME_BAAS,
                "game_key": "align-baas-key",
                "env": "development",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertTrue(body.get("ok"))
        self.assertIn("public_api_base", body)

    def test_topology_project_rejects_baas_bootstrap(self):
        resp = self.client.get(
            "/api/public/baas-bootstrap",
            query_string={
                "game_id": self.GAME_TOPO,
                "game_key": "align-topo-key",
                "env": "development",
            },
        )
        self.assertIn(resp.status_code, (400, 422))
        body = resp.get_json() or {}
        self.assertFalse(body.get("ok", True))

    def test_deploy_pack_topology_manifest(self):
        from services.server_management.deploy_pack_service import build_deploy_pack

        blob, name = build_deploy_pack("topology")
        self.assertIn("topology", name)
        self.assertGreater(len(blob), 1000)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = set(zf.namelist())
            self.assertIn("manifest.json", names)
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(manifest.get("architecture"), "topology_server")
            self.assertTrue(any("topology" in n for n in names))

    def test_deploy_pack_baas_manifest(self):
        from services.server_management.deploy_pack_service import build_deploy_pack

        blob, name = build_deploy_pack("baas")
        self.assertIn("baas", name)
        self.assertGreater(len(blob), 1000)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = set(zf.namelist())
            self.assertIn("manifest.json", names)
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(manifest.get("architecture"), "casual_baas_server")
            self.assertTrue(any("baas" in n.lower() for n in names))

    def test_server_release_state_machine(self):
        from services.release import server_artifact_service as sas
        from services.release import server_release_service as srs
        from unittest import mock

        init_db()
        art = sas.register_artifact(
            self.TOPO_PROJECT,
            {"artifact_id": "art-align-1", "version_label": "1.0.0", "checksum": "abc"},
        )
        rel = srs.create_server_release(
            self.TOPO_PROJECT,
            {
                "artifact_id": art["artifact_id"],
                "topology_id": "topology-align",
                "env_key": "development",
                "target_services": ["svc-1"],
            },
            actor="admin",
        )
        self.assertEqual(rel.get("status"), "ready")
        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-1", "status": "PENDING"}]
            deployed = srs.deploy_server_release(self.TOPO_PROJECT, rel["server_release_id"], actor="admin")
        self.assertEqual(deployed.get("status"), "deploying")

    def test_baas_bootstrap_contract_fixture(self):
        from services.release.baas_bootstrap_contract import assert_baas_bootstrap_contract, contract_fixture_path

        with open(contract_fixture_path(), encoding="utf-8") as fh:
            sample = json.load(fh)
        assert_baas_bootstrap_contract(sample)

    def test_baas_bootstrap_contract_live_response(self):
        from services.release.baas_bootstrap_contract import validate_baas_bootstrap_contract

        resp = self.client.get(
            "/api/public/client-bootstrap",
            query_string={
                "game_id": self.GAME_BAAS,
                "game_key": "align-baas-key",
                "env": "development",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        body["framework"] = "casual_baas"
        body["bootstrap_kind"] = "baas"
        errors = validate_baas_bootstrap_contract(body)
        self.assertEqual(errors, [], msg="; ".join(errors))

    def test_server_artifact_promotion_flow(self):
        from services.release import server_artifact_service as sas
        from services.release import server_release_service as srs
        from services.release.server_artifact_promotion_service import (
            list_server_promotion_candidates,
            promote_server_artifact_to_env,
        )

        init_db()
        art = sas.register_artifact(
            self.TOPO_PROJECT,
            {"artifact_id": "art-promo-1", "version_label": "1.0.0", "checksum": "abc"},
        )
        rel = srs.create_server_release(
            self.TOPO_PROJECT,
            {
                "artifact_id": art["artifact_id"],
                "topology_id": "topology-align",
                "env_key": "development",
                "target_services": ["svc-1"],
            },
            actor="admin",
        )
        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-1", "status": "PENDING"}]
            srs.deploy_server_release(self.TOPO_PROJECT, rel["server_release_id"], "admin")
        srs.complete_deploy_server_release(
            self.TOPO_PROJECT, rel["server_release_id"], ok=True, actor="admin", service_id="svc-1"
        )
        candidates = list_server_promotion_candidates(self.TOPO_PROJECT)
        self.assertTrue(any(c.get("server_release_id") == rel["server_release_id"] for c in candidates))
        promoted = promote_server_artifact_to_env(
            self.TOPO_PROJECT,
            rel["server_release_id"],
            "testing",
            "admin",
        )
        self.assertEqual(promoted.get("target_env_key"), "testing")
        self.assertTrue(promoted.get("server_release_id"))


if __name__ == "__main__":
    unittest.main()
