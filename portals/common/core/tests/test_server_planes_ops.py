# -*- coding: utf-8 -*-
"""Both server planes: topology ops, agent deploy, and casual BaaS."""

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

from app_new import app  # noqa: E402
from models.data import projects_db  # noqa: E402
from repositories.admin import projects_repo  # noqa: E402
from server_frameworks.baas_plane import client_bootstrap, open_service, publish_announcement, send_player_mail  # noqa: E402
from server_frameworks.topology_plane import close_topology, open_topology, read_server_release  # noqa: E402
from services.baas.service_crud import delete_service  # noqa: E402
from services.ops.topology_registry import _load_nodes, _save_nodes, _topology_id_exists  # noqa: E402
from services.release import server_artifact_service as sas  # noqa: E402

TOPO_PROJECT = "test_plane_topo"
BAAS_PROJECT = "test_plane_baas"
TOPO_ID = "test-plane-topo"
ENV = "development"
GW_ID = "test-plane-gw"
BIZ_ID = "test-plane-biz"
TOKEN = "test-plane-token"
AGENT_ID = "test-plane-agent"


def _remember_project(project_id: str, row: dict) -> None:
    projects_db[project_id] = row
    projects_repo.upsert_project(project_id, row)


class ServerPlanesOpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _remember_project(TOPO_PROJECT, {
            "name": "Plane Topology",
            "game_id": "plane-topo-game",
            "game_key": "plane-topo-key",
            "server_mode": "topology",
            "status": "active",
            "created_by": "admin",
        })
        _remember_project(BAAS_PROJECT, {
            "name": "Plane BaaS",
            "game_id": "plane-baas-game",
            "game_key": "plane-baas-key",
            "server_mode": "casual_baas",
            "status": "active",
            "created_by": "admin",
        })
        if _topology_id_exists(TOPO_ID):
            close_topology(TOPO_ID)
        cls._drop_nodes()

    @classmethod
    def tearDownClass(cls):
        if _topology_id_exists(TOPO_ID):
            close_topology(TOPO_ID)
        cls._drop_nodes()
        try:
            from services.baas.service_crud import list_services

            for row in list_services(BAAS_PROJECT, ENV):
                delete_service(BAAS_PROJECT, row["service_id"])
        except Exception:
            pass
        for project_id in (TOPO_PROJECT, BAAS_PROJECT):
            try:
                projects_repo.delete_project(project_id)
            except Exception:
                pass
            projects_db.pop(project_id, None)

    def setUp(self):
        self.client = app.test_client()
        app.config["WTF_CSRF_ENABLED"] = False
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    @classmethod
    def _drop_nodes(cls):
        rows = [row for row in _load_nodes() if str(row.get("id") or "") not in {GW_ID, BIZ_ID}]
        _save_nodes(rows)

    def test_topology_pages_and_catalog(self):
        for path in (
            f"/admin/projects/{TOPO_PROJECT}/server-management",
            f"/admin/projects/{TOPO_PROJECT}/agents",
            f"/admin/projects/{TOPO_PROJECT}/actions",
            f"/admin/projects/{TOPO_PROJECT}/diagnostics",
            f"/admin/projects/{TOPO_PROJECT}/ops",
        ):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)

        catalog = self.client.get("/api/ops-platform/action-catalog")
        self.assertEqual(catalog.status_code, 200)
        actions = catalog.get_json().get("actions") or []
        self.assertTrue(any(row.get("value") == "start" for row in actions))

        presets = self.client.get("/api/ops-platform/node-presets")
        self.assertEqual(presets.status_code, 200)
        ids = {row.get("preset_id") for row in presets.get_json().get("presets") or []}
        self.assertIn("gateway_http", ids)
        self.assertIn("business_main", ids)

    def test_topology_graph_agent_and_deploy(self):
        open_topology(TOPO_PROJECT, ENV, TOPO_ID, "测试拓扑", "admin")
        self.addCleanup(self._cleanup_topology)
        try:
            created = self.client.post(
                f"/api/projects/{TOPO_PROJECT}/topologies",
                json={"name": "列表里的第二份", "env_key": ENV},
            )
            self.assertIn(created.status_code, (200, 201), created.get_data(as_text=True))
            extra_id = ""
            body = created.get_json() or {}
            data = body.get("data") if isinstance(body.get("data"), dict) else body
            extra_id = str((data or {}).get("topology_id") or "")
            if extra_id:
                self.addCleanup(lambda: close_topology(extra_id) if _topology_id_exists(extra_id) else None)

            gateway = self._add_node(GW_ID, "gateway_http", "测试网关", 80, 80)
            self.assertEqual(gateway.get("node", {}).get("id"), GW_ID)
            self.assertEqual(gateway.get("node", {}).get("ops_write_key"), TOKEN)
            from services.ops.topology_registry import _load_nodes as load_nodes
            found = [n for n in load_nodes() if n.get("id") == GW_ID]
            self.assertTrue(found, [n.get("id") for n in load_nodes()][:30])
            self.assertEqual(found[0].get("ops_write_key"), TOKEN)
            business = self._add_node(BIZ_ID, "business_main", "测试游戏服", 320, 80)
            self.assertEqual(business.get("node", {}).get("id"), BIZ_ID)

            edges = (business.get("topology") or {}).get("edges") or []
            self.assertTrue(
                any(edge.get("from") == GW_ID and edge.get("to") == BIZ_ID for edge in edges),
                edges,
            )
            touching = [
                edge for edge in edges
                if edge.get("to") == BIZ_ID or edge.get("from") == GW_ID
            ]
            ordered = [
                edge for edge in touching
                if not (edge.get("from") == GW_ID and edge.get("to") == BIZ_ID)
            ] + [
                edge for edge in touching
                if edge.get("from") == GW_ID and edge.get("to") == BIZ_ID
            ]
            for edge in ordered:
                removed = self.client.post(
                    "/api/ops-platform/topology/edge/delete",
                    json={
                        "project_id": TOPO_PROJECT,
                        "env_key": ENV,
                        "topology_id": TOPO_ID,
                        "edge_id": edge["id"],
                    },
                )
                self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True))

            linked = self.client.post(
                "/api/ops-platform/topology/edge/upsert",
                json={
                    "project_id": TOPO_PROJECT,
                    "env_key": ENV,
                    "topology_id": TOPO_ID,
                    "from": GW_ID,
                    "to": BIZ_ID,
                    "note": "手工连线",
                },
            )
            self.assertEqual(linked.status_code, 200, linked.get_data(as_text=True))
            kept = [
                edge for edge in (linked.get_json().get("topology") or {}).get("edges") or []
                if edge.get("from") == GW_ID and edge.get("to") == BIZ_ID
            ]
            self.assertTrue(kept)

            denied = self.client.post(
                "/api/ops-platform/agent/register",
                json={"node_id": GW_ID, "agent_id": AGENT_ID, "token": "wrong"},
            )
            self.assertEqual(denied.status_code, 403)

            registered = self.client.post(
                "/api/ops-platform/agent/register",
                json={"node_id": GW_ID, "agent_id": AGENT_ID, "token": TOKEN, "hostname": "plane-test"},
                headers={"X-Agent-Token": TOKEN},
            )
            self.assertEqual(registered.status_code, 200, registered.get_data(as_text=True))

            heartbeat = self.client.post(
                "/api/ops-platform/agent/heartbeat",
                json={"node_id": GW_ID, "agent_id": AGENT_ID, "token": TOKEN},
                headers={"X-Agent-Token": TOKEN},
            )
            self.assertEqual(heartbeat.status_code, 200, heartbeat.get_data(as_text=True))

            artifact = sas.register_artifact(
                TOPO_PROJECT,
                {
                    "artifact_id": "sart-test-plane",
                    "version_label": "0.0.1-test",
                    "bundle_path": "memory://test-plane.zip",
                    "checksum": "abc123",
                    "protocol_version": "v1",
                },
            )
            release = self.client.post(
                f"/api/admin/projects/{TOPO_PROJECT}/server-releases",
                json={
                    "topology_id": TOPO_ID,
                    "artifact_id": artifact["artifact_id"],
                    "target_services": [GW_ID],
                    "env_key": ENV,
                },
            )
            self.assertEqual(release.status_code, 201, release.get_data(as_text=True))
            release_id = release.get_json()["data"]["server_release_id"]
            self.assertEqual(release.get_json()["data"]["status"], "ready")

            deployed = self.client.post(f"/api/admin/projects/{TOPO_PROJECT}/server-releases/{release_id}/deploy")
            self.assertEqual(deployed.status_code, 200, deployed.get_data(as_text=True))
            self.assertEqual(deployed.get_json()["data"]["status"], "deploying")

            pulled = self.client.post(
                "/api/ops-platform/agent/pull",
                json={"node_id": GW_ID, "agent_id": AGENT_ID, "token": TOKEN, "limit": 5},
                headers={"X-Agent-Token": TOKEN},
            )
            self.assertEqual(pulled.status_code, 200, pulled.get_data(as_text=True))
            jobs = pulled.get_json().get("jobs") or []
            self.assertTrue(jobs, pulled.get_data(as_text=True))
            job = next(item for item in jobs if item.get("action_type") == "deploy_server_artifact")

            reported = self.client.post(
                "/api/ops-platform/agent/report",
                json={
                    "node_id": GW_ID,
                    "agent_id": AGENT_ID,
                    "token": TOKEN,
                    "job_id": job["job_id"],
                    "status": "SUCCESS",
                    "result": {"message": "测试部署完成"},
                },
                headers={"X-Agent-Token": TOKEN},
            )
            self.assertEqual(reported.status_code, 200, reported.get_data(as_text=True))
            self.assertEqual(reported.get_json().get("server_release", {}).get("status"), "deployed")
            self.assertEqual(read_server_release(TOPO_PROJECT, release_id).get("status"), "deployed")

            active = self.client.get(
                "/api/ops-platform/runtime/active",
                query_string={"project_id": TOPO_PROJECT, "env_key": ENV, "topology_id": TOPO_ID},
            )
            self.assertEqual(active.status_code, 200, active.get_data(as_text=True))
            self.assertIn("active", active.get_json())

            summary = self.client.get(
                "/api/ops-platform/diagnostics/summary",
                query_string={"project_id": TOPO_PROJECT, "env_key": ENV},
            )
            self.assertEqual(summary.status_code, 200, summary.get_data(as_text=True))
            self.assertTrue(summary.get_json())

            frozen = self.client.post(
                "/api/ops-platform/change-governance/freeze",
                json={"project_id": TOPO_PROJECT, "active": True, "reason": "测试冻结"},
            )
            self.assertEqual(frozen.status_code, 200, frozen.get_data(as_text=True))
            thawed = self.client.post(
                "/api/ops-platform/change-governance/freeze",
                json={"project_id": TOPO_PROJECT, "active": False, "reason": "测试解除"},
            )
            self.assertEqual(thawed.status_code, 200, thawed.get_data(as_text=True))

            removed = self.client.post(
                "/api/ops-platform/topology/node/delete",
                json={"project_id": TOPO_PROJECT, "env_key": ENV, "topology_id": TOPO_ID, "node_id": BIZ_ID},
            )
            self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True))
            left = {node.get("id") for node in (removed.get_json().get("topology") or {}).get("nodes") or []}
            self.assertNotIn(BIZ_ID, left)
        finally:
            self._drop_nodes()

    def test_baas_service_announce_mail_and_bootstrap(self):
        page = self.client.get(f"/admin/projects/{BAAS_PROJECT}/casual-services")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True)[:300])

        opened = self.client.post(
            f"/api/projects/{BAAS_PROJECT}/baas/services",
            json={"env_key": ENV},
        )
        self.assertEqual(opened.status_code, 201, opened.get_data(as_text=True))
        service = opened.get_json()["data"]["service"]
        service_id = service["service_id"]
        self.addCleanup(lambda: delete_service(BAAS_PROJECT, service_id))

        renamed = self.client.patch(
            f"/api/projects/{BAAS_PROJECT}/baas/services/{service_id}",
            json={"description": "测试休闲服务说明"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.get_data(as_text=True))
        self.assertEqual(renamed.get_json()["data"]["description"], "测试休闲服务说明")

        announcement = self.client.post(
            f"/api/projects/{BAAS_PROJECT}/baas/services/{service_id}/announcements",
            json={"title": "停机公告", "body": "测试公告", "status": "published"},
        )
        self.assertEqual(announcement.status_code, 200, announcement.get_data(as_text=True))
        self.assertEqual(announcement.get_json()["data"]["title"], "停机公告")

        mail = self.client.post(
            f"/api/projects/{BAAS_PROJECT}/baas/services/{service_id}/mail",
            json={"player_id": "player-test", "title": "补偿", "body": "测试邮件"},
        )
        self.assertEqual(mail.status_code, 200, mail.get_data(as_text=True))
        self.assertTrue(mail.get_json()["data"].get("mail_id"))

        boot = self.client.get(
            "/api/public/client-bootstrap",
            query_string={
                "game_id": "plane-baas-game",
                "game_key": "plane-baas-key",
                "env": ENV,
            },
        )
        self.assertEqual(boot.status_code, 200, boot.get_data(as_text=True))
        self.assertEqual(boot.get_json().get("framework"), "casual_baas")
        payload = client_bootstrap(BAAS_PROJECT, ENV, "plane-baas-game", "plane-baas-key")
        self.assertIn("public_api_base", payload)

        svc, _secret = open_service(BAAS_PROJECT, ENV, "admin")
        self.assertEqual(svc["service_id"], service_id)
        row = publish_announcement(service_id, "第二条", "平面入口", "admin")
        self.assertEqual(row["title"], "第二条")
        sent = send_player_mail(service_id, "player-test", "再一封", "平面入口", "admin")
        self.assertTrue(sent.get("mail_id"))

    def test_framework_modules_stay_split(self):
        from server_frameworks.registry import client_module_for_project, server_module_for_project

        self.assertEqual(server_module_for_project(TOPO_PROJECT), "topology_server")
        self.assertEqual(client_module_for_project(TOPO_PROJECT), "topology_client")
        self.assertEqual(server_module_for_project(BAAS_PROJECT), "casual_baas_server")
        self.assertEqual(client_module_for_project(BAAS_PROJECT), "baas_client")
        import services.ops.helpers as helpers
        import services.ops.page_shell as page_shell
        self.assertIs(helpers._render_ops_page, page_shell._render_ops_page)
        self.assertTrue(callable(helpers._list_topologies))
        self.assertTrue(callable(helpers._spawn_runtime_start_orchestration))

    def _add_node(self, node_id: str, preset_id: str, name: str, x: int, y: int) -> dict:
        resp = self.client.post(
            "/api/ops-platform/node/add-from-preset",
            json={
                "id": node_id,
                "preset_id": preset_id,
                "name": name,
                "project_id": TOPO_PROJECT,
                "env_key": ENV,
                "topology_id": TOPO_ID,
                "ops_write_key": TOKEN,
                "x": x,
                "y": y,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return resp.get_json()

    def _cleanup_topology(self):
        if _topology_id_exists(TOPO_ID):
            close_topology(TOPO_ID)


if __name__ == "__main__":
    unittest.main()
