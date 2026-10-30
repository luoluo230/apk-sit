# -*- coding: utf-8 -*-
"""Ops platform thin facade — re-exports domain modules. Plan P1-01."""

from __future__ import annotations

from services.ops.agent_service import _default_agent_policy, _load_agent_policy, _save_agent_policy
from services.ops.page_shell import (
    _allow_gm_execute,
    _allow_ops_execute,
    _allow_ops_view,
    _ops_csrf_token,
    _render_local_template,
    _render_ops_page,
    _render_page,
    _render_standalone_page,
    _session_username,
)
from services.ops.runtime_service import _runtime_active_for_scope
from services.ops import shared_bootstrap as _boot

globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})
from services.ops.topology_service import (
    _env_label,
    _load_topology_contents,
    _load_topology_registry,
    _normalize_env_key,
    _runtime_default_topology_id,
    _save_topology_contents,
    _save_topology_registry,
    _scope_binding_key,
    _topology_content_counts,
)


def _merge_ops_module(mod) -> None:
    globals().update({k: getattr(mod, k) for k in dir(mod) if not k.startswith("__")})


import services.ops.diagnostics as _ops_diagnostics
import services.ops.topology_contracts as _ops_topology_contracts
import services.ops.cluster_importer as _ops_cluster_importer
import services.ops.topology_registry as _ops_topology_registry
import services.ops.agent_registry as _ops_agent_registry
import services.ops.runtime_orchestrator as _ops_runtime_orchestrator

for _mod in (
    _ops_diagnostics,
    _ops_topology_contracts,
    _ops_cluster_importer,
    _ops_topology_registry,
    _ops_agent_registry,
    _ops_runtime_orchestrator,
):
    _merge_ops_module(_mod)

from services.ops import cross_bind

cross_bind.wire_all()
for _mod in (
    _ops_diagnostics,
    _ops_topology_contracts,
    _ops_cluster_importer,
    _ops_topology_registry,
    _ops_agent_registry,
    _ops_runtime_orchestrator,
):
    _merge_ops_module(_mod)

del _mod, _merge_ops_module, cross_bind

__all__ = []
