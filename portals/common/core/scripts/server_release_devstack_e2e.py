#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real DevStack server release E2E — no enqueue mock; Agent daemon required."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

DEFAULT_BASE = os.getenv("RELEASE_GATE_BASE_URL", "http://127.0.0.1:5003")
DEFAULT_PROJECT = os.getenv("SERVER_E2E_PROJECT_ID", "GomeKu")
POLL_SEC = float(os.getenv("SERVER_E2E_POLL_SEC", "2"))
TIMEOUT_SEC = float(os.getenv("SERVER_E2E_TIMEOUT_SEC", "120"))


def _fail(msg: str, code: int = 1) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return code


def _health(base: str) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/health", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _preflight_agent_pull(base: str) -> None:
    """Fail fast when Portal returns jobs without action_type (stale multi-instance)."""
    import urllib.request

    body = json.dumps(
        {
            "node_id": "ops-cn-1",
            "agent_id": "agent-local-cn-1",
            "limit": 1,
            "token": os.getenv("AGENT_TOKEN", "ops-write-key-2026"),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/ops-platform/agent/pull",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Agent-Token": os.getenv("AGENT_TOKEN", "ops-write-key-2026"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"agent pull preflight failed: {exc}") from exc
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if str(job.get("status") or "").upper() in ("SUCCESS", "FAILED", "CANCELED"):
            continue
        if not str(job.get("action_type") or "").strip():
            raise RuntimeError(
                "agent pull returned job without action_type — run scripts/Stop-Portal5003.ps1 "
                "then scripts/Start-Portal5003.ps1 -Background (duplicate stale Portal on :5003)"
            )


def _start_agent_daemon(base: str) -> subprocess.Popen:
    daemon = ROOT / "tools" / "canonical_local_agent_daemon.py"
    env = os.environ.copy()
    env.setdefault("RELEASE_GATE_BASE_URL", base)
    proc = subprocess.Popen(
        [sys.executable, str(daemon), "--daemon", "--base", base],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(3)
    if proc.poll() is not None:
        err = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"agent daemon exited early: {err}")
    return proc


def _register_agent_topology(base: str, project_id: str) -> None:
    sys.path.insert(0, str(ROOT))
    from dev.tools.ops_ecosystem_chain import (
        _cluster_agents,
        _load_cluster,
        _resolve_game_server_repo,
        step_agent_protocol_register,
    )

    repo = _resolve_game_server_repo(os.getenv("GAME_SERVER_REPO", ""))
    agents = _cluster_agents(_load_cluster(repo))
    step_agent_protocol_register(base, agents, project_id)


def _make_artifact_bundle() -> str:
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("game-cn-1/version.txt", f"e2e-{int(time.time())}")
        zf.writestr("game-cn-1/appsettings.json", "{}")
    return path


def _run_flow(project_id: str, base: str) -> Dict[str, Any]:
    os.environ.setdefault("USE_SQLITE", "true")
    from app_new import app
    from models.db import init_db
    from services.release import server_artifact_service as sas
    from services.release import server_release_service as srs

    init_db()
    bundle = _make_artifact_bundle()
    try:
        with app.app_context():
            with app.test_request_context(base_url=base):
                art = sas.register_artifact(
                    project_id,
                    {"version_label": "e2e-agent", "notes": "server_release_devstack_e2e"},
                    source_path=bundle,
                )
                sr = srs.create_server_release(
                    project_id,
                    {
                        "artifact_id": art["artifact_id"],
                        "target_services": ["game-cn-1"],
                        "env_key": "development",
                        "topology_id": "topology-gomeku-development-default",
                    },
                    actor="e2e",
                )
                release_id = sr["server_release_id"]
                deployed = srs.deploy_server_release(project_id, release_id, actor="e2e")
                if str(deployed.get("status") or "") not in ("deploying", "deployed"):
                    raise RuntimeError(f"unexpected status after deploy enqueue: {deployed.get('status')}")

                deadline = time.time() + TIMEOUT_SEC
                final: Optional[Dict[str, Any]] = None
                while time.time() < deadline:
                    row = srs.get_server_release(project_id, release_id) or {}
                    status = str(row.get("status") or "")
                    if status in ("deployed", "failed"):
                        final = row
                        break
                    time.sleep(POLL_SEC)
                if not final:
                    raise TimeoutError(f"release {release_id} not terminal within {TIMEOUT_SEC}s")
                if final.get("status") != "deployed":
                    raise RuntimeError(f"release failed: {json.dumps(final, ensure_ascii=False)[:500]}")
                payload = final.get("payload") if isinstance(final.get("payload"), dict) else {}
                results = payload.get("deploy_results") if isinstance(payload.get("deploy_results"), dict) else {}
                game_result = results.get("game-cn-1") or {}
                if not game_result.get("ok"):
                    raise RuntimeError(f"game-cn-1 deploy_result not ok: {game_result}")
                return {
                    "server_release_id": release_id,
                    "status": final.get("status"),
                    "deploy_results": results,
                    "artifact_id": art.get("artifact_id"),
                }
    finally:
        try:
            os.remove(bundle)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Real server release DevStack E2E")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT)
    parser.add_argument("--skip-agent-start", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    if not _health(base):
        return _fail(f"Portal not healthy at {base} — start DevStack first")

    try:
        _preflight_agent_pull(base)
    except RuntimeError as exc:
        return _fail(str(exc))

    agent_proc: Optional[subprocess.Popen] = None
    try:
        _register_agent_topology(base, args.project_id)
        if not args.skip_agent_start:
            agent_proc = _start_agent_daemon(base)
        result = _run_flow(args.project_id, base)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        if args.write_evidence:
            from scripts.closure_evidence import write_evidence

            write_evidence(
                "GAP-P2-01-E2E-01",
                command=f"server_release_devstack_e2e.py --base-url {base}",
                exit_code=0,
                status="DONE",
                notes=json.dumps(result, ensure_ascii=False),
            )
            write_evidence(
                "GAP-P2-01-REV-01",
                command=f"server_release_devstack_e2e.py --base-url {base}",
                exit_code=0,
                status="DONE",
            )
            write_evidence(
                "GAP-P2-01-OUT-01",
                command="gameserver_agent_exec + complete-server-deploy",
                exit_code=0,
                status="DONE",
            )
        print("server_release_devstack_e2e PASS")
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if agent_proc and agent_proc.poll() is None:
            agent_proc.terminate()
            try:
                agent_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                agent_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
