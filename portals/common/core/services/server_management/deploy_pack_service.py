# -*- coding: utf-8 -*-
"""Build downloadable server architecture deployment zip packages."""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime
from typing import Dict, List, Tuple

_CORE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_CORE_DIR, "..", "..", ".."))

_SKIP_PARTS = {"__pycache__", ".pytest_cache", "node_modules", ".git", "jenkins-clone"}


def _repo_root() -> str:
    return _REPO_ROOT


def _add_path(zf: zipfile.ZipFile, abs_path: str, arc_prefix: str = "") -> int:
    count = 0
    if not os.path.exists(abs_path):
        return 0
    if os.path.isfile(abs_path):
        arc = os.path.join(arc_prefix, os.path.basename(abs_path)).replace("\\", "/")
        zf.write(abs_path, arc)
        return 1
    for dirpath, dirnames, filenames in os.walk(abs_path):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_PARTS and not d.startswith(".")]
        for name in filenames:
            if name.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, _repo_root())
            if arc_prefix:
                rel = os.path.join(arc_prefix, rel).replace("\\", "/")
            rel = rel.replace("\\", "/")
            zf.write(full, rel)
            count += 1
    return count


def _pack_manifest(kind: str) -> Dict[str, str]:
    if kind == "topology":
        return {
            "architecture": "topology_server",
            "label": "中重度拓扑服务器架构",
            "entry_script": "scripts/Start-DevStack.ps1",
            "env": "PORTAL_SERVER_FRAMEWORKS=topology",
            "client_package": "packages/client_network/topology",
            "bootstrap": "/api/public/client-bootstrap",
            "bootstrap_legacy": "/api/public/runtime-bootstrap",
        }
    return {
        "architecture": "casual_baas_server",
        "label": "轻度 BaaS 服务器架构",
        "entry_script": "scripts/Start-BaaSStack.ps1",
        "env": "PORTAL_SERVER_FRAMEWORKS=baas",
        "client_package": "packages/client_network/baas",
        "bootstrap": "/api/public/client-bootstrap",
        "bootstrap_legacy": "/api/public/baas-bootstrap",
    }


def _topology_paths() -> List[str]:
    return [
        "scripts/Start-DevStack.ps1",
        "scripts/Sync-DevStackClientConfig.ps1",
        "scripts/Stop-Portal5003.ps1",
        "scripts/Start-Portal5003.ps1",
        "scripts/Export-ClientNetworkModule.ps1",
        "scripts/Import-ClientNetworkModule.ps1",
        "packages/client_network/topology",
        "packages/client_network/common",
        "packages/client_network/stubs",
        "portals/common/core/server_frameworks",
        "portals/common/core/routes/ops",
        "portals/common/core/services/ops",
        "portals/common/core/services/release/topology_binding_service.py",
        "portals/common/core/services/server_mode.py",
        "portals/common/core/requirements-prod.txt",
        "portals/common/core/requirements.txt",
        "docs/design_specs/server_framework_modules.md",
        "docs/design_specs/topology_binding_architecture.md",
        "docs/runbooks/topology_server_deploy.md",
        "docs/runbooks/topology_server_deploy_step_by_step.md",
        "docs/runbooks/deploy_architecture.md",
    ]


def _baas_paths() -> List[str]:
    return [
        "scripts/Start-BaaSStack.ps1",
        "docker-compose.baas.yml",
        "portals/common/core/app_baas.py",
        "portals/common/core/scripts/run_baas_server.ps1",
        "portals/common/core/scripts/run_baas_pvp_fanout_e2e.py",
        "portals/common/core/scripts/seed_baas_playmode_e2e.py",
        "portals/common/core/scripts/run_baas_playmode_e2e.py",
        "packages/client_network/baas",
        "packages/client_network/common",
        "packages/client_network/stubs",
        "scripts/Export-ClientNetworkModule.ps1",
        "scripts/Import-ClientNetworkModule.ps1",
        "portals/common/core/server_frameworks",
        "portals/common/core/routes/baas",
        "portals/common/core/services/baas",
        "portals/common/core/models/baas_migrations.py",
        "portals/common/core/services/server_mode.py",
        "portals/common/core/requirements-prod.txt",
        "portals/common/core/requirements.txt",
        "docs/design_specs/server_framework_modules.md",
        "docs/design_specs/casual_baas_services.md",
        "docs/design_specs/casual_baas_pvp_mvp_boundary.md",
        "docs/runbooks/baas_standalone_deploy.md",
        "docs/runbooks/baas_server_deploy_step_by_step.md",
        "docs/runbooks/deploy_architecture.md",
        "docs/evidence/baas-playmode-e2e-latest.json",
    ]


def _readme_text(kind: str) -> str:
    meta = _pack_manifest(kind)
    lines = [
        f"# {meta['label']} — 部署包",
        "",
        f"生成时间: {datetime.utcnow().replace(microsecond=0).isoformat()}Z",
        "",
        "## 快速开始",
        "",
    ]
    if kind == "topology":
        lines.extend([
            "1. 解压到 apk-site 仓库根目录（与 portals/、scripts/ 同级合并）。",
            "2. 安装 Python 依赖后启动 Portal：",
            "   ```powershell",
            "   powershell -ExecutionPolicy Bypass -File scripts\\Start-DevStack.ps1 -SkipGameServer",
            "   ```",
            "3. 同步客户端拓扑网络模块：",
            "   ```powershell",
            "   powershell -ExecutionPolicy Bypass -File scripts\\Sync-DevStackClientConfig.ps1 -Mode topology",
            "   ```",
            "4. Portal 管理入口：服务器管理 → 中重度服务器",
        ])
    else:
        lines.extend([
            "1. 解压到 apk-site 仓库根目录（与 portals/、scripts/ 同级合并）。",
            "2. 一键启动独立 BaaS：",
            "   ```powershell",
            "   powershell -ExecutionPolicy Bypass -File scripts\\Start-BaaSStack.ps1 -Background",
            "   ```",
            "3. 可选 PostgreSQL：添加 `-UsePostgres`",
            "4. 同步客户端 BaaS 模块：",
            "   ```powershell",
            "   powershell -ExecutionPolicy Bypass -File scripts\\Sync-DevStackClientConfig.ps1 -Mode baas",
            "   ```",
            "5. 默认地址：http://127.0.0.1:5004/admin/baas",
        ])
    lines.extend([
        "",
        "## 环境变量",
        "",
        f"- `{meta['env']}`",
        f"- Bootstrap: `{meta['bootstrap']}`",
        f"- 客户端包: `{meta['client_package']}`",
        "",
        "详细逐步教程（必读）：",
        "",
    ])
    if kind == "topology":
        lines.append("- `docs/runbooks/topology_server_deploy_step_by_step.md`")
    else:
        lines.append("- `docs/runbooks/baas_server_deploy_step_by_step.md`")
    lines.extend([
        "",
        "速查 Runbook 见 docs/runbooks/ 与 docs/design_specs/。",
    ])
    return "\n".join(lines) + "\n"


def build_deploy_pack(kind: str) -> Tuple[bytes, str]:
    kind = str(kind or "").strip().lower()
    if kind not in ("topology", "baas"):
        raise ValueError("kind 须为 topology 或 baas")
    paths = _topology_paths() if kind == "topology" else _baas_paths()
    buf = io.BytesIO()
    added = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("DEPLOY_README.md", _readme_text(kind))
        import json

        zf.writestr("manifest.json", json.dumps(_pack_manifest(kind), ensure_ascii=False, indent=2))
        for rel in paths:
            abs_path = os.path.join(_repo_root(), rel.replace("/", os.sep))
            added += _add_path(zf, abs_path)
        if added == 0:
            raise RuntimeError("部署包为空，请确认仓库路径完整")
    filename = f"{'topology' if kind == 'topology' else 'baas'}-server-architecture.zip"
    return buf.getvalue(), filename


def deploy_pack_info(kind: str) -> Dict[str, str]:
    kind = str(kind or "").strip().lower()
    meta = _pack_manifest(kind)
    meta["download_url"] = f"/api/server-management/deploy-pack/{kind}"
    meta["filename"] = f"{'topology' if kind == 'topology' else 'baas'}-server-architecture.zip"
    return meta
