# -*- coding: utf-8 -*-
"""Internal ops dependency injection — direct submodule imports (Plan P1-01 Step 6)."""

from __future__ import annotations

from services.ops import cross_bind

cross_bind.wire_all()

from services.ops import (  # noqa: E402
    agent_registry,
    agent_service,
    cluster_importer,
    diagnostics,
    runtime_orchestrator,
    runtime_service,
    shared_bootstrap,
    storage,
    topology_contracts,
    topology_registry,
    topology_service,
)

for _mod in (
    shared_bootstrap,
    storage,
    topology_service,
    runtime_service,
    cluster_importer,
    topology_contracts,
    topology_registry,
    agent_registry,
    agent_service,
    runtime_orchestrator,
    diagnostics,
):
    for _name, _val in vars(_mod).items():
        if _name.startswith("__"):
            continue
        globals()[_name] = _val

del _mod, _name, _val, cross_bind
