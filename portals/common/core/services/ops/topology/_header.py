"""Topology CRUD, scoped load/save, bindings."""
from __future__ import annotations
from services.ops import shared_bootstrap as _boot
globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})
from services.ops.topology_service import (
    _default_env_options,
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
from services.ops.cluster_importer import _load_cluster_json
